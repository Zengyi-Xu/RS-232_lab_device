"""Lab Engine Setup 框图编辑器面板。

提供基于 tk.Canvas 的可视化节点编辑器：
- 工具栏添加 Host / Comm / Instrument / Routine 节点
- 拖拽移动节点
- 在端口之间连线（贝塞尔曲线）
- 画布缩放、平移、网格吸附
- 属性面板编辑节点参数
- 保存/加载 .labsetup.json
- 一键同步到 Run tab
"""
import math
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Dict, List, Optional, Tuple

from lab_engine.core.registry import InstrumentRegistry, RoutineRegistry
from lab_engine.core.setup_graph import (
    NODE_HEIGHT,
    NODE_WIDTH,
    PORT_RADIUS,
    Node,
    SetupGraph,
)
from lab_engine.gui.shell import (
    COLOR_BG,
    COLOR_CARD,
    COLOR_PRIMARY,
    COLOR_TEXT_DIM,
    UI_FONT,
    dpi_scale,
)


# 节点类型配色
NODE_COLORS = {
    "host": "#3B82F6",      # 蓝
    "comm": "#8B5CF6",      # 紫
    "instrument": "#10B981",  # 绿
    "routine": "#F59E0B",   # 橙
}

# 端口类型配色
PORT_COLORS = {
    "control": "#EF4444",   # 红
    "comm": "#EAB308",      # 黄
    "data": "#22C55E",      # 绿
    "any": "#64748B",       # 灰
}

GRID_SIZE = 20


class SetupPanel(ttk.Frame):
    """Setup 框图编辑器。"""

    def __init__(
        self,
        parent,
        routine_registry: RoutineRegistry,
        on_apply: Optional[Callable[[SetupGraph], None]] = None,
        scale: float = 1.0,
    ):
        super().__init__(parent)
        self.routine_registry = routine_registry
        self.on_apply = on_apply
        self.scale = scale

        self.graph = SetupGraph()
        self.selected_node_id: Optional[str] = None
        self._drag_node_id: Optional[str] = None
        self._drag_start: Optional[Tuple[float, float]] = None
        self._edge_start: Optional[Tuple[str, str]] = None
        self._temp_edge_line: Optional[int] = None
        self._temp_edge_coords: Optional[Tuple[float, float, float, float]] = None

        # 画布状态
        self.zoom = 1.0
        self.pan_start: Optional[Tuple[float, float]] = None
        self._space_pressed = False
        self._panning = False

        # canvas item 缓存
        self._node_items: Dict[str, Dict[str, Any]] = {}
        self._edge_items: Dict[str, int] = {}
        self._grid_items: List[int] = []

        self._prop_vars: Dict[str, tk.Variable] = {}
        self._prop_widgets: List[tk.Widget] = []

        self._build_ui()
        self._bind_events()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _build_ui(self):
        # 顶部工具栏
        toolbar = tk.Frame(self, bg=COLOR_BG)
        toolbar.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(toolbar, text="Setup 框图", style="Title.TLabel").pack(side=tk.LEFT)

        ttk.Button(toolbar, text="+ 上位机", command=lambda: self._add_node("host")).pack(
            side=tk.LEFT, padx=(16, 4)
        )
        ttk.Button(toolbar, text="+ 通信", command=lambda: self._add_node("comm")).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(toolbar, text="+ 仪器", command=lambda: self._add_node("instrument")).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(toolbar, text="+ 例程", command=lambda: self._add_node("routine")).pack(
            side=tk.LEFT, padx=4
        )

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Button(toolbar, text="新建", command=self._new_graph).pack(side=tk.LEFT, padx=4)
        ttk.Button(toolbar, text="打开", command=self._load_graph).pack(side=tk.LEFT, padx=4)
        ttk.Button(toolbar, text="保存", command=self._save_graph).pack(side=tk.LEFT, padx=4)

        # 主区域：canvas + 属性面板
        body = tk.Frame(self, bg=COLOR_BG)
        body.pack(fill=tk.BOTH, expand=True)

        # Canvas 容器（带滚动条）
        canvas_frame = tk.Frame(body, bg=COLOR_BG)
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(
            canvas_frame,
            bg=COLOR_BG,
            highlightthickness=1,
            highlightbackground="#CBD5E1",
            scrollregion=(0, 0, dpi_scale(4000, self.scale), dpi_scale(3000, self.scale)),
        )
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        vbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)
        hbar = ttk.Scrollbar(self, orient=tk.HORIZONTAL, command=self.canvas.xview)
        hbar.pack(fill=tk.X)
        self.canvas.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set)

        # 网格背景
        self._draw_grid()

        # 画布帮助文本（无边框，随画布滚动）
        self._draw_help_text()

        # 小地图
        self._build_minimap()

        # 属性面板（可滚动）
        prop_card = tk.Frame(body, bg=COLOR_CARD,
                             highlightbackground="#E2E8F0", highlightthickness=1, bd=0)
        prop_card.pack(side=tk.RIGHT, fill=tk.Y, padx=(8, 0))
        prop_card.pack_propagate(False)
        prop_card.configure(width=dpi_scale(300, self.scale))

        prop_inner = tk.Frame(prop_card, bg=COLOR_CARD)
        prop_inner.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)

        ttk.Label(prop_inner, text="属性", style="Section.TLabel").pack(anchor=tk.W, pady=(0, 8))

        # 可滚动属性区域
        self.prop_canvas = tk.Canvas(
            prop_inner,
            bg=COLOR_CARD,
            highlightthickness=0,
            width=dpi_scale(260, self.scale),
        )
        prop_vsb = ttk.Scrollbar(prop_inner, orient=tk.VERTICAL, command=self.prop_canvas.yview)
        self.prop_canvas.configure(yscrollcommand=prop_vsb.set)
        prop_vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.prop_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.prop_frame = tk.Frame(self.prop_canvas, bg=COLOR_CARD)
        self.prop_canvas.create_window((0, 0), window=self.prop_frame, anchor="nw",
                                        width=dpi_scale(260, self.scale))
        self.prop_frame.bind(
            "<Configure>",
            lambda _e: self.prop_canvas.configure(scrollregion=self.prop_canvas.bbox("all"))
        )

        ttk.Label(prop_inner, text="提示: 选中节点后编辑属性，拖拽端口连线。\nCtrl+滚轮缩放，空格+左键平移。",
                  wraplength=dpi_scale(260, self.scale), style="DimCard.TLabel").pack(
            side=tk.BOTTOM, anchor=tk.W, pady=(8, 0)
        )

        # 底部操作栏
        footer = tk.Frame(self, bg=COLOR_BG)
        footer.pack(fill=tk.X, pady=(8, 0))
        self.apply_btn = ttk.Button(
            footer, text="应用到运行配置", style="Accent.TButton", command=self._apply_to_run
        )
        self.apply_btn.pack(side=tk.RIGHT)
        self.status_lbl = ttk.Label(footer, text="就绪")
        self.status_lbl.pack(side=tk.LEFT)

    def _build_minimap(self):
        """右下角小地图。"""
        self.minimap = tk.Canvas(
            self.canvas,
            width=dpi_scale(160, self.scale),
            height=dpi_scale(120, self.scale),
            bg="#E2E8F0",
            highlightthickness=1,
            highlightbackground="#CBD5E1",
        )
        # 固定在 canvas 右下角，不随内容滚动
        self.minimap.place(relx=1.0, rely=1.0, anchor=tk.SE, x=-8, y=-8)

    def _draw_help_text(self):
        """在画布左上角绘制帮助文本。"""
        help_lines = [
            "Setup 框图使用说明",
            "",
            "1. 点击顶部按钮添加节点（上位机/通信/仪器/例程）",
            "2. 拖拽节点移动位置（自动吸附到网格）",
            "3. 从输出端口拖到输入端口创建连线",
            "4. 选中节点后可在右侧编辑属性",
            "5. Delete 删除选中节点",
            "",
            "快捷键：",
            "  Ctrl + 滚轮  —— 缩放画布",
            "  空格 + 左键  —— 平移画布",
            "  中键拖拽     —— 平移画布",
            "",
            "节点关系：上位机 → 通信接口 → 仪器 → 例程",
        ]
        x, y = self._to_screen(30, 30)
        line_h = self._to_screen_scalar(18)
        for i, line in enumerate(help_lines):
            if i == 0:
                font = (UI_FONT, max(8, int(10 * self.zoom * self.scale)), "bold")
                fill = COLOR_PRIMARY
            elif line == "":
                continue
            elif line.startswith("  "):
                font = (UI_FONT, max(6, int(8 * self.zoom * self.scale)))
                fill = COLOR_TEXT_DIM
            else:
                font = (UI_FONT, max(6, int(9 * self.zoom * self.scale)))
                fill = "#475569"
            self.canvas.create_text(
                x, y + i * line_h,
                text=line, font=font, fill=fill,
                anchor=tk.NW,
                tags=("help_text",),
            )

    def _draw_grid(self):
        """绘制网格背景（随 zoom/scale 变化）。"""
        for item in self._grid_items:
            self.canvas.delete(item)
        self._grid_items.clear()

        step = self._to_screen_scalar(GRID_SIZE)
        width = self.canvas.winfo_screenwidth() * 2
        height = self.canvas.winfo_screenheight() * 2
        for x in range(0, int(width), max(1, int(step))):
            for y in range(0, int(height), max(1, int(step))):
                item = self.canvas.create_oval(
                    x - 1, y - 1, x + 1, y + 1,
                    fill="#E2E8F0", outline="",
                )
                self._grid_items.append(item)
        self.canvas.tag_lower("grid")
        for item in self._grid_items:
            self.canvas.addtag_withtag("grid", item)

    def _bind_events(self):
        self.canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<ButtonPress-2>", self._on_middle_press)
        self.canvas.bind("<B2-Motion>", self._on_middle_drag)
        self.canvas.bind("<ButtonRelease-2>", self._on_middle_release)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.bind_all("<KeyPress-space>", self._on_space_press)
        self.bind_all("<KeyRelease-space>", self._on_space_release)
        self.bind_all("<Delete>", self._on_delete_key)
        self.bind_all("<BackSpace>", self._on_delete_key)

    # ------------------------------------------------------------------
    # 节点与图操作
    # ------------------------------------------------------------------
    def _add_node(self, node_type: str):
        # 在画布中心附近添加，避免总是重叠
        x = self.canvas.canvasx(self.canvas.winfo_width() / 2) / self.zoom
        y = self.canvas.canvasy(self.canvas.winfo_height() / 2) / self.zoom
        x += (len(self.graph.nodes) % 5) * 40
        y += (len(self.graph.nodes) % 3) * 140
        node = self.graph.add_node(node_type, x, y)
        self._init_node_defaults(node)
        self._draw_node(node)
        self._select_node(node.node_id)
        self._set_status(f"添加节点: {node.label}")
        self._update_minimap()

    def _init_node_defaults(self, node: Node):
        if node.node_type == "comm":
            node.data.setdefault("protocol", "RS-232")
            node.data.setdefault("address", "COM1")
            node.data.setdefault("port", 9600)
        elif node.node_type == "instrument":
            keys = InstrumentRegistry.keys()
            node.data.setdefault("instrument_key", keys[0] if keys else "keithley2400")
            node.data.setdefault("alias", f"inst_{len(self.graph.nodes)}")
            self._rebuild_instrument_ports(node)
        elif node.node_type == "routine":
            names = self.routine_registry.names()
            node.data.setdefault("routine_name", names[0] if names else "")
            self._rebuild_routine_ports(node)

    def _rebuild_instrument_ports(self, node: Node):
        from lab_engine.core.setup_graph import Port
        node.ports = [
            Port("comm", "通信", "input", "comm"),
            Port("data", "数据", "output", "data"),
        ]

    def _rebuild_routine_ports(self, node: Node):
        from lab_engine.core.setup_graph import Port
        routine_name = node.data.get("routine_name", "")
        routine = self.routine_registry.get(routine_name)
        ports = []
        if routine:
            for alias in routine.instruments.keys():
                ports.append(Port(f"inst_{alias}", alias, "input", "data"))
        else:
            ports.append(Port("inst_a", "仪器 A", "input", "data"))
        node.ports = ports

    def _remove_node(self, node_id: str):
        self.graph.remove_node(node_id)
        self._erase_node(node_id)
        for edge_id in list(self._edge_items.keys()):
            if edge_id not in self.graph.edges:
                self._erase_edge(edge_id)
        if self.selected_node_id == node_id:
            self.selected_node_id = None
            self._clear_property_panel()
        self._redraw_all_edges()
        self._update_minimap()

    def _remove_edge(self, edge_id: str):
        self.graph.remove_edge(edge_id)
        self._erase_edge(edge_id)
        self._update_minimap()

    # ------------------------------------------------------------------
    # Canvas 绘制
    # ------------------------------------------------------------------
    def _round_rect(self, x1, y1, x2, y2, r=8, **kwargs):
        """绘制圆角矩形。"""
        points = [
            x1 + r, y1,
            x2 - r, y1,
            x2, y1,
            x2, y1 + r,
            x2, y2 - r,
            x2, y2,
            x2 - r, y2,
            x1 + r, y2,
            x1, y2,
            x1, y2 - r,
            x1, y1 + r,
            x1, y1,
        ]
        return self.canvas.create_polygon(points, smooth=True, **kwargs)

    def _node_size(self, node: Node) -> Tuple[float, float]:
        """计算节点逻辑尺寸（不随 DPI / zoom 缩放）。"""
        n_ports = max(2, len(node.ports))
        w = NODE_WIDTH
        h = max(NODE_HEIGHT, 50 + n_ports * 28)
        return w, h

    def _to_screen(self, x: float, y: float) -> Tuple[float, float]:
        """把数据坐标转换为屏幕坐标（考虑 DPI 与 zoom）。"""
        return x * self.zoom * self.scale, y * self.zoom * self.scale

    def _to_screen_scalar(self, v: float) -> float:
        return v * self.zoom * self.scale

    def _from_screen(self, x: float, y: float) -> Tuple[float, float]:
        """把屏幕坐标转换为数据坐标。"""
        return x / (self.zoom * self.scale), y / (self.zoom * self.scale)

    def _draw_node(self, node: Node):
        self._erase_node(node.node_id)
        items: Dict[str, Any] = {"ports": {}, "labels": []}

        w, h = self._node_size(node)
        x, y = self._to_screen(node.x, node.y)
        zw, zh = self._to_screen_scalar(w), self._to_screen_scalar(h)
        r = self._to_screen_scalar(8)

        color = NODE_COLORS.get(node.node_type, COLOR_PRIMARY)

        # 节点主体
        rect = self._round_rect(
            x, y, x + zw, y + zh, r=r,
            fill=COLOR_CARD, outline="#CBD5E1", width=max(1, int(2 * self.zoom)),
            tags=(f"node:{node.node_id}", "node"),
        )
        items["rect"] = rect

        # 标题背景
        title_h = self._to_screen_scalar(24)
        title_rect = self._round_rect(
            x, y, x + zw, y + title_h, r=r,
            fill=color, outline="",
            tags=(f"node:{node.node_id}", "node_title_bg"),
        )
        items["title_bg"] = title_rect

        # 标题文字
        title_text = self.canvas.create_text(
            x + zw / 2, y + title_h / 2,
            text=node.label, fill="white",
            font=(UI_FONT, max(7, int(9 * self.zoom * self.scale)), "bold"),
            tags=(f"node:{node.node_id}", "node_title"),
        )
        items["title"] = title_text

        # 类型标签
        type_text = self.canvas.create_text(
            x + zw / 2, y + zh - self._to_screen_scalar(10),
            text=node.node_type, fill=COLOR_TEXT_DIM,
            font=(UI_FONT, max(6, int(8 * self.zoom * self.scale))),
            tags=(f"node:{node.node_id}", "node_type"),
        )
        items["type_label"] = type_text

        # 端口
        inputs = [p for p in node.ports if p.direction == "input"]
        outputs = [p for p in node.ports if p.direction == "output"]

        for port in inputs:
            px, py = self._port_position(node, port, h)
            px, py = self._to_screen(px, py)
            pr = self._to_screen_scalar(PORT_RADIUS)
            c = self.canvas.create_oval(
                px - pr, py - pr, px + pr, py + pr,
                fill=PORT_COLORS.get(port.data_type, "#64748B"),
                outline="white", width=max(1, int(2 * self.zoom)),
                tags=(f"port:{node.node_id}:{port.name}", "port"),
            )
            items["ports"][port.name] = c
            lbl = self.canvas.create_text(
                px + self._to_screen_scalar(10), py,
                text=port.label, fill=COLOR_TEXT_DIM,
                font=(UI_FONT, max(6, int(8 * self.zoom * self.scale))),
                anchor=tk.W, tags=(f"port_label:{node.node_id}:{port.name}",),
            )
            items["labels"].append(lbl)

        for port in outputs:
            px, py = self._port_position(node, port, h)
            px, py = self._to_screen(px, py)
            pr = self._to_screen_scalar(PORT_RADIUS)
            c = self.canvas.create_oval(
                px - pr, py - pr, px + pr, py + pr,
                fill=PORT_COLORS.get(port.data_type, "#64748B"),
                outline="white", width=max(1, int(2 * self.zoom)),
                tags=(f"port:{node.node_id}:{port.name}", "port"),
            )
            items["ports"][port.name] = c
            lbl = self.canvas.create_text(
                px - self._to_screen_scalar(10), py,
                text=port.label, fill=COLOR_TEXT_DIM,
                font=(UI_FONT, max(6, int(8 * self.zoom * self.scale))),
                anchor=tk.E, tags=(f"port_label:{node.node_id}:{port.name}",),
            )
            items["labels"].append(lbl)

        # 状态指示圆点
        status_map = self.graph.validate_status()
        status_info = status_map.get(node.node_id, {})
        status = status_info.get("status", "normal")
        if status != "normal":
            dot_r = max(3, int(4 * self.zoom))
            dot_x = x + zw - dot_r * 2
            dot_y = y + title_h + dot_r * 1.5
            dot_color = {"warning": "#EAB308", "error": "#EF4444"}.get(status, "#64748B")
            dot = self.canvas.create_oval(
                dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r,
                fill=dot_color, outline="white", width=max(1, int(1.5 * self.zoom)),
                tags=(f"status:{node.node_id}", "status_dot"),
            )
            items["status_dot"] = dot
            msg = status_info.get("message", "")
            if msg:
                msg_text = self.canvas.create_text(
                    dot_x - dot_r - 4, dot_y,
                    text=msg, fill=dot_color,
                    font=(UI_FONT, max(6, int(7 * self.zoom))),
                    anchor=tk.E,
                    tags=(f"status_msg:{node.node_id}", "status_msg"),
                )
                items["status_msg"] = msg_text

        self._node_items[node.node_id] = items
        self._update_node_selection_look(node.node_id)

    def _port_position(self, node: Node, port: Any, node_h: Optional[float] = None) -> Tuple[float, float]:
        """返回端口的逻辑坐标（未乘以 zoom/scale）。"""
        w, default_h = self._node_size(node)
        h = node_h if node_h is not None else default_h
        inputs = [p for p in node.ports if p.direction == "input"]
        outputs = [p for p in node.ports if p.direction == "output"]

        if port.direction == "input":
            idx = inputs.index(port)
            n = len(inputs)
            y = node.y + 30 + (idx + 1) * ((h - 40) / max(n, 1))
            return node.x, y
        else:
            idx = outputs.index(port)
            n = len(outputs)
            y = node.y + 30 + (idx + 1) * ((h - 40) / max(n, 1))
            return node.x + w, y

    def _erase_node(self, node_id: str):
        items = self._node_items.pop(node_id, {})
        for key, val in items.items():
            if key == "ports":
                for c in val.values():
                    self.canvas.delete(c)
            elif key == "labels":
                for lbl in val:
                    self.canvas.delete(lbl)
            else:
                self.canvas.delete(val)

    def _draw_edge(self, edge_id: str):
        self._erase_edge(edge_id)
        edge = self.graph.edges.get(edge_id)
        if edge is None:
            return
        src = self.graph.get_node(edge.source_node)
        dst = self.graph.get_node(edge.target_node)
        if src is None or dst is None:
            return
        src_port = src.port(edge.source_port)
        dst_port = dst.port(edge.target_port)
        if src_port is None or dst_port is None:
            return
        x1, y1 = self._port_position(src, src_port)
        x2, y2 = self._port_position(dst, dst_port)
        x1, y1 = self._to_screen(x1, y1)
        x2, y2 = self._to_screen(x2, y2)

        # 贝塞尔曲线：中点控制点
        cx = (x1 + x2) / 2
        color = PORT_COLORS.get(src_port.data_type, COLOR_PRIMARY)
        line = self.canvas.create_line(
            x1, y1, cx, y1, cx, y2, x2, y2,
            fill=color, width=max(1, int(2 * self.zoom)),
            smooth=True, splinesteps=24,
            tags=(f"edge:{edge_id}", "edge"),
        )
        self._edge_items[edge_id] = line
        self.canvas.tag_lower(line, "node")

    def _erase_edge(self, edge_id: str):
        line = self._edge_items.pop(edge_id, None)
        if line is not None:
            self.canvas.delete(line)

    def _redraw_all_edges(self):
        for edge_id in list(self._edge_items.keys()):
            self._erase_edge(edge_id)
        for edge_id in self.graph.edges.keys():
            self._draw_edge(edge_id)

    def _redraw_node(self, node_id: str):
        node = self.graph.get_node(node_id)
        if node is None:
            return
        self._draw_node(node)
        self._redraw_all_edges()
        self._update_minimap()

    def _update_node_selection_look(self, node_id: str):
        items = self._node_items.get(node_id)
        if items is None:
            return
        rect = items.get("rect")
        if rect is None:
            return
        if self.selected_node_id == node_id:
            color = NODE_COLORS.get(self.graph.get_node(node_id).node_type, COLOR_PRIMARY)
            self.canvas.itemconfigure(rect, outline=color)
            self.canvas.itemconfigure(rect, width=max(2, int(3 * self.zoom)))
        else:
            self.canvas.itemconfigure(rect, outline="#CBD5E1")
            self.canvas.itemconfigure(rect, width=max(1, int(2 * self.zoom)))

    def _update_minimap(self):
        """更新小地图：显示节点缩略图与当前视口。"""
        self.minimap.delete("all")
        if not self.graph.nodes:
            self.minimap.create_text(
                self.minimap.winfo_width() / 2 or 80,
                self.minimap.winfo_height() / 2 or 60,
                text="空", fill=COLOR_TEXT_DIM, font=(UI_FONT, 8),
            )
            return

        # 逻辑坐标范围
        xs = [n.x for n in self.graph.nodes.values()]
        ys = [n.y for n in self.graph.nodes.values()]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        # 留一点边距
        margin = 40
        min_x -= margin
        max_x += margin + NODE_WIDTH
        min_y -= margin
        max_y += margin + NODE_HEIGHT
        span_x = max(max_x - min_x, 1)
        span_y = max(max_y - min_y, 1)

        w = self.minimap.winfo_width() or dpi_scale(160, self.scale)
        h = self.minimap.winfo_height() or dpi_scale(120, self.scale)

        # 绘制节点
        for node in self.graph.nodes.values():
            nx = (node.x - min_x) / span_x * w
            ny = (node.y - min_y) / span_y * h
            nw = max(4, NODE_WIDTH / span_x * w)
            nh = max(3, NODE_HEIGHT / span_y * h)
            self.minimap.create_rectangle(
                nx, ny, nx + nw, ny + nh,
                fill=NODE_COLORS.get(node.node_type, COLOR_PRIMARY),
                outline="white",
            )

        # 绘制当前视口
        vx1 = self.canvas.canvasx(0)
        vy1 = self.canvas.canvasy(0)
        vx2 = self.canvas.canvasx(self.canvas.winfo_width())
        vy2 = self.canvas.canvasy(self.canvas.winfo_height())
        # 转换为逻辑坐标
        lx1, ly1 = self._from_screen(vx1, vy1)
        lx2, ly2 = self._from_screen(vx2, vy2)
        # 映射到小地图
        mx1 = (lx1 - min_x) / span_x * w
        my1 = (ly1 - min_y) / span_y * h
        mx2 = (lx2 - min_x) / span_x * w
        my2 = (ly2 - min_y) / span_y * h
        self.minimap.create_rectangle(
            mx1, my1, mx2, my2,
            outline=COLOR_PRIMARY, width=2, dash=(3, 3),
        )

    # ------------------------------------------------------------------
    # 鼠标交互
    # ------------------------------------------------------------------
    def _hit_test(self, x: float, y: float):
        """返回命中的对象信息（x, y 为逻辑坐标）。"""
        sx, sy = self._to_screen(x, y)
        r = max(2, int(3 * self.zoom * self.scale))
        items = self.canvas.find_overlapping(sx - r, sy - r, sx + r, sy + r)
        for item in reversed(items):
            tags = self.canvas.gettags(item)
            for tag in tags:
                if tag.startswith("port:"):
                    _, node_id, port_name = tag.split(":")
                    return "port", node_id, port_name
                if tag.startswith("node:"):
                    _, node_id = tag.split(":")
                    return "node", node_id, None
        return None, None, None

    def _canvas_to_graph(self, x: float, y: float) -> Tuple[float, float]:
        """把画布屏幕坐标转换为逻辑坐标。"""
        return self._from_screen(self.canvas.canvasx(x), self.canvas.canvasy(y))

    def _on_canvas_press(self, event):
        x, y = self._canvas_to_graph(event.x, event.y)
        kind, node_id, port_name = self._hit_test(x, y)

        if self._space_pressed:
            self._panning = True
            self.pan_start = (event.x, event.y)
            self.canvas.config(cursor="fleur")
            return

        if kind == "port":
            self._edge_start = (node_id, port_name)
            self._drag_start = (x, y)
            self._highlight_connectable_ports(node_id, port_name)
        elif kind == "node":
            self._select_node(node_id)
            self._drag_node_id = node_id
            self._drag_start = (x, y)
        else:
            self._select_node(None)

    def _on_canvas_drag(self, event):
        x, y = self._canvas_to_graph(event.x, event.y)

        if self._panning:
            if self.pan_start is not None:
                dx = event.x - self.pan_start[0]
                dy = event.y - self.pan_start[1]
                self.canvas.xview_scroll(int(-dx / self.zoom), "units")
                self.canvas.yview_scroll(int(-dy / self.zoom), "units")
                self.pan_start = (event.x, event.y)
            return

        if self._edge_start is not None:
            self._draw_temp_edge(x, y)
        elif self._drag_node_id is not None:
            dx = x - self._drag_start[0]
            dy = y - self._drag_start[1]
            node = self.graph.get_node(self._drag_node_id)
            if node:
                node.x += dx
                node.y += dy
                # 网格吸附（逻辑坐标）
                node.x = round(node.x / GRID_SIZE) * GRID_SIZE
                node.y = round(node.y / GRID_SIZE) * GRID_SIZE
                self._drag_start = (x, y)
                self._redraw_node(self._drag_node_id)

    def _on_canvas_release(self, event):
        x, y = self._canvas_to_graph(event.x, event.y)

        if self._panning:
            self._panning = False
            self.pan_start = None
            self.canvas.config(cursor="")
            return

        if self._edge_start is not None:
            self._clear_temp_edge()
            self._clear_port_highlights()
            kind, node_id, port_name = self._hit_test(x, y)
            if kind == "port" and node_id and port_name:
                src_id, src_port = self._edge_start
                edge = self.graph.add_edge(src_id, src_port, node_id, port_name)
                if edge:
                    self._draw_edge(edge.edge_id)
                    self._set_status("已创建连线")
                    self._update_minimap()
                else:
                    self._set_status("连线无效")
            self._edge_start = None
        elif self._drag_node_id is not None:
            self._drag_node_id = None
            self._drag_start = None

    def _on_middle_press(self, event):
        self._panning = True
        self.pan_start = (event.x, event.y)
        self.canvas.config(cursor="fleur")

    def _on_middle_drag(self, event):
        if self._panning and self.pan_start is not None:
            dx = event.x - self.pan_start[0]
            dy = event.y - self.pan_start[1]
            self.canvas.xview_scroll(int(-dx / self.zoom), "units")
            self.canvas.yview_scroll(int(-dy / self.zoom), "units")
            self.pan_start = (event.x, event.y)

    def _on_middle_release(self, event):
        self._panning = False
        self.pan_start = None
        self.canvas.config(cursor="")

    def _on_mousewheel(self, event):
        if event.state & 0x0004:  # Ctrl
            factor = 1.1 if event.delta > 0 else 0.9
            old_zoom = self.zoom
            self.zoom *= factor
            self.zoom = max(0.3, min(3.0, self.zoom))
            if self.zoom != old_zoom:
                self._redraw_all()
                self._set_status(f"缩放: {self.zoom:.2f}x")

    def _on_space_press(self, _event):
        self._space_pressed = True

    def _on_space_release(self, _event):
        self._space_pressed = False
        self._panning = False
        self.pan_start = None
        self.canvas.config(cursor="")

    def _on_canvas_double(self, event):
        pass

    def _on_delete_key(self, _event):
        if self.selected_node_id:
            self._remove_node(self.selected_node_id)
            self._set_status("已删除节点")

    def _select_node(self, node_id: Optional[str]):
        old = self.selected_node_id
        self.selected_node_id = node_id
        if old:
            self._update_node_selection_look(old)
        if node_id:
            self._update_node_selection_look(node_id)
            self._build_property_panel()
        else:
            self._clear_property_panel()

    # ------------------------------------------------------------------
    # 临时连线
    # ------------------------------------------------------------------
    def _draw_temp_edge(self, x2: float, y2: float):
        self._clear_temp_edge()
        src_id, src_port_name = self._edge_start
        src = self.graph.get_node(src_id)
        src_port = src.port(src_port_name) if src else None
        if src is None or src_port is None:
            return
        x1, y1 = self._port_position(src, src_port)
        x1 *= self.zoom
        y1 *= self.zoom
        x2 *= self.zoom
        y2 *= self.zoom
        cx = (x1 + x2) / 2
        self._temp_edge_line = self.canvas.create_line(
            x1, y1, cx, y1, cx, y2, x2, y2,
            fill="#94A3B8", width=max(1, int(2 * self.zoom)),
            smooth=True, splinesteps=24, dash=(4, 4),
            tags=("temp_edge",),
        )

    def _highlight_connectable_ports(self, source_node_id: str, source_port_name: str):
        """高亮可连接的端口。"""
        src_node = self.graph.get_node(source_node_id)
        src_port = src_node.port(source_port_name) if src_node else None
        if src_port is None:
            return

        for node_id, items in self._node_items.items():
            node = self.graph.get_node(node_id)
            if node is None:
                continue
            for port_name, item_id in items.get("ports", {}).items():
                port = node.port(port_name)
                if port is None:
                    continue
                # 可连接：方向相反，且类型匹配
                can_connect = (
                    port.direction != src_port.direction
                    and (port.data_type == src_port.data_type
                         or port.data_type == "any"
                         or src_port.data_type == "any")
                )
                if can_connect:
                    self.canvas.itemconfigure(item_id, outline="#22C55E")
                    self.canvas.itemconfigure(item_id, width=max(2, int(3 * self.zoom)))
                else:
                    self.canvas.itemconfigure(item_id, outline="#CBD5E1")
                    self.canvas.itemconfigure(item_id, width=max(1, int(1 * self.zoom)))

    def _clear_port_highlights(self):
        """清除端口高亮。"""
        for items in self._node_items.values():
            for item_id in items.get("ports", {}).values():
                self.canvas.itemconfigure(item_id, outline="white")
                self.canvas.itemconfigure(item_id, width=max(1, int(2 * self.zoom)))

    def _clear_temp_edge(self):
        if self._temp_edge_line is not None:
            self.canvas.delete(self._temp_edge_line)
            self._temp_edge_line = None
        self._clear_port_highlights()

    # ------------------------------------------------------------------
    # 画布重绘
    # ------------------------------------------------------------------
    def _redraw_all(self):
        """缩放或全量刷新。"""
        self.canvas.delete("all")
        self._node_items.clear()
        self._edge_items.clear()
        self._grid_items.clear()
        self._draw_grid()
        for node in self.graph.nodes.values():
            self._draw_node(node)
        self._redraw_all_edges()
        self._update_minimap()

    # ------------------------------------------------------------------
    # 属性面板
    # ------------------------------------------------------------------
    def _clear_property_panel(self):
        for w in self.prop_frame.winfo_children():
            w.destroy()
        self._prop_widgets.clear()
        self._prop_vars.clear()
        ttk.Label(self.prop_frame, text="未选择节点", style="DimCard.TLabel").pack(
            anchor=tk.W, pady=(4, 0)
        )

    def _build_property_panel(self):
        self._clear_property_panel()
        node = self.graph.get_node(self.selected_node_id)
        if node is None:
            return

        # 通用：标签
        self._add_prop_entry(node, "label", "名称", node.label)

        if node.node_type == "comm":
            self._add_prop_choice(node, "protocol", "协议", ["RS-232", "GPIB", "TCPIP", "USBTMC", "VISA"])
            self._add_prop_entry(node, "address", "地址/端口", node.data.get("address", ""))
            self._add_prop_entry(node, "port", "参数", str(node.data.get("port", "")))

        elif node.node_type == "instrument":
            self._add_prop_choice(node, "instrument_key", "仪器类型", InstrumentRegistry.keys())
            self._add_prop_entry(node, "alias", "别名", node.data.get("alias", ""))
            meta = InstrumentRegistry.get(node.data.get("instrument_key", ""))
            if meta:
                for p in meta.connection_params:
                    name = p["name"]
                    label = p.get("label", name)
                    default = node.data.get(name, p.get("default", ""))
                    ptype = p.get("type", "")
                    if ptype == "choice":
                        self._add_prop_choice(node, name, label, p.get("choices", []))
                    else:
                        self._add_prop_entry(node, name, label, str(default))

        elif node.node_type == "routine":
            self._add_prop_choice(node, "routine_name", "例程", self.routine_registry.names())
            routine = self.routine_registry.get(node.data.get("routine_name", ""))
            if routine:
                for p in routine.params:
                    name = p["name"]
                    label = p.get("label", name)
                    default = node.data.get(name, p.get("default", ""))
                    ptype = p.get("type", "")
                    if ptype == "choice":
                        self._add_prop_choice(node, name, label, p.get("choices", []))
                    elif ptype == "bool":
                        self._add_prop_bool(node, name, label, bool(default))
                    else:
                        self._add_prop_entry(node, name, label, str(default))

    def _add_prop_entry(self, node: Node, key: str, label: str, default: str):
        row = tk.Frame(self.prop_frame, bg=COLOR_CARD)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text=f"{label}:", width=10).pack(side=tk.LEFT)
        var = tk.StringVar(value=str(default))
        var.trace_add("write", lambda *_: self._on_prop_changed(node, key, var))
        entry = ttk.Entry(row, textvariable=var, width=20)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._prop_vars[key] = var
        self._prop_widgets.extend([row, entry])

    def _add_prop_choice(self, node: Node, key: str, label: str, values: List[str]):
        row = tk.Frame(self.prop_frame, bg=COLOR_CARD)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text=f"{label}:", width=10).pack(side=tk.LEFT)
        var = tk.StringVar(value=str(node.data.get(key, values[0] if values else "")))
        combo = ttk.Combobox(row, textvariable=var, values=values, state="readonly", width=18)
        combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        combo.bind("<<ComboboxSelected>>", lambda _e: self._on_prop_changed(node, key, var))
        self._prop_vars[key] = var
        self._prop_widgets.extend([row, combo])

    def _add_prop_bool(self, node: Node, key: str, label: str, default: bool):
        row = tk.Frame(self.prop_frame, bg=COLOR_CARD)
        row.pack(fill=tk.X, pady=3)
        var = tk.BooleanVar(value=default)
        cb = ttk.Checkbutton(row, variable=var, text=label)
        cb.pack(side=tk.LEFT)
        var.trace_add("write", lambda *_: self._on_prop_changed(node, key, var))
        self._prop_vars[key] = var
        self._prop_widgets.extend([row, cb])

    def _on_prop_changed(self, node: Node, key: str, var: tk.Variable):
        value = var.get()
        old_value = node.data.get(key)
        node.data[key] = value

        if key == "label":
            node.label = value or _default_label(node.node_type)
            self._redraw_node(node.node_id)

        if key == "instrument_key":
            self._rebuild_instrument_ports(node)
            self._redraw_node(node.node_id)

        if key == "routine_name":
            self._rebuild_routine_ports(node)
            self._redraw_node(node.node_id)
            self._build_property_panel()

        self._set_status(f"更新 {node.label}.{key}")

    # ------------------------------------------------------------------
    # 文件操作
    # ------------------------------------------------------------------
    def get_graph(self) -> SetupGraph:
        return self.graph

    def set_graph(self, graph: SetupGraph):
        self.graph = graph
        self.selected_node_id = None
        self.zoom = 1.0
        self._redraw_all()
        self._clear_property_panel()
        self._set_status("已加载 Setup 图")

    def _new_graph(self):
        self.set_graph(SetupGraph())
        self._set_status("新建空白 Setup 图")

    def _save_graph(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".labsetup.json",
            filetypes=[("Lab Setup", "*.labsetup.json"), ("JSON", "*.json")],
            title="保存 Setup 图",
        )
        if path:
            self.graph.save(Path(path))
            self._set_status(f"已保存: {path}")

    def _load_graph(self):
        path = filedialog.askopenfilename(
            filetypes=[("Lab Setup", "*.labsetup.json"), ("JSON", "*.json")],
            title="打开 Setup 图",
        )
        if path:
            try:
                graph = SetupGraph.load(Path(path))
                self.set_graph(graph)
                self._set_status(f"已打开: {path}")
            except Exception as exc:
                messagebox.showerror("打开失败", str(exc))

    def _apply_to_run(self):
        errors = self.graph.validate()
        if errors:
            messagebox.showwarning("Setup 图未通过校验", "\n".join(errors))
            return
        if self.on_apply:
            self.on_apply(self.graph)
            self._set_status("已同步到运行配置")

    def _set_status(self, text: str):
        self.status_lbl.configure(text=text)


def _default_label(node_type: str) -> str:
    from lab_engine.core.setup_graph import _default_label as dl
    return dl(node_type)

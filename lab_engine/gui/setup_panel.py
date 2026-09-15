"""Lab Engine Setup 框图编辑器面板。

提供基于 tk.Canvas 的可视化节点编辑器：
- 工具栏添加 Host / Comm / Instrument / Routine 节点
- 拖拽移动节点
- 在端口之间连线
- 属性面板编辑节点参数
- 保存/加载 .labsetup.json
- 一键同步到 Run tab
"""
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

        # canvas item 缓存：node_id -> {rect, title, port_items: {name: circle}, label_items}
        self._node_items: Dict[str, Dict[str, Any]] = {}
        self._edge_items: Dict[str, int] = {}

        self._prop_vars: Dict[str, tk.Variable] = {}
        self._prop_widgets: List[tk.Widget] = []

        self._build_ui()
        self._bind_events()
        self._refresh_toolbar_state()

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
            scrollregion=(0, 0, dpi_scale(2000, self.scale), dpi_scale(1500, self.scale)),
        )
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        vbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)
        hbar = ttk.Scrollbar(self, orient=tk.HORIZONTAL, command=self.canvas.xview)
        hbar.pack(fill=tk.X)
        self.canvas.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set)

        # 属性面板
        prop_card = tk.Frame(body, bg=COLOR_CARD,
                             highlightbackground="#E2E8F0", highlightthickness=1, bd=0)
        prop_card.pack(side=tk.RIGHT, fill=tk.Y, padx=(8, 0))
        prop_card.pack_propagate(False)
        prop_card.configure(width=dpi_scale(280, self.scale))

        prop_inner = tk.Frame(prop_card, bg=COLOR_CARD)
        prop_inner.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)

        ttk.Label(prop_inner, text="属性", style="Section.TLabel").pack(anchor=tk.W, pady=(0, 8))
        self.prop_frame = tk.Frame(prop_inner, bg=COLOR_CARD)
        self.prop_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(prop_inner, text="提示: 选中节点后编辑属性，拖拽端口连线。",
                  wraplength=dpi_scale(240, self.scale), style="DimCard.TLabel").pack(
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

    def _bind_events(self):
        self.canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Double-Button-1>", self._on_canvas_double)
        self.bind_all("<Delete>", self._on_delete_key)
        self.bind_all("<BackSpace>", self._on_delete_key)

    def _refresh_toolbar_state(self):
        pass

    # ------------------------------------------------------------------
    # 节点与图操作
    # ------------------------------------------------------------------
    def _add_node(self, node_type: str):
        x = dpi_scale(120 + len(self.graph.nodes) * 40, self.scale)
        y = dpi_scale(100 + (len(self.graph.nodes) % 3) * 140, self.scale)
        node = self.graph.add_node(node_type, x, y)
        self._init_node_defaults(node)
        self._draw_node(node)
        self._select_node(node.node_id)
        self._set_status(f"添加节点: {node.label}")

    def _init_node_defaults(self, node: Node):
        """为新节点填充默认属性。"""
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
        """根据仪器类型重建 instrument 节点端口。"""
        from lab_engine.core.setup_graph import Port
        node.ports = [
            Port("comm", "通信", "input", "comm"),
            Port("data", "数据", "output", "data"),
        ]

    def _rebuild_routine_ports(self, node: Node):
        """根据例程声明重建 routine 节点输入端口。"""
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

    def _remove_edge(self, edge_id: str):
        self.graph.remove_edge(edge_id)
        self._erase_edge(edge_id)

    # ------------------------------------------------------------------
    # Canvas 绘制
    # ------------------------------------------------------------------
    def _draw_node(self, node: Node):
        self._erase_node(node.node_id)
        items: Dict[str, Any] = {"ports": {}, "labels": []}

        w = dpi_scale(NODE_WIDTH, self.scale)
        # 根据端口数量调整高度
        n_ports = max(2, len(node.ports))
        h = dpi_scale(max(NODE_HEIGHT, 50 + n_ports * 28), self.scale)

        # 节点矩形
        rect = self.canvas.create_rectangle(
            node.x, node.y, node.x + w, node.y + h,
            fill=COLOR_CARD, outline="#CBD5E1", width=2,
            tags=(f"node:{node.node_id}", "node"),
        )
        items["rect"] = rect

        # 标题背景
        title_h = dpi_scale(24, self.scale)
        title_rect = self.canvas.create_rectangle(
            node.x, node.y, node.x + w, node.y + title_h,
            fill=COLOR_PRIMARY, outline="",
            tags=(f"node:{node.node_id}", "node_title_bg"),
        )
        items["title_bg"] = title_rect

        # 标题文字
        title_text = self.canvas.create_text(
            node.x + w / 2, node.y + title_h / 2,
            text=node.label, fill="white", font=(UI_FONT, 9, "bold"),
            tags=(f"node:{node.node_id}", "node_title"),
        )
        items["title"] = title_text

        # 类型标签
        type_text = self.canvas.create_text(
            node.x + w / 2, node.y + h - dpi_scale(10, self.scale),
            text=node.node_type, fill=COLOR_TEXT_DIM, font=(UI_FONT, 8),
            tags=(f"node:{node.node_id}", "node_type"),
        )
        items["type_label"] = type_text

        # 端口
        inputs = [p for p in node.ports if p.direction == "input"]
        outputs = [p for p in node.ports if p.direction == "output"]

        for i, port in enumerate(inputs):
            px, py = self._port_position(node, port, h)
            c = self.canvas.create_oval(
                px - PORT_RADIUS, py - PORT_RADIUS,
                px + PORT_RADIUS, py + PORT_RADIUS,
                fill="#64748B", outline="white", width=2,
                tags=(f"port:{node.node_id}:{port.name}", "port"),
            )
            items["ports"][port.name] = c
            lbl = self.canvas.create_text(
                px + dpi_scale(10, self.scale), py,
                text=port.label, fill=COLOR_TEXT_DIM, font=(UI_FONT, 8),
                anchor=tk.W, tags=(f"port_label:{node.node_id}:{port.name}",),
            )
            items["labels"].append(lbl)

        for i, port in enumerate(outputs):
            px, py = self._port_position(node, port, h)
            c = self.canvas.create_oval(
                px - PORT_RADIUS, py - PORT_RADIUS,
                px + PORT_RADIUS, py + PORT_RADIUS,
                fill="#64748B", outline="white", width=2,
                tags=(f"port:{node.node_id}:{port.name}", "port"),
            )
            items["ports"][port.name] = c
            lbl = self.canvas.create_text(
                px - dpi_scale(10, self.scale), py,
                text=port.label, fill=COLOR_TEXT_DIM, font=(UI_FONT, 8),
                anchor=tk.E, tags=(f"port_label:{node.node_id}:{port.name}",),
            )
            items["labels"].append(lbl)

        self._node_items[node.node_id] = items
        self._update_node_selection_look(node.node_id)

    def _port_position(self, node: Node, port: Any, node_h: Optional[float] = None) -> Tuple[float, float]:
        w = dpi_scale(NODE_WIDTH, self.scale)
        h = node_h or dpi_scale(NODE_HEIGHT, self.scale)
        inputs = [p for p in node.ports if p.direction == "input"]
        outputs = [p for p in node.ports if p.direction == "output"]

        if port.direction == "input":
            idx = inputs.index(port)
            n = len(inputs)
            y = node.y + 30 * self.scale + (idx + 1) * ((h - 40 * self.scale) / max(n, 1))
            return node.x, y
        else:
            idx = outputs.index(port)
            n = len(outputs)
            y = node.y + 30 * self.scale + (idx + 1) * ((h - 40 * self.scale) / max(n, 1))
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
        line = self.canvas.create_line(
            x1, y1, x2, y2,
            fill=COLOR_PRIMARY, width=2,
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

    def _update_node_selection_look(self, node_id: str):
        items = self._node_items.get(node_id)
        if items is None:
            return
        rect = items.get("rect")
        if rect is None:
            return
        color = COLOR_PRIMARY if self.selected_node_id == node_id else "#CBD5E1"
        self.canvas.itemconfigure(rect, outline=color)
        self.canvas.itemconfigure(rect, width=3 if self.selected_node_id == node_id else 2)

    # ------------------------------------------------------------------
    # 鼠标交互
    # ------------------------------------------------------------------
    def _hit_test(self, x: float, y: float):
        """返回命中的对象信息。"""
        items = self.canvas.find_overlapping(x - 2, y - 2, x + 2, y + 2)
        for item in reversed(items):
            tags = self.canvas.gettags(item)
            for tag in tags:
                if tag.startswith("port:"):
                    _, node_id, port_name = tag.split(":")
                    return "port", node_id, port_name
                if tag.startswith("node:"):
                    _, node_id = tag.split(":")
                    return "node", node_id, None
                if tag == "node":
                    # 找到最近的 node tag
                    for t in tags:
                        if t.startswith("node:"):
                            _, node_id = t.split(":")
                            return "node", node_id, None
        return None, None, None

    def _on_canvas_press(self, event):
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        kind, node_id, port_name = self._hit_test(x, y)

        if kind == "port":
            self._edge_start = (node_id, port_name)
            self._drag_start = (x, y)
        elif kind == "node":
            self._select_node(node_id)
            self._drag_node_id = node_id
            self._drag_start = (x, y)
        else:
            self._select_node(None)

    def _on_canvas_drag(self, event):
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

        if self._edge_start is not None:
            self._draw_temp_edge(x, y)
        elif self._drag_node_id is not None:
            dx = x - self._drag_start[0]
            dy = y - self._drag_start[1]
            node = self.graph.get_node(self._drag_node_id)
            if node:
                node.x += dx
                node.y += dy
                self._drag_start = (x, y)
                self._redraw_node(self._drag_node_id)

    def _on_canvas_release(self, event):
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

        if self._edge_start is not None:
            self._clear_temp_edge()
            kind, node_id, port_name = self._hit_test(x, y)
            if kind == "port" and node_id and port_name:
                src_id, src_port = self._edge_start
                edge = self.graph.add_edge(src_id, src_port, node_id, port_name)
                if edge:
                    self._draw_edge(edge.edge_id)
                    self._set_status("已创建连线")
                else:
                    self._set_status("连线无效")
            self._edge_start = None
        elif self._drag_node_id is not None:
            self._drag_node_id = None
            self._drag_start = None

    def _on_canvas_double(self, event):
        pass

    def _draw_temp_edge(self, x2: float, y2: float):
        self._clear_temp_edge()
        src_id, src_port_name = self._edge_start
        src = self.graph.get_node(src_id)
        src_port = src.port(src_port_name) if src else None
        if src is None or src_port is None:
            return
        x1, y1 = self._port_position(src, src_port)
        self._temp_edge_line = self.canvas.create_line(
            x1, y1, x2, y2, fill="#94A3B8", width=2, dash=(4, 4), tags=("temp_edge",)
        )

    def _clear_temp_edge(self):
        if self._temp_edge_line is not None:
            self.canvas.delete(self._temp_edge_line)
            self._temp_edge_line = None

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
    # 属性面板
    # ------------------------------------------------------------------
    def _clear_property_panel(self):
        for w in self._prop_widgets:
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
            # 根据仪器类型渲染连接参数
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

        # 特殊处理：标签
        if key == "label":
            node.label = value or _default_label(node.node_type)
            self._redraw_node(node.node_id)

        # 特殊处理：instrument 类型改变 -> 保留 alias，不需要改端口
        if key == "instrument_key":
            self._rebuild_instrument_ports(node)
            self._redraw_node(node.node_id)

        # 特殊处理：routine 改变 -> 重建端口
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
        self._node_items.clear()
        self._edge_items.clear()
        self.canvas.delete("all")
        for node in self.graph.nodes.values():
            self._init_node_defaults(node)
            self._draw_node(node)
        self._redraw_all_edges()
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

"""Lab Engine 主应用。"""
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, Optional

from lab_engine.core.data_manager import DataManager
from lab_engine.core.registry import RoutineMeta, RoutineRegistry
from lab_engine.core.routine_context import RoutineContext
from lab_engine.core.setup_graph import SetupGraph
from lab_engine.gui.connection_panel import ConnectionPanel
from lab_engine.gui.log_panel import LogPanel
from lab_engine.gui.plot_panel import PlotPanel
from lab_engine.gui.routine_panel import RoutinePanel
from lab_engine.gui.setup_panel import SetupPanel
from lab_engine.gui.shell import (
    COLOR_BG,
    COLOR_CARD,
    configure_styles,
    dpi_scale,
    make_card,
    set_dpi_aware,
    set_tk_scaling,
    setup_plot_fonts,
    UI_FONT,
)

# 确保本仓库的 ivlab 可用
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 触发仪器注册
import lab_engine.instruments  # noqa: F401


UPDATE_MS = 100


class _RoutineWorker(threading.Thread):
    """在后台线程中执行例程。"""

    def __init__(
        self,
        routine: RoutineMeta,
        instruments: Dict[str, Any],
        params: Dict[str, Any],
        context: RoutineContext,
    ):
        super().__init__(daemon=True)
        self.routine = routine
        self.instruments = instruments
        self.params = params
        self.context = context
        self.success = False
        self.error: Optional[str] = None

    def run(self):
        try:
            self.routine.run(self.instruments, self.params, self.context)
            self.success = True
        except Exception as exc:
            self.error = str(exc)
            self.context.error(f"例程异常: {exc}")
            self.success = False
        finally:
            self.context.done(success=self.success)


class LabEngineApp(tk.Tk):
    """Lab Engine 主窗口。"""

    def __init__(self):
        super().__init__()
        set_dpi_aware()
        self.scale = set_tk_scaling(self)
        setup_plot_fonts()

        self.title("Lab Engine — 通用实验室仪器控制引擎")
        self.configure(bg=COLOR_BG)

        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w = min(int(sw * 0.85), dpi_scale(1500, self.scale))
        h = min(int(sh * 0.85), dpi_scale(950, self.scale))
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
        self.minsize(dpi_scale(1050, self.scale), dpi_scale(680, self.scale))

        configure_styles(self, self.scale)

        # 核心对象
        self.registry = RoutineRegistry()
        self.registry.discover([
            Path(__file__).resolve().parent / "routines",
        ])
        self.data_manager = DataManager(Path.cwd() / "data")
        self.msg_queue: queue.Queue = queue.Queue()

        # 运行状态
        self.worker: Optional[_RoutineWorker] = None
        self.stop_event = threading.Event()
        self.current_context: Optional[RoutineContext] = None
        self._last_params: Dict[str, Any] = {}

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(UPDATE_MS, self._poll_messages)

    def _build_ui(self):
        # 顶部标题栏
        header = tk.Frame(self, bg=COLOR_BG)
        header.pack(fill=tk.X, padx=16, pady=(14, 6))
        ttk.Label(header, text="Lab Engine", style="Title.TLabel").pack(side=tk.LEFT)
        self.status_lbl = ttk.Label(header, text="就绪")
        self.status_lbl.pack(side=tk.RIGHT)

        # 主 Notebook：Setup / Run
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 8))

        setup_tab = tk.Frame(self.notebook, bg=COLOR_BG)
        run_tab = tk.Frame(self.notebook, bg=COLOR_BG)
        self.notebook.add(setup_tab, text="  Setup 框图  ")
        self.notebook.add(run_tab, text="  Run 运行  ")

        # ---- Setup tab ----
        self.setup_panel = SetupPanel(
            setup_tab,
            routine_registry=self.registry,
            on_apply=self._apply_setup_graph,
            scale=self.scale,
        )
        self.setup_panel.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # ---- Run tab ----
        self._build_run_tab(run_tab)

    def _build_run_tab(self, parent):
        # 主区域：左侧可滚动面板 + 右侧图/日志
        main_paned = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True)

        # 先创建右侧面板，使 plot_panel / log_panel 在例程触发 on_select 前已存在
        right = tk.Frame(main_paned, bg=COLOR_BG)

        # 绘图区
        plot_card = make_card(right, fill=tk.BOTH, expand=True, pady=(0, 8))
        self.plot_panel = PlotPanel(plot_card)
        self.plot_panel.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # 日志区
        log_card = make_card(right, fill=tk.BOTH, expand=True)
        log_inner = tk.Frame(log_card, bg=COLOR_CARD)
        log_inner.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)
        ttk.Label(log_inner, text="运行日志", style="Section.TLabel").pack(anchor=tk.W)
        self.log_panel = LogPanel(log_inner, height=10)
        self.log_panel.pack(fill=tk.BOTH, expand=True, pady=(6, 0))

        # 左侧可滚动面板
        left_frame = tk.Frame(main_paned, bg=COLOR_BG)
        left_canvas = tk.Canvas(left_frame, bg=COLOR_BG, highlightthickness=0)
        left_vsb = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=left_canvas.yview)
        left_canvas.configure(yscrollcommand=left_vsb.set)
        left_vsb.pack(side=tk.RIGHT, fill=tk.Y)
        left_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        left_inner = tk.Frame(left_canvas, bg=COLOR_BG)
        left_canvas.create_window((0, 0), window=left_inner, anchor="nw",
                                  width=dpi_scale(480, self.scale))
        left_inner.bind("<Configure>",
                        lambda _e: left_canvas.configure(scrollregion=left_canvas.bbox("all")))

        # 输出目录
        out_card = make_card(left_inner, fill=tk.X, pady=(0, 8))
        out_inner = tk.Frame(out_card, bg=COLOR_CARD)
        out_inner.pack(fill=tk.X, padx=12, pady=10)
        ttk.Label(out_inner, text="输出目录:", style="Section.TLabel").pack(side=tk.LEFT)
        self.output_dir_var = tk.StringVar(value=str(self.data_manager.base_dir))
        ttk.Entry(out_inner, textvariable=self.output_dir_var, width=28).pack(side=tk.LEFT, padx=8)
        ttk.Button(out_inner, text="浏览", command=self._browse_output_dir).pack(side=tk.LEFT)

        # 仪器连接面板
        self.connection_panel = ConnectionPanel(
            left_inner,
            self.msg_queue,
            on_connection_change=self._on_instrument_connection_change,
        )
        self.connection_panel.pack(fill=tk.X, pady=(0, 8))

        # 例程面板（创建时会触发 on_select，依赖 plot_panel 已存在）
        self.routine_panel = RoutinePanel(
            left_inner,
            self.registry,
            on_select=self._on_routine_selected,
            on_run=self._on_run,
            on_stop=self._on_stop,
        )
        self.routine_panel.pack(fill=tk.X, pady=(0, 8))

        main_paned.add(left_frame, weight=1)
        main_paned.add(right, weight=2)

    def _apply_setup_graph(self, graph: SetupGraph):
        """把 Setup 图同步到 Run tab 的连接面板与例程面板。"""
        # 1. 收集 instrument 节点 -> 例程期望的 instruments 字典
        instruments_meta: Dict[str, Dict[str, Any]] = {}
        for node in graph.nodes_by_type("instrument"):
            alias = node.data.get("alias") or node.node_id
            key = node.data.get("instrument_key", "")
            instruments_meta[alias] = {"type": key, "required": True}

        # 2. 选择例程：取第一个 routine 节点
        routine_nodes = graph.nodes_by_type("routine")
        if routine_nodes:
            routine_name = routine_nodes[0].data.get("routine_name", "")
            if routine_name and routine_name in self.registry.names():
                self.routine_panel.select_routine(routine_name)

        # 3. 应用仪器配置（如果当前例程已选，以例程声明为准；否则以图里的 instrument 节点为准）
        current_routine = self.routine_panel.current_routine
        if current_routine:
            # 合并：例程声明的仪器 + 图中同名 instrument 节点的类型/参数
            merged = dict(current_routine.instruments)
            for alias, info in instruments_meta.items():
                if alias in merged:
                    merged[alias]["type"] = info["type"]
                else:
                    merged[alias] = info
            self.connection_panel.set_instruments(merged)
        elif instruments_meta:
            self.connection_panel.set_instruments(instruments_meta)

        # 4. 把图中每个 instrument 节点的连接参数写回对应卡片
        for node in graph.nodes_by_type("instrument"):
            alias = node.data.get("alias") or node.node_id
            card = self.connection_panel.cards.get(alias)
            if card is None:
                continue
            meta = self.connection_panel.cards[alias].meta if alias in self.connection_panel.cards else None
            if meta is None:
                continue
            for p in meta.connection_params:
                name = p["name"]
                if name in card.param_vars:
                    value = node.data.get(name)
                    if value is not None:
                        card.param_vars[name].set(str(value))

        # 5. 把 routine 节点的参数写回例程面板
        if routine_nodes and self.routine_panel.current_routine:
            routine_node = routine_nodes[0]
            for p in self.routine_panel.current_routine.params:
                name = p["name"]
                if name not in self.routine_panel.param_vars:
                    continue
                value = routine_node.data.get(name)
                if value is None:
                    continue
                ptype = p.get("type", "")
                try:
                    if ptype == "bool":
                        value = bool(value)
                    elif ptype == "int":
                        value = int(value)
                    elif ptype == "float":
                        value = float(value)
                    else:
                        value = str(value)
                    self.routine_panel.param_vars[name].set(value)
                except Exception:
                    pass

        # 6. 切换到 Run tab
        self.notebook.select(1)
        self.log_panel.append("已从 Setup 框图同步运行配置")

    def _on_instrument_connection_change(self, alias: str, connected: bool):
        """仪器连接状态改变时，更新 Setup 框图中的节点状态。"""
        if hasattr(self, "setup_panel"):
            self.setup_panel.set_instrument_status(alias, connected)

    def _browse_output_dir(self):
        path = filedialog.askdirectory(title="选择输出目录", initialdir=self.output_dir_var.get())
        if path:
            self.output_dir_var.set(path)
            self.data_manager = DataManager(Path(path))

    def _on_routine_selected(self, routine: Optional[RoutineMeta]):
        self.plot_panel.clear()
        self.log_panel.clear()
        if routine:
            self.connection_panel.set_instruments(routine.instruments)
            self.log_panel.append(f"已加载例程: {routine.name}")
        else:
            self.connection_panel.set_instruments({})

    def _on_run(self):
        routine = self.routine_panel.current_routine
        if routine is None:
            messagebox.showwarning("提示", "请先选择一个例程")
            return

        instruments = self.connection_panel.get_connected_instruments()
        missing = [
            alias for alias, info in routine.instruments.items()
            if info.get("required", True) and alias not in instruments
        ]
        if missing:
            messagebox.showwarning("仪器未连接",
                                   f"请先连接以下必需仪器: {', '.join(missing)}")
            return

        params = self.routine_panel.get_params()
        self._last_params = params
        self.stop_event.clear()
        self.routine_panel.set_running(True)
        self.connection_panel.set_enabled(False)
        self.routine_panel.reset_progress()
        self.plot_panel.clear()

        # 创建本次运行目录
        run_id, run_dir = self.data_manager.new_run(routine.name)
        self.current_context = RoutineContext(
            run_id=run_id,
            output_dir=run_dir,
            msg_queue=self.msg_queue,
            stop_event=self.stop_event,
        )

        self.log_panel.append(f"开始运行: {routine.name} ({run_id})")
        self.status_lbl.configure(text=f"运行中: {routine.name}")

        self.worker = _RoutineWorker(
            routine=routine,
            instruments=instruments,
            params=params,
            context=self.current_context,
        )
        self.worker.start()

    def _on_stop(self):
        self.stop_event.set()
        self.log_panel.append("已请求停止例程", level="warn")
        self.status_lbl.configure(text="停止请求已发送")

    def _poll_messages(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                self._handle_message(msg)
        except queue.Empty:
            pass

        self.connection_panel.update_ui()
        self.after(UPDATE_MS, self._poll_messages)

    def _handle_message(self, msg: tuple):
        kind, payload = msg
        if kind == "log":
            self.log_panel.append(payload.get("text", ""), payload.get("level", "info"))
        elif kind == "progress":
            self.routine_panel.set_progress(payload.get("current", 0), payload.get("total", 1))
        elif kind == "point":
            self.plot_panel.add_point(**payload)
        elif kind == "data":
            self.plot_panel.add_points(self.current_context.points if self.current_context else [])
        elif kind == "done":
            self._on_routine_done(payload)

    def _on_routine_done(self, payload: Dict[str, Any]):
        self.routine_panel.set_running(False)
        self.connection_panel.set_enabled(True)
        success = payload.get("success", False)

        if self.current_context and self.worker:
            routine = self.routine_panel.current_routine
            points = self.current_context.points
            run_dir = self.current_context.output_dir
            if points:
                self.data_manager.save_csv(run_dir, points)
            self.data_manager.save_metadata(
                run_dir=run_dir,
                routine_name=routine.name if routine else "unknown",
                routine_path=routine.path if routine else Path(),
                params=self._last_params,
                instruments=self.connection_panel.get_instruments_idn(),
            )
            self.log_panel.append(f"数据已保存: {run_dir}")

        if success:
            self.status_lbl.configure(text="运行完成")
            self.log_panel.append("例程运行完成")
        else:
            error = self.worker.error if self.worker else None
            self.status_lbl.configure(text="运行失败" + (f": {error}" if error else ""))
            self.log_panel.append("例程运行结束（未成功）", level="warn")

        self.worker = None
        self.current_context = None

    def _on_close(self):
        self.stop_event.set()
        self.connection_panel.disconnect_all()
        self.connection_panel.stop_all_workers()
        if self.worker and self.worker.is_alive():
            self.worker.join(timeout=2.0)
        self.destroy()


def main():
    app = LabEngineApp()
    app.mainloop()


if __name__ == "__main__":
    main()

"""Keithley 2400 + GPD4303S 联合测试例程 GUI

运行方式（在项目根目录）:
    python examples/k2400_gpd4303s_routine_gui.py

功能：
    - 在同一面板里连接/断开 Keithley 2400 源表与 GPD4303S 四通道电源
    - 实时显示两台仪器的读数与连接状态
    - 通过文件对话框导入用户编写的测试例程（Python 插件）
    - 根据例程声明的 PARAMS 动态生成参数面板
    - 运行例程时实时显示日志、进度与 I-V 曲线
    - 自动保存测试数据（CSV + JSON 元数据）

插件接口：
    例程是一个普通 .py 文件，必须暴露以下三个对象：
        NAME = "例程名称"
        DESCRIPTION = "例程说明"
        PARAMS = [
            {"name": "param_name", "label": "参数标签", "type": "float",
             "default": 0.0, "min": -10.0, "max": 10.0},
            ...
        ]
        def run(instruments, params, report):
            k2400 = instruments["k2400"]   # Keithley2400 实例
            gpd = instruments["gpd"]       # GPD4303S 实例
            report("log", text="...")
            report("progress", current=1, total=10)
            report("point", voltage=0.0, current=1e-6)
            if report("is_stopped"):       # 检查用户是否请求停止
                return

    支持的参数类型：float / int / choice / bool
"""
import argparse
import csv
import ctypes
import datetime
import importlib.util
import json
import logging
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ivlab.instruments.gpd4303s import GPD4303S
from ivlab.instruments.keithley2400 import Keithley2400
from ivlab.utils.port_scanner import list_com_ports


UPDATE_MS = 250
CHANNELS = (1, 2, 3, 4)
CONFIG_FILE = Path(__file__).resolve().parent.parent / "data" / ".k2400_gpd_routine_gui.json"


# ---------------------------------------------------------------------------
# DPI 与中文显示辅助
# ---------------------------------------------------------------------------
def _set_dpi_aware():
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _get_system_dpi() -> int:
    if sys.platform != "win32":
        return 96
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return dpi
    except Exception:
        return 96


def _set_tk_scaling(root: tk.Tk):
    dpi = _get_system_dpi()
    try:
        root.tk.call("tk", "scaling", dpi / 72.0)
    except Exception:
        pass
    return dpi


def _dpi_scale(pixels: int, dpi: int) -> int:
    return int(pixels * dpi / 96.0)


def _setup_chinese_font():
    candidates = [
        "Microsoft YaHei", "SimHei", "SimSun", "STSong",
        "WenQuanYi Micro Hei", "Noto Sans CJK SC", "Source Han Sans SC",
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for name in candidates:
        if name in available:
            plt.rcParams["font.sans-serif"] = [name] + plt.rcParams.get("font.sans-serif", [])
            break
    plt.rcParams["axes.unicode_minus"] = False


_set_dpi_aware()
_setup_chinese_font()


# ---------------------------------------------------------------------------
# 日志重定向
# ---------------------------------------------------------------------------
class GuiLogHandler(logging.Handler):
    def __init__(self, msg_queue: queue.Queue):
        super().__init__(level=logging.DEBUG)
        self.msg_queue = msg_queue
        self.setFormatter(logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S"))

    def emit(self, record):
        try:
            text = self.format(record)
            self.msg_queue.put(("debug", text))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 后台 Worker：持有两台仪器，执行例程，轮询状态
# ---------------------------------------------------------------------------
class RoutineWorker(threading.Thread):
    def __init__(self, state: dict, msg_queue: queue.Queue, cmd_queue: queue.Queue):
        super().__init__(daemon=True)
        self.state = state
        self.msg_queue = msg_queue
        self.cmd_queue = cmd_queue
        self._running = True
        self._routine_running = False
        self._stop_event = threading.Event()

        self.k2400: Keithley2400 | None = None
        self.gpd: GPD4303S | None = None
        self._log_handler = GuiLogHandler(msg_queue)

        self._current_routine_name = ""
        self._current_points: list[dict] = []

    def _post(self, kind: str, **kwargs):
        self.msg_queue.put((kind, kwargs))

    def _handle_cmd(self, cmd: tuple):
        if cmd[0] == "connect":
            _, inst_name, port, baudrate = cmd
            self._connect_instrument(inst_name, port, baudrate)
        elif cmd[0] == "disconnect":
            _, inst_name = cmd
            self._disconnect_instrument(inst_name)
        elif cmd[0] == "disconnect_all":
            # 先停例程再断开，避免在扫描过程中直接拔掉端口导致锁死
            self._stop_event.set()
            self._disconnect_all()
        elif cmd[0] == "run_routine":
            _, module_path, params = cmd
            self._run_routine(module_path, params)
        elif cmd[0] == "stop_routine":
            self._stop_event.set()

    def _connect_instrument(self, name: str, port: str, baudrate: int):
        try:
            if name == "k2400":
                if self.k2400 is not None:
                    return
                self._post("log", text=f"连接 Keithley 2400: {port}")
                self.k2400 = Keithley2400(port=port, baudrate=baudrate, timeout=5.0)
                self.k2400.connect(retries=2)
                self.k2400.logger.addHandler(self._log_handler)
                self.state["k2400"].update({
                    "connected": True,
                    "idn": self.k2400.idn(),
                    "error": "",
                })
                self._post("log", text=f"K2400 已连接: {self.state['k2400']['idn']}")
            elif name == "gpd":
                if self.gpd is not None:
                    return
                self._post("log", text=f"连接 GPD4303S: {port}")
                self.gpd = GPD4303S(port=port, baudrate=baudrate, timeout=5.0)
                self.gpd.connect(retries=2)
                self.gpd.logger.addHandler(self._log_handler)
                self.state["gpd"].update({
                    "connected": True,
                    "idn": self.gpd.idn(),
                    "error": "",
                })
                self._post("log", text=f"GPD4303S 已连接: {self.state['gpd']['idn']}")
        except Exception as exc:
            self.state[name]["error"] = str(exc)
            self.state[name]["connected"] = False
            self._post("log", text=f"连接 {name} 失败: {exc}", tag="error")

    def _disconnect_instrument(self, name: str):
        if name == "k2400" and self.k2400 is not None:
            try:
                self.k2400.logger.removeHandler(self._log_handler)
            except Exception:
                pass
            try:
                self.k2400.disconnect()
            except Exception as exc:
                self._post("log", text=f"断开 K2400 出错: {exc}", tag="warn")
            self.k2400 = None
            self.state["k2400"].update({"connected": False, "idn": "", "output": False, "error": ""})
            self._post("log", text="K2400 已断开")
        elif name == "gpd" and self.gpd is not None:
            try:
                self.gpd.logger.removeHandler(self._log_handler)
            except Exception:
                pass
            try:
                self.gpd.disconnect()
            except Exception as exc:
                self._post("log", text=f"断开 GPD 出错: {exc}", tag="warn")
            self.gpd = None
            self.state["gpd"].update({"connected": False, "idn": "", "output": False, "channels": {}, "error": ""})
            self._post("log", text="GPD4303S 已断开")

    def _disconnect_all(self):
        self._disconnect_instrument("k2400")
        self._disconnect_instrument("gpd")

    def _poll_instruments(self):
        if self.k2400 is not None and self.state["k2400"]["connected"]:
            try:
                data = self.k2400.measure()
                self.state["k2400"].update({
                    "v": data.get("voltage"),
                    "i": data.get("current"),
                    "r": data.get("resistance"),
                    "error": "",
                })
            except Exception as exc:
                self.state["k2400"]["error"] = str(exc)

        if self.gpd is not None and self.state["gpd"]["connected"]:
            try:
                status = self.gpd.get_status()
                channels = {}
                for ch in CHANNELS:
                    channels[ch] = {
                        "v_set": self.gpd.get_voltage_set(ch),
                        "i_set": self.gpd.get_current_set(ch),
                        "v_out": self.gpd.measure_voltage(ch),
                        "i_out": self.gpd.measure_current(ch),
                        "mode": status["channel_modes"].get(ch, "?"),
                    }
                raw = status["raw"]
                output_on = len(raw) >= 6 and raw[5] == "1"
                self.state["gpd"].update({
                    "channels": channels,
                    "output": output_on,
                    "error": "",
                })
            except Exception as exc:
                self.state["gpd"]["error"] = str(exc)

    def _report(self, kind: str, **kwargs):
        if kind == "is_stopped":
            return self._stop_event.is_set()
        if kind == "log":
            self._post("log", **kwargs)
        elif kind == "progress":
            self._post("progress", **kwargs)
        elif kind == "point":
            self._current_points.append(kwargs)
            self._post("point", **kwargs)
        elif kind == "data":
            self._post("data", **kwargs)
        elif kind == "done":
            self._post("done", **kwargs)
        elif kind == "error":
            self._post("log", text=kwargs.get("text", ""), tag="error")

    def _run_routine(self, module_path: str, params: dict):
        self._routine_running = True
        self._stop_event.clear()
        self._current_points.clear()
        self._current_routine_name = Path(module_path).stem

        if self.k2400 is None or self.gpd is None:
            self._post("log", text="请先连接 K2400 和 GPD4303S", tag="error")
            self._post("done", success=False)
            self._routine_running = False
            return

        try:
            spec = importlib.util.spec_from_file_location("routine_module", module_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            for attr in ("NAME", "PARAMS", "run"):
                if not hasattr(module, attr):
                    raise ValueError(f"例程文件缺少必要对象: {attr}")

            self._post("log", text=f"开始运行例程: {module.NAME}")
            instruments = {"k2400": self.k2400, "gpd": self.gpd}
            module.run(instruments, params, self._report)
        except Exception as exc:
            self._post("log", text=f"例程运行异常: {exc}", tag="error")
            self._post("done", success=False)
        finally:
            self._routine_running = False

    def run(self):
        while self._running:
            try:
                cmd = self.cmd_queue.get_nowait()
                self._handle_cmd(cmd)
            except queue.Empty:
                pass

            if not self._routine_running:
                self._poll_instruments()

            time.sleep(0.25)

        self._disconnect_all()

    def stop(self):
        self._running = False
        self._stop_event.set()
        self.cmd_queue.put(("disconnect_all",))


# ---------------------------------------------------------------------------
# 主 GUI
# ---------------------------------------------------------------------------
class K2400GPDRoutineApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Keithley 2400 + GPD4303S 联合测试例程平台")
        self.dpi = _set_tk_scaling(self)
        self.geometry(f"{_dpi_scale(1400, self.dpi)}x{_dpi_scale(900, self.dpi)}")
        self.configure(bg="#F3F5F7")

        self.style = ttk.Style(self)
        self.style.configure(".", font=("Microsoft YaHei UI", 9))
        self.style.configure("Value.TLabel", font=("Consolas", 10, "bold"))
        self.style.configure("Title.TLabel", font=("Microsoft YaHei UI", 10, "bold"))

        self.state = {
            "k2400": {"connected": False, "idn": "", "v": None, "i": None, "r": None, "output": False, "error": ""},
            "gpd": {"connected": False, "idn": "", "output": False, "channels": {}, "error": ""},
        }
        self.msg_queue: queue.Queue = queue.Queue()
        self.cmd_queue: queue.Queue = queue.Queue()
        self.worker = RoutineWorker(self.state, self.msg_queue, self.cmd_queue)
        self.worker.start()

        self.routine_module: object | None = None
        self.routine_path: str = ""
        self.param_vars: dict[str, tk.Variable] = {}
        self.param_widgets: list[tk.Widget] = []
        self.data_points: list[dict] = []

        self._build_ui()
        self._load_config()
        self._refresh_ports()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(UPDATE_MS, self._poll_messages)

    # -----------------------------------------------------------------------
    # UI 构建
    # -----------------------------------------------------------------------
    def _build_ui(self):
        main_frame = tk.Frame(self, bg="#F3F5F7")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        left = tk.Frame(main_frame, bg="#FFFFFF", highlightbackground="#E2E8F0", highlightthickness=1)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left.pack_propagate(False)
        left.config(width=_dpi_scale(480, self.dpi))

        right = tk.Frame(main_frame, bg="#FFFFFF", highlightbackground="#E2E8F0", highlightthickness=1)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(left, bg="#FFFFFF", highlightthickness=0)
        scrollbar = ttk.Scrollbar(left, orient=tk.VERTICAL, command=canvas.yview)
        self.left_content = tk.Frame(canvas, bg="#FFFFFF")
        self.left_content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.left_content, anchor=tk.NW, width=_dpi_scale(460, self.dpi))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._build_instrument_panels(self.left_content)
        self._build_routine_panel(self.left_content)
        self._build_control_panel(self.left_content)
        self._build_right_panel(right)

    def _build_instrument_panels(self, parent):
        # K2400
        kf = ttk.LabelFrame(parent, text=" Keithley 2400 连接 ", padding=10)
        kf.pack(fill=tk.X, padx=10, pady=(10, 5))

        ttk.Label(kf, text="COM 口:").grid(row=0, column=0, sticky=tk.W, pady=3)
        self.k2400_port_var = tk.StringVar(value="")
        self.k2400_port_combo = ttk.Combobox(kf, textvariable=self.k2400_port_var, values=[], width=12, state="readonly")
        self.k2400_port_combo.grid(row=0, column=1, padx=4, pady=3)
        ttk.Button(kf, text="⟳", width=3, command=self._refresh_ports).grid(row=0, column=2, padx=2, pady=3)

        ttk.Label(kf, text="波特率:").grid(row=1, column=0, sticky=tk.W, pady=3)
        self.k2400_baud_var = tk.StringVar(value="9600")
        ttk.Combobox(kf, textvariable=self.k2400_baud_var, values=["9600", "57600", "115200"], width=10, state="readonly").grid(row=1, column=1, padx=4, pady=3)

        self.k2400_conn_btn = ttk.Button(kf, text="连接", command=lambda: self._toggle_connect("k2400"))
        self.k2400_conn_btn.grid(row=1, column=2, padx=2, pady=3)

        self.k2400_status_lbl = ttk.Label(kf, text="未连接", foreground="gray")
        self.k2400_status_lbl.grid(row=0, column=3, padx=(10, 0), pady=3)

        self.k2400_idn_lbl = ttk.Label(kf, text="IDN: --", wraplength=300)
        self.k2400_idn_lbl.grid(row=2, column=0, columnspan=4, sticky=tk.W, pady=3)

        self.k2400_read_lbl = ttk.Label(kf, text="V: --  I: --  R: --", style="Value.TLabel")
        self.k2400_read_lbl.grid(row=3, column=0, columnspan=4, sticky=tk.W, pady=3)

        # GPD
        gf = ttk.LabelFrame(parent, text=" GPD4303S 连接 ", padding=10)
        gf.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(gf, text="COM 口:").grid(row=0, column=0, sticky=tk.W, pady=3)
        self.gpd_port_var = tk.StringVar(value="")
        self.gpd_port_combo = ttk.Combobox(gf, textvariable=self.gpd_port_var, values=[], width=12, state="readonly")
        self.gpd_port_combo.grid(row=0, column=1, padx=4, pady=3)

        ttk.Label(gf, text="波特率:").grid(row=1, column=0, sticky=tk.W, pady=3)
        self.gpd_baud_var = tk.StringVar(value="9600")
        ttk.Combobox(gf, textvariable=self.gpd_baud_var, values=["9600", "57600", "115200"], width=10, state="readonly").grid(row=1, column=1, padx=4, pady=3)

        self.gpd_conn_btn = ttk.Button(gf, text="连接", command=lambda: self._toggle_connect("gpd"))
        self.gpd_conn_btn.grid(row=1, column=2, padx=2, pady=3)

        self.gpd_status_lbl = ttk.Label(gf, text="未连接", foreground="gray")
        self.gpd_status_lbl.grid(row=0, column=3, padx=(10, 0), pady=3)

        self.gpd_idn_lbl = ttk.Label(gf, text="IDN: --", wraplength=300)
        self.gpd_idn_lbl.grid(row=2, column=0, columnspan=4, sticky=tk.W, pady=3)

        self.gpd_output_lbl = ttk.Label(gf, text="总输出: 关", foreground="red", font=("", 9, "bold"))
        self.gpd_output_lbl.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=3)

        # 通道卡片
        cards = ttk.Frame(gf)
        cards.grid(row=4, column=0, columnspan=4, sticky=tk.EW, pady=(5, 0))
        self.gpd_channel_lbls: dict[tuple[int, str], ttk.Label] = {}
        for i, ch in enumerate(CHANNELS):
            col = i % 2
            row = i // 2
            card = ttk.LabelFrame(cards, text=f" CH{ch} ", padding=5)
            card.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
            cards.columnconfigure(col, weight=1)
            ttk.Label(card, text="Vout:").grid(row=0, column=0, sticky=tk.W)
            v_lbl = ttk.Label(card, text="--", style="Value.TLabel")
            v_lbl.grid(row=0, column=1, sticky=tk.W)
            ttk.Label(card, text="Iout:").grid(row=1, column=0, sticky=tk.W)
            i_lbl = ttk.Label(card, text="--", style="Value.TLabel")
            i_lbl.grid(row=1, column=1, sticky=tk.W)
            ttk.Label(card, text="模式:").grid(row=2, column=0, sticky=tk.W)
            m_lbl = ttk.Label(card, text="--")
            m_lbl.grid(row=2, column=1, sticky=tk.W)
            self.gpd_channel_lbls[(ch, "v_out")] = v_lbl
            self.gpd_channel_lbls[(ch, "i_out")] = i_lbl
            self.gpd_channel_lbls[(ch, "mode")] = m_lbl

    def _build_routine_panel(self, parent):
        rf = ttk.LabelFrame(parent, text=" 测试例程 ", padding=10)
        rf.pack(fill=tk.X, padx=10, pady=5)

        ttk.Button(rf, text="加载例程文件 (.py)", command=self._load_routine).pack(fill=tk.X, pady=3)

        self.routine_name_lbl = ttk.Label(rf, text="例程: 未加载", style="Title.TLabel")
        self.routine_name_lbl.pack(anchor=tk.W, pady=(5, 0))

        self.routine_desc_lbl = ttk.Label(rf, text="", wraplength=400)
        self.routine_desc_lbl.pack(anchor=tk.W, pady=(0, 5))

        self.params_frame = ttk.Frame(rf)
        self.params_frame.pack(fill=tk.X, pady=5)

    def _build_control_panel(self, parent):
        cf = ttk.LabelFrame(parent, text=" 运行控制 ", padding=10)
        cf.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(cf, text="输出目录:").grid(row=0, column=0, sticky=tk.W, pady=3)
        self.output_dir_var = tk.StringVar(value=str(Path(__file__).resolve().parent.parent / "data"))
        ttk.Entry(cf, textvariable=self.output_dir_var, width=30).grid(row=0, column=1, padx=4, pady=3)
        ttk.Button(cf, text="浏览", command=self._browse_output_dir).grid(row=0, column=2, padx=4, pady=3)

        btn_frame = ttk.Frame(cf)
        btn_frame.grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=(10, 5))
        self.run_btn = ttk.Button(btn_frame, text="▶ 开始例程", command=self._start_routine, state=tk.DISABLED)
        self.run_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.stop_btn = ttk.Button(btn_frame, text="■ 停止", command=self._stop_routine, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.disconnect_btn = ttk.Button(btn_frame, text="⏻ 断开所有仪器", command=self._disconnect_all_instruments)
        self.disconnect_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(cf, variable=self.progress_var, maximum=100.0, length=300)
        self.progress_bar.grid(row=2, column=0, columnspan=3, sticky=tk.EW, pady=(5, 0))

        self.error_lbl = ttk.Label(cf, text="", foreground="red")
        self.error_lbl.grid(row=3, column=0, columnspan=3, sticky=tk.W, pady=(5, 0))

    def _build_right_panel(self, parent):
        plot_frame = ttk.LabelFrame(parent, text=" 数据曲线 ", padding=5)
        plot_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))

        self.fig = Figure(figsize=(7, 5), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_xlabel("Voltage (V)")
        self.ax.set_ylabel("Current (A)")
        self.ax.set_title("I-V Curve")
        self.ax.grid(True, alpha=0.3)
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        log_frame = ttk.LabelFrame(parent, text=" 运行日志 ", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 10))
        self.log_text = tk.Text(log_frame, wrap=tk.WORD, state=tk.DISABLED, bg="#0F172A",
                                fg="#E2E8F0", font=("Consolas", 9))
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=sb.set)
        self.log_text.tag_configure("info", foreground="#E2E8F0")
        self.log_text.tag_configure("warn", foreground="#FBBF24")
        self.log_text.tag_configure("error", foreground="#F87171")

    # -----------------------------------------------------------------------
    # 交互逻辑
    # -----------------------------------------------------------------------
    def _refresh_ports(self):
        ports = [p["port"] for p in list_com_ports()]
        self.k2400_port_combo["values"] = ports
        self.gpd_port_combo["values"] = ports
        if ports:
            if not self.k2400_port_var.get():
                self.k2400_port_var.set(ports[0])
            if not self.gpd_port_var.get():
                self.gpd_port_var.set(ports[0] if len(ports) < 2 else ports[1])

    def _toggle_connect(self, name: str):
        if self.state[name]["connected"]:
            self.cmd_queue.put(("disconnect", name))
        else:
            port = self.k2400_port_var.get() if name == "k2400" else self.gpd_port_var.get()
            baud = int(self.k2400_baud_var.get() if name == "k2400" else self.gpd_baud_var.get())
            if not port:
                self.error_lbl.config(text=f"请先选择 {name} 的 COM 口")
                return
            self.error_lbl.config(text="")
            self.cmd_queue.put(("connect", name, port, baud))

    def _load_routine(self):
        default_dir = Path(__file__).resolve().parent / "routines"
        default_dir.mkdir(exist_ok=True)
        path = filedialog.askopenfilename(
            title="选择测试例程",
            initialdir=str(default_dir),
            filetypes=[("Python 例程", "*.py"), ("所有文件", "*.*")]
        )
        if not path:
            return
        try:
            spec = importlib.util.spec_from_file_location("routine_module", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            for attr in ("NAME", "PARAMS", "run"):
                if not hasattr(module, attr):
                    raise ValueError(f"例程文件缺少必要对象: {attr}")
            self.routine_module = module
            self.routine_path = path
            self.routine_name_lbl.config(text=f"例程: {module.NAME}")
            self.routine_desc_lbl.config(text=getattr(module, "DESCRIPTION", ""))
            self._build_param_controls(module.PARAMS)
            self.run_btn.config(state=tk.NORMAL)
            self._log(f"已加载例程: {module.NAME} ({path})")
        except Exception as exc:
            messagebox.showerror("加载失败", f"无法加载例程文件:\n{exc}")
            self.routine_module = None
            self.routine_path = ""
            self.run_btn.config(state=tk.DISABLED)

    def _build_param_controls(self, params: list[dict]):
        for w in self.param_widgets:
            w.destroy()
        self.param_widgets.clear()
        self.param_vars.clear()

        for p in params:
            name = p["name"]
            label = p.get("label", name)
            ptype = p.get("type", "float")
            default = p.get("default", 0)

            row = ttk.Frame(self.params_frame)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=f"{label}:", width=22).pack(side=tk.LEFT)

            if ptype == "float":
                var = tk.DoubleVar(value=float(default))
                entry = ttk.Entry(row, textvariable=var, width=14)
                entry.pack(side=tk.LEFT)
            elif ptype == "int":
                var = tk.IntVar(value=int(default))
                entry = ttk.Entry(row, textvariable=var, width=14)
                entry.pack(side=tk.LEFT)
            elif ptype == "choice":
                var = tk.StringVar(value=str(default))
                choices = p.get("choices", [])
                combo = ttk.Combobox(row, textvariable=var, values=choices, width=12, state="readonly")
                combo.pack(side=tk.LEFT)
            elif ptype == "bool":
                var = tk.BooleanVar(value=bool(default))
                cb = ttk.Checkbutton(row, variable=var, text="启用")
                cb.pack(side=tk.LEFT)
            else:
                var = tk.StringVar(value=str(default))
                entry = ttk.Entry(row, textvariable=var, width=14)
                entry.pack(side=tk.LEFT)

            self.param_vars[name] = var
            self.param_widgets.append(row)

    def _get_params(self) -> dict:
        params = {}
        if self.routine_module is None:
            return params
        for p in self.routine_module.PARAMS:
            name = p["name"]
            var = self.param_vars.get(name)
            if var is None:
                continue
            ptype = p.get("type", "float")
            try:
                if ptype == "float":
                    params[name] = float(var.get())
                elif ptype == "int":
                    params[name] = int(var.get())
                elif ptype == "bool":
                    params[name] = bool(var.get())
                else:
                    params[name] = str(var.get())
            except Exception as exc:
                raise ValueError(f"参数 '{name}' 格式错误: {exc}")
        return params

    def _validate_params(self) -> bool:
        if self.routine_module is None:
            messagebox.showwarning("未加载例程", "请先加载测试例程")
            return False
        try:
            params = self._get_params()
            for p in self.routine_module.PARAMS:
                name = p["name"]
                value = params.get(name)
                if value is None:
                    continue
                if "min" in p and value < p["min"]:
                    raise ValueError(f"{p.get('label', name)} 不能小于 {p['min']}")
                if "max" in p and value > p["max"]:
                    raise ValueError(f"{p.get('label', name)} 不能大于 {p['max']}")
        except Exception as exc:
            messagebox.showerror("参数错误", str(exc))
            return False
        return True

    def _start_routine(self):
        if not self._validate_params():
            return
        if not (self.state["k2400"]["connected"] and self.state["gpd"]["connected"]):
            messagebox.showwarning("仪器未连接", "请先连接 K2400 和 GPD4303S")
            return

        self.data_points.clear()
        self.ax.clear()
        self.ax.set_xlabel("Voltage (V)")
        self.ax.set_ylabel("Current (A)")
        self.ax.set_title("I-V Curve")
        self.ax.grid(True, alpha=0.3)
        self.canvas.draw_idle()

        self.run_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.progress_var.set(0.0)
        self.error_lbl.config(text="")
        self._log(f"=== 开始运行: {self.routine_module.NAME} ===")

        params = self._get_params()
        self.cmd_queue.put(("run_routine", self.routine_path, params))

    def _stop_routine(self):
        self.cmd_queue.put(("stop_routine",))
        self._log("已请求停止例程", "warn")

    def _disconnect_all_instruments(self):
        """一键断开所有仪器，释放串口占用。"""
        self.cmd_queue.put(("disconnect_all",))
        self._log("已请求断开所有仪器", "warn")

    def _browse_output_dir(self):
        path = filedialog.askdirectory(title="选择输出目录", initialdir=self.output_dir_var.get())
        if path:
            self.output_dir_var.set(path)

    # -----------------------------------------------------------------------
    # 消息处理与 UI 刷新
    # -----------------------------------------------------------------------
    def _log(self, text: str, tag: str = "info"):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{datetime.datetime.now():%H:%M:%S}  {text}\n", tag)
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _update_plot(self):
        if not self.data_points:
            return
        vs = [p["voltage"] for p in self.data_points if "voltage" in p]
        is_ = [p["current"] for p in self.data_points if "current" in p]
        if len(vs) < 2:
            return
        self.ax.clear()
        self.ax.plot(vs, is_, "b-o", markersize=3, linewidth=1)
        self.ax.set_xlabel("Voltage (V)")
        self.ax.set_ylabel("Current (A)")
        self.ax.set_title("I-V Curve")
        self.ax.grid(True, alpha=0.3)
        self.canvas.draw_idle()

    def _save_data(self):
        if not self.data_points:
            return
        try:
            out_dir = Path(self.output_dir_var.get())
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            routine_name = self.routine_module.NAME if self.routine_module else "routine"
            folder = out_dir / f"k2400_gpd_{ts}"
            folder.mkdir(parents=True, exist_ok=True)

            csv_path = folder / f"{routine_name}.csv"
            with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
                if self.data_points:
                    writer = csv.DictWriter(f, fieldnames=self.data_points[0].keys())
                    writer.writeheader()
                    for row in self.data_points:
                        writer.writerow(row)

            meta = {
                "routine_name": routine_name,
                "routine_path": self.routine_path,
                "saved_at": datetime.datetime.now().isoformat(),
                "points": len(self.data_points),
                "k2400_idn": self.state["k2400"].get("idn", ""),
                "gpd_idn": self.state["gpd"].get("idn", ""),
                "params": self._get_params() if self.routine_module else {},
            }
            with open(folder / "metadata.json", "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)

            self._log(f"数据已保存: {folder}")
        except Exception as exc:
            self._log(f"保存数据失败: {exc}", "error")

    def _poll_messages(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                kind, kwargs = msg
                if kind == "log":
                    self._log(kwargs.get("text", ""), kwargs.get("tag", "info"))
                elif kind == "debug":
                    pass  # 调试日志可在此输出到额外面板
                elif kind == "progress":
                    current = kwargs.get("current", 0)
                    total = kwargs.get("total", 1)
                    pct = (current / total * 100.0) if total > 0 else 0.0
                    self.progress_var.set(pct)
                elif kind == "point":
                    self.data_points.append(kwargs)
                    if len(self.data_points) % 5 == 0:
                        self._update_plot()
                elif kind == "data":
                    self._update_plot()
                elif kind == "done":
                    self.run_btn.config(state=tk.NORMAL)
                    self.stop_btn.config(state=tk.DISABLED)
                    if kwargs.get("success", False):
                        self._log("例程运行完成")
                    else:
                        self._log("例程运行结束（未成功）", "warn")
                    self._save_data()
        except queue.Empty:
            pass

        self._update_instrument_ui()
        self.after(UPDATE_MS, self._poll_messages)

    def _update_instrument_ui(self):
        # K2400
        k = self.state["k2400"]
        if k["connected"]:
            self.k2400_status_lbl.config(text="已连接", foreground="green")
            self.k2400_conn_btn.config(text="断开")
            self.k2400_idn_lbl.config(text=f"IDN: {k.get('idn', '')}")
            v = k.get("v")
            i = k.get("i")
            r = k.get("r")
            self.k2400_read_lbl.config(
                text=f"V: {v:.4e} V  I: {i:.4e} A  R: {r:.4e} Ω" if v is not None else "V: --  I: --  R: --"
            )
        else:
            self.k2400_status_lbl.config(text="未连接", foreground="gray")
            self.k2400_conn_btn.config(text="连接")
            self.k2400_idn_lbl.config(text="IDN: --")
            self.k2400_read_lbl.config(text="V: --  I: --  R: --")
        err = k.get("error", "")
        if err:
            self.error_lbl.config(text=f"K2400: {err}")

        # GPD
        g = self.state["gpd"]
        if g["connected"]:
            self.gpd_status_lbl.config(text="已连接", foreground="green")
            self.gpd_conn_btn.config(text="断开")
            self.gpd_idn_lbl.config(text=f"IDN: {g.get('idn', '')}")
            output_on = g.get("output", False)
            if output_on:
                self.gpd_output_lbl.config(text="总输出: 开", foreground="green")
            else:
                self.gpd_output_lbl.config(text="总输出: 关", foreground="red")
            channels = g.get("channels", {})
            for ch in CHANNELS:
                data = channels.get(ch, {})
                v_out = data.get("v_out")
                i_out = data.get("i_out")
                mode = data.get("mode")
                self.gpd_channel_lbls[(ch, "v_out")].config(text=f"{v_out:.3f} V" if v_out is not None else "--")
                self.gpd_channel_lbls[(ch, "i_out")].config(text=f"{i_out:.3f} A" if i_out is not None else "--")
                self.gpd_channel_lbls[(ch, "mode")].config(text=mode if mode else "--")
        else:
            self.gpd_status_lbl.config(text="未连接", foreground="gray")
            self.gpd_conn_btn.config(text="连接")
            self.gpd_idn_lbl.config(text="IDN: --")
            self.gpd_output_lbl.config(text="总输出: 关", foreground="red")
            for ch in CHANNELS:
                self.gpd_channel_lbls[(ch, "v_out")].config(text="--")
                self.gpd_channel_lbls[(ch, "i_out")].config(text="--")
                self.gpd_channel_lbls[(ch, "mode")].config(text="--")
        err = g.get("error", "")
        if err:
            self.error_lbl.config(text=f"GPD: {err}")

    # -----------------------------------------------------------------------
    # 配置持久化
    # -----------------------------------------------------------------------
    def _load_config(self):
        if not CONFIG_FILE.is_file():
            return
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as exc:
            self._log(f"读取配置失败: {exc}", "warn")
            return
        mapping = {
            "k2400_port": (self.k2400_port_var, str),
            "k2400_baud": (self.k2400_baud_var, str),
            "gpd_port": (self.gpd_port_var, str),
            "gpd_baud": (self.gpd_baud_var, str),
            "output_dir": (self.output_dir_var, str),
            "routine_path": (None, str),  # 特殊处理
        }
        for key, (var, cast) in mapping.items():
            if key not in cfg:
                continue
            if key == "routine_path" and cfg[key]:
                self.routine_path = cfg[key]
            elif var is not None:
                try:
                    var.set(cast(cfg[key]))
                except Exception:
                    pass

    def _save_config(self):
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            cfg = {
                "k2400_port": self.k2400_port_var.get(),
                "k2400_baud": self.k2400_baud_var.get(),
                "gpd_port": self.gpd_port_var.get(),
                "gpd_baud": self.gpd_baud_var.get(),
                "output_dir": self.output_dir_var.get(),
                "routine_path": self.routine_path,
            }
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            self._log(f"保存配置失败: {exc}", "warn")

    def _on_close(self):
        self._save_config()
        if self.worker.is_alive():
            self.worker.stop()
            self.worker.join(timeout=3.0)
        self.destroy()


# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Keithley 2400 + GPD4303S 联合测试例程 GUI")
    args = parser.parse_args()
    app = K2400GPDRoutineApp()
    app.mainloop()


if __name__ == "__main__":
    main()

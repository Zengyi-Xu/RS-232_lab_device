"""扁平拟物风格 UI 示例（Flat Skeuomorphic）。

展示一种介于扁平化与拟物化之间的界面风格：
- 浅色柔和背景
- 圆角卡片 + 轻微投影
- 低饱和度主色 + 高对比文字
- 按钮有微妙的按压感
"""
import tkinter as tk
from tkinter import ttk


# 配色方案
COLOR_BG = "#F5F7FA"           # 极浅灰蓝背景
COLOR_CARD = "#FFFFFF"          # 纯白卡片
COLOR_BORDER = "#E2E8F0"        # 浅灰边框
COLOR_PRIMARY = "#3B82F6"       # 柔和蓝
COLOR_PRIMARY_HOVER = "#2563EB"
COLOR_SUCCESS = "#10B981"       # 柔和绿
COLOR_WARNING = "#F59E0B"       # 柔和橙
COLOR_DANGER = "#EF4444"        # 柔和红
COLOR_TEXT = "#1E293B"          # 深灰文字
COLOR_TEXT_DIM = "#64748B"      # 次要文字
COLOR_SHADOW = "#CBD5E1"        # 阴影色


class FlatSkeuomorphicDemo(tk.Tk):
    """扁平拟物风格演示窗口。"""

    def __init__(self):
        super().__init__()
        self.title("扁平拟物风格 UI 示例")
        self.configure(bg=COLOR_BG)
        self.geometry("900x700")

        self._setup_styles()
        self._build_ui()

    def _setup_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        # 按钮：圆角 + 微阴影 + 按压反馈
        style.configure("Flat.TButton",
                        font=("Microsoft YaHei UI", 10),
                        padding=(16, 8),
                        background=COLOR_CARD,
                        foreground=COLOR_TEXT,
                        borderwidth=1,
                        relief="solid",
                        bordercolor=COLOR_BORDER)
        style.map("Flat.TButton",
                  background=[("active", "#F1F5F9"), ("pressed", "#E2E8F0")],
                  relief=[("pressed", "sunken"), ("!pressed", "solid")])

        style.configure("Primary.TButton",
                        font=("Microsoft YaHei UI", 10, "bold"),
                        padding=(16, 8),
                        background=COLOR_PRIMARY,
                        foreground="white",
                        borderwidth=0)
        style.map("Primary.TButton",
                  background=[("active", COLOR_PRIMARY_HOVER)])

        style.configure("Success.TButton",
                        font=("Microsoft YaHei UI", 10),
                        padding=(16, 8),
                        background=COLOR_SUCCESS,
                        foreground="white",
                        borderwidth=0)

        style.configure("Danger.TButton",
                        font=("Microsoft YaHei UI", 10),
                        padding=(16, 8),
                        background=COLOR_DANGER,
                        foreground="white",
                        borderwidth=0)

        # 标签
        style.configure("Title.TLabel",
                        font=("Microsoft YaHei UI", 16, "bold"),
                        background=COLOR_BG,
                        foreground=COLOR_TEXT)
        style.configure("Section.TLabel",
                        font=("Microsoft YaHei UI", 11, "bold"),
                        background=COLOR_CARD,
                        foreground=COLOR_PRIMARY)
        style.configure("Dim.TLabel",
                        font=("Microsoft YaHei UI", 9),
                        background=COLOR_CARD,
                        foreground=COLOR_TEXT_DIM)

        # 输入框
        style.configure("Flat.TEntry",
                        font=("Microsoft YaHei UI", 10),
                        padding=(10, 6),
                        fieldbackground=COLOR_CARD,
                        borderwidth=1,
                        relief="solid",
                        bordercolor=COLOR_BORDER)

        # 下拉框
        style.configure("Flat.TCombobox",
                        font=("Microsoft YaHei UI", 10),
                        padding=(10, 6),
                        fieldbackground=COLOR_CARD,
                        borderwidth=1,
                        relief="solid")

        # 进度条
        style.configure("Flat.Horizontal.TProgressbar",
                        background=COLOR_PRIMARY,
                        troughcolor="#E2E8F0",
                        borderwidth=0,
                        thickness=8)

    def _build_ui(self):
        # 顶部标题
        header = tk.Frame(self, bg=COLOR_BG)
        header.pack(fill=tk.X, padx=24, pady=(24, 16))
        ttk.Label(header, text="扁平拟物风格 Lab Engine", style="Title.TLabel").pack(side=tk.LEFT)

        # 主内容区
        main = tk.Frame(self, bg=COLOR_BG)
        main.pack(fill=tk.BOTH, expand=True, padx=24, pady=(0, 24))

        # 左侧：卡片堆叠
        left = tk.Frame(main, bg=COLOR_BG)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 12))

        # 仪器连接卡片
        card1 = self._make_card(left, "仪器连接")
        self._add_instrument_row(card1, "Keithley 2400", "COM3", True)
        self._add_instrument_row(card1, "GPD-4303S", "COM4", False)
        self._add_instrument_row(card1, "Cornerstone 260", "USB", True)

        # 例程选择卡片
        card2 = self._make_card(left, "测试例程")
        self._add_routine_selector(card2)

        # 参数卡片
        card3 = self._make_card(left, "参数")
        self._add_param_row(card3, "起始电压 (V)", "0.0")
        self._add_param_row(card3, "终止电压 (V)", "2.0")
        self._add_param_row(card3, "扫描点数", "51")

        # 右侧：控制与状态
        right = tk.Frame(main, bg=COLOR_BG)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(12, 0))

        # 控制按钮卡片
        ctrl_card = self._make_card(right, "运行控制")
        btn_frame = tk.Frame(ctrl_card, bg=COLOR_CARD)
        btn_frame.pack(fill=tk.X, padx=16, pady=16)
        ttk.Button(btn_frame, text="▶ 开始例程", style="Primary.TButton").pack(
            side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_frame, text="■ 停止", style="Danger.TButton").pack(side=tk.LEFT)

        # 进度卡片
        prog_card = self._make_card(right, "进度")
        prog_inner = tk.Frame(prog_card, bg=COLOR_CARD)
        prog_inner.pack(fill=tk.X, padx=16, pady=16)
        ttk.Label(prog_inner, text="当前进度", style="Dim.TLabel").pack(anchor=tk.W)
        progress = ttk.Progressbar(prog_inner, style="Flat.Horizontal.TProgressbar",
                                   mode="determinate", value=65)
        progress.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(prog_inner, text="65%", style="Section.TLabel").pack(anchor=tk.E, pady=(4, 0))

        # 状态卡片
        status_card = self._make_card(right, "状态")
        status_inner = tk.Frame(status_card, bg=COLOR_CARD)
        status_inner.pack(fill=tk.X, padx=16, pady=16)
        self._add_status_row(status_inner, "K2400", "已连接", COLOR_SUCCESS)
        self._add_status_row(status_inner, "GPD4303S", "未连接", COLOR_TEXT_DIM)
        self._add_status_row(status_inner, "CS260", "已连接", COLOR_SUCCESS)
        self._add_status_row(status_inner, "SVA1032X", "错误", COLOR_DANGER)

        # 底部日志
        log_card = self._make_card(self, "运行日志")
        log_inner = tk.Frame(log_card, bg=COLOR_CARD)
        log_inner.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)
        log_text = tk.Text(log_inner, height=6, font=("Consolas", 9),
                           bg="#0F172A", fg="#E2E8F0", bd=0, highlightthickness=0)
        log_text.pack(fill=tk.BOTH, expand=True)
        log_text.insert(tk.END, "[INFO] Lab Engine 已启动\n")
        log_text.insert(tk.END, "[INFO] 已连接 Keithley 2400 (COM3)\n")
        log_text.insert(tk.END, "[WARN] GPD-4303S 未连接\n")
        log_text.insert(tk.END, "[INFO] 已加载例程: 基础 IV 扫描\n")
        log_text.configure(state=tk.DISABLED)

    def _make_card(self, parent, title):
        """创建带标题的卡片。"""
        card = tk.Frame(parent, bg=COLOR_CARD,
                        highlightbackground=COLOR_BORDER, highlightthickness=1, bd=0)
        card.pack(fill=tk.X, pady=(0, 12))
        hdr = tk.Frame(card, bg=COLOR_CARD)
        hdr.pack(fill=tk.X, padx=16, pady=(12, 8))
        ttk.Label(hdr, text=title, style="Section.TLabel").pack(anchor=tk.W)
        return card

    def _add_instrument_row(self, parent, name, port, connected):
        row = tk.Frame(parent, bg=COLOR_CARD)
        row.pack(fill=tk.X, padx=16, pady=4)
        ttk.Label(row, text=name, background=COLOR_CARD, foreground=COLOR_TEXT,
                  font=("Microsoft YaHei UI", 10)).pack(side=tk.LEFT)
        ttk.Label(row, text=port, style="Dim.TLabel").pack(side=tk.LEFT, padx=(8, 0))
        status = ttk.Label(row, text="● 已连接" if connected else "○ 未连接",
                           foreground=COLOR_SUCCESS if connected else COLOR_TEXT_DIM,
                           background=COLOR_CARD,
                           font=("Microsoft YaHei UI", 9))
        status.pack(side=tk.RIGHT)

    def _add_routine_selector(self, parent):
        row = tk.Frame(parent, bg=COLOR_CARD)
        row.pack(fill=tk.X, padx=16, pady=(0, 12))
        combo = ttk.Combobox(row, values=["基础 IV 扫描", "回滞扫描分析", "DMT 网格扫描"],
                             state="readonly", style="Flat.TCombobox")
        combo.set("基础 IV 扫描")
        combo.pack(fill=tk.X)

    def _add_param_row(self, parent, label, default):
        row = tk.Frame(parent, bg=COLOR_CARD)
        row.pack(fill=tk.X, padx=16, pady=4)
        ttk.Label(row, text=label, background=COLOR_CARD, foreground=COLOR_TEXT,
                  font=("Microsoft YaHei UI", 9), width=14).pack(side=tk.LEFT)
        entry = ttk.Entry(row, style="Flat.TEntry", width=16)
        entry.insert(0, default)
        entry.pack(side=tk.LEFT)

    def _add_status_row(self, parent, name, status, color):
        row = tk.Frame(parent, bg=COLOR_CARD)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text=name, background=COLOR_CARD, foreground=COLOR_TEXT,
                  font=("Microsoft YaHei UI", 9)).pack(side=tk.LEFT)
        ttk.Label(row, text=status, background=COLOR_CARD, foreground=color,
                  font=("Microsoft YaHei UI", 9, "bold")).pack(side=tk.RIGHT)


if __name__ == "__main__":
    app = FlatSkeuomorphicDemo()
    app.mainloop()

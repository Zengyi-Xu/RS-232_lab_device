"""实时数据曲线面板。"""
import tkinter as tk
from typing import Any, Dict, List, Optional

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from lab_engine.gui.shell import COLOR_CARD


class PlotPanel(tk.Frame):
    """基于 matplotlib 的实时曲线面板。"""

    def __init__(self, parent):
        super().__init__(parent, bg=COLOR_CARD)
        self.points: List[Dict[str, Any]] = []
        self.x_key: Optional[str] = None
        self.y_key: Optional[str] = None
        self._setup_ui()

    def _setup_ui(self):
        self.fig = Figure(figsize=(6, 4), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_title("等待数据...")
        self.ax.grid(True, alpha=0.3)
        self.fig.tight_layout()

        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.toolbar = NavigationToolbar2Tk(self.canvas, self)
        self.toolbar.update()

    def clear(self):
        """清空数据。"""
        self.points = []
        self.x_key = None
        self.y_key = None
        self.ax.clear()
        self.ax.set_title("等待数据...")
        self.ax.grid(True, alpha=0.3)
        self.canvas.draw_idle()

    def add_point(self, **kwargs: Any):
        """添加一个数据点并尝试自动绘图。"""
        self.points.append(dict(kwargs))
        self._auto_select_axes()
        if self.x_key and self.y_key and len(self.points) % 3 == 0:
            self._redraw()

    def add_points(self, points: List[Dict[str, Any]]):
        """批量添加数据点。"""
        self.points.extend(points)
        self._auto_select_axes()
        if self.x_key and self.y_key:
            self._redraw()

    def _auto_select_axes(self):
        """根据数据自动选择 x/y 列。"""
        if not self.points:
            return
        keys = list(self.points[0].keys())
        numeric_keys = [
            k for k in keys
            if isinstance(self.points[0].get(k), (int, float, np.number))
        ]
        if len(numeric_keys) < 2:
            return

        # 常见 I-V 扫描：优先 voltage / current
        if "voltage" in numeric_keys and "current" in numeric_keys:
            self.x_key = "voltage"
            self.y_key = "current"
        elif "x" in numeric_keys and "y" in numeric_keys:
            self.x_key = "x"
            self.y_key = "y"
        else:
            self.x_key = numeric_keys[0]
            self.y_key = numeric_keys[1]

    def _redraw(self):
        """重绘曲线。"""
        if not self.x_key or not self.y_key:
            return
        xs = [p.get(self.x_key) for p in self.points if isinstance(p.get(self.x_key), (int, float, np.number))]
        ys = [p.get(self.y_key) for p in self.points if isinstance(p.get(self.y_key), (int, float, np.number))]
        if len(xs) < 2:
            return

        self.ax.clear()
        self.ax.plot(xs, ys, "b-o", markersize=3, linewidth=1)
        self.ax.set_xlabel(self.x_key)
        self.ax.set_ylabel(self.y_key)
        self.ax.set_title(f"{self.y_key} vs {self.x_key}")
        self.ax.grid(True, alpha=0.3)
        self.fig.tight_layout()
        self.canvas.draw_idle()

    def set_labels(self, xlabel: str, ylabel: str, title: str):
        """手动设置坐标轴标签。"""
        self.ax.set_xlabel(xlabel)
        self.ax.set_ylabel(ylabel)
        self.ax.set_title(title)
        self.canvas.draw_idle()

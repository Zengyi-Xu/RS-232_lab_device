"""临时测试：单独启动 SetupPanel。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import tkinter as tk
from lab_engine.core.registry import RoutineRegistry
from lab_engine.gui.setup_panel import SetupPanel

# 触发仪器注册
import lab_engine.instruments  # noqa: F401

root = tk.Tk()
root.title("Setup Panel Test")
root.geometry("1200x800")

registry = RoutineRegistry()
registry.discover([Path(__file__).resolve().parent / "lab_engine" / "routines"])

panel = SetupPanel(root, routine_registry=registry)
panel.pack(fill=tk.BOTH, expand=True)

root.mainloop()

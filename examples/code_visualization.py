"""DMT_PY_NN 代码结构可视化示例。

扫描 DMT_PY_NN 项目的 Python 文件，提取模块导入关系，
用 lab_engine 的 SetupPanel 引擎绘制成依赖图。

运行：
    python examples/code_visualization.py [PROJECT_ROOT]

默认 PROJECT_ROOT 为 workspace 下的 DMT_PY_NN 目录。
"""
import ast
import sys
from pathlib import Path

# 把 lab_engine 加入路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tkinter as tk
from lab_engine.core.registry import RoutineRegistry
from lab_engine.core.setup_graph import Node, Port, SetupGraph
from lab_engine.gui.setup_panel import SetupPanel
from lab_engine.gui.shell import set_dpi_aware, set_tk_scaling, setup_plot_fonts


# 代码文件分类规则
def categorize(path: Path, root: Path) -> str:
    name = path.stem.lower()
    parts = [p.lower() for p in path.relative_to(root).parts[:-1]]

    if "gui" in name or "panel" in name:
        return "gui"
    if any(x in name for x in ["controller", "awg", "oscilloscope", "scope", "test_m8190a", "gpd4303s"]):
        return "hardware"
    if "nn" in parts or name.startswith("nn_") or "bigrgu" in name or "gru" in name:
        return "nn"
    if "plot" in name:
        return "plot"
    if "scan" in name:
        return "scan"
    if name in ["main", "dmt_core", "config", "utils", "virtual_channel", "record"]:
        return "core"
    return "util"


def module_name(path: Path, root: Path) -> str:
    """从文件路径生成模块全名，如 dmt_core 或 data.nn.ZY_BiGRU_GPU。"""
    rel = path.relative_to(root)
    parts = list(rel.with_suffix("").parts)
    return ".".join(parts)


def extract_imports(path: Path) -> set[str]:
    """解析单个 Python 文件，返回导入的顶层模块名集合。"""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except Exception:
        return set()

    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split(".")[0])
    return imports


def find_target_module(import_name: str, project_modules: set[str]) -> str | None:
    """把一次导入名匹配到项目内的具体模块。"""
    if import_name in project_modules:
        return import_name
    candidates = [m for m in project_modules if m.startswith(import_name + ".")]
    if candidates:
        return max(candidates, key=len)
    return None


def _compute_depths(graph: SetupGraph, max_depth: int = 8, edge_filter=None) -> dict[str, int]:
    """计算每个节点的依赖深度。

    - 忽略自环（递归不改变层级）
    - 深度上限 max_depth，避免循环依赖把层级拉爆
    - edge_filter: 可选，只统计满足条件的边参与层级计算
    """
    depth = {n.node_id: 0 for n in graph.nodes.values()}
    max_iter = len(graph.nodes) * 2
    for _ in range(max_iter):
        changed = False
        for edge in graph.edges.values():
            if edge.source_node == edge.target_node:
                continue
            if edge_filter and not edge_filter(edge):
                continue
            d = min(depth[edge.source_node] + 1, max_depth)
            if d > depth[edge.target_node]:
                depth[edge.target_node] = d
                changed = True
        if not changed:
            break
    return depth


def layout_by_depth(graph: SetupGraph, level_width: int = 280, level_height: int = 140):
    """按依赖深度分层布局。"""
    depth = _compute_depths(graph)

    levels: dict[int, list] = {}
    for node in graph.nodes.values():
        levels.setdefault(depth[node.node_id], []).append(node)

    # 帮助文本在左上角，节点统一放到其下方的空白处
    start_x = 80
    start_y = 220
    for lvl, nodes in levels.items():
        for i, node in enumerate(nodes):
            node.x = start_x + lvl * level_width
            node.y = start_y + i * level_height


def _signature(func: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """返回函数/方法签名字符串（简化版）。"""
    parts = []
    for arg in func.args.args:
        s = arg.arg
        if arg.annotation and hasattr(ast, "unparse"):
            s += f": {ast.unparse(arg.annotation)}"
        parts.append(s)
    if func.args.vararg:
        parts.append(f"*{func.args.vararg.arg}")
    if func.args.kwarg:
        parts.append(f"**{func.args.kwarg.arg}")
    return f"({', '.join(parts)})"


def _resolve_call_name(func_node, current_class: str | None) -> str | None:
    """把 ast.Call.func 解析为限定函数/方法名。"""
    if isinstance(func_node, ast.Name):
        return func_node.id
    if isinstance(func_node, ast.Attribute):
        if isinstance(func_node.value, ast.Name):
            if func_node.value.id == "self" and current_class:
                return f"{current_class}.{func_node.attr}"
            return f"{func_node.value.id}.{func_node.attr}"
    return None


def _find_calls(expr) -> list:
    """找出表达式中所有的 Call 节点。"""
    return [node for node in ast.walk(expr) if isinstance(node, ast.Call)]


def _add_param_ports(node: Node, params: list[str], skip_self: bool = False):
    """为函数/方法节点添加参数输入端口、called_by 输入端口、return 和 calls_out 输出端口。"""
    if skip_self and params and params[0] == "self":
        params = params[1:]
    ports = [Port(f"param_{i}", param, "input", "data") for i, param in enumerate(params)]
    ports.append(Port("called_by", "被调用", "input", "control"))
    ports.append(Port("return", "return", "output", "data"))
    ports.append(Port("calls_out", "调用", "output", "control"))
    node.ports = ports
    return params


def build_internal_graph(path: Path) -> SetupGraph:
    """解析单个 Python 文件，构建函数间依赖与数据流图。"""
    graph = SetupGraph()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return graph

    classes = []
    functions = []
    methods: dict[tuple[str, str], ast.FunctionDef] = {}

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            classes.append(node)
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods[(node.name, item.name)] = item
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node)

    # qualified_name -> (graph_node, ast_node, params, current_class)
    func_defs: dict[str, tuple[Node, ast.FunctionDef, list[str], str | None]] = {}

    # 创建 class 节点
    for cls in classes:
        graph.add_node(
            "class",
            x=0, y=0,
            label=cls.name,
            data={
                "type": "class",
                "lineno": cls.lineno,
                "path": str(path),
                "bases": [ast.unparse(b) for b in cls.bases] if hasattr(ast, "unparse") else [],
            },
        )

    # 创建 function 节点
    for func in functions:
        params = [arg.arg for arg in func.args.args]
        node = graph.add_node(
            "function",
            x=0, y=0,
            label=func.name,
            data={
                "type": "function",
                "lineno": func.lineno,
                "path": str(path),
                "signature": _signature(func),
            },
        )
        params = _add_param_ports(node, params)
        func_defs[func.name] = (node, func, params, None)

    # 创建 method 节点
    for (cls_name, meth_name), func in methods.items():
        params = [arg.arg for arg in func.args.args]
        node = graph.add_node(
            "method",
            x=0, y=0,
            label=f"{cls_name}.{meth_name}",
            data={
                "type": "method",
                "lineno": func.lineno,
                "path": str(path),
                "parent": cls_name,
                "signature": _signature(func),
            },
        )
        params = _add_param_ports(node, params, skip_self=True)
        func_defs[f"{cls_name}.{meth_name}"] = (node, func, params, cls_name)

    # 分析函数体，建立数据流边
    for qname, (node, func, params, current_class) in func_defs.items():
        _analyze_function_body(graph, node, func, params, func_defs, current_class)

    _layout_internal_nodes(graph)
    return graph


def _analyze_function_body(graph, caller_node, func, params, func_defs, current_class):
    """分析单个函数体，建立参数/返回值/调用的数据流边。"""
    origins = {}  # var_name -> (source_node_id, source_port_name)
    for i, param in enumerate(params):
        origins[param] = (caller_node.node_id, f"param_{i}")

    # Pass 1: 跟踪赋值，建立变量来源
    for stmt in ast.walk(func):
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
            target = stmt.targets[0].id
            if isinstance(stmt.value, ast.Call):
                callee = _resolve_call_name(stmt.value.func, current_class)
                if callee in func_defs:
                    origins[target] = (func_defs[callee][0].node_id, "return")
            elif isinstance(stmt.value, ast.Name) and stmt.value.id in origins:
                origins[target] = origins[stmt.value.id]

    # Pass 2: 为函数调用和 return 建立调用边与数据流边
    seen_calls = set()  # 避免同一函数对重复调用边
    for stmt in ast.walk(func):
        if isinstance(stmt, ast.Call):
            callee = _resolve_call_name(stmt.func, current_class)
            if callee in func_defs:
                callee_node, callee_func, callee_params, _ = func_defs[callee]
                # 通用调用边（红色 control 类型，表示调用关系），同一对只加一次
                key = (caller_node.node_id, callee_node.node_id)
                if key not in seen_calls:
                    seen_calls.add(key)
                    graph.add_edge(
                        caller_node.node_id, "calls_out",
                        callee_node.node_id, "called_by",
                        allow_multi_input=True,
                    )
                # 数据流边：把已知来源的实参连到对应形参
                for i, arg in enumerate(stmt.args):
                    if i >= len(callee_params):
                        break
                    if isinstance(arg, ast.Name) and arg.id in origins:
                        src_node_id, src_port = origins[arg.id]
                        graph.add_edge(src_node_id, src_port, callee_node.node_id, f"param_{i}")
        elif isinstance(stmt, ast.Return) and stmt.value:
            if isinstance(stmt.value, ast.Name) and stmt.value.id in origins:
                src_node_id, src_port = origins[stmt.value.id]
                graph.add_edge(src_node_id, src_port, caller_node.node_id, "return")
            for call in _find_calls(stmt.value):
                callee = _resolve_call_name(call.func, current_class)
                if callee in func_defs:
                    graph.add_edge(func_defs[callee][0].node_id, "return", caller_node.node_id, "return")


def _layout_internal_nodes(graph: SetupGraph, level_width: int = 320, level_gap: int = 40):
    """按依赖深度分列布局内部节点，支持可变高度。

    只用调用边计算层级，使上游调用者在左、下游被调用者在右。
    数据流边只作为连线展示，不参与层级计算，避免循环。
    """
    # 内部视图只用调用边计算层级，避免数据回传造成循环
    depth = _compute_depths(graph, edge_filter=lambda e: e.source_port == "calls_out")

    levels: dict[int, list] = {}
    for node in graph.nodes.values():
        levels.setdefault(depth[node.node_id], []).append(node)

    # 同一层内按类型排序：class 在前，function 其次，method 最后
    type_order = {"class": 0, "function": 1, "method": 2}

    start_x = 80
    start_y = 220
    for lvl, nodes in levels.items():
        nodes.sort(key=lambda n: (type_order.get(n.node_type, 3), n.label))
        y = start_y
        x = start_x + lvl * level_width
        for node in nodes:
            node.x = x
            node.y = y
            n_ports = max(2, len(node.ports))
            h = max(80, 50 + n_ports * 28)
            y += h + level_gap


def open_internal_view(parent, path: Path, title: str, scale: float) -> None:
    """弹出新窗口显示模块内部结构。"""
    top = tk.Toplevel(parent)
    top.title(f"内部结构: {title}")
    sw, sh = parent.winfo_screenwidth(), parent.winfo_screenheight()
    w = min(int(sw * 0.8), 1400)
    h = min(int(sh * 0.8), 900)
    top.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    panel = SetupPanel(
        top,
        routine_registry=RoutineRegistry(),
        scale=scale,
        viewer_mode=True,
    )
    panel.pack(fill=tk.BOTH, expand=True)

    graph = build_internal_graph(path)
    panel.set_graph(graph)

    if graph.nodes:
        max_x = max(n.x for n in graph.nodes.values()) + 300
        max_y = max(n.y for n in graph.nodes.values()) + 300
        panel.canvas.configure(scrollregion=(0, 0, int(max_x * scale), int(max_y * scale)))


def build_graph(project_root: Path) -> SetupGraph:
    """扫描项目目录，构建模块依赖图。"""
    graph = SetupGraph()

    def should_include(p: Path) -> bool:
        if "__pycache__" in p.parts:
            return False
        if "codeplot_assets" in p.parts:
            return False
        return True

    py_files = [p for p in project_root.rglob("*.py") if should_include(p)]

    # 记录所有项目模块名
    project_modules = {module_name(p, project_root) for p in py_files}

    # 创建节点
    nodes_by_module: dict[str, object] = {}
    for p in py_files:
        mod = module_name(p, project_root)
        cat = categorize(p, project_root)
        node = graph.add_node(
            cat,
            x=100,
            y=100,
            label=p.stem,
            node_id=mod,
            data={"module": mod, "path": str(p.relative_to(project_root))},
        )
        node.ports = [
            Port("imports", "导入", "input", "data"),
            Port("exports", "导出", "output", "data"),
        ]
        nodes_by_module[mod] = node

    # 创建依赖边
    for p in py_files:
        src_mod = module_name(p, project_root)
        src_node = nodes_by_module.get(src_mod)
        if src_node is None:
            continue
        for imp in extract_imports(p):
            dst_mod = find_target_module(imp, project_modules)
            if dst_mod is None or dst_mod == src_mod:
                continue
            dst_node = nodes_by_module[dst_mod]
            graph.add_edge(src_node.node_id, "exports", dst_node.node_id, "imports")

    layout_by_depth(graph)
    return graph


def main():
    if len(sys.argv) > 1:
        project_root = Path(sys.argv[1]).resolve()
    else:
        project_root = Path(__file__).resolve().parent.parent.parent / "DMT_PY_NN"

    if not project_root.exists():
        print(f"项目目录不存在: {project_root}")
        print("用法: python examples/code_visualization.py [PROJECT_ROOT]")
        sys.exit(1)

    set_dpi_aware()
    root = tk.Tk()
    root.title(f"Code Structure: {project_root.name}")
    scale = set_tk_scaling(root)
    setup_plot_fonts()

    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    w = min(int(sw * 0.9), 1600)
    h = min(int(sh * 0.9), 1000)
    root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    registry = RoutineRegistry()
    registry.discover([Path(__file__).resolve().parent.parent / "lab_engine" / "routines"])

    def on_module_activate(node: Node):
        # 只在模块级节点上响应；内部视图里的 class/function/method 节点不触发
        if node.node_type in ("class", "function", "method"):
            return
        path_str = node.data.get("path")
        if not path_str:
            return
        path = project_root / path_str
        if not path.exists():
            return
        open_internal_view(root, path, node.label, scale)

    panel = SetupPanel(
        root,
        routine_registry=registry,
        scale=scale,
        on_node_activate=on_module_activate,
        node_activate_label="查看内部结构",
    )

    graph = build_graph(project_root)
    panel.set_graph(graph)

    # 根据节点范围调整滚动区域
    if graph.nodes:
        max_x = max(n.x for n in graph.nodes.values()) + 300
        max_y = max(n.y for n in graph.nodes.values()) + 200
        panel.canvas.configure(scrollregion=(0, 0, int(max_x * scale), int(max_y * scale)))

    panel.pack(fill=tk.BOTH, expand=True)
    root.mainloop()


if __name__ == "__main__":
    main()

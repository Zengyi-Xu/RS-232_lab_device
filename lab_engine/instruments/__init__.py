"""Lab Engine 仪器注册。

Phase 1 直接复用 ivlab 中的仪器驱动，只在这里补充引擎需要的元数据。
"""
from ivlab.instruments.cornerstone260 import Cornerstone260
from ivlab.instruments.gpd4303s import GPD4303S
from ivlab.instruments.keithley2400 import Keithley2400
from ivlab.instruments.sva1032x import SVA1032X

from lab_engine.core.registry import InstrumentRegistry


InstrumentRegistry.register(
    key="cornerstone260",
    cls_type=Cornerstone260,
    name="Cornerstone 260 单色仪",
    connection_params=[
        {"name": "dll_path", "label": "Cornerstone.dll 路径（留空自动查找）", "type": "str", "default": ""},
    ],
)


InstrumentRegistry.register(
    key="sva1032x",
    cls_type=SVA1032X,
    name="Siglent SVA1032X 频谱/矢网",
    connection_params=[
        {"name": "resource_name", "label": "VISA 资源名（留空自动发现）", "type": "str", "default": ""},
    ],
)


InstrumentRegistry.register(
    key="keithley2400",
    cls_type=Keithley2400,
    name="Keithley 2400",
    connection_params=[
        {"name": "port", "label": "串口 / GPIB 资源", "type": "port"},
        {"name": "baudrate", "label": "波特率", "type": "int", "default": 9600},
        {
            "name": "interface",
            "label": "接口",
            "type": "choice",
            "choices": ["rs232", "gpib"],
            "default": "rs232",
        },
    ],
)

InstrumentRegistry.register(
    key="gpd4303s",
    cls_type=GPD4303S,
    name="GPD-4303S 四通道直流电源",
    connection_params=[
        {"name": "port", "label": "串口", "type": "port"},
        {"name": "baudrate", "label": "波特率", "type": "int", "default": 9600},
    ],
)

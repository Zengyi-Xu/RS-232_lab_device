"""扫描参数配置模型"""
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class ScanConfig:
    """IV扫描配置"""
    start_v: float = 0.0          # 起始电压 (V)
    stop_v: float = 1.0           # 终止电压 (V)
    points: int = 101             # 点数
    nplc: float = 1.0             # NPLC
    compliance_i: float = 0.1     # 电流限值 (A)
    compliance_v: Optional[float] = None  # 电压限值 (V)
    source_mode: str = "voltage"  # voltage 或 current
    measure_func: str = "current" # current 或 voltage
    auto_range: bool = True
    fixed_range: Optional[float] = None
    source_delay: float = 0.0     # 源建立延迟 (s)
    output_on_before: bool = True
    output_off_after: bool = True
    n_average: int = 1            # 平均次数
    randomize_direction: bool = False  # 随机化扫描方向
    scan_type: str = "single"     # single, double, sweep (0->Vmax->0->-Vmax->0)

    def __post_init__(self):
        if self.points < 2:
            raise ValueError("points必须>=2")
        if self.n_average < 1:
            raise ValueError("n_average必须>=1")


@dataclass
class InstrumentConfig:
    """仪器连接配置"""
    port: Optional[str] = None        # 串口设备，如 /dev/ttyUSB0（GPIB 方式下可为 None）
    baudrate: int = 9600
    timeout: float = 5.0
    model: str = "2400"  # 2400, 2450, 2600B
    address: str = "smua"  # 2600B通道地址
    gpib_address: Optional[int] = None  # GPIB 地址（如 24）；设置后走 GPIB，忽略串口
    gpib_board: int = 0                 # GPIB 板卡号（单台 NI GPIB-USB-HS 时为 0）

"""基础IV扫描示例

运行方式（在项目根目录）: python examples/basic_iv_scan.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ivlab.instruments.keithley2400 import Keithley2400
from ivlab.core.config import ScanConfig
from ivlab.scanner.iv_scanner import IVScanner
from ivlab.scanner.data_handler import DataHandler
from ivlab.utils.port_scanner import interactive_select_port


def main():
    print("=== Keithley 2400 基础IV扫描 ===\n")

    # 选择端口
    port = interactive_select_port()

    # 连接仪器
    inst = Keithley2400(port=port, baudrate=9600)
    try:
        inst.connect()
        print(f"已连接: {inst.idn()}\n")

        # 配置扫描参数
        config = ScanConfig(
            start_v=0.0,
            stop_v=2.0,
            points=51,
            nplc=1.0,
            compliance_i=0.1,
            n_average=1,
            scan_type="single"
        )

        # 创建扫描器
        scanner = IVScanner(inst, config)

        # 执行扫描
        print("开始扫描...")
        results = scanner.run()

        # 保存数据
        handler = DataHandler(output_dir="./data")
        handler.save_scan_result(results[0], prefix="basic_iv")

        print(f"\n扫描完成！保存了 {len(results)} 组数据")
        print(f"电压范围: {results[0].voltages[0]:.3f}V ~ {results[0].voltages[-1]:.3f}V")
        print(f"电流范围: {results[0].currents.min():.3e}A ~ {results[0].currents.max():.3e}A")

    finally:
        inst.disconnect()
        print("\n仪器已断开")


if __name__ == "__main__":
    main()

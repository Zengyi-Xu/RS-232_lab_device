"""基础IV扫描示例

运行方式（在项目根目录）:
    python examples/basic_iv_scan.py                      # RS-232
    python examples/basic_iv_scan.py --gpib 22            # GPIB 地址 22（需 NI-VISA 后端）
    python examples/basic_iv_scan.py --gpib 22 --gpib-port COM8   # 串口转GPIB适配器（Prologix）
"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ivlab.instruments.keithley2400 import Keithley2400
from ivlab.instruments.keithley2400_gpib import Keithley2400GPIB
from ivlab.instruments.keithley2400_prologix import Keithley2400Prologix
from ivlab.core.config import ScanConfig
from ivlab.scanner.iv_scanner import IVScanner
from ivlab.scanner.data_handler import DataHandler
from ivlab.utils.port_scanner import interactive_select_port


def main():
    parser = argparse.ArgumentParser(description="Keithley 2400 基础 IV 扫描")
    parser.add_argument("--gpib", type=int, default=None,
                        help="GPIB 地址（如 22），指定后走 GPIB；否则走 RS-232")
    parser.add_argument("--gpib-port", type=str, default=None,
                        help="串口转GPIB适配器端口（如 COM8），与 --gpib 配合走 Prologix 适配器")
    parser.add_argument("--port", type=str, default=None,
                        help="串口号（如 COM3），不指定则交互式选择")
    args = parser.parse_args()

    print("=== Keithley 2400 基础IV扫描 ===\n")

    if args.gpib is not None and args.gpib_port:
        print(f"使用串口转GPIB适配器: {args.gpib_port}, GPIB 地址: {args.gpib}")
        inst = Keithley2400Prologix(port=args.gpib_port, gpib_addr=args.gpib)
    elif args.gpib is not None:
        print(f"使用 GPIB 地址: {args.gpib}")
        inst = Keithley2400GPIB(gpib_addr=args.gpib)
    else:
        port = args.port or interactive_select_port()
        print(f"使用串口: {port}")
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

"""Cornerstone 260 波长扫描示例

运行方式（在项目根目录）:
    python examples/wavelength_scan.py                # 默认 400→410 nm, 步长 2 nm
    python examples/wavelength_scan.py --start 500 --stop 600 --step 5
    python examples/wavelength_scan.py --port COM3    # RS-232 接口的 CS260

仅移动单色仪（无功率计）时输出波长-位置对照表；
接入光功率计可扩展为光谱扫描（见 WavelengthScanner 的 power_meter 参数）。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse

from ivlab.instruments.cornerstone260 import Cornerstone260
from ivlab.instruments.monochromator import Monochromator
from ivlab.scanner.wavelength_scanner import WavelengthScanner, WavelengthScanConfig
from ivlab.scanner.data_handler import DataHandler


def progress(current: int, total: int, wl: float, power):
    print(f"\r进度: {current}/{total}  波长 {wl:.2f} nm"
          + (f"  功率 {power:.3e}" if power is not None else ""), end="", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Cornerstone 260 波长扫描")
    parser.add_argument("--start", type=float, default=400.0, help="起始波长 (nm)")
    parser.add_argument("--stop", type=float, default=410.0, help="终止波长 (nm)")
    parser.add_argument("--step", type=float, default=2.0, help="步长 (nm)")
    parser.add_argument("--dwell", type=float, default=0.0, help="到位后驻留时间 (s)")
    parser.add_argument("--double", action="store_true", help="往返扫描")
    parser.add_argument("--close-shutter", action="store_true", help="扫描结束后关闭快门")
    parser.add_argument("--port", type=str, default=None,
                        help="串口号（如 COM3），指定后走 RS-232；否则走 USB")
    parser.add_argument("--dll", type=str, default=None, help="Cornerstone.dll 路径")
    parser.add_argument("--outdir", type=str, default="./data", help="数据输出目录")
    parser.add_argument("--plot", action="store_true", help="扫描后弹出图形窗口")
    args = parser.parse_args()

    print("=== Cornerstone 260 波长扫描 ===\n")

    if args.port:
        mono = Monochromator(port=args.port)
    else:
        mono = Cornerstone260(dll_path=args.dll)

    try:
        mono.connect()
        print(f"已连接: {mono.idn()}")
        print(f"当前波长: {mono.get_wavelength():.3f} nm, "
              f"快门: {'打开' if mono.get_shutter() else '关闭'}")
        print(f"光栅: {mono.get_grating()}\n")

        config = WavelengthScanConfig(
            start_nm=args.start,
            stop_nm=args.stop,
            step_nm=args.step,
            dwell_s=args.dwell,
            scan_type="double" if args.double else "single",
            close_shutter_after=args.close_shutter,
        )

        scanner = WavelengthScanner(mono, config)
        print(f"扫描范围: {args.start} → {args.stop} nm, 步长 {args.step} nm")
        results = scanner.run(progress_callback=progress)
        print()

        handler = DataHandler(output_dir=args.outdir)
        filepath = handler.save_wavelength_scan(results)
        print(f"数据已保存: {filepath}")

        if args.plot:
            import matplotlib.pyplot as plt
            for r in results:
                plt.plot(r.actual, label=r.direction)
            plt.xlabel("Wavelength (nm)")
            plt.legend()
            plt.show()

    finally:
        mono.disconnect()
        print("仪器已断开")


if __name__ == "__main__":
    main()

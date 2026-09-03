"""单色仪 + 源表联动扫描示例

运行方式（在项目根目录）:
    python examples/mono_iv_scan.py --gpib 22 --start 400 --stop 410 --steps 10 --voltage 1.0
    python examples/mono_iv_scan.py --port COM3 --start 400 --stop 410 --steps 10

默认单色仪走 USB（Newport DLL），2400 走 GPIB；加 --mono-port 可让单色仪走 RS-232。
"""
import argparse
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ivlab.instruments.cornerstone260 import Cornerstone260
from ivlab.instruments.keithley2400 import Keithley2400
from ivlab.instruments.keithley2400_gpib import Keithley2400GPIB
from ivlab.instruments.monochromator import Monochromator
from ivlab.utils.port_scanner import interactive_select_port


def setup_sourcemeter(args):
    """根据参数创建并连接 2400 源表（GPIB 优先）"""
    if args.gpib is not None:
        print(f"2400 使用 GPIB 地址: {args.gpib}")
        inst = Keithley2400GPIB(gpib_addr=args.gpib)
    else:
        port = args.port or interactive_select_port()
        print(f"2400 使用串口: {port}")
        inst = Keithley2400(port=port, baudrate=9600)
    inst.connect()
    print(f"2400 已连接: {inst.idn()}")
    return inst


def setup_monochromator(args):
    """根据参数创建并连接单色仪（USB 优先）"""
    if args.mono_port:
        print(f"单色仪使用串口: {args.mono_port}")
        mono = Monochromator(port=args.mono_port)
    else:
        print("单色仪使用 USB")
        mono = Cornerstone260()
    mono.connect()
    print(f"单色仪已连接: {mono.idn()}")
    return mono


def run_scan(mono, sourcemeter, start_nm, stop_nm, steps, voltage):
    """交替扫描波长并读取源表数据"""
    wavelengths = [start_nm + i * (stop_nm - start_nm) / (steps - 1) for i in range(steps)]
    results = []

    # 配置源表：电压源，开输出
    sourcemeter.set_source_mode("voltage")
    sourcemeter.set_compliance(0.1)
    sourcemeter.set_output_level(voltage)
    sourcemeter.output_on()
    print(f"\n2400 输出电压已设为 {voltage} V，输出开启")
    time.sleep(0.5)

    print(f"\n开始扫描: {start_nm} -> {stop_nm} nm, 共 {steps} 步\n")
    for i, wl in enumerate(wavelengths, 1):
        print(f"[{i}/{steps}] 移动单色仪到 {wl:.2f} nm ...")
        actual_wl = mono.goto_wavelength(wl)
        time.sleep(0.2)

        reading = sourcemeter.measure()
        row = {
            "step": i,
            "target_wavelength_nm": wl,
            "actual_wavelength_nm": actual_wl,
            "voltage_V": reading["voltage"],
            "current_A": reading["current"],
            "resistance_Ohm": reading["resistance"],
            "timestamp": reading["timestamp"],
        }
        results.append(row)
        print(f"       电压: {row['voltage_V']:.6f} V, 电流: {row['current_A']:.6e} A")

    sourcemeter.output_off()
    print("\n2400 输出已关闭")
    return results


def save_csv(results, outdir):
    """保存结果为 CSV"""
    Path(outdir).mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filepath = Path(outdir) / f"mono_iv_scan_{timestamp}.csv"

    fieldnames = [
        "step",
        "target_wavelength_nm",
        "actual_wavelength_nm",
        "voltage_V",
        "current_A",
        "resistance_Ohm",
        "timestamp",
    ]
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    return filepath


def main():
    parser = argparse.ArgumentParser(description="单色仪 + Keithley 2400 联动波长-IV 扫描")
    parser.add_argument("--start", type=float, required=True, help="起始波长 (nm)")
    parser.add_argument("--stop", type=float, required=True, help="终止波长 (nm)")
    parser.add_argument("--steps", type=int, default=10, help="扫描步数 (默认 10)")
    parser.add_argument("--voltage", type=float, default=1.0, help="2400 输出电压 (V, 默认 1.0)")
    parser.add_argument("--gpib", type=int, default=None, help="2400 GPIB 地址")
    parser.add_argument("--port", type=str, default=None, help="2400 串口号（不指定则交互选择）")
    parser.add_argument("--mono-port", type=str, default=None, help="单色仪串口号（不指定则走 USB）")
    parser.add_argument("--outdir", type=str, default="./data", help="CSV 输出目录")
    args = parser.parse_args()

    if args.steps < 2:
        raise ValueError("steps 必须 >= 2")

    print("=== 单色仪 + 2400 联动扫描 ===\n")

    mono = setup_monochromator(args)
    sourcemeter = setup_sourcemeter(args)

    try:
        results = run_scan(
            mono, sourcemeter,
            args.start, args.stop, args.steps, args.voltage
        )
        filepath = save_csv(results, args.outdir)
        print(f"\n数据已保存: {filepath}")
    finally:
        sourcemeter.disconnect()
        mono.disconnect()
        print("仪器已断开")


if __name__ == "__main__":
    main()

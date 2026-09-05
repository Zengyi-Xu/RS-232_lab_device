"""SVA1032X 频谱/矢量网络分析仪控制示例（USB-B / USB-TMC）

运行方式（在项目根目录）:
    python examples/sva1032x_demo.py                # VNA 模式 (S21) 演示
    python examples/sva1032x_demo.py --mode sa      # 频谱分析模式演示

前提：
    1. 用 USB A-B 线连接电脑与仪器 USB Device 口；
    2. 安装 NI-VISA（或 Keysight VISA），Windows 自动识别为 USB-TMC 设备；
    3. pip install pyvisa（已在 requirements.txt 中）。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse

from ivlab.instruments.sva1032x import SVA1032X


def demo_vna(sva: SVA1032X, args):
    """VNA 模式：S 参数测量"""
    print("\n--- VNA 模式（矢量网络分析）---")
    sva.set_mode("vna")

    # 测量参数：S11 或 S21
    sva.set_trace_count(1)
    sva.set_vna_parameter(args.param, trace=1)
    sva.set_vna_format("mlog", trace=1)
    print(f"测量参数: {args.param}, 格式: 对数幅度")

    # 扫频范围
    sva.set_frequency(start=args.start, stop=args.stop)
    sva.set_sweep_points(args.points)
    print(f"扫频: {args.start / 1e6:g} MHz ~ {args.stop / 1e6:g} MHz, {args.points} 点")

    # 幅值范围与刻度
    sva.set_amplitude(ref_level=args.ref_level, scale_per_div=args.scale)
    sva.set_reference_position(args.ref_pos)   # 参考点位置 0~10 格
    print(f"参考电平: {args.ref_level} dB, Scale: {args.scale} dB/div, "
          f"参考点位置: {args.ref_pos} 格")

    # 单次扫描 + Marker
    sva.single_sweep()
    sva.set_marker(1, True)
    sva.set_marker_mode(1, "normal")
    sva.set_marker_peak(1)                     # Marker 移到峰值
    m = sva.get_marker(1)
    print(f"Marker1 (峰值): {m['x'] / 1e6:.4f} MHz, {m['y']:.3f} dB")

    sva.set_marker(2, True)
    sva.set_marker_mode(2, "delta")
    sva.set_marker_position(2, args.marker_freq)   # Marker 位置
    sva.set_marker_reference(2, 1)                 # Delta 参考点为 Marker1
    m2 = sva.get_marker(2)
    print(f"Marker2 (Delta, 参考 Marker1): Δf = {m2['x'] / 1e3:g} kHz, "
          f"Δ幅度 = {m2['y']:.3f} dB")

    # Marker → 参考电平
    sva.set_marker_to_ref_level(1)
    print(f"已将 Marker1 幅度设为参考电平: "
          f"{sva.get_amplitude()['ref_level']} dB")


def demo_sa(sva: SVA1032X, args):
    """SA 模式：频谱分析"""
    print("\n--- SA 模式（频谱分析）---")
    sva.set_mode("sa")

    # 扫频范围（也可 center/span 方式）
    sva.set_frequency(center=args.center, span=args.span)
    f = sva.get_frequency()
    print(f"扫频: {f['start'] / 1e6:g} MHz ~ {f['stop'] / 1e6:g} MHz "
          f"(中心 {f['center'] / 1e6:g} MHz, SPAN {f['span'] / 1e6:g} MHz)")

    # 幅值范围与刻度
    sva.set_amplitude(ref_level=args.ref_level, scale_per_div=args.scale)
    print(f"参考电平: {args.ref_level} dBm, Scale: {args.scale} dB/div")

    # Marker：普通模式 + 峰值跟踪
    sva.set_marker(1, True)
    sva.set_marker_mode(1, "normal")
    sva.set_marker_position(1, args.marker_freq)
    sva.set_marker_peak_track(1, True)
    import time
    time.sleep(1.0)
    m = sva.get_marker(1)
    print(f"Marker1: {m['x'] / 1e6:.6f} MHz, {m['y']:.3f} dBm")

    # Delta Marker，参考点为 Marker1
    sva.set_marker(2, True)
    sva.set_marker_mode(2, "delta")
    sva.set_marker_reference(2, 1)
    m2 = sva.get_marker(2)
    print(f"Marker2 (Delta, 参考 Marker1): Δf = {m2['x'] / 1e3:g} kHz, "
          f"Δ幅度 = {m2['y']:.3f} dB")


def main():
    parser = argparse.ArgumentParser(description="Siglent SVA1032X 控制示例")
    parser.add_argument("--mode", choices=["sa", "vna"], default="vna",
                        help="仪器模式: sa=频谱分析, vna=矢量网络分析 (默认 vna)")
    parser.add_argument("--param", choices=["S11", "S21"], default="S21",
                        help="VNA 测量参数 (默认 S21)")
    parser.add_argument("--start", type=float, default=1e6,
                        help="起始频率 (Hz)，默认 1 MHz")
    parser.add_argument("--stop", type=float, default=3.2e9,
                        help="终止频率 (Hz)，默认 3.2 GHz")
    parser.add_argument("--center", type=float, default=2.4e9,
                        help="SA 中心频率 (Hz)，默认 2.4 GHz")
    parser.add_argument("--span", type=float, default=100e6,
                        help="SA 扫宽 (Hz)，默认 100 MHz")
    parser.add_argument("--points", type=int, default=1601,
                        help="扫描点数 (默认 1601)")
    parser.add_argument("--ref-level", type=float, default=0.0,
                        help="参考电平，SA 单位 dBm，VNA 单位 dB (默认 0)")
    parser.add_argument("--scale", type=float, default=10.0,
                        help="Scale/Div，dB/格 (默认 10)")
    parser.add_argument("--ref-pos", type=int, default=5,
                        help="参考点位置 0~10 格，仅 VNA (默认 5)")
    parser.add_argument("--marker-freq", type=float, default=2.4e9,
                        help="Marker2 频率位置 (Hz)，默认 2.4 GHz")
    parser.add_argument("--resource", type=str, default=None,
                        help="VISA 资源名（如 USB0::0xF4EC::xxx::INSTR），默认自动发现")
    args = parser.parse_args()

    print("=== Siglent SVA1032X 控制示例 ===")

    sva = SVA1032X(resource_name=args.resource)
    try:
        sva.connect()
        print(f"已连接: {sva.idn()}")
        print(f"当前模式: {sva.get_mode()}")

        if args.mode == "vna":
            demo_vna(sva, args)
        else:
            demo_sa(sva, args)

        # 查询错误队列
        errors = sva.check_errors()
        if errors:
            print(f"\n仪器错误队列: {errors}")
        else:
            print("\n无错误")

    finally:
        sva.disconnect()
        print("仪器已断开")


if __name__ == "__main__":
    main()

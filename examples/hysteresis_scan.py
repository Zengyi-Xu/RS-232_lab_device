"""回滞扫描与分析示例

运行方式（在项目根目录）: python examples/hysteresis_scan.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib.pyplot as plt

from ivlab.instruments.keithley2400 import Keithley2400
from ivlab.core.config import ScanConfig
from ivlab.scanner.iv_scanner import IVScanner
from ivlab.scanner.hysteresis import HysteresisAnalyzer
from ivlab.scanner.data_handler import DataHandler
from ivlab.utils.port_scanner import interactive_select_port


def plot_results(fwd, bwd, h_result):
    """绘制回滞曲线"""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # I-V 曲线
    ax = axes[0]
    ax.plot(fwd.voltages, fwd.currents, "b-", label="Forward", linewidth=1.5)
    ax.plot(bwd.voltages, bwd.currents, "r-", label="Backward", linewidth=1.5)
    ax.set_xlabel("Voltage (V)")
    ax.set_ylabel("Current (A)")
    ax.set_title("I-V Hysteresis Loop")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # ΔI 曲线
    ax = axes[1]
    ax.plot(h_result.voltage_grid, h_result.delta_i, "g-", linewidth=1.5)
    ax.axhline(0, color="k", linestyle="--", alpha=0.3)
    ax.set_xlabel("Voltage (V)")
    ax.set_ylabel("ΔI = I_bwd - I_fwd (A)")
    ax.set_title(f"Hysteresis Index = {h_result.hysteresis_index:.4f}")
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig("hysteresis_plot.png", dpi=150)
    plt.show()
    print("图表已保存: hysteresis_plot.png")


def main():
    print("=== 回滞扫描与分析 ===\n")

    port = interactive_select_port()
    inst = Keithley2400(port=port, baudrate=9600)

    try:
        inst.connect()
        print(f"已连接: {inst.idn()}\n")

        # 配置：双向扫描
        config = ScanConfig(
            start_v=-1.0,
            stop_v=1.0,
            points=101,
            nplc=1.0,
            compliance_i=0.1,
            n_average=2,           # 2次平均
            randomize_direction=True,
            scan_type="double"     # 正向+反向
        )

        scanner = IVScanner(inst, config)
        print("开始双向扫描（含平均）...")
        results = scanner.run()

        # 回滞分析
        analyzer = HysteresisAnalyzer()

        # 找到正向和反向结果（取最后一次的平均）
        fwd_results = [r for r in results if r.direction == "forward"]
        bwd_results = [r for r in results if r.direction == "backward"]

        if fwd_results and bwd_results:
            h_result = analyzer.analyze(fwd_results[-1], bwd_results[-1])

            print(f"\n=== 回滞分析结果 ===")
            print(f"回滞面积: {h_result.hysteresis_area:.3e} V·A")
            print(f"回滞指数: {h_result.hysteresis_index:.4f}")
            print(f"最大ΔI:   {h_result.delta_i_max:.3e} A")
            print(f"对称因子: {h_result.symmetry_factor:.3f}")

            # 保存数据
            handler = DataHandler(output_dir="./data")
            handler.save_scan_result(fwd_results[-1], prefix="hyst_fwd")
            handler.save_scan_result(bwd_results[-1], prefix="hyst_bwd")
            handler.save_hysteresis_result(h_result, prefix="hyst_analysis")

            # 绘图
            try:
                plot_results(fwd_results[-1], bwd_results[-1], h_result)
            except Exception as e:
                print(f"绘图失败: {e}")
        else:
            print("未找到配对的双向扫描结果")

    finally:
        inst.disconnect()
        print("\n仪器已断开")


if __name__ == "__main__":
    main()

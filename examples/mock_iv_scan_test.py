"""离线 mock 测试：用软件仿真的 Keithley 2400 跑通 IV 扫描全流程。

运行方式（项目根目录）:
    python examples/mock_iv_scan_test.py

本脚本不连接任何真实仪器，用于验证：
- Keithley 2400 驱动 / SCPI 命令解析
- IVScanner 的 single / double / sweep 三种扫描类型
- DataHandler 的 CSV 保存
- HysteresisAnalyzer 的回滞分析
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ivlab.core.config import ScanConfig
from ivlab.instruments.mock_keithley2400 import MockKeithley2400
from ivlab.scanner.data_handler import DataHandler
from ivlab.scanner.hysteresis import HysteresisAnalyzer
from ivlab.scanner.iv_scanner import IVScanner


def test_single_scan():
    print("\n=== 测试 single 单向扫描 ===")
    inst = MockKeithley2400()
    try:
        inst.connect()
        print(f"IDN: {inst.idn()}")

        config = ScanConfig(
            start_v=0.0,
            stop_v=2.0,
            points=51,
            nplc=1.0,
            compliance_i=0.1,
            scan_type="single",
            n_average=1,
        )
        scanner = IVScanner(inst, config)
        results = scanner.run()

        handler = DataHandler(output_dir="./data/mock")
        path = handler.save_scan_result(results[0], prefix="mock_single")
        print(f"保存: {path}")
        print(f"电压范围: {results[0].voltages[0]:.3f}V ~ {results[0].voltages[-1]:.3f}V")
        print(f"电流范围: {results[0].currents.min():.3e}A ~ {results[0].currents.max():.3e}A")
    finally:
        inst.disconnect()


def test_double_scan():
    print("\n=== 测试 double 双向扫描 + 回滞分析 ===")
    inst = MockKeithley2400()
    try:
        inst.connect()
        config = ScanConfig(
            start_v=-1.0,
            stop_v=1.0,
            points=101,
            nplc=1.0,
            compliance_i=0.1,
            scan_type="double",
            n_average=2,
            randomize_direction=True,
        )
        scanner = IVScanner(inst, config)
        results = scanner.run()

        fwd = [r for r in results if r.direction == "forward"][-1]
        bwd = [r for r in results if r.direction == "backward"][-1]

        analyzer = HysteresisAnalyzer()
        h = analyzer.analyze(fwd, bwd)

        print(f"回滞面积: {h.hysteresis_area:.3e} V·A")
        print(f"回滞指数: {h.hysteresis_index:.4f}")
        print(f"最大 ΔI:  {h.delta_i_max:.3e} A")

        handler = DataHandler(output_dir="./data/mock")
        handler.save_hysteresis_result(h, prefix="mock_hyst")
    finally:
        inst.disconnect()


def test_sweep_scan():
    print("\n=== 测试 sweep 往返扫描 ===")
    inst = MockKeithley2400()
    try:
        inst.connect()
        config = ScanConfig(
            start_v=0.0,
            stop_v=1.0,
            points=21,
            nplc=1.0,
            compliance_i=0.1,
            scan_type="sweep",
            n_average=1,
        )
        scanner = IVScanner(inst, config)
        results = scanner.run()
        print(f"扫描点数: {len(results[0].voltages)}")
        print(f"电压极值: min={results[0].voltages.min():.3f}V, max={results[0].voltages.max():.3f}V")
    finally:
        inst.disconnect()


def main():
    print("=== Mock Keithley 2400 离线测试 ===")
    test_single_scan()
    test_double_scan()
    test_sweep_scan()
    print("\n全部测试完成，数据保存在 ./data/mock/")


if __name__ == "__main__":
    main()

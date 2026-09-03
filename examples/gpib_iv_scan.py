"""GPIB 接口 IV 扫描示例（NI GPIB-USB-HS + Keithley 2400）"""
from ivlab.instruments.keithley2400 import Keithley2400
from ivlab.core.config import ScanConfig
from ivlab.scanner.iv_scanner import IVScanner
from ivlab.scanner.data_handler import DataHandler


def main():
    print("=== Keithley 2400 GPIB IV扫描 ===\n")

    # Keithley 2400 出厂默认 GPIB 地址为 24，
    # 可通过仪器前面板 MENU -> GPIB 地址 查看/修改
    gpib_address = int(input("请输入2400的GPIB地址 [默认24]: ") or "24")

    # 连接仪器（设置 gpib_address 后走 GPIB，不再需要串口参数）
    inst = Keithley2400(gpib_address=gpib_address)
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
        handler.save_scan_result(results[0], prefix="gpib_iv")

        print(f"\n扫描完成！保存了 {len(results)} 组数据")
        print(f"电压范围: {results[0].voltages[0]:.3f}V ~ {results[0].voltages[-1]:.3f}V")
        print(f"电流范围: {results[0].currents.min():.3e}A ~ {results[0].currents.max():.3e}A")

    finally:
        inst.disconnect()
        print("\n仪器已断开")


if __name__ == "__main__":
    main()

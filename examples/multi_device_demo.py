"""多仪器协调示例"""
from ivlab.instruments.keithley2400 import Keithley2400
from ivlab.instruments.monochromator import Monochromator
from ivlab.instruments.optical_power_meter import OpticalPowerMeter
from ivlab.scanner.multi_instrument import MultiInstrumentCoordinator, ScanStep
from ivlab.utils.port_scanner import list_com_ports


def main():
    print("=== 多仪器协调演示 ===\n")
    print("可用端口:")
    for p in list_com_ports():
        print(f"  {p['port']}: {p['description']}")

    # 创建协调器
    coord = MultiInstrumentCoordinator()

    # 添加仪器（使用模拟连接，实际使用时替换为真实端口）
    # source = Keithley2400(port="COM3")
    # mono = Monochromator(port="COM4")
    # power = OpticalPowerMeter(port="COM5")

    # coord.add_instrument("source", source)
    # coord.add_instrument("monochromator", mono)
    # coord.add_instrument("power_meter", power)

    # 定义扫描序列
    sequence = [
        # 1. 设置单色仪波长
        ScanStep("monochromator", "set_wavelength", {"wavelength": 500}, wait_after=1.0),

        # 2. 设置源表电压
        ScanStep("source", "set_voltage", {"voltage": 1.0}, wait_after=0.5),

        # 3. 读取光功率（同时读取所有仪器）
        ScanStep("power_meter", "read_power", {"read_all": True}, wait_after=0.2),

        # 4. 改变波长
        ScanStep("monochromator", "set_wavelength", {"wavelength": 600}, wait_after=1.0),

        # 5. 再次读取
        ScanStep("power_meter", "read_power", {"read_all": True}, wait_after=0.2),
    ]

    print("\n扫描序列定义完成，共", len(sequence), "步")
    print("实际运行时取消注释连接代码并替换为真实端口")

    # 执行序列
    # coord.connect_all()
    # data = coord.run_sequence(sequence)
    # coord.disconnect_all()


if __name__ == "__main__":
    main()

"""Cornerstone 260 单色仪波长扫描示例"""
import csv
import os
import time

from ivlab.instruments.monochromator import Monochromator
from ivlab.utils.port_scanner import interactive_select_port


def main():
    print("=== Cornerstone 260 单色仪波长扫描 ===\n")

    port = interactive_select_port()

    # Cornerstone 260 默认 RS-232 参数：9600 8N1
    mono = Monochromator(port=port, baudrate=9600, timeout=5.0)

    try:
        mono.connect()
        print(f"当前波长: {mono.query('WAVE?')} nm\n")

        # 扫描参数
        start_nm = 400.0
        stop_nm = 700.0
        step_nm = 10.0
        settle_s = 1.0  # 每个波长的稳定等待时间

        print(f"扫描范围: {start_nm:.1f} ~ {stop_nm:.1f} nm, 步长 {step_nm:.1f} nm")

        # 打开快门
        mono.output_on()

        # 执行扫描并记录
        data = []
        t0 = time.time()
        for wl in mono.scan_wavelength(start_nm, stop_nm, step_nm):
            time.sleep(settle_s)  # 等光栅稳定
            actual = float(mono.query("WAVE?"))
            data.append((actual, time.time() - t0))
            print(f"  {actual:.2f} nm  (t = {data[-1][1]:.1f} s)")

        # 保存 CSV
        os.makedirs("./data", exist_ok=True)
        filename = time.strftime("./data/mono_scan_%Y%m%d_%H%M%S.csv")
        with open(filename, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["wavelength_nm", "elapsed_s"])
            writer.writerows(data)
        print(f"\n已保存 {len(data)} 个波长点到: {filename}")

    finally:
        mono.output_off()
        mono.disconnect()
        print("\n仪器已断开")


if __name__ == "__main__":
    main()

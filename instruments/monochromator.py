"""Cornerstone 260 单色仪 - 预留接口"""
from .base import BaseInstrument


class Monochromator(BaseInstrument):
    """单色仪基类，预留 Cornerstone 260 接口"""

    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 5.0, logger=None):
        super().__init__(port, baudrate, timeout, model="CS260", logger=logger)

    def set_source_mode(self, mode: str):
        raise NotImplementedError("单色仪不支持源模式")

    def set_compliance(self, value: float):
        raise NotImplementedError("单色仪不支持合规限值")

    def set_nplc(self, nplc: float):
        raise NotImplementedError("单色仪不支持NPLC")

    def set_output_level(self, level: float):
        raise NotImplementedError("单色仪不支持输出电平")

    def measure(self) -> dict:
        """读取当前波长位置"""
        resp = self.query("WAVE?")
        return {
            "wavelength": float(resp),
            "timestamp": 0,
            "status": ""
        }

    def output_on(self):
        self.set_shutter("O")  # Open

    def output_off(self):
        self.set_shutter("C")  # Close

    def set_range(self, auto: bool, fixed_value=None):
        pass

    def set_wavelength(self, wavelength_nm: float):
        """设置波长 (nm)"""
        self.write(f"WAVE {wavelength_nm:.2f}")

    def set_shutter(self, state: str):
        """控制快门: O=Open, C=Close"""
        self.write(f"SHUTTER {state.upper()}")

    def goto_wavelength(self, wavelength_nm: float, wait: bool = True):
        """移动到指定波长并可选等待稳定"""
        self.set_wavelength(wavelength_nm)
        if wait:
            import time
            time.sleep(0.5)  # 等待光栅移动

    def scan_wavelength(self, start_nm: float, stop_nm: float, step_nm: float):
        """波长扫描序列生成器"""
        import numpy as np
        for wl in np.arange(start_nm, stop_nm + step_nm/2, step_nm):
            self.goto_wavelength(wl)
            yield wl

"""Keithley 2400 源表实现"""
from .scpi_instrument import SCPIInstrument


class Keithley2400(SCPIInstrument):
    """Keithley 2400 SourceMeter"""

    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 5.0, logger=None):
        super().__init__(port, baudrate, timeout, model="2400", logger=logger)

    def _post_connect(self):
        super()._post_connect()
        # 2400 特定初始化
        self.write(":SYST:RSEN OFF")  # 2线制测量（可改为4线制）
        self.write(":FORM:ELEM VOLT,CURR,RES,TIME,STAT")

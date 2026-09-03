"""Keithley 2400 源表实现"""
from typing import Optional
from .scpi_instrument import SCPIInstrument


class Keithley2400(SCPIInstrument):
    """Keithley 2400 SourceMeter"""

    def __init__(self, port: Optional[str] = None, baudrate: int = 9600, timeout: float = 5.0,
                 logger=None, gpib_address: Optional[int] = None, gpib_board: int = 0):
        super().__init__(port, baudrate, timeout, model="2400", logger=logger,
                         gpib_address=gpib_address, gpib_board=gpib_board)

    def _post_connect(self):
        super()._post_connect()
        # 2400 特定初始化
        self.write(":SYST:RSEN OFF")  # 2线制测量（可改为4线制）
        self.write(":FORM:ELEM VOLT,CURR,RES,TIME,STAT")

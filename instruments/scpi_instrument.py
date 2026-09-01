"""SCPI 协议适配器 - 适用于 2400/2450"""
from typing import Optional
from .base import BaseInstrument
from ..core.exceptions import CommandError


class SCPIInstrument(BaseInstrument):
    """SCPI 指令集仪器基类"""

    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 5.0, 
                 model: str = "", logger=None):
        super().__init__(port, baudrate, timeout, model, logger)
        self._source_mode = "voltage"
        self._measure_func = "current"

    def _post_connect(self):
        """连接后清空缓冲区并查询IDN"""
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()
        try:
            idn = self.idn()
            self.logger.info(f"[{self.model}] IDN: {idn}")
        except Exception:
            pass

    def set_source_mode(self, mode: str):
        """设置源模式"""
        mode = mode.lower()
        if mode == "voltage":
            self.write(":SOUR:FUNC VOLT")
            self._source_mode = "voltage"
        elif mode == "current":
            self.write(":SOUR:FUNC CURR")
            self._source_mode = "current"
        else:
            raise ConfigurationError(f"不支持的源模式: {mode}")
        self.logger.debug(f"[{self.model}] 源模式设为 {mode}")

    def set_compliance(self, value: float):
        """设置合规限值"""
        if self._source_mode == "voltage":
            self.write(f":SENS:CURR:PROT {value}")
        else:
            self.write(f":SENS:VOLT:PROT {value}")
        self.logger.debug(f"[{self.model}] 合规限值设为 {value}")

    def set_nplc(self, nplc: float):
        """设置NPLC"""
        if self._measure_func == "current":
            self.write(f":SENS:CURR:NPLC {nplc}")
        elif self._measure_func == "voltage":
            self.write(f":SENS:VOLT:NPLC {nplc}")
        else:
            self.write(f":SENS:CURR:NPLC {nplc}")
        self.logger.debug(f"[{self.model}] NPLC设为 {nplc}")

    def set_output_level(self, level: float):
        """设置输出电平"""
        if self._source_mode == "voltage":
            self.write(f":SOUR:VOLT:LEV {level}")
        else:
            self.write(f":SOUR:CURR:LEV {level}")

    def measure(self) -> dict:
        """执行测量，返回电压、电流、电阻、时间"""
        resp = self.query(":READ?")
        # 2400返回格式: voltage,current,resistance,time,status
        parts = resp.split(",")
        if len(parts) >= 4:
            return {
                "voltage": float(parts[0]),
                "current": float(parts[1]),
                "resistance": float(parts[2]),
                "timestamp": float(parts[3]),
                "status": parts[4] if len(parts) > 4 else ""
            }
        raise CommandError(f"测量返回格式异常: {resp}")

    def output_on(self):
        self.write(":OUTP ON")
        self.logger.debug(f"[{self.model}] 输出开启")

    def output_off(self):
        self.write(":OUTP OFF")
        self.logger.debug(f"[{self.model}] 输出关闭")

    def set_range(self, auto: bool, fixed_value: Optional[float] = None):
        """设置量程"""
        func = "CURR" if self._measure_func == "current" else "VOLT"
        if auto:
            self.write(f":SENS:{func}:RANG:AUTO ON")
        elif fixed_value is not None:
            self.write(f":SENS:{func}:RANG {fixed_value}")
            self.write(f":SENS:{func}:RANG:AUTO OFF")

    def set_measure_function(self, func: str):
        """设置测量功能"""
        func = func.lower()
        if func == "current":
            self.write(":SENS:FUNC \"CURR\"")
            self._measure_func = "current"
        elif func == "voltage":
            self.write(":SENS:FUNC \"VOLT\"")
            self._measure_func = "voltage"
        else:
            raise ConfigurationError(f"不支持的测量功能: {func}")

    def check_errors(self) -> list:
        """检查错误队列"""
        errors = []
        for _ in range(10):  # 最多读10个错误
            resp = self.query(":SYST:ERR?")
            if "+0" in resp or "No error" in resp:
                break
            errors.append(resp)
        return errors

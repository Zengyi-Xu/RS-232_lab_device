"""仪器抽象基类"""
import serial
import time
from abc import ABC, abstractmethod
from typing import Optional, Any
from ..core.exceptions import ConnectionError, CommandError, TimeoutError
from ..core.logger import setup_logger
from ..utils.gpib_transport import GpibTransport


class BaseInstrument(ABC):
    """所有仪器的抽象基类"""

    def __init__(self, port: Optional[str] = None, baudrate: int = 9600, timeout: float = 5.0,
                 model: str = "", logger=None, gpib_address: Optional[int] = None,
                 gpib_board: int = 0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.model = model
        self.gpib_address = gpib_address
        self.gpib_board = gpib_board
        self.ser: Optional[Any] = None
        self.connected = False
        self.logger = logger or setup_logger(f"inst.{model}")
        self._debug = False

    @property
    def use_gpib(self) -> bool:
        """是否使用 GPIB 接口（否则使用串口）"""
        return self.gpib_address is not None

    def connect(self, retries: int = 3) -> bool:
        """连接仪器，支持重试"""
        for attempt in range(1, retries + 1):
            try:
                if self.use_gpib:
                    self.logger.info(
                        f"[{self.model}] 尝试连接 GPIB board={self.gpib_board} "
                        f"address={self.gpib_address} (第{attempt}次)"
                    )
                    self.ser = GpibTransport(
                        address=self.gpib_address,
                        board=self.gpib_board,
                        timeout=self.timeout,
                    )
                    self.ser.open()
                else:
                    self.logger.info(f"[{self.model}] 尝试连接 {self.port} (第{attempt}次)")
                    self.ser = serial.Serial(
                        port=self.port,
                        baudrate=self.baudrate,
                        bytesize=serial.EIGHTBITS,
                        parity=serial.PARITY_NONE,
                        stopbits=serial.STOPBITS_ONE,
                        timeout=self.timeout,
                        xonxoff=False,
                        rtscts=False
                    )
                time.sleep(0.5)  # 等待接口稳定
                self.connected = True
                self._post_connect()
                self.logger.info(f"[{self.model}] 连接成功")
                return True
            except Exception as e:
                self.logger.warning(f"[{self.model}] 连接失败: {e}")
                time.sleep(1)
        raise ConnectionError(f"[{self.model}] 连接失败，已重试{retries}次")

    def disconnect(self):
        """断开连接，安全关闭输出"""
        if self.connected:
            try:
                self._pre_disconnect()
            except Exception as e:
                self.logger.warning(f"[{self.model}] 断开前清理失败: {e}")
            finally:
                if self.ser and self.ser.is_open:
                    self.ser.close()
                self.connected = False
                self.logger.info(f"[{self.model}] 已断开")

    def write(self, cmd: str):
        """发送指令"""
        if not self.connected:
            raise ConnectionError(f"[{self.model}] 未连接")
        full_cmd = cmd + "\n"
        self.ser.write(full_cmd.encode("ascii"))
        if self._debug:
            self.logger.debug(f"[{self.model}] SEND: {cmd}")
        self.ser.flush()

    def read(self, timeout: Optional[float] = None) -> str:
        """读取响应"""
        if not self.connected:
            raise ConnectionError(f"[{self.model}] 未连接")
        old_timeout = self.ser.timeout
        if timeout:
            self.ser.timeout = timeout
        try:
            raw = self.ser.readline()
            resp = raw.decode("ascii", errors="replace").strip()
            if self._debug:
                self.logger.debug(f"[{self.model}] RECV: {resp}")
            return resp
        finally:
            if timeout:
                self.ser.timeout = old_timeout

    def query(self, cmd: str, timeout: Optional[float] = None) -> str:
        """发送指令并读取响应"""
        self.write(cmd)
        time.sleep(0.05)  # 小延迟确保仪器处理
        return self.read(timeout=timeout)

    def reset(self):
        """复位仪器"""
        self.write("*RST")
        time.sleep(0.5)
        self.logger.info(f"[{self.model}] 已复位")

    def check_errors(self) -> list:
        """检查错误队列，返回错误列表"""
        return []

    def idn(self) -> str:
        """查询仪器标识"""
        return self.query("*IDN?")

    # --- 抽象方法：子类必须实现 ---
    @abstractmethod
    def set_source_mode(self, mode: str):
        """设置源模式: voltage 或 current"""
        pass

    @abstractmethod
    def set_compliance(self, value: float):
        """设置合规限值"""
        pass

    @abstractmethod
    def set_nplc(self, nplc: float):
        """设置NPLC"""
        pass

    @abstractmethod
    def set_output_level(self, level: float):
        """设置输出电平"""
        pass

    @abstractmethod
    def measure(self) -> dict:
        """执行测量，返回 {voltage, current, resistance, timestamp}"""
        pass

    @abstractmethod
    def output_on(self):
        """开启输出"""
        pass

    @abstractmethod
    def output_off(self):
        """关闭输出"""
        pass

    @abstractmethod
    def set_range(self, auto: bool, fixed_value: Optional[float] = None):
        """设置量程"""
        pass

    # --- 钩子方法 ---
    def _post_connect(self):
        """连接后的初始化，子类可覆盖"""
        pass

    def _pre_disconnect(self):
        """断开前的清理，子类可覆盖"""
        self.output_off()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False

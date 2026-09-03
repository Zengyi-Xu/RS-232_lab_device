"""GPIB 传输层 - 通过 ctypes 调用 linux-gpib 的 libgpib 库

与 pyserial.Serial 保持兼容接口：write/readline/flush/close/timeout，
使得 BaseInstrument 无需区分底层是串口还是 GPIB。
"""
import ctypes
import ctypes.util


# ibsta 状态位
ERR = 0x8000
TIMO = 0x4000
END = 0x0100

# 超时档位（ibtmo 的 tmo 代码 -> 秒数）
_TIMEOUT_TABLE = [
    (0, None),    # 无超时
    (1, 1e-5),    # 10 us
    (2, 3e-5),    # 30 us
    (3, 1e-4),    # 100 us
    (4, 3e-4),    # 300 us
    (5, 1e-3),    # 1 ms
    (6, 3e-3),    # 3 ms
    (7, 1e-2),    # 10 ms
    (8, 3e-2),    # 30 ms
    (9, 1e-1),    # 100 ms
    (10, 3e-1),   # 300 ms
    (11, 1.0),    # 1 s
    (12, 3.0),    # 3 s
    (13, 10.0),   # 10 s
    (14, 30.0),   # 30 s
    (15, 100.0),  # 100 s
    (16, 300.0),  # 300 s
    (17, 1000.0), # 1000 s
]


def _load_lib():
    for name in ("libgpib.so.0", "libgpib.so", ctypes.util.find_library("gpib")):
        if not name:
            continue
        try:
            return ctypes.CDLL(name)
        except OSError:
            continue
    raise OSError("找不到 libgpib 库，请先安装 linux-gpib 用户态库")


class GpibTransport:
    """GPIB 设备传输层，接口对齐 pyserial.Serial 的常用子集"""

    def __init__(self, address: int, board: int = 0, timeout: float = 5.0):
        self.address = address
        self.board = board
        self._timeout = timeout
        self._lib = _load_lib()
        self._lib.ibdev.restype = ctypes.c_int
        self._lib.ibdev.argtypes = [ctypes.c_int] * 6
        self._lib.ibwrt.restype = ctypes.c_int
        self._lib.ibwrt.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_long]
        self._lib.ibrd.restype = ctypes.c_int
        self._lib.ibrd.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_long]
        self._lib.ibtmo.restype = ctypes.c_int
        self._lib.ibtmo.argtypes = [ctypes.c_int, ctypes.c_int]
        self._lib.ibonl.restype = ctypes.c_int
        self._lib.ibonl.argtypes = [ctypes.c_int, ctypes.c_int]
        self._lib.ibcnt = ctypes.c_int.in_dll(self._lib, "ibcnt")
        self._lib.ibsta = ctypes.c_int.in_dll(self._lib, "ibsta")
        self._ud = -1
        self._readbuf = ctypes.create_string_buffer(65536)

    @property
    def is_open(self) -> bool:
        return self._ud >= 0

    @property
    def timeout(self) -> float:
        return self._timeout

    @timeout.setter
    def timeout(self, value: float):
        self._timeout = value
        if self.is_open:
            self._lib.ibtmo(self._ud, self._timeout_to_code(value))

    @staticmethod
    def _timeout_to_code(seconds):
        """将秒数映射到最近的超时档位代码"""
        best, best_diff = 13, float("inf")
        for code, t in _TIMEOUT_TABLE:
            if t is None:
                continue
            diff = abs(t - seconds)
            if diff < best_diff:
                best, best_diff = code, diff
        return best

    def open(self):
        """打开设备（ibdev 内部会自动完成连接）"""
        if self.is_open:
            return
        tmo = self._timeout_to_code(self._timeout)
        # ibdev(board, pad, sad, tmo, eot, eos)
        self._ud = self._lib.ibdev(self.board, self.address, 0, tmo, 1, 0)
        if self._ud < 0 or (self._lib.ibsta.value & ERR):
            self._ud = -1
            raise OSError(
                f"无法打开 GPIB 设备: board={self.board}, address={self.address}。"
                f"请检查 /dev/gpib{self.board} 是否存在、驱动是否加载、"
                f"以及仪器的 GPIB 地址 {self.address} 是否正确"
            )

    def write(self, data: bytes) -> int:
        """写入数据（自动附带 EOI）"""
        if not self.is_open:
            raise OSError("GPIB 设备未打开")
        self._lib.ibwrt(self._ud, data, len(data))
        if self._lib.ibsta.value & ERR:
            if self._lib.ibsta.value & TIMO:
                raise TimeoutError("GPIB 写入超时")
            raise OSError(f"GPIB 写入失败 (ibsta=0x{self._lib.ibsta.value:04x})")
        return self._lib.ibcnt.value

    def readline(self) -> bytes:
        """读取一行（以 \\n 或 EOI 结束），超时时返回已收到的数据"""
        chunks = []
        while True:
            self._lib.ibrd(self._ud, self._readbuf, len(self._readbuf))
            cnt = self._lib.ibcnt.value
            sta = self._lib.ibsta.value
            if cnt > 0:
                data = self._readbuf.raw[:cnt]
                chunks.append(data)
                if b"\n" in data:
                    break
            if sta & END or sta & (TIMO | ERR) or cnt == 0:
                break
        return b"".join(chunks)

    def flush(self):
        pass  # GPIB 无需 flush

    def reset_input_buffer(self):
        pass  # 接口兼容占位

    def reset_output_buffer(self):
        pass  # 接口兼容占位

    def close(self):
        """关闭设备并下线"""
        if self.is_open:
            self._lib.ibonl(self._ud, 0)
            self._ud = -1

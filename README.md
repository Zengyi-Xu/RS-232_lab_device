# IVLab — 多仪器自动化测试框架

基于 Python + RS-232/USB/GPIB 的多仪器控制框架，支持 Keithley 2400/2450/2600B 源表的 IV 曲线实时扫描、回滞分析、多次平均降噪（2400 支持 RS-232 与 GPIB/NI488），以及 Cornerstone 260 单色仪的 USB/RS-232 通信与波长扫描，并预留 Newport 2359-R 光功率计扩展接口。

---

## 功能特性

| 功能 | 状态 | 说明 |
|------|------|------|
| **Keithley 2400** | ✅ 完整 | SCPI 指令集，支持 RS-232 与 GPIB/NI488 |
| **Keithley 2450** | ✅ 完整 | 自动切换至 2400 SCPI 兼容模式 |
| **Keithley 2600B** | ✅ 完整 | TSP/Lua 脚本模式（`smua`/`smub`） |
| **双向扫描** | ✅ 完整 | 正向 + 反向，形成闭合 I-V 环 |
| **往返扫描** | ✅ 完整 | 0 → Vmax → 0 → -Vmax → 0 |
| **多次平均** | ✅ 完整 | N 次重复扫描，支持方向随机化 |
| **回滞分析** | ✅ 完整 | 回滞面积、回滞指数、最大 ΔI、对称因子 |
| **实时绘图** | ✅ 完整 | matplotlib 动态 I-V 曲线 + ΔI 分析图 |
| **CSV 保存** | ✅ 完整 | 含元数据头，Excel 可直接打开 |
| **多仪器协调** | ✅ 完整 | 扫描序列定义，支持并行读取 |
| **CS260 USB** | ✅ 完整 | Newport 官方 DLL 桥接（32 位 PowerShell 子进程） |
| **CS260 RS-232** | ✅ 完整 | ASCII 指令集（`WAVE`/`SHUTTER`/`GRAT`），轮询到位判定 |
| **波长扫描** | ✅ 完整 | 单向/往返波长扫描，可同步读光功率计，CSV 保存 |
| **2359-R 预留** | 📝 接口 | 协议待填入 `optical_power_meter.py` |

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

依赖：`pyserial`, `pyvisa`, `numpy`, `matplotlib`, `pandas`

### 2. 基础 IV 扫描

```bash
python examples/basic_iv_scan.py              # RS-232
python examples/basic_iv_scan.py --gpib 22    # GPIB 地址 22
```

程序会自动扫描可用 COM 端口（RS-232 模式），交互式选择后执行单向电压扫描；加 `--gpib` 则通过 GPIB/NI488 控制。

### 3. 回滞扫描与分析

```bash
python examples/hysteresis_scan.py
```

执行双向扫描（正向 + 反向），自动计算回滞面积、回滞指数，并生成对比图。

### 4. 波长扫描（Cornerstone 260）

```bash
python examples/wavelength_scan.py --start 400 --stop 410 --step 2
```

自动连接 USB 接口的 CS260（或加 `--port COMx` 使用 RS-232），执行波长扫描并保存 CSV。

### 5. 多仪器协调（演示）

```bash
python examples/multi_device_demo.py
```

展示如何定义多仪器扫描序列（单色仪 → 源表 → 光功率计）。

---

## 项目结构

```
RS-232_lab_device-main/          # 项目根目录
├── ivlab/                       # Python 包
│   ├── core/                    # 核心基础设施
│   │   ├── exceptions.py        # 自定义异常类
│   │   ├── config.py            # ScanConfig / InstrumentConfig
│   │   └── logger.py            # 统一日志（控制台 + 文件）
│   ├── instruments/             # 仪器驱动层（只负责单点控制与查询）
│   │   ├── base.py              # BaseInstrument 抽象基类（RS-232）
│   │   ├── scpi_mixin.py        # SCPI 指令集 Mixin
│   │   ├── scpi_instrument.py   # SCPI 协议适配器（RS-232）
│   │   ├── gpib_instrument.py   # GPIB 协议适配器（pyvisa）
│   │   ├── tsp_instrument.py    # TSP/Lua 协议适配器
│   │   ├── keithley2400.py      # 2400 RS-232 实现
│   │   ├── keithley2400_gpib.py # 2400 GPIB/NI488 实现
│   │   ├── keithley2450.py      # 2450 兼容模式
│   │   ├── keithley2600.py      # 2600B TSP 模式
│   │   ├── optical_power_meter.py  # 2359-R 预留
│   │   ├── monochromator.py     # CS260 RS-232 ASCII 协议
│   │   ├── cornerstone260.py    # CS260 USB（Newport DLL 桥接）
│   │   ├── usbtmc_instrument.py # USB-TMC 通用基类（pyvisa + VISA USB 驱动）
│   │   ├── sva1032x.py          # Siglent SVA1000X 频谱仪驱动
│   │   └── _cornerstone_bridge.ps1  # 32 位 PowerShell 通信桥
│   ├── scanner/                 # 扫描与分析引擎（上层编排逻辑）
│   │   ├── iv_scanner.py        # IV 扫描引擎
│   │   ├── wavelength_scanner.py# 波长扫描引擎
│   │   ├── hysteresis.py        # 回滞分析器
│   │   ├── multi_instrument.py  # 多仪器协调器
│   │   └── data_handler.py      # CSV / JSON 数据保存
│   └── utils/
│       └── port_scanner.py      # COM 口自动扫描
├── examples/                    # 示例脚本（可直接运行）
│   ├── basic_iv_scan.py         # 基础扫描示例
│   ├── hysteresis_scan.py       # 回滞分析示例
│   ├── wavelength_scan.py       # CS260 波长扫描示例
│   ├── multi_device_demo.py     # 多仪器协调示例
│   └── sva1032x_demo.py         # SVA1032X 频谱仪示例
├── README.md
├── CHANGELOG.md
└── requirements.txt
```

层次约定：`instruments` 驱动层只提供单点移动/查询；扫描序列等编排逻辑
统一放在 `scanner` 层，避免下层模块反向依赖上层。

---

## 核心类说明

### BaseInstrument（抽象基类）

所有仪器的统一接口：

```python
inst.connect()          # 连接（支持重试）
inst.disconnect()       # 断开（自动关闭输出）
inst.write(cmd)         # 发送指令
inst.read()             # 读取响应
inst.query(cmd)         # 发送并读取
inst.reset()            # 仪器复位
inst.idn()              # 查询型号

# 子类必须实现：
inst.set_source_mode("voltage")   # 或 "current"；切换后自动测量互补物理量：
                                  #   电压源测电流、电流源测电压（:SENS:FUNC 自动下发），
                                  #   set_measure_function 不允许设成与源模式相同的物理量
inst.set_compliance(0.1)          # 限值（对端物理量：电压源限电流、电流源限电压）
inst.set_nplc(1.0)                # 积分时间
inst.set_output_level(1.0)        # 设置输出
inst.measure()                    # 返回 {voltage, current, resistance, timestamp}
inst.output_on() / output_off()   # 输出开关
inst.set_range(auto=True)         # 量程设置
```

### IVScanner（扫描引擎）

```python
from ivlab.core.config import ScanConfig
from ivlab.scanner.iv_scanner import IVScanner

config = ScanConfig(
    start_v=0.0, stop_v=2.0, points=101,
    nplc=1.0, compliance_i=0.1,
    scan_type="double",      # single / double / sweep
    n_average=3,             # 平均次数
    randomize_direction=True # 随机化方向
)

scanner = IVScanner(instrument, config)
results = scanner.run()      # 执行扫描
avg = scanner.get_averaged_result()  # 获取平均结果
```

### HysteresisAnalyzer（回滞分析）

```python
from ivlab.scanner.hysteresis import HysteresisAnalyzer

analyzer = HysteresisAnalyzer()
h = analyzer.analyze(forward_result, backward_result)

print(f"回滞面积: {h.hysteresis_area:.3e}")
print(f"回滞指数: {h.hysteresis_index:.4f}")
print(f"最大 ΔI:  {h.delta_i_max:.3e} A")
```

### Cornerstone260（单色仪 USB 接口）与波长扫描

CS260 的 USB 版不是虚拟串口，需通过 Newport 官方 `Cornerstone.dll` 通信。
该 DLL 是 .NET 2.0 程序集，在 64 位进程下枚举设备会触发 `IntPtr` 溢出，
因此驱动内部启动一个 32 位 Windows PowerShell 子进程加载 DLL
（`_cornerstone_bridge.ps1`），主进程通过 JSON 行协议与其通信。
前提：已安装 Newport Mono Utility（含 Cypress USB 驱动），DLL 默认搜索
`C:\Program Files (x86)\Newport\Mono Utility 5.0.4\Cornerstone DLL\`。

```python
from ivlab.instruments.cornerstone260 import Cornerstone260
from ivlab.scanner.wavelength_scanner import WavelengthScanner, WavelengthScanConfig
from ivlab.scanner.data_handler import DataHandler

mono = Cornerstone260()          # 或 Cornerstone260(dll_path=r"...")
mono.connect()
print(mono.idn())                # Cornerstone 260, SN1003, V04.40
print(mono.get_wavelength())     # 当前波长 (nm)

config = WavelengthScanConfig(
    start_nm=400.0, stop_nm=700.0, step_nm=1.0,
    scan_type="double",           # 往返扫描
)
scanner = WavelengthScanner(mono, config)   # 可传 power_meter= 同步读功率
results = scanner.run()

handler = DataHandler(output_dir="./data")
handler.save_wavelength_scan(results)
mono.disconnect()
```

RS-232 接口的 CS260 直接使用 `ivlab.instruments.monochromator.Monochromator(port="COMx")`，
ASCII 指令以 `\r` 终止，`goto_wavelength()` 轮询 `WAVE?` 判定到位。

### MultiInstrumentCoordinator（多仪器协调）

```python
from ivlab.scanner.multi_instrument import MultiInstrumentCoordinator, ScanStep

coord = MultiInstrumentCoordinator()
coord.add_instrument("source", keithley2400)
coord.add_instrument("mono", monochromator)
coord.add_instrument("power", power_meter)

sequence = [
    ScanStep("mono", "set_wavelength", {"wavelength": 500}, wait_after=1.0),
    ScanStep("source", "set_voltage", {"voltage": 1.0}, wait_after=0.5),
    ScanStep("power", "read_power", {"read_all": True}),
]

coord.connect_all()
data = coord.run_sequence(sequence)
coord.disconnect_all()
```

---

## GPIB / NI488 使用说明

Keithley 2400 除 RS-232 外，也支持通过 GPIB（IEEE-488）控制。

### 前提

1. 安装 VISA 后端（任选其一）：
   - **NI-VISA**：National Instruments 官方驱动，配合 NI GPIB-USB-HS 卡
   - **Keysight VISA**：配合 Keysight 82357B 等 GPIB-USB 适配器
   - **pyvisa-py**：纯 Python 后端，无需安装大体积驱动（功能有限）

2. 确认 pyvisa 能识别到仪器：

```python
import pyvisa
rm = pyvisa.ResourceManager()
print(rm.list_resources())
# 应输出类似：('GPIB0::22::INSTR',)
```

### 代码示例

```python
from ivlab.instruments.keithley2400_gpib import Keithley2400GPIB

inst = Keithley2400GPIB(gpib_addr=22)
inst.connect()
print(inst.idn())
inst.output_on()
print(inst.measure())
inst.disconnect()
```

### 命令行示例

```bash
python examples/basic_iv_scan.py --gpib 22
```

---

## 扩展新仪器

以 Newport 2359-R 为例，只需在预留接口中补全协议：

```python
# ivlab/instruments/optical_power_meter.py

def measure(self) -> dict:
    self.write("READ?")  # 替换为实际指令
    resp = self.read()
    return {
        "power": float(resp),
        "unit": "dBm",
        "timestamp": time.time()
    }
```

扫描引擎和协调器会自动识别，**无需修改上层代码**。

---

## 仪器通信协议速查

### Keithley 2400 / 2450（SCPI）

```
*RST                    # 复位
:SOUR:FUNC VOLT        # 电压源
:SENS:FUNC "CURR"      # 测电流
:SENS:CURR:PROT 0.1    # 电流合规 100mA
:SENS:CURR:NPLC 1      # NPLC
:OUTP ON               # 开启输出
:READ?                 # 读取 V,I,R,time
:OUTP OFF              # 关闭输出
```

### Keithley 2600B（TSP / Lua）

```lua
reset()
smua.source.func = smua.OUTPUT_DCVOLTS
smua.source.levelv = 1.0
smua.source.limiti = 0.1
smua.measure.nplc = 1
smua.source.output = smua.OUTPUT_ON
print(smua.measure.v())   -- 电压
print(smua.measure.i())   -- 电流
smua.source.output = smua.OUTPUT_OFF
```

### Cornerstone 260（ASCII）

```
WAVE 500.0     # 设置波长 500nm
WAVE?          # 查询波长
SHUTTER O      # 打开快门
SHUTTER C      # 关闭快门
GRAT 2         # 切换到 2 号光栅
FILTER 3       # 切换到 3 号滤光片
```

USB 接口经 Newport DLL 调用同一 ASCII 指令集（`sendCommand`/`getResponse`）。

---

## 调试与日志

- 所有 SCPI/TSP 指令和仪器响应自动记录到 `logs/ivlab.log`
- 开启原始通信打印：`inst._debug = True`
- Ctrl+C 安全退出：自动关闭输出、切回本地、保存已采数据
- 溢出检测：自动识别 `9.91E37` 并标记为 `NaN`

---

## 数据格式

### CSV 文件结构

```csv
# IV Scan Result
# Direction,forward
# nplc,1.0
# compliance,0.1

Voltage(V),Current(A),Resistance(Ohm),Time(s)
0.000000e+00,1.234567e-06,8.100000e+05,0.000000
0.020000e+00,2.345678e-06,4.200000e+05,0.050000
...
```

### 回滞分析 CSV

```csv
# Hysteresis Analysis
# Hysteresis Area,1.234e-08
# Hysteresis Index,0.0234

Voltage(V),Forward_I(A),Backward_I(A),Delta_I(A)
```

---

## 作者

**zengyi-xu** — 集成光子器件与光计算系统研究

---

## License

MIT

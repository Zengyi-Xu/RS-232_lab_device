# IVLab — 多仪器自动化测试框架

基于 Python + RS-232/USB 串口的多仪器控制框架，支持 Keithley 2400/2450/2600B 源表的 IV 曲线实时扫描、回滞分析、多次平均降噪，并预留 Newport 2359-R 光功率计与 Cornerstone 260 单色仪扩展接口。

---

## 功能特性

| 功能 | 状态 | 说明 |
|------|------|------|
| **Keithley 2400** | ✅ 完整 | SCPI 指令集，标准 RS-232 控制 |
| **Keithley 2450** | ✅ 完整 | 自动切换至 2400 SCPI 兼容模式 |
| **Keithley 2600B** | ✅ 完整 | TSP/Lua 脚本模式（`smua`/`smub`） |
| **双向扫描** | ✅ 完整 | 正向 + 反向，形成闭合 I-V 环 |
| **往返扫描** | ✅ 完整 | 0 → Vmax → 0 → -Vmax → 0 |
| **多次平均** | ✅ 完整 | N 次重复扫描，支持方向随机化 |
| **回滞分析** | ✅ 完整 | 回滞面积、回滞指数、最大 ΔI、对称因子 |
| **实时绘图** | ✅ 完整 | matplotlib 动态 I-V 曲线 + ΔI 分析图 |
| **CSV 保存** | ✅ 完整 | 含元数据头，Excel 可直接打开 |
| **多仪器协调** | ✅ 完整 | 扫描序列定义，支持并行读取 |
| **2359-R 预留** | 📝 接口 | 协议待填入 `optical_power_meter.py` |
| **CS260 预留** | 📝 接口 | 协议待填入 `monochromator.py` |

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

依赖：`pyserial`, `numpy`, `matplotlib`, `pandas`

### 2. 基础 IV 扫描

```bash
cd examples
python basic_iv_scan.py
```

程序会自动扫描可用 COM 端口，交互式选择后执行单向电压扫描。

### 3. 回滞扫描与分析

```bash
python hysteresis_scan.py
```

执行双向扫描（正向 + 反向），自动计算回滞面积、回滞指数，并生成对比图。

### 4. 多仪器协调（演示）

```bash
python multi_device_demo.py
```

展示如何定义多仪器扫描序列（单色仪 → 源表 → 光功率计）。

---

## 项目结构

```
ivlab/
├── core/                       # 核心基础设施
│   ├── exceptions.py           # 自定义异常类
│   ├── config.py               # ScanConfig / InstrumentConfig
│   └── logger.py               # 统一日志（控制台 + 文件）
├── instruments/                # 仪器驱动层
│   ├── base.py                 # BaseInstrument 抽象基类
│   ├── scpi_instrument.py      # SCPI 协议适配器
│   ├── tsp_instrument.py       # TSP/Lua 协议适配器
│   ├── keithley2400.py         # 2400 实现
│   ├── keithley2450.py         # 2450 兼容模式
│   ├── keithley2600.py         # 2600B TSP 模式
│   ├── optical_power_meter.py  # 2359-R 预留
│   └── monochromator.py        # Cornerstone 260 预留
├── scanner/                    # 扫描与分析引擎
│   ├── iv_scanner.py           # IV 扫描引擎
│   ├── hysteresis.py           # 回滞分析器
│   ├── multi_instrument.py     # 多仪器协调器
│   └── data_handler.py         # CSV / JSON 数据保存
├── utils/
│   └── port_scanner.py         # COM 口自动扫描
└── examples/
    ├── basic_iv_scan.py        # 基础扫描示例
    ├── hysteresis_scan.py      # 回滞分析示例
    └── multi_device_demo.py    # 多仪器协调示例
```

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
inst.set_source_mode("voltage")   # 或 "current"
inst.set_compliance(0.1)          # 限值
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
```

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

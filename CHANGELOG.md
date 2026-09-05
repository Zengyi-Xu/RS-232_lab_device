# 更新日志

## 2026-09-05

### 新增

- **Siglent SVA1032X 频谱仪支持**：新增 `ivlab/instruments/usbtmc_instrument.py`（USB-TMC 通用基类，基于 pyvisa + NI-VISA/Keysight VISA，支持按 VID 自动发现资源）与 `ivlab/instruments/sva1032x.py`（SVA1000X 系列驱动），并附示例 `examples/sva1032x_demo.py`。这类仪器的 USB-B Device 口不是虚拟串口，必须经 VISA 的 USB 驱动访问（资源名形如 `USB0::0xF4EC::0x1032::INSTR`）。

### 修复

- **Keithley 2400 串口无响应**：串口连接时显式拉高 RTS/DTR 握手线，否则仪器不发送任何数据。
- **query() 误读命令回显**：Keithley 2400 的 RS-232 口会回显命令，`query()` 现在自动跳过回显行，避免把回显当作响应解析。

### 改进

- **源模式与测量功能互补**：`set_source_mode` 切换源模式时，自动把测量功能设为互补端并下发 `:SENS:FUNC`（电压源测电流、电流源测电压），同时修正 `_measure_func`，保证 `set_nplc` / `set_range` 作用于正确的物理量。串口（SCPIInstrument）与 GPIB（GPIBSCPIInstrument）两个后端同时生效。
- **互斥校验**：`set_measure_function` 现在拒绝设置与源模式相同的测量功能，并给出明确中文提示。
- **IVScanner 自动推导测量功能**：`setup_instrument` 按 `source_mode` 自动选择互补测量功能，`ScanConfig.measure_func` 字段不再被扫描器使用（保留在配置中不影响兼容）。

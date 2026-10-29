# cddtools

[English](README.md)

`cddtools` 是一个独立的 Python 工具库，用于解析 `.cdd` 诊断文件并导出
JSON。可以作为库导入、通过命令行导出，也提供一个图形界面预览一些信息。

## 用途说明

本项目只做**读取**：

- **学习** — 理解 `.cdd` 数据模型的组织方式。
- **预览** — 不打开完整编辑器就能查一个 DID、一条 DTC 或某个服务的报文布局。
- **给 AI 工具喂数据** — 把 `.cdd` 转成 LLM 或脚本能读的 JSON，开发过程中快速回答
  关于某个 ECU 诊断内容的问题，加速开发。

### 安装

```bash
pip install -e .
```

## 已实现

| CDD 内容 | 模块 | 说明 |
|---|---|---|
| 数据类型（`DATATYPES`） | `cdd_datatypes_parser` | CANdelaStudio 提供的全部 13 种转换（Raw value、Text Table、Linear、Piecewise Linear、Characteristic Curve、Formula、Procedural Conversion、Packet、Mux 及四种迭代类型）；位域成员、无效值、对象属性 |
| DID（`DIDS`） | `cdd_did_parser` | 标识符、各 variant 是否存在、DID 数据摘要、是否被使用 |
| 故障码（`RECORDDTPOOL`） | `cdd_dtc_parser` | SAE J2012 编码解析（P/C/B/U + 失效类型字节）、模板驱动的属性（Priority、Lamp Flag、Monitor type…）|
| DTC 状态字节（`DTCSTATUSMASK`） | `cdd_dtc_parser.parse_status_mask()` | ISO 14229-1 的 8 个位，含每位是否被 ECU 实现，以及合成的支持掩码 |
| 诊断类（`DCLTMPLS` + 各 variant） | `cdd_diagnostic_classes_parser` | 文档定义的全部诊断类，以及各 variant 勾选了哪些 |
| 诊断实例与服务（`DIAGINST`） | `cdd_services_parser` | Request / Pos. Resp. / Neg. Resp. 报文格式、带字节位与位偏移的电报表格、负响应码 |
| 属性与接口（`DEFATTS`） | `cdd_attributes_parser` | 文档定义的全部接口及其通信参数，各自标明 ECU 是否支持 |
| 状态组（`STATEGROUPS`） | `cdd_states_parser` | 会话与安全访问状态组 |
| *（派生，非 CDD 内容）* | `cdd_tester` | CAN 地址、ISO-TP 参数、UDS 时序、按服务 ID 索引的服务表，以及展开后的电报参数（encoding / factor / offset / unit / choices / 位域组 / startBit / 可直接发送的字节缓冲）|

数据类型和 DTC 记录自身携带的属性值，由它们各自的解析器一并报出。

## 未实现

| CDD 内容 | 状态 |
|---|---|
| 协议服务的独立列表 | 解析服务时已用到，但没做成独立列表 |
| 负响应的独立列表 | 同上，目前只挂在负响应报文里 |
| 快照记录（Snapshot Records） | 未解析 |
| 扩展数据记录（Extended Data Records） | 未解析 |
| 车辆系统组（Vehicle System Groups） | 未解析 |
| 需求项（Requirements） | 未解析 |
| 识别特征 / 识别模式 | 未解析 |
| 库 / 导入池 | 未解析 |
| 各接口分别支持哪些服务 | 未解析 |
| ODX `ECUSHAREDDATA` | 未解析 |
| 诊断类模板本身 | 仅用于解析类与服务的引用 |

已实现部分内部的已知缺口：

- DoIP 接口能识别、时序能取到，但没有生成对应的地址结构——样本文档里 DoIP 接口
  未启用，无从验证。
- 电报里显示的 payload 占位符（`zz`、`yy`）是显示时生成的，文件里并不存在，因此
  统一输出为 `..`。

## 命令行

```bash
cddtools parse input.cdd output.json      # 写入 JSON 文件
python -m cddtools parseDtcs input.cdd    # 输出到 stdout
```

两种拼写都接受（`parseDtcs` 或 `parse-dtcs`）：

| 命令 | 输出 |
|---|---|
| `parse`、`parseTesterInfo` | 面向连接的完整结构 |
| `parseDatatypes` | 数据类型 |
| `parseDids` | DID |
| `parseDtcs` | DTC |
| `parseDtcStatusMask` | DTC 状态字节 |
| `parseDiagnosticClasses` | 诊断类 |
| `parseServices` | 诊断实例与电报 |
| `parseSnapshot` | 按 variant 分组的稳定 DID/DTC 定义，展开关联数据类型 |
| `parseStates` | 状态组 |
| `parseInterfaces` | 全部接口，各带 `enabled` 标记 |
| `parseSupportedInterfaces` | 仅 ECU 支持的接口 |
| `parseAttributes` | 全部属性定义及其生效值 |

## Python API

所有入口返回同一种信封：

```python
{"error": 0, "data": ...}          # 成功
{"error": 1, "message": "..."}     # 失败
```

```python
import cddtools

cddtools.parse_dtcs("ECU.cdd")
cddtools.parse_interfaces("ECU.cdd")
cddtools.parse_tester_info("ECU.cdd")
cddtools.parse_snapshot("ECU.cdd")
```

`parse_snapshot` 提供用于文件或 variant 比较的只读数据：展开 DID 类型引用，
保留固定及可变位长，移除文档内部 ID，并按各 variant 的引用筛选 DID/DTC。
这些是诊断定义，不表示 ECU 当前故障状态。此入口不要求存在受支持的总线接口；
无法解析的长度保留为 `None`，不会视为零。

对同一个文档跑多个解析器时，只加载一次：

```python
from cddtools import load_ecu_doc
from cddtools.cdd_did_parser import CddDidParser
from cddtools.cdd_dtc_parser import CddDtcParser

shared, ecu_doc = load_ecu_doc("ECU.cdd")
dids = CddDidParser(shared).parse(ecu_doc)
dtcs = CddDtcParser(shared).parse(ecu_doc)
```

## 图形界面

```bash
python -m cddtools.cdd_viewer
```

只读查看器，每个面板一个 tab（Interfaces、Diagnostic Classes、Supported Services、
Data Types、DIDs、DTCs、DTC Status、States）。每个 tab 有自己的
“Export … as JSON” 按钮。

## 示例与测试

`examples/parse_*_example.py` 可以从命令行单独跑各个解析器。

`examples/CddTools.cdd` 是全部测试和文档的基准文件：一份由模板派生、不含任何客户
项目数据的文档，随仓库提交，所以全新 clone 下来就能跑测试：

```bash
python -m unittest discover -s tests
```

`.gitignore` 会挡住其余所有 `.cdd`、它们的导出文件，以及任何由它们导出的
JSON——把机密文档放进 `examples/` 也不会被误提交。

## 文档

| | |
|---|---|
| [docs/usage.md](docs/usage.md) | 怎么跑：命令行、Python API、图形界面、示例脚本、测试 |
| [docs/cdd-format.md](docs/cdd-format.md) | `.cdd` 数据模型、公共工具，以及各解析器共通的陷阱 |
| [docs/parsers.md](docs/parsers.md) | 各面板解析器读哪些字段、跟哪些引用链、输出什么形状 |
| [docs/tester.md](docs/tester.md) | 派生层 `cdd_tester` |
| [docs/viewer.md](docs/viewer.md) | 只读图形界面 |

## 声明

- **输出仅供参考**。


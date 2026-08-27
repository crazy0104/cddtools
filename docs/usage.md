# 怎么跑

命令与 API 的完整清单在 [../README.zh.md](../README.zh.md)，本文是上手用法。
下面所有命令都以随仓库提交的 `examples/CddTools.cdd` 为例，不用另外准备文件。

## 安装

```bash
pip install -e .
```

## 命令行

```bash
# 面向连接的完整视图：地址、时序、DID、DTC、服务
python -m cddtools parse examples/CddTools.cdd

# 一次一块内容
python -m cddtools parseDids examples/CddTools.cdd
python -m cddtools parseDtcs examples/CddTools.cdd
python -m cddtools parseInterfaces examples/CddTools.cdd

# 写文件而不是打到 stdout
cddtools parse examples/CddTools.cdd output.json
```

两种拼写都接受（`parseDtcs` 或 `parse-dtcs`），全部子命令见 README。

## Python API

顶层入口返回统一信封，成功 `error=0`，失败 `error=1` 并带 `message`：

```python
from cddtools import parse, parse_dids, parse_dtcs

result = parse("examples/CddTools.cdd")
dids = parse_dids("examples/CddTools.cdd")
```

### 对同一份文档跑多个解析器

**别对每个解析器重新解析一遍 XML**。`load_ecu_doc()` 把「解析 XML → 定位 `ECUDOC`
→ 建 id 索引」打包成一步，把 `shared` 传给各解析器即可（id 索引是各种 `@*ref` 反查
的前提，见 [cdd-format.md §3](cdd-format.md#3-引用怎么解)）：

```python
from cddtools import load_ecu_doc
from cddtools.cdd_datatypes_parser import CddDataTypesParser
from cddtools.cdd_did_parser import CddDidParser
from cddtools.cdd_dtc_parser import CddDtcParser

shared, ecu_doc = load_ecu_doc("examples/CddTools.cdd")

datatypes = CddDataTypesParser(shared).parse(ecu_doc)
dids = CddDidParser(shared).parse(ecu_doc)
dtcs = CddDtcParser(shared).parse(ecu_doc)
```

七个解析器的构造和调用形式完全一致（`Parser(shared).parse(ecu_doc)`），返回
`list[dict]`。各自的输出字段见 [parsers.md](parsers.md)。

### 常用套路

```python
from cddtools import load_ecu_doc
from cddtools.cdd_datatypes_parser import CddDataTypesParser
from cddtools.cdd_did_parser import CddDidParser
from cddtools.cdd_attributes_parser import CddAttributesParser

shared, ecu_doc = load_ecu_doc("examples/CddTools.cdd")

# 按 qual 建索引取单条
by_qual = {e["qual"]: e for e in CddDataTypesParser(shared).parse(ecu_doc)}
print(by_qual["P2Ex"]["conversion"])                # "Linear"

# 按 DID 号取
dids = CddDidParser(shared).parse(ecu_doc)
by_did = {e["identifierHex"]: e for e in dids}
print(by_did["0x0100"]["dataSummary"])

# 「定义了但没被任何服务用到」的 DID
print([e["identifierHex"] for e in dids if not e["used"]])   # ['0xFF00', '0xFF01']

# 这个 ECU 实际支持的接口（不是模板提供的全部）
active = CddAttributesParser(shared).active_interface(ecu_doc)
print(active["name"])                               # "CAN"
```

各解析器的排序：数据类型按名字、DID 按 identifier 升序、DTC 按显示码、诊断类保持
文档顺序。

## 示例脚本

`examples/parse_*_example.py` 从命令行直接驱动各解析器并打印成表，是最快看清输出
形状的方式。都支持不带参数直接跑（默认 `examples/CddTools.cdd`），也都支持
`--json out.json` 导出：

```bash
python examples/parse_datatypes_example.py                        # Conversion 分布 + 每种一个样例
python examples/parse_datatypes_example.py --qual Memory_Address_and_Size   # 单条详情（Mux）

python examples/parse_did_example.py                              # DID 一览表
python examples/parse_did_example.py --qual Boot_Software

python examples/parse_dtc_example.py                              # DTC 简表
python examples/parse_dtc_example.py --dtc P0100

python examples/parse_diagnostic_classes_example.py               # 带勾选标记的完整列表
python examples/parse_diagnostic_classes_example.py --enabled-only

python examples/parse_services_example.py                         # 一行一个实例的总表
python examples/parse_services_example.py --class Sessions        # 某个类，带电报表格
python examples/parse_services_example.py --qual DefaultSession   # 单个实例完整 JSON

python examples/parse_attributes_example.py                       # 接口 + 时序 + 地址
python examples/parse_attributes_example.py --all                 # 全部属性按分类列出
python examples/parse_attributes_example.py --category Timing
```

`--qual` / `--class` / `--dtc` 传错了会提示没匹配上，并列出可选值。

## 图形界面

```bash
python -m cddtools.cdd_viewer
```

只读窗口，每块内容一个 tab，每个 tab 能单独导出 JSON。界面细节见
[viewer.md](viewer.md)。

## 测试

```bash
python -m unittest discover -s tests -p "test_*.py"
```

全部用例都跑在 `examples/CddTools.cdd` 上，全新 clone 即可通过。

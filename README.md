# cddtools

[English](README.en.md)

`cddtools` 是一个独立的 Python 工具库，用于解析 CANdela `.cdd` 诊断文件，并导出
JSON 数据。它可以作为库导入，也可以通过命令行输出 JSON 文件。

### 功能

- 解析 `.cdd` 文件并输出 JSON。
- 解析 ECU、Variant、UDS 服务列表、请求参数和响应参数。
- 解析 CAN 地址配置、UDS timing、DID、DTC、CDD 数据类型、枚举、文本表、长度、
  字节序、单位、factor/offset 等信息。
- 支持在完整 JSON 中单独输出 `didList` 和 `dtcList`。
- 支持单独导出 DID 列表或 DTC 列表。
- 支持命令行输出到 stdout 或写入指定 JSON 文件。
- 支持 Python API：`parse_tester_info()`、`parse()`、`parse_dids()`、
  `parse_dtcs()`、`load_file()`。

### 安装

```bash
pip install -e .
```

### 命令行

写入 JSON 文件：

```bash
cddtools parse input.cdd output.json --parseResp
```

输出到 stdout：

```bash
python -m cddtools parse input.cdd
```

支持的命令：

- `parse`
- `parseTesterInfo`
- `parse-tester-info`
- `parseDids`
- `parse-dids`
- `parseDtcs`
- `parse-dtcs`

目前 `parse` 和 `parseTesterInfo` 返回相同的 JSON 结构。

单独导出 DID 或 DTC：

```bash
python -m cddtools parseDids input.cdd
python -m cddtools parseDtcs input.cdd
```

### Python API

```python
from cddtools import parse, parse_dids, parse_dtcs, parse_tester_info

result = parse_tester_info("input.cdd")
same_shape = parse("input.cdd")
did_list = parse_dids("input.cdd")
dtc_list = parse_dtcs("input.cdd")
```

返回值是字典：

```json
{
    "error": 0,
    "data": {
        "CDD": {
            "ECU_NAME": {
                "id": "...",
                "name": "ECU_NAME",
                "type": "can",
                "udsTime": {},
                "seqList": [],
                "address": [],
                "didList": [],
                "dtcList": [],
                "allServiceList": {}
            }
        }
    }
}
```

失败时返回：

```json
{
    "error": 1,
    "message": "error message"
}
```

### 示例

仓库内包含一个最小示例：

```bash
python -m cddtools parse examples/Multilingual-Example.cdd
```

### 文档

- [使用说明](doc/usage.md)

### 测试

```bash
python -m unittest discover -s tests -p "test_*.py"
```

# cddtools

[中文](README.md)

`cddtools` is a standalone Python package for parsing CANdela `.cdd` diagnostic
files into JSON. It can be used as a Python library or as a command-line JSON
exporter.

### Features

- Parse `.cdd` files and export JSON.
- Parse ECU, variants, UDS services, request parameters, and response
  parameters.
- Parse CAN addressing, UDS timing, DID, DTC, CDD data types, enums, text
  tables, lengths, byte order, units, factor/offset, and related metadata.
- Include separate `didList` and `dtcList` fields in full JSON output.
- Export DID or DTC lists separately.
- Write JSON to stdout or to a specified output file.
- Provide Python APIs: `parse_tester_info()`, `parse()`, `parse_dids()`,
  `parse_dtcs()`, and `load_file()`.

### Install

```bash
pip install -e .
```

### CLI

Write JSON to a file:

```bash
cddtools parse input.cdd output.json --parseResp
```

Write JSON to stdout:

```bash
python -m cddtools parse input.cdd
```

Supported commands:

- `parse`
- `parseTesterInfo`
- `parse-tester-info`
- `parseDids`
- `parse-dids`
- `parseDtcs`
- `parse-dtcs`

`parse` currently returns the same JSON shape as `parseTesterInfo`.

Export DID or DTC separately:

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

The result is a dictionary:

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

On failure:

```json
{
    "error": 1,
    "message": "error message"
}
```

### Example

A minimal example is included:

```bash
python -m cddtools parse examples/Multilingual-Example.cdd
```

### Documentation

- [Usage](doc/usage.md)

### Testing

```bash
python -m unittest discover -s tests -p "test_*.py"
```

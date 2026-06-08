# Usage

`cddtools` parses CANdela `.cdd` diagnostic files and exports JSON. It is not
tied to a specific downstream tool format.

## Install

Install the package in editable mode during development:

```bash
pip install -e .
```

## Command Line

Export the full JSON structure to a file:

```bash
cddtools parse examples/Multilingual-Example.cdd output.json --parseResp
```

Print the full JSON structure to stdout:

```bash
python -m cddtools parse examples/Multilingual-Example.cdd
```

Export DID or DTC lists only:

```bash
python -m cddtools parseDids examples/Multilingual-Example.cdd
python -m cddtools parseDtcs examples/Multilingual-Example.cdd
```

## Python API

```python
from cddtools import parse, parse_dids, parse_dtcs

result = parse("examples/Multilingual-Example.cdd")
did_list = parse_dids("examples/Multilingual-Example.cdd")
dtc_list = parse_dtcs("examples/Multilingual-Example.cdd")
```

Successful calls return dictionaries with `error` set to `0`. Failed calls
return `error` set to `1` and include a `message` field.

## Tests

The test suite follows the lightweight `unittest` style used by projects such
as `odxtools`:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

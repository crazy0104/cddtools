# cddtools

[中文](README.zh.md)

`cddtools` is a standalone Python package for parsing `.cdd` diagnostic files
into JSON. It can be imported as a library, used from the command line to
export, and it also ships a GUI for previewing some of the content.

## Scope

This project only **reads**:

- **Learning** — understanding how the `.cdd` data model is laid out.
- **Previewing** — looking up a DID, a DTC or a service's telegram layout
  without opening the full editor.
- **Feeding AI tooling** — turning a `.cdd` into JSON an LLM or a script can
  read, so questions about an ECU's diagnostic content can be answered quickly
  during development.

### Install

```bash
pip install -e .
```

## What is implemented

| CDD content | Module | Notes |
|---|---|---|
| Data types (`DATATYPES`) | `cdd_datatypes_parser` | All thirteen conversions CANdelaStudio offers (Raw value, Text Table, Linear, Piecewise Linear, Characteristic Curve, Formula, Procedural Conversion, Packet, Mux and the four iteration kinds); bit-field members, invalid values, per-object attributes |
| DIDs (`DIDS`) | `cdd_did_parser` | Identifier, per-variant presence, DID data summary, whether it is used |
| Fault memory (`RECORDDTPOOL`) | `cdd_dtc_parser` | SAE J2012 code decoding (P/C/B/U + failure type byte), template-driven properties (Priority, Lamp Flag, Monitor type, …) |
| DTC status byte (`DTCSTATUSMASK`) | `cdd_dtc_parser.parse_status_mask()` | The 8 ISO 14229-1 bits, including whether the ECU implements each one, plus a combined supported mask |
| Diagnostic classes (`DCLTMPLS` + variants) | `cdd_diagnostic_classes_parser` | Every class the document defines, plus which ones each variant enables |
| Diagnostic instances and services (`DIAGINST`) | `cdd_services_parser` | Request / Pos. Resp. / Neg. Resp. telegram layouts, telegram tables with byte and bit positions, negative response codes |
| Attributes and interfaces (`DEFATTS`) | `cdd_attributes_parser` | Every interface the document defines with its communication parameters, each flagged with whether the ECU supports it |
| State groups (`STATEGROUPS`) | `cdd_states_parser` | Session and security-access state groups |
| *(derived, not a CDD section)* | `cdd_tester` | CAN addressing, ISO-TP parameters, UDS timing, services indexed by service id, and telegram parameters expanded with encoding / factor / offset / unit / choices / bit groups / start bit / ready-to-send byte buffers |

The attribute values carried by data types and DTC records themselves are
reported by their respective parsers.

## What is not implemented

| CDD content | Status |
|---|---|
| Protocol services as a standalone list | Used while parsing services, but not exposed as a list of its own |
| Negative responses as a standalone list | Same — currently attached to negative-response telegrams only |
| Snapshot records | Not parsed |
| Extended data records | Not parsed |
| Vehicle system groups | Not parsed |
| Requirements | Not parsed |
| Identifying features / patterns | Not parsed |
| Libraries / import pool | Not parsed |
| Which services each interface supports | Not parsed |
| ODX `ECUSHAREDDATA` | Not parsed |
| Diagnostic class templates themselves | Only read to resolve classes and services |

Known gaps inside what *is* implemented:

- DoIP interfaces are recognised and their timing can be read, but no matching
  address structure is produced — DoIP is not enabled in the sample document,
  so there is nothing to verify against.
- The payload placeholder shown in a telegram (`zz`, `yy`) is generated at
  display time and does not exist in the file, so it is emitted as `..`.

## CLI

```bash
cddtools parse input.cdd output.json      # write a JSON file
python -m cddtools parseDtcs input.cdd    # write to stdout
```

Both spellings are accepted (`parseDtcs` or `parse-dtcs`):

| Command | Output |
|---|---|
| `parse`, `parseTesterInfo` | The full connection-oriented structure |
| `parseDatatypes` | Data types |
| `parseDids` | DIDs |
| `parseDtcs` | DTCs |
| `parseDtcStatusMask` | DTC status byte |
| `parseDiagnosticClasses` | Diagnostic classes |
| `parseServices` | Diagnostic instances and telegrams |
| `parseSnapshot` | Stable DID/DTC definitions grouped by variant, with expanded data types |
| `parseStates` | State groups |
| `parseInterfaces` | Every interface, each with an `enabled` flag |
| `parseSupportedInterfaces` | Only the interfaces the ECU supports |
| `parseAttributes` | Every attribute definition and its effective value |

## Python API

Every entry point returns the same envelope:

```python
{"error": 0, "data": ...}          # success
{"error": 1, "message": "..."}     # failure
```

```python
import cddtools

cddtools.parse_dtcs("ECU.cdd")
cddtools.parse_interfaces("ECU.cdd")
cddtools.parse_tester_info("ECU.cdd")
cddtools.parse_snapshot("ECU.cdd")
```

`parse_snapshot` is a read-only view for comparing CDD files or variants. It
resolves DID data types, retains fixed and variable bit lengths, and omits
document-local IDs. DIDs and DTCs are selected by each variant's references;
they are definitions, not the ECU's current fault state. It does not require
a supported bus interface. Unresolved lengths are `None`, never zero.

To run several parsers over one document, load it only once:

```python
from cddtools import load_ecu_doc
from cddtools.cdd_did_parser import CddDidParser
from cddtools.cdd_dtc_parser import CddDtcParser

shared, ecu_doc = load_ecu_doc("ECU.cdd")
dids = CddDidParser(shared).parse(ecu_doc)
dtcs = CddDtcParser(shared).parse(ecu_doc)
```

## GUI

```bash
python -m cddtools.cdd_viewer
```

A read-only viewer with one tab per panel (Interfaces, Diagnostic Classes,
Supported Services, Data Types, DIDs, DTCs, DTC Status, States). Each tab has
its own "Export … as JSON" button.

## Examples and tests

`examples/parse_*_example.py` runs each parser on its own from the command
line.

`examples/CddTools.cdd` is the document every test and document is based on: a
template-derived file with no customer project data, committed to the
repository, so the tests run on a fresh clone:

```bash
python -m unittest discover -s tests
```

`.gitignore` keeps every other `.cdd`, their exports and any JSON exported from
them out of the repository — a confidential document dropped into `examples/`
is never committed by accident.

## Documentation

| | |
|---|---|
| [docs/usage.md](docs/usage.md) | Running it: CLI, Python API, GUI, example scripts, tests |
| [docs/cdd-format.md](docs/cdd-format.md) | The `.cdd` data model, the shared utilities, and the traps common to every parser |
| [docs/parsers.md](docs/parsers.md) | What each panel parser reads, the reference chains it follows, its output shape |
| [docs/tester.md](docs/tester.md) | The derived `cdd_tester` layer |
| [docs/viewer.md](docs/viewer.md) | The read-only GUI |

## Disclaimer

- **Output is for reference.**

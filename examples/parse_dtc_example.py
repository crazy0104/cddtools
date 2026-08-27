"""Parse the Fault Memory / DTC panel of a .cdd file.

Usage:
    python examples/parse_dtc_example.py [file.cdd]                 # summary + full list
    python examples/parse_dtc_example.py [file.cdd] --dtc DTC       # print one DTC's full details (e.g. P0100)
    python examples/parse_dtc_example.py [file.cdd] --json out.json # export all DTCs as JSON

With no file given, parses examples/CddTools.cdd.
"""

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cddtools.cdd_dtc_parser import CddDtcParser
from cddtools.cdd_parser_shared import CddParserShared

DEFAULT_CDD_PATH = Path(__file__).resolve().parent / "CddTools.cdd"


def load_dtcs(file_path):
    root = ET.parse(file_path).getroot()
    ecu_doc = root if root.tag == "ECUDOC" else root.find("ECUDOC")
    if ecu_doc is None:
        raise ValueError("ECUDOC not found")

    shared = CddParserShared()
    shared.build_id_index(ecu_doc)
    return CddDtcParser(shared).parse(ecu_doc)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", nargs="?", default=DEFAULT_CDD_PATH, type=Path)
    parser.add_argument("--dtc", help="print the full details of a single DTC by its display code (e.g. P0100)")
    parser.add_argument("--json", type=Path, help="export all parsed DTCs as JSON to this path")
    args = parser.parse_args()

    entries = load_dtcs(args.file)
    print(f"{args.file}: {len(entries)} DTC(s)")

    if args.json:
        args.json.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote {len(entries)} entries to {args.json}")
        return

    if args.dtc:
        entry = next((e for e in entries if e["dtc"] == args.dtc), None)
        if entry is None:
            print(f"No DTC {args.dtc!r}")
            return
        print(json.dumps(entry, indent=2, ensure_ascii=False))
        return

    print(f"\n{'DTC':<8} {'Failure':<9} {'Prio':<8} {'Used':<5} Error text")
    for entry in entries:
        priority = entry["properties"].get("Priority", "")
        print(f"{entry['dtc']:<8} {entry['failureType'] or '-':<9} {priority:<8} {'yes' if entry['used'] else 'no':<5} {entry['errorText']}")


if __name__ == "__main__":
    main()

"""Parse the DID Overview panel of a .cdd file.

Usage:
    python examples/parse_did_example.py [file.cdd]                     # summary + full list
    python examples/parse_did_example.py [file.cdd] --qual QUAL         # print one DID's full details
    python examples/parse_did_example.py [file.cdd] --json out.json     # export all DIDs as JSON

With no file given, parses examples/CddTools.cdd.
"""

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cddtools.cdd_did_parser import CddDidParser
from cddtools.cdd_parser_shared import CddParserShared

DEFAULT_CDD_PATH = Path(__file__).resolve().parent / "CddTools.cdd"


def load_dids(file_path):
    root = ET.parse(file_path).getroot()
    ecu_doc = root if root.tag == "ECUDOC" else root.find("ECUDOC")
    if ecu_doc is None:
        raise ValueError("ECUDOC not found")

    shared = CddParserShared()
    shared.build_id_index(ecu_doc)
    return CddDidParser(shared).parse(ecu_doc)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", nargs="?", default=DEFAULT_CDD_PATH, type=Path)
    parser.add_argument("--qual", help="print the full details of a single DID by its Qualifier")
    parser.add_argument("--json", type=Path, help="export all parsed DIDs as JSON to this path")
    args = parser.parse_args()

    entries = load_dids(args.file)
    print(f"{args.file}: {len(entries)} DID(s)")

    if args.json:
        args.json.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote {len(entries)} entries to {args.json}")
        return

    if args.qual:
        entry = next((e for e in entries if e["qual"] == args.qual), None)
        if entry is None:
            print(f"No DID with qual={args.qual!r}")
            return
        print(json.dumps(entry, indent=2, ensure_ascii=False))
        return

    print(f"\n{'Identifier':<10} {'Used':<5} {'Name':<50} DID Data")
    for entry in entries:
        print(f"{entry['identifierHex']:<10} {'yes' if entry['used'] else 'no':<5} {entry['name']:<50} {entry['dataSummary']}")


if __name__ == "__main__":
    main()

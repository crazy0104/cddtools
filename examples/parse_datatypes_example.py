"""Parse the Data Types panel of a .cdd file.

Usage:
    python examples/parse_datatypes_example.py [file.cdd]                  # summary + one sample per kind
    python examples/parse_datatypes_example.py [file.cdd] --qual QUAL      # print one entry's full details
    python examples/parse_datatypes_example.py [file.cdd] --json out.json  # export all entries as JSON

With no file given, parses examples/CddTools.cdd.
"""

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cddtools.cdd_datatypes_parser import CddDataTypesParser
from cddtools.cdd_parser_shared import CddParserShared

DEFAULT_CDD_PATH = Path(__file__).resolve().parent / "CddTools.cdd"


def load_datatypes(file_path):
    root = ET.parse(file_path).getroot()
    ecu_doc = root if root.tag == "ECUDOC" else root.find("ECUDOC")
    if ecu_doc is None:
        raise ValueError("ECUDOC not found")

    shared = CddParserShared()
    shared.build_id_index(ecu_doc)
    return CddDataTypesParser(shared).parse(ecu_doc)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", nargs="?", default=DEFAULT_CDD_PATH, type=Path)
    parser.add_argument("--qual", help="print the full details of a single data type by its Qualifier")
    parser.add_argument("--json", type=Path, help="export all parsed entries as JSON to this path")
    args = parser.parse_args()

    entries = load_datatypes(args.file)
    print(f"{args.file}: {len(entries)} data type(s)")

    if args.json:
        args.json.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote {len(entries)} entries to {args.json}")
        return

    if args.qual:
        entry = next((e for e in entries if e["qual"] == args.qual), None)
        if entry is None:
            print(f"No data type with qual={args.qual!r}")
            return
        print(json.dumps(entry, indent=2, ensure_ascii=False))
        return

    counts = Counter(entry["conversion"] for entry in entries)
    print("\nBy conversion:")
    for conversion, count in counts.most_common():
        print(f"  {conversion}: {count}")

    print("\nSample entry per kind:")
    seen_kinds = set()
    for entry in entries:
        if entry["kind"] in seen_kinds:
            continue
        seen_kinds.add(entry["kind"])
        print(f"\n--- {entry['conversion']} ({entry['kind']}) ---")
        print(json.dumps(entry, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

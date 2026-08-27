"""Parse the Supported Diagnostic Classes panel of a .cdd file.

Usage:
    python examples/parse_diagnostic_classes_example.py [file.cdd]                  # checkbox list per variant
    python examples/parse_diagnostic_classes_example.py [file.cdd] --qual QUAL      # one class's full details
    python examples/parse_diagnostic_classes_example.py [file.cdd] --enabled-only   # only ticked classes
    python examples/parse_diagnostic_classes_example.py [file.cdd] --json out.json  # export all as JSON

With no file given, parses examples/CddTools.cdd.
"""

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cddtools.cdd_diagnostic_classes_parser import CddDiagnosticClassesParser
from cddtools.cdd_parser_shared import CddParserShared

DEFAULT_CDD_PATH = Path(__file__).resolve().parent / "CddTools.cdd"


def load_diagnostic_classes(file_path):
    root = ET.parse(file_path).getroot()
    ecu_doc = root if root.tag == "ECUDOC" else root.find("ECUDOC")
    if ecu_doc is None:
        raise ValueError("ECUDOC not found")

    shared = CddParserShared()
    shared.build_id_index(ecu_doc)
    return CddDiagnosticClassesParser(shared).parse(ecu_doc)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", nargs="?", default=DEFAULT_CDD_PATH, type=Path)
    parser.add_argument("--qual", help="print the full details of a single class by its Qualifier")
    parser.add_argument("--enabled-only", action="store_true", help="list only classes enabled in some variant")
    parser.add_argument("--json", type=Path, help="export all parsed classes as JSON to this path")
    args = parser.parse_args()

    entries = load_diagnostic_classes(args.file)
    enabled_count = sum(entry["enabled"] for entry in entries)
    print(f"{args.file}: {len(entries)} diagnostic class(es) supported, {enabled_count} enabled")

    if args.json:
        args.json.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote {len(entries)} entries to {args.json}")
        return

    if args.qual:
        entry = next((e for e in entries if e["qual"] == args.qual), None)
        if entry is None:
            print(f"No diagnostic class with qual={args.qual!r}")
            return
        print(json.dumps(entry, indent=2, ensure_ascii=False))
        return

    if args.enabled_only:
        entries = [entry for entry in entries if entry["enabled"]]

    variant_quals = list(entries[0]["variants"]) if entries else []
    variant_header = "  ".join(f"{qual:^{max(len(qual), 5)}}" for qual in variant_quals)
    print(f"\n{'':3}{'Class':<46} {'Kind':<10} {variant_header}")
    for entry in entries:
        # "[x]" mirrors the panel checkbox; "S" marks singleton templates,
        # which show up in the tree as a bare diagnostic instance.
        mark = "[x]" if entry["enabled"] else "[ ]"
        singleton = "S" if entry["singleton"] else " "
        cells = "  ".join(
            f"{('yes' if entry['variants'][qual] else '-'):^{max(len(qual), 5)}}" for qual in variant_quals
        )
        print(f"{mark}{singleton} {entry['name']:<45} {entry['classKind'] or '':<10} {cells}")


if __name__ == "__main__":
    main()

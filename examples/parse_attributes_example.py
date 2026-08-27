"""Parse the attribute system: interfaces, communication parameters, timing.

Usage:
    python examples/parse_attributes_example.py [file.cdd]                 # interfaces + derived connection settings
    python examples/parse_attributes_example.py [file.cdd] --all           # every attribute, grouped by category
    python examples/parse_attributes_example.py [file.cdd] --category Timing
    python examples/parse_attributes_example.py [file.cdd] --json out.json

With no file given, parses examples/CddTools.cdd.
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cddtools.cdd_attributes_parser import CddAttributesParser
from cddtools.cdd_tester import CddTester
from cddtools.api import load_ecu_doc

DEFAULT_CDD_PATH = Path(__file__).resolve().parent / "CddTools.cdd"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", nargs="?", default=DEFAULT_CDD_PATH, type=Path)
    parser.add_argument("--all", action="store_true", help="list every attribute, grouped by category")
    parser.add_argument("--category", help="list only attributes of this category")
    parser.add_argument("--json", type=Path, help="export all parsed attributes as JSON")
    args = parser.parse_args()

    shared, ecu_doc = load_ecu_doc(args.file)
    attributes = CddAttributesParser(shared)
    entries = attributes.parse(ecu_doc)
    print(f"{args.file}: {len(entries)} attribute(s)")

    if args.json:
        args.json.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote {len(entries)} entries to {args.json}")
        return

    if args.all or args.category:
        grouped = defaultdict(list)
        for entry in entries:
            grouped[entry["category"]].append(entry)
        for category in sorted(grouped, key=lambda name: name or ""):
            if args.category and category != args.category:
                continue
            print(f"\n-- {category} ({len(grouped[category])}) --")
            for entry in grouped[category]:
                marker = "*" if entry["source"] != "default" else " "
                print(f"  {marker} {entry['qual']:44} = {str(entry['value']):>12}  ({entry['source']})")
        print("\n* = overridden below the definition's default")
        return

    print("\nInterfaces:")
    for interface in attributes.parse_interfaces(ecu_doc):
        mark = "[x]" if interface["enabled"] else "[ ]"
        print(f"  {mark} {interface['qual']:32} {len(interface['parameters'])} parameter(s)")

    interface = attributes.active_interface(ecu_doc)
    if interface is None:
        print("\nNo interface is marked as supported.")
        return

    tester = CddTester(shared)
    print(f"\nActive interface: {interface['qual']}  (bus kind: {tester.detect_bus_kind(interface)})")

    timing = tester.build_uds_timing(interface)
    print("\nUDS timing:")
    for key in ("pTime", "pExtTime", "s3Time", "testerPresentEnable"):
        if key in timing:
            print(f"  {key:20} {timing[key]}")

    print("\nAddresses:")
    for address in tester.build_can_addresses(interface):
        can = address["canAddr"]
        print(f"  {can['name']:11} tx={can['canIdTx']:12} rx={can['canIdRx']:12} {can['idType']}")
        print(f"              bs={can['bs']} stMin={can['stMin']} nAs={can['nAs']} nAr={can['nAr']} "
              f"nBs={can['nBs']} nCr={can['nCr']} padding={can['padding']}/{can['paddingValue']}")


if __name__ == "__main__":
    main()

"""Parse the Diagnostic Instance (services / telegrams) panel of a .cdd file.

Usage:
    python examples/parse_services_example.py [file.cdd]                  # one line per instance
    python examples/parse_services_example.py [file.cdd] --qual QUAL      # one instance in full
    python examples/parse_services_example.py [file.cdd] --class CLASS    # only instances of a class
    python examples/parse_services_example.py [file.cdd] --json out.json  # export all as JSON

With no file given, parses examples/CddTools.cdd.
"""

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cddtools.cdd_parser_shared import CddParserShared
from cddtools.cdd_services_parser import CddServicesParser

DEFAULT_CDD_PATH = Path(__file__).resolve().parent / "CddTools.cdd"


def load_services(file_path):
    root = ET.parse(file_path).getroot()
    ecu_doc = root if root.tag == "ECUDOC" else root.find("ECUDOC")
    if ecu_doc is None:
        raise ValueError("ECUDOC not found")

    shared = CddParserShared()
    shared.build_id_index(ecu_doc)
    return CddServicesParser(shared).parse(ecu_doc)


def print_instance(entry):
    header = f"{entry['className']} / {entry['name']}"
    if entry["identifier"]:
        header = f"{entry['className']} / {entry['identifier']} {entry['name']}"
    print(f"\n=== [{entry['variant']}] {header} ===")

    for service in entry["services"]:
        print(f"  Service: {service['name']}   Protocol Service: {service['protocolService']}")
        for key, label in (
            ("request", "Request "),
            ("positiveResponse", "Pos.Resp"),
            ("negativeResponse", "Neg.Resp"),
        ):
            primitive = service[key]
            if primitive:
                print(f"    {label}: {primitive['bytes']}")

    for telegram in entry["telegrams"]:
        print(f"\n  Telegram: {telegram['name']}")
        print(f"    {'Byte':>4} {'Bit':>3}  {'Name':<34} {'Data Type':<44} {'Default':<9} Constant")
        for param in telegram["parameters"]:
            bit = "" if param["bitPos"] is None else str(param["bitPos"])
            print(
                f"    {param['byteNo']:>4} {bit:>3}  {param['name'][:34]:<34} "
                f"{(param['dataType'] or '')[:44]:<44} {(param['default'] or ''):<9} {param['constant'] or ''}"
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", nargs="?", default=DEFAULT_CDD_PATH, type=Path)
    parser.add_argument("--qual", help="print one diagnostic instance in full by its Qualifier")
    parser.add_argument("--class", dest="class_qual", help="only instances whose class Qualifier matches")
    parser.add_argument("--json", type=Path, help="export all parsed instances as JSON to this path")
    args = parser.parse_args()

    entries = load_services(args.file)
    print(f"{args.file}: {len(entries)} diagnostic instance(s)")

    if args.json:
        args.json.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote {len(entries)} entries to {args.json}")
        return

    if args.qual:
        matches = [e for e in entries if e["qual"] == args.qual]
        if not matches:
            print(f"No diagnostic instance with qual={args.qual!r}")
            return
        for entry in matches:
            print(json.dumps(entry, indent=2, ensure_ascii=False))
        return

    if args.class_qual:
        matches = [e for e in entries if e["classQual"] == args.class_qual]
        if not matches:
            available = sorted({e["classQual"] for e in entries})
            print(f"No diagnostic class with qual={args.class_qual!r}")
            print(f"Available: {', '.join(available)}")
            return
        for entry in matches:
            print_instance(entry)
        return

    print(f"\n{'Variant':<24} {'Class':<30} {'Id':<6} {'Instance':<32} Request / PosResp / NegResp")
    for entry in entries:
        service = entry["services"][0] if entry["services"] else None
        telegrams = ""
        if service:
            telegrams = " | ".join(
                service[key]["bytes"]
                for key in ("request", "positiveResponse", "negativeResponse")
                if service[key]
            )
        print(
            f"{entry['variant'][:24]:<24} {entry['className'][:30]:<30} "
            f"{entry['identifier'] or '':<6} {entry['name'][:32]:<32} {telegrams}"
        )


if __name__ == "__main__":
    main()

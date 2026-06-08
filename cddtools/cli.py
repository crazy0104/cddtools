import argparse
import json
import sys

from .api import parse, parse_dids, parse_dtcs, parse_tester_info
from ._version import __version__


def _build_arg_parser():
    parser = argparse.ArgumentParser(
        prog="cddtools",
        description="Parse CANdela CDD files and write JSON output.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "command",
        choices=(
            "parse",
            "parseTesterInfo",
            "parse-tester-info",
            "parseDids",
            "parse-dids",
            "parseDtcs",
            "parse-dtcs",
        ),
        help="Parser command to run.",
    )
    parser.add_argument("cdd_file_path", help="Input .cdd file path.")
    parser.add_argument(
        "output_json_path",
        nargs="?",
        help="Output JSON file path. If omitted, JSON is written to stdout.",
    )
    parser.add_argument(
        "--parseResp",
        action="store_true",
        help="Parse response parameters when supported.",
    )
    return parser


def run_command(command, cdd_file_path, parse_resp=False):
    if command == "parse":
        return parse(cdd_file_path, parse_resp=parse_resp)
    if command in ("parseTesterInfo", "parse-tester-info"):
        return parse_tester_info(cdd_file_path, parse_resp=parse_resp)
    if command in ("parseDids", "parse-dids"):
        return parse_dids(cdd_file_path)
    if command in ("parseDtcs", "parse-dtcs"):
        return parse_dtcs(cdd_file_path)
    return {"error": 1, "message": f"Unknown command: {command}"}


def main(argv=None):
    parser = _build_arg_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    result = run_command(args.command, args.cdd_file_path, args.parseResp)
    json_text = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output_json_path:
        with open(args.output_json_path, "w", encoding="utf-8") as handle:
            handle.write(json_text)
            handle.write("\n")
    else:
        print(json_text)

    return 1 if result.get("error") else 0

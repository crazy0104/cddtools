import argparse
import json
import sys

from ._version import __version__
from .api import (
    parse,
    parse_attributes,
    parse_datatypes,
    parse_diagnostic_classes,
    parse_dids,
    parse_dtc_status_mask,
    parse_dtcs,
    parse_interfaces,
    parse_services,
    parse_snapshot,
    parse_states,
    parse_supported_interfaces,
    parse_tester_info,
)

# Command -> handler. Both spellings of each name are accepted so scripts
# written against either style keep working.
COMMANDS = {
    "parse": parse,
    "parseTesterInfo": parse_tester_info,
    "parse-tester-info": parse_tester_info,
    "parseDids": parse_dids,
    "parse-dids": parse_dids,
    "parseDtcs": parse_dtcs,
    "parse-dtcs": parse_dtcs,
    "parseDatatypes": parse_datatypes,
    "parse-datatypes": parse_datatypes,
    "parseDiagnosticClasses": parse_diagnostic_classes,
    "parse-diagnostic-classes": parse_diagnostic_classes,
    "parseServices": parse_services,
    "parse-services": parse_services,
    "parseSnapshot": parse_snapshot,
    "parse-snapshot": parse_snapshot,
    "parseAttributes": parse_attributes,
    "parse-attributes": parse_attributes,
    "parseInterfaces": parse_interfaces,
    "parse-interfaces": parse_interfaces,
    "parseSupportedInterfaces": parse_supported_interfaces,
    "parse-supported-interfaces": parse_supported_interfaces,
    "parseStates": parse_states,
    "parse-states": parse_states,
    "parseDtcStatusMask": parse_dtc_status_mask,
    "parse-dtc-status-mask": parse_dtc_status_mask,
}


def _build_arg_parser():
    parser = argparse.ArgumentParser(
        prog="cddtools",
        description="Parse CDD files and write JSON output.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("command", choices=tuple(COMMANDS), help="Parser command to run.")
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
    handler = COMMANDS.get(command)
    if handler is None:
        return {"error": 1, "message": f"Unknown command: {command}"}
    if handler in (parse, parse_tester_info):
        return handler(cdd_file_path, parse_resp=parse_resp)
    return handler(cdd_file_path)


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

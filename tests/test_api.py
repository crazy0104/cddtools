import unittest
from pathlib import Path

from cddtools import __version__, parse, parse_dids, parse_dtcs


EXAMPLE_CDD = Path(__file__).resolve().parents[1] / "examples" / "Multilingual-Example.cdd"


class ApiTests(unittest.TestCase):
    def test_version_is_available(self):
        self.assertEqual(__version__, "0.0.1")

    def test_parse_exports_json_data(self):
        result = parse(EXAMPLE_CDD)

        self.assertEqual(result["error"], 0)
        root = next(iter(result["data"].values()))
        ecu = next(iter(root.values()))

        self.assertEqual(ecu["name"], "Multilingual_Example")
        self.assertEqual(len(ecu["didList"]), 2)
        self.assertEqual(len(ecu["dtcList"]), 0)
        self.assertIn("0x22", ecu["allServiceList"])
        self.assertIn("0x2E", ecu["allServiceList"])

    def test_parse_dids_exports_did_list(self):
        result = parse_dids(EXAMPLE_CDD)

        self.assertEqual(result["error"], 0)
        self.assertEqual(len(result["data"]), 2)
        self.assertEqual(result["data"][0]["name"], "A/D Values")

    def test_parse_dtcs_exports_empty_dtc_list_when_absent(self):
        result = parse_dtcs(EXAMPLE_CDD)

        self.assertEqual(result["error"], 0)
        self.assertEqual(result["data"], [])


if __name__ == "__main__":
    unittest.main()

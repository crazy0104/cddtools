"""Read-only comparison and fault-memory request regressions."""

import base64
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from cddtools import load_ecu_doc, parse_snapshot, parse_tester_info
from cddtools.cdd_snapshot import CddSnapshotParser

SAMPLE = PROJECT_ROOT / "examples" / "CddTools.cdd"


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tree = ET.parse(SAMPLE)
        self.doc = self.tree.getroot().find("ECUDOC")

    def snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.cdd"
            self.tree.write(path, encoding="utf-8")
            result = parse_snapshot(path)
            self.assertEqual(result["error"], 0, result.get("message"))
            return result["data"]

    def test_same_file_is_stable_and_read_only(self):
        before = SAMPLE.read_bytes()
        first = parse_snapshot(SAMPLE)
        self.assertEqual(first["error"], 0)
        self.assertEqual(first, parse_snapshot(SAMPLE))
        self.assertEqual(SAMPLE.read_bytes(), before)

    def test_xml_ids_and_definition_order_do_not_affect_snapshot(self):
        expected = self.snapshot()
        identifiers = {
            element.attrib["id"]: f"replacement_{index}"
            for index, element in enumerate(self.doc.iter()) if "id" in element.attrib
        }
        for element in self.doc.iter():
            for key, value in list(element.attrib.items()):
                element.set(key, identifiers.get(value, value))
        datatypes = self.doc.find("DATATYPES")
        datatypes[:] = list(reversed(list(datatypes)))
        self.assertEqual(self.snapshot(), expected)

    def test_variants_use_their_own_did_and_dtc_references(self):
        variants = self.doc.find("ECU").findall("VAR")
        refs = variants[1].find("DIDREFS")
        removed_id = refs[0].attrib["didRef"]
        removed_number = int(next(d for d in self.doc.find("DIDS") if d.attrib["id"] == removed_id).attrib["n"])
        refs.remove(refs[0])
        base, other = self.snapshot()["variants"]
        self.assertEqual((len(base["dids"]), len(other["dids"])), (16, 15))
        self.assertNotIn(removed_number, [d["identifier"] for d in other["dids"]])
        self.assertEqual((len(base["dtcs"]), len(other["dtcs"])), (4, 0))

    def test_type_length_change_is_visible_without_a_did_change(self):
        expected = self.snapshot()["variants"][0]["dids"][0]
        did = next(d for d in self.doc.find("DIDS") if int(d.attrib["n"]) == expected["identifier"])
        reference = did.find("STRUCTURE/DATAOBJ").attrib["dtref"]
        datatype = next(d for d in self.doc.find("DATATYPES") if d.attrib["id"] == reference)
        datatype.find("CVALUETYPE").set("bl", "24")
        actual = self.snapshot()["variants"][0]["dids"][0]
        self.assertEqual(expected["bitLength"], 80)
        self.assertEqual(actual["bitLength"], 120)
        self.assertEqual(actual["identifier"], expected["identifier"])

    def test_enum_and_linear_conversion_changes_are_inlined(self):
        did = self.doc.find("DIDS/DID")
        member = did.find("STRUCTURE/DATAOBJ")
        for kind, child_tag, attribute, value in (("TEXTTBL", "TEXTMAP", "s", "999"), ("LINCOMP", "COMP", "f", "2.5")):
            with self.subTest(kind=kind):
                datatype = self.doc.find(f"DATATYPES/{kind}")
                member.set("dtref", datatype.attrib["id"])
                before = self.snapshot()
                datatype.find(child_tag).set(attribute, value)
                self.assertNotEqual(self.snapshot(), before)

    def test_text_map_order_does_not_affect_snapshot(self):
        table = next(d for d in self.doc.find("DATATYPES") if d.findtext("QUAL") == "UDS_Version_4_Byte")
        expected = self.snapshot()
        self.assertIn("UDS_Version_4_Byte", json.dumps(expected))
        mappings = table.findall("TEXTMAP")
        for mapping in mappings:
            table.remove(mapping)
        table.extend(reversed(mappings))
        self.assertEqual(self.snapshot(), expected)

    def test_text_map_values_use_the_coded_element_width(self):
        table = next(d for d in self.doc.find("DATATYPES") if d.findtext("QUAL") == "UDS_Version_4_Byte")
        table.find("CVALUETYPE").attrib.update(bl="16", qty="field", minsz="2", maxsz="2")
        mappings = table.findall("TEXTMAP")
        for mapping in mappings[1:]:
            table.remove(mapping)
        did = self.doc.find("DIDS/DID")
        did.find("STRUCTURE/DATAOBJ").set("dtref", table.attrib["id"])
        previous = None
        for value, expected in (("(1,0)", "0x00010000"), ("(0,256)", "0x00000100")):
            mappings[0].attrib.update(s=value, e="(1,256)")
            current = self.snapshot()
            parsed_did = next(d for d in current["variants"][0]["dids"] if d["identifier"] == int(did.attrib["n"]))
            row = parsed_did["data"][0]["dataType"]["textTable"][0]
            self.assertEqual(row["start"], expected)
            self.assertEqual(row["end"], "0x00010100")
            if previous is not None:
                self.assertNotEqual(current, previous)
            previous = current

    def test_member_order_remains_significant(self):
        structure = self.doc.find("DIDS/DID/STRUCTURE")
        structure.clear()
        ET.SubElement(structure, "GAPDATAOBJ", bl="3")
        ET.SubElement(structure, "GAPDATAOBJ", bl="5")
        expected = self.snapshot()
        structure[:] = list(reversed(list(structure)))
        self.assertNotEqual(self.snapshot(), expected)

    def test_procedure_job_file_contents_are_compared(self):
        datatype = self.doc.find("DATATYPES/PROCDT")
        did = self.doc.find("DIDS/DID")
        did.find("STRUCTURE/DATAOBJ").set("dtref", datatype.attrib["id"])
        job = self.doc.find("JOBFILES/JOBFILE")
        document = job.find("EXTDOC")
        contents = document.find("FILECONTENTS")
        expected = self.snapshot()
        parsed_did = next(d for d in expected["variants"][0]["dids"] if d["identifier"] == int(did.attrib["n"]))
        result = parsed_did["data"][0]["dataType"]["procedure"][0]["jobFile"]
        self.assertEqual(result["syntax"], "CAPL")
        self.assertEqual(result["documents"][0]["filename"], "CddTools.can")
        self.assertEqual(result["documents"][0]["contentHash"], hashlib.sha256(base64.b64decode(contents.text)).hexdigest())
        document.attrib.update(creationdt="new creation time", changedt="new change time")
        contents.text = "\n".join(contents.text.split())
        job.set("id", "renumbered_job")
        datatype.find("PROCCONV/FUNCTION").set("jobFileRef", "renumbered_job")
        self.assertEqual(self.snapshot(), expected)
        replacement = b"variables { int changed; }"
        contents.text = base64.b64encode(replacement).decode("ascii")
        contents.set("len", str(len(replacement)))
        self.assertNotEqual(self.snapshot(), expected)

    def test_gap_structure_and_variable_length_offsets(self):
        did = self.doc.find("DIDS/DID")
        structure = did.find("STRUCTURE")
        structure.clear()
        types = self.doc.find("DATATYPES")
        datatype = ET.SubElement(types, "IDENT", id="test_variable")
        ET.SubElement(datatype, "QUAL").text = "VariableBytes"
        ET.SubElement(datatype, "CVALUETYPE", bl="8", qty="field", minsz="0", maxsz="4")
        ET.SubElement(structure, "GAPDATAOBJ", bl="3")
        nested = ET.SubElement(structure, "STRUCT")
        ET.SubElement(nested, "GAPDATAOBJ", bl="5")
        ET.SubElement(structure, "DATAOBJ", dtref="test_variable")
        ET.SubElement(structure, "GAPDATAOBJ", bl="8")
        result = next(d for d in self.snapshot()["variants"][0]["dids"] if d["identifier"] == int(did.attrib["n"]))
        self.assertIsNone(result["bitLength"])
        self.assertEqual((result["minBitLength"], result["maxBitLength"]), (16, 48))
        self.assertTrue(result["variableLength"])
        self.assertEqual([m["bitOffset"] for m in result["data"]], [0, 3, 8, None])

    def test_unresolved_type_has_unknown_length(self):
        did = self.doc.find("DIDS/DID")
        did.find("STRUCTURE/DATAOBJ").set("dtref", "missing")
        result = next(d for d in self.snapshot()["variants"][0]["dids"] if d["identifier"] == int(did.attrib["n"]))
        self.assertIsNone(result["bitLength"])
        self.assertIsNone(result["minBitLength"])
        self.assertTrue(result["data"][0]["dataType"]["unresolved"])

    def test_numeric_dtc_properties_are_not_lost(self):
        before = self.snapshot()
        record = next(self.doc.iter("RECORD"))
        field = record.find("UNSRECORDITEM")
        field.set("v", "7")
        after = self.snapshot()
        self.assertNotEqual(after, before)
        changed = next(d for d in after["variants"][0]["dtcs"] if d["raw"] == int(record.attrib["v"]))
        self.assertIn(7, changed["properties"].values())

    def test_snapshot_does_not_require_a_supported_interface(self):
        ecu = self.doc.find("ECU")
        attributes = self.doc.find("ATTRCATS")
        if attributes is not None:
            self.doc.remove(attributes)
        for child in list(ecu):
            if child.tag in ("ENUM", "UNS", "CSTR"):
                ecu.remove(child)
        self.assertEqual(len(self.snapshot()["variants"][0]["dtcs"]), 4)

    def test_snapshot_cli(self):
        completed = subprocess.run(
            [sys.executable, "-m", "cddtools", "parse-snapshot", str(SAMPLE)],
            cwd=PROJECT_ROOT, capture_output=True, text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(len(json.loads(completed.stdout)["data"]["variants"]), 2)


class FaultMemoryRequestTests(unittest.TestCase):
    def test_record_number_and_dtc_form_complete_requests(self):
        result = parse_tester_info(SAMPLE)
        self.assertEqual(result["error"], 0, result.get("message"))
        tester = result["data"]["CddTools"]["Base_Variant"]
        for subfunction in ("0x04", "0x06"):
            service = next(s for s in tester["allServiceList"]["0x19"] if s["subfunc"] == subfunction)
            self.assertEqual(len(service["params"]), 3)
            _, dtc, record = service["params"]
            self.assertEqual((record["type"], record["bitLen"]), ("NUM", 8))
            self.assertFalse(record["meta"]["cddField"]["variableLength"])
            self.assertTrue(record["editable"])
            self.assertIn("1", record["meta"]["cddField"]["choices"])
            selected = next(d for d in dtc["DTC_Table"] if d["hexValue"] == 0x010017)
            self.assertEqual(selected["bitLength"], 24)
            dtc["value"]["data"] = list(selected["hexValue"].to_bytes(3, "big"))
            pdu = [0x19] + [byte for param in service["params"] for byte in param["value"]["data"]]
            self.assertEqual(pdu, [0x19, int(subfunction, 16), 0x01, 0x00, 0x17, 0x01])
        self.assertEqual(result["data"]["CddTools"]["Base_Variant1"]["dtcList"], [])

    def test_obd_records_do_not_enter_uds_dtc_picker(self):
        shared, doc = load_ecu_doc(SAMPLE)
        pool = next(d for d in doc.iter("RECORDDT") if d.attrib.get("rtSpec") == "faultMemory")
        obd = copy.deepcopy(pool)
        obd.set("rtSpec", "obdFaultMemory")
        for record in obd.findall("RECORD"):
            record.set("id", record.attrib["id"] + "_obd")
            record.set("v", "256")
        doc.find("RECORDDTPOOL").append(obd)
        variant = doc.find("ECU/VAR")
        ET.SubElement(variant, "RECORDREF", idref=obd.find("RECORD").attrib["id"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "obd.cdd"
            ET.ElementTree(doc).write(path, encoding="utf-8")
            result = parse_tester_info(path)
        self.assertEqual(result["error"], 0, result.get("message"))
        tester = result["data"]["CddTools"]["Base_Variant"]
        self.assertEqual({d["bitLength"] for d in tester["dtcList"]}, {16, 24})
        service = next(s for s in tester["allServiceList"]["0x19"] if s["subfunc"] == "0x04")
        self.assertEqual(len(service["params"][1]["DTC_Table"]), 4)
        self.assertEqual({d["source"] for d in service["params"][1]["DTC_Table"]}, {"faultMemory"})


if __name__ == "__main__":
    unittest.main()

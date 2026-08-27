"""Regression tests for the CDD parsers.

Everything runs against `examples/CddTools.cdd`, the one document committed
to this repository. It is a template-derived document with no customer
project data, and it is rich enough to exercise each parser:
seven interfaces (CAN, CAN Extended, CAN FD, CAN FD Extended, two FlexRay
variants and DoIP), 114 data types covering all thirteen conversions, DIDs
both used and unused, DTCs, 30 diagnostic classes and the state groups.

Expected values here were read back from that document.
"""

import sys
import unittest
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from cddtools.cdd_attributes_parser import CddAttributesParser
from cddtools.cdd_datatypes_parser import CONVERSION_LABELS, CddDataTypesParser
from cddtools.cdd_diagnostic_classes_parser import CddDiagnosticClassesParser
from cddtools.cdd_did_parser import CddDidParser
from cddtools.cdd_dtc_parser import CddDtcParser
from cddtools.cdd_parser_shared import CddParserShared
from cddtools.cdd_services_parser import CddServicesParser
from cddtools.cdd_states_parser import CddStatesParser
from cddtools.cdd_tester import CddTester

EXAMPLES = PROJECT_ROOT / "examples"
SAMPLE = EXAMPLES / "CddTools.cdd"


def load_ecu_doc(file_path):
    root = ET.parse(file_path).getroot()
    ecu_doc = root if root.tag == "ECUDOC" else root.find("ECUDOC")
    shared = CddParserShared()
    shared.build_id_index(ecu_doc)
    return shared, ecu_doc


class SampleTestCase(unittest.TestCase):
    """Parses the sample document once for the whole class."""

    @classmethod
    def setUpClass(cls):
        if not SAMPLE.exists():
            raise unittest.SkipTest(f"{SAMPLE.name} is not checked out")
        cls.shared, cls.ecu_doc = load_ecu_doc(SAMPLE)


class FieldValueTests(unittest.TestCase):
    """A field (array) value lists one entry per element, as "(a,b,c)".

    `CVALUETYPE@bl` is the width of one element, so the value on the wire is
    the elements folded together, first element most significant. Reading
    such a value as a single number is what used to abort a whole import.
    """

    def setUp(self):
        self.shared = CddParserShared()

    def test_scalar_values_are_unchanged(self):
        self.assertEqual(self.shared.cdd_int("1792"), 1792)
        self.assertEqual(self.shared.hex_value("1792"), "0x700")
        self.assertEqual(self.shared.hex_value("204"), "0xCC")

    def test_field_values_fold_big_endian(self):
        self.assertEqual(self.shared.cdd_int("(0,0,0,0,0,0)"), 0)
        self.assertEqual(self.shared.cdd_int("(1,2)"), 0x0102)
        self.assertEqual(self.shared.cdd_int("(1,2)", 16), 0x00010002)
        self.assertEqual(self.shared.hex_value("(0,0,0,0,0,0)"), "0x000000000000")
        self.assertEqual(self.shared.hex_value("(144,4)"), "0x9004")

    def test_non_numeric_values_do_not_raise(self):
        self.assertIsNone(self.shared.cdd_int("(en-US,zh-HANS)"))
        self.assertIsNone(self.shared.cdd_int(""))
        self.assertIsNone(self.shared.cdd_int(None))
        self.assertEqual(self.shared.hex_value("(en-US,zh-HANS)"), "(en-US,zh-HANS)")


class DataTypesParserTests(SampleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.entries = CddDataTypesParser(cls.shared).parse(cls.ecu_doc)
        cls.by_qual = {entry["qual"]: entry for entry in cls.entries}

    def test_every_kind_resolves_to_a_label(self):
        """A kind missing from CONVERSION_LABELS falls back to the raw tag,
        which reads like a label and so goes unnoticed. Every kind the sample
        contains must be mapped."""
        unmapped = sorted(
            {entry["kind"] for entry in self.entries} - set(CONVERSION_LABELS)
        )

        self.assertEqual(unmapped, [])

    def test_all_thirteen_conversions_are_covered(self):
        """The document was extended to hold one of every data type kind
        CANdelaStudio offers, so the sample exercises each branch."""
        self.assertEqual(
            {entry["kind"] for entry in self.entries}, set(CONVERSION_LABELS)
        )

    def test_conversion_breakdown(self):
        """Only the kinds the document is built around are pinned by count;
        the rest exist once each and are asserted above."""
        counts = Counter(entry["conversion"] for entry in self.entries)

        self.assertEqual(counts["Text Table"], 54)
        self.assertEqual(counts["Raw value"], 43)
        self.assertEqual(counts["Packet"], 3)
        self.assertEqual(counts["Mux"], 2)

    def test_bit_length_display(self):
        # An atom renders as "byte:bit"...
        self.assertEqual(self.by_qual["P2"]["bitLength"], "2:0")
        # ...a fixed-size field as "[elements]".
        self.assertEqual(self.by_qual["ASCII_17_Bytes"]["bitLength"], "[17]")
        # ...and a variable one as "[min..max]".
        self.assertEqual(self.by_qual["Memory_Address_and_Size"]["bitLength"], "[2..9]")

    def test_linear_conversion(self):
        entry = self.by_qual["P2Ex"]

        self.assertEqual(entry["conversion"], "Linear")
        self.assertEqual(entry["linear"]["factor"], 10.0)
        self.assertEqual(entry["linear"]["offset"], 0.0)
        self.assertEqual(entry["physicalValue"]["unit"], "ms")

    def test_characteristic_curve_carries_its_interpolation_flag(self):
        """VALTBL is the only conversion that reads back an @interpolated
        attribute; it is what separates a curve from a piecewise linear."""
        entry = self.by_qual["Characteristic_Curve"]

        self.assertEqual(entry["conversion"], "Characteristic Curve")
        self.assertIs(entry["interpolated"], False)

    def test_piecewise_linear_is_a_distinct_kind(self):
        entry = self.by_qual["Piecewise_Linear"]

        self.assertEqual(entry["kind"], "COMPTBL")
        self.assertEqual(entry["conversion"], "Piecewise Linear")

    def test_formula_carries_its_expression_and_direction(self):
        entry = self.by_qual["Formula"]

        self.assertEqual(entry["conversion"], "Formula")
        self.assertEqual(
            entry["formula"], [{"usage": "coded2Phys", "text": "abs(x)"}]
        )

    def test_procedure_points_at_a_job_file(self):
        """A procedural conversion delegates to a function in a job file;
        entryPoint is empty here and normalises to None."""
        entry = self.by_qual["Procedure"]
        function, = entry["procedure"]

        self.assertEqual(entry["conversion"], "Procedural Conversion")
        self.assertEqual(function["usage"], "coded2Phys")
        self.assertTrue(function["jobFileRef"])
        self.assertIsNone(function["entryPoint"])

    def test_iterations_expose_their_members(self):
        """Every iteration kind repeats a member list. Before the kinds were
        named correctly these fell through and lost their members entirely."""
        for qual in ("Fixed_Count", "Counter", "_End_Marker", "End_of_Service"):
            with self.subTest(qual=qual):
                self.assertTrue(self.by_qual[qual]["members"])

    def test_fixed_count_iteration_stores_its_repetition_count(self):
        """A fixed count is the only iteration whose length is in the file;
        the other three read it from the telegram or the service."""
        entry = self.by_qual["Fixed_Count"]

        self.assertEqual(entry["conversion"], "Fixed Count Iteration")
        self.assertEqual(entry["numOfItems"], 2)
        self.assertEqual(len(entry["members"]), 2)

    def test_counter_and_end_marker_iterations_have_no_stored_count(self):
        for qual in ("Counter", "_End_Marker"):
            with self.subTest(qual=qual):
                self.assertNotIn("numOfItems", self.by_qual[qual])

    def test_end_of_service_iteration_stores_a_minimum(self):
        entry = self.by_qual["End_of_Service"]

        self.assertEqual(entry["conversion"], "End-of-Service Iteration")
        self.assertEqual(entry["minNumOfItems"], 1)

    def test_text_table_with_ranges_and_add_info(self):
        entry = self.by_qual["DataIdentifier"]

        self.assertEqual(entry["conversion"], "Text Table")
        self.assertTrue(any(row["end"] for row in entry["textTable"]))
        self.assertTrue(any(row["addInfo"] for row in entry["textTable"]))

    def test_invalid_values(self):
        entry = self.by_qual["CAN_Protocols_Supported_1Byte"]

        self.assertTrue(entry["invalidValues"])
        for invalid in entry["invalidValues"]:
            self.assertTrue(invalid["start"].startswith("0x"))
            self.assertIsNotNone(invalid["invalidType"])

    def test_attributes_resolve_through_attrref(self):
        entry = self.by_qual["DTC_Aging_Counter_Counting_Downwards"]

        self.assertTrue(entry["attributes"])
        for attribute in entry["attributes"]:
            self.assertTrue(attribute["name"])

    def test_packet_members_include_bitfield_and_gap(self):
        entry = self.by_qual["Communication_Type"]

        self.assertEqual(entry["conversion"], "Packet")
        struct = entry["members"][0]
        self.assertEqual(struct["type"], "Struct")
        self.assertEqual(
            [(m["name"], m["type"]) for m in struct["members"]],
            [
                ("normalCommunicationMessages", "Member"),
                ("networkManagementCommunicationMessages", "Member"),
                ("(reserved)", "Gap"),
                ("communicationTypeNetworks", "Member"),
            ],
        )
        self.assertEqual(struct["members"][2]["bitLength"], 2)

    def test_mux_selector_and_cases(self):
        entry = self.by_qual["Memory_Address_and_Size"]

        self.assertEqual(entry["conversion"], "Mux")
        self.assertEqual(entry["mux"]["selectorDtQual"], "AddressAndLengthFormatIdentifier")
        self.assertEqual([m["name"] for m in entry["mux"]["default"]], ["Address", "Size"])
        self.assertEqual(entry["mux"]["cases"][0]["start"], "0x11")
        for case in entry["mux"]["cases"]:
            self.assertTrue(case["members"])

    def test_precision_is_read_from_sig_not_treated_as_signed(self):
        """`sig` is Precision (decimal places); signedness lives in `enc`."""
        signed = [
            e for e in self.entries if (e["codedValue"] or {}).get("encoding") == "Signed"
        ]
        self.assertTrue(signed)
        for entry in self.entries:
            for value_type in (entry["codedValue"], entry["physicalValue"]):
                if value_type:
                    self.assertIsInstance(value_type["precision"], int)


class DidParserTests(SampleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.entries = CddDidParser(cls.shared).parse(cls.ecu_doc)

    def test_identifier_is_read_and_formatted(self):
        by_id = {entry["identifierHex"]: entry for entry in self.entries}

        self.assertEqual(by_id["0x0100"]["name"], "Development Data")
        self.assertEqual(by_id["0x0100"]["identifier"], 0x0100)
        # Four hex digits, matching the DID Overview panel.
        for entry in self.entries:
            self.assertRegex(entry["identifierHex"], r"^0x[0-9A-F]{4}$")

    def test_sorted_by_identifier(self):
        identifiers = [entry["identifier"] for entry in self.entries]
        self.assertEqual(identifiers, sorted(identifiers))

    def test_unused_dids_are_detected(self):
        """A DID listed in the variant's DIDREFS but referenced by no
        DIDDATAREF/DIDREF is defined but never read or written."""
        unused = [e["identifierHex"] for e in self.entries if not e["used"]]

        self.assertEqual(unused, ["0xFF00", "0xFF01"])

    def test_multi_object_data_summary(self):
        entry = next(e for e in self.entries if e["identifierHex"] == "0x0100")

        self.assertGreater(len(entry["data"]), 1)
        self.assertIn(", ", entry["dataSummary"])
        self.assertTrue(entry["dataSummary"].startswith("Operating System"))

    def test_per_variant_presence(self):
        """A DID reports the variants it appears in. Pinning the exact list
        breaks whenever the sample gains a variant, so assert the mechanism:
        every DID names at least one, and only variants the document defines."""
        declared = {
            (var.findtext("QUAL") or "").strip() for var in self.ecu_doc.iter("VAR")
        }

        self.assertIn("Base_Variant", declared)
        for entry in self.entries:
            self.assertTrue(entry["variants"])
            self.assertLessEqual(set(entry["variants"]), declared)


class DtcParserTests(SampleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.entries = CddDtcParser(cls.shared).parse(cls.ecu_doc)
        cls.by_dtc = {entry["dtc"]: entry for entry in cls.entries}

    def test_dtc_code_decoding(self):
        """24-bit raw value -> SAE J2012 display code + failure type byte.

        The top two bits of the 16-bit code select P/C/B/U; the low byte of
        the 24-bit value is the failure type.
        """
        # 0x010017: category bits '00' -> P, code 0x0100, failure type 0x17.
        self.assertEqual(self.by_dtc["P0100"]["raw"], 0x010017)
        self.assertEqual(self.by_dtc["P0100"]["failureType"], "0x17")
        # 0xD17488: category bits '11' -> U, code 0x1174, failure type 0x88.
        self.assertEqual(self.by_dtc["U1174"]["raw"], 0xD17488)
        self.assertEqual(self.by_dtc["U1174"]["failureType"], "0x88")

    def test_failure_type_text_from_the_shared_table(self):
        self.assertEqual(
            self.by_dtc["P0100"]["failureTypeText"], "Circuit Voltage Above Threshold"
        )
        self.assertEqual(self.by_dtc["U1174"]["failureTypeText"], "Bus off")

    def test_properties_come_from_the_record_template(self):
        """Property names are declared per document by RECORDTMPL, so the
        parser reports whatever columns that template defines."""
        properties = self.by_dtc["P0100"]["properties"]

        self.assertIn("DTC Priority", properties)
        self.assertIn("DTC Severity", properties)
        for entry in self.entries:
            self.assertEqual(set(entry["properties"]), set(properties))

    def test_sorted_and_used(self):
        codes = [entry["dtc"] for entry in self.entries]
        self.assertEqual(codes, sorted(codes))
        self.assertTrue(all(entry["used"] for entry in self.entries))


class DtcStatusMaskTests(SampleTestCase):
    def test_bits_are_in_iso_14229_order(self):
        mask = CddDtcParser(self.shared).parse_status_mask(self.ecu_doc)

        self.assertEqual(mask["bitLength"], 8)
        self.assertEqual([bit["bit"] for bit in mask["bits"]], list(range(8)))
        self.assertEqual(
            [bit["mask"] for bit in mask["bits"]],
            ["0x01", "0x02", "0x04", "0x08", "0x10", "0x20", "0x40", "0x80"],
        )
        self.assertEqual(mask["bits"][0]["name"], "Test failed")
        self.assertEqual(mask["bits"][7]["name"], "Warning indicator requested")

    def test_support_flags(self):
        """`conv` says whether the ECU implements each bit; the supported
        ones collapse into a single byte mask."""
        mask = CddDtcParser(self.shared).parse_status_mask(self.ecu_doc)

        self.assertEqual(mask["supportedMask"], "0x00")
        self.assertTrue(all(not bit["supported"] for bit in mask["bits"]))

    def test_absent_section_returns_none(self):
        empty = ET.fromstring("<ECUDOC></ECUDOC>")
        self.assertIsNone(CddDtcParser(self.shared).parse_status_mask(empty))


class StatesParserTests(SampleTestCase):
    def test_state_groups(self):
        groups = CddStatesParser(self.shared).parse(self.ecu_doc)

        # `spec` is the stable axis: group names are per-document.
        self.assertEqual([g["spec"] for g in groups], ["session", "security"])
        self.assertEqual([g["kind"] for g in groups], ["Session", "Security Access"])
        self.assertEqual(
            [s["name"] for s in groups[0]["states"]], ["Default", "Programming", "Extended"]
        )
        self.assertEqual([s["name"] for s in groups[1]["states"]], ["Locked", "Unlocked L1"])

    def test_absent_section_returns_empty(self):
        empty = ET.fromstring("<ECUDOC></ECUDOC>")
        self.assertEqual(CddStatesParser(self.shared).parse(empty), [])


class DiagnosticClassesParserTests(SampleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.entries = CddDiagnosticClassesParser(cls.shared).parse(cls.ecu_doc)
        cls.by_qual = {entry["qual"]: entry for entry in cls.entries}

    def test_every_template_is_listed_with_its_enabled_flag(self):
        """DCLTMPLS holds every class the document defines; a variant
        enables one by containing a DIAGCLASS/DIAGINST that points at it."""
        self.assertEqual(len(self.entries), 30)
        self.assertEqual(sum(e["enabled"] for e in self.entries), 19)
        # Both states occur, so the flag actually discriminates.
        self.assertTrue(any(not e["enabled"] for e in self.entries))

    def test_document_order_is_preserved(self):
        self.assertEqual(
            [e["name"] for e in self.entries[:4]],
            ["Sessions", "Ecu Reset", "Security Access", "Communication Control"],
        )

    def test_singleton_templates(self):
        """single='1' templates appear in the variant as a bare DIAGINST
        rather than a DIAGCLASS holding instances."""
        self.assertEqual(sum(e["singleton"] for e in self.entries), 11)
        self.assertTrue(self.by_qual["TesterPresent"]["singleton"])
        self.assertFalse(self.by_qual["Sessions"]["singleton"])

    def test_instance_counts(self):
        sessions = self.by_qual["Sessions"]

        self.assertTrue(sessions["variants"]["Base_Variant"])
        self.assertEqual(sessions["instanceCounts"]["Base_Variant"], 3)


class ServicesParserTests(SampleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.entries = CddServicesParser(cls.shared).parse(cls.ecu_doc)

    def test_session_instances_share_a_layout_but_not_a_sub_function(self):
        """All three sessions resolve the same PROTOCOLSERVICE; the byte
        that separates them comes from each instance's STATICVALUE."""
        sessions = [e for e in self.entries if e["classQual"] == "Sessions"]

        self.assertEqual(
            [(e["identifier"], e["name"]) for e in sessions],
            [
                ("0x01", "Default Session"),
                ("0x02", "Programming Session"),
                ("0x03", "Extended Diagnostic Session"),
            ],
        )
        self.assertEqual(
            [e["services"][0]["request"]["bytes"] for e in sessions],
            ["10 01", "10 02", "10 03"],
        )
        for entry in sessions:
            service = entry["services"][0]
            self.assertEqual(service["protocolService"], "($10) DiagnosticSessionControl")
            # The payload placeholder is generated at display time and is
            # not stored in the file, hence "..".
            self.assertEqual(
                service["positiveResponse"]["bytes"], f"50 {entry['identifier'][2:]} .."
            )
            self.assertEqual(service["negativeResponse"]["bytes"], "7F 10 rc")

    def test_telegram_byte_positions(self):
        entry = next(e for e in self.entries if e["name"] == "Default Session")

        self.assertEqual([t["name"] for t in entry["telegrams"]], ["SessionParameterRecord"])
        self.assertEqual(
            [(p["name"], p["byteNo"], p["bitLength"]) for p in entry["telegrams"][0]["parameters"]],
            # Two 16-bit parameters, so the second starts at byte 2.
            [("P2", 0, 16), ("P2Ex", 2, 16)],
        )

    def test_field_parameters_occupy_their_whole_width(self):
        """For qty="field" the CVALUETYPE bl is one *element*'s width, so a
        17-byte ASCII string stores bl=8 with minsz=maxsz=17. Reading bl
        alone would lay following parameters on top of it."""
        for entry in self.entries:
            for telegram in entry["telegrams"]:
                offset = 0
                for parameter in telegram["parameters"]:
                    self.assertEqual(parameter["byteNo"], offset // 8)
                    offset += parameter["bitLength"] or 0

    def test_multi_byte_identifier_is_split_into_bytes(self):
        entry = next(e for e in self.entries if e["identifier"] == "0xF180")

        self.assertEqual(entry["services"][0]["request"]["bytes"], "22 F1 80")

    def test_negative_response_carries_codes(self):
        entry = next(e for e in self.entries if e["name"] == "Default Session")
        payload = next(
            c
            for c in entry["services"][0]["negativeResponse"]["components"]
            if c["role"] == "Payload"
        )

        self.assertEqual(payload["dest"], "resCode")
        self.assertTrue(payload["responseCodes"])
        for code in payload["responseCodes"]:
            self.assertTrue(code["code"].startswith("0x"))

    def test_every_instance_resolves_its_references(self):
        """No dangling tmplref / shstaticref anywhere in the document."""
        self.assertEqual(len(self.entries), 37)
        for entry in self.entries:
            for service in entry["services"]:
                self.assertIsNotNone(service["protocolService"], entry["name"])
                self.assertIsNotNone(service["request"], entry["name"])
                for primitive in (
                    service["request"],
                    service["positiveResponse"],
                    service["negativeResponse"],
                ):
                    if primitive is None:
                        continue
                    for component in primitive["components"]:
                        if component["kind"] == "STATICCOMP":
                            self.assertIsNotNone(
                                component["value"], (entry["name"], component["name"])
                            )

    def test_singleton_instances_hang_off_the_variant(self):
        by_qual = {entry["qual"]: entry for entry in self.entries}

        self.assertIn("TesterPresent", by_qual)
        self.assertEqual(by_qual["TesterPresent"]["className"], "Tester Present")


class AttributesParserTests(SampleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.parser = CddAttributesParser(cls.shared)
        cls.interfaces = cls.parser.parse_interfaces(cls.ecu_doc)
        cls.by_qual = {i["qual"]: i for i in cls.interfaces}

    def test_interface_names_are_read_from_the_document(self):
        """Interface qualifiers are per-document, and several here do not
        start with "CAN." -- a hardcoded prefix would miss them."""
        self.assertEqual(
            [(i["qual"], i["enabled"]) for i in self.interfaces],
            [
                ("CAN", True),
                ("CAN_Extended_Addressing", False),
                ("FlexRay_ISO", False),
                ("FlexRay_Autosar2x", False),
                ("DoIP_ISO13400", False),
                ("CAN_FD", False),
                ("CAN_FD_Extended_Addressing", False),
            ],
        )

    def test_supported_interfaces_are_a_subset(self):
        supported = self.parser.parse_supported_interfaces(self.ecu_doc)

        self.assertEqual([i["qual"] for i in supported], ["CAN"])
        self.assertEqual(self.parser.active_interface(self.ecu_doc)["qual"], "CAN")

    def test_parameters_belong_to_their_interface(self):
        for interface in self.interfaces:
            for parameter in interface["parameters"]:
                self.assertEqual(parameter["interface"], interface["qual"])
                self.assertEqual(
                    parameter["qual"], f"{interface['qual']}.{parameter['parameter']}"
                )

    def test_value_text_renders_like_the_panel(self):
        by_parameter = {p["parameter"]: p for p in self.by_qual["CAN"]["parameters"]}

        self.assertEqual(by_parameter["ReqCanId"]["valueText"], "0x07AA")
        self.assertEqual(by_parameter["ResCanId"]["valueText"], "0x07AB")
        self.assertEqual(by_parameter["ReqCanId"]["display"], "Hexadecimal")
        self.assertEqual(by_parameter["P2Client"]["valueText"], "150")
        self.assertEqual(by_parameter["P2Client"]["display"], "Decimal")
        # Enums show their tag text and sort by id.
        self.assertEqual(by_parameter["AddrScheme"]["valueText"], "Normal")
        self.assertEqual(by_parameter["AddrScheme"]["display"], "Sort by ID")

    def test_default_and_overwritten_are_separate_columns(self):
        """The panel keeps "Default Value" and "Overwritten Value" apart, so
        an overridden parameter has to report both plus where it came from."""
        by_parameter = {p["parameter"]: p for p in self.by_qual["CAN"]["parameters"]}

        overridden = by_parameter["CANFrameFillerByte"]
        self.assertEqual(overridden["defaultText"], "0x00")
        self.assertEqual(overridden["valueText"], "0xCC")
        self.assertEqual(overridden["source"], "ecu")

        untouched = by_parameter["Baudrate"]
        self.assertEqual(untouched["valueText"], untouched["defaultText"])
        self.assertEqual(untouched["source"], "default")

    def test_an_overridden_enum_still_resolves_its_tag(self):
        """An override carries a raw number; the tag text still has to come
        from the definition's ETAGs."""
        by_parameter = {p["parameter"]: p for p in self.by_qual["CAN"]["parameters"]}
        handling = by_parameter["RC78Handling"]

        self.assertEqual(handling["source"], "ecu")
        self.assertEqual(handling["kind"], "enum")
        self.assertEqual(handling["defaultText"], "EnabledUnlimited")
        self.assertEqual(handling["valueText"], "Enabled")

    def test_ecu_overrides_are_the_exception(self):
        """Most parameters fall back to their definition's default, so a
        parser reading only the ECU's own UNS/ENUM/CSTR would miss nearly
        everything."""
        entries = self.parser.parse(self.ecu_doc)
        overridden = [e for e in entries if e["source"] != "default"]

        self.assertLess(len(overridden), len(entries) / 10)
        # Overrides land on the ECU, so every variant sees them.
        for entry in overridden:
            for variant in entry["variants"].values():
                self.assertEqual(variant["value"], entry["value"])

    def test_an_override_equal_to_the_default_still_reports_as_one(self):
        """Whether a value was overridden and whether it differs from the
        default are separate questions; the panel shows such a value in the
        Overwritten Value column either way."""
        entries = self.parser.parse(self.ecu_doc)
        restated = [
            e
            for e in entries
            if e["source"] == "ecu" and e["valueText"] == e["defaultText"]
        ]

        self.assertTrue(restated)
        for entry in restated:
            self.assertEqual(entry["source"], "ecu")

    def test_categories(self):
        categories = Counter(p["category"] for i in self.interfaces for p in i["parameters"])

        self.assertIn("Communication", categories)
        self.assertIn("Timing", categories)


class TesterTests(SampleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tester = CddTester(cls.shared)
        cls.attributes = CddAttributesParser(cls.shared)
        cls.by_qual = {i["qual"]: i for i in cls.attributes.parse_interfaces(cls.ecu_doc)}

    def test_bus_kind_from_the_parameter_set(self):
        """Interface names cannot be matched on, so the bus kind comes from
        which parameters the interface defines."""
        self.assertEqual(self.tester.detect_bus_kind(self.by_qual["CAN"]), "can")
        self.assertEqual(self.tester.detect_bus_kind(self.by_qual["DoIP_ISO13400"]), "eth")

    def test_uds_timing(self):
        interface = self.attributes.active_interface(self.ecu_doc)

        self.assertEqual(
            self.tester.build_uds_timing(interface),
            {"pTime": 150, "pExtTime": 2000, "s3Time": 4000, "testerPresentEnable": True},
        )

    def test_can_addresses(self):
        addresses = self.tester.build_can_addresses(self.by_qual["CAN"])

        self.assertEqual([a["canAddr"]["name"] for a in addresses], ["Physical", "Functional"])
        physical = addresses[0]["canAddr"]
        self.assertEqual(physical["canIdTx"], "0x7aa")
        self.assertEqual(physical["canIdRx"], "0x7ab")
        self.assertEqual(physical["idType"], "STANDARD")
        self.assertEqual(physical["addrFormat"], "NORMAL")
        self.assertEqual(physical["baudrate"], 500000)

    def test_addressing_scheme_is_not_assumed_normal(self):
        """The document defines both Normal and Extended addressing, so the
        scheme has to come from the AddrScheme enum's tag text."""
        normal = self.tester.build_can_addresses(self.by_qual["CAN"])[0]["canAddr"]
        extended = self.tester.build_can_addresses(
            self.by_qual["CAN_Extended_Addressing"]
        )[0]["canAddr"]

        self.assertEqual(normal["addrFormat"], "NORMAL")
        self.assertEqual(extended["addrFormat"], "EXTENDED")

    def test_can_fd_settings_come_from_the_document(self):
        """CanFd* parameters exist only on a CAN FD interface, so their
        absence is what identifies a classic CAN one."""
        classic = self.tester.build_can_addresses(self.by_qual["CAN"])[0]["canAddr"]
        self.assertEqual((classic["canfd"], classic["brs"], classic["dlc"]), (False, False, 8))
        self.assertNotIn("dataBaudrate", classic)

        can_fd = self.tester.build_can_addresses(self.by_qual["CAN_FD"])[0]["canAddr"]
        self.assertEqual((can_fd["canfd"], can_fd["brs"], can_fd["dlc"]), (True, True, 64))
        self.assertIn("dataBaudrate", can_fd)

    def test_start_bit_convention(self):
        """`startBit` is the CAN-tooling convention, which is not the same
        as the panel's Byte No. / Bit Pos. and only differs for big-endian."""
        # Motorola names the signal by its most significant bit.
        self.assertEqual(self.tester.start_bit(0, 16, "big_endian"), 7)
        self.assertEqual(self.tester.start_bit(16, 16, "big_endian"), 23)
        self.assertEqual(self.tester.start_bit(4, 4, "big_endian"), 7)
        # Intel names the least significant bit, which is the offset itself.
        self.assertEqual(self.tester.start_bit(0, 16, "little_endian"), 0)
        self.assertEqual(self.tester.start_bit(16, 16, "little_endian"), 16)

    def test_buffer_is_big_endian_bytes(self):
        self.assertEqual(self.tester.buffer(0xF180, 16)["data"], [0xF1, 0x80])
        self.assertEqual(self.tester.buffer(50, 16)["data"], [0, 50])
        self.assertEqual(self.tester.buffer(1, 8)["data"], [1])
        # An unset parameter still yields a correctly sized zeroed buffer.
        self.assertEqual(self.tester.buffer(None, 24)["data"], [0, 0, 0])

    def test_expanded_parameter_inlines_the_data_type(self):
        """A telegram parameter carries only a dataTypeQual; the tester
        layer denormalises the conversion facts onto it."""
        data_types = {
            e["qual"]: e for e in CddDataTypesParser(self.shared).parse(self.ecu_doc)
        }
        instance = next(
            e
            for e in CddServicesParser(self.shared).parse(self.ecu_doc)
            if e["name"] == "Default Session"
        )
        expanded = self.tester.expand_telegram(instance["telegrams"][0], data_types)
        p2_ex = expanded["parameters"][1]

        self.assertEqual(p2_ex["name"], "P2Ex")
        self.assertEqual(p2_ex["bitLength"], 16)
        self.assertEqual(p2_ex["byteOrder"], "big_endian")
        self.assertEqual(p2_ex["encoding"], "uns")
        self.assertEqual(p2_ex["unit"], "ms")
        # P2Ex is a linear conversion with a factor of 10.
        self.assertEqual(p2_ex["factor"], 10.0)
        self.assertEqual(p2_ex["offset"], 0.0)
        self.assertEqual(p2_ex["startBit"], 23)
        self.assertEqual(p2_ex["value"], {"type": "Buffer", "data": [0, 0]})

    def test_expanded_parameter_exposes_choices_and_bit_groups(self):
        data_types = {
            e["qual"]: e for e in CddDataTypesParser(self.shared).parse(self.ecu_doc)
        }

        text_table = self.tester.expand_parameter(
            {
                "name": "Id", "qual": "Id", "bitOffset": 0, "bitLength": 16,
                "dataTypeQual": "DataIdentifier", "constant": None, "default": None,
            },
            data_types,
        )
        self.assertTrue(text_table["choices"])

        # Communication_Type packs flags and a 2-bit gap into one byte.
        packed = self.tester.expand_parameter(
            {
                "name": "Type", "qual": "Type", "bitOffset": 0, "bitLength": 8,
                "dataTypeQual": "Communication_Type", "constant": None, "default": None,
            },
            data_types,
        )
        self.assertEqual(
            [g["name"] for g in packed["bitGroups"]],
            [
                "normalCommunicationMessages",
                "networkManagementCommunicationMessages",
                "communicationTypeNetworks",
            ],
        )
        # The gap is skipped but still advances the offset.
        self.assertEqual([g["bitOffset"] for g in packed["bitGroups"]], [0, 1, 4])

    def test_build_shape(self):
        tester = self.tester.build(self.ecu_doc)
        ecu = next(iter(tester.values()))
        variant = next(iter(ecu.values()))

        self.assertEqual(variant["type"], "can")
        self.assertEqual(variant["interface"], "CAN")
        self.assertEqual(len(variant["didList"]), 16)
        self.assertEqual(len(variant["dtcList"]), 4)
        # Services are indexed by the request's first byte.
        self.assertIn("0x10", variant["allServiceList"])
        for sid in variant["allServiceList"]:
            self.assertRegex(sid, r"^0x[0-9A-F]{2}$")


class ApiTests(unittest.TestCase):
    """The public API keeps the original release's names and envelope."""

    @classmethod
    def setUpClass(cls):
        if not SAMPLE.exists():
            raise unittest.SkipTest(f"{SAMPLE.name} is not checked out")

    def test_envelope_on_success(self):
        from cddtools import parse_dids

        result = parse_dids(str(SAMPLE))
        self.assertEqual(result["error"], 0)
        self.assertEqual(len(result["data"]), 16)

    def test_envelope_on_failure(self):
        from cddtools import parse_dids

        result = parse_dids(str(EXAMPLES / "does-not-exist.cdd"))
        self.assertEqual(result["error"], 1)
        self.assertIn("message", result)

    def test_all_entry_points_succeed(self):
        import cddtools

        for name in (
            "parse",
            "parse_attributes",
            "parse_datatypes",
            "parse_diagnostic_classes",
            "parse_dids",
            "parse_dtc_status_mask",
            "parse_dtcs",
            "parse_interfaces",
            "parse_services",
            "parse_states",
            "parse_supported_interfaces",
            "parse_tester_info",
            "load_file",
        ):
            with self.subTest(entry_point=name):
                result = getattr(cddtools, name)(str(SAMPLE))
                self.assertEqual(result["error"], 0, result.get("message"))

    def test_cli_writes_json(self):
        import json
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.json"
            completed = subprocess.run(
                [sys.executable, "-m", "cddtools", "parseDtcs", str(SAMPLE), str(out)],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["error"], 0)
            self.assertEqual(len(payload["data"]), 4)

    def test_cli_reports_version(self):
        """`--version` must report what the package declares, so the two
        cannot drift apart."""
        import subprocess

        import cddtools

        completed = subprocess.run(
            [sys.executable, "-m", "cddtools", "--version"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            completed.stdout.strip(), f"cddtools {cddtools.__version__}"
        )


if __name__ == "__main__":
    unittest.main()

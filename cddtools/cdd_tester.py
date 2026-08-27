import math
import uuid

try:
    from .cdd_attributes_parser import CddAttributesParser
    from .cdd_datatypes_parser import CddDataTypesParser
    from .cdd_did_parser import CddDidParser
    from .cdd_dtc_parser import CddDtcParser
    from .cdd_parser_shared import CddParserShared
    from .cdd_services_parser import CddServicesParser
except ImportError:
    from cdd_attributes_parser import CddAttributesParser
    from cdd_datatypes_parser import CddDataTypesParser
    from cdd_did_parser import CddDidParser
    from cdd_dtc_parser import CddDtcParser
    from cdd_parser_shared import CddParserShared
    from cdd_services_parser import CddServicesParser

BIG_ENDIAN = "big_endian"
LITTLE_ENDIAN = "little_endian"
BYTE_ORDERS = {"HighLow (Motorola)": BIG_ENDIAN, "LowHigh (Intel)": LITTLE_ENDIAN}

# Encoding label -> the short code a tester keys value conversion off.
ENCODINGS = {
    "Unsigned": "uns",
    "Signed": "sgn",
    "Unicode": "utf",
    "ASCII": "asc",
    "IEEE Float (double)": "dbl",
    "IEEE Float (single)": "flt",
    "BCD": "bcd",
}


# Communication parameter -> ISO-TP key in the emitted CAN address, with the
# fallback used when the document does not define the parameter.
ISOTP_PARAMETERS = (
    ("bs", ("Blocksize",), 0),
    ("stMin", ("StMin",), 10),
    ("nAs", ("TimeoutAs",), 1000),
    ("nAr", ("TimeoutAr",), 1000),
    ("nBs", ("TimeoutBs",), 1000),
    ("nCr", ("TimeoutCr",), 1000),
    ("nBr", ("TimeBr",), 0),
    ("nCs", ("TimeCs",), 0),
    ("maxWTF", ("MaxWTF", "MaxNumberOfWaitFrames", "Max_number_Wait_Frames"), 0),
)

# Parameters that identify what kind of bus an interface describes. Interface
# qualifiers are per-document ("CAN", "CAN_FD", "FlexRay_Autosar2x",
# "DoIP_ISO13400"...) so the bus kind has to be inferred from the parameter
# set rather than from the name.
CAN_MARKER_PARAMETERS = ("ReqCanId", "ResCanId", "CanIdType")
DOIP_MARKER_PREFIXES = ("CP_DoIP", "CP_P2Max", "CP_P6Max")

STANDARD_CAN_ID_MAX = 0x7FF

# `CanFdMaxDlc` tag text -> payload bytes. Classic CAN tops out at 8; CAN FD
# adds the larger sizes. Present only on CAN FD interfaces.
CAN_FD_MAX_DLC = {
    "CAN20": 8,
    "CANFD8": 8,
    "CANFD12": 12,
    "CANFD16": 16,
    "CANFD20": 20,
    "CANFD24": 24,
    "CANFD32": 32,
    "CANFD48": 48,
    "CANFD64": 64,
}
CLASSIC_CAN_DLC = 8


class CddTester:
    """Derives connection-oriented settings from the CDD.

    Everything here is an *interpretation* of the parsed data rather than
    a reproduction of it: CAN identifiers, ISO-TP parameters and UDS timing
    get reshaped into the form a tester needs to open a connection. Keys
    like canIdTx, pTime and nAs are this project's invention and do not
    exist in the CDD. The faithful view lives in CddAttributesParser.
    """

    def __init__(self, shared=None):
        self._shared = shared or CddParserShared()
        self._attributes = CddAttributesParser(self._shared)

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _by_parameter(interface):
        return {parameter["parameter"]: parameter for parameter in interface["parameters"]}

    @staticmethod
    def _number(parameters, names, default=None):
        """First of `names` that resolves to a number, else `default`."""
        if isinstance(names, str):
            names = (names,)
        for name in names:
            parameter = parameters.get(name)
            if parameter is None or parameter["value"] in (None, ""):
                continue
            try:
                return int(parameter["value"])
            except (TypeError, ValueError):
                continue
        return default

    def detect_bus_kind(self, interface):
        if interface is None:
            return "can"
        parameters = self._by_parameter(interface)
        if any(name in parameters for name in CAN_MARKER_PARAMETERS):
            return "can"
        if any(
            name.startswith(prefix)
            for name in parameters
            for prefix in DOIP_MARKER_PREFIXES
        ):
            return "eth"
        return "can"

    # -- timing --------------------------------------------------------------

    def build_uds_timing(self, interface):
        """P2 / P2* / S3 as a tester consumes them.

        Both the CAN and the DoIP parameter sets are checked, since the two
        spell the same concepts differently.
        """
        if interface is None:
            return {}
        parameters = self._by_parameter(interface)

        timing = {}
        p2 = self._number(parameters, ("P2Client", "CP_P2Max_Ecu", "CP_P2Max"))
        p2_star = self._number(parameters, ("P2ExClient", "CP_P2Star_Ecu", "CP_P2Star"))
        s3 = self._number(
            parameters,
            ("S3Client", "CP_TesterPresentTime", "CP_TesterPresentTime_Ecu"),
        )
        if p2 is not None:
            timing["pTime"] = p2
        if p2_star is not None:
            timing["pExtTime"] = p2_star
        if s3 is not None:
            timing["s3Time"] = s3
            timing["testerPresentEnable"] = s3 > 0
        return timing

    # -- addressing ----------------------------------------------------------

    def _address_defaults(self, parameters):
        defaults = {
            key: self._number(parameters, names, fallback)
            for key, names, fallback in ISOTP_PARAMETERS
        }
        defaults["paddingValue"] = hex(self._number(parameters, "CANFrameFillerByte", 0))
        defaults["padding"] = self._number(parameters, "FillerByteHandling", 1) != 0

        # CAN FD settings live only on CAN FD interfaces; a classic CAN
        # interface simply has no CanFd* parameters, which is what makes
        # their absence mean "classic CAN" rather than "unknown".
        can_fd = self._text(parameters, "CanFdHandling") == "Enabled"
        defaults["canfd"] = can_fd
        defaults["brs"] = can_fd and self._text(parameters, "CanFdBrsHandling") == "Enabled"
        defaults["dlc"] = (
            CAN_FD_MAX_DLC.get(self._text(parameters, "CanFdMaxDlc"), CLASSIC_CAN_DLC)
            if can_fd
            else CLASSIC_CAN_DLC
        )
        if can_fd:
            data_baudrate = self._number(parameters, "CanFdDataBaudrate")
            if data_baudrate is not None:
                defaults["dataBaudrate"] = data_baudrate
        baudrate = self._number(parameters, "Baudrate")
        if baudrate is not None:
            defaults["baudrate"] = baudrate

        # Diagnostics never uses CAN remote frames and the CDD has no
        # parameter for them, so this stays constant.
        defaults["remote"] = False
        defaults["AE"] = str(self._number(parameters, "AddressExtension", 0))
        return defaults

    @staticmethod
    def _text(parameters, name):
        """An enum parameter's tag text, e.g. AddrScheme -> "Mixed"."""
        parameter = parameters.get(name)
        return parameter.get("valueText") if parameter else None

    def _addr_format(self, parameters, name):
        """NORMAL / MIXED / EXTENDED, from the AddrScheme enum's tag text.

        The numeric value cannot be used: the enum tags are defined per
        document, so value 0 reads "Normal" in one file while another file
        gives a different tag the same number.
        """
        text = self._text(parameters, name)
        return text.upper() if text else "NORMAL"

    def _id_type(self, parameters, name, *can_ids):
        """STANDARD / EXTENDED from the CAN-ID Type enum.

        Same caveat as _addr_format: every sample document stores 0 here,
        but the tag reads "11-Bit" in two of them and "29-Bit" in the third.
        Falls back to the identifier's magnitude when the parameter is
        missing.
        """
        text = self._text(parameters, name)
        if text:
            return "EXTENDED" if "29" in text else "STANDARD"
        return (
            "EXTENDED"
            if any(i is not None and i > STANDARD_CAN_ID_MAX for i in can_ids)
            else "STANDARD"
        )

    def _address_entry(self, name, addr_type, tx_id, rx_id, id_type, addr_format, defaults):
        return {
            "type": "can",
            "canAddr": {
                "name": name,
                "addrFormat": addr_format,
                "addrType": addr_type,
                "SA": tx_id,
                "TA": rx_id,
                "canIdTx": tx_id,
                "canIdRx": rx_id,
                "idType": id_type,
                **defaults,
            },
        }

    def build_can_addresses(self, interface):
        if interface is None or self.detect_bus_kind(interface) != "can":
            return []

        parameters = self._by_parameter(interface)
        request_id = self._number(parameters, "ReqCanId")
        response_id = self._number(parameters, "ResCanId")
        functional_id = self._number(parameters, "ReqCanIdFunc")
        if request_id is None and response_id is None:
            return []

        defaults = self._address_defaults(parameters)
        addresses = [
            self._address_entry(
                "Physical",
                "PHYSICAL",
                hex(request_id) if request_id is not None else None,
                hex(response_id) if response_id is not None else None,
                self._id_type(parameters, "CanIdType", request_id, response_id),
                self._addr_format(parameters, "AddrScheme"),
                defaults,
            )
        ]
        if functional_id is not None:
            addresses.append(
                self._address_entry(
                    "Functional",
                    "FUNCTIONAL",
                    hex(functional_id),
                    hex(response_id) if response_id is not None else None,
                    self._id_type(parameters, "CanIdTypeFunc", functional_id),
                    self._addr_format(parameters, "AddrSchemeFunc"),
                    defaults,
                )
            )
        return addresses

    # -- parameter expansion -------------------------------------------------

    @staticmethod
    def start_bit(bit_offset, bit_length, byte_order):
        """CDD bit offset -> the start-bit convention CAN tooling uses.

        In Motorola (big-endian) order a signal is named by the bit it
        *starts* at, which is its most significant bit within the first
        byte; Intel order names the least significant bit, which is the
        offset itself. The panel's own Byte No. / Bit Pos. columns are a
        different convention and stay on the parser's output untouched.
        """
        if byte_order != BIG_ENDIAN or bit_length is None:
            return bit_offset
        return 8 * (bit_offset // 8) + min(7, (bit_offset % 8) + bit_length - 1)

    @staticmethod
    def buffer(value, bit_length):
        """A value as the byte array a tester puts on the wire."""
        byte_count = max(1, math.ceil((bit_length or 8) / 8))
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = 0
        return {
            "type": "Buffer",
            "data": [(number >> shift) & 0xFF for shift in range((byte_count - 1) * 8, -1, -8)],
        }

    @staticmethod
    def _choices(data_type):
        """{raw value: label} for a text table, as a tester would show it."""
        if not data_type or not data_type.get("textTable"):
            return None
        choices = {}
        for row in data_type["textTable"]:
            start = row.get("start")
            if start is None:
                continue
            try:
                choices[int(str(start), 16 if str(start).startswith("0x") else 10)] = row["text"]
            except ValueError:
                choices[start] = row["text"]
        return choices or None

    def _bit_groups(self, data_type, data_types):
        """A packet's bit-field members, flattened into one group list.

        A parameter whose data type packs several sub-values into a byte
        needs them individually to be encodable; `members` on the data type
        keeps them nested one level deeper.
        """
        if not data_type or not data_type.get("members"):
            return None
        groups = []
        offset = 0
        for member in data_type["members"]:
            children = member["members"] if member["type"] == "Struct" else [member]
            for child in children:
                if child["type"] == "Gap":
                    offset += child.get("bitLength") or 0
                    continue
                child_type = data_types.get(child.get("dtQual"))
                coded = (child_type or {}).get("codedValue") or {}
                bit_length = coded.get("bitLength")
                groups.append(
                    {
                        "name": child["name"],
                        "qual": child["qual"],
                        "bitOffset": offset,
                        "bitLength": bit_length,
                        "encoding": ENCODINGS.get(coded.get("encoding"), coded.get("encoding")),
                        "choices": self._choices(child_type),
                    }
                )
                offset += bit_length or 0
        return groups or None

    def expand_parameter(self, parameter, data_types):
        """A telegram parameter with its data type's detail inlined.

        The parser deliberately reports only the structure plus a
        `dataTypeQual`; a tester needs the conversion facts alongside each
        parameter to encode a request and decode a response, so they are
        denormalised here rather than in the parser.
        """
        data_type = data_types.get(parameter.get("dataTypeQual"))
        coded = (data_type or {}).get("codedValue") or {}
        physical = (data_type or {}).get("physicalValue") or {}
        linear = (data_type or {}).get("linear") or {}
        byte_order = BYTE_ORDERS.get(coded.get("byteOrder"), BIG_ENDIAN)
        bit_length = parameter.get("bitLength")

        # A constant pins the value; otherwise the default is the starting
        # point, and failing both the parameter starts out zeroed.
        raw = parameter.get("constant")
        if raw is None:
            raw = parameter.get("default")

        return {
            "name": parameter["name"],
            "qual": parameter["qual"],
            "bitOffset": parameter.get("bitOffset"),
            "startBit": self.start_bit(parameter.get("bitOffset") or 0, bit_length, byte_order),
            "bitLength": bit_length,
            "minBitLength": parameter.get("minBitLength"),
            "maxBitLength": parameter.get("maxBitLength"),
            "variableLength": parameter.get("variableLength"),
            "quantity": coded.get("quantity"),
            "byteOrder": byte_order,
            "encoding": ENCODINGS.get(coded.get("encoding"), coded.get("encoding")),
            "unit": physical.get("unit"),
            "factor": linear.get("factor", 1.0),
            "offset": linear.get("offset", 0.0),
            "minimum": coded.get("minSize"),
            "maximum": coded.get("maxSize"),
            "precision": physical.get("precision"),
            "choices": self._choices(data_type),
            "bitGroups": self._bit_groups(data_type, data_types),
            "constant": parameter.get("constant"),
            "default": parameter.get("default"),
            "value": self.buffer(raw, bit_length),
            "physicalValue": None if raw is None else raw,
            "dataType": parameter.get("dataType"),
            "dataTypeQual": parameter.get("dataTypeQual"),
        }

    def expand_telegram(self, telegram, data_types):
        return {
            **telegram,
            "parameters": [
                self.expand_parameter(parameter, data_types)
                for parameter in telegram["parameters"]
            ],
        }

    # -- assembly ------------------------------------------------------------

    def build(self, ecu_doc):
        """The main-compatible tester structure, one entry per variant."""
        ecu = self._shared.first_child(ecu_doc, "ECU")
        if ecu is None:
            return {}

        ecu_name = (
            self._shared.text_by_path(ecu, "QUAL")
            or self._shared.text_by_path(ecu, "NAME/TUV")
            or "CDD"
        )
        interface = self._attributes.active_interface(ecu_doc)
        did_list = CddDidParser(self._shared).parse(ecu_doc)
        dtc_list = CddDtcParser(self._shared).parse(ecu_doc)
        instances = CddServicesParser(self._shared).parse(ecu_doc)
        # Keyed by qualifier because that is what a telegram parameter
        # carries; resolving each data type once keeps expansion cheap.
        data_types = {
            entry["qual"]: entry for entry in CddDataTypesParser(self._shared).parse(ecu_doc)
        }

        variants = self._shared.direct_children(ecu, "VAR") or [ecu]
        result = {ecu_name: {}}
        for variant in variants:
            variant_qual = self._shared.qual(variant)
            service_map = {}
            for instance in instances:
                if instance["variant"] != variant_qual:
                    continue
                for service in instance["services"]:
                    request = service.get("request")
                    if not request or not request.get("bytes"):
                        continue
                    # The service id is the first byte of the request, which
                    # is the CONSTCOMP marked spec="sid".
                    sid = f"0x{request['bytes'].split()[0]}"
                    service_map.setdefault(sid, []).append(
                        {
                            "id": str(uuid.uuid5(uuid.NAMESPACE_OID, instance["id"] or "")),
                            "name": instance["name"],
                            "serviceId": sid,
                            "identifier": instance["identifier"],
                            "request": request,
                            "positiveResponse": service.get("positiveResponse"),
                            "negativeResponse": service.get("negativeResponse"),
                            "telegrams": [
                                self.expand_telegram(telegram, data_types)
                                for telegram in instance["telegrams"]
                            ],
                        }
                    )

            result[ecu_name][variant_qual or ecu_name] = {
                "id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{ecu_name}/{variant_qual}")),
                "name": variant_qual or ecu_name,
                "type": self.detect_bus_kind(interface),
                "interface": interface["qual"] if interface else None,
                "udsTime": self.build_uds_timing(interface),
                "seqList": [],
                "address": self.build_can_addresses(interface),
                "didList": did_list,
                "dtcList": dtc_list,
                "allServiceList": service_map,
            }
        return result

from .cdd_tester_parser import CddParse


def parse_tester_info(file_path, parse_resp=True):
    parser = CddParse()
    return parser.parse_tester_info(file_path)


def parse_dids(file_path):
    parser = CddParse()
    return parser.parse_dids(file_path)


def parse_dtcs(file_path):
    parser = CddParse()
    return parser.parse_dtcs(file_path)


def parse(file_path, parse_resp=False):
    return parse_tester_info(file_path, parse_resp=parse_resp)


def load_file(file_path, parse_resp=True):
    return parse_tester_info(file_path, parse_resp=parse_resp)

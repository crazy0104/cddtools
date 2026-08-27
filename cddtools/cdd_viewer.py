import json
import tkinter as tk
import xml.etree.ElementTree as ET
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    from .cdd_attributes_parser import CddAttributesParser
    from .cdd_datatypes_parser import CddDataTypesParser
    from .cdd_diagnostic_classes_parser import CddDiagnosticClassesParser
    from .cdd_did_parser import CddDidParser
    from .cdd_dtc_parser import CddDtcParser
    from .cdd_parser_shared import CddParserShared
    from .cdd_services_parser import CddServicesParser
    from .cdd_states_parser import CddStatesParser
except ImportError:
    from cdd_attributes_parser import CddAttributesParser
    from cdd_datatypes_parser import CddDataTypesParser
    from cdd_diagnostic_classes_parser import CddDiagnosticClassesParser
    from cdd_did_parser import CddDidParser
    from cdd_dtc_parser import CddDtcParser
    from cdd_parser_shared import CddParserShared
    from cdd_services_parser import CddServicesParser
    from cdd_states_parser import CddStatesParser


DEFAULT_CDD_PATH = Path(__file__).resolve().parents[1] / "examples" / "CddTools.cdd"

TAB_DIAG_CLASSES = "Diagnostic Classes"
TAB_SERVICES = "Supported Services"
TAB_DATA_TYPES = "Data Types"
TAB_DIDS = "DIDs"
TAB_DTCS = "DTCs"
TAB_INTERFACES = "Interfaces"
TAB_STATES = "States"
TAB_DTC_STATUS = "DTC Status"

# (column id, heading, width) per tab, in addition to the tree's #0 (name) column.
# The Diagnostic Classes tab gets one extra column per variant, appended at
# load time by _diag_class_columns() since the variant names are per-document.
TAB_COLUMNS = {
    TAB_DIAG_CLASSES: (
        ("qual", "Qual", 200),
        ("enabled", "Enabled", 70),
        ("singleton", "Singleton", 75),
        ("classKind", "Kind", 80),
    ),
    # The Supported Services tab is a tree (variant > class > instance > telegram
    # rows), so its columns are shared by rows of several different kinds.
    TAB_SERVICES: (
        ("detail", "Id / Bytes / Byte No.", 170),
        ("qual", "Qual", 190),
        ("dataType", "Data Type / Protocol Service", 300),
        ("extra", "Default / Constant", 150),
    ),
    TAB_DATA_TYPES: (
        ("qual", "Qual", 220),
        ("conversion", "Conversion", 140),
        ("bitLength", "Bit Length", 90),
        ("bitmask", "Bitmask", 90),
    ),
    TAB_DIDS: (
        ("qual", "Qual", 200),
        ("identifierHex", "Identifier", 90),
        ("used", "Used", 60),
        ("dataSummary", "DID Data", 360),
    ),
    # Mirrors the "Communication Parameter" panel column for column: the
    # tree holds one interface per top-level row with its parameters
    # underneath, rather than every attribute in the document.
    TAB_INTERFACES: (
        ("kind", "Type", 90),
        ("category", "Category", 120),
        ("display", "Display", 110),
        ("defaultText", "Default Value", 120),
        ("valueText", "Overwritten Value", 130),
        ("description", "Description", 420),
    ),
    TAB_STATES: (
        ("qual", "Qual", 200),
        ("kind", "Kind", 140),
        ("description", "Description", 420),
    ),
    TAB_DTC_STATUS: (
        ("mask", "Mask", 70),
        ("supported", "Supported", 90),
        ("support", "Definition", 180),
        ("qual", "Qual", 300),
    ),
    TAB_DTCS: (
        ("failureType", "Failure Type", 90),
        ("failureTypeText", "Failure Type Text", 220),
        ("used", "Used", 60),
        ("errorText", "Error Text", 360),
    ),
}

TAB_TREE_LABEL = {
    TAB_DIAG_CLASSES: "Class",
    TAB_SERVICES: "Variant / Class / Instance",
    TAB_DATA_TYPES: "Name",
    TAB_DIDS: "Name",
    TAB_DTCS: "DTC",
    TAB_INTERFACES: "Interface / Parameter",
    TAB_STATES: "State Group / State",
    TAB_DTC_STATUS: "Bit",
}


def load_ecu_doc(file_path):
    root = ET.parse(file_path).getroot()
    ecu_doc = root if root.tag == "ECUDOC" else root.find("ECUDOC")
    if ecu_doc is None:
        raise ValueError("ECUDOC not found")
    shared = CddParserShared()
    shared.build_id_index(ecu_doc)
    return shared, ecu_doc


def parse_tab(tab, shared, ecu_doc):
    if tab == TAB_INTERFACES:
        return CddAttributesParser(shared).parse_interfaces(ecu_doc)
    if tab == TAB_STATES:
        return CddStatesParser(shared).parse(ecu_doc)
    if tab == TAB_DTC_STATUS:
        mask = CddDtcParser(shared).parse_status_mask(ecu_doc)
        return mask["bits"] if mask else []
    if tab == TAB_DIAG_CLASSES:
        return CddDiagnosticClassesParser(shared).parse(ecu_doc)
    if tab == TAB_SERVICES:
        return CddServicesParser(shared).parse(ecu_doc)
    if tab == TAB_DATA_TYPES:
        return CddDataTypesParser(shared).parse(ecu_doc)
    if tab == TAB_DIDS:
        return CddDidParser(shared).parse(ecu_doc)
    return CddDtcParser(shared).parse(ecu_doc)


def service_tree_rows(entry):
    """Child rows of one diagnostic instance, as (text, values, data) triples.

    Flattens the instance's services (Request / Pos. Resp. / Neg. Resp. byte
    sequences) and its telegram tables into rows the Treeview can nest under
    the instance node.
    """
    rows = []
    for service in entry["services"]:
        service_row = (
            service["name"],
            ("", service["qual"] or "", service["protocolService"] or "", service["semantic"] or ""),
            service,
            [],
        )
        for key, label in (
            ("request", "Request"),
            ("positiveResponse", "Pos. Resp."),
            ("negativeResponse", "Neg. Resp."),
        ):
            primitive = service.get(key)
            if primitive:
                service_row[3].append(
                    (label, (primitive["bytes"], primitive["qual"] or "", primitive["name"] or "", ""), primitive, [])
                )
        rows.append(service_row)

    for telegram in entry["telegrams"]:
        telegram_row = (telegram["name"], ("", telegram["qual"] or "", "", ""), telegram, [])
        for param in telegram["parameters"]:
            bit = "" if param["bitPos"] is None else f".{param['bitPos']}"
            extra = " / ".join(part for part in (param["default"], param["constant"]) if part)
            telegram_row[3].append(
                (
                    param["name"],
                    (f"{param['byteNo']}{bit}", param["qual"] or "", param["dataType"] or "", extra),
                    param,
                    [],
                )
            )
        rows.append(telegram_row)
    return rows


def variant_quals(entries):
    """Variant qualifiers a Diagnostic Classes result is reported against."""
    return list(entries[0]["variants"]) if entries else []


def interface_parameter_rows(interface):
    """One row per communication parameter, as the panel lists them."""
    rows = []
    for parameter in interface["parameters"]:
        # "Overwritten Value" stays blank unless something below the
        # definition actually set it, which is how the panel reads.
        overwritten = parameter["valueText"] if parameter["source"] != "default" else ""
        rows.append(
            (
                parameter["parameter"],
                (
                    parameter["kind"],
                    parameter["category"] or "",
                    parameter["display"] or "",
                    parameter["defaultText"] or "",
                    overwritten or "",
                    parameter["description"] or "",
                ),
                parameter,
                [],
            )
        )
    return rows


def state_rows(group):
    """The states of one group, as child rows."""
    return [
        (state["name"], (state["qual"], "", state["description"] or ""), state, [])
        for state in group["states"]
    ]


def row_for_entry(tab, entry, extra_columns=()):
    if tab == TAB_STATES:
        return f"{entry['name']} ({len(entry['states'])})", (
            entry["qual"],
            entry["kind"] or "",
            entry["description"] or "",
        )
    if tab == TAB_DTC_STATUS:
        return f"bit {entry['bit']}  {entry['name']}", (
            entry["mask"],
            "✓" if entry["supported"] else "",
            entry["support"] or "",
            entry["qual"],
        )
    if tab == TAB_INTERFACES:
        overridden = sum(1 for p in entry["parameters"] if p["source"] != "default")
        # Every interface the template offers is listed; the tick marks the
        # ones this ECU declares support for.
        return f"{'✓' if entry['enabled'] else '  '} {entry['name']}", (
            "Interface",
            "",
            "",
            f"{len(entry['parameters'])} parameter(s)",
            f"{overridden} overwritten" if overridden else "",
            entry["qual"],
        )
    if tab == TAB_SERVICES:
        text = f"[{entry['variant']}] {entry['className']} / {entry['name']}"
        service = entry["services"][0] if entry["services"] else None
        return text, (
            entry["identifier"] or "",
            entry["qual"],
            service["protocolService"] if service else "",
            "",
        )
    if tab == TAB_DIAG_CLASSES:
        text = entry["name"]
        values = (
            entry["qual"],
            "yes" if entry["enabled"] else "no",
            "yes" if entry["singleton"] else "no",
            entry["classKind"] or "",
        ) + tuple("yes" if entry["variants"].get(qual) else "-" for qual in extra_columns)
    elif tab == TAB_DATA_TYPES:
        text = entry["name"]
        values = (entry["qual"], entry["conversion"], entry["bitLength"], entry["bitmask"] or "")
    elif tab == TAB_DIDS:
        text = entry["name"]
        values = (entry["qual"], entry["identifierHex"], "yes" if entry["used"] else "no", entry["dataSummary"])
    else:
        text = entry["dtc"]
        values = (
            entry["failureType"] or "",
            entry["failureTypeText"] or "",
            "yes" if entry["used"] else "no",
            entry["errorText"],
        )
    return text, values


class CddViewer(tk.Tk):
    """Read-only viewer for the Diagnostic Classes / Data Types / DIDs /
    DTCs panels of a .cdd file. No editing: the tree is populated once per
    tab and the detail pane is a disabled Text widget. Each tab has its own
    "Export <tab> as JSON..." button to save that tab's parsed entries."""

    # Interfaces first: it is the cheapest tab to parse, so the window
    # comes up without waiting on a large Data Types section.
    TABS = (
        TAB_INTERFACES,
        TAB_DIAG_CLASSES,
        TAB_SERVICES,
        TAB_DATA_TYPES,
        TAB_DIDS,
        TAB_DTCS,
        TAB_DTC_STATUS,
        TAB_STATES,
    )

    def __init__(self):
        super().__init__()
        self.title("CDD Viewer (read-only)")
        self.geometry("1200x720")
        self.minsize(900, 560)

        self._shared = None
        self._ecu_doc = None
        self._current_path = None
        self._entries = {tab: [] for tab in self.TABS}
        self._loaded = {tab: False for tab in self.TABS}
        self._node_data = {tab: {} for tab in self.TABS}
        self._trees = {}

        self._build_ui()
        self.load_cdd(DEFAULT_CDD_PATH, show_error=False)

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self, padding=(10, 8))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(1, weight=1)

        ttk.Button(toolbar, text="Open CDD", command=self.open_cdd).grid(row=0, column=0, padx=(0, 8))
        self.file_var = tk.StringVar(value="No CDD loaded")
        ttk.Label(toolbar, textvariable=self.file_var).grid(row=0, column=1, sticky="w")

        content = ttk.PanedWindow(self, orient="horizontal")
        content.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 8))

        self.notebook = ttk.Notebook(content)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        for tab in self.TABS:
            frame = ttk.Frame(self.notebook)
            frame.columnconfigure(0, weight=1)
            frame.rowconfigure(0, weight=1)

            columns = TAB_COLUMNS[tab]
            tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show="tree headings")
            tree.heading("#0", text=TAB_TREE_LABEL[tab])
            tree.column("#0", width=260, minwidth=160, stretch=False)
            for col_id, heading, width in columns:
                tree.heading(col_id, text=heading)
                tree.column(col_id, width=width, minwidth=60, stretch=False)
            tree.grid(row=0, column=0, sticky="nsew")

            v_scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
            v_scroll.grid(row=0, column=1, sticky="ns")
            h_scroll = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
            h_scroll.grid(row=1, column=0, sticky="ew")
            tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
            tree.bind("<<TreeviewSelect>>", lambda _event, t=tab: self.show_selected_detail(t))

            tab_toolbar = ttk.Frame(frame, padding=(0, 6, 0, 0))
            tab_toolbar.grid(row=2, column=0, columnspan=2, sticky="ew")
            ttk.Button(
                tab_toolbar,
                text=f"Export {tab} as JSON...",
                command=lambda t=tab: self.export_tab(t),
            ).grid(row=0, column=0, sticky="w")

            self.notebook.add(frame, text=tab)
            self._trees[tab] = tree

        content.add(self.notebook, weight=3)

        detail_frame = ttk.Frame(content)
        detail_frame.columnconfigure(0, weight=1)
        detail_frame.rowconfigure(0, weight=1)
        self.detail = tk.Text(detail_frame, wrap="none", height=10, state="disabled")
        self.detail.grid(row=0, column=0, sticky="nsew")
        detail_v_scroll = ttk.Scrollbar(detail_frame, orient="vertical", command=self.detail.yview)
        detail_v_scroll.grid(row=0, column=1, sticky="ns")
        detail_h_scroll = ttk.Scrollbar(detail_frame, orient="horizontal", command=self.detail.xview)
        detail_h_scroll.grid(row=1, column=0, sticky="ew")
        self.detail.configure(yscrollcommand=detail_v_scroll.set, xscrollcommand=detail_h_scroll.set)

        content.add(detail_frame, weight=2)

        self.status_var = tk.StringVar(value="Open a CDD file to load its Data Types / DIDs / DTCs.")
        ttk.Label(self, textvariable=self.status_var, padding=(10, 0, 10, 8)).grid(row=2, column=0, sticky="ew")

    def _current_tab(self):
        return self.notebook.tab(self.notebook.select(), "text")

    def open_cdd(self):
        file_name = filedialog.askopenfilename(
            title="Open CDD file",
            initialdir=str(DEFAULT_CDD_PATH.parent),
            filetypes=[("CDD files", "*.cdd"), ("All files", "*.*")],
        )
        if not file_name:
            return
        self.load_cdd(Path(file_name))

    def load_cdd(self, file_path, show_error=True):
        file_path = Path(file_path)
        if not file_path.exists():
            self.status_var.set(f"File not found: {file_path}")
            return

        try:
            shared, ecu_doc = load_ecu_doc(file_path)
        except Exception as exc:
            if show_error:
                messagebox.showerror("Load failed", str(exc))
            self.status_var.set(f"Load failed: {exc}")
            return

        self._shared = shared
        self._ecu_doc = ecu_doc
        self._current_path = file_path
        self.file_var.set(str(file_path))

        self._entries = {tab: [] for tab in self.TABS}
        self._loaded = {tab: False for tab in self.TABS}
        self._node_data = {tab: {} for tab in self.TABS}
        for tree in self._trees.values():
            tree.delete(*tree.get_children())
        self.detail.configure(state="normal")
        self.detail.delete("1.0", tk.END)
        self.detail.configure(state="disabled")

        self._populate_tab(self._current_tab())

    def _on_tab_changed(self, _event=None):
        self._populate_tab(self._current_tab())

    def _apply_variant_columns(self, tree, tab, entries):
        """Diagnostic Classes gets one 'ticked in this variant?' column per
        variant. Variant names differ per document, so the columns can only
        be built once the entries are parsed."""
        if tab != TAB_DIAG_CLASSES:
            return ()

        quals = variant_quals(entries)
        base = TAB_COLUMNS[tab]
        tree.configure(columns=[col[0] for col in base] + list(quals))
        for col_id, heading, width in base:
            tree.heading(col_id, text=heading)
            tree.column(col_id, width=width, minwidth=60, stretch=False)
        for qual in quals:
            tree.heading(qual, text=qual)
            tree.column(qual, width=max(90, 9 * len(qual)), minwidth=70, stretch=False)
        return quals

    def _insert_child_rows(self, tree, parent, rows, node_data):
        for text, values, data, children in rows:
            node_id = tree.insert(parent, "end", text=text, values=values, open=False)
            node_data[node_id] = data
            if children:
                self._insert_child_rows(tree, node_id, children, node_data)

    def _populate_tab(self, tab):
        if self._ecu_doc is None or self._loaded.get(tab):
            return

        try:
            entries = parse_tab(tab, self._shared, self._ecu_doc)
        except Exception as exc:
            messagebox.showerror("Parse failed", str(exc))
            return

        tree = self._trees[tab]
        extra_columns = self._apply_variant_columns(tree, tab, entries)
        node_data = {}
        for entry in entries:
            text, values = row_for_entry(tab, entry, extra_columns)
            node_id = tree.insert("", "end", text=text, values=values, open=False)
            node_data[node_id] = entry
            if tab == TAB_SERVICES:
                self._insert_child_rows(tree, node_id, service_tree_rows(entry), node_data)
            elif tab == TAB_INTERFACES:
                self._insert_child_rows(tree, node_id, interface_parameter_rows(entry), node_data)
            elif tab == TAB_STATES:
                self._insert_child_rows(tree, node_id, state_rows(entry), node_data)

        self._entries[tab] = entries
        self._node_data[tab] = node_data
        self._loaded[tab] = True
        self.status_var.set(f"{tab}: {len(entries)} entrie(s) loaded.")

    def show_selected_detail(self, tab):
        selected = self._trees[tab].selection()
        self.detail.configure(state="normal")
        self.detail.delete("1.0", tk.END)
        if selected:
            data = self._node_data[tab].get(selected[0], {})
            self.detail.insert("1.0", json.dumps(data, indent=2, ensure_ascii=False))
        self.detail.configure(state="disabled")

    def export_tab(self, tab):
        if self._ecu_doc is None:
            messagebox.showinfo("Export JSON", "Open a CDD file first.")
            return

        self._populate_tab(tab)
        entries = self._entries.get(tab, [])

        default_name = f"{self._current_path.stem}_{tab.lower().replace(' ', '_')}.json"
        file_name = filedialog.asksaveasfilename(
            title=f"Export {tab} as JSON",
            initialdir=str(self._current_path.parent),
            initialfile=default_name,
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not file_name:
            return

        Path(file_name).write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
        self.status_var.set(f"Exported {len(entries)} {tab} entrie(s) to {file_name}")


def main():
    app = CddViewer()
    app.mainloop()


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
Standalone regression harness for the RCC BOQ XLSX writer.

Extracts the dependency-free XLSX/formwork/quantity functions straight
from the production code (the lib/ engine modules first, then the
pushbutton script.py - so tests always run against the real code where
it currently lives), builds a sample workbook including quantity takeoff
columns, totals rows and the BOQ Summary sheet, then unzips the result
and XML-validates every part. Run with any Python 3.x:
python test_xlsx_writer.py
"""

import io
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from xml.dom import minidom

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_PATH = os.path.join(
    REPO_DIR,
    "Nudge.extension",
    "Nudge.tab",
    "Generate.panel",
    "BOQ.pushbutton",
    "script.py"
)
UI_PATH = os.path.join(
    REPO_DIR,
    "Nudge.extension",
    "Nudge.tab",
    "Generate.panel",
    "BOQ.pushbutton",
    "ui.xaml"
)

# Engine modules under the extension lib/ folder (v1.8.6 module split,
# PROJECT_STRUCTURE.md section 9). Functions are resolved from these
# first; script.py stays as the fallback so the harness is green before,
# during and after the incremental split.
ENGINE_MODULES = [
    os.path.join(REPO_DIR, "Nudge.extension", "lib", "settings_engine.py"),
    os.path.join(REPO_DIR, "Nudge.extension", "lib", "quantity_engine.py"),
    os.path.join(REPO_DIR, "Nudge.extension", "lib", "formwork_engine.py"),
    os.path.join(REPO_DIR, "Nudge.extension", "lib", "rebar_engine.py"),
    os.path.join(REPO_DIR, "Nudge.extension", "lib", "assembly_engine.py"),
    os.path.join(REPO_DIR, "Nudge.extension", "lib", "costing_engine.py"),
    os.path.join(REPO_DIR, "Nudge.extension", "lib", "export_engine.py"),
    os.path.join(REPO_DIR, "Nudge.extension", "lib", "rule_engine.py"),
    # Appended last on purpose: export_engine.py carries its own
    # behaviorally identical safe_text, and resolving that name from
    # where it already resolved keeps this split behavior-neutral.
    os.path.join(REPO_DIR, "Nudge.extension", "lib", "parameter_engine.py"),
]

# The exec'd write_basic_xlsx does a call-time
# `from costing_engine import build_costing_sheet` (anti-cyclical import,
# same mechanism pyRevit uses with the extension lib on sys.path), so the
# lib folder must be importable while the harness runs.
LIB_DIR = os.path.join(REPO_DIR, "Nudge.extension", "lib")

FUNCTION_NAMES = [
    # Pure cell/XML primitives
    "safe_text",
    "xlsx_column_name",
    "xlsx_sheet_reference",
    "xlsx_inline_string",
    "try_export_as_number",
    "xlsx_cell",
    "xlsx_formula_cell",
    # Classic workbook parts
    "build_xlsx_sheet_xml",
    "build_xlsx_sheet_xml_site",
    "build_xlsx_styles_xml",
    "build_xlsx_workbook_xml",
    "build_xlsx_workbook_rels_xml",
    "build_xlsx_root_rels_xml",
    "build_xlsx_content_types_xml",
    "build_parameter_metadata_sheet",
    "build_missing_values_summary",
    "build_costing_sheet",
    "build_level_summary_table",
    "normalize_concrete_grade",
    "build_grade_summary_table",
    "sanitize_file_name",
    "build_default_output_name",
    "build_summary_cover_rows",
    "_publish_temp_workbook",
    "write_basic_xlsx",
    "get_parameters",
    "read_metric_parameter",
    "build_element_parameter_context",
    "find_parameter_in_context",
    # Site-format (v1.4.x) builders - pure, Revit-free
    "meters_to_millimeters",
    "build_section_description",
    "resolve_element_dimensions",
    "compute_shuttering_area",
    "_safe_factor",
    "normalize_formwork_rules",
    "get_formwork_factor",
    "is_formwork_enabled",
    "build_shuttering_formula",
    "_positive_number",
    "rebar_unit_weight_kg_per_m",
    "build_rebar_quantity_values",
    "_rebar_number",
    "_rounded_total",
    "normalize_rebar_dimension_mm",
    "build_rebar_bbs_table",
    "build_rebar_diameter_summary_table",
    "normalize_assembly_profile",
    "_assembly_sum",
    "build_structural_assembly_table",
    "_site_sort_key",
    "_sort_site_rows",
    "_site_cell_value",
    "_site_numeric",
    "_site_dim_value",
    "_site_desc_text",
    "build_site_detail_sheet",
    "build_site_summary_sheet",
    "build_site_tabular_sheet",
    "write_site_xlsx",
    "_finish_site_sheet",
    "enforce_uniform_grid_borders",
]


def extract_function_source(source, name):
    """Pull one top-level def block out of the script source."""
    pattern = re.compile(
        r"^def {0}\(.*?(?=^def |\Z)".format(name),
        re.S | re.M
    )

    match = pattern.search(source)

    if not match:
        raise AssertionError(
            "Could not extract function: {}".format(name)
        )

    return match.group(0)


def load_source_texts():
    """Read every existing source file (engine modules, then script.py)."""
    texts = []
    for path in ENGINE_MODULES + [SCRIPT_PATH]:
        if os.path.isfile(path):
            with io.open(path, "r", encoding="utf-8-sig") as handle:
                texts.append((path, handle.read()))
    if not texts:
        raise AssertionError("No source files found to extract from")
    return texts


def extract_from_sources(texts, name):
    """Pull one top-level def block from the engine modules or script.py."""
    searched = []
    for path, source in texts:
        try:
            return extract_function_source(source, name), path
        except AssertionError:
            searched.append(os.path.basename(path))
    raise AssertionError(
        "Could not extract function: {} (searched: {})".format(
            name, ", ".join(searched))
    )


def extract_constant_from_sources(texts, name):
    """Pull one top-level single-line constant assignment by name."""
    pattern = re.compile(r"^{0} = .*$".format(name), re.M)
    searched = []
    for path, source in texts:
        match = pattern.search(source)
        if match:
            return match.group(0), path
        searched.append(os.path.basename(path))
    raise AssertionError(
        "Could not extract constant: {} (searched: {})".format(
            name, ", ".join(searched))
    )


def main():
    failures = []

    def check(condition, message):
        if condition:
            print("PASS: {}".format(message))
        else:
            failures.append(message)
            print("FAIL: {}".format(message))

    # source texts: engine modules first, script.py as fallback.
    if LIB_DIR not in sys.path:
        sys.path.insert(0, LIB_DIR)
    texts = load_source_texts()
    for path, _ in texts:
        print("Source: {}".format(os.path.relpath(path, REPO_DIR)))

    CONSTANT_LINES = ['STYLE_DEFAULT = 0', 'STYLE_HEADER = 1', 'STYLE_NUMBER = 2', 'STYLE_TOTAL_TEXT = 3', 'STYLE_TOTAL_NUMBER = 4', 'STYLE_SITE_TITLE = 5', 'STYLE_SITE_META = 6', 'STYLE_SITE_SUBTITLE = 7', 'STYLE_SITE_BAND = 8', 'STYLE_SITE_SUBBAND = 9', 'STYLE_SITE_NUM = 10', 'STYLE_SITE_MM = 11', 'STYLE_SITE_TOTAL_NUM = 12', 'STYLE_SITE_TOTAL_TEXT = 13', 'STYLE_SITE_PLAIN = 14', 'SITE_CATEGORY_ORDER = ("Beam", "Column", "Structure Wall", "Slab", "Foundation", "Rebar")', 'SITE_DETAIL_BAND_ROWS = (5, 6)', 'SITE_DETAIL_DATA_START_ROW = 7', 'SITE_DETAIL_COLUMN_WIDTHS = [6, 30, 8, 8, 8, 12, 14, 14]', 'DEFAULT_FORMWORK_RULES = {"enabled": True, "deduction_pct": {"Column": 0.0, "Beam": 0.0, "Structure Wall": 0.0, "Slab": 0.0, "Foundation": 0.0}}', 'formwork_rules = {"enabled": DEFAULT_FORMWORK_RULES["enabled"], "deduction_pct": dict(DEFAULT_FORMWORK_RULES["deduction_pct"])}']
    CONSTANT_LINES.append('DEFAULT_ASSEMBLY_PROFILE = {"id": "global-custom", "name": "Global / Custom", "edition": "1.0.0", "source": "Project specification / applicable local SOR", "binding_wire_factor": None, "cover_block_factor": None, "labour_factor": None}')

    import time

    namespace = {
        "os": os,
        "re": re,
        "zipfile": zipfile,
        "time": time,
    }

    # Auto-injected module constants the site builders rely on.
    for _const_line in CONSTANT_LINES:
        exec(_const_line, namespace)

    from xml.sax.saxutils import escape as xml_escape
    namespace["xml_escape"] = xml_escape
    from collections import OrderedDict
    namespace["OrderedDict"] = OrderedDict

    source_tally = {}
    for name in FUNCTION_NAMES:
        block, from_path = extract_from_sources(texts, name)
        exec(block, namespace)
        source_tally[os.path.basename(from_path)] = \
            source_tally.get(os.path.basename(from_path), 0) + 1

    # Site-format module constants (v1.4.0): simple single-line
    # assignments pulled straight from the production source so the
    # extracted builders always see the real layout contract.
    for constant_name in (
        "SITE_CATEGORY_ORDER",
        "SITE_DETAIL_BAND_ROWS",
        "SITE_DETAIL_DATA_START_ROW",
        "SITE_DETAIL_COLUMN_WIDTHS",
        "CONCRETE_GRADE_VALUES",
        "SITE_ITEMS_SHEET_NAME"
    ):
        constant_line, _ = extract_constant_from_sources(texts, constant_name)
        exec(constant_line, namespace)

    for path, style_source in texts:
        for style_match in re.finditer(
                r"^STYLE_[A-Z_]+ = \d+$",
                style_source,
                re.M):
            exec(style_match.group(0), namespace)

    print("Extracted {} functions from: {}".format(
        len(FUNCTION_NAMES),
        ", ".join(
            "{} x{}".format(fname, count)
            for fname, count in sorted(source_tally.items()))
    ))

    class BrokenInteropFloat(object):
        def __float__(self):
            raise SystemError("simulated interop null")

    interop_profile = namespace["normalize_assembly_profile"]({
        "binding_wire_factor": BrokenInteropFloat(),
        "cover_block_factor": None,
        "labour_factor": None,
    })
    check(
        interop_profile["binding_wire_factor"] is None
        and interop_profile["cover_block_factor"] is None
        and interop_profile["labour_factor"] is None,
        "Assembly profile treats CPython/.NET null coercion failures as missing factors"
    )

    retry_root = tempfile.mkdtemp(prefix="rcc-boq-publish-")
    real_os = namespace["os"]
    publish_temp = os.path.join(retry_root, "workbook.xlsx.tmp")
    publish_target = os.path.join(retry_root, "workbook.xlsx")

    class TransientRenameOs(object):
        def __init__(self):
            self.path = real_os.path
            self.rename_calls = 0

        def __getattr__(self, name):
            return getattr(real_os, name)

        def rename(self, source, destination):
            self.rename_calls += 1
            if self.rename_calls < 3:
                raise OSError(13, "simulated Windows file lock")
            return real_os.rename(source, destination)

    rename_proxy = TransientRenameOs()
    published_after_retry = False
    try:
        with io.open(publish_temp, "wb") as test_workbook:
            test_workbook.write(b"validated workbook")
        namespace["os"] = rename_proxy
        namespace["_publish_temp_workbook"](
            publish_temp, publish_target, attempts=3, delay_seconds=0)
        with io.open(publish_target, "rb") as published_workbook:
            published_after_retry = published_workbook.read() == b"validated workbook"
    finally:
        namespace["os"] = real_os
        shutil.rmtree(retry_root, ignore_errors=True)
    check(
        published_after_retry and rename_proxy.rename_calls == 3,
        "Validated workbook publish retries transient Windows file locks"
    )

    check(
        namespace["xlsx_sheet_reference"]("Beam") == "Beam"
        and namespace["xlsx_sheet_reference"]("Structure Wall")
        == "'Structure Wall'",
        "Excel sheet references quote names containing spaces"
    )

    data_result = {
        "Beam": [
            {
                "Element ID": "100",
                "Level": "Ground Floor",
                "Grade": "M25",
                "Mark": "B1",
                "Concrete Volume": "",
                "Rate": 1200.0,
                "Qty: Volume (m3)": 0.2832,
                "Qty: Area (m2)": "",
                "Qty: Length (m)": 3.048,
                "Qty: Count": 1
            },
            {
                "Element ID": "101",
                "Level": "First Floor",
                "Grade": "M30",
                "Mark": "B2",
                "Concrete Volume": "",
                "Rate": 1200.0,
                "Qty: Volume (m3)": 0.567,
                "Qty: Area (m2)": "",
                "Qty: Length (m)": 6.096,
                "Qty: Count": 1
            }
        ],
        "Column": [
            {
                "Element ID": "200",
                "Level": "Ground Floor",
                "Grade": "M30",
                "Mark": "C1",
                "Rate": 1500.0,
                "Qty: Volume (m3)": 0.42,
                "Qty: Area (m2)": 0.16,
                "Qty: Length (m)": 3.5,
                "Qty: Height (m)": 3.5,
                "Qty: Count": 1
            }
        ],
        "Structure Wall": [
            {
                "Element ID": "250",
                "Level": "Ground Floor",
                "Grade": "M25",
                "Mark": "SW1",
                "Rate": 1350.0,
                "Qty: Volume (m3)": 2.0,
                "Qty: Area (m2)": 10.0,
                "Qty: Length (m)": 4.0,
                "Qty: Height (m)": 2.5,
                "Qty: Thickness (m)": 0.2,
                "Qty: Count": 1
            }
        ],
        "Slab": [],
        "Foundation": [
            {
                "Element ID": "300",
                "Level": "(No Level)",
                "Grade": "",
                "Mark": "F1",
                "Rate": 1800.0,
                "Qty: Volume (m3)": 1.85,
                "Qty: Area (m2)": 9.3,
                "Qty: Length (m)": "",
                "Qty: Thickness (m)": 0.3,
                "Qty: Count": 1
            }
        ],
        "Rebar": [
            {
                "Element ID": "400",
                "Level": "Ground Floor",
                "Mark": "R1",
                "Rate": 72.0,
                "Rebar: Bar Mark": "R1",
                "Rebar: Diameter (mm)": 12.0,
                "Rebar: Shape": "M_00",
                "Rebar: Quantity": 4,
                "Rebar: Bar Length (m)": 3.0,
                "Rebar: Cutting Length (m)": 3.0,
                "Rebar: Total Length (m)": 12.0,
                "Rebar: Unit Weight (kg/m)": 0.8889,
                "Rebar: Total Weight (kg)": 10.667,
                "Rebar: Host Element ID": "200",
                "Rebar: Host Category": "Structural Columns",
                "Rebar: A (mm)": 3000.0,
                "Rebar: Bend Diameter (mm)": 48.0,
                "Rebar: Hook at Start": "",
                "Rebar: Hook at End": ""
            }
        ]
    }

    parameter_metadata = {
        "Beam": [
            {"Parameter Name": "Mark"},
            {"Parameter Name": "Concrete Volume"}
        ]
    }

    output_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "_boq_writer_test.xlsx"
    )
    validation_report_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "_boq_validation_test.json"
    )

    sheet_rows = namespace["write_basic_xlsx"](
        output_path,
        data_result,
        parameter_metadata,
        project_name="CHHANYADO HOSPITAL SURAT",
        tool_version="RCC BOQ Parameter Manager v1.4.0",
        generated_stamp="2026-08-26 10:00",
        validation_report_path=validation_report_path
    )

    try:

        check(
            "BOQ Summary" in sheet_rows,
            "BOQ Summary sheet was generated"
        )

        with io.open(validation_report_path, "r", encoding="utf-8") as report_file:
            validation_report = json.load(report_file)
        check(
            validation_report.get("schema")
            == "rcc-boq-export-validation/1.0.0"
            and validation_report.get("ok") is True
            and validation_report.get("mismatch_count") == 0
            and validation_report.get("expected_cell_count")
            == validation_report.get("actual_cell_count")
            and len(validation_report.get("workbook_sha256", "")) == 64,
            "Canonical validator rereads every generated Classic XLSX cell"
        )

        import export_validation
        with zipfile.ZipFile(output_path, "r") as validation_archive:
            validation_sheet_names = [
                item[0]
                for item in export_validation._workbook_sheet_targets(
                    validation_archive)
            ]
        tampered_rows = dict(
            (name, [list(row) for row in rows])
            for name, rows in sheet_rows.items()
        )
        tampered_rows["Beam"][1][0] = "unexpected-element-id"
        tampered_report = export_validation.validate_workbook(
            output_path,
            validation_sheet_names,
            tampered_rows,
            document_title="CHHANYADO HOSPITAL SURAT",
            export_format="classic",
            tool_version="RCC BOQ Parameter Manager v1.17.0"
        )
        check(
            tampered_report.get("ok") is False
            and tampered_report.get("mismatch_count") == 1
            and tampered_report.get("mismatches", [])[0].get("sheet")
            == "Beam",
            "Canonical validator detects a persisted XLSX cell mismatch"
        )

        assembly_table = sheet_rows.get("Structural Assembly", [])
        check(
            bool(assembly_table)
            and assembly_table[0] == ["Category", "Component", "Quantity", "Unit", "Basis", "Status", "Profile", "Source"],
            "P6 Structural Assembly sheet was generated with auditable headers"
        )
        column_rebar = [row for row in assembly_table[1:]
                        if row[0] == "Column" and row[1] == "Reinforcement"]
        check(
            bool(column_rebar) and column_rebar[0][2] == 10.667,
            "P6 hosted Rebar weight maps to its structural assembly"
        )
        input_rows = [row for row in assembly_table[1:]
                      if row[1] in ("Binding Wire", "Cover Blocks", "Labour")]
        check(
            bool(input_rows) and all(row[2] == "" and row[5] == "Input required" for row in input_rows),
            "P6 unsupported global allowances stay blank instead of inventing quantities"
        )

        beam_table = sheet_rows["Beam"]

        check(
            beam_table[0][-2:] == [
                "Qty: Length (m)",
                "Qty: Count"
            ],
            "Non-empty quantity columns retained on Beam sheet; "
            "Count appended (fully-empty Qty: Area pruned)"
        )

        check(
            "Qty: Count" in beam_table[0],
            "P1 element Count column present on Beam sheet"
        )

        check(
            "Concrete Volume" not in beam_table[0],
            "Fully-empty parameter column pruned from Beam sheet"
        )

        check(
            beam_table[-1][0] == "TOTAL",
            "TOTAL row appended to Beam sheet"
        )

        check(
            "Costing" in sheet_rows,
            "Costing sheet was generated"
        )

        costing_table = sheet_rows["Costing"]

        check(
            costing_table[0] == [
                "Category",
                "Element ID",
                "Quantity",
                "Rate",
                "Amount"
            ],
            "Costing sheet headers correct"
        )

        check(
            costing_table[-1][0] == "TOTAL",
            "Costing sheet has a TOTAL row"
        )

        amount_formula_count = sum(
            1 for row in costing_table[1:-1]
            if isinstance(row[4], tuple)
            and row[4][0] == "FORMULA"
        )

        check(
            amount_formula_count == 6,
            "Every element row has a live Quantity x Rate formula"
        )

        column_table = sheet_rows["Column"]

        check(
            "Qty: Height (m)" in column_table[0],
            "P1 Column Height (Parameter quantity) column present"
        )

        foundation_table = sheet_rows["Foundation"]
        wall_table = sheet_rows["Structure Wall"]

        check(
            "Qty: Height (m)" in wall_table[0]
            and "Qty: Thickness (m)" in wall_table[0],
            "Structure Wall Height and Thickness quantity columns present"
        )

        check(
            "Qty: Thickness (m)" in foundation_table[0],
            "P1 Foundation Thickness (Parameter quantity) column present"
        )

        rebar_table = sheet_rows["Rebar"]
        check(
            "Rebar: Diameter (mm)" in rebar_table[0]
            and "Rebar: Total Length (m)" in rebar_table[0]
            and "Rebar: Total Weight (kg)" in rebar_table[0]
            and "Rebar: Host Element ID" in rebar_table[0],
            "P4 Rebar detail sheet contains core quantity and host columns"
        )

        rebar_bbs_table = sheet_rows["Rebar BBS"]
        rebar_summary_table = sheet_rows["Rebar Summary"]
        check(
            "A (mm)" in rebar_bbs_table[0]
            and "Cutting Length (m)" in rebar_bbs_table[0]
            and rebar_bbs_table[1][
                rebar_bbs_table[0].index("A (mm)")
            ] == 3000.0
            and rebar_bbs_table[1][
                rebar_bbs_table[0].index("Cutting Length (m)")
            ] == 3.0,
            "P5 BBS preserves A-H geometry and Revit cutting length"
        )
        check(
            rebar_summary_table[1] == [
                12.0, 4, 12.0, 0.8889, 10.667, 0.0107
            ],
            "P5 diameter summary aggregates count, length, kg and tonnes"
        )

        check(
            "Qty: Count" in foundation_table[0]
            and "Qty: Count" in column_table[0]
            and "Qty: Count" in wall_table[0],
            "P1 element Count column present on all populated sheets"
        )

        # P2: level-wise grouping
        check(
            beam_table[0][1] == "Level",
            "P2 Level column sits directly after Element ID on element sheets"
        )

        level_table = sheet_rows["BOQ by Level"]

        check(
            level_table[0] == [
                "Level",
                "Category",
                "Elements",
                "Total Volume (m3)",
                "Total Area (m2)",
                "Total Length (m)"
            ],
            "P2 BOQ by Level headers correct"
        )

        level_keys = set(row[0] for row in level_table[1:])

        check(
            level_keys == set(["Ground Floor", "First Floor", "(No Level)"]),
            "P2 every collected level produces a grouped row"
        )

        sumif_count = sum(
            1 for row in level_table[1:]
            for cell in row[3:]
            if isinstance(cell, tuple)
            and cell[0] == "FORMULA"
            and "SUMIF(" in cell[1]
        )

        check(
            sumif_count == 12,
            "P2 live SUMIF per Level x Category x available-metric cell "
            "(expected 12 including Structure Wall; Foundation has no Length "
            "col; got {})".format(sumif_count)
        )

        check(
            any(
                isinstance(row[2], int) for row in level_table[1:]
            ),
            "P2 Elements count is a static number per grouped row"
        )

        # P2: concrete-grade grouping
        check(
            beam_table[0][2] == "Grade",
            "P2 Grade column sits directly after Level on element sheets"
        )

        grade_table = sheet_rows["BOQ by Grade"]

        check(
            grade_table[0] == [
                "Grade",
                "Category",
                "Elements",
                "Total Volume (m3)",
                "Total Area (m2)",
                "Total Length (m)"
            ],
            "P2 BOQ by Grade headers correct"
        )

        grade_keys = set(row[0] for row in grade_table[1:])

        check(
            grade_keys == set(["M25", "M30", "(No Grade)"]),
            "P2 every collected grade produces a grouped row "
            "(empty grades group under (No Grade))"
        )

        grade_sumif_count = sum(
            1 for row in grade_table[1:]
            for cell in row[3:]
            if isinstance(cell, tuple)
            and cell[0] == "FORMULA"
            and "SUMIF(" in cell[1]
        )

        check(
            grade_sumif_count == 12,
            "P2 live SUMIF per Grade x Category x available-metric cell "
            "(expected 12 including Structure Wall; got {})".format(
                grade_sumif_count
            )
        )

        wall_level_formulas = [
            cell[1]
            for row in level_table[1:]
            if row[1] == "Structure Wall"
            for cell in row[3:]
            if isinstance(cell, tuple) and cell[0] == "FORMULA"
        ]
        check(
            wall_level_formulas
            and all("'Structure Wall'!" in formula
                    for formula in wall_level_formulas),
            "Structure Wall level formulas use quoted sheet references"
        )

        check(
            any(
                isinstance(row[2], int) for row in grade_table[1:]
            ),
            "P2 Grade Elements count is a static number per grouped row"
        )

        normalize = namespace["normalize_concrete_grade"]

        check(
            normalize("M25") == "M25"
            and normalize("m-30") == "M30"
            and normalize("M 40") == "M40"
            and normalize("Concrete - M25 grade") == "M25"
            and normalize("MIX") == ""
            and normalize("M150") == ""
            and normalize("M60") in namespace["CONCRETE_GRADE_VALUES"]
            and normalize("") == "",
            "P2 grade token normalization accepts M25/m-30/M 40 forms "
            "and rejects non-grades"
        )

        # Professional output: front Summary cover + naming convention
        summary_cover = sheet_rows["Summary"]

        check(
            summary_cover[0][0] == "RCC - CONCRETE FINISHING BOQ",
            "Summary cover title present as the first sheet"
        )

        cover_pairs = dict(
            (row[0], row[1]) for row in summary_cover
            if row[0] in ("Project", "Generated", "Tool")
        )

        check(
            cover_pairs.get("Project") == "CHHANYADO HOSPITAL SURAT"
            and cover_pairs.get("Generated") == "2026-08-26 10:00"
            and "v1.4.0" in str(cover_pairs.get("Tool")),
            "Summary cover carries project, stamp and tool version"
        )

        listed = set(
            row[0] for row in summary_cover
            if row[0] in (
                "Beam", "Column", "Structure Wall", "Foundation", "Rebar",
                "BOQ Summary", "BOQ by Level", "BOQ by Grade", "Costing"
            )
        )

        check(
            listed == set(
                [
                    "Beam", "Column", "Structure Wall", "Foundation", "Rebar",
                    "BOQ Summary", "BOQ by Level", "BOQ by Grade", "Costing"
                ]
            ),
            "Summary cover lists every workbook sheet"
        )

        sanitized = namespace["sanitize_file_name"]('My / Project: "X"*?')

        check(
            sanitized == "My-Project-X-",
            "File-name sanitization strips Windows-forbidden characters "
            "and collapses separator runs (got {})".format(sanitized)
        )

        default_name = namespace["build_default_output_name"](
            "CHHANYADO HOSPITAL SURAT"
        )

        name_pattern = re.compile(
            r"^\d{8}-CHHANYADO-HOSPITAL-SURAT-CONCRETE_FINISHING_BOQ\.xlsx$"
        )

        check(
            name_pattern.match(default_name) is not None,
            "Default output name follows YYYYMMDD-Project-BOQ convention "
            "(got {})".format(default_name)
        )

        # ====================================================
        # v1.4.0 SITE FORMAT: formwork engine (pure logic)
        # ====================================================

        meters_to_millimeters = namespace["meters_to_millimeters"]

        check(
            meters_to_millimeters(3.048) == 3048
            and meters_to_millimeters("0.15") == 150
            and meters_to_millimeters("") == ""
            and meters_to_millimeters(None) == "",
            "MM conversion rounds metres to whole millimetres"
        )

        check(
            namespace["build_section_description"](3.13, 0.15)
            == "150 X 3130",
            "Section description renders WIDTH X LENGTH in millimetres"
        )

        check(
            namespace["build_section_description"](3.13, "")
            == "",
            "Section description stays blank when a dimension is missing"
        )

        beam_dims = namespace["resolve_element_dimensions"](
            "Beam",
            length_m=6.096,
            width_m=0.23,
            height_m=0.6
        )

        check(
            beam_dims == {"length": 6.096, "width": 0.23, "height": 0.6},
            "Beam dimension resolution keeps L/W/H as given"
        )

        angled_beam_dims = namespace["resolve_element_dimensions"](
            "Beam",
            length_m=3.277,
            depth_m=0.725,
            bbox_width_m=1.273,
            bbox_height_m=0.725
        )

        check(
            angled_beam_dims["width"] == ""
            and angled_beam_dims["height"] == 0.725,
            "Beam dimensions reject rotated bounding-box width when actual section width is missing"
        )

        class FakeMetricStorageType(object):
            Double = "double"

        class FakeMetricBuiltInParameter(object):
            STRUCTURAL_SECTION_COMMON_WIDTH = "section_width"

        class FakeMetricDB(object):
            StorageType = FakeMetricStorageType
            BuiltInParameter = FakeMetricBuiltInParameter

        class FakeMetricDefinition(object):
            def __init__(self, name):
                self.Name = name

        class FakeMetricParameter(object):
            HasValue = True
            StorageType = FakeMetricStorageType.Double

            def __init__(self, name, internal_feet):
                self.Definition = FakeMetricDefinition(name)
                self.internal_feet = internal_feet

            def AsDouble(self):
                return self.internal_feet

        class FakeMetricCandidate(object):
            def __init__(self, built_in=None, named=None):
                self.built_in = built_in
                self.named = named or {}
                self.Parameters = list(self.named.values())

            def get_Parameter(self, _parameter_id):
                return self.built_in

            def LookupParameter(self, name):
                return self.named.get(name)

        class FakeMetricElement(FakeMetricCandidate):
            def __init__(self, symbol):
                FakeMetricCandidate.__init__(self)
                self.Symbol = symbol

        metric_namespace = {
            "DB": FakeMetricDB,
            "doc": None,
            # Revit stores lengths internally in feet.
            "convert_quantity_value": lambda value, _kind: round(
                float(value) * 0.3048, 4
            )
        }
        metric_source, _ = extract_from_sources(texts, "read_metric_parameter")
        exec(metric_source, metric_namespace)
        read_metric = metric_namespace["read_metric_parameter"]

        built_in_width = FakeMetricParameter("Width", 0.9842519685)
        alias_width = FakeMetricParameter("BEAM WIDTH", 1.312335958)
        built_in_symbol = FakeMetricCandidate(
            built_in=built_in_width,
            named={"BEAM WIDTH": alias_width}
        )
        detected_width = read_metric(
            FakeMetricElement(built_in_symbol),
            ("BEAM WIDTH", "Width"),
            ("STRUCTURAL_SECTION_COMMON_WIDTH", "NOT_IN_THIS_API")
        )

        alias_symbol = FakeMetricCandidate(
            named={"BEAM WIDTH": FakeMetricParameter("BEAM WIDTH", 0.9842519685)}
        )
        aliased_width = read_metric(
            FakeMetricElement(alias_symbol),
            ("Beam Width", "Width"),
            ("NOT_IN_THIS_API",)
        )

        check(
            abs(detected_width - 0.3) < 0.0001
            and abs(aliased_width - 0.3) < 0.0001,
            "Beam width feature detection prefers Revit built-in and supports BEAM WIDTH alias"
        )

        class FakeInvalidElementId(object):
            pass

        class FakeCacheElementId(object):
            InvalidElementId = FakeInvalidElementId()

        class FakeCacheDB(object):
            ElementId = FakeCacheElementId

        class FakeTypeId(object):
            def __init__(self, value):
                self.IntegerValue = value

            def Equals(self, other):
                return False

        class CountingParameterOwner(object):
            def __init__(self, parameters):
                self._parameters = parameters
                self.parameter_reads = 0

            @property
            def Parameters(self):
                self.parameter_reads += 1
                return self._parameters

        type_mark = FakeMetricParameter("Type Mark", 1.0)
        cached_type = CountingParameterOwner([type_mark])

        class FakeCacheDocument(object):
            def __init__(self):
                self.reads = 0

            def GetElement(self, _type_id):
                self.reads += 1
                return cached_type

        class FakeCacheInstance(CountingParameterOwner):
            def __init__(self, mark):
                CountingParameterOwner.__init__(
                    self,
                    [FakeMetricParameter("Mark", mark)]
                )

            def GetTypeId(self):
                return FakeTypeId(42)

        cache_document = FakeCacheDocument()
        cache_namespace = {
            "DB": FakeCacheDB,
            "doc": cache_document
        }
        for helper_name in (
            "build_element_parameter_context",
            "find_parameter_in_context"
        ):
            helper_source, _ = extract_from_sources(texts, helper_name)
            exec(helper_source, cache_namespace)

        shared_type_cache = {}
        first_instance = FakeCacheInstance(1.0)
        second_instance = FakeCacheInstance(2.0)
        first_context = cache_namespace["build_element_parameter_context"](
            first_instance,
            shared_type_cache
        )
        second_context = cache_namespace["build_element_parameter_context"](
            second_instance,
            shared_type_cache
        )
        first_mark, first_scope = cache_namespace["find_parameter_in_context"](
            first_context,
            "Mark"
        )
        cached_type_mark, type_scope = cache_namespace["find_parameter_in_context"](
            second_context,
            "Type Mark"
        )

        check(
            first_mark is not None
            and first_scope == "Instance"
            and cached_type_mark is type_mark
            and type_scope == "Type"
            and first_instance.parameter_reads == 1
            and second_instance.parameter_reads == 1
            and cached_type.parameter_reads == 1
            and cache_document.reads == 1,
            "Fast export indexes each instance once and reuses one parameter index per Revit type"
        )

        column_dims = namespace["resolve_element_dimensions"](
            "Column",
            width_m=0.45,
            height_m=3.5,
            depth_m=0.3
        )

        check(
            column_dims["width"] == 0.3
            and column_dims["length"] == 0.45
            and column_dims["height"] == 3.5,
            "Column section pair sorted W <= L like the manual sheet"
        )

        bbox_column = namespace["resolve_element_dimensions"](
            "Column",
            bbox_length_m=9.2,
            bbox_width_m=1.6,
            bbox_height_m=5.2
        )

        check(
            bbox_column["width"] == 1.6
            and bbox_column["length"] == 9.2
            and bbox_column["height"] == 5.2,
            "Column dimensions fall back to the bounding box pair"
        )

        wall_dims = namespace["resolve_element_dimensions"](
            "Structure Wall",
            length_m=4.0,
            thickness_m=0.2,
            height_m=2.5
        )

        check(
            wall_dims == {"length": 4.0, "width": 0.2, "height": 2.5},
            "Structure Wall dimensions resolve Length/Thickness/Height"
        )

        compute_shuttering_area = namespace["compute_shuttering_area"]

        check(
            compute_shuttering_area(
                "Column", length_m=0.45, width_m=0.3, height_m=3.5
            ) == 5.25,
            "Column shuttering = 2(L+W)H (four faces)"
        )

        check(
            compute_shuttering_area(
                "Beam", length_m=6.096, width_m=0.23, height_m=0.6
            ) == 8.72,
            "Beam shuttering = (W+2H)L (soffit plus two sides)"
        )

        check(
            compute_shuttering_area(
                "Structure Wall", length_m=4.0, height_m=2.5
            ) == 20.0,
            "Structure Wall shuttering = 2LH (gross two-face area)"
        )

        rebar_values = namespace["build_rebar_quantity_values"](
            diameter_mm=12.0,
            quantity=4,
            bar_length_m=3.0,
            total_length_m=""
        )
        check(
            namespace["rebar_unit_weight_kg_per_m"](12.0) == 0.8889
            and rebar_values["Quantity"] == 4
            and rebar_values["Total Length (m)"] == 12.0
            and rebar_values["Total Weight (kg)"] == 10.667,
            "P4 Rebar d^2/162 unit weight and total weight calculation"
        )

        grouped_bbs = namespace["build_rebar_bbs_table"]([
            {
                "Rebar: Bar Mark": "L1", "Rebar: Shape": "L SHAPE",
                "Rebar: Diameter (mm)": 20, "Rebar: A (mm)": "150 mm",
                "Rebar: B (mm)": "8408 mm",
                "Rebar: Cutting Length (m)": 8.5162,
                "Rebar: Quantity": 2, "Rebar: Total Length (m)": 17.0324,
                "Rebar: Unit Weight (kg/m)": 2.4691,
                "Rebar: Total Weight (kg)": 42.056,
                "Rebar: Element ID": "101",
                "Rebar: Host Element ID": "10", "Level": "Level 1"
            },
            {
                "Rebar: Bar Mark": "L1", "Rebar: Shape": "L SHAPE",
                "Rebar: Diameter (mm)": 20, "Rebar: A (mm)": 150,
                "Rebar: B (mm)": 8408,
                "Rebar: Cutting Length (m)": 8.5162,
                "Rebar: Quantity": 3, "Rebar: Total Length (m)": 25.5486,
                "Rebar: Unit Weight (kg/m)": 2.4691,
                "Rebar: Total Weight (kg)": 63.084,
                "Rebar: Element ID": "102",
                "Rebar: Host Element ID": "10", "Level": "Level 1"
            }
        ])
        grouped_headers = grouped_bbs[0]
        check(
            len(grouped_bbs) == 2
            and grouped_bbs[1][grouped_headers.index("A (mm)")] == 150.0
            and grouped_bbs[1][grouped_headers.index("Quantity")] == 5
            and grouped_bbs[1][grouped_headers.index("Total Length (m)")] == 42.581
            and grouped_bbs[1][
                grouped_headers.index("Rebar Element ID")
            ] == "101, 102"
            and len(grouped_bbs[1]) == len(grouped_headers),
            "P5 BBS groups matching shapes and parses Revit mm display text"
        )
        variable_bbs = namespace["build_rebar_bbs_table"]([
            {
                "Rebar: Bar Mark": "V1", "Rebar: Shape": "L SHAPE",
                "Rebar: Diameter (mm)": 20, "Rebar: A (mm)": "Varies",
                "Rebar: B (mm)": 492,
                "Rebar: Quantity": 3, "Rebar: Total Length (m)": 33.51,
                "Rebar: Unit Weight (kg/m)": 2.4691,
                "Rebar: Total Weight (kg)": 82.74,
                "Rebar: Element ID": "501",
                "Rebar: Host Element ID": "200", "Level": "Level 1"
            },
            {
                "Rebar: Bar Mark": "V1", "Rebar: Shape": "L SHAPE",
                "Rebar: Diameter (mm)": 20, "Rebar: A (mm)": "Varies",
                "Rebar: B (mm)": 492,
                "Rebar: Quantity": 3, "Rebar: Total Length (m)": 28.95,
                "Rebar: Unit Weight (kg/m)": 2.4691,
                "Rebar: Total Weight (kg)": 71.48,
                "Rebar: Element ID": "502",
                "Rebar: Host Element ID": "200", "Level": "Level 1"
            }
        ])
        variable_headers = variable_bbs[0]
        check(
            len(variable_bbs) == 3
            and variable_bbs[1][
                variable_headers.index("Cutting Length (m)")
            ] == ""
            and variable_bbs[1][
                variable_headers.index("Average Bar Length (m)")
            ] == 11.17
            and variable_bbs[1][
                variable_headers.index("Length Status")
            ] == "Variable set / average only"
            and variable_bbs[1][
                variable_headers.index("Rebar Element ID")
            ] == "501"
            and variable_bbs[1][
                variable_headers.index("A (mm)")
            ] == "Varies"
            and variable_bbs[2][
                variable_headers.index("Average Bar Length (m)")
            ] == 9.65
            and sum(
                row[variable_headers.index("Quantity")]
                for row in variable_bbs[1:]
            ) == 6
            and round(sum(
                row[variable_headers.index("Total Length (m)")]
                for row in variable_bbs[1:]
            ), 4) == 62.46,
            "P5 keeps varying sets separate with traceable averages"
        )
        check(
            namespace["normalize_rebar_dimension_mm"](
                "<varies>", "", False
            ) == "Varies"
            and namespace["normalize_rebar_dimension_mm"](
                "492 mm", 492.0, True
            ) == 492.0,
            "P5 preserves varying A-H dimensions and normalizes fixed mm"
        )

        check(
            compute_shuttering_area("Slab", area_m2=9.3) == 9.3,
            "Slab shuttering = soffit contact area passthrough"
        )

        check(
            compute_shuttering_area(
                "Foundation", length_m=1.8, width_m=1.2, height_m=0.3
            ) == 1.8,
            "Foundation shuttering = footing side faces 2(L+W)H"
        )

        check(
            compute_shuttering_area("Beam") == ""
            and compute_shuttering_area("Slab") == ""
            and compute_shuttering_area("Slab", area_m2=-1) == "",
            "Shuttering stays blank when dimensions are missing or bad"
        )

        # ====================================================
        # P3 slice 2: configurable formwork rules (pure logic)
        # ====================================================

        normalize_formwork_rules = namespace["normalize_formwork_rules"]
        get_formwork_factor = namespace["get_formwork_factor"]
        is_formwork_enabled = namespace["is_formwork_enabled"]

        check(
            normalize_formwork_rules(None)["enabled"] is True
            and normalize_formwork_rules(None)["deduction_pct"]["Beam"] == 0.0,
            "normalize_formwork_rules falls back to defaults on bad input"
        )

        cleaned_rules = normalize_formwork_rules({
            "enabled": False,
            "deduction_pct": {
                "Beam": 5,
                "Column": "x",
                "Structure Wall": 12.5,
                "Slab": 150,
                "Foundation": -3
            }
        })

        check(
            cleaned_rules["enabled"] is False
            and cleaned_rules["deduction_pct"]["Beam"] == 5.0
            and cleaned_rules["deduction_pct"]["Column"] == 0.0
            and cleaned_rules["deduction_pct"]["Structure Wall"] == 12.5
            and cleaned_rules["deduction_pct"]["Slab"] == 100.0
            and cleaned_rules["deduction_pct"]["Foundation"] == 0.0,
            "Deduction percentages are clamped to 0-100 and bad values reset"
        )

        namespace["formwork_rules"]["deduction_pct"]["Beam"] = 5.0

        check(
            get_formwork_factor("Beam") == 0.95,
            "get_formwork_factor converts the Beam percentage to a multiplier"
        )

        namespace["formwork_rules"]["deduction_pct"]["Beam"] = 0.0

        check(
            is_formwork_enabled() is True,
            "Formwork takeoff is enabled by default"
        )

        namespace["formwork_rules"]["enabled"] = False

        check(
            is_formwork_enabled() is False,
            "is_formwork_enabled reflects the runtime rules state"
        )

        namespace["formwork_rules"]["enabled"] = True

        check(
            compute_shuttering_area(
                "Column", length_m=0.45, width_m=0.3, height_m=3.5, factor=0.95
            ) == round(2.0 * (0.45 + 0.3) * 3.5 * 0.95, 2),
            "Column shuttering honours the deduction factor"
        )

        check(
            compute_shuttering_area(
                "Beam", length_m=6.096, width_m=0.23, height_m=0.6, factor=0.9
            ) == round((0.23 + 2.0 * 0.6) * 6.096 * 0.9, 2),
            "Beam shuttering honours the deduction factor"
        )

        check(
            compute_shuttering_area("Slab", area_m2=9.3, factor=0.9)
            == round(9.3 * 0.9, 2),
            "Slab soffit shuttering honours the deduction factor"
        )

        check(
            compute_shuttering_area(
                "Column", length_m=0.45, width_m=0.3, height_m=3.5,
                enabled=False
            ) == "",
            "Disabled formwork rules blank the SHUTTERING column"
        )

        check(
            compute_shuttering_area("Slab", area_m2=9.3, factor=0) == "",
            "A zero factor yields a blank shuttering cell"
        )

        check(
            compute_shuttering_area(
                "Column", length_m=0.45, width_m=0.3, height_m=3.5, factor=-1
            ) == 5.25,
            "A negative factor falls back to no deduction"
        )

        # ===================================================
        # Shuttering formula helper (for Excel cell formulas)
        # ===================================================

        build_shuttering_formula = namespace["build_shuttering_formula"]

        check(
            build_shuttering_formula("Column", "F", "G", "H", 1.0)
            == "=ROUND(2*(F+G)*H, 2)",
            "Column shuttering formula: 2*(L+W)*H"
        )

        check(
            build_shuttering_formula("Beam", "F", "G", "H", 1.0)
            == "=ROUND((G+2*H)*F, 2)",
            "Beam shuttering formula: (W+2*H)*L"
        )

        check(
            build_shuttering_formula(
                "Structure Wall", "F", "G", "H", 1.0
            ) == "=ROUND(2*F*H, 2)",
            "Structure Wall shuttering formula: 2*L*H"
        )

        check(
            build_shuttering_formula("Slab", "F", "G", "H", 1.0)
            == "=ROUND(F*G, 2)",
            "Slab shuttering formula: L*W (soffit area)"
        )

        check(
            build_shuttering_formula("Foundation", "F", "G", "H", 1.0)
            == "=ROUND(2*(F+G)*H, 2)",
            "Foundation shuttering formula: 2*(L+W)*H"
        )

        check(
            build_shuttering_formula("Column", "F", "G", "H", 0.95)
            == "=ROUND(2*(F+G)*H*0.95, 2)",
            "Column formula includes deduction factor (5% deduction)"
        )

        check(
            build_shuttering_formula("Beam", "F", "G", "H", 0.9)
            == "=ROUND((G+2*H)*F*0.9, 2)",
            "Beam formula includes deduction factor (10% deduction)"
        )

        check(
            build_shuttering_formula("Unknown", "F", "G", "H", 1.0) == "",
            "Unknown category returns empty string"
        )

        ordered_levels_check = sorted(
            ["Level 10", "Level 2"],
            key=namespace["_site_sort_key"]
        )

        check(
            ordered_levels_check == ["Level 2", "Level 10"],
            "Natural sort orders levels numerically (2 before 10)"
        )

        # v1.8.7: named storeys order like a real building (foundation
        # and plinth below numbered floors, terrace and OHW/LMR above),
        # and site detail rows group ascending by their level column.
        building_order = [
            "12 TERRACE LEVEL", "05 2ND LEVEL", "04 1ST LEVEL",
            "OHW/LMR LEVEL", "03 PLINTH LEVEL", "01 FOUNDATION LEVEL",
            "TERRACE LEVEL", "1ST LEVEL", "PLINTH LEVEL", "Level 2",
            "Level 10", "8TH LEVEL"
        ]

        check(
            sorted(building_order, key=namespace["_site_sort_key"])
            == [
                "01 FOUNDATION LEVEL", "03 PLINTH LEVEL", "PLINTH LEVEL",
                "1ST LEVEL", "Level 2", "04 1ST LEVEL", "05 2ND LEVEL",
                "8TH LEVEL", "Level 10", "12 TERRACE LEVEL",
                "TERRACE LEVEL", "OHW/LMR LEVEL"
            ],
            "Level key orders building storeys: FOUNDATION < PLINTH < "
            "numbered < TERRACE < OHW/LMR"
        )

        sort_rows = namespace["_sort_site_rows"]

        shuffled_rows = [
            {"LEVEL_V": "8TH LEVEL", "MARK": "B8"},
            {"LEVEL_V": "PLINTH LEVEL", "MARK": "B9"},
            {"LEVEL_V": "1ST LEVEL", "MARK": "B1"},
            {"LEVEL_V": "1ST LEVEL", "MARK": "B2"},
            {"LEVEL_V": "2ND LEVEL", "MARK": "B3"},
        ]

        check(
            [row["MARK"] for row in sort_rows(shuffled_rows)]
            == ["B9", "B1", "B2", "B3", "B8"],
            "Site rows group ascending by level (stable within a level)"
        )

        unsorted_rows = [{"AREA": 2}, {"AREA": 1}]

        check(
            sort_rows(unsorted_rows) == unsorted_rows,
            "Rows without a level column keep collection order"
        )

        # ====================================================
        # v1.4.0 SITE FORMAT: table builders
        # ====================================================

        site_rows_fixture = [
            {
                "Element ID": "100",
                "Level": "Level 1",
                "Mark": "B1",
                "Qty: Volume (m3)": 0.8356,
                "Qty: Dim L (m)": 6.096,
                "Qty: Dim W (m)": 0.23,
                "Qty: Dim H (m)": 0.6,
                "Qty: Shuttering (m2)": 8.72
            },
            {
                "Element ID": "101",
                "Level": "Level 2",
                "Mark": "B2",
                "Qty: Volume (m3)": 1.2437,
                "Qty: Dim L (m)": 7.3152,
                "Qty: Dim W (m)": 0.3,
                "Qty: Dim H (m)": 0.6,
                "Qty: Shuttering (m2)": 10.49
            }
        ]

        detail_table, detail_meta = \
            namespace["build_site_detail_sheet"](
                "Beam",
                site_rows_fixture,
                "CHHANYADO HOSPITAL SURAT"
            )

        check(
            detail_table[1][0] == "RCC - CONCRETE FINISHING BOQ"
            and detail_table[2][0] == "BEAM DETAILS",
            "Detail sheet title block carries workbook and category rows"
        )

        check(
            detail_table[4][0] == ("MERGE_V", "SNO")
            and detail_table[4][1] == ("MERGE_V", "MARK"),
            "Detail band header is SNO + selected params only"
        )

        first_site_row = detail_table[6]

        check(
            first_site_row[0] == 1
            and first_site_row[1] == "B1",
            "Element rows are SNO followed by the selected MARK"
        )

        check(
            len(first_site_row) == 6
            and detail_table[7][1] == "B2",
            "Detail sheet has SNO + param + L/W/H + SHUTTERING columns"
        )

        check(
            detail_table[4][2] == ("MERGE_V", "L (m)")
            and detail_table[4][3] == ("MERGE_V", "W (m)")
            and detail_table[4][4] == ("MERGE_V", "H (m)")
            and detail_table[4][5] == ("MERGE_V", "SHUTTERING (SQM)"),
            "Dimension columns L/W/H and SHUTTERING header present"
        )

        check(
            first_site_row[2] == "6.096"
            and first_site_row[3] == "0.230"
            and first_site_row[4] == "0.600",
            "Dimension columns carry L/W/H values (3 decimals)"
        )

        check(
            isinstance(first_site_row[5], tuple)
            and first_site_row[5][0] == "FORMULA"
            and "ROUND" in first_site_row[5][1],
            "SHUTTERING column contains a FORMULA tuple"
        )

        check(
            "=ROUND((D7+2*E7)*C7, 2)" == first_site_row[5][1],
            "Beam shuttering formula: (W+2*H)*L"
        )

        nofw_table, nofw_meta = namespace["build_site_detail_sheet"](
            "Beam", site_rows_fixture, "Sample Project",
            include_formwork=False
        )

        check(
            len(nofw_table[6]) == 2
            and nofw_meta["shuttering_col"] == "",
            "Include formwork off removes dimension and SHUTTERING columns"
        )

        check(
            nofw_meta["widths"] == [7, 18],
            "Widths shrink back when formwork is off"
        )

        check(
            namespace["_site_desc_text"](1200.0) == "1200"
            and namespace["_site_desc_text"](" 450 mm ") == "450 mm"
            and namespace["_site_desc_text"]("") == "",
            "Selected-parameter values render without trailing .0 noise"
        )

        check(
            "TOTAL" not in detail_table[-1]
            and detail_meta["data_start"] == 7
            and detail_meta["columns"] == {}
            and detail_meta["level_col"] == "",
            "No SUM totals row; meta drops the F/G/H SUMIF contract"
        )

        summary_table_s, summary_meta_s = \
            namespace["build_site_summary_sheet"](
                {"Beam": site_rows_fixture},
                {"Beam": detail_meta},
                "CHHANYADO HOSPITAL SURAT"
            )

        check(
            summary_table_s[1][0] == "RCC - CONCRETE FINISHING BOQ"
            and summary_table_s[2][0]
            == "ITEM-WISE SUMMARY - CONCRETE AND SHUTTERING",
            "Summary title block carries the VOL/SHUT caption"
        )

        check(
            summary_table_s[4] == [
                ("MERGE_V", "SNO"),
                ("MERGE_V", "CATEGORY"),
                "ELEMENTS",
                "VOLUME (m3)",
                "SHUTTERING (m2)",
            ]
            and summary_table_s[6][0] == 1
            and summary_table_s[6][1] == "BEAM"
            and summary_table_s[6][2] == 2,
            "Summary header lists SNO|CATEGORY|ELEMENTS|VOL|SHUT columns"
        )

        check(
            summary_meta_s["levels"] == []
            and summary_meta_s["total_columns"] == 5
            and summary_meta_s["columns"]["Volume (m3)"] == "D"
            and summary_meta_s["columns"]["Shuttering (m2)"] == "E",
            "Summary meta exposes the 5-column VOL/SHUT column plan"
        )

        nofw_summary_table, nofw_summary_meta = \
            namespace["build_site_summary_sheet"](
                {"Beam": site_rows_fixture},
                {"Beam": detail_meta},
                "CHHANYADO HOSPITAL SURAT",
                include_formwork=False
            )

        check(
            nofw_summary_table[2][0]
            == "ITEM-WISE SUMMARY - CONCRETE"
            and nofw_summary_table[4] == [
                ("MERGE_V", "SNO"),
                ("MERGE_V", "CATEGORY"),
                "ELEMENTS",
                "VOLUME (m3)",
            ]
            and len(nofw_summary_table[6]) == 4
            and "SHUTTERING (m2)" not in nofw_summary_table[4],
            "Formwork off drops the summary SHUTTERING column and caption"
        )

        check(
            nofw_summary_meta["total_columns"] == 4
            and "Shuttering (m2)" not in nofw_summary_meta["columns"]
            and nofw_summary_table[-1][0] == "TOTAL",
            "Formwork-off summary meta carries the 4-column plan"
        )

    finally:

        # Early failures above may leave the sample workbook behind;
        # the zip-based checks below reopen it from disk regardless.
        pass

    archive = zipfile.ZipFile(output_path, "r")

    try:

        part_names = archive.namelist()

        for part_name in part_names:

            if not part_name.endswith(".xml") \
                    and not part_name.endswith(".rels"):
                continue

            payload = archive.read(part_name)

            try:
                minidom.parseString(payload)
                print("XML OK : {}".format(part_name))
            except Exception as parse_error:
                failures.append(
                    "{} malformed: {}".format(part_name, parse_error)
                )
                print("FAIL   : {} ({})".format(part_name, parse_error))

        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")

        check(
            'fullCalcOnLoad="1"' in workbook_xml,
            "workbook.xml enables fullCalcOnLoad so formulas evaluate"
        )

        sheet_order = re.findall(
            r'<sheet name="([^"]+)"',
            workbook_xml
        )

        expected_order = [
            "Summary", "Beam", "Column", "Structure Wall", "Foundation",
            "Rebar", "Rebar Summary", "Rebar BBS", "BOQ Summary",
            "Structural Assembly", "BOQ by Level", "BOQ by Grade", "Costing"
        ]

        check(
            sheet_order == expected_order,
            "Sheet order correct: {}".format(sheet_order)
        )

        check(
            list(sheet_rows.keys()) == sheet_order,
            "Classic writer returns sheets in workbook order for the export popup listing"
        )

        check(
            "Parameter Metadata" not in sheet_order
            and "Missing Values Summary" not in sheet_order
            and "Slab" not in sheet_order,
            "Obsolete empty / metadata sheets removed from workbook"
        )

        content_types = archive.read(
            "[Content_Types].xml"
        ).decode("utf-8")

        override_count = content_types.count(
            "spreadsheetml.worksheet+xml"
        )

        check(
            override_count == len(expected_order),
            "Content types declare every worksheet ({} of {})".format(
                override_count,
                len(expected_order)
            )
        )

        beam_xml = archive.read(
            "xl/worksheets/sheet2.xml"
        ).decode("utf-8")

        check(
            "<f>SUM(" in beam_xml,
            "Beam TOTAL row has SUM formulas"
        )

        filter_match = re.search(
            r'<autoFilter ref="A1:[A-Z]+(\d+)"',
            beam_xml
        )

        check(
            filter_match is not None
            and int(filter_match.group(1)) == len(beam_table) - 1,
            "Auto-filter range excludes the totals row"
        )

        header_cells = re.findall(
            r'<c r="[A-Z]+1"[^>]*s="1"',
            beam_xml
        )

        check(
            len(header_cells) == len(beam_table[0]),
            "Every Beam header cell carries the styled header format"
        )

        summary_xml = archive.read(
            "xl/worksheets/sheet{0}.xml".format(
                expected_order.index("BOQ Summary") + 1
            )
        ).decode("utf-8")

        check(
            "<f>Beam!" in summary_xml,
            "BOQ Summary references category sheets by formula"
        )

        check(
            "<f>'Structure Wall'!" in summary_xml,
            "BOQ Summary safely references the Structure Wall sheet"
        )

        check(
            "GRAND TOTAL" in summary_xml,
            "BOQ Summary has a GRAND TOTAL row"
        )

        summary_row_numbers = [
            int(number)
            for number in re.findall(r'<row r="(\d+)"', summary_xml)
        ]
        grand_total_row = max(summary_row_numbers)
        last_category_row = grand_total_row - 1

        check(
            last_category_row >= 2
            and all(
                "<f>SUM({0}2:{0}{1})</f>".format(letter, last_category_row)
                in summary_xml
                for letter in ("B", "C", "D", "E")
            ),
            "BOQ Summary GRAND TOTAL sums every category row, including the last"
        )

        styles_xml = archive.read("xl/styles.xml").decode("utf-8")

        check(
            'numFmtId="4"' in styles_xml,
            "Styles define the #,##0.00 number format (builtin 4)"
        )

        check(
            'rgb="FFF2994A"' in styles_xml,
            "Styles define the Ember accent header fill"
        )

        cellxf_count = len(
            re.findall(r"<xf ", styles_xml.split("<cellXfs")[1])
        )

        check(
            cellxf_count >= 5,
            "Styles expose all five cell formats"
        )

    finally:

        archive.close()

        try:
            os.remove(output_path)
        except:
            pass
        try:
            os.remove(validation_report_path)
        except:
            pass

    # ============================================================
    # v1.4.0 SITE FORMAT workbook validation (zip-level)
    # ============================================================

    site_output_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "_boq_site_test.xlsx"
    )

    site_data = {
        "Beam": [
            {
                "Element ID": "100",
                "Level": "Level 1",
                "Mark": "B1",
                "Qty: Volume (m3)": 0.8356,
                "Qty: Dim L (m)": 6.096,
                "Qty: Dim W (m)": 0.23,
                "Qty: Dim H (m)": 0.6,
                "Qty: Shuttering (m2)": 8.72
            },
            {
                "Element ID": "101",
                "Level": "Level 2",
                "Mark": "B2",
                "Qty: Volume (m3)": 1.2437,
                "Qty: Dim L (m)": 7.3152,
                "Qty: Dim W (m)": 0.3,
                "Qty: Dim H (m)": 0.6,
                "Qty: Shuttering (m2)": 10.49
            }
        ],
        "Column": [],
        "Structure Wall": [
            {
                "Element ID": "250",
                "Level": "Level 1",
                "Mark": "SW1",
                "Qty: Volume (m3)": 2.0,
                "Qty: Thickness (m)": 0.2,
                "Qty: Count": 1,
                "Qty: Dim L (m)": 4.0,
                "Qty: Dim W (m)": 0.2,
                "Qty: Dim H (m)": 2.5,
                "Qty: Shuttering (m2)": 20.0
            }
        ],
        "Slab": [],
        "Foundation": [],
        "Rebar": [
            {
                "Element ID": "400",
                "Level": "Level 1",
                "Mark": "R1",
                "Rebar: Bar Mark": "R1",
                "Rebar: Diameter (mm)": 12.0,
                "Rebar: Shape": "M_00",
                "Rebar: Quantity": 4,
                "Rebar: Bar Length (m)": 3.0,
                "Rebar: Cutting Length (m)": 3.0,
                "Rebar: Total Length (m)": 12.0,
                "Rebar: Unit Weight (kg/m)": 0.8889,
                "Rebar: Total Weight (kg)": 10.667,
                "Rebar: Element ID": "400",
                "Rebar: Host Element ID": "200",
                "Rebar: Host Category": "Structural Columns",
                "Rebar: A (mm)": 3000.0,
                "Rebar: Bend Diameter (mm)": 48.0,
                "Rebar: Hook at Start": "",
                "Rebar: Hook at End": ""
            }
        ]
    }

    namespace["write_site_xlsx"](
        site_output_path,
        site_data,
        project_name="CHHANYADO HOSPITAL SURAT",
        tool_version="RCC BOQ Parameter Manager v1.4.0",
        generated_stamp="2026-08-27 10:00",
        selected_parameters={
            "Beam": ["Mark"],
            "Structure Wall": [
                "Mark", "Qty: Thickness (m)", "Qty: Count"
            ],
            "Rebar": ["Mark"]
        }
    )

    site_archive = zipfile.ZipFile(site_output_path, "r")

    try:

        for part_name in site_archive.namelist():

            if not part_name.endswith(".xml") \
                    and not part_name.endswith(".rels"):
                continue

            payload = site_archive.read(part_name)

            try:
                minidom.parseString(payload)
                print("XML OK : {}".format(part_name))
            except Exception as parse_error:
                failures.append(
                    "{} malformed: {}".format(part_name, parse_error)
                )
                print("FAIL   : {} ({})".format(part_name, parse_error))

        site_workbook_xml = site_archive.read(
            "xl/workbook.xml"
        ).decode("utf-8")

        sheet_order_site = re.findall(
            r'<sheet name="([^"]+)"',
            site_workbook_xml
        )

        check(
            sheet_order_site == [
                "Summary", "Beam", "Structure Wall", "Rebar",
                "Rebar Summary", "Rebar BBS", "Structural Assembly"
            ],
            "Site workbook order: Summary then populated categories "
            "(got {})".format(sheet_order_site)
        )

        check(
            'fullCalcOnLoad="1"' in site_workbook_xml,
            "Site workbook enables fullCalcOnLoad for its live formulas"
        )

        site_summary_xml = site_archive.read(
            "xl/worksheets/sheet1.xml"
        ).decode("utf-8")

        merge_counts = re.findall(
            r'<mergeCells count="(\d+)"',
            site_summary_xml
        )

        check(
            bool(merge_counts) and int(merge_counts[0]) >= 4,
            "Summary title blocks and header band carry merged cells "
            "(count={})".format(merge_counts)
        )

        check(
            ">BEAM<" in site_summary_xml
            and ">STRUCTURE WALL<" in site_summary_xml
            and ">2<" in site_summary_xml,
            "Summary lists each populated category with its element count"
        )

        site_beam_xml = site_archive.read(
            "xl/worksheets/sheet2.xml"
        ).decode("utf-8")

        check(
            '<mergeCell ref="A5:A6"/>' in site_beam_xml
            and '<mergeCell ref="B5:B6"/>' in site_beam_xml,
            "Detail sheet vertically merges SNO/MARK header cells "
            "(selection-only layout)"
        )

        check(
            ">B1<" in site_beam_xml and ">B2<" in site_beam_xml
            and "<f>ROUND" in site_beam_xml,
            "Detail element rows carry selected MARK values and "
            "SHUTTERING formula"
        )

        site_wall_xml = site_archive.read(
            "xl/worksheets/sheet3.xml"
        ).decode("utf-8")

        check(
            ">SW1<" in site_wall_xml
            and ">QTY: THICKNESS (M)<" in site_wall_xml
            and ">QTY: COUNT<" in site_wall_xml
            and "<f>ROUND(2*" in site_wall_xml,
            "Structure Wall site detail retains selected Thickness/Count and 2LH formula"
        )

        site_rebar_xml = site_archive.read(
            "xl/worksheets/sheet4.xml"
        ).decode("utf-8")

        check(
            ">LEVEL<" in site_rebar_xml
            and ">Level 1<" in site_rebar_xml
            and ">REBAR: DIAMETER (MM)<" in site_rebar_xml
            and ">REBAR: TOTAL WEIGHT (KG)<" in site_rebar_xml
            and ">10.667<" in site_rebar_xml
            and "SHUTTERING (SQM)" not in site_rebar_xml,
            "P4 Site Rebar sheet exports Level/weight fields without formwork columns"
        )

        site_rebar_summary_xml = site_archive.read(
            "xl/worksheets/sheet5.xml"
        ).decode("utf-8")
        site_rebar_bbs_xml = site_archive.read(
            "xl/worksheets/sheet6.xml"
        ).decode("utf-8")
        check(
            ">REBAR DIAMETER SUMMARY<" in site_rebar_summary_xml
            and ">TOTAL WEIGHT (TON)<" in site_rebar_summary_xml
            and ">0.0107<" in site_rebar_summary_xml,
            "P5 Site workbook includes diameter-wise steel summary"
        )
        check(
            ">REBAR BENDING SCHEDULE<" in site_rebar_bbs_xml
            and ">A (MM)<" in site_rebar_bbs_xml
            and ">CUTTING LENGTH (M)<" in site_rebar_bbs_xml
            and ">LENGTH STATUS<" in site_rebar_bbs_xml
            and (">3000<" in site_rebar_bbs_xml
                 or ">3000.0<" in site_rebar_bbs_xml),
            "P5 Site workbook includes shape dimensions and cutting length"
        )

        site_styles_xml = site_archive.read(
            "xl/styles.xml"
        ).decode("utf-8")

        check(
            'rgb="FFFCE8D5"' in site_styles_xml,
            "Site styles define the Ember light band fill"
        )

        # ---- Merge-grid integrity (owner saw Excel's repair prompt) ----
        # A degenerate (single-cell), duplicate or overlapping mergeCell
        # span makes Excel raise "We found a problem with some content".
        # This pass mechanically disproves that class of corruption on
        # EVERY generated site worksheet.
        problem_spans = []
        total_span_count = 0

        for part_index in range(1, len(sheet_order_site) + 1):

            sheet_part_name = "xl/worksheets/sheet{0}.xml".format(
                part_index
            )

            sheet_xml_text = site_archive.read(
                sheet_part_name
            ).decode("utf-8")

            refs = re.findall(
                r'<mergeCell ref="([^"]+)"/>',
                sheet_xml_text
            )

            total_span_count += len(refs)

            sheet_bounds = []

            for ref in refs:

                try:
                    start_ref, end_ref = ref.split(":")

                    def _parse_cell(cell_text):
                        cell_match = re.match(
                            r"([A-Z]+)(\d+)",
                            cell_text
                        )

                        letters = cell_match.group(1)
                        digits = int(cell_match.group(2))

                        column_number = 0

                        for letter in letters:
                            column_number = (
                                column_number * 26
                                + ord(letter) - 64
                            )

                        return digits, column_number

                    row_a, col_a = _parse_cell(start_ref)
                    row_b, col_b = _parse_cell(end_ref)
                except Exception:
                    problem_spans.append(
                        "{} malformed {}".format(sheet_part_name, ref)
                    )
                    continue

                bounds = (
                    min(row_a, row_b),
                    min(col_a, col_b),
                    max(row_a, row_b),
                    max(col_a, col_b)
                )

                if bounds[:2] == bounds[2:]:
                    problem_spans.append(
                        "{0} degenerate {1}".format(
                            sheet_part_name,
                            ref
                        )
                    )
                    continue

                if bounds in sheet_bounds:
                    problem_spans.append(
                        "{0} duplicate {1}".format(
                            sheet_part_name,
                            ref
                        )
                    )
                    continue

                for existing in sheet_bounds:
                    overlaps = not (
                        bounds[2] < existing[0]
                        or existing[2] < bounds[0]
                        or bounds[3] < existing[1]
                        or existing[3] < bounds[1]
                    )

                    if overlaps:
                        problem_spans.append(
                            "{0} overlapping {1} vs prior span"
                            .format(sheet_part_name, ref)
                        )
                        break

                sheet_bounds.append(bounds)

        check(
            total_span_count > 0 and not problem_spans,
            "Merge grid clean on all site sheets: {0} spans, zero "
            "degenerate/duplicate/overlapping (problems={1})".format(
                total_span_count,
                problem_spans
            )
        )

        # ---- Bordered grid wiring ----
        cellxfs_body = site_styles_xml.split("<cellXfs")[1].split(
            "</cellXfs>"
        )[0]

        xf_openings = re.findall(r"<xf [^>]*>", cellxfs_body)

        bordered_style_indexes = [
            position
            for position, opening in enumerate(xf_openings)
            if 'borderId="2"' in opening
        ]

        check(
            '<left style="thin"' in site_styles_xml
            and len(bordered_style_indexes) >= 6,
            "Styles expose the full thin-border box and wire it into "
            "{} grid formats".format(len(bordered_style_indexes))
        )

        row7_search = re.search(
            r'<row r="7">(.*?)</row>',
            site_beam_xml,
            re.S
        )

        row7_attributes = []

        if row7_search:
            row7_attributes = re.findall(
                r'<c r="[A-Z]+7"([^<>]*)>',
                row7_search.group(1)
            )

        unbordered_cells = []

        for cell_attributes in row7_attributes:

            style_match = re.search(
                r' s="(\d+)"',
                cell_attributes
            )

            if style_match is None:
                unbordered_cells.append(cell_attributes)
                continue

            try:
                style_number = int(style_match.group(1))
            except Exception:
                unbordered_cells.append(cell_attributes)
                continue

            if style_number not in bordered_style_indexes:
                unbordered_cells.append(cell_attributes)

        check(
            bool(row7_attributes) and not unbordered_cells,
            "Every first data-row cell carries a bordered grid style "
            "(offenders={})".format(unbordered_cells)
        )

    finally:

        site_archive.close()

        try:
            os.remove(site_output_path)
        except:
            pass

    # -----------------------------------------------------------------
    # v1.9.0 Structure Wall collection/UI contract.
    # -----------------------------------------------------------------
    class FakeWallBuiltInParameter(object):
        WALL_STRUCTURAL_SIGNIFICANT = "wall_structural"

    class FakeWallDB(object):
        BuiltInParameter = FakeWallBuiltInParameter

    class FakeWallFlag(object):
        def __init__(self, value):
            self.value = value

        def AsInteger(self):
            return self.value

    class FakeWall(object):
        def __init__(self, value):
            self.flag = (
                None if value is None else FakeWallFlag(value)
            )

        def get_Parameter(self, _parameter_id):
            return self.flag

        def LookupParameter(self, _name):
            return self.flag

    wall_filter_ns = {"DB": FakeWallDB}
    wall_filter_block, _ = extract_from_sources(
        texts, "is_structural_wall"
    )
    exec(wall_filter_block, wall_filter_ns)
    check(
        wall_filter_ns["is_structural_wall"](FakeWall(1)) is True
        and wall_filter_ns["is_structural_wall"](FakeWall(0)) is False
        and wall_filter_ns["is_structural_wall"](FakeWall(None)) is False,
        "Structure Wall collector accepts only Structural-flag walls"
    )

    class FakeParameterItem(object):
        def __init__(self, name):
            self.Name = name

    class FakeDefinition(object):
        def __init__(self, name):
            self.Name = name

    class FakeParameter(object):
        def __init__(self, name):
            self.Definition = FakeDefinition(name)

    class FakeParameterElement(object):
        Parameters = [FakeParameter("Mark")]

    namespace["ParameterItem"] = FakeParameterItem
    wall_available = namespace["get_parameters"](
        [FakeParameterElement()],
        ("Qty: Thickness (m)", "Qty: Count")
    )
    wall_available_names = [item.Name for item in wall_available]
    check(
        "Mark" in wall_available_names
        and "Qty: Thickness (m)" in wall_available_names
        and "Qty: Count" in wall_available_names,
        "Structure Wall Available list includes calculated Thickness and Count"
    )

    rebar_derived_names = (
        "Level",
        "Rebar: Bar Mark",
        "Rebar: Diameter (mm)",
        "Rebar: Shape",
        "Rebar: Quantity",
        "Rebar: Bar Length (m)",
        "Rebar: Cutting Length (m)",
        "Rebar: Total Length (m)",
        "Rebar: Unit Weight (kg/m)",
        "Rebar: Total Weight (kg)",
        "Rebar: Element ID",
        "Rebar: Host Element ID",
        "Rebar: Host Category",
        "Rebar: A (mm)", "Rebar: B (mm)", "Rebar: C (mm)",
        "Rebar: D (mm)", "Rebar: E (mm)", "Rebar: F (mm)",
        "Rebar: G (mm)", "Rebar: H (mm)",
        "Rebar: Bend Diameter (mm)",
        "Rebar: Hook at Start", "Rebar: Hook at End"
    )
    rebar_available = namespace["get_parameters"](
        [FakeParameterElement()],
        rebar_derived_names
    )
    rebar_available_names = [item.Name for item in rebar_available]

    with io.open(UI_PATH, "r", encoding="utf-8-sig") as ui_handle:
        ui_text = ui_handle.read()
    script_text = next(
        source for path, source in texts if path == SCRIPT_PATH
    )
    try:
        minidom.parseString(ui_text.encode("utf-8"))
        ui_valid = True
    except Exception:
        ui_valid = False
    required_wall_controls = (
        "StructureWallSearch", "StructureWallAvailable",
        "StructureWallSelected", "StructureWallAdd",
        "StructureWallRemove", "StructureWallUp", "StructureWallDown",
        "StructureWallTop", "StructureWallBottom"
    )
    check(
        ui_valid
        and 'Header="Structure Wall"' in ui_text
        and all(name in ui_text for name in required_wall_controls),
        "Structure Wall XAML tab is valid and exposes every wired control"
    )

    required_assembly_controls = (
        "AssemblyProfileName", "AssemblyProfileSource",
        "AssemblyBindingWireFactor", "AssemblyCoverBlockFactor",
        "AssemblyLabourFactor"
    )
    check(
        ui_valid
        and 'Header="Assembly Profile"' in ui_text
        and all(name in ui_text for name in required_assembly_controls)
        and 'settings["assembly_profile"]' in script_text
        and "assembly_profile=assembly_profile" in script_text,
        "P6 Assembly Profile UI, persistence and exporter wiring are present"
    )
    check(
        'x:Name="StatusText"' in ui_text
        and 'TextTrimming="CharacterEllipsis"' in ui_text
        and 'ToolTip="{Binding Text, RelativeSource={RelativeSource Self}}"' in ui_text
        and 'x:Name="SiteFormatCheck"' in ui_text
        and 'x:Name="IncludeFormworkCheck"' in ui_text
        and '<ColumnDefinition Width="*"/>' in ui_text,
        "v1.15.1 footer keeps options visible while long status text truncates"
    )

    required_rebar_controls = (
        "RebarSearch", "RebarAvailable", "RebarSelected", "RebarAdd",
        "RebarRemove", "RebarUp", "RebarDown", "RebarTop", "RebarBottom"
    )
    check(
        'Header="Rebar"' in ui_text
        and all(name in ui_text for name in required_rebar_controls)
        and "DB.BuiltInCategory.OST_Rebar" in script_text
        and "get_rebar_quantities(element)" in script_text,
        "P4 Rebar tab, collection and quantity adapter are wired"
    )
    check(
        all(name in rebar_available_names for name in rebar_derived_names)
        and "derived_names = REBAR_DERIVED_PARAMETERS" in script_text,
        "Rebar Available list includes every automatic P4 export column"
    )
    check(
        "from collections import OrderedDict" in script_text
        and "row = OrderedDict([" in script_text,
        "IP27 rows preserve Selected parameter order with OrderedDict"
    )

    def nested_handler_source(name):
        match = re.search(
            r"^(?P<indent>[ \t]+)def {0}\(".format(re.escape(name)),
            script_text,
            re.M
        )
        if match is None:
            raise AssertionError("Could not find nested handler: {}".format(name))
        tail = script_text[match.end():]
        next_handler = re.search(
            r"^{0}def ".format(re.escape(match.group("indent"))),
            tail,
            re.M
        )
        end = (
            match.end() + next_handler.start()
            if next_handler is not None
            else len(script_text)
        )
        return script_text[match.start():end]

    persistent_selection_handlers = (
        "add_parameters", "remove_parameters",
        "move_up", "move_down", "move_top", "move_bottom",
        "apply_parameters", "export_to_excel"
    )
    check(
        all(
            "capture_and_save_settings()" in nested_handler_source(name)
            for name in persistent_selection_handlers
        )
        and "window.Closing += save_before_window_close" in script_text
        and "capture_and_save_settings()" in nested_handler_source(
            "save_before_window_close"
        ),
        "Selected parameter choices/order autosave after edits, actions and window close"
    )
    capture_source = nested_handler_source("capture_and_save_settings")
    check(
        "settings = load_app_settings()" in capture_source
        and capture_source.index("settings = load_app_settings()")
        < capture_source.index('settings["selected"] = {}'),
        "Selection autosave preserves unrelated settings such as last export folder"
    )
    export_handler_source = nested_handler_source("export_to_excel")
    check(
        "if use_site_format:" in export_handler_source
        and "parameter_metadata = {}" in export_handler_source
        and "include_grade=True" in export_handler_source
        and "metadata_seconds" in export_handler_source
        and "data_seconds" in export_handler_source
        and "workbook_seconds" in export_handler_source,
        "Fast Site export skips Classic metadata work, keeps P10 grade resolution and reports phase timings"
    )
    check(
        'needs_bbox = element_name in ("Slab", "Foundation")' in script_text
        and "level_cache = {}" in script_text
        and "get_element_level(element, level_cache)" in script_text,
        "Fast Revit data path caches levels and avoids unnecessary framing bounding boxes"
    )

    class FakeLevelBuiltIns(object):
        INSTANCE_REFERENCE_LEVEL_PARAM = "reference_level"
        LEVEL_PARAM = "level"
        SCHEDULE_LEVEL_PARAM = "schedule_level"

    class FakeLevelStorage(object):
        ElementId = "ElementId"

    class FakeLevelDB(object):
        BuiltInParameter = FakeLevelBuiltIns
        StorageType = FakeLevelStorage

    class FakeLevelId(object):
        def __init__(self, value):
            self.IntegerValue = value

    class FakeLevelElement(object):
        def __init__(self, element_id, level_id=-1, host_id=-1, name=""):
            self.Id = FakeLevelId(element_id)
            self.LevelId = FakeLevelId(level_id)
            self._host_id = FakeLevelId(host_id)
            self.Name = name

        def get_Parameter(self, _parameter_id):
            return None

        def GetHostId(self):
            return self._host_id

    level = FakeLevelElement(100, name="Level 1")
    host = FakeLevelElement(200, level_id=100)
    hosted_rebar = FakeLevelElement(400, host_id=200)

    class FakeLevelDoc(object):
        def GetElement(self, element_id):
            return {
                100: level,
                200: host,
                400: hosted_rebar,
            }.get(element_id.IntegerValue)

    level_ns = {"DB": FakeLevelDB, "doc": FakeLevelDoc()}
    level_block, _ = extract_from_sources(texts, "get_element_level")
    exec(level_block, level_ns)
    check(
        level_ns["get_element_level"](hosted_rebar) == "Level 1",
        "P5 hosted Rebar inherits Level from its Beam/Column/Wall host"
    )

    # -----------------------------------------------------------------
    # v1.8.10 centralized RCC classification and routing regression.
    # This is the production acceptance matrix: both physical categories
    # can route to either logical sheet, codes use strict boundaries,
    # Chajja stays in Slab, and the audit proves no duplicates/missing rows.
    # -----------------------------------------------------------------
    routing_ns = {
        "re": re,
        "safe_text": lambda value, fallback="": (
            fallback if value is None else str(value)
        ),
        "find_parameter_with_scope": lambda element, name: (
            getattr(element, "parameter_map", {}).get(name),
            "Instance"
        ),
        "find_parameter_on_element": lambda element, name, **kwargs: (
            getattr(element, "parameter_map", {}).get(name)
        ),
        "safe_parameter_value": lambda parameter: (
            "" if parameter is None else parameter.value
        ),
    }
    for classifier_name in (
        "normalize_label",
        "code_token_match",
        "_contains_rcc_identity_signal",
        "_built_in_parameter_text",
        "get_element_identity_text",
        "_read_identity_parameter",
        "_element_source_category",
        "_element_family_type_names",
        "_element_routing_key",
        "_safe_element_id_text",
        "classify_identity_text",
        "_route",
        "classify_rcc_element",
        "build_logical_rcc_collections",
        "validate_classification_audit",
        "classification_audit_has_findings",
        "classification_audit_detail_results",
        "build_compact_classification_findings",
    ):
        block, _ = extract_from_sources(texts, classifier_name)
        exec(block, routing_ns)

    class FakeId(object):
        def __init__(self, value):
            self.IntegerValue = value

    class FakeCategory(object):
        def __init__(self, name):
            self.Name = name

    class FakeDefinition(object):
        def __init__(self, name):
            self.Name = name

    class FakeParameter(object):
        def __init__(self, name, value):
            self.Definition = FakeDefinition(name)
            self.value = value
            self.HasValue = value not in (None, "")

    class FakeBuiltInParameter(object):
        ELEM_TYPE_PARAM = "ELEM_TYPE_PARAM"
        SYMBOL_NAME_PARAM = "SYMBOL_NAME_PARAM"
        ALL_MODEL_TYPE_NAME = "ALL_MODEL_TYPE_NAME"
        ELEM_FAMILY_PARAM = "ELEM_FAMILY_PARAM"
        SYMBOL_FAMILY_NAME_PARAM = "SYMBOL_FAMILY_NAME_PARAM"
        ALL_MODEL_FAMILY_NAME = "ALL_MODEL_FAMILY_NAME"

    class FakeDB(object):
        BuiltInParameter = FakeBuiltInParameter

    routing_ns["DB"] = FakeDB

    class FakeElement(object):
        next_id = 1000

        def __init__(
            self, name, category, element_id=None, parameter_values=None,
            built_in_values=None
        ):
            self.Name = name
            self.Category = FakeCategory(category)
            if element_id is None:
                element_id = FakeElement.next_id
                FakeElement.next_id += 1
            self.Id = FakeId(element_id)
            self.parameter_map = {}
            for parameter_name, value in (parameter_values or {}).items():
                self.parameter_map[parameter_name] = FakeParameter(
                    parameter_name, value
                )
            self.Parameters = list(self.parameter_map.values())
            self.built_in_map = {}
            for parameter_name, value in (built_in_values or {}).items():
                self.built_in_map[parameter_name] = FakeParameter(
                    parameter_name, value
                )

        def get_Parameter(self, parameter_id):
            return self.built_in_map.get(parameter_id)

    def classify_name(name, category):
        return routing_ns["classify_rcc_element"](
            FakeElement(name, category), category
        )

    direct_cases = (
        ("F1", "Floors", "Foundation", "Footing"),
        ("F10", "Floors", "Foundation", "Footing"),
        ("CF2", "Floors", "Foundation", "Combined Footing"),
        ("F2A", "Structural Foundations", "Foundation", "Footing"),
        ("CF1A", "Floors", "Foundation", "Combined Footing"),
        ("WF1", "Structural Foundations", "Foundation", "Footing"),
        ("Foundation Slab: F2A", "Structural Foundations", "Foundation", "Footing"),
        ("Foundation Slab: WF2", "Structural Foundations", "Foundation", "Footing"),
        ("PCC_FOOTING", "Floors", "Foundation", "PCC"),
        ("RAFT_PCC", "Floors", "Foundation", "PCC"),
        ("RCC_SLAB_F1", "Floors", "Foundation", "Footing"),
        ("S1", "Structural Foundations", "Slab", "Slab"),
        ("GS", "Structural Foundations", "Slab", "Grade Slab"),
        ("GRADE-SLAB", "Structural Foundations", "Slab", "Grade Slab"),
        ("FOLD_SLAB", "Structural Foundations", "Slab", "Fold Slab"),
        ("RCC Chajja", "Structural Foundations", "Slab", "Slab"),
        ("LOBBY", "Floors", "Slab", "Slab"),
        ("ramp", "Floors", "Slab", "Slab"),
    )
    for name, category, expected_group, expected_subtype in direct_cases:
        result = classify_name(name, category)
        check(
            result["logical_group"] == expected_group
            and result["subtype"] == expected_subtype
            and bool(result["reason"]),
            "Routing: {} {} -> {}/{}".format(
                category, name, result["logical_group"], result["subtype"]
            )
        )

    for unsafe_name in ("F", "SF", "FLOOR", "FOLD", "WF", "F2AB"):
        unsafe = classify_name(unsafe_name, "Floors")
        check(
            unsafe["logical_group"] == "Slab"
            and unsafe["subtype"] == "Other",
            "Strict code boundary rejects '{}' as a footing".format(
                unsafe_name
            )
        )

    parameter_footing = routing_ns["classify_rcc_element"](
        FakeElement(
            "RCC_SLAB_200MM",
            "Floors",
            parameter_values={"ID_UNMT": "CF2"}
        ),
        "Floors"
    )
    parameter_chajja = routing_ns["classify_rcc_element"](
        FakeElement(
            "GENERIC FOUNDATION",
            "Structural Foundations",
            parameter_values={"ITEM DES.": "Chajja 01"}
        ),
        "Structural Foundations"
    )
    check(
        parameter_footing["logical_group"] == "Foundation"
        and parameter_footing["subtype"] == "Combined Footing",
        "Reliable ID_UNMT value overrides slab-like family wording"
    )
    check(
        parameter_chajja["logical_group"] == "Slab",
        "Reliable ITEM DES. routes Foundation-stored Chajja to Slab"
    )

    system_floor = routing_ns["classify_rcc_element"](
        FakeElement(
            "Floor",
            "Floors",
            element_id=3201775,
            built_in_values={
                "ELEM_TYPE_PARAM": "ramp",
                "ELEM_FAMILY_PARAM": "Floor",
            }
        ),
        "Floors"
    )
    check(
        system_floor["logical_group"] == "Slab"
        and system_floor["subtype"] == "Slab"
        and system_floor["family"] == "Floor"
        and system_floor["type_name"] == "ramp",
        "System Floor built-in Type fallback routes and reports ramp"
    )

    case_a_foundation_names = (
        "F1", "F2", "CF1", "CF2", "PCC", "Raft",
    )
    case_a_slab_names = (
        "Grade Slab", "Slab", "Chajja", "Fold Slab",
    )
    case_a = routing_ns["build_logical_rcc_collections"](
        [],
        [
            FakeElement(name, "Structural Foundations")
            for name in case_a_foundation_names + case_a_slab_names
        ],
        routing_ns["classify_rcc_element"],
    )
    check(
        [e.Name for e in case_a["Foundation"]]
        == list(case_a_foundation_names)
        and [e.Name for e in case_a["Slab"]] == list(case_a_slab_names),
        "Case A: Structural Foundation elements route by logical identity"
    )

    case_b_foundation_names = ("F1", "CF1", "PCC", "Raft")
    case_b_slab_names = (
        "S1", "S2", "GS", "Grade Slab", "Fold Slab", "Chajja",
    )
    case_b = routing_ns["build_logical_rcc_collections"](
        [
            FakeElement(name, "Floors")
            for name in case_b_foundation_names + case_b_slab_names
        ],
        [],
        routing_ns["classify_rcc_element"],
    )
    check(
        [e.Name for e in case_b["Foundation"]]
        == list(case_b_foundation_names)
        and [e.Name for e in case_b["Slab"]] == list(case_b_slab_names),
        "Case B: Floor elements route by logical identity"
    )

    mixed_foundation = ("F1", "F2", "PCC", "Raft", "GS", "Chajja")
    mixed_floors = ("S1", "S2", "CF1", "PCC_FOOTING")
    mixed = routing_ns["build_logical_rcc_collections"](
        [FakeElement(name, "Floors") for name in mixed_floors],
        [
            FakeElement(name, "Structural Foundations")
            for name in mixed_foundation
        ],
        routing_ns["classify_rcc_element"],
    )
    check(
        [e.Name for e in mixed["Slab"]] == [
            "S1", "S2", "GS", "Chajja"
        ]
        and [e.Name for e in mixed["Foundation"]] == [
            "CF1", "PCC_FOOTING", "F1", "F2", "PCC", "Raft"
        ],
        "Mixed project: both source categories route with no missing rows"
    )
    valid_audit, audit_summary = routing_ns[
        "validate_classification_audit"
    ](mixed["audit"])
    check(
        valid_audit
        and mixed["audit"]["eligible_unique"] == 10
        and not mixed["audit"]["destination_duplicate_ids"]
        and not mixed["audit"]["unclassified"],
        "Classification audit reconciles all mixed-project rows ({})".format(
            audit_summary
        )
    )
    check(
        not routing_ns["classification_audit_has_findings"](
            mixed["audit"]
        ),
        "Healthy classification audit stays silent"
    )

    duplicate = FakeElement("F1", "Floors", element_id=9999)
    duplicate_route = routing_ns["build_logical_rcc_collections"](
        [duplicate], [duplicate],
        routing_ns["classify_rcc_element"],
    )
    check(
        duplicate_route["audit"]["eligible_unique"] == 1
        and duplicate_route["audit"]["source_duplicate_ids"] == ["9999"]
        and not duplicate_route["audit"]["destination_duplicate_ids"],
        "Duplicate source ElementId is reported and exported exactly once"
    )
    check(
        routing_ns["classification_audit_has_findings"](
            duplicate_route["audit"]
        ),
        "Classification audit emits diagnostics when findings exist"
    )
    duplicate_details = routing_ns[
        "classification_audit_detail_results"
    ](duplicate_route["audit"])
    check(
        len(duplicate_details) == 1
        and duplicate_details[0]["element_id"] == "9999",
        "Classification diagnostics include only the duplicate finding row"
    )

    one_other = routing_ns["build_logical_rcc_collections"](
        [
            FakeElement("S1", "Floors"),
            FakeElement("UNMAPPED", "Floors"),
            FakeElement("S2", "Floors"),
        ],
        [],
        routing_ns["classify_rcc_element"],
    )
    other_details = routing_ns[
        "classification_audit_detail_results"
    ](one_other["audit"])
    check(
        len(other_details) == 1
        and other_details[0]["subtype"] == "Other",
        "Classification diagnostics exclude healthy rows around an Other route"
    )
    compact_other = routing_ns["build_compact_classification_findings"](
        one_other["audit"]
    )
    check(
        "ID {}".format(other_details[0]["element_id"]) in compact_other
        and "Floors" in compact_other
        and "Unknown identity retained" in compact_other
        and "S1" not in compact_other
        and "S2" not in compact_other,
        "Completion popup compactly identifies only Other routing elements"
    )

    # -----------------------------------------------------------------
    # v1.21.0 P10 Unmapped Element Report (pure validation engine).
    # Feeds the real classifier audit rows above through the engine so the
    # routing contract between script.py and lib/validation_engine.py stays
    # exercised, then proves both workbook writers publish the sheet.
    # -----------------------------------------------------------------
    import validation_engine

    other_id = str(other_details[0]["element_id"])
    unmapped_data = {
        "Beam": [
            {"Element ID": "1", "Level": "L1", "Grade": "M30",
             "Qty: Volume (m3)": 0.5},
            {"Element ID": "2", "Level": "L1", "Grade": "(No Grade)",
             "Qty: Volume (m3)": 0.4},
        ],
        "Column": [
            {"Element ID": "3", "Level": "L2", "Grade": "",
             "Qty: Volume (m3)": ""},
            {"Element ID": "4", "Level": "L2", "Grade": "M40",
             "Qty: Volume (m3)": "0"},
            {"Element ID": "5", "Level": "L2", "Grade": "M40",
             "Qty: Volume (m3)": "n/a"},
        ],
        "Slab": [
            {"Element ID": "6", "Level": "L3"},
            {"Element ID": other_id, "Level": "L3", "Grade": "M25",
             "Qty: Volume (m3)": 1.2},
        ],
        "Rebar": [
            {"Element ID": "9", "Level": "L1",
             "Rebar: Total Weight (kg)": ""},
        ],
    }
    p10_findings = validation_engine.collect_routing_findings(
        list(other_details) + [{
            "element_id": "777", "subtype": "Other",
            "logical_group": "Slab", "reason": "Filtered out of export",
        }],
        ["888", other_id]
    )
    check(
        [(item["element_id"], item["issue"]) for item in p10_findings] == [
            (other_id, validation_engine.ISSUE_UNCERTAIN_ROUTING),
            (other_id, validation_engine.ISSUE_DUPLICATE_ROUTING),
            ("777", validation_engine.ISSUE_UNCERTAIN_ROUTING),
            ("888", validation_engine.ISSUE_DUPLICATE_ROUTING),
        ]
        and "Unknown identity retained" in p10_findings[0]["detail"],
        "P10 routing findings flatten real classifier audit rows and duplicate IDs"
    )
    p10_report = validation_engine.build_unmapped_element_report(
        unmapped_data, p10_findings
    )
    check(
        p10_report[0] == ["Category", "Element ID", "Level", "Issue", "Detail"],
        "P10 report headers are Category / Element ID / Level / Issue / Detail"
    )
    check(
        [(row[0], row[1], row[3]) for row in p10_report[1:]] == [
            ("Beam", "2", validation_engine.ISSUE_MISSING_GRADE),
            ("Column", "3", validation_engine.ISSUE_MISSING_GRADE),
            ("Column", "3", validation_engine.ISSUE_MISSING_VOLUME),
            ("Column", "4", validation_engine.ISSUE_MISSING_VOLUME),
            ("Column", "5", validation_engine.ISSUE_MISSING_VOLUME),
            ("Slab", other_id, validation_engine.ISSUE_UNCERTAIN_ROUTING),
            ("Slab", other_id, validation_engine.ISSUE_DUPLICATE_ROUTING),
        ],
        "P10 flags (No Grade)/blank grade and blank/zero/non-numeric volume; "
        "skips Rebar, rows without those columns and non-exported routing IDs"
    )
    check(
        all(
            row[4] == validation_engine.MISSING_GRADE_DETAIL
            for row in p10_report[1:]
            if row[3] == validation_engine.ISSUE_MISSING_GRADE
        )
        and "GRADE OF CONCRETE" in validation_engine.MISSING_GRADE_DETAIL
        and "Grade" in validation_engine.MISSING_GRADE_DETAIL
        and "material" not in validation_engine.MISSING_GRADE_DETAIL.lower()
        and "identity" not in validation_engine.MISSING_GRADE_DETAIL.lower(),
        "P10 missing-grade detail names only the two authoritative fields"
    )
    check(
        all(row[2] == "L3" for row in p10_report[1:] if row[1] == other_id),
        "P10 routing findings inherit the exported element category and level"
    )
    check(
        validation_engine.build_unmapped_element_report(
            {"Beam": [{"Element ID": "1", "Level": "L1", "Grade": "M30",
                       "Qty: Volume (m3)": 0.5}]},
            []
        ) == [["Category", "Element ID", "Level", "Issue", "Detail"]],
        "P10 clean export yields a header-only report"
    )

    # ------------------------------------------------------------
    # P9 compact validation report (v1.25.8)
    #
    # Deliberately summarizes `p10_report` - the same table the workbook
    # sheet is built from - so the count a person reads before export can
    # never disagree with the rows they find afterwards.
    # ------------------------------------------------------------
    # ------------------------------------------------------------
    # P9 missing parameters and missing rebar (v1.25.11)
    #
    # Both refuse to report what a project does not use: a parameter its
    # own category leaves blank everywhere, or rebar in a model that
    # models none. Without that, each would bury the real findings.
    # ------------------------------------------------------------
    p9_param_data = {
        "Beam": [
            {"Element ID": "1", "ID_UNMT": "B1", "NEVER_USED": ""},
            {"Element ID": "2", "ID_UNMT": "B2", "NEVER_USED": ""},
            {"Element ID": "3", "ID_UNMT": "", "NEVER_USED": ""},
            {"Element ID": "4", "ID_UNMT": "B4", "NEVER_USED": ""},
        ]
    }
    p9_param_findings = validation_engine.collect_missing_parameter_findings(
        p9_param_data)
    check(
        [(row["element_id"], row["issue"]) for row in p9_param_findings]
        == [("3", validation_engine.ISSUE_MISSING_PARAMETER)]
        and "3 of 4" in p9_param_findings[0]["detail"],
        "P9 reports a blank parameter its own category otherwise fills"
    )
    check(
        all("NEVER_USED" not in row["detail"] for row in p9_param_findings),
        "P9 ignores a parameter this project fills nowhere, instead of "
        "flagging every element"
    )
    check(
        validation_engine.collect_missing_parameter_findings(
            {"Beam": [{"Element ID": "1", "ID_UNMT": "B1"},
                      {"Element ID": "2", "ID_UNMT": "B2"}]}) == [],
        "P9 reports nothing when every element carries the parameter"
    )
    check(
        validation_engine.collect_missing_parameter_findings(
            {"Beam": [{"Element ID": "1", "Qty: Volume (m3)": "",
                       "Level": "", "Grade": ""},
                      {"Element ID": "2", "Qty: Volume (m3)": 1.0,
                       "Level": "L1", "Grade": "M30"}]}) == [],
        "P9 never reports the export's own columns as missing parameters"
    )

    # Rebar: silent on a model that models none, specific once it does.
    p9_rebar_data = {
        "Beam": [{"Element ID": "1"}, {"Element ID": "2"},
                 {"Element ID": "3"}]
    }
    check(
        validation_engine.collect_missing_rebar_findings(p9_rebar_data) == [],
        "P9 stays silent about rebar in a model that models none"
    )
    p9_rebar_data["Rebar"] = [{"Rebar: Host Element ID": "1"},
                              {"Rebar: Host Element ID": "1"}]
    check(
        [row["element_id"] for row in
         validation_engine.collect_missing_rebar_findings(p9_rebar_data)]
        == ["2", "3"],
        "P9 names the concrete elements no rebar is hosted by"
    )
    check(
        validation_engine.issue_severity(
            validation_engine.ISSUE_MISSING_PARAMETER) == "Warning"
        and validation_engine.issue_severity(
            validation_engine.ISSUE_MISSING_REBAR) == "Warning",
        "P9 treats both new checks as warnings, not errors"
    )

    check(
        "collect_missing_parameter_findings(" in export_handler_source
        and "collect_missing_rebar_findings(" in export_handler_source,
        "P9 export handler feeds both new checks into the one report"
    )

    p9_summary = validation_engine.summarize_validation_findings(p10_report)
    check(
        [(entry["issue"], entry["count"], entry["severity"])
         for entry in p9_summary] == [
            (validation_engine.ISSUE_MISSING_VOLUME, 3, "Error"),
            (validation_engine.ISSUE_DUPLICATE_ROUTING, 1, "Error"),
            (validation_engine.ISSUE_MISSING_GRADE, 2, "Warning"),
            (validation_engine.ISSUE_UNCERTAIN_ROUTING, 1, "Warning"),
        ],
        "P9 summary groups findings by issue, errors first then by count"
    )
    check(
        validation_engine.count_validation_findings(p10_report) == (4, 3, 7)
        and sum(entry["count"] for entry in p9_summary) == len(p10_report) - 1,
        "P9 counts every report row exactly once as an error or a warning"
    )
    check(
        p9_summary[0]["categories"] == {"Column": 3}
        and p9_summary[2]["categories"] == {"Beam": 1, "Column": 1},
        "P9 summary says which categories an issue came from"
    )

    p9_report = validation_engine.build_validation_report(p10_report)
    check(
        p9_report["ok"] is False
        and p9_report["headline"] == "4 error(s), 3 warning(s) in 7 finding(s)"
        and p9_report["lines"][0]
        == "Error: 3 x Missing or zero volume (Column 3)"
        and p9_report["text"].startswith(p9_report["headline"]),
        "P9 report headline and first line read as a person would say them"
    )
    check(
        len(p9_report["lines"]) == 4
        and all("x " in line for line in p9_report["lines"]),
        "P9 report prints one short line per issue, not one per finding"
    )

    # A warning is worth reading but is not a reason to stop: the
    # quantities it describes are still right.
    warnings_only = [list(validation_engine.UNMAPPED_HEADERS)] + [
        ["Beam", "1", "L1", validation_engine.ISSUE_MISSING_GRADE, "d"],
        ["Slab", "2", "L1", validation_engine.ISSUE_MISSING_MATERIAL, "d"],
    ]
    warning_report = validation_engine.build_validation_report(warnings_only)
    check(
        warning_report["ok"] is True
        and warning_report["errors"] == 0
        and warning_report["warnings"] == 2,
        "P9 warnings alone leave the export ok; only errors clear that flag"
    )

    clean_report = validation_engine.build_validation_report(
        [list(validation_engine.UNMAPPED_HEADERS)])
    check(
        clean_report["ok"] is True
        and clean_report["total"] == 0
        and clean_report["lines"] == []
        and clean_report["text"] == "No validation findings",
        "P9 a clean export says so in one line and lists nothing"
    )

    # An issue this engine has never heard of must still be reported.
    unknown_table = [list(validation_engine.UNMAPPED_HEADERS)] + [
        ["Beam", "9", "L1", "Some future issue", "d"]]
    unknown_report = validation_engine.build_validation_report(unknown_table)
    check(
        unknown_report["total"] == 1
        and unknown_report["warnings"] == 1
        and "Some future issue" in unknown_report["text"],
        "P9 an unrecognized issue is reported as a warning, never dropped"
    )

    check(
        validation_engine.build_validation_report(
            p10_report, max_lines=2)["lines"][-1] == "...and 2 more issue type(s)",
        "P9 the compact report caps its lines and counts the remainder"
    )

    p9_source = io.open(
        os.path.join(LIB_DIR, "validation_engine.py"),
        "r", encoding="utf-8-sig").read()
    check(
        "import Autodesk" not in p9_source
        and "from Autodesk" not in p9_source
        and "from pyrevit" not in p9_source
        and "import pyrevit" not in p9_source,
        "P9 validation engine imports no Revit or pyRevit symbol"
    )

    # v1.22.0 P10-02: missing structural material.
    material_report = validation_engine.build_unmapped_element_report(
        {
            "Beam": [
                {"Element ID": "11", "Level": "L1", "Grade": "M30",
                 "Qty: Volume (m3)": 0.5},
                {"Element ID": "12", "Level": "L1", "Grade": "M30",
                 "Qty: Volume (m3)": 0.5},
                {"Element ID": "13", "Level": "L1", "Grade": "M30",
                 "Qty: Volume (m3)": 0.5},
            ],
            "Foundation": [
                {"Element ID": "14", "Level": "L0", "Grade": "M30",
                 "Qty: Volume (m3)": 1.0},
                {"Element ID": "15", "Level": "L0", "Grade": "M30",
                 "Qty: Volume (m3)": 1.0},
            ],
        },
        [],
        {"11": "RCC_BEAM", "12": "", "14": "<By Category>", "15": "GRADE_SLAB"}
    )
    check(
        [(row[0], row[1], row[3]) for row in material_report[1:]] == [
            ("Beam", "12", validation_engine.ISSUE_MISSING_MATERIAL),
            ("Foundation", "14", validation_engine.ISSUE_MISSING_MATERIAL),
        ],
        "P10-02 flags blank and <By Category> structural material; skips "
        "present materials and elements the export never resolved"
    )

    material_ns = {
        "safe_parameter_value": lambda parameter: (
            "" if parameter is None else parameter.value
        ),
    }
    material_constant, _ = extract_constant_from_sources(
        texts, "STRUCTURAL_MATERIAL_PARAMETER_NAMES"
    )
    exec(material_constant, material_ns)
    for material_helper in (
        "structural_material_candidates",
        "resolve_structural_material",
    ):
        material_block, _ = extract_from_sources(texts, material_helper)
        exec(material_block, material_ns)
    resolve_material = material_ns["resolve_structural_material"]

    class FakeMaterialParameter(object):
        def __init__(self, value):
            self.value = value

    check(
        resolve_material({
            "instance": {"structural material": FakeMaterialParameter("RCC_BEAM")},
            "type": {},
        }) == "RCC_BEAM"
        and resolve_material({
            "instance": {"structural material": FakeMaterialParameter("")},
            "type": {"structural material": FakeMaterialParameter("RCC_WALL")},
        }) == "RCC_WALL"
        and resolve_material({
            "instance": {},
            "type": {"structural material": FakeMaterialParameter("<By Category>")},
        }) == ""
        and resolve_material({
            "instance": {"material": FakeMaterialParameter("Concrete M25")},
            "type": {},
        }) == "Concrete M25"
        and resolve_material({"instance": {}, "type": {}}) == ""
        and resolve_material(None) == "",
        "P10-02 material resolver reads instance then type Structural Material, "
        "falls back to Material and treats <By Category> as missing"
    )

    # v1.22.2 P10-03: only owner-confirmed grade fields are authoritative.
    grade_ns = {
        "re": re,
        "safe_parameter_value": material_ns["safe_parameter_value"],
    }
    grade_line, _ = extract_constant_from_sources(
        texts, "CONCRETE_GRADE_VALUES"
    )
    exec(grade_line, grade_ns)
    exec(
        re.search(
            r"^CONCRETE_GRADE_PARAMETER_HINTS = \(.*?\)$",
            script_text,
            re.S | re.M
        ).group(0),
        grade_ns
    )
    for grade_helper in (
        "normalize_concrete_grade",
        "concrete_grade_parameter_candidates",
        "resolve_concrete_grade",
    ):
        grade_block, _ = extract_from_sources(texts, grade_helper)
        exec(grade_block, grade_ns)
    resolve_grade = grade_ns["resolve_concrete_grade"]

    class FakeGradeElement(object):
        def __init__(self, identity=""):
            self.identity = identity

    def grade_context(instance=None, type_values=None):
        return {
            "instance": dict(
                (name.lower(), FakeMaterialParameter(value))
                for name, value in (instance or {}).items()
            ),
            "type": dict(
                (name.lower(), FakeMaterialParameter(value))
                for name, value in (type_values or {}).items()
            ),
            "type_element": None,
        }

    check(
        resolve_grade(FakeGradeElement(), grade_context({
            "GRADE OF CONCRETE": "M30",
            "Grade": "M20",
            "Structural Material": "Concrete - M25",
        })) == "M30"
        and resolve_grade(FakeGradeElement(), grade_context({
            "Grade": "M40",
        })) == "M40"
        and resolve_grade(FakeGradeElement(), grade_context(
            {"Grade of Concrete": ""},
            {"Grade of Concrete": "M35"},
        )) == "M35"
        and resolve_grade(FakeGradeElement(), grade_context(
            {"Grade of Concrete": "TBD"},
            {"Grade of Concrete": "M25"},
        )) == "M25"
        and resolve_grade(FakeGradeElement(), grade_context({
            "Grade of Concrete": "TBD",
            "Grade": "M20",
        })) == "M20"
        and resolve_grade(FakeGradeElement(), grade_context({
            "Structural Material": "Concrete - M25",
        })) == "(No Grade)"
        and resolve_grade(FakeGradeElement("B1 M45"), grade_context({
            "Structural Material": "RCC_BEAM",
        })) == "(No Grade)",
        "P10-03 grade resolver uses only Grade of Concrete then Grade, "
        "falls through instance to type, and never infers from material or identity"
    )
    check(
        "element_materials = {}" in export_handler_source
        and "material_sink=element_materials" in export_handler_source
        and "material_sink[" in script_text
        and "and needs_parameter_context" in script_text,
        "P10-02 export collects materials only for indexed elements and feeds the report"
    )

    def p10_sheet_order(workbook_path):
        with zipfile.ZipFile(workbook_path, "r") as p10_archive:
            return re.findall(
                r'<sheet name="([^"]+)"',
                p10_archive.read("xl/workbook.xml").decode("utf-8")
            )

    def p10_validation(report_path):
        with io.open(report_path, "r", encoding="utf-8") as p10_json:
            return json.load(p10_json)

    p10_root = tempfile.mkdtemp(prefix="rcc-boq-p10-")
    try:
        p10_classic_data = {
            "Beam": [
                {"Element ID": "1", "Level": "L1", "Grade": "M30",
                 "Mark": "B1", "Qty: Volume (m3)": 0.5, "Qty: Count": 1},
                {"Element ID": "2", "Level": "L1", "Grade": "(No Grade)",
                 "Mark": "B2", "Qty: Volume (m3)": 0.4, "Qty: Count": 1},
            ],
        }
        classic_report = validation_engine.build_unmapped_element_report(
            p10_classic_data, []
        )
        classic_rows = namespace["write_basic_xlsx"](
            os.path.join(p10_root, "classic.xlsx"),
            p10_classic_data,
            {},
            project_name="P10 TEST",
            tool_version="RCC BOQ Parameter Manager v1.21.0",
            generated_stamp="2026-09-15 12:00",
            validation_report_path=os.path.join(p10_root, "classic.json"),
            unmapped_report=classic_report
        )
        classic_order = p10_sheet_order(os.path.join(p10_root, "classic.xlsx"))
        cover_names = set(
            row[0] for row in classic_rows["Summary"] if row
        )
        check(
            classic_order[-1] == validation_engine.UNMAPPED_SHEET_NAME
            and classic_order[-2] == "Costing"
            and classic_rows[validation_engine.UNMAPPED_SHEET_NAME]
            == classic_report
            and validation_engine.UNMAPPED_SHEET_NAME in cover_names
            and p10_validation(
                os.path.join(p10_root, "classic.json")
            ).get("ok") is True,
            "P10 Classic workbook appends a validated Unmapped Elements "
            "sheet after Costing and lists it on the cover"
        )

        namespace["write_basic_xlsx"](
            os.path.join(p10_root, "clean.xlsx"),
            p10_classic_data,
            {},
            validation_report_path=os.path.join(p10_root, "clean.json"),
            unmapped_report=[list(validation_engine.UNMAPPED_HEADERS)]
        )
        check(
            validation_engine.UNMAPPED_SHEET_NAME
            not in p10_sheet_order(os.path.join(p10_root, "clean.xlsx")),
            "P10 header-only report adds no empty tab to the workbook"
        )

        p10_site_data = {
            "Beam": [
                {"Element ID": "1", "Level": "L1", "Grade": "(No Grade)",
                 "Mark": "B1", "Qty: Volume (m3)": 0.5,
                 "Qty: Dim L (m)": 3.0, "Qty: Dim W (m)": 0.23,
                 "Qty: Dim H (m)": 0.6, "Qty: Shuttering (m2)": 4.29},
            ],
        }
        site_report = validation_engine.build_unmapped_element_report(
            p10_site_data, []
        )
        site_rows = namespace["write_site_xlsx"](
            os.path.join(p10_root, "site.xlsx"),
            p10_site_data,
            project_name="P10 TEST",
            selected_parameters={"Beam": ["Mark"]},
            validation_report_path=os.path.join(p10_root, "site.json"),
            unmapped_report=site_report
        )
        site_unmapped = site_rows.get(validation_engine.UNMAPPED_SHEET_NAME, [])
        check(
            p10_sheet_order(os.path.join(p10_root, "site.xlsx"))[-1]
            == validation_engine.UNMAPPED_SHEET_NAME
            and len(site_unmapped) > 6
            and site_unmapped[1] == ["RCC - MODEL VALIDATION"]
            and site_unmapped[2] == ["UNMAPPED ELEMENTS"]
            and site_unmapped[4][3] == ("MERGE_V", "ISSUE")
            and site_unmapped[6] == site_report[1]
            and p10_validation(
                os.path.join(p10_root, "site.json")
            ).get("ok") is True,
            "P10 Site workbook appends a validated Unmapped Elements sheet "
            "inside the site title bands"
        )
        check(
            all("GRADE" not in str(cell) for cell in site_rows["Beam"][4]),
            "P10 grade resolution adds no Grade column to Site detail sheets"
        )
        check(
            list(site_rows.keys())
            == p10_sheet_order(os.path.join(p10_root, "site.xlsx")),
            "Site writer returns sheets in workbook order for the export popup listing"
        )
    finally:
        shutil.rmtree(p10_root, ignore_errors=True)

    check(
        export_handler_source.count("unmapped_report=unmapped_report") == 2
        and "build_unmapped_element_report(" in export_handler_source
        and "classification_audit_detail_results(" in export_handler_source
        and "UNMAPPED_SHEET_NAME" in export_handler_source,
        "P10 export handler builds one report and passes it to both workbook writers"
    )

    check(
        "build_validation_report(unmapped_report)" in export_handler_source
        and 'p9_report["headline"]' in export_handler_source
        and 'p9_report["lines"]' in export_handler_source
        and "Unmapped elements: {} finding(s)" not in export_handler_source,
        "P9 export handler summarizes the same report table it writes to the sheet"
    )

    # ------------------------------------------------------------
    # Identity row ordering (v1.25.9)
    #
    # Plain text sorting reads B10 as smaller than B2, which is exactly
    # the mistake this replaces, so the checks pin the numeric ordering
    # rather than just "is sorted".
    # ------------------------------------------------------------
    import export_engine as ordering_engine

    check(
        sorted(["B10", "B2", "B1", "B2A", "B10A", "B3", "B21"],
               key=ordering_engine.identity_sort_key)
        == ["B1", "B2", "B2A", "B3", "B10", "B10A", "B21"],
        "Identity order reads the numbers as numbers: B2 before B10"
    )
    check(
        sorted(["B2", "", "B1", None], key=ordering_engine.identity_sort_key)
        == ["B1", "B2", "", None],
        "Identity order puts rows with no identity last, not first"
    )
    check(
        [row["ID_UNMT"] for row in ordering_engine.sort_rows_by_identity(
            [{"ID_UNMT": value} for value in
             ("B10", "B2", "B1", "C1", "B2A")])]
        == ["B1", "B2", "B2A", "B10", "C1"],
        "Identity order sorts the rows themselves, letters then numbers"
    )

    # A project that fills Mark instead of ID_UNMT is ordered by Mark.
    check(
        [row["Mark"] for row in ordering_engine.sort_rows_by_identity(
            [{"ID_UNMT": "", "Mark": "C10"},
             {"ID_UNMT": "", "Mark": "C2"}])] == ["C2", "C10"],
        "Identity order falls back to Mark when ID_UNMT is empty"
    )

    # A project that fills neither keeps the order the model gave, rather
    # than being shuffled by a field nobody uses.
    untouched = [{"Element ID": "3"}, {"Element ID": "1"}]
    check(
        ordering_engine.sort_rows_by_identity(untouched)
        == [{"Element ID": "3"}, {"Element ID": "1"}],
        "Identity order leaves a project that fills no identity alone"
    )

    check(
        ordering_engine.sort_rows_by_identity([]) == []
        and ordering_engine.sort_rows_by_identity(None) == [],
        "Identity order survives an empty category"
    )

    # Level first, identity inside the level - how a BOQ is read.
    level_rows = [
        {"Level": "04 1ST LEVEL", "ID_UNMT": "B10"},
        {"Level": "03 PLINTH LEVEL", "ID_UNMT": "B2"},
        {"Level": "04 1ST LEVEL", "ID_UNMT": "B2"},
        {"Level": "13 OHW/LMR LEVEL", "ID_UNMT": "B1"},
        {"Level": "12 TERRACE LEVEL", "ID_UNMT": "B1"},
        {"Level": "03 PLINTH LEVEL", "ID_UNMT": "B1"},
    ]
    check(
        [(row["Level"], row["ID_UNMT"])
         for row in ordering_engine.sort_rows_for_boq(level_rows)] == [
            ("03 PLINTH LEVEL", "B1"),
            ("03 PLINTH LEVEL", "B2"),
            ("04 1ST LEVEL", "B2"),
            ("04 1ST LEVEL", "B10"),
            ("12 TERRACE LEVEL", "B1"),
            ("13 OHW/LMR LEVEL", "B1"),
        ],
        "BOQ order is level first, then identity inside the level"
    )
    check(
        [row["Level"] for row in ordering_engine.sort_rows_for_boq(
            [{"Level": "13 OHW/LMR LEVEL"}, {"Level": "12 TERRACE LEVEL"},
             {"Level": "03 PLINTH LEVEL"}])]
        == ["03 PLINTH LEVEL", "12 TERRACE LEVEL", "13 OHW/LMR LEVEL"],
        "BOQ order reads the level number, so 12 TERRACE precedes 13 OHW/LMR"
    )
    check(
        [row["ID_UNMT"] for row in ordering_engine.sort_rows_for_boq(
            [{"ID_UNMT": "B10"}, {"ID_UNMT": "B2"}])] == ["B2", "B10"]
        and ordering_engine.sort_rows_for_boq([{"X": 2}, {"X": 1}])
        == [{"X": 2}, {"X": 1}],
        "BOQ order uses whichever of level and identity the project fills"
    )

    # ------------------------------------------------------------
    # Top-level billing (v1.25.10)
    #
    # A column runs between two floors and Revit's Level for it is the
    # base, so the level-wise BOQ was putting every column a storey low.
    # These checks pin which categories are billed to their top level and
    # that the fallback still protects an element that has no top.
    # ------------------------------------------------------------
    top_level_constant, _ = extract_constant_from_sources(
        texts, "TOP_LEVEL_CATEGORIES")
    check(
        '"Column"' in top_level_constant
        and '"Structure Wall"' in top_level_constant
        and '"Beam"' not in top_level_constant
        and '"Slab"' not in top_level_constant
        and '"Foundation"' not in top_level_constant,
        "Only Column and Structure Wall are billed to the level they support"
    )

    top_level_block, _ = extract_from_sources(texts, "get_element_top_level")
    check(
        'return ""' in top_level_block
        and "SCHEDULE_TOP_LEVEL_PARAM" in top_level_constant + top_level_block
        or "TOP_LEVEL_BUILT_IN_NAMES" in top_level_block,
        "The top-level reader returns empty rather than guessing a level"
    )

    level_choice_block, _ = extract_from_sources(texts, "build_element_data")
    check(
        "TOP_LEVEL_CATEGORIES" in level_choice_block
        and "get_element_top_level(" in level_choice_block
        and "get_element_level(" in level_choice_block,
        "build_element_data takes the top level first and falls back to the base"
    )

    ordering_block, _ = extract_from_sources(texts, "build_element_data")
    check(
        "sort_rows_for_boq(" in ordering_block,
        "build_element_data orders every category before returning it"
    )

    # ------------------------------------------------------------
    # P11 rate analysis (v1.26.0)
    #
    # The arithmetic is checked by hand below rather than against the
    # engine's own output, and the incomplete case is checked as hard as
    # the complete one: a build-up missing a figure must stay blank, not
    # price the work at zero.
    # ------------------------------------------------------------
    import costing_engine as rate_engine

    full_buildup = {
        "item_code": "RCC-M30", "description": "M30 concrete in beams",
        "unit": "m3", "material": 5200, "wastage_pct": 3,
        "labour": 1400, "machinery": 350, "overheads_pct": 12,
    }
    analysed, missing = rate_engine.compute_analysed_rate(
        rate_engine.normalize_rate_analysis(full_buildup))
    # 5200 + 3% of 5200 = 5356; + 1400 + 350 = 7106; + 12% = 7958.72
    check(
        analysed == 7958.72 and missing == [],
        "P11 wastage applies to material and overheads to the subtotal"
    )

    zero_pct = dict(full_buildup, wastage_pct=0, overheads_pct=0)
    check(
        rate_engine.compute_analysed_rate(
            rate_engine.normalize_rate_analysis(zero_pct))[0] == 6950.0,
        "P11 zero percentages are honoured, not treated as missing"
    )

    for absent in ("material", "labour", "machinery", "wastage_pct",
                   "overheads_pct"):
        partial = dict(full_buildup)
        del partial[absent]
        rate, gaps = rate_engine.compute_analysed_rate(
            rate_engine.normalize_rate_analysis(partial))
        if rate is not None or gaps != [absent]:
            check(False, "P11 a build-up missing {0} must not be priced".format(
                absent))
            break
    else:
        check(
            True,
            "P11 a build-up missing any one of the five is left unpriced"
        )

    for bad in (-1, "", "abc", None, True):
        rate, gaps = rate_engine.compute_analysed_rate(
            rate_engine.normalize_rate_analysis(
                dict(full_buildup, labour=bad)))
        if rate is not None or gaps != ["labour"]:
            check(False,
                  "P11 an unusable labour figure ({0!r}) must not be "
                  "priced".format(bad))
            break
    else:
        check(
            True,
            "P11 negative, blank, non-numeric and boolean figures are refused"
        )

    rate_table = rate_engine.build_rate_analysis_sheet([
        full_buildup,
        {"item_code": "SHUT-BM", "description": "Beam shuttering",
         "unit": "m2", "material": 180, "wastage_pct": 5, "labour": 120},
    ])
    check(
        rate_table[0] == list(rate_engine.RATE_ANALYSIS_HEADERS)
        and rate_table[1][-1] == rate_engine.STATUS_PRICED
        and rate_table[1][-2] == 7958.72,
        "P11 sheet prices a complete item and names its rate"
    )
    check(
        rate_table[2][-2] == ""
        and rate_table[2][-1].startswith(rate_engine.STATUS_INPUT_REQUIRED)
        and "machinery" in rate_table[2][-1]
        and rate_table[2][3] == 180.0,
        "P11 sheet keeps an incomplete item, blank rate, and says what is "
        "missing"
    )
    check(
        rate_engine.build_rate_analysis_sheet([])
        == [list(rate_engine.RATE_ANALYSIS_HEADERS)]
        and rate_engine.build_rate_analysis_sheet(None)
        == [list(rate_engine.RATE_ANALYSIS_HEADERS)],
        "P11 no rate analysis yields a header-only sheet"
    )

    # The store: only declared fields, junk refused, round-trip intact.
    rate_stored = rate_engine.save_rate_analysis(
        {"theme": "Auto"},
        [full_buildup,
         {"item_code": "SHUT", "unit": "m2", "material": 180,
          "wastage_pct": 5, "labour": 120, "smuggled": "nope"}])
    check(
        sorted(rate_stored.keys()) == ["rate_analysis", "theme"]
        and "smuggled" not in rate_stored["rate_analysis"][1]
        and "machinery" not in rate_stored["rate_analysis"][1]
        and rate_stored["rate_analysis"][1]["material"] == 180.0,
        "P11 store keeps only declared fields, and only the ones supplied"
    )
    check(
        rate_engine.compute_analysed_rate(
            rate_engine.load_rate_analysis(rate_stored)[0])[0] == 7958.72,
        "P11 a saved build-up prices identically when loaded back"
    )
    check(
        rate_engine.load_rate_analysis({"rate_analysis": "nonsense"}) == []
        and rate_engine.load_rate_analysis(None) == []
        and rate_engine.load_rate_analysis({}) == [],
        "P11 a corrupt or absent store cannot stop an export"
    )

    writer_source, _ = extract_from_sources(texts, "write_basic_xlsx")
    site_writer_source, _ = extract_from_sources(texts, "write_site_xlsx")
    check(
        "rate_analysis" in writer_source
        and "build_rate_analysis_sheet(rate_analysis)" in writer_source
        and "build_rate_analysis_sheet(rate_analysis)" in site_writer_source,
        "P11 both workbook formats build the Rate Analysis sheet"
    )
    check(
        "if len(rate_table) > 1:" in writer_source
        and "if len(rate_plain_table) > 1:" in site_writer_source,
        "P11 a project with no build-ups keeps its familiar workbook"
    )
    check(
        "rate_analysis=rate_analysis," in export_handler_source
        and "load_rate_analysis(" in export_handler_source,
        "P11 the export handler loads the build-ups and passes them on"
    )

    rate_source = io.open(
        os.path.join(LIB_DIR, "costing_engine.py"),
        "r", encoding="utf-8-sig").read()
    check(
        "import Autodesk" not in rate_source
        and "from pyrevit" not in rate_source
        and "wastage" in rate_engine.RATE_BASIS.lower()
        and "overheads" in rate_engine.RATE_BASIS.lower(),
        "P11 engine imports no Revit symbol and states its basis"
    )

    # ------------------------------------------------------------
    # Saved selections survive a document that has none of them (v1.26.1)
    #
    # Found live: an export run on an architectural model with no
    # structural elements discovered no parameters, restored none, and
    # then saved that emptiness over a working BOQ setup.
    # ------------------------------------------------------------
    capture_block = nested_handler_source("capture_and_save_settings")
    check(
        "previous_selected" in capture_block
        and "category_parameters.get(element_name" in capture_block,
        "Saving selections consults what this document actually discovered"
    )
    check(
        capture_block.count("settings[\"selected\"][element_name] = current") == 1
        and "if not discovered:" in capture_block,
        "An empty category with no discovered parameters keeps its saved list"
    )

    engine_guard_block, _ = extract_from_sources(
        texts, "_warn_if_not_cp3123"
    )
    check(
        "get_output" not in engine_guard_block
        and "not is_cp3123 and not is_ironpython" in engine_guard_block,
        "Known CP3123/IP27 engines do not force an output popup"
    )

    # ------------------------------------------------------------
    # P8 rule engine split (lib/rule_engine.py)
    #
    # The routing regression above already runs these rules; these
    # checks pin down *where* they come from, so a future edit cannot
    # quietly move a rule back into script.py and lose its isolation.
    # ------------------------------------------------------------
    rule_engine_path = os.path.join(LIB_DIR, "rule_engine.py")
    with io.open(rule_engine_path, "r", encoding="utf-8-sig") as handle:
        rule_engine_source = handle.read()

    check(
        "import Autodesk" not in rule_engine_source
        and "from Autodesk" not in rule_engine_source
        and "from pyrevit" not in rule_engine_source
        and "import pyrevit" not in rule_engine_source,
        "P8 rule engine imports no Revit or pyRevit symbol"
    )

    moved_rules = (
        "normalize_label",
        "code_token_match",
        "_contains_rcc_identity_signal",
        "_element_source_category",
        "_element_routing_key",
        "_safe_element_id_text",
        "classify_identity_text",
        "build_logical_rcc_collections",
        "validate_classification_audit",
        "classification_audit_has_findings",
        "classification_audit_detail_results",
        "build_compact_classification_findings",
    )
    rule_sources = {}
    for rule_name in moved_rules:
        _block, rule_path = extract_from_sources(texts, rule_name)
        rule_sources[rule_name] = os.path.basename(rule_path)
    check(
        set(rule_sources.values()) == {"rule_engine.py"},
        "P8 classification rules resolve from lib/rule_engine.py"
    )

    parameter_engine_path = os.path.join(LIB_DIR, "parameter_engine.py")
    with io.open(parameter_engine_path, "r", encoding="utf-8-sig") as handle:
        parameter_engine_source = handle.read()

    check(
        "import Autodesk" not in parameter_engine_source
        and "from Autodesk" not in parameter_engine_source
        and "from pyrevit" not in parameter_engine_source
        and "import pyrevit" not in parameter_engine_source,
        "P8 parameter engine imports no Revit or pyRevit symbol"
    )

    moved_readers = (
        "safe_storage_type",
        "safe_is_shared",
        "safe_is_read_only",
        "safe_definition_info",
        "find_parameter_on_element",
        "find_parameter_in_context",
        "count_parameter_metadata",
        "get_parameters",
    )
    reader_sources = {}
    for reader_name in moved_readers:
        _block, reader_path = extract_from_sources(texts, reader_name)
        reader_sources[reader_name] = os.path.basename(reader_path)
    check(
        set(reader_sources.values()) == {"parameter_engine.py"},
        "P8 parameter readers resolve from lib/parameter_engine.py"
    )

    # safe_text is the one moved name that also exists in
    # export_engine.py. What matters is that script.py no longer owns a
    # copy - whichever engine module answers, it is not the pushbutton.
    _safe_text_block, safe_text_path = extract_from_sources(texts, "safe_text")
    check(
        os.path.basename(safe_text_path) != "script.py",
        "P8 leaves no safe_text definition in script.py"
    )

    _grade_block, grade_path = extract_from_sources(
        texts, "normalize_concrete_grade")
    check(
        os.path.basename(grade_path) == "rule_engine.py",
        "P8 concrete-grade normalization resolves from lib/rule_engine.py"
    )

    for revit_bound in ("classify_rcc_element",):
        _block, bound_path = extract_from_sources(texts, revit_bound)
        check(
            os.path.basename(bound_path) == "script.py",
            "P8 leaves the Revit-bound {} in script.py".format(revit_bound)
        )

    # classify_rcc_element is now a reader, not a rule: the route must
    # come from the engine, and the element-bound identity reads must
    # stay behind in the pushbutton.
    classifier_block, _ = extract_from_sources(texts, "classify_rcc_element")
    check(
        "classify_identity_text(" in classifier_block
        and "code_token_match(" not in classifier_block
        and "get_element_identity_text(" in classifier_block,
        "P8 classify_rcc_element reads the element and defers the route"
    )

    # The point of the split: the route rules can now be imported and
    # argued with directly, on plain text, with no element, no fake and
    # no exec. If this import ever needs a Revit symbol, it fails here.
    import rule_engine as rule_engine_module

    route_cases = (
        ("pcc footing", "Floors", "Foundation", "PCC"),
        ("combined footing c1", "Floors", "Foundation", "Combined Footing"),
        ("cf1a", "Floors", "Foundation", "Combined Footing"),
        ("wf1", "Structural Foundations", "Foundation", "Footing"),
        ("combined raft", "Floors", "Foundation", "Combined Raft"),
        ("raft", "Floors", "Foundation", "Raft"),
        ("grade slab", "Floors", "Slab", "Grade Slab"),
        ("gs", "Floors", "Slab", "Grade Slab"),
        ("fold slab", "Floors", "Slab", "Fold Slab"),
        ("s1", "Floors", "Slab", "Slab"),
        ("chajja2", "Floors", "Slab", "Slab"),
        ("lobby", "Floors", "Slab", "Slab"),
        ("ramp", "Floors", "Slab", "Slab"),
    )
    route_failures = []
    for text, source_name, expected_group, expected_subtype in route_cases:
        route = rule_engine_module.classify_identity_text(text, source_name)
        if (
            route["logical_group"] != expected_group
            or route["subtype"] != expected_subtype
            or not route["reason"]
        ):
            route_failures.append(
                "{} -> {}/{}".format(
                    text, route["logical_group"], route["subtype"]
                )
            )
    check(
        not route_failures,
        "P8 route rules decide every known identity from text alone{}".format(
            "" if not route_failures else " ({})".format(
                "; ".join(route_failures))
        )
    )

    # An unknown identity is never dropped and never guessed into a
    # priced subtype: it stays under the sheet its own source category
    # implies, marked Other so the audit reports it.
    unknown_floor = rule_engine_module.classify_identity_text(
        "unmapped thing", "Floors")
    unknown_foundation = rule_engine_module.classify_identity_text(
        "unmapped thing", "Structural Foundations")
    check(
        unknown_floor["logical_group"] == "Slab"
        and unknown_floor["subtype"] == "Other"
        and unknown_foundation["logical_group"] == "Foundation"
        and unknown_foundation["subtype"] == "Other",
        "P8 an unknown identity stays on its source sheet as Other"
    )

    # Foundation wording must keep winning over generic slab wording:
    # a foundation slab named for its footing is a footing, not a slab.
    precedence = rule_engine_module.classify_identity_text(
        "foundation slab f2a", "Structural Foundations")
    pcc_precedence = rule_engine_module.classify_identity_text(
        "rcc slab pcc", "Floors")
    check(
        precedence["logical_group"] == "Foundation"
        and precedence["subtype"] == "Footing"
        and pcc_precedence["subtype"] == "PCC",
        "P8 foundation identities still precede generic slab wording"
    )

    # safe_is_project_parameter reads doc.ParameterBindings, so it is
    # host-bound despite naming no Revit type, and must not have moved.
    for revit_bound in ("safe_parameter_value", "find_parameter_with_scope",
                        "build_parameter_metadata", "resolve_concrete_grade",
                        "safe_is_project_parameter"):
        _block, bound_path = extract_from_sources(texts, revit_bound)
        check(
            os.path.basename(bound_path) == "script.py",
            "P8 leaves the Revit-bound {} in script.py".format(revit_bound)
        )

    # ------------------------------------------------------------
    # P7 site items engine (lib/site_items_engine.py)
    #
    # Imported directly, like the authoring engine: it is a self
    # contained pure module, so importing keeps its internal calls
    # intact and shadows nothing in the shared extraction namespace.
    # ------------------------------------------------------------
    import site_items_engine

    site_items_path = os.path.join(LIB_DIR, "site_items_engine.py")
    with io.open(site_items_path, "r", encoding="utf-8-sig") as handle:
        site_items_source = handle.read()

    check(
        "import Autodesk" not in site_items_source
        and "from Autodesk" not in site_items_source
        and "from pyrevit" not in site_items_source
        and "import pyrevit" not in site_items_source,
        "P7 site items engine imports no Revit or pyRevit symbol"
    )

    typed = site_items_engine.normalize_site_items([
        {"code": "SI-01", "description": "Binding wire", "quantity": "25",
         "unit": "kg", "rate": "85.5"},
        {"code": "SI-02", "description": "Scaffolding hire", "quantity": 1,
         "unit": "LS", "rate": None, "remarks": "awaiting quote"},
    ])

    check(
        typed[0]["quantity"] == 25.0 and typed[0]["rate"] == 85.5
        and typed[1]["rate"] is None,
        "P7 normalizes typed numbers and keeps an absent rate as None"
    )

    # A zero or negative rate must not survive as a number: pricing real
    # work at nothing is the failure mode this guards against.
    refused = site_items_engine.normalize_site_items([
        {"code": "Z", "description": "d", "quantity": "0", "unit": "u", "rate": "-5"},
        {"code": "T", "description": "d", "quantity": True, "unit": "u", "rate": "abc"},
    ])
    check(
        all(item["quantity"] is None and item["rate"] is None for item in refused),
        "P7 refuses zero, negative, boolean and non-numeric quantity or rate"
    )

    check(
        site_items_engine.site_item_amount(typed[0]) == 2137.5
        and site_items_engine.site_item_amount(typed[1]) is None,
        "P7 amount is quantity x rate, and blank when either is unusable"
    )

    summary = site_items_engine.summarize_site_items(typed)
    check(
        summary == {"count": 2, "priced_count": 1, "unpriced_count": 1,
                    "amount_total": 2137.5},
        "P7 summary totals only priced lines and counts the rest separately"
    )

    incomplete = site_items_engine.normalize_site_items([
        {"code": "SI-01", "description": "Binding wire", "quantity": "25",
         "unit": "kg", "rate": "85.5"},
        {"code": "SI-01", "description": "", "quantity": "-4", "unit": "",
         "rate": "0"},
        {"description": "", "quantity": "", "unit": "", "rate": ""},
    ])
    findings = site_items_engine.validate_site_items(incomplete)
    check(
        any("Duplicate item code: SI-01" in f for f in findings)
        and any("SI-01: missing description" in f for f in findings)
        and any("SI-01: quantity is missing" in f for f in findings)
        and any("SI-01: missing unit" in f for f in findings)
        and any("SI-01: rate is missing" in f for f in findings),
        "P7 validation names every unusable field on a line"
    )

    check(
        any(f.startswith("Row 3:") for f in findings),
        "P7 validation falls back to the row number when a line has no code"
    )

    check(
        site_items_engine.validate_site_items(
            site_items_engine.normalize_site_items([typed[0]])) == [],
        "P7 validation accepts a complete line item"
    )

    table = site_items_engine.build_site_items_table(typed)
    check(
        list(table[0]) == list(site_items_engine.SITE_ITEM_HEADERS)
        and table[1][5] == 2137.5
        and table[2][4] == "" and table[2][5] == ""
        and table[-1][0] == "TOTAL" and table[-1][5] == 2137.5,
        "P7 table blanks unpriced cells and totals only what could be priced"
    )

    check(
        site_items_engine.build_site_items_table([]) == [
            list(site_items_engine.SITE_ITEM_HEADERS)],
        "P7 an empty item list yields a header-only table with no TOTAL row"
    )

    check(
        len(site_items_engine.priceable_site_items(typed)) == 1,
        "P7 priceable_site_items returns only fully priced lines"
    )

    # Store: a default list seeds a project the first time it is opened,
    # and the project's own list is editable from there (owner decision,
    # 2026-09-19).
    store = site_items_engine.normalize_site_items_store({
        "default": [{"code": "D-01", "description": "Scaffolding",
                     "quantity": "1", "unit": "LS", "rate": "50000"}],
    })

    seeded = site_items_engine.resolve_site_items(store, "AMANI")
    check(
        seeded["source"] == "default"
        and [item["code"] for item in seeded["items"]] == ["D-01"],
        "P7 a document with no list of its own is seeded from the default"
    )

    store = site_items_engine.save_site_items(store, "AMANI", [
        {"code": "A-01", "description": "Site office", "quantity": "1",
         "unit": "LS", "rate": "20000"},
    ])
    owned = site_items_engine.resolve_site_items(store, "AMANI")
    check(
        owned["source"] == "document"
        and [item["code"] for item in owned["items"]] == ["A-01"],
        "P7 once saved, a document uses its own list instead of the default"
    )

    # The decision that matters: changing the default must never reach a
    # project that was already priced from its own list.
    store = site_items_engine.set_default_site_items(store, [
        {"code": "D-99", "description": "New template line", "quantity": "2",
         "unit": "nos", "rate": "100"},
    ])
    after = site_items_engine.resolve_site_items(store, "AMANI")
    fresh = site_items_engine.resolve_site_items(store, "UMA-NIWAS")
    check(
        [item["code"] for item in after["items"]] == ["A-01"]
        and after["source"] == "document"
        and [item["code"] for item in fresh["items"]] == ["D-99"]
        and fresh["source"] == "default",
        "P7 a changed default seeds only new documents and never edits a saved one"
    )

    reset = site_items_engine.forget_document_site_items(store, "AMANI")
    check(
        site_items_engine.resolve_site_items(reset, "AMANI")["source"] == "default",
        "P7 forgetting a document's list re-seeds it from the default"
    )

    check(
        site_items_engine.resolve_site_items(
            site_items_engine.normalize_site_items_store({}), "ANY") ==
        {"items": [], "source": "empty"},
        "P7 an empty store resolves to no items rather than raising"
    )

    check(
        site_items_engine.normalize_site_items_store(
            {"default": "junk", "by_document": ["not", "a", "dict"]}) ==
        {"default": [], "by_document": {}},
        "P7 a corrupt or hand-edited store degrades to empty instead of raising"
    )

    check(
        site_items_engine.save_site_items(store, "", typed)[
            "by_document"].get("") is None,
        "P7 a blank document title is never used as a store key"
    )

    # P7 export: the sheet in both formats, and the Costing roll-up.
    p7_root = tempfile.mkdtemp(prefix="rcc-boq-p7-")
    try:
        p7_data = {
            "Beam": [
                {"Element ID": "1", "Level": "L1", "Grade": "M30",
                 "Rate": 4500, "Qty: Volume (m3)": 2.0, "Qty: Count": 1},
            ],
        }
        p7_items = site_items_engine.normalize_site_items([
            {"code": "SI-01", "description": "Binding wire", "quantity": "25",
             "unit": "kg", "rate": "85.5"},
            {"code": "SI-02", "description": "Scaffolding hire", "quantity": "1",
             "unit": "LS", "rate": None, "remarks": "awaiting quote"},
        ])

        p7_rows = namespace["write_basic_xlsx"](
            os.path.join(p7_root, "classic.xlsx"),
            p7_data,
            {},
            project_name="P7 TEST",
            tool_version="RCC BOQ Parameter Manager v1.25.2",
            generated_stamp="2026-09-19 12:00",
            site_items=p7_items
        )
        p7_order = p10_sheet_order(os.path.join(p7_root, "classic.xlsx"))
        p7_cover = set(row[0] for row in p7_rows["Summary"] if row)

        check(
            "Site Items" in p7_order
            and p7_order.index("Site Items") < p7_order.index("Costing")
            and "Site Items" in p7_cover,
            "P7 Classic lists Site Items on the cover and before Costing"
        )

        check(
            p7_rows["Site Items"]
            == site_items_engine.build_site_items_table(p7_items),
            "P7 Classic Site Items sheet carries the engine's own table"
        )

        costing = p7_rows["Costing"]
        site_rows = [row for row in costing if row[0] == "Site Item"]
        total_row = [row for row in costing if row[0] == "TOTAL"][0]
        check(
            [row[1] for row in site_rows] == ["SI-01", "SI-02"]
            and site_rows[0][4] == ("FORMULA", "C3*D3")
            and site_rows[1][4] == "",
            "P7 Costing prices site items by formula and blanks the unpriced one"
        )

        check(
            total_row[4] == ("FORMULA", "SUM(E2:E{0})".format(len(costing) - 1)),
            "P7 the Costing TOTAL spans the site item rows too"
        )

        clean_rows = namespace["write_basic_xlsx"](
            os.path.join(p7_root, "clean.xlsx"),
            p7_data,
            {},
            project_name="P7 TEST",
            tool_version="RCC BOQ Parameter Manager v1.25.2",
            generated_stamp="2026-09-19 12:00"
        )
        check(
            "Site Items" not in clean_rows
            and not [row for row in clean_rows["Costing"]
                     if row[0] == "Site Item"],
            "P7 a project with no site items keeps its familiar workbook"
        )

        p7_site_rows = namespace["write_site_xlsx"](
            os.path.join(p7_root, "site.xlsx"),
            p7_data,
            project_name="P7 TEST",
            tool_version="RCC BOQ Parameter Manager v1.25.2",
            generated_stamp="2026-09-19 12:00",
            site_items=p7_items
        )
        site_sheet = p7_site_rows.get("Site Items") or []
        flat = [u"{0}".format(cell) for row in site_sheet for cell in row]
        check(
            site_sheet
            and "SITE / NON-MODEL ITEMS" in flat
            and "SI-01" in flat and "SI-02" in flat,
            "P7 Site workbook carries the items inside the site title bands"
        )
    finally:
        shutil.rmtree(p7_root, ignore_errors=True)

    # ------------------------------------------------------------
    # Authoring spec engine (lib/authoring_spec.py)
    #
    # Imported directly rather than name-extracted: it is a self
    # contained pure module, so importing it keeps the engine's own
    # internal calls intact and avoids shadowing names that the
    # extracted BOQ engines already define in the shared namespace.
    # ------------------------------------------------------------
    import authoring_spec

    authoring_source_path = os.path.join(LIB_DIR, "authoring_spec.py")
    with io.open(authoring_source_path, "r", encoding="utf-8-sig") as handle:
        authoring_source = handle.read()

    check(
        "import Autodesk" not in authoring_source
        and "from Autodesk" not in authoring_source
        and "from pyrevit" not in authoring_source
        and "import pyrevit" not in authoring_source,
        "Authoring spec engine imports no Revit or pyRevit symbol"
    )

    authored = authoring_spec.normalize_model_spec({
        "template": "T.rte",
        "output_path": "out.rvt",
        "levels": [
            {"name": "Level 2", "elevation_mm": 3000.0},
            {"name": "Level 1", "elevation_mm": 0.0},
        ],
        "elements": [
            {"kind": "column", "name": "C1", "top_level": "Level 2"},
            {"kind": "beam", "name": "B1"},
            {"kind": "slab", "name": "S1"},
            {"kind": "foundation", "name": "F1"},
        ],
    })

    check(
        [level["name"] for level in authored["levels"]] == ["Level 1", "Level 2"],
        "Authoring spec sorts declared levels by elevation"
    )

    check(
        authored["elements"][0]["width_mm"] == 300.0
        and authored["elements"][0]["depth_mm"] == 450.0
        and authored["elements"][1]["length_mm"] == 4000.0
        and authored["elements"][2]["thickness_mm"] == 150.0,
        "Authoring spec fills per-kind dimension defaults"
    )

    # 300 x 450 mm over a 3000 mm storey is the column the live Revit
    # session actually produced (0.4050 m3 read back from the model).
    check(
        abs(authoring_spec.expected_element_volume_m3(
            authored, authored["elements"][0]) - 0.405) < 1e-9,
        "Authoring spec column volume matches width x depth x storey height"
    )

    check(
        abs(authoring_spec.expected_element_volume_m3(
            authored, authored["elements"][2]) - 1.8) < 1e-9
        and abs(authoring_spec.expected_element_volume_m3(
            authored, authored["elements"][3]) - 1.0125) < 1e-9,
        "Authoring spec footprint volumes cover slab and foundation"
    )

    check(
        authoring_spec.validate_model_spec(authored) == [],
        "Authoring spec accepts a fully declared model"
    )

    summary = authoring_spec.summarize_expected_quantities(authored)
    check(
        summary["total"]["count"] == 4
        and abs(summary["total"]["volume_m3"]
                - (0.405 + 0.4140 + 1.8 + 1.0125)) < 1e-9,
        "Authoring spec summary totals every declared kind"
    )

    broken = authoring_spec.normalize_model_spec({
        "levels": [{"name": "Level 1", "elevation_mm": 0.0}],
        "elements": [
            {"kind": "column", "name": "C1"},
            {"kind": "column", "name": "C1", "top_level": "Roof"},
            {"kind": "wall", "name": "W1"},
            {"kind": "slab", "name": "S1", "thickness_mm": 0,
             "base_level": "Basement"},
        ],
    })
    broken_findings = authoring_spec.validate_model_spec(broken)
    check(
        any("needs a top_level" in f for f in broken_findings)
        and any("Duplicate element name: C1" in f for f in broken_findings)
        and any("top level 'Roof' not declared" in f for f in broken_findings)
        and any("unknown kind 'wall'" in f for f in broken_findings)
        and any("non-positive thickness_mm" in f for f in broken_findings)
        and any("base level 'Basement' not declared" in f
                for f in broken_findings),
        "Authoring spec reports every unbuildable declaration by name"
    )

    check(
        authoring_spec.expected_element_volume_m3(
            broken, broken["elements"][0]) is None,
        "Authoring spec returns no volume when a column has no top level"
    )

    check(
        authoring_spec.compare_actual_to_expected(authored, [
            {"name": "C1", "volume_m3": 0.405},
            {"name": "B1", "volume_m3": 0.414},
            {"name": "S1", "volume_m3": 1.8},
            {"name": "F1", "volume_m3": 1.0125},
        ]) == [],
        "Authoring spec comparison passes when Revit built what was declared"
    )

    drifted = authoring_spec.compare_actual_to_expected(authored, [
        {"name": "C1", "volume_m3": 0.500},
        {"name": "B1", "volume_m3": 0.414},
        {"name": "S1", "volume_m3": 1.8},
        {"name": "X9", "volume_m3": 2.0},
    ])
    check(
        any("C1: volume 0.5000 m3 differs from declared 0.4050 m3" in f
            for f in drifted)
        and any("F1: declared but not built" in f for f in drifted)
        and any("X9: built but never declared" in f for f in drifted),
        "Authoring spec comparison flags drift, missing and stray elements"
    )

    # family_path lets a spec pin the family file, because the family
    # NAME is itself identity the BOQ classifier reads - the P10-03
    # fixture needs a foundation whose family name carries no routing
    # token (M_Footing-Rectangular would contribute "footing").
    pinned = authoring_spec.normalize_model_spec({
        "elements": [
            {"kind": "foundation", "name": "Pedestal PD1",
             "family_path": "C:/lib/M_Cup Foundation.rfa"},
            {"kind": "slab", "name": "Deck Panel PX1"},
        ],
    })
    check(
        pinned["elements"][0]["family_path"] == "C:/lib/M_Cup Foundation.rfa"
        and pinned["elements"][1]["family_path"] == ""
        and authoring_spec.validate_model_spec(pinned) == [],
        "Authoring spec carries an optional family_path and defaults it empty"
    )

    check(
        abs(authoring_spec.mm_to_feet(304.8) - 1.0) < 1e-12
        and abs(authoring_spec.feet_to_mm(1.0) - 304.8) < 1e-12
        and abs(authoring_spec.cubic_feet_to_cubic_meters(1.0)
                - 0.028316846592) < 1e-15,
        "Authoring spec unit conversions round-trip against Revit internals"
    )

    print("")

    if failures:
        print("RESULT: {} failure(s)".format(len(failures)))
        sys.exit(1)

    print("RESULT: all checks passed")


if __name__ == "__main__":
    main()

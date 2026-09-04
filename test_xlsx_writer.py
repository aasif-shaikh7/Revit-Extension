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
import os
import re
import sys
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
    os.path.join(REPO_DIR, "Nudge.extension", "lib", "costing_engine.py"),
    os.path.join(REPO_DIR, "Nudge.extension", "lib", "export_engine.py"),
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
    "write_basic_xlsx",
    "get_parameters",
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
    "_site_sort_key",
    "_sort_site_rows",
    "_site_cell_value",
    "_site_numeric",
    "_site_dim_value",
    "_site_desc_text",
    "build_site_detail_sheet",
    "build_site_summary_sheet",
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
        "CONCRETE_GRADE_VALUES"
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
                "Rebar: Total Length (m)": 12.0,
                "Rebar: Unit Weight (kg/m)": 0.8889,
                "Rebar: Total Weight (kg)": 10.667,
                "Rebar: Host Element ID": "200",
                "Rebar: Host Category": "Structural Columns"
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

    sheet_rows = namespace["write_basic_xlsx"](
        output_path,
        data_result,
        parameter_metadata,
        project_name="CHHANYADO HOSPITAL SURAT",
        tool_version="RCC BOQ Parameter Manager v1.4.0",
        generated_stamp="2026-08-26 10:00"
    )

    try:

        check(
            "BOQ Summary" in sheet_rows,
            "BOQ Summary sheet was generated"
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
            "Rebar", "BOQ Summary", "BOQ by Level", "BOQ by Grade", "Costing"
        ]

        check(
            sheet_order == expected_order,
            "Sheet order correct: {}".format(sheet_order)
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
                "Rebar: Total Length (m)": 12.0,
                "Rebar: Unit Weight (kg/m)": 0.8889,
                "Rebar: Total Weight (kg)": 10.667,
                "Rebar: Host Element ID": "200",
                "Rebar: Host Category": "Structural Columns"
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
            sheet_order_site == ["Summary", "Beam", "Structure Wall", "Rebar"],
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
        "Rebar: Total Length (m)",
        "Rebar: Unit Weight (kg/m)",
        "Rebar: Total Weight (kg)",
        "Rebar: Host Element ID",
        "Rebar: Host Category"
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
        "get_element_identity_text",
        "_read_identity_parameter",
        "_element_source_category",
        "_element_family_type_names",
        "_element_routing_key",
        "_safe_element_id_text",
        "classify_rcc_element",
        "build_logical_rcc_collections",
        "validate_classification_audit",
        "classification_audit_has_findings",
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

    class FakeElement(object):
        next_id = 1000

        def __init__(
            self, name, category, element_id=None, parameter_values=None
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

    def classify_name(name, category):
        return routing_ns["classify_rcc_element"](
            FakeElement(name, category), category
        )

    direct_cases = (
        ("F1", "Floors", "Foundation", "Footing"),
        ("F10", "Floors", "Foundation", "Footing"),
        ("CF2", "Floors", "Foundation", "Combined Footing"),
        ("PCC_FOOTING", "Floors", "Foundation", "PCC"),
        ("RAFT_PCC", "Floors", "Foundation", "PCC"),
        ("RCC_SLAB_F1", "Floors", "Foundation", "Footing"),
        ("S1", "Structural Foundations", "Slab", "Slab"),
        ("GS", "Structural Foundations", "Slab", "Grade Slab"),
        ("GRADE-SLAB", "Structural Foundations", "Slab", "Grade Slab"),
        ("FOLD_SLAB", "Structural Foundations", "Slab", "Fold Slab"),
        ("RCC Chajja", "Structural Foundations", "Slab", "Slab"),
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

    for unsafe_name in ("F", "SF", "FLOOR", "FOLD"):
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
        [duplicate], [duplicate]
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

    engine_guard_block, _ = extract_from_sources(
        texts, "_warn_if_not_cp3123"
    )
    check(
        "get_output" not in engine_guard_block
        and "not is_cp3123 and not is_ironpython" in engine_guard_block,
        "Known CP3123/IP27 engines do not force an output popup"
    )

    print("")

    if failures:
        print("RESULT: {} failure(s)".format(len(failures)))
        sys.exit(1)

    print("RESULT: all checks passed")


if __name__ == "__main__":
    main()

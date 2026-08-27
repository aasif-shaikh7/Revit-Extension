# -*- coding: utf-8 -*-
"""
Standalone regression harness for the RCC BOQ XLSX writer.

Extracts the dependency-free XLSX functions straight from the pushbutton
script.py (so tests always run against the real production code), builds
a sample workbook including quantity takeoff columns, totals rows and
the BOQ Summary sheet, then unzips the result and XML-validates every
part. Run with any Python 3.x:  python test_xlsx_writer.py
"""

import io
import os
import re
import sys
import zipfile
from xml.dom import minidom

SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "Aasif.extension",
    "Aasif.tab",
    "Generate.panel",
    "BOQ.pushbutton",
    "script.py"
)

FUNCTION_NAMES = [
    "safe_text",
    "xlsx_column_name",
    "xlsx_inline_string",
    "try_export_as_number",
    "xlsx_cell",
    "xlsx_formula_cell",
    "build_xlsx_sheet_xml",
    "build_xlsx_styles_xml",
    "build_xlsx_workbook_xml",
    "build_xlsx_workbook_rels_xml",
    "build_xlsx_root_rels_xml",
    "build_xlsx_content_types_xml",
    "build_parameter_metadata_sheet",
    "build_missing_values_summary",
    "build_costing_sheet",
    "build_level_summary_table",
    "sanitize_file_name",
    "build_default_output_name",
    "build_summary_cover_rows",
    "write_basic_xlsx",
    "_site_sort_key",
    "_site_cell_value",
    "_site_numeric",
    "_site_dim_value",
    "_site_desc_text",
    "meters_to_millimeters",
    "build_section_description",
    "resolve_element_dimensions",
    "compute_shuttering_area",
    "build_site_detail_sheet",
    "build_site_summary_sheet",
    "build_xlsx_sheet_xml_site",
    "_finish_site_sheet",
    "write_site_xlsx"
]


def extract_function_source(source, name):
    """Pull one top-level def block out of the script source."""
    pattern = re.compile(
        r"^def {0}\(.*?(?=^def )".format(name),
        re.S | re.M
    )

    match = pattern.search(source)

    if not match:
        raise AssertionError(
            "Could not extract function: {}".format(name)
        )

    return match.group(0)


def main():
    failures = []

    def check(condition, message):
        if condition:
            print("PASS: {}".format(message))
        else:
            failures.append(message)
            print("FAIL: {}".format(message))

    with io.open(SCRIPT_PATH, "r", encoding="utf-8") as handle:
        source = handle.read()

    import time

    namespace = {
        "os": os,
        "re": re,
        "zipfile": zipfile,
        "time": time,
    }

    from xml.sax.saxutils import escape as xml_escape
    namespace["xml_escape"] = xml_escape

    for name in FUNCTION_NAMES:
        exec(
            extract_function_source(source, name),
            namespace
        )

    # Site-format module constants (v1.4.0): simple single-line
    # assignments pulled straight from the production source so the
    # extracted builders always see the real layout contract.
    for constant_name in (
        "SITE_CATEGORY_ORDER",
        "SITE_DETAIL_BAND_ROWS",
        "SITE_DETAIL_DATA_START_ROW",
        "SITE_DETAIL_COLUMN_WIDTHS"
    ):
        constant_pattern = re.compile(
            r"^{0} = .*$".format(constant_name),
            re.M
        )

        match = constant_pattern.search(source)

        assert match is not None, \
            "Could not extract constant: {}".format(constant_name)

        exec(match.group(0), namespace)

    for style_match in re.finditer(
            r"^STYLE_[A-Z_]+ = \d+$",
            source,
            re.M):
        exec(style_match.group(0), namespace)

    print("Extracted {} functions.".format(len(FUNCTION_NAMES)))

    data_result = {
        "Beam": [
            {
                "Element ID": "100",
                "Level": "Ground Floor",
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
                "Mark": "C1",
                "Rate": 1500.0,
                "Qty: Volume (m3)": 0.42,
                "Qty: Area (m2)": 0.16,
                "Qty: Length (m)": 3.5,
                "Qty: Height (m)": 3.5,
                "Qty: Count": 1
            }
        ],
        "Slab": [],
        "Foundation": [
            {
                "Element ID": "300",
                "Level": "(No Level)",
                "Mark": "F1",
                "Rate": 1800.0,
                "Qty: Volume (m3)": 1.85,
                "Qty: Area (m2)": 9.3,
                "Qty: Length (m)": "",
                "Qty: Thickness (m)": 0.3,
                "Qty: Count": 1
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
            amount_formula_count == 4,
            "Every element row has a live Quantity x Rate formula"
        )

        column_table = sheet_rows["Column"]

        check(
            "Qty: Height (m)" in column_table[0],
            "P1 Column Height (Parameter quantity) column present"
        )

        foundation_table = sheet_rows["Foundation"]

        check(
            "Qty: Thickness (m)" in foundation_table[0],
            "P1 Foundation Thickness (Parameter quantity) column present"
        )

        check(
            "Qty: Count" in foundation_table[0]
            and "Qty: Count" in column_table[0],
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
            sumif_count == 9,
            "P2 live SUMIF per Level x Category x available-metric cell "
            "(expected 9: Beam has no Area col, Foundation has no Length "
            "col; got {})".format(sumif_count)
        )

        check(
            any(
                isinstance(row[2], int) for row in level_table[1:]
            ),
            "P2 Elements count is a static number per grouped row"
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
                "Beam", "Column", "Foundation",
                "BOQ Summary", "BOQ by Level", "Costing"
            )
        )

        check(
            listed == set(
                [
                    "Beam", "Column", "Foundation",
                    "BOQ Summary", "BOQ by Level", "Costing"
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

        ordered_levels_check = sorted(
            ["Level 10", "Level 2"],
            key=namespace["_site_sort_key"]
        )

        check(
            ordered_levels_check == ["Level 2", "Level 10"],
            "Natural sort orders levels numerically (2 before 10)"
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
            and detail_table[4][1] == ("MERGE_V", "DESCRIPTION")
            and detail_table[4][7] == ("MERGE_V", "LEVEL")
            and detail_table[5][5] == "VOLUME (m3)"
            and detail_table[5][6] == "SHUTTERING (SQM)",
            "Two-tier header band uses MERGE_V markers on rows 5:6"
        )

        first_site_row = detail_table[6]

        check(
            first_site_row[0] == 1
            and first_site_row[2] == 6096
            and first_site_row[3] == 230
            and first_site_row[4] == 600,
            "Element rows render whole-millimetre SIZE integers"
        )

        check(
            first_site_row[5] == 0.84 and first_site_row[6] == 8.72,
            "Element rows carry VOLUME and SHUTTERING figures rounded"
        )

        check(
            first_site_row[1] == "B1 | 230 X 6096",
            "DESCRIPTION follows the selected parameters, then cross-section"
        )

        check(
            namespace["_site_desc_text"](1200.0) == "1200"
            and namespace["_site_desc_text"](" 450 mm ") == "450 mm"
            and namespace["_site_desc_text"]("") == "",
            "Selected-parameter values render without trailing .0 noise"
        )

        site_total_row = detail_table[-1]

        check(
            site_total_row[0] == "TOTAL"
            and isinstance(site_total_row[5], tuple)
            and site_total_row[5][1] == "SUM(F7:F8)"
            and isinstance(site_total_row[6], tuple)
            and site_total_row[6][1] == "SUM(G7:G8)",
            "Detail TOTAL row holds live SUM formulas for both metrics"
        )

        check(
            detail_meta["total_row"] == len(detail_table)
            and detail_meta["data_start"] == 7
            and detail_meta["columns"]["Volume (m3)"] == "F"
            and detail_meta["columns"]["Shuttering (m2)"] == "G"
            and detail_meta["level_col"] == "H",
            "Detail meta exposes the F/G/H contract for SUMIF feeds"
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
            "Summary title block matches the manual front page"
        )

        check(
            summary_table_s[4][:2]
            == [("MERGE_V", "LEVEL"), ("MERGE_V", "ITEM")]
            and summary_table_s[4][2] == "BEAM"
            and summary_table_s[5][2] == "VOL (m3)"
            and summary_table_s[5][3] == "SHUT (sqm)"
            and summary_table_s[4][4] == "TOTAL (m3)"
            and summary_table_s[4][5] == "TOTAL (sqm)",
            "Summary bands pair each category with VOL/SHUT sub-columns"
        )

        grid_row = summary_table_s[6]

        volume_formula = grid_row[2]

        check(
            isinstance(volume_formula, tuple)
            and volume_formula[1].startswith("SUMIF(Beam!$H$7:$H$8,")
            and '"Level 1"' in volume_formula[1],
            "Summary level row holds a live SUMIF per metric column"
        )

        check(
            grid_row[4][0] == "FORMULA" and grid_row[5][0] == "FORMULA"
            and "C7" in grid_row[4][1] and "D7" in grid_row[5][1],
            "Summary TOTAL columns sum the category pairs horizontally"
        )

        check(
            summary_meta_s["levels"] == ["Level 1", "Level 2"]
            and summary_meta_s["total_columns"] == 6,
            "Summary meta records sorted levels and the column plan"
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
            "Summary", "Beam", "Column", "Foundation",
            "BOQ Summary", "BOQ by Level", "Costing"
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
            "xl/worksheets/sheet5.xml"
        ).decode("utf-8")

        check(
            "<f>Beam!" in summary_xml,
            "BOQ Summary references category sheets by formula"
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
            'rgb="FF305496"' in styles_xml,
            "Styles define the dark blue header fill"
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
        "Slab": [],
        "Foundation": []
    }

    namespace["write_site_xlsx"](
        site_output_path,
        site_data,
        project_name="CHHANYADO HOSPITAL SURAT",
        tool_version="RCC BOQ Parameter Manager v1.4.0",
        generated_stamp="2026-08-27 10:00"
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
            sheet_order_site == ["Summary", "Beam"],
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
            bool(merge_counts) and int(merge_counts[0]) >= 5,
            "Summary title blocks and header band carry merged cells "
            "(count={})".format(merge_counts)
        )

        check(
            "<f>SUMIF(Beam!$H$7:$H$8," in site_summary_xml,
            "Summary level rows use live SUMIF against the Beam detail"
        )

        check(
            ">Level 1<" in site_summary_xml
            and ">Level 2<" in site_summary_xml,
            "Summary lists every exported level as SUMIF criteria"
        )

        site_beam_xml = site_archive.read(
            "xl/worksheets/sheet2.xml"
        ).decode("utf-8")

        check(
            '<mergeCell ref="A5:A6"/>' in site_beam_xml
            and '<mergeCell ref="C5:E5"/>' in site_beam_xml
            and '<mergeCell ref="F5:G5"/>' in site_beam_xml,
            "Detail sheet merges SIZE/QTY groups and single-column "
            "vertical headers exactly like the manual layout"
        )

        check(
            "<f>SUM(F7:F8)</f>" in site_beam_xml,
            "Detail TOTAL row sums the element VOLUME values"
        )

        site_styles_xml = site_archive.read(
            "xl/styles.xml"
        ).decode("utf-8")

        check(
            'rgb="FFBDD7EE"' in site_styles_xml,
            "Site styles define the light blue band fill"
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

    print("")

    if failures:
        print("RESULT: {} failure(s)".format(len(failures)))
        sys.exit(1)

    print("RESULT: all checks passed")


if __name__ == "__main__":
    main()

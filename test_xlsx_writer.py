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
    "write_basic_xlsx"
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

    namespace = {
        "os": os,
        "re": re,
        "zipfile": zipfile,
    }

    from xml.sax.saxutils import escape as xml_escape
    namespace["xml_escape"] = xml_escape

    for name in FUNCTION_NAMES:
        exec(
            extract_function_source(source, name),
            namespace
        )

    print("Extracted {} functions.".format(len(FUNCTION_NAMES)))

    data_result = {
        "Beam": [
            {
                "Element ID": "100",
                "Mark": "B1",
                "Concrete Volume": "",
                "Rate": 1200.0,
                "Qty: Volume (m3)": 0.2832,
                "Qty: Area (m2)": "",
                "Qty: Length (m)": 3.048
            },
            {
                "Element ID": "101",
                "Mark": "B2",
                "Concrete Volume": "",
                "Rate": 1200.0,
                "Qty: Volume (m3)": 0.567,
                "Qty: Area (m2)": "",
                "Qty: Length (m)": 6.096
            }
        ],
        "Column": [
            {
                "Element ID": "200",
                "Mark": "C1",
                "Rate": 1500.0,
                "Qty: Volume (m3)": 0.42,
                "Qty: Area (m2)": 0.16,
                "Qty: Length (m)": 3.5
            }
        ],
        "Slab": [],
        "Foundation": [
            {
                "Element ID": "300",
                "Mark": "F1",
                "Rate": 1800.0,
                "Qty: Volume (m3)": 1.85,
                "Qty: Area (m2)": 9.3,
                "Qty: Length (m)": ""
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
        parameter_metadata
    )

    try:

        check(
            "BOQ Summary" in sheet_rows,
            "BOQ Summary sheet was generated"
        )

        beam_table = sheet_rows["Beam"]

        check(
            beam_table[0][-2:] == [
                "Qty: Volume (m3)",
                "Qty: Length (m)"
            ],
            "Non-empty quantity columns retained on Beam sheet "
            "(fully-empty Qty: Area pruned)"
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
            "Beam", "Column", "Foundation",
            "BOQ Summary", "Costing"
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
            "xl/worksheets/sheet1.xml"
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
            "xl/worksheets/sheet4.xml"
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

    print("")

    if failures:
        print("RESULT: {} failure(s)".format(len(failures)))
        sys.exit(1)

    print("RESULT: all checks passed")


if __name__ == "__main__":
    main()

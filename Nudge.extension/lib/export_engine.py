# -*- coding: utf-8 -*-
"""Export engine - dependency-free Open XML workbook writer (RCC BOQ).

Moved verbatim from BOQ.pushbutton/script.py in the v1.8.6 module split
(PROJECT_STRUCTURE.md section 9). Pure Python: os / re / time / zipfile
plus xml.sax.saxutils only - no Revit symbols. Builds both the classic
workbook (element sheets + BOQ Summary + BOQ by Level + BOQ by Grade +
Costing) and the v1.4.0 site-format workbook.

Two functions that used to share this section now live in sibling
engine modules (both importable in plain Python):
  - build_costing_sheet      -> lib/costing_engine.py
  - build_shuttering_formula -> lib/formwork_engine.py
"""
import os
import re
import time
import zipfile
from xml.sax.saxutils import escape as xml_escape

from formwork_engine import (
    build_shuttering_formula,
    get_formwork_factor,
)

def safe_text(value, fallback="Unknown"):
    """
    Convert a Revit API value to a safe string without allowing
    metadata collection to fail because a property is unavailable.
    """
    try:
        if value is None:
            return fallback

        text = str(value)

        if text == "":
            return fallback

        return text

    except:
        return fallback

# ============================================================
# BASIC XLSX EXPORT ENGINE - STEP 6A
# ============================================================

def xlsx_column_name(index):
    """Convert a 1-based column number to an Excel column name."""
    result = ""
    number = index

    while number > 0:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result

    return result


def xlsx_inline_string(value):
    """Create an Open XML inline string cell value."""
    if value is None:
        text = ""
    else:
        try:
            text = str(value)
        except:
            text = ""

    # Excel/Open XML requires strings to contain only XML 1.0-valid
    # characters. Strip control characters (other than tab/newline/
    # carriage-return) that some Revit parameter values may carry,
    # otherwise the produced workbook may be rejected by Excel.
    try:
        text = re.sub(
            u'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]',
            u'',
            text
        )
    except:
        pass

    escaped = xml_escape(text)

    # xml:space preserves leading/trailing spaces in parameter values.
    return (
        '<is><t xml:space="preserve">{}</t></is>'.format(
            escaped
        )
    )


def try_export_as_number(value):
    """
    Return True when a value should be written as an XML numeric cell
    instead of a text cell. Simple integers and decimals are exported
    as numbers so Excel can sum/average them. Values bearing units or
    other non-numeric text remain as strings.
    """
    try:

        if isinstance(value, bool):
            return False

        if isinstance(value, (int, float)):
            return True

        text = str(value).strip()

        if text == "":
            return False

        float(text)

        return bool(
            re.match(r'^-?\d+(\.\d+)?$', text)
        )

    except:
        return False

    return False


def xlsx_cell(cell_ref, value, style_index=None):
    """Create a worksheet cell. Numeric values become real numbers."""
    style_part = ""

    if style_index is not None:
        style_part = ' s="{}"'.format(style_index)

    if try_export_as_number(value):
        numeric_text = None

        if isinstance(value, (int, float)):
            numeric_text = str(value)
        else:
            numeric_text = str(value).strip()

        return (
            '<c r="{}"{}><v>{}</v></c>'.format(
                cell_ref,
                style_part,
                numeric_text
            )
        )

    return (
        '<c r="{}" t="inlineStr"{}>{}</c>'.format(
            cell_ref,
            style_part,
            xlsx_inline_string(value)
        )
    )


# Style indexes into build_xlsx_styles_xml() cellXfs.
STYLE_DEFAULT = 0
STYLE_HEADER = 1
STYLE_NUMBER = 2
STYLE_TOTAL_TEXT = 3
STYLE_TOTAL_NUMBER = 4

# Site-format (v1.4.0) style indexes appended in the same cellXfs list.
STYLE_SITE_TITLE = 5
STYLE_SITE_META = 6
STYLE_SITE_SUBTITLE = 7
STYLE_SITE_BAND = 8
STYLE_SITE_SUBBAND = 9
STYLE_SITE_NUM = 10
STYLE_SITE_MM = 11
STYLE_SITE_TOTAL_NUM = 12
STYLE_SITE_TOTAL_TEXT = 13

# Bordered plain text (descriptions, selected-parameter values, the
# LEVEL feed column) so the whole site sheet carries the thin grid.
STYLE_SITE_PLAIN = 14

# ------------------------------------------------------------
# Brand palette (docs/reference/brand-guidelines.md) — Ember accent.
# The exported workbook strips Revit's own blue (guidelines: "Don't use
# Revit's own blue as an accent") and uses the Ember ramp instead. Keys
# map to the fills baked into styles.xml.
#   Ember 500  F2994A  primary accent / bold header fill (white text)
#   Ember 100  FCE8D5  light band tint
#   Ember 200  FFF0E3  lighter sub-band tint (keeps the band/sub-band
#                      distinction of the blue ramp it replaces)
#   Neutral    F2F2F2  totals shading (unchanged)
# ------------------------------------------------------------
EMBER_500 = "F2994A"
EMBER_100 = "FCE8D5"
EMBER_200 = "FFF0E3"
GRAY_TOTALS_FILL = "F2F2F2"


def xlsx_formula_cell(cell_ref, expression, style_index=None):
    """
    Create a worksheet cell holding a live Excel formula.
    The expression is stored without its leading "=" sign, exactly as
    Open XML expects inside the <f> element. Excel evaluates formulas
    on load because workbook.xml enables fullCalcOnLoad.
    """
    style_part = ""

    if style_index is not None:
        style_part = ' s="{}"'.format(style_index)

    try:
        expression_text = str(expression).strip()

        if expression_text[:1] == "=":
            expression_text = expression_text[1:]

    except:
        expression_text = ""

    escaped_expression = xml_escape(expression_text)

    return (
        '<c r="{}"{}><f>{}</f></c>'.format(
            cell_ref,
            style_part,
            escaped_expression
        )
    )


def build_xlsx_sheet_xml(rows, number_columns=None):
    """
    Build worksheet XML for a 2D list of values.

    number_columns: optional collection of 1-based column indexes that
    hold numeric quantity data; those cells receive #,##0.00 styling.

    Cell values may be ("FORMULA", "SUM(A1:A2)") tuples which render as
    live Excel formulas. A trailing row containing such markers (or a
    leading "TOTAL" label) is treated as the totals row: it is styled
    with the bold/gray/border styles and excluded from auto-filter.
    """
    row_xml = []
    max_columns = 0

    for row_number, values in enumerate(rows, 1):
        cells = []

        if len(values) > max_columns:
            max_columns = len(values)

        # Detect a trailing totals row for styling purposes.
        is_totals_row = False

        if rows and row_number == len(rows) and row_number > 1:

            has_marker = False

            for candidate in values:
                if isinstance(candidate, tuple):
                    has_marker = True
                    break

            first_is_total_label = False

            try:
                first_is_total_label = (
                    isinstance(values[0], str)
                    and (
                        values[0] == "TOTAL"
                        or values[0][:11] == "GRAND TOTAL"
                    )
                )
            except:
                first_is_total_label = False

            if has_marker or first_is_total_label:
                is_totals_row = True

        for column_number, value in enumerate(values, 1):
            cell_ref = "{}{}".format(
                xlsx_column_name(column_number),
                row_number
            )

            # Formula marker tuples render as live Excel formulas.
            if (
                isinstance(value, tuple)
                and len(value) == 2
                and value[0] == "FORMULA"
            ):

                # Formula cells that belong to a totals row keep the bold
                # gray totals style; formula cells in normal data rows use
                # the plain #,##0.00 numeric style instead.
                formula_style = STYLE_TOTAL_NUMBER

                if not is_totals_row:
                    formula_style = STYLE_NUMBER

                cells.append(
                    xlsx_formula_cell(
                        cell_ref,
                        value[1],
                        formula_style
                    )
                )

                continue

            style_index = None

            if row_number == 1:
                # Styled header row: bold white on dark blue fill.
                style_index = STYLE_HEADER
            elif is_totals_row:
                if try_export_as_number(value):
                    style_index = STYLE_TOTAL_NUMBER
                else:
                    style_index = STYLE_TOTAL_TEXT
            elif (
                number_columns
                and column_number in number_columns
                and try_export_as_number(value)
            ):
                # Numeric quantity cells with thousand separators.
                style_index = STYLE_NUMBER

            cells.append(
                xlsx_cell(
                    cell_ref,
                    value,
                    style_index
                )
            )

        row_xml.append(
            '<row r="{}">{}</row>'.format(
                row_number,
                "".join(cells)
            )
        )

    if rows and max_columns:
        dimension = "A1:{}{}".format(
            xlsx_column_name(max_columns),
            len(rows)
        )
    else:
        dimension = "A1:A1"

    # Reasonable column widths keep long parameter names readable without
    # generating extremely wide worksheets. Widths are auto-fitted from
    # the header and cell content, then capped to keep sheets tidy.
    column_widths = []

    for column_number in range(1, max_columns + 1):

        longest = 0

        for values in rows:

            if column_number <= len(values):

                try:
                    text_length = len(
                        str(values[column_number - 1])
                    )
                except:
                    text_length = 0

                if text_length > longest:
                    longest = text_length

        # Approximate display width = longest text length + padding.
        width = longest + 2

        if width < 8:
            width = 8

        if width > 60:
            width = 60

        # The Element ID / index column gets a modest fixed width.
        if column_number == 1:
            width = 12

        column_widths.append(width)

    cols = []

    for column_number, width in enumerate(
        column_widths,
        1
    ):

        cols.append(
            '<col min="{}" max="{}" width="{}" customWidth="1"/>'.format(
                column_number,
                column_number,
                width
            )
        )

    auto_filter = ""

    if rows and max_columns:

        filter_end_row = len(rows)

        # Exclude a trailing totals row from the auto-filter range so
        # sorting and filtering never drag the SUM row around.
        last_values = rows[-1]

        last_has_marker = False

        for candidate in last_values:
            if isinstance(candidate, tuple):
                last_has_marker = True
                break

        last_is_total = last_has_marker

        if not last_is_total:

            try:
                last_is_total = (
                    isinstance(last_values[0], str)
                    and last_values[0] == "TOTAL"
                )
            except:
                last_is_total = False

        if last_is_total:
            filter_end_row = len(rows) - 1

        if filter_end_row >= 1:
            auto_filter = (
                '<autoFilter ref="A1:{}{}"/>'.format(
                    xlsx_column_name(max_columns),
                    filter_end_row
                )
            )

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<dimension ref="{}"/>'
        '<sheetViews>'
        '<sheetView workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        '<selection pane="bottomLeft" activeCell="A2" sqref="A2"/>'
        '</sheetView>'
        '</sheetViews>'
        '<sheetFormatPr defaultRowHeight="15"/>'
        '<cols>{}</cols>'
        '<sheetData>{}</sheetData>'
        '{}' 
        '</worksheet>'
    ).format(
        dimension,
        "".join(cols),
        "".join(row_xml),
        auto_filter
    )


def build_xlsx_sheet_xml_site(rows, widths=None):
    """
    Render one worksheet in the v1.4.0 site format.

    Differences from the classic writer:
      - Rows 1-3 form the merged title block (project / workbook /
        section caption) and receive the dedicated site styles.
      - Rows 5-6 are the two-tier header band. Cells carrying a
        ("MERGE_V", label) tuple are vertically merged onto the band
        pair; plain labels followed by empty cells are horizontally
        merged across their group width. Both tiers get the light-blue
        band styles and thin borders.
      - Element rows: integers render through the right-aligned MM
        style (no thousand separators, mirroring manual millimetre
        lists), floats use the #,##0.00 style; the trailing TOTAL row
        reuses the bold grey totals styles. ("FORMULA", ...) and
        ("REF", ...) tuples become live formulas.
      - A mergeCells part collects every span; panes freeze below the
        header band and no auto-filter is emitted (merges would fight
        it).

    widths: optional per-column width overrides (list, 1-based order).
    """
    total_row_index = len(rows)

    merged_spans = []

    # Fixed layout contract shared by detail and Summary builders.
    title_rows = (1, 2, 3)
    band_rows = SITE_DETAIL_BAND_ROWS

    max_columns = max(
        [len(values) for values in rows] + [1]
    )

    row_xml = []

    for row_number, values in enumerate(rows, 1):

        cells = []

        is_title = row_number in title_rows
        is_band = row_number == band_rows[0]
        is_subband = row_number == band_rows[1]

        last_has_formula_marker = False

        if row_number == total_row_index:

            for candidate in values:
                if isinstance(candidate, tuple):
                    last_has_formula_marker = True
                    break

        first_is_total_label = False

        try:
            first_is_total_label = (
                not isinstance(values[0], tuple)
                and str(values[0])[:5] == "TOTAL"
            )
        except:
            first_is_total_label = False

        is_total = (
            row_number > band_rows[1] + 1
            and (
                first_is_total_label or last_has_formula_marker
            )
        )

        for column_number, value in enumerate(values, 1):

            cell_ref = "{0}{1}".format(
                xlsx_column_name(column_number),
                row_number
            )

            style_index = None

            if is_title:
                style_index = (
                    STYLE_SITE_TITLE if row_number == 1
                    else STYLE_SITE_META if row_number == 2
                    else STYLE_SITE_SUBTITLE
                )
            elif is_band:
                style_index = STYLE_SITE_BAND
            elif is_subband:
                style_index = STYLE_SITE_SUBBAND
            elif is_total:
                style_index = (
                    STYLE_SITE_TOTAL_NUM
                    if try_export_as_number(value)
                    else STYLE_SITE_TOTAL_TEXT
                )

            if (
                isinstance(value, tuple)
                and len(value) == 2
                and value[0] in ("FORMULA", "REF")
            ):

                if style_index is None:
                    style_index = STYLE_SITE_NUM

                cells.append(
                    xlsx_formula_cell(
                        cell_ref,
                        value[1],
                        style_index
                    )
                )
                continue

            if (
                isinstance(value, tuple)
                and len(value) == 2
                and value[0] == "MERGE_V"
            ):

                # The span itself is collected inside _finish_site_sheet;
                # appending here too produced a degenerate second entry
                # for the same column and Excel answered with its repair
                # prompt on open.
                cells.append(
                    xlsx_cell(cell_ref, value[1], style_index)
                )
                continue

            if style_index is None:

                if isinstance(value, bool):
                    # Rare, but keep the bordered grid unbroken anyway.
                    style_index = STYLE_SITE_PLAIN
                elif isinstance(value, int):
                    style_index = STYLE_SITE_MM
                elif isinstance(value, float):
                    style_index = STYLE_SITE_NUM
                else:
                    # Text, blank spacers and unknown payloads receive the
                    # bordered plain style so every sheet shows a full
                    # thin-border grid (owner feedback: "border rakho").
                    style_index = STYLE_SITE_PLAIN

            cells.append(
                xlsx_cell(cell_ref, value, style_index)
            )

        row_xml.append(
            '<row r="{0}">{1}</row>'.format(row_number, "".join(cells))
        )

    return _finish_site_sheet(
        rows,
        row_xml,
        merged_spans,
        band_rows,
        title_rows,
        total_row_index,
        max_columns,
        widths
    )


def _finish_site_sheet(rows, row_xml, merged_spans, band_rows,
                       title_rows, total_row_index, max_columns,
                       widths):
    """
    Finish the site worksheet: collect merge spans and emit the final
    worksheet XML. Kept separate so the cell loop stays readable.
    """
    unused = (total_row_index,)

    # Title block rows merge across every produced column.
    for title_row in title_rows:
        if title_row <= len(rows) and max_columns > 1:
            merged_spans.append(
                (title_row, 1, title_row, max_columns)
            )

    # Band row horizontal groups plus vertical continuations.
    band_values = (
        rows[band_rows[0] - 1]
        if band_rows[0] - 1 < len(rows)
        else []
    )

    column_cursor = 1

    while column_cursor <= len(band_values):

        band_value = band_values[column_cursor - 1]

        if band_value in ("", None):
            column_cursor += 1
            continue

        # Vertically merged header cells (MERGE_V markers) always stand
        # alone horizontally; neighbouring empties around them stay
        # unmerged so two spans can never overlap. Overlapping mergeCell
        # entries are exactly what made Excel raise its repair prompt.
        if isinstance(band_value, tuple):

            merged_spans.append(
                (band_rows[0], column_cursor,
                 band_rows[1], column_cursor)
            )

            column_cursor += 1
            continue

        group_start = column_cursor
        group_end = column_cursor

        # band_values is 0-based, so band_values[group_end] is the cell
        # AFTER the 1-based column the cursor points at. Extend while the
        # NEXT cell is blank; stop at the next real label.
        while (
            group_end < len(band_values)
            and band_values[group_end] in ("", None)
        ):
            group_end += 1

        if group_end > group_start:
            merged_spans.append(
                (band_rows[0], group_start,
                 band_rows[0], group_end)
            )

        column_cursor = group_end + 1

    unique_spans = []
    seen_spans = set()

    for span in merged_spans:

        if len(span) == 2:
            span = (span[0], span[1], span[0], span[1])

        # Safety net: never emit single-cell (degenerate) spans. Excel
        # rejects mergeCell entries whose corners coincide.
        if span[0] == span[2] and span[1] == span[3]:
            continue

        if span in seen_spans:
            continue

        seen_spans.add(span)
        unique_spans.append(span)

    merge_xml = ""

    if unique_spans:

        merge_parts = []

        for span in unique_spans:

            start_ref = "{0}{1}".format(
                xlsx_column_name(span[1]),
                span[0]
            )
            end_ref = "{0}{1}".format(
                xlsx_column_name(span[3]),
                span[2]
            )

            merge_parts.append(
                '<mergeCell ref="{0}:{1}"/>'.format(
                    start_ref,
                    end_ref
                )
            )

        merge_xml = '<mergeCells count="{0}">{1}</mergeCells>'.format(
            len(unique_spans),
            "".join(merge_parts)
        )

    column_xml_parts = []

    for column_number in range(1, max_columns + 1):

        width_value = 14

        try:
            if widths and column_number <= len(widths):
                width_value = widths[column_number - 1]
        except:
            width_value = 14

        if width_value < 6:
            width_value = 6
        if width_value > 60:
            width_value = 60

        column_xml_parts.append(
            '<col min="{0}" max="{0}" width="{1}" customWidth="1"/>'.format(
                column_number,
                width_value
            )
        )

    dimension = "A1:{0}{1}".format(
        xlsx_column_name(max_columns),
        len(rows) or 1
    )

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/'
        'spreadsheetml/2006/main">'
        '<dimension ref="{0}"/>'
        '<sheetViews>'
        '<sheetView workbookViewId="0" showGridLines="0">'
        '<pane ySplit="{1}" topLeftCell="A{2}" '
        'activePane="bottomLeft" state="frozen"/>'
        '</sheetView>'
        '</sheetViews>'
        '<sheetFormatPr defaultRowHeight="15"/>'
        '<cols>{3}</cols>'
        '<sheetData>{4}</sheetData>'
        '{5}'
        '</worksheet>'
    ).format(
        dimension,
        band_rows[1],
        band_rows[1] + 1,
        "".join(column_xml_parts),
        "".join(row_xml),
        merge_xml
    )
def build_xlsx_styles_xml():
    """
    Workbook styles used by the export engine:

    xf 0 - default body text
    xf 1 - header row: bold white on Ember accent fill
    xf 2 - numeric quantity cells with #,##0.00 formatting
    xf 3 - totals label cells: bold on light gray with top border
    xf 4 - totals number cells: bold #,##0.00 on light gray
    """
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<numFmts count="0"/>'
        '<fonts count="3">'
        '<font><sz val="11"/><name val="Segoe UI"/></font>'
        '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Segoe UI"/></font>'
        '<font><b/><sz val="11"/><name val="Segoe UI"/></font>'
        '</fonts>'
        '<fills count="6">'
        '<fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFF2994A"/><bgColor indexed="64"/></patternFill></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFF2F2F2"/><bgColor indexed="64"/></patternFill></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFFCE8D5"/><bgColor indexed="64"/></patternFill></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFFFF0E3"/><bgColor indexed="64"/></patternFill></fill>'
        '</fills>'
        '<borders count="3">'
        '<border><left/><right/><top/><bottom/><diagonal/></border>'
        '<border><left/><right/><top><style>thin</style></top><bottom/><diagonal/></border>'
        '<border><left style="thin"><color auto="1"/></left><right style="thin"><color auto="1"/></right><top style="thin"><color auto="1"/></top><bottom style="thin"><color auto="1"/></bottom><diagonal/></border>'
        '</borders>'
        '<cellStyleXfs count="1">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>'
        '</cellStyleXfs>'
        '<cellXfs count="15">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>'
        '<xf numFmtId="4" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
        '<xf numFmtId="0" fontId="2" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>'
        '<xf numFmtId="4" fontId="2" fillId="3" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1"/>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="2" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>'
        '<xf numFmtId="0" fontId="2" fillId="0" borderId="2" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="left" vertical="center"/></xf>'
        '<xf numFmtId="0" fontId="2" fillId="4" borderId="2" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>'
        '<xf numFmtId="0" fontId="2" fillId="4" borderId="2" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="5" borderId="2" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>'
        '<xf numFmtId="4" fontId="0" fillId="0" borderId="2" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment horizontal="right"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="2" xfId="0" applyBorder="1" applyAlignment="1"><alignment horizontal="right"/></xf>'
        '<xf numFmtId="4" fontId="2" fillId="3" borderId="2" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="right"/></xf>'
        '<xf numFmtId="0" fontId="2" fillId="3" borderId="2" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="left" vertical="center"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="2" xfId="0" applyBorder="1" applyAlignment="1"><alignment horizontal="left" vertical="center"/></xf>'
        '</cellXfs>'
        '<cellStyles count="1">'
        '<cellStyle name="Normal" xfId="0" builtinId="0"/>'
        '</cellStyles>'
        '</styleSheet>'
    )


def build_xlsx_workbook_xml(sheet_names):
    sheets = []

    for index, sheet_name in enumerate(sheet_names, 1):
        sheets.append(
            '<sheet name="{}" sheetId="{}" r:id="rId{}"/>'.format(
                xml_escape(sheet_name),
                index,
                index
            )
        )

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets>{}</sheets>'
        '<calcPr calcId="191029" fullCalcOnLoad="1"/>'
        '</workbook>'
    ).format("".join(sheets))


def build_xlsx_workbook_rels_xml(sheet_count):
    rels = []

    for index in range(1, sheet_count + 1):
        rels.append(
            '<Relationship Id="rId{}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet{}.xml"/>'.format(
                index,
                index
            )
        )

    styles_rel_id = sheet_count + 1

    rels.append(
        '<Relationship Id="rId{}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'.format(
            styles_rel_id
        )
    )

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '{}'
        '</Relationships>'
    ).format("".join(rels))


def build_xlsx_root_rels_xml():
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        '</Relationships>'
    )


def build_xlsx_content_types_xml(sheet_count):
    overrides = [
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
    ]

    for index in range(1, sheet_count + 1):
        overrides.append(
            '<Override PartName="/xl/worksheets/sheet{}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'.format(
                index
            )
        )

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '{}'
        '</Types>'
    ).format("".join(overrides))


def build_parameter_metadata_sheet(parameter_metadata):
    """
    Flatten the captured parameter metadata dictionary into a 2D table
    ready for the XLSX exporter. Each row describes one selected
    parameter plus definition-level information captured by the
    metadata engine.
    """
    headers = [
        "Category",
        "Order",
        "Parameter Name",
        "Instance / Type",
        "Shared",
        "Project Parameter",
        "Global Parameter",
        "Built-in Parameter",
        "Read Only",
        "Storage Type",
        "Parameter ID",
        "Definition Type",
        "Definition Name",
        "Data Type",
        "Data Type TypeId",
        "Group Type",
        "Group TypeId"
    ]

    table = [headers]

    if not parameter_metadata:
        return table

    for category in ("Beam", "Column", "Slab", "Foundation"):

        records = parameter_metadata.get(
            category,
            []
        )

        for order, record in enumerate(
            records,
            1
        ):

            definition = {}

            try:
                raw_definition = record.get(
                    "Parameter Definition"
                )

                if isinstance(
                    raw_definition,
                    dict
                ):
                    definition = raw_definition
            except:
                definition = {}

            def metafield(key, default="Unknown"):
                try:
                    value = record.get(
                        key,
                        default
                    )
                    return safe_text(
                        value,
                        default
                    )
                except:
                    return default

            row = [
                category,
                order,
                metafield(
                    "Parameter Name",
                    "Unknown"
                ),
                metafield(
                    "Instance / Type",
                    "Unknown"
                ),
                "Yes" if record.get(
                    "Shared"
                ) else "No",
                "Yes" if record.get(
                    "Project Parameter"
                ) else "No",
                "Yes" if record.get(
                    "Global Parameter"
                ) else "No",
                "Yes" if record.get(
                    "Built-in Parameter"
                ) else "No",
                "Yes" if record.get(
                    "Read Only"
                ) else "No",
                metafield(
                    "Storage Type",
                    "Unknown"
                ),
                metafield(
                    "Parameter ID",
                    "N/A"
                ),
                safe_text(
                    definition.get(
                        "Definition Type",
                        "Unknown"
                    ),
                    "Unknown"
                ),
                safe_text(
                    definition.get(
                        "Definition Name",
                        "Unknown"
                    ),
                    "Unknown"
                ),
                safe_text(
                    definition.get(
                        "Data Type",
                        "Unknown"
                    ),
                    "Unknown"
                ),
                safe_text(
                    definition.get(
                        "Data Type TypeId",
                        "N/A"
                    ),
                    "N/A"
                ),
                safe_text(
                    definition.get(
                        "Group Type",
                        "Unknown"
                    ),
                    "Unknown"
                ),
                safe_text(
                    definition.get(
                        "Group TypeId",
                        "N/A"
                    ),
                    "N/A"
                )
            ]

            table.append(row)

    return table


def build_missing_values_summary(data_result):
    """
    Build a compact data-quality report from the raw element data.
    For every selected parameter that has at least one empty value it
    reports: category, parameter name, total elements, missing/empty
    count, filled count and fill percentage.

    Columns that are completely empty on every element are reported too,
    but such columns are pruned from the main element sheets.
    """
    headers = [
        "Category",
        "Parameter Name",
        "Total Elements",
        "Missing / Empty",
        "Filled",
        "Fill %"
    ]

    table = [headers]

    for category in (
        "Beam",
        "Column",
        "Slab",
        "Foundation"
    ):

        rows = data_result.get(
            category,
            []
        )

        if not rows:
            continue

        # Parameter columns are ordered as stored in the first generated row.
        parameter_names = []

        try:
            for key in rows[0].keys():
                if key == "Element ID":
                    continue

                # P2: Level and Grade are engine-added grouping columns,
                # not selected parameters; they are not part of the audit.
                if key in ("Level", "Grade"):
                    continue

                # Quantity columns carry their own totals on the
                # element sheets and the BOQ Summary; they are not
                # part of the parameter completeness audit.
                if key[:4] == "Qty:":
                    continue

                parameter_names.append(key)
        except:
            parameter_names = []

        total = len(rows)

        for parameter_name in parameter_names:

            missing = 0

            for row in rows:

                try:
                    value = row.get(
                        parameter_name,
                        ""
                    )
                except:
                    value = ""

                if value in ("", None):
                    missing += 1

            if missing == 0:
                continue

            filled = total - missing

            fill_percent = 0.0

            if total:
                fill_percent = round(
                    (filled * 100.0) / total,
                    1
                )

            table.append(
                [
                    category,
                    parameter_name,
                    total,
                    missing,
                    filled,
                    "{} %".format(
                        fill_percent
                    )
                ]
            )

    return table


def build_level_summary_table(data_result, summary_info):
    """
    P2: build the level-wise grouping table.

    Returns (headers, rows). One row per (Level x Category) pair present in
    the collected data. Elements is a static count; every metric cell is a
    live SUMIF formula against that category sheet's Level column, so the
    report stays in sync with the underlying element data.
    """
    category_order = ("Beam", "Column", "Slab", "Foundation")

    level_order = []
    level_counts = {}

    for category_name in category_order:
        rows = data_result.get(category_name, [])
        for row in rows:
            try:
                level_text = str(row.get("Level", "") or "").strip()
            except:
                level_text = ""

            level_key = level_text if level_text else "(No Level)"

            if level_key not in level_counts:
                level_counts[level_key] = {}
                level_order.append(level_key)

            per_category = level_counts[level_key]
            per_category[category_name] = (
                per_category.get(category_name, 0) + 1
            )

    headers = [
        "Level",
        "Category",
        "Elements",
        "Total Volume (m3)",
        "Total Area (m2)",
        "Total Length (m)"
    ]

    metric_keys = (
        "Volume (m3)",
        "Area (m2)",
        "Length (m)"
    )

    rows_out = []

    for level_key in level_order:

        per_category = level_counts[level_key]

        for category_name in category_order:

            if category_name not in per_category:
                continue

            info = summary_info.get(category_name) or {}

            try:
                columns = info.get("columns") or {}
            except:
                columns = {}

            try:
                level_col = info.get("level_col") or ""
            except:
                level_col = ""

            try:
                data_end = info.get("data_end") or 0
            except:
                data_end = 0

            row = [
                level_key,
                category_name,
                per_category[category_name]
            ]

            for metric_key in metric_keys:

                cell = ""

                metric_letter = columns.get(metric_key)

                if metric_letter and level_col and data_end > 1:

                    criteria = '"{0}"'.format(level_key)

                    formula = (
                        "SUMIF({0}!${1}$2:${1}${4},{2},"
                        "{0}!${3}$2:${3}${4})"
                    ).format(
                        category_name,
                        level_col,
                        criteria,
                        metric_letter,
                        data_end
                    )

                    cell = ("FORMULA", formula)

                row.append(cell)

            rows_out.append(row)

    return (headers, rows_out)


def build_grade_summary_table(data_result, summary_info):
    """
    P2: build the concrete-grade grouping table.

    Returns (headers, rows). One row per (Grade x Category) pair present
    in the collected data. Elements is a static count; every metric cell
    is a live SUMIF formula against that category sheet's Grade column,
    so the report stays in sync with the underlying element data.
    """
    category_order = ("Beam", "Column", "Slab", "Foundation")

    grade_order = []
    grade_counts = {}

    for category_name in category_order:
        rows = data_result.get(category_name, [])
        for row in rows:
            try:
                grade_text = str(row.get("Grade", "") or "").strip()
            except:
                grade_text = ""

            grade_key = grade_text if grade_text else "(No Grade)"

            if grade_key not in grade_counts:
                grade_counts[grade_key] = {}
                grade_order.append(grade_key)

            per_category = grade_counts[grade_key]
            per_category[category_name] = (
                per_category.get(category_name, 0) + 1
            )

    headers = [
        "Grade",
        "Category",
        "Elements",
        "Total Volume (m3)",
        "Total Area (m2)",
        "Total Length (m)"
    ]

    metric_keys = (
        "Volume (m3)",
        "Area (m2)",
        "Length (m)"
    )

    rows_out = []

    for grade_key in grade_order:

        per_category = grade_counts[grade_key]

        for category_name in category_order:

            if category_name not in per_category:
                continue

            info = summary_info.get(category_name) or {}

            try:
                columns = info.get("columns") or {}
            except:
                columns = {}

            try:
                grade_col = info.get("grade_col") or ""
            except:
                grade_col = ""

            try:
                data_end = info.get("data_end") or 0
            except:
                data_end = 0

            row = [
                grade_key,
                category_name,
                per_category[category_name]
            ]

            for metric_key in metric_keys:

                cell = ""

                metric_letter = columns.get(metric_key)

                if metric_letter and grade_col and data_end > 1:

                    criteria = '"{0}"'.format(grade_key)

                    formula = (
                        "SUMIF({0}!${1}$2:${1}${4},{2},"
                        "{0}!${3}$2:${3}${4})"
                    ).format(
                        category_name,
                        grade_col,
                        criteria,
                        metric_letter,
                        data_end
                    )

                    cell = ("FORMULA", formula)

                row.append(cell)

            rows_out.append(row)

    return (headers, rows_out)


def sanitize_file_name(value):
    """
    Return a filesystem-safe name fragment for output files.

    Replaces characters Windows forbids in file names with a hyphen,
    collapses whitespace to single hyphens, and never returns an empty
    string (falls back to "Revit Project").
    """
    try:
        text = str(value or "")
    except:
        text = ""

    cleaned_chars = []

    for character in text:
        if character in '\\/:*?"<>|':
            cleaned_chars.append("-")
        else:
            cleaned_chars.append(character)

    cleaned = "".join(cleaned_chars)

    try:
        cleaned = re.sub(r"\s+", "-", cleaned.strip())
        cleaned = re.sub(r"-{2,}", "-", cleaned)
    except:
        pass

    return cleaned if cleaned else "Revit-Project"


def build_default_output_name(doc_title):
    """
    Professional output naming convention, mirroring site workbooks such as
    20260312-CHHANYADO_HOSPITAL_SURAT-CONCRETE_FINISHING_BOQ.xlsm :

        YYYYMMDD-<Project>-CONCRETE_FINISHING_BOQ.xlsx

    The date is today; the project fragment comes from the Revit document
    title, sanitized for the filesystem.
    """
    stamp = time.strftime("%Y%m%d")

    return "{0}-{1}-CONCRETE_FINISHING_BOQ.xlsx".format(
        stamp,
        sanitize_file_name(doc_title)
    )


def build_summary_cover_rows(
        project_name,
        generated_stamp,
        tool_version,
        sheet_names_list):
    """
    Build the front Summary cover sheet rows.

    Returns a uniform-width grid (every row padded to six columns) so the
    worksheet writer can emit it like any other sheet. Static content only:
    project identity, generation stamp, tool version and the workbook's
    sheet listing.
    """
    width = 6

    def pad(cells):
        row = list(cells)
        while len(row) < width:
            row.append("")
        return row[:width]

    rows = [
        pad(["RCC - CONCRETE FINISHING BOQ"]),
        pad([]),
        pad(["Project", project_name]),
        pad(["Generated", generated_stamp]),
        pad(["Tool", tool_version]),
        pad([]),
        pad(["Workbook contents"]),
    ]

    for sheet_name in sheet_names_list:
        rows.append(pad([sheet_name]))

    return rows


# ============================================================
# SITE FORMAT (v1.4.0) - PURE BUILDERS
# ============================================================

def write_basic_xlsx(file_path, data_result, parameter_metadata=None,
                     project_name="", tool_version="", generated_stamp="",
                     site_format=False):
    """
    Write a dependency-free XLSX workbook using Open XML parts.
    This avoids requiring Excel, openpyxl, or other external packages
    inside the pyRevit IronPython environment.

    With site_format=True the workbook takes the v1.4.0 site format: a
    front level-wise Summary plus one manual-site-style detail sheet per
    populated category (merged title blocks, MM size columns,
    VOLUME / SHUTTERING). When site_format=False the legacy classic
    layout (one sheet per category, BOQ Summary, BOQ by Level, Costing)
    is produced instead.
    """
    # v1.4.0: honour the format switch here too so both the export
    # dispatch and any direct callers share one behaviour.
    if site_format:

        return write_site_xlsx(
            file_path,
            data_result,
            project_name=project_name,
            tool_version=tool_version,
            generated_stamp=generated_stamp
        )

    # Only categories that actually contain at least one element produce a
    # sheet. Entirely empty tabs (e.g. an unused Slab category) are omitted
    # so the exported workbook stays free of blank worksheet tabs.
    element_categories = [
        category_name
        for category_name in (
            "Beam",
            "Column",
            "Slab",
            "Foundation"
        )
        if data_result.get(category_name)
    ]

    sheet_names = []

    sheet_rows = {}

    # Tracks which 1-based column indexes hold numeric quantities per
    # sheet so the worksheet writer can apply #,##0.00 styling.
    quantity_column_map = {}

    # Records per-category total row positions and quantity column
    # letters so the BOQ Summary sheet can reference them by formula.
    summary_info = {}

    for sheet_name in element_categories:
        rows = data_result.get(sheet_name, [])

        sheet_names.append(sheet_name)

        headers = ["Element ID"]

        if rows:
            # Preserve selected parameter order from the first generated row.
            for key in rows[0].keys():
                if key != "Element ID":
                    headers.append(key)

        # Prune parameter columns that are entirely empty for every element:
        # such columns only add noise to the sheet. The raw data is still
        # included in the Missing Values Summary report.
        retained_headers = ["Element ID"]

        for key in headers[1:]:

            # v1.6.2: the Dim / Shuttering quantity columns exist to feed
            # the site-format workbook. The classic workbook stays clean
            # without them (Volume / Area / Length / Height / Thickness /
            # Count remain).
            if key == "Qty: Shuttering (m2)" or key.startswith("Qty: Dim"):
                continue

            has_value = False

            for row in rows:

                try:
                    value = row.get(key, "")
                except:
                    value = ""

                if value not in ("", None):
                    has_value = True
                    break

            # P2: Level and Grade are deterministic grouping columns; they
            # are kept even when fully empty so the BOQ by Level / BOQ by
            # Grade sheets can always reference them by formula.
            if has_value or not rows or key in ("Level", "Grade"):
                retained_headers.append(key)

        table = [retained_headers]

        for row in rows:
            values = []
            values.append(row.get("Element ID", ""))

            for key in retained_headers[1:]:
                values.append(row.get(key, ""))

            table.append(values)

        # Quantity takeoff columns are appended by the engine with a
        # "Qty:" prefix. They receive numeric styling and a live SUM
        # totals row at the bottom of the sheet.
        quantity_indexes = []

        for position, header_text in enumerate(retained_headers):

            try:
                is_quantity = header_text[:4] == "Qty:"
            except:
                is_quantity = False

            if is_quantity:
                quantity_indexes.append(position + 1)

        if quantity_indexes and quantity_indexes[0] > 1:
            quantity_column_map[sheet_name] = quantity_indexes

        if quantity_indexes and rows:

            total_row_number = len(table) + 1

            total_values = ["TOTAL"]

            for _unused in retained_headers[1:]:
                total_values.append("")

            for column_index in quantity_indexes:

                column_letter = xlsx_column_name(column_index)

                total_values[column_index - 1] = (
                    "FORMULA",
                    "SUM({0}2:{0}{1})".format(
                        column_letter,
                        len(table)
                    )
                )

            table.append(total_values)

            summary_info[sheet_name] = {
                "elements": len(rows),
                "total_row": total_row_number,
                "columns": {},
                "level_col": "",
                "grade_col": "",
                "data_end": 0
            }

            for column_index in quantity_indexes:

                header_text = retained_headers[
                    column_index - 1
                ]

                # Strip the "Qty: " prefix; strip() guards the space
                # that follows the colon so metric keys line up with
                # the BOQ Summary column labels exactly.
                summary_info[sheet_name]["columns"][
                    header_text[4:].strip()
                ] = xlsx_column_name(column_index)

            # P2: remember the Level column letter and the last data row so
            # the level-wise grouping sheet can build live SUMIF formulas.
            try:
                summary_info[sheet_name]["level_col"] = (
                    xlsx_column_name(
                        retained_headers.index("Level") + 1
                    )
                )
            except:
                pass

            # P2: same for the Grade column so the grade-wise grouping
            # sheet can build its live SUMIF formulas.
            try:
                summary_info[sheet_name]["grade_col"] = (
                    xlsx_column_name(
                        retained_headers.index("Grade") + 1
                    )
                )
            except:
                pass

            summary_info[sheet_name]["data_end"] = len(table)

        sheet_rows[sheet_name] = table

    # Build the BOQ Summary sheet from the recorded category totals.
    # Each cell references its category TOTAL row directly, so Excel
    # keeps every figure in sync with the underlying element sheets.
    summary_metric_order = [
        ("Volume (m3)", "Total Volume (m3)"),
        ("Area (m2)", "Total Area (m2)"),
        ("Length (m)", "Total Length (m)")
    ]

    summary_table = [
        [
            "Category",
            "Elements",
            "Total Volume (m3)",
            "Total Area (m2)",
            "Total Length (m)"
        ]
    ]

    for category_name in ("Beam", "Column", "Slab", "Foundation"):

        info = summary_info.get(category_name)

        if not info:
            continue

        summary_row = [
            category_name,
            info["elements"]
        ]

        for metric_key, _summary_header in summary_metric_order:

            reference = ""

            metric_column = info["columns"].get(metric_key)

            if metric_column:
                reference = (
                    "FORMULA",
                    "{0}!{1}{2}".format(
                        category_name,
                        metric_column,
                        info["total_row"]
                    )
                )

            summary_row.append(reference)

        summary_table.append(summary_row)

    if len(summary_table) > 1:

        summary_data_end = len(summary_table) - 1

        grand_values = ["GRAND TOTAL"]

        grand_values.append(
            (
                "FORMULA",
                "SUM(B2:B{0})".format(summary_data_end)
            )
        )

        for offset in range(3, 6):

            grand_letter = xlsx_column_name(offset)

            grand_values.append(
                (
                    "FORMULA",
                    "SUM({0}2:{0}{1})".format(
                        grand_letter,
                        summary_data_end
                    )
                )
            )

        summary_table.append(grand_values)

        # Place the summary right after the element sheets so it is the
        # first thing reviewers see after the raw category data.
        summary_position = len(sheet_names)
        sheet_names.insert(summary_position, "BOQ Summary")
        sheet_rows["BOQ Summary"] = summary_table

        quantity_column_map["BOQ Summary"] = [2, 3, 4, 5]

    # P2: level-wise grouping. One row per Level x Category with live SUMIF
    # formulas against the category sheets, placed between BOQ Summary and
    # Costing so reviewers see grouped quantities right after totals.
    level_headers, level_rows = build_level_summary_table(
        data_result,
        summary_info
    )

    if level_rows:

        sheet_names.append("BOQ by Level")
        sheet_rows["BOQ by Level"] = [level_headers] + level_rows
        quantity_column_map["BOQ by Level"] = [4, 5, 6]

    # P2: concrete-grade grouping. One row per Grade x Category with live
    # SUMIF formulas, placed directly after BOQ by Level so the grouped
    # views stay together before Costing.
    grade_headers, grade_rows = build_grade_summary_table(
        data_result,
        summary_info
    )

    if grade_rows:

        sheet_names.append("BOQ by Grade")
        sheet_rows["BOQ by Grade"] = [grade_headers] + grade_rows
        quantity_column_map["BOQ by Grade"] = [4, 5, 6]

    # Per-element Costing sheet. Each element row carries its primary
    # quantity, its unit rate and a computed amount (quantity x rate).
    # build_costing_sheet lives in lib/costing_engine.py (section 9).
    # Imported at call time to avoid a circular import between the
    # workbook writer and the costing engine.
    from costing_engine import build_costing_sheet

    costing_sheet = build_costing_sheet(
        data_result
    )

    if len(costing_sheet) > 1:
        sheet_names.append("Costing")
        sheet_rows["Costing"] = costing_sheet
        quantity_column_map["Costing"] = [3, 4, 5]

    # Professional output: front Summary cover as the first sheet.
    summary_cover = build_summary_cover_rows(
        project_name,
        generated_stamp,
        tool_version,
        list(sheet_names)
    )

    sheet_names.insert(0, "Summary")
    sheet_rows["Summary"] = summary_cover

    parent_dir = os.path.dirname(file_path)

    if parent_dir and not os.path.exists(parent_dir):
        os.makedirs(parent_dir)

    temp_path = file_path + ".tmp"

    if os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except:
            pass

    with zipfile.ZipFile(
        temp_path,
        "w",
        zipfile.ZIP_DEFLATED
    ) as archive:

        archive.writestr(
            "[Content_Types].xml",
            build_xlsx_content_types_xml(
                len(sheet_names)
            ).encode("utf-8")
        )

        archive.writestr(
            "_rels/.rels",
            build_xlsx_root_rels_xml().encode("utf-8")
        )

        archive.writestr(
            "xl/workbook.xml",
            build_xlsx_workbook_xml(
                sheet_names
            ).encode("utf-8")
        )

        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            build_xlsx_workbook_rels_xml(
                len(sheet_names)
            ).encode("utf-8")
        )

        archive.writestr(
            "xl/styles.xml",
            enforce_uniform_grid_borders(
                build_xlsx_styles_xml()).encode("utf-8")
        )

        for index, sheet_name in enumerate(sheet_names, 1):
            archive.writestr(
                "xl/worksheets/sheet{}.xml".format(index),
                build_xlsx_sheet_xml(
                    sheet_rows[sheet_name],
                    quantity_column_map.get(sheet_name)
                ).encode("utf-8")
            )

    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except:
            pass

    os.rename(temp_path, file_path)

    return sheet_rows


# ============================================================
# SITE FORMAT (v1.4.0) - PURE BUILDERS
#
# Reproduces the hand-made site BOQ look: merged title block rows,
# a light-blue two-tier header grid, millimetre dimension columns,
# VOLUME + SHUTTERING figures per element and a level-wise front
# Summary. Pure and Revit-free so test_xlsx_writer.py exercises
# the layout rules directly.
# ============================================================

# Manual category order drives sheet sequence everywhere below.
SITE_CATEGORY_ORDER = ("Beam", "Column", "Slab", "Foundation")

SITE_DETAIL_BAND_ROWS = (5, 6)
SITE_DETAIL_DATA_START_ROW = 7


def _site_sort_key(level_name):
    """
    Natural sort key for level text so detail rows group by storey.

    Documented building order (lowest to highest): foundation/basement
    levels, plinth, numbered levels (1, 2, ... 10+), terrace, overhead
    tank / lift machine room levels, then any other text alphabetically.

    Common site level names carry no digits (PLINTH LEVEL, TERRACE
    LEVEL, OHW/LMR LEVEL), so keyword ranks sit outside the numeric
    range; numeric names keep the "Level 2 sorts after Level 1"
    behaviour. Levels that embed their model order ("01 FOUNDATION
    LEVEL") still rank by the keyword, which matches the same order.
    """

    try:
        level_text = str(level_name).strip()
    except:
        level_text = ""

    lowered = level_text.lower()

    # Keyword ranks first: they decide for named storeys that either
    # carry no number at all or whose number is the model list index.
    if "foundation" in lowered or lowered.startswith("base"):
        return (-300, lowered)

    if "plinth" in lowered:
        return (-200, lowered)

    if "terrace" in lowered:
        return (10 ** 9 - 2, lowered)

    if "ohw" in lowered or "lmr" in lowered:
        return (10 ** 9 - 1, lowered)

    match = re.search(r"(\d+)", level_text)

    number_part = int(match.group(1)) if match else 10 ** 9

    return (number_part, lowered)


def _sort_site_rows(rows):
    """
    Order site detail rows by their first LEVEL-like column (ascending).

    Looks for the first selected-parameter key containing "LEVEL"
    (LEVEL_V, BASE LEVEL, Level, ...) and stable-sorts the rows with
    _site_sort_key so each storey's elements stay contiguous in
    ascending building order. Rows without any level-like column (e.g.
    Slab / Foundation selections) come back in their original
    collection order; the sort is stable, so elements within one level
    keep their collection order and the SNO sequence stays
    deterministic.
    """
    result = list(rows or [])

    level_key = None

    for probe in result[:1]:
        for key in probe.keys():
            try:
                key_text = str(key)
            except:
                continue
            if "LEVEL" in key_text.upper():
                level_key = key
                break

    if level_key is None:
        return result

    try:
        result.sort(key=lambda row: _site_sort_key(row.get(level_key, "")))
    except:
        pass

    return result


def _site_cell_value(row, key):
    """Return a stripped string value from an element row, never None."""
    try:
        return str(row.get(key, "") or "").strip()
    except:
        return ""


def _site_numeric(row, key):
    """Return a rounded float or "" from one element-row column."""
    try:
        value = row.get(key, "")
    except:
        value = ""

    if value in ("", None):
        return ""

    try:
        return round(float(value), 2)
    except:
        return ""


def _site_dim_value(row, key):
    """
    Return the UNROUNDED float of one dimension column, or "".

    Dimensions must not be pre-rounded before millimetre conversion
    (round(6.096, 2) -> 6.1 would shift the SIZE column to 6100 mm);
    only the displayed VOLUME / SHUTTERING figures use 2 decimals.
    """
    try:
        value = row.get(key, "")
    except:
        value = ""

    if value in ("", None):
        return ""

    try:
        return float(value)
    except:
        return ""


def _site_desc_text(value):
    """
    Format one user-selected parameter value for the DESCRIPTION cell.

    Whole-number values lose their trailing .0 (raw float payloads from
    synthetic or typed-in parameters render as clean integers); every
    other payload passes through as stripped text. Empty stays "".
    """
    if value in ("", None):
        return ""

    try:
        text = str(value).strip()
    except:
        return ""

    try:
        number_value = float(text)

        if number_value == int(number_value):
            return str(int(number_value))
    except:
        pass

    return text


def build_site_detail_sheet(category_name, rows, project_name,
                            include_formwork=True, formwork_factor=1.0):
    """
    Site detail sheet, selection-only columns plus dimension columns
    (L/W/H) and a formula-based SHUTTERING column.

    Shows exactly the parameters the user ticked in the UI, then three
    automatic dimension columns (L/W/H in metres), then one automatic
    "SHUTTERING (SQM)" column with a live Excel formula that calculates
    shuttering area from the dimension cells - rendered only when
    include_formwork is True (the footer "Include formwork" checkbox).

    Layout: rows 1-3 merged title block, row 4 spacer, rows 5/6
    two-tier band (each header vertically merged), row 7+ one row per
    element with SNO followed by the selected values in UI order,
    dimension values, and the shuttering formula.

    meta carries the dynamic widths (per parameter count) and, when
    formwork is shown, the SHUTTERING column letter so a future summary
    can aggregate it.
    """
    data_rows = rows or []

    skip_names = ("Element ID", "Level", "Grade")

    param_names = []

    for probe in data_rows[:1]:
        for key in probe.keys():
            try:
                key_text = str(key)
            except:
                continue
            if key_text in skip_names:
                continue
            if key_text[:4] == "Qty:":
                continue
            param_names.append(key_text)

    show_shuttering = bool(include_formwork)

    # Dimension columns (L/W/H) are always present when shuttering is shown
    dim_count = 3 if show_shuttering else 0
    total_cols = 1 + len(param_names) + dim_count + (1 if show_shuttering else 0)

    def merge_vertical(label):
        return ("MERGE_V", label)

    band_one = [merge_vertical("SNO")]

    for param_name in param_names:
        band_one.append(merge_vertical(str(param_name).upper()))

    band_two = ["" for _band_cell in param_names]

    if show_shuttering:
        band_one.append(merge_vertical("L (m)"))
        band_two.append("")
        band_one.append(merge_vertical("W (m)"))
        band_two.append("")
        band_one.append(merge_vertical("H (m)"))
        band_two.append("")
        band_one.append(merge_vertical("SHUTTERING (SQM)"))
        band_two.append("")

    table = [
        [str(project_name or "")],
        ["RCC - CONCRETE FINISHING BOQ"],
        ["{0} DETAILS".format(category_name.upper())],
        [""],
        band_one,
        band_two,
    ]

    item_number = 1

    for row in data_rows:

        out_values = [item_number]

        for param_name in param_names:

            try:
                raw_value = row.get(param_name, "")
            except:
                raw_value = ""

            display_value = ""

            if raw_value not in ("", None):
                try:
                    numeric = float(raw_value)
                    if numeric == int(numeric):
                        display_value = str(int(numeric))
                    else:
                        display_value = str(raw_value)
                except:
                    display_value = str(raw_value)

            out_values.append(display_value)

        if show_shuttering:

            # Get dimension values for this row
            dim_l = row.get("Qty: Dim L (m)", "")
            dim_w = row.get("Qty: Dim W (m)", "")
            dim_h = row.get("Qty: Dim H (m)", "")

            # Format dimension values
            def fmt_dim(val):
                if val in ("", None):
                    return ""
                try:
                    return "{0:.3f}".format(float(val))
                except:
                    return str(val)

            out_values.append(fmt_dim(dim_l))
            out_values.append(fmt_dim(dim_w))
            out_values.append(fmt_dim(dim_h))

            # Build formula cell as a tuple (FORMULA, expression)
            # Data starts at row SITE_DETAIL_DATA_START_ROW (7)
            data_row = SITE_DETAIL_DATA_START_ROW + item_number - 1
            l_col = "{0}{1}".format(xlsx_column_name(1 + len(param_names) + 1), data_row)
            w_col = "{0}{1}".format(xlsx_column_name(1 + len(param_names) + 2), data_row)
            h_col = "{0}{1}".format(xlsx_column_name(1 + len(param_names) + 3), data_row)
            formula = build_shuttering_formula(
                category_name, l_col, w_col, h_col, formwork_factor
            )
            out_values.append(("FORMULA", formula))

        table.append(out_values)
        item_number += 1

    shuttering_col = ""

    if show_shuttering:
        shuttering_col = xlsx_column_name(
            1 + len(param_names) + dim_count + 1
        )

    meta = {
        "columns": {},
        "level_col": "",
        "shuttering_col": shuttering_col,
        "total_row": len(table),
        "data_start": SITE_DETAIL_DATA_START_ROW,
        "data_end": len(table),
        "elements": len(data_rows),
        "widths": (
            [7]
            + [18 for _name in param_names]
            + ([8, 8, 8, 12] if show_shuttering else [])
        ),
        "param_columns": list(param_names)
    }

    return (table, meta)


def build_site_summary_sheet(data_result, site_detail_meta, project_name,
                             include_formwork=True):
    """
    Build the front Summary in the site format.

    Layout (1-based Excel rows):
      Row 1 : project                     (writer merges across width)
      Row 2 : RCC - CONCRETE FINISHING BOQ
      Row 3 : ITEM-WISE SUMMARY - CONCRETE AND SHUTTERING
      Row 4 : blank spacer row
      Row 5 : SNO | CATEGORY | ELEMENTS | VOLUME (m3) | SHUTTERING (m2)
      Row 6 : band two (vertical merges / blanks)

    SNO | CATEGORY | ELEMENTS are static; VOLUME aggregates the rows'
    Qty: Volume (m3) values. The SHUTTERING (m2) column (aggregated
    from Qty: Shuttering (m2), plus a live SUM in the TOTAL row) is
    rendered only when include_formwork is True - the same footer
    checkbox that drives the detail sheets' SHUTTERING (SQM) column.

    Returns (summary_table, meta) where meta documents the produced
    grid for the regression harness.
    """
    present_categories = [
        category_name
        for category_name in SITE_CATEGORY_ORDER
        if category_name in site_detail_meta
    ]

    if not present_categories:
        return ([], {})

    header_label_map = {
        "Beam": "BEAM",
        "Column": "COLUMN",
        "Slab": "SLAB",
        "Foundation": "FOUNDATION"
    }

    # Element rows in data_result still carry the metric columns even
    # though the selection-only detail sheets hide them. Aggregate
    # VOLUME and SHUTTERING per category straight from data_result so
    # the Summary keeps both figures while the detail tabs stay clean.
    def aggregate_metric(category_name, metric_key):
        total = 0.0
        for row in (data_result.get(category_name) or []):
            try:
                metric_value = float(row.get(metric_key, 0) or 0)
            except:
                metric_value = 0.0
            total += metric_value
        return round(total, 2) if total else ""

    show_shuttering = bool(include_formwork)

    out_rows = [
        [str(project_name or "")],
        ["RCC - CONCRETE FINISHING BOQ"],
        [
            "ITEM-WISE SUMMARY - CONCRETE{0}".format(
                " AND SHUTTERING" if show_shuttering else ""
            )
        ],
        [],
        [
            ("MERGE_V", "SNO"),
            ("MERGE_V", "CATEGORY"),
            "ELEMENTS",
            "VOLUME (m3)",
        ] + (["SHUTTERING (m2)"] if show_shuttering else []),
        ["", "", "", ""] + ([""] if show_shuttering else []),
    ]

    first_data_row = len(out_rows) + 1

    item_number = 1

    for category_name in present_categories:

        category_meta = site_detail_meta.get(category_name, {})

        category_row = [
            item_number,
            header_label_map[category_name],
            category_meta.get("elements", 0),
            aggregate_metric(category_name, "Qty: Volume (m3)")
        ]

        if show_shuttering:
            category_row.append(
                aggregate_metric(category_name, "Qty: Shuttering (m2)")
            )

        out_rows.append(category_row)

        item_number += 1

    total_row_number = len(out_rows) + 1

    vol_col = 4
    shut_col = 5

    vol_letter = xlsx_column_name(vol_col)
    shut_letter = xlsx_column_name(shut_col)

    total_row_cells = [
        "TOTAL",
        "",
        "",
        (
            "FORMULA",
            "SUM({0}{1}:{0}{2})".format(
                vol_letter, first_data_row, total_row_number - 1)
        )
    ]

    if show_shuttering:
        total_row_cells.append(
            (
                "FORMULA",
                "SUM({0}{1}:{0}{2})".format(
                    shut_letter, first_data_row, total_row_number - 1)
            )
        )

    out_rows.append(total_row_cells)

    summary_columns = {
        "Volume (m3)": vol_letter
    }

    if show_shuttering:
        summary_columns["Shuttering (m2)"] = shut_letter

    meta = {
        "present_categories": present_categories,
        "columns": summary_columns,
        "total_columns": 5 if show_shuttering else 4,
        "bands": (5, 6),
        "grid_start": first_data_row,
        "levels": []
    }

    return (out_rows, meta)


SITE_DETAIL_COLUMN_WIDTHS = [6, 30, 8, 8, 8, 12, 14, 14]


def write_site_xlsx(file_path, data_result, project_name="",
                    tool_version="", generated_stamp="",
                    include_formwork=True):
    """
    Write the v1.4.0 site-format workbook.

    Sheet plan mirrors the manual site BOQ:
      Summary                - element-count cover
      Beam / Column / Slab /
      Foundation             - one detail sheet per populated category
                               with title blocks, one column per
                               user-selected parameter and (P3, v1.8.0)
                               an automatic SHUTTERING (SQM) column
                               when include_formwork is True - no other
                               automatic columns and no SUM totals row.

    Returns a plain {sheet_name: table} mapping (identical contract to
    write_basic_xlsx) covering Summary plus every populated category.
    """
    produced = {}

    site_detail_meta = {}

    sheet_names = ["Summary"]

    sheet_rows = {}

    sheet_widths = {}

    sheet_meta = {}

    for category_name in SITE_CATEGORY_ORDER:

        rows = _sort_site_rows(
            data_result.get(category_name) or []
        )

        if not rows:
            continue

        table, meta = build_site_detail_sheet(
            category_name,
            rows,
            project_name,
            include_formwork=include_formwork,
            formwork_factor=get_formwork_factor(category_name)
        )

        sheet_names.append(category_name)

        sheet_rows[category_name] = table

        sheet_widths[category_name] = meta.get("widths") or [7, 18]

        sheet_meta[category_name] = {
            "kind": "detail",
            "band_rows": SITE_DETAIL_BAND_ROWS,
            "data_start": meta["data_start"],
            "total_row": meta["total_row"]
        }

        site_detail_meta[category_name] = meta

    summary_table, summary_meta = build_site_summary_sheet(
        data_result,
        site_detail_meta,
        project_name,
        include_formwork=include_formwork
    )

    if not summary_table:
        # Nothing exported at all - keep the workbook honest with an
        # empty shell rather than writing a broken file.
        summary_table = [
            [project_name],
            ["RCC - CONCRETE FINISHING BOQ"],
            ["Nothing to export yet — pick the elements you need and run it again"],
            [],
        ]

        summary_meta = {"empty": True}

    total_columns = summary_meta.get("total_columns", 3)

    # SNO | CATEGORY | ELEMENTS | VOL (+ SHUT only when formwork shows)
    summary_widths = [7, 24, 10, 14] + (
        [17] if include_formwork else []
    )


    sheet_rows["Summary"] = summary_table

    sheet_widths["Summary"] = summary_widths

    sheet_meta["Summary"] = {
        "kind": "summary",
        "band_rows": summary_meta.get(
            "bands",
            SITE_DETAIL_BAND_ROWS
        ),
        "grid_start": summary_meta.get("grid_start", 7),
        "columns": summary_meta.get("columns", {}),
        "levels": summary_meta.get("levels", []),
        "bands_cells": len(summary_table[4]) if len(summary_table) > 4 else 0
    }

    parent_dir = os.path.dirname(file_path)

    if parent_dir and not os.path.exists(parent_dir):
        os.makedirs(parent_dir)

    temp_path = file_path + ".tmp"

    if os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except:
            pass

    with zipfile.ZipFile(
        temp_path,
        "w",
        zipfile.ZIP_DEFLATED
    ) as archive:

        archive.writestr(
            "[Content_Types].xml",
            build_xlsx_content_types_xml(
                len(sheet_names)
            ).encode("utf-8")
        )

        archive.writestr(
            "_rels/.rels",
            build_xlsx_root_rels_xml().encode("utf-8")
        )

        archive.writestr(
            "xl/workbook.xml",
            build_xlsx_workbook_xml(sheet_names).encode("utf-8")
        )

        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            build_xlsx_workbook_rels_xml(
                len(sheet_names)
            ).encode("utf-8")
        )

        archive.writestr(
            "xl/styles.xml",
            enforce_uniform_grid_borders(
                build_xlsx_styles_xml()).encode("utf-8")
        )

        for index, sheet_name in enumerate(sheet_names, 1):

            sheet_xml = build_xlsx_sheet_xml_site(
                sheet_rows[sheet_name],
                sheet_widths.get(sheet_name)
            )

            archive.writestr(
                "xl/worksheets/sheet{0}.xml".format(index),
                sheet_xml.encode("utf-8")
            )

    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except:
            pass

    os.rename(temp_path, file_path)

    # Plain {sheet_name: table} mapping - same contract as
    # write_basic_xlsx, so the export dialog code can treat both
    # writers uniformly.
    return sheet_rows


def enforce_uniform_grid_borders(styles_xml):
    """Harden styles.xml: every cellXf gets the shared thin-box border
    (borderId=2). Guarantees data-row borders render on every sheet
    regardless of which style index a builder picked; fills, fonts and
    number formats are untouched."""
    try:
        head, sep, tail = styles_xml.partition("<cellXfs")
        if not sep:
            return styles_xml
        gt = tail.index(">")
        open_tail = tail[:gt + 1]
        rest = tail[gt + 1:]
        close_idx = rest.rfind("</cellXfs>")
        if close_idx < 0:
            return styles_xml
        body = rest[:close_idx]
        parts = []
        cursor = 0
        for fm in re.finditer(r"<xf\b[^>]*>", body):
            parts.append(body[cursor:fm.start()])
            tag = fm.group(0)
            tag = re.sub(r'\s*borderId="\d+"', "", tag)
            tag = tag.replace("<xf ", '<xf borderId="2" ', 1)                if tag.startswith("<xf ") else                 tag.replace("<xf", '<xf borderId="2"', 1)
            if "applyBorder=" not in tag:
                tag = tag.rstrip()
                if tag.endswith("/>"):
                    tag = tag[:-2] + ' applyBorder="1"/>'
                else:
                    tag += ' applyBorder="1"'
            parts.append(tag)
            cursor = fm.end()
        parts.append(body[cursor:])
        return head + sep + open_tail + "".join(parts) + rest[close_idx:]
    except:
        return styles_xml

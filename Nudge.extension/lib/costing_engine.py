# -*- coding: utf-8 -*-
"""Costing engine - per-element rate x quantity, and the rate build-up.

Moved verbatim from BOQ.pushbutton/script.py in the v1.8.6 module split
(PROJECT_STRUCTURE.md section 9). Pure Python (xlsx_column_name comes
from lib/export_engine.py); no Revit symbols.

P11 (rate analysis) lands below build_costing_sheet: where that sheet
takes a rate as given, the analysis says where the rate comes from -
material, labour, machinery, wastage and overheads. P12 will supply those
figures from a rate database; until then a caller passes them in.
"""
from export_engine import xlsx_column_name

RATE_ANALYSIS_SHEET_NAME = "Rate Analysis"

RATE_ANALYSIS_HEADERS = (
    "Item Code", "Description", "Unit",
    "Material", "Wastage", "Labour", "Machinery", "Overheads",
    "Analysed Rate", "Status",
)

# The three that are money per unit, and the two that are percentages.
RATE_COST_COMPONENTS = ("material", "labour", "machinery")
RATE_PERCENT_COMPONENTS = ("wastage_pct", "overheads_pct")

# Said once here rather than assumed in three places: wastage applies to
# the material only - labour and machinery are not wasted - and overheads
# apply to everything under them.
RATE_BASIS = (
    "Wastage on material; overheads on material + wastage + labour + "
    "machinery"
)

STATUS_PRICED = "Priced"
STATUS_INPUT_REQUIRED = "Input required"

def build_costing_sheet(data_result, site_items=None):
    """
    Build a per-element Costing sheet.

    Each exported element contributes one row that shows its primary metric
    quantity, its unit rate (sourced from a Cost / Rate / Price parameter
    already present in the element row) and a live amount equal to
    quantity x rate. A trailing TOTAL row sums the amount column.

    P7 site items are appended as further lines before that TOTAL, so the
    sheet's own SUM covers model-derived and typed work alike and there is
    only ever one cost total to read.

    Returns a 2D row table ready for the XLSX writer. When no element
    carries both a quantity and a usable rate, only the header remains.
    """
    rate_hints = (
        "cost",
        "rate",
        "price"
    )

    headers = [
        "Category",
        "Element ID",
        "Quantity",
        "Rate",
        "Amount"
    ]

    table = [headers]

    for category_name in (
        "Beam", "Column", "Structure Wall", "Slab", "Foundation", "Rebar"
    ):

        rows = data_result.get(category_name, [])

        if not rows:
            continue

        # Find the rate parameter for this category. Prefer a column whose
        # name clearly marks it as a unit cost / rate / price.
        rate_key = None

        for key in rows[0].keys():

            if key in ("Element ID",):
                continue

            try:
                lowered = str(key).lower()
            except:
                lowered = ""

            if lowered[:4] == "qty:":
                continue

            if any(hint in lowered for hint in rate_hints):
                rate_key = key
                break

        # Choose the primary quantity column when multiple metrics exist.
        if category_name == "Rebar":
            quantity_keys = [
                "Rebar: Total Weight (kg)",
                "Rebar: Total Length (m)"
            ]
        else:
            quantity_keys = [
                "Qty: Volume (m3)",
                "Qty: Area (m2)",
                "Qty: Length (m)"
            ]

        for row in rows:

            element_id = row.get("Element ID", "")

            quantity_value = ""

            for qkey in quantity_keys:
                try:
                    quantity_value = row.get(qkey, "")
                except Exception:
                    quantity_value = ""

                if quantity_value not in ("", None):
                    break

            rate_value = ""

            if rate_key is not None:
                try:
                    rate_value = row.get(rate_key, "")
                except Exception:
                    rate_value = ""

            quantity_number = None
            rate_number = None

            try:
                quantity_number = float(quantity_value)
            except Exception:
                quantity_number = None

            try:
                rate_number = float(rate_value)
            except Exception:
                rate_number = None

            row_number = len(table) + 1

            amount = ""

            if quantity_number is not None and rate_number is not None:
                amount = (
                    "FORMULA",
                    "{0}{1}*{2}{1}".format(
                        xlsx_column_name(3),
                        row_number,
                        xlsx_column_name(4),
                        row_number
                    )
                )

            table.append(
                [
                    category_name,
                    element_id,
                    quantity_value,
                    rate_value,
                    amount
                ]
            )

    # P7: typed site items, priced the same way and summed by the same
    # TOTAL. An unpriced line still appears, with a blank Amount, so the
    # sheet never hides work that is merely awaiting a rate.
    if site_items:

        from site_items_engine import site_item_label

        for item in site_items:

            quantity_number = item.get("quantity")
            rate_number = item.get("rate")

            row_number = len(table) + 1

            amount = ""

            if quantity_number is not None and rate_number is not None:
                amount = (
                    "FORMULA",
                    "{0}{1}*{2}{1}".format(
                        xlsx_column_name(3),
                        row_number,
                        xlsx_column_name(4),
                        row_number
                    )
                )

            table.append(
                [
                    "Site Item",
                    site_item_label(item),
                    quantity_number if quantity_number is not None else "",
                    rate_number if rate_number is not None else "",
                    amount
                ]
            )

    if len(table) > 1:

        total_row_number = len(table) + 1

        total_row = [
            "TOTAL",
            "",
            "",
            "",
            (
                "FORMULA",
                "SUM({0}2:{0}{1})".format(
                    xlsx_column_name(5),
                    total_row_number - 1
                )
            )
        ]

        table.append(total_row)

    return table


# ------------------------------------------------------------------
# P11: rate analysis
# ------------------------------------------------------------------


def _rate_number(value):
    """A non-negative number, or None when the figure is unusable.

    Absent, blank, negative, boolean and non-numeric all normalize to
    None: a rate build-up that quietly treats a missing labour figure as
    zero prices work nobody costed.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except Exception:
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    if number < 0:
        return None
    return number


def normalize_rate_analysis(raw):
    """Normalize one item's rate build-up.

    Every component is kept as given or as None - never defaulted to
    zero - so compute_analysed_rate can say which figure is missing
    instead of inventing a rate.
    """
    raw = raw if isinstance(raw, dict) else {}

    def text(key):
        try:
            return str(raw.get(key, "") or "").strip()
        except Exception:
            return ""

    analysis = {
        "item_code": text("item_code"),
        "description": text("description"),
        "unit": text("unit"),
    }
    for component in RATE_COST_COMPONENTS + RATE_PERCENT_COMPONENTS:
        analysis[component] = _rate_number(raw.get(component))
    return analysis


def compute_analysed_rate(analysis):
    """Return (rate, missing) for one normalized build-up.

    rate is None whenever any of the five components is missing, and
    `missing` names them - the P6 rule applied to money: an unsupported
    allowance stays blank rather than being priced at zero.
    """
    analysis = analysis if isinstance(analysis, dict) else {}

    missing = [name for name in RATE_COST_COMPONENTS + RATE_PERCENT_COMPONENTS
               if analysis.get(name) is None]
    if missing:
        return None, missing

    material = analysis["material"]
    wastage = material * analysis["wastage_pct"] / 100.0
    subtotal = material + wastage + analysis["labour"] + analysis["machinery"]
    overheads = subtotal * analysis["overheads_pct"] / 100.0

    return round(subtotal + overheads, 2), []


def summarize_rate_analysis(raw_analyses):
    """Normalize, price and describe a list of build-ups, in order."""
    rows = []
    for raw in list(raw_analyses or []):
        analysis = normalize_rate_analysis(raw)
        rate, missing = compute_analysed_rate(analysis)
        analysis["analysed_rate"] = rate
        analysis["missing"] = missing
        analysis["status"] = (
            STATUS_PRICED if rate is not None
            else "{0}: {1}".format(STATUS_INPUT_REQUIRED, ", ".join(missing))
        )
        rows.append(analysis)
    return rows


def build_rate_analysis_sheet(raw_analyses):
    """Build the Rate Analysis table: headers plus one row per item.

    An item whose build-up is incomplete still gets its row - with the
    figures it does have, a blank rate and a status naming what is
    missing - because a silently absent item is the one nobody chases.
    """
    table = [list(RATE_ANALYSIS_HEADERS)]

    for analysis in summarize_rate_analysis(raw_analyses):
        def cell(name):
            value = analysis.get(name)
            return "" if value is None else value

        table.append([
            analysis.get("item_code", ""),
            analysis.get("description", ""),
            analysis.get("unit", ""),
            cell("material"),
            cell("wastage_pct"),
            cell("labour"),
            cell("machinery"),
            cell("overheads_pct"),
            cell("analysed_rate"),
            analysis.get("status", ""),
        ])

    return table


def load_rate_analysis(settings):
    """Read the saved rate build-ups out of the settings document.

    Returns normalized rows, never None, and ignores anything that is not
    a list of dictionaries - a corrupt settings file must not be able to
    stop an export.
    """
    try:
        raw = (settings or {}).get("rate_analysis")
    except AttributeError:
        return []
    if not isinstance(raw, list):
        return []
    return [normalize_rate_analysis(item)
            for item in raw if isinstance(item, dict)]


def save_rate_analysis(settings, analyses):
    """Return the settings document with these build-ups stored.

    Only the declared fields are written, so an item cannot smuggle
    unrelated keys into the settings file.
    """
    document = settings if isinstance(settings, dict) else {}
    stored = []

    for analysis in list(analyses or []):
        if not isinstance(analysis, dict):
            continue
        normalized = normalize_rate_analysis(analysis)
        row = {}
        for key in ("item_code", "description", "unit"):
            if normalized.get(key):
                row[key] = normalized[key]
        for key in RATE_COST_COMPONENTS + RATE_PERCENT_COMPONENTS:
            if normalized.get(key) is not None:
                row[key] = normalized[key]
        if row:
            stored.append(row)

    document["rate_analysis"] = stored
    return document


def find_rate_code_conflict(analyses, item_code, ignore_index=-1):
    """Index of another build-up already using this code, or -1.

    A rate schedule is looked up by item code, so two lines with the same
    code - possibly at different rates - leave nobody sure which one the
    BOQ means. Codes compare case-insensitively and ignore surrounding
    spaces, because "RCC-M30" and "rcc-m30 " are the same item to a reader.
    `ignore_index` is the line being updated, which may keep its own code.
    """
    try:
        wanted = str(item_code or "").strip().upper()
    except Exception:
        return -1
    if not wanted:
        return -1

    for index, analysis in enumerate(list(analyses or [])):
        if index == ignore_index:
            continue
        try:
            code = str((analysis or {}).get("item_code", "") or "")
        except AttributeError:
            continue
        if code.strip().upper() == wanted:
            return index
    return -1

# -*- coding: utf-8 -*-
"""Costing engine - per-element rate x quantity sheet builder.

Moved verbatim from BOQ.pushbutton/script.py in the v1.8.6 module split
(PROJECT_STRUCTURE.md section 9). Pure Python (xlsx_column_name comes
from lib/export_engine.py); no Revit symbols. Future rate-analysis
phases (P11/P12) extend this module.
"""
from export_engine import xlsx_column_name

def build_costing_sheet(data_result):
    """
    Build a per-element Costing sheet.

    Each exported element contributes one row that shows its primary metric
    quantity, its unit rate (sourced from a Cost / Rate / Price parameter
    already present in the element row) and a live amount equal to
    quantity x rate. A trailing TOTAL row sums the amount column.

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

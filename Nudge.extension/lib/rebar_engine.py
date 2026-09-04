# -*- coding: utf-8 -*-
"""P4 Rebar Quantity Engine - pure steel length and weight calculations.

This module deliberately contains no Revit symbols. Revit-bound parameter and
host reads stay in BOQ.pushbutton/script.py; this file owns the deterministic
quantity contract that can be tested in plain Python.
"""


def _positive_number(value):
    """Return a positive float, otherwise None."""
    try:
        number = float(value)
    except:
        return None
    if number <= 0:
        return None
    return number


def rebar_unit_weight_kg_per_m(diameter_mm):
    """Return nominal steel unit weight using the standard d^2/162 rule."""
    diameter = _positive_number(diameter_mm)
    if diameter is None:
        return ""
    return round((diameter * diameter) / 162.0, 4)


def build_rebar_quantity_values(diameter_mm="", quantity="",
                                bar_length_m="", total_length_m=""):
    """Normalize one Rebar/set into the P4 calculated quantity fields.

    Revit's TotalLength is preferred. When it is unavailable, total length is
    derived from individual bar length x included bar Quantity.
    """
    diameter = _positive_number(diameter_mm)
    bar_length = _positive_number(bar_length_m)
    total_length = _positive_number(total_length_m)

    try:
        bar_quantity = int(quantity)
    except:
        bar_quantity = 0
    if bar_quantity < 1:
        bar_quantity = 1

    if total_length is None and bar_length is not None:
        total_length = bar_length * bar_quantity

    unit_weight = rebar_unit_weight_kg_per_m(diameter)
    total_weight = ""
    if unit_weight != "" and total_length is not None:
        total_weight = round(float(unit_weight) * total_length, 3)

    return {
        "Diameter (mm)": round(diameter, 3) if diameter is not None else "",
        "Quantity": bar_quantity,
        "Bar Length (m)": round(bar_length, 4) if bar_length is not None else "",
        "Total Length (m)": round(total_length, 4) if total_length is not None else "",
        "Unit Weight (kg/m)": unit_weight,
        "Total Weight (kg)": total_weight,
    }

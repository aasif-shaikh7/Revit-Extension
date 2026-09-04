# -*- coding: utf-8 -*-
"""P4/P5 Rebar Quantity and BBS Engine.

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


def _rebar_number(value):
    """Read a numeric value, including Revit display text such as '350 mm'."""
    if value in ("", None):
        return None
    try:
        return float(value)
    except:
        pass
    try:
        token = str(value).strip().split()[0].replace(",", "")
        return float(token)
    except:
        return None


def _rounded_total(value, digits):
    number = _rebar_number(value)
    return round(number, digits) if number is not None else ""


def build_rebar_bbs_table(rebar_rows):
    """Group Revit rebar/set rows into a shape-aware cutting schedule.

    Revit's Bar Length remains the authoritative cutting length because the
    shape definition owns repeated segments, bend radii and hooks. A-H and
    bend/hook fields are retained as an auditable description of that shape.
    """
    dimension_names = tuple("ABCDEFGH")
    headers = (
        ["Bar Mark", "Shape", "Diameter (mm)"]
        + ["{0} (mm)".format(name) for name in dimension_names]
        + [
            "Bend Diameter (mm)", "Hook at Start", "Hook at End",
            "Cutting Length (m)", "Average Bar Length (m)",
            "Length Status", "Quantity", "Total Length (m)",
            "Unit Weight (kg/m)", "Total Weight (kg)",
            "Host Category", "Host Element ID", "Level"
        ]
    )
    grouped = {}
    order = []

    for row in rebar_rows or []:
        dimensions = tuple(
            _rounded_total(row.get("Rebar: {0} (mm)".format(name), ""), 3)
            for name in dimension_names
        )
        cutting_length = _rounded_total(
            row.get("Rebar: Cutting Length (m)",
                    row.get("Rebar: Bar Length (m)", "")),
            4
        )
        shape_name = str(row.get("Rebar: Shape", "") or "")
        diameter = _rounded_total(
            row.get("Rebar: Diameter (mm)", ""), 3
        )
        if not shape_name and diameter == "" and cutting_length == "":
            continue
        key = (
            str(row.get("Rebar: Bar Mark", "") or ""),
            shape_name,
            diameter,
            dimensions,
            _rounded_total(row.get("Rebar: Bend Diameter (mm)", ""), 3),
            str(row.get("Rebar: Hook at Start", "") or ""),
            str(row.get("Rebar: Hook at End", "") or ""),
            cutting_length,
            _rounded_total(row.get("Rebar: Unit Weight (kg/m)", ""), 4),
            str(row.get("Rebar: Host Category", "") or ""),
            str(row.get("Rebar: Host Element ID", "") or ""),
            str(row.get("Level", "") or ""),
        )
        if key not in grouped:
            grouped[key] = {"quantity": 0, "length": 0.0, "weight": 0.0}
            order.append(key)
        quantity = _rebar_number(row.get("Rebar: Quantity", ""))
        total_length = _rebar_number(row.get("Rebar: Total Length (m)", ""))
        total_weight = _rebar_number(row.get("Rebar: Total Weight (kg)", ""))
        grouped[key]["quantity"] += int(quantity) if quantity is not None else 0
        grouped[key]["length"] += total_length if total_length is not None else 0.0
        grouped[key]["weight"] += total_weight if total_weight is not None else 0.0

    table = [headers]
    for key in order:
        values = grouped[key]
        average_length = ""
        if values["quantity"] > 0 and values["length"] > 0:
            average_length = round(
                values["length"] / float(values["quantity"]),
                4
            )
        if key[7] != "":
            length_status = "Fixed / Revit Bar Length"
        elif average_length != "":
            length_status = "Variable set / average only"
        else:
            length_status = "Length unavailable"
        row_values = (
            [key[0], key[1], key[2]] + list(key[3])
            + [key[4], key[5], key[6], key[7], average_length,
               length_status, values["quantity"],
               round(values["length"], 4), key[8],
               round(values["weight"], 3), key[9], key[10], key[11]]
        )
        table.append(row_values)
    return table


def build_rebar_diameter_summary_table(rebar_rows):
    """Return diameter-wise bar count, total length, kilograms and tonnes."""
    headers = [
        "Diameter (mm)", "Number of Bars", "Total Length (m)",
        "Unit Weight (kg/m)", "Total Weight (kg)", "Total Weight (ton)"
    ]
    grouped = {}
    order = []
    for row in rebar_rows or []:
        diameter = _rounded_total(row.get("Rebar: Diameter (mm)", ""), 3)
        if diameter == "":
            continue
        if diameter not in grouped:
            grouped[diameter] = {"quantity": 0, "length": 0.0, "weight": 0.0}
            order.append(diameter)
        quantity = _rebar_number(row.get("Rebar: Quantity", ""))
        length = _rebar_number(row.get("Rebar: Total Length (m)", ""))
        weight = _rebar_number(row.get("Rebar: Total Weight (kg)", ""))
        grouped[diameter]["quantity"] += int(quantity) if quantity is not None else 0
        grouped[diameter]["length"] += length if length is not None else 0.0
        grouped[diameter]["weight"] += weight if weight is not None else 0.0

    table = [headers]
    for diameter in sorted(order):
        values = grouped[diameter]
        unit_weight = rebar_unit_weight_kg_per_m(diameter)
        table.append([
            diameter, values["quantity"], round(values["length"], 4),
            unit_weight, round(values["weight"], 3),
            round(values["weight"] / 1000.0, 4)
        ])
    return table

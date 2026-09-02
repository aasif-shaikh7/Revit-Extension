# -*- coding: utf-8 -*-
"""Quantity engine - unit conversion and dimension helpers.

Moved verbatim from BOQ.pushbutton/script.py in the v1.8.6 module split
(PROJECT_STRUCTURE.md section 9). Pure Python; the one Revit touchpoint
(the UnitUtils conversion path) is imported lazily behind a try/except
so this module stays importable outside Revit - without the host API
the deterministic imperial-to-metric constants below are the fallback.

The Revit-bound takeoff readers (read_metric_parameter,
get_element_quantities) remain in script.py by design.
"""
import re



FEET_TO_METERS = 0.3048

SQUARE_FEET_TO_SQUARE_METERS = 0.09290304

CUBIC_FEET_TO_CUBIC_METERS = 0.028316846592



def convert_quantity_value(internal_value, unit_kind):
    """
    Convert one raw internal-unit double into the matching metric
    value (meters / square meters / cubic meters).

    Conversion order:
    1. UnitUtils with UnitTypeId (Revit 2021+ API).
    2. UnitUtils with DisplayUnitType (Revit 2014-2020 API).
    3. Fixed foot-based conversion constants.
    """
    if internal_value is None:
        return ""

    # Host API - only present when running inside Revit. The guarded
    # import keeps this module importable in plain Python so the
    # harness can run the engine without Revit symbols (the fixed
    # conversion constants below are the documented fallback).
    try:
        from Autodesk.Revit import DB
    except Exception:
        DB = None

    type_id_map = None

    try:
        type_id_map = {
            "length": DB.UnitTypeId.Meter,
            "area": DB.UnitTypeId.SquareMeter,
            "volume": DB.UnitTypeId.CubicMeter
        }
    except:
        type_id_map = None

    if type_id_map is not None:

        try:
            converted = DB.UnitUtils.ConvertFromInternalUnits(
                internal_value,
                type_id_map[unit_kind]
            )

            return round(converted, 4)
        except:
            pass

    display_type_map = None

    try:
        display_type_map = {
            "length": DB.DisplayUnitType.DUT_METERS,
            "area": DB.DisplayUnitType.DUT_SQUARE_METERS,
            "volume": DB.DisplayUnitType.DUT_CUBIC_METERS
        }
    except:
        display_type_map = None

    if display_type_map is not None:

        try:
            converted = DB.UnitUtils.ConvertFromInternalUnits(
                internal_value,
                display_type_map[unit_kind]
            )

            return round(converted, 4)
        except:
            pass

    factor_map = {
        "length": FEET_TO_METERS,
        "area": SQUARE_FEET_TO_SQUARE_METERS,
        "volume": CUBIC_FEET_TO_CUBIC_METERS
    }

    try:
        converted = internal_value * factor_map.get(
            unit_kind,
            1.0
        )

        return round(converted, 4)
    except:
        return ""


def meters_to_millimeters(meter_value):
    """
    Convert a metre value (float or numeric string) to whole millimetres.

    Returns an int, or "" when the input is empty/non-numeric so the
    destination cell can stay blank instead of failing the export.
    """
    if meter_value in ("", None):
        return ""

    try:
        return int(round(float(meter_value) * 1000.0))
    except:
        return ""


def build_section_description(length_m, width_m):
    """
    Build the site-style cross-section description string from metric
    dimensions, mirroring entries like "150 X 3130" in the manual BOQ.

    Format is WIDTH X LENGTH in millimetres. Returns "" when either
    dimension is missing so the cell stays blank.
    """
    length_mm = meters_to_millimeters(length_m)
    width_mm = meters_to_millimeters(width_m)

    if length_mm == "" or width_mm == "":
        return ""

    return "{0} X {1}".format(width_mm, length_mm)


def resolve_element_dimensions(
        category_name,
        length_m="",
        width_m="",
        height_m="",
        depth_m="",
        thickness_m="",
        bbox_length_m="",
        bbox_width_m="",
        bbox_height_m=""):
    """
    P3/site-format: resolve one element's Length / Width / Height in
    metres from every available dimension source, deterministically.

    Source priority per category:
      Beam       : L = calculated length | bbox long side
                   W = Width | bbox short side
                   H = Depth | Height | bbox vertical side
      Column     : H = Height | bbox vertical side
                   section pair = (Width x Depth) | bbox pair, sorted so
                   W <= L exactly like the manual sheet lists them
      Slab /
      Foundation : H = Thickness | bbox vertical side
                   plan pair from bbox sides

    Never throws; missing dimensions come back as "" and the matching
    columns simply stay blank/pruned.
    """
    def first_available(*candidates):
        for candidate in candidates:
            if candidate not in ("", None):
                try:
                    return float(candidate)
                except:
                    return candidate
        return ""

    def sorted_pair(first_value, second_value):
        if first_value in ("", None) or second_value in ("", None):
            return ""
        try:
            low = min(float(first_value), float(second_value))
            high = max(float(first_value), float(second_value))
            return (low, high)
        except:
            return ""

    result = {"length": "", "width": "", "height": ""}

    if category_name == "Beam":

        result["length"] = first_available(length_m, bbox_length_m)
        result["width"] = first_available(width_m, bbox_width_m)
        result["height"] = first_available(
            depth_m, height_m, bbox_height_m
        )

    elif category_name == "Column":

        result["height"] = first_available(height_m, bbox_height_m)

        section_pair = sorted_pair(width_m, depth_m)

        if section_pair != "":
            result["width"] = round(section_pair[0], 4)
            result["length"] = round(section_pair[1], 4)
        else:
            bbox_pair = sorted_pair(bbox_width_m, bbox_length_m)

            if bbox_pair != "":
                result["width"] = round(bbox_pair[0], 4)
                result["length"] = round(bbox_pair[1], 4)

    else:

        # Slab / Foundation: vertical dimension is the thickness, the
        # plan pair comes from the bounding box footprint.
        result["height"] = first_available(thickness_m, bbox_height_m)

        plan_pair = sorted_pair(bbox_width_m, bbox_length_m)

        if plan_pair != "":
            result["width"] = round(plan_pair[0], 4)
            result["length"] = round(plan_pair[1], 4)

    for key in ("length", "width", "height"):
        try:
            result[key] = round(float(result[key]), 4)
        except:
            result[key] = ""

    return result


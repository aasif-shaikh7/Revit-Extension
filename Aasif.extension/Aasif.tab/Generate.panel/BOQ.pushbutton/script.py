# -*- coding: utf-8 -*-

"""
RCC BOQ Parameter Manager
=========================
Generates an RCC (Reinforced Cement Concrete) Bill of Quantities workbook
from the structural elements in the active Revit document.

Targets Revit 2025+ with pyRevit 6.10.0+ on the CP3123 (CPython 3.12.3) or
IP27 (IronPython 2.7) engine. The XLSX engine is dependency-free and is
covered by test_xlsx_writer.py.

__title__ = 'RCC BOQ'
__author__ = 'Aasif'
__version__ = '1.7.4'
__min_revit_ver__ = '2025'
__doc__ = 'RCC BOQ Parameter Manager - Beam / Column / Slab / Foundation BOQ export'
"""

from pyrevit import revit, forms
from Autodesk.Revit import DB

import os
import traceback
import re
import json
import time
import zipfile
from xml.sax.saxutils import escape as xml_escape
from System import Environment
from System.Windows.Forms import SaveFileDialog, DialogResult


# ============================================================
# PARAMETER ITEM
# ============================================================

class ParameterItem(object):

    def __init__(self, name):
        self.Name = name

    def __str__(self):
        return self.Name


# ============================================================
# GLOBAL DATA
# ============================================================

# Single source of truth for the runtime version. Keep in sync with the
# `__version__` value declared in the module docstring at the top of this
# script. Semantic versioning (MAJOR.MINOR.PATCH) - see PROJECT_STRUCTURE.md.
SCRIPT_VERSION = '1.7.4'

# v1.4.0 site-format export switch. When True the export produces the
# manual site-style workbook (title blocks, MM dimension columns,
# VOLUME + SHUTTERING, level-wise front Summary). When False the legacy
# classic workbook is produced (kept as a rollback path).
site_format_flag = True

selected_parameters = {
    "Beam": [],
    "Column": [],
    "Slab": [],
    "Foundation": []
}

# Export-scope flags. When export_only_flag is True, only elements that are
# currently selected in the Revit view are included in the element sheets.
export_only_flag = False
active_selection_ids = set()

# Quantity takeoff flag. When True, the export appends numeric quantity
# columns (volume, area, length) to the element sheets and builds the
# BOQ Summary sheet with live SUM formulas.
quantities_flag = True


def get_selection_ids():
    """
    Safely collect the integer ElementIds of the elements currently
    selected in Revit. Handles multiple pyRevit selection API shapes.
    """
    result = set()

    selection = None

    try:
        selection = revit.get_selection()
    except:
        selection = None

    if selection is None:
        try:
            selection = revit.selection
        except:
            selection = None

    if selection is None:
        return result

    candidate_set = None

    try:
        candidate_set = selection.elements
    except:
        candidate_set = None

    if candidate_set is None:
        try:
            candidate_set = selection
        except:
            candidate_set = None

    if candidate_set is None:
        return result

    try:
        for element in candidate_set:
            try:
                result.add(
                    element.Id.IntegerValue
                )
            except:
                pass
    except:
        pass

    return result


# ============================================================
# SETTINGS PERSISTENCE
# ============================================================

def get_settings_path():
    """Return the JSON settings path stored in the user profile folder."""
    home = ""

    try:
        home = os.path.expanduser("~")
    except:
        home = ""

    return os.path.join(
        home,
        ".rcc_boq_settings.json"
    )


def load_app_settings():
    """Load saved settings (selections, filters, last folder) or empty dict."""
    result = {}

    try:
        path = get_settings_path()

        if os.path.exists(path):

            with open(path, "r") as handle:

                loaded = json.load(handle)

                if isinstance(loaded, dict):
                    result = loaded

    except:
        pass

    return result


def save_app_settings(settings):
    """Persist the given settings dict to the JSON settings file."""
    try:
        path = get_settings_path()

        with open(path, "w") as handle:

            json.dump(
                settings,
                handle,
                indent=2
            )

    except:
        pass


# ============================================================
# PARAMETER METADATA ENGINE
# ============================================================

# Stores metadata in the same Beam / Column / Slab / Foundation
# structure used by the existing parameter-selection system.
parameter_metadata = {
    "Beam": [],
    "Column": [],
    "Slab": [],
    "Foundation": []
}


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


def safe_element_id(parameter):
    """
    Return the parameter ElementId as text where available.
    """
    try:
        parameter_id = parameter.Id

        if parameter_id is None:
            return "N/A"

        try:
            return str(parameter_id.IntegerValue)
        except:
            return safe_text(parameter_id, "N/A")

    except:
        return "N/A"


def safe_storage_type(parameter):
    """
    Return the Revit StorageType name safely.
    """
    try:
        storage_type = parameter.StorageType

        if storage_type is None:
            return "Unknown"

        return safe_text(storage_type, "Unknown")

    except:
        return "Unknown"


def safe_is_shared(parameter):
    try:
        return bool(parameter.IsShared)
    except:
        return False


def safe_is_read_only(parameter):
    try:
        return bool(parameter.IsReadOnly)
    except:
        return False


def safe_is_built_in(parameter):
    """
    Revit 2025 provides ParameterUtils.IsBuiltInParameter(ElementId).
    Fall back to False if the API call/property is unavailable.
    """
    try:
        parameter_id = parameter.Id

        if parameter_id is None:
            return False

        try:
            return bool(
                DB.ParameterUtils.IsBuiltInParameter(
                    parameter_id
                )
            )
        except:
            # Safe fallback for API environments where the utility
            # is not exposed as expected.
            return False

    except:
        return False


def safe_is_global(parameter):
    """
    True only when the parameter currently has an associated
    global parameter. Unsupported/unavailable cases return False.
    """
    try:
        global_parameter_id = (
            parameter.GetAssociatedGlobalParameter()
        )

        if global_parameter_id is None:
            return False

        try:
            return not global_parameter_id.Equals(
                DB.ElementId.InvalidElementId
            )
        except:
            try:
                return global_parameter_id.IntegerValue != -1
            except:
                return False

    except:
        return False


def safe_is_project_parameter(parameter_definition):
    """
    A project parameter is identified by a definition that exists
    in the document's ParameterBindings map.

    Shared parameters may also be project-bound, so Shared and
    Project Parameter are deliberately kept as separate metadata
    fields and may both be True.
    """
    try:
        if parameter_definition is None:
            return False

        bindings = doc.ParameterBindings

        if bindings is None:
            return False

        return bool(
            bindings.Contains(
                parameter_definition
            )
        )

    except:
        return False


def safe_definition_info(definition):
    """
    Capture Definition-level information available in Revit 2025.
    Missing/unsupported values are returned as Unknown or N/A.
    """
    info = {
        "Definition Type": "Unknown",
        "Definition Name": "Unknown",
        "Data Type": "Unknown",
        "Data Type TypeId": "N/A",
        "Group Type": "Unknown",
        "Group TypeId": "N/A"
    }

    if definition is None:
        return info

    try:
        info["Definition Type"] = safe_text(
            definition.GetType().__name__,
            "Unknown"
        )
    except:
        pass

    try:
        info["Definition Name"] = safe_text(
            definition.Name,
            "Unknown"
        )
    except:
        pass

    try:
        data_type = definition.GetDataType()

        if data_type is not None:
            info["Data Type"] = safe_text(
                data_type,
                "Unknown"
            )

            try:
                info["Data Type TypeId"] = safe_text(
                    data_type.TypeId,
                    "N/A"
                )
            except:
                pass

    except:
        pass

    try:
        group_type = definition.GetGroupTypeId()

        if group_type is not None:
            info["Group Type"] = safe_text(
                group_type,
                "Unknown"
            )

            try:
                info["Group TypeId"] = safe_text(
                    group_type.TypeId,
                    "N/A"
                )
            except:
                pass

    except:
        pass

    return info


def find_parameter_on_element(element, parameter_name):
    """
    Find the first matching parameter on an element by Definition.Name.
    Returns the Parameter object or None.
    """
    if element is None:
        return None

    try:
        for parameter in element.Parameters:

            try:
                definition = parameter.Definition

                if not definition:
                    continue

                name = definition.Name

                if name == parameter_name:
                    return parameter

            except:
                continue

    except:
        return None

    return None


def find_parameter_with_scope(element, parameter_name):
    """
    Resolve a selected parameter against an element.

    Existing UI parameter loading is based on element.Parameters,
    therefore Instance is preferred. Type is checked as a fallback
    so the metadata layer can report Type where it is actually found.
    """
    parameter = find_parameter_on_element(
        element,
        parameter_name
    )

    if parameter is not None:
        return (
            parameter,
            "Instance"
        )

    try:
        type_id = element.GetTypeId()

        if (
            type_id is not None
            and not type_id.Equals(
                DB.ElementId.InvalidElementId
            )
        ):

            type_element = doc.GetElement(
                type_id
            )

            parameter = find_parameter_on_element(
                type_element,
                parameter_name
            )

            if parameter is not None:
                return (
                    parameter,
                    "Type"
                )

    except:
        pass

    return (
        None,
        "Unknown"
    )


def build_parameter_metadata():
    """
    Build metadata only for the parameters currently selected
    in each tab.

    IMPORTANT:
    The current ListBox order is used as the source order, so this
    metadata layer respects the user's existing Add / Remove /
    Up / Down / Top / Bottom ordering without redesigning it.
    """
    metadata_result = {
        "Beam": [],
        "Column": [],
        "Slab": [],
        "Foundation": []
    }

    for element_name in control_map.keys():

        try:
            controls = control_map[element_name]

            selected = window.FindName(
                controls["selected"]
            )

            if not selected:
                continue

        except:
            continue

        # Respect the current order visible in Selected / Export.
        selected_items = []

        try:
            for item in selected.Items:
                selected_items.append(item)
        except:
            selected_items = []

        elements = category_elements.get(
            element_name,
            []
        )

        for item in selected_items:

            try:
                parameter_name = item.Name
            except:
                parameter_name = safe_text(
                    item,
                    "Unknown"
                )

            found_parameter = None
            parameter_scope = "Unknown"

            # Search actual project elements until the parameter
            # can be resolved. All metadata is derived from Revit,
            # not from hard-coded parameter names.
            for element in elements:

                try:
                    parameter, scope = (
                        find_parameter_with_scope(
                            element,
                            parameter_name
                        )
                    )

                    if parameter is not None:
                        found_parameter = parameter
                        parameter_scope = scope
                        break

                except:
                    continue

            if found_parameter is None:

                # Parameter was selected from the current available
                # list but could not be resolved at metadata time.
                # Keep the record instead of crashing.
                metadata_result[
                    element_name
                ].append(
                    {
                        "Parameter Name": parameter_name,
                        "Instance / Type": "Unknown",
                        "Shared": False,
                        "Project Parameter": False,
                        "Global Parameter": False,
                        "Built-in Parameter": False,
                        "Read Only": False,
                        "Storage Type": "Unknown",
                        "Parameter ID": "N/A",
                        "Parameter Definition": {
                            "Definition Type": "Unknown",
                            "Definition Name": "Unknown",
                            "Data Type": "Unknown",
                            "Data Type TypeId": "N/A",
                            "Group Type": "Unknown",
                            "Group TypeId": "N/A"
                        }
                    }
                )

                continue

            definition = None

            try:
                definition = found_parameter.Definition
            except:
                definition = None

            definition_info = (
                safe_definition_info(
                    definition
                )
            )

            metadata_result[
                element_name
            ].append(
                {
                    "Parameter Name": parameter_name,
                    "Instance / Type": parameter_scope,
                    "Shared": safe_is_shared(
                        found_parameter
                    ),
                    "Project Parameter": (
                        safe_is_project_parameter(
                            definition
                        )
                    ),
                    "Global Parameter": (
                        safe_is_global(
                            found_parameter
                        )
                    ),
                    "Built-in Parameter": (
                        safe_is_built_in(
                            found_parameter
                        )
                    ),
                    "Read Only": (
                        safe_is_read_only(
                            found_parameter
                        )
                    ),
                    "Storage Type": (
                        safe_storage_type(
                            found_parameter
                        )
                    ),
                    "Parameter ID": (
                        safe_element_id(
                            found_parameter
                        )
                    ),
                    "Parameter Definition": (
                        definition_info
                    )
                }
            )

    return metadata_result


def count_parameter_metadata(metadata):
    total = 0

    try:
        for element_name in metadata.keys():
            total += len(
                metadata[element_name]
            )
    except:
        pass

    return total


# ============================================================
# ELEMENT DATA ENGINE
# ============================================================

def safe_parameter_value(parameter):
    """
    Read the actual parameter value safely.
    Returns a string suitable for validation/reporting and future Excel export.
    """
    if parameter is None:
        return ""

    try:
        if not parameter.HasValue:
            return ""
    except:
        pass

    try:
        storage_type = parameter.StorageType
    except:
        storage_type = None

    try:
        if storage_type == DB.StorageType.String:
            value = parameter.AsString()
            return "" if value is None else str(value)

        if storage_type == DB.StorageType.Integer:
            try:
                value_string = parameter.AsValueString()
                if value_string not in (None, ""):
                    return str(value_string)
            except:
                pass
            return str(parameter.AsInteger())

        if storage_type == DB.StorageType.Double:
            try:
                value_string = parameter.AsValueString()
                if value_string not in (None, ""):
                    return str(value_string)
            except:
                pass
            try:
                return str(parameter.AsDouble())
            except:
                return ""

        if storage_type == DB.StorageType.ElementId:
            element_id = parameter.AsElementId()

            if element_id is None:
                return ""

            try:
                if element_id.Equals(DB.ElementId.InvalidElementId):
                    return ""
            except:
                try:
                    if element_id.IntegerValue == -1:
                        return ""
                except:
                    pass

            # Element-referencing parameters (Type, Level, Base/Top/Reference
            # Level, Cover Type, etc.) must export the referenced element's
            # NAME, not the raw numeric ElementId. Prefer Revit's own display
            # value, then the resolved element's Name, then the id as fallback.
            try:
                value_string = parameter.AsValueString()
                if value_string not in (None, ""):
                    return str(value_string)
            except:
                pass

            try:
                referenced = doc.GetElement(element_id)
                if referenced is not None:
                    name = None
                    try:
                        name = referenced.Name
                    except:
                        name = None
                    if name not in (None, ""):
                        return str(name)
            except:
                pass

            try:
                return str(element_id.IntegerValue)
            except:
                return safe_text(element_id, "")

    except:
        pass

    try:
        value_string = parameter.AsValueString()
        if value_string not in (None, ""):
            return str(value_string)
    except:
        pass

    try:
        value = parameter.AsString()
        if value is not None:
            return str(value)
    except:
        pass

    return ""


# ============================================================
# QUANTITY TAKEOFF ENGINE
# ============================================================

# Internal Revit units are fixed imperial bases, so metric conversion
# constants are deterministic even when the UnitUtils API is not
# available on older Revit versions.
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


def read_metric_parameter(element, name_hint):
    """
    Read a single metric (metres) double parameter by name from an element.

    This is a Parameter Quantity (a dimension the user set in the model),
    unlike the geometry-computed Volume / Area / Length. Searches the
    element's own parameters and its type parameters via LookupParameter,
    then converts the value to metres. Returns "" when absent so the
    column is pruned from the sheet.
    """
    def has_metric_value(param):
        try:
            if param is None:
                return False
            if not param.HasValue:
                return False
            return param.StorageType == DB.StorageType.Double
        except:
            return False

    param = None

    candidates = [element]

    try:
        candidates.append(element.Symbol)
    except:
        pass
    try:
        candidates.append(element.get_Type())
    except:
        pass

    for candidate in candidates:
        try:
            candidate_param = candidate.LookupParameter(name_hint)
        except:
            candidate_param = None
        if has_metric_value(candidate_param):
            param = candidate_param
            break

    if not has_metric_value(param):
        return ""

    try:
        return convert_quantity_value(param.AsDouble(), "length")
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


def compute_shuttering_area(
        category_name,
        length_m="",
        width_m="",
        height_m="",
        area_m2=""):
    """
    P3/site-format formwork (SHUTTERING) rules, deterministic and pure.

      Column     : perimeter of the four sides x height
                   = 2 * (L + W) * H
      Beam       : soffit width plus two side faces along the length
                   = (W + 2 * H) * L
      Slab       : soffit contact area = plan area
      Foundation : footing side faces = 2 * (L + W) * H

    Returns the area rounded to 2 decimals, or "" when the dimensions
    required by the rule are unavailable so the cell stays blank.
    """
    def to_float(value):
        try:
            return float(value)
        except:
            return None

    if category_name == "Slab":

        area_value = to_float(area_m2)

        if area_value is not None and area_value > 0:
            return round(area_value, 2)

        return ""

    length_value = to_float(length_m)
    width_value = to_float(width_m)
    height_value = to_float(height_m)

    if height_value is None:
        return ""

    if length_value is None or width_value is None:
        return ""

    if category_name == "Column":
        shuttering = 2.0 * (length_value + width_value) * height_value

    elif category_name == "Beam":
        shuttering = (width_value + 2.0 * height_value) * length_value

    elif category_name == "Foundation":
        shuttering = 2.0 * (length_value + width_value) * height_value

    else:
        return ""

    if shuttering <= 0:
        return ""

    return round(shuttering, 2)


def get_element_quantities(element, element_name=""):
    """
    Collect quantity takeoff values for one element, category-aware.

    Returns an ordered list of (column_label, value) tuples. The value is
    either a rounded float (metric) or an empty string when the quantity
    does not apply to the element.

    Source distinction (PRD Phase 1):
      - Calculated quantity : Volume, Area, Length (geometry / computed).
      - Parameter quantity : Height (Column), Thickness (Slab/Foundation)
        read from model parameters by name.
      - Count : one per element row (the TOTAL row sums to element count).
    """
    quantity_sources = [
        (
            "Volume (m3)",
            "volume",
            DB.BuiltInParameter.HOST_VOLUME_COMPUTED
        ),
        (
            "Area (m2)",
            "area",
            DB.BuiltInParameter.HOST_AREA_COMPUTED
        ),
        (
            "Length (m)",
            "length",
            DB.BuiltInParameter.INSTANCE_LENGTH_PARAM
        )
    ]

    results = []

    for column_label, unit_kind, built_in_parameter in quantity_sources:

        value = ""

        try:
            parameter = element.get_Parameter(
                built_in_parameter
            )
        except:
            parameter = None

        if parameter is not None:

            has_value = False

            try:
                has_value = bool(parameter.HasValue)
            except:
                has_value = True

            storage_is_double = False

            try:
                storage_is_double = (
                    parameter.StorageType
                    == DB.StorageType.Double
                )
            except:
                storage_is_double = False

            if has_value and storage_is_double:

                try:
                    value = convert_quantity_value(
                        parameter.AsDouble(),
                        unit_kind
                    )
                except:
                    value = ""

        results.append(
            (
                "Qty: " + column_label,
                value
            )
        )

    # P3/site-format: collect the raw dimension sources once, resolve them
    # into L/W/H metres, then derive the SHUTTERING formwork area. The
    # pure decision logic lives in resolve_element_dimensions /
    # compute_shuttering_area so the harness can test it without Revit.
    param_width = read_metric_parameter(element, "Width")
    param_depth = read_metric_parameter(element, "Depth")

    param_height = ""
    param_thickness = ""

    if element_name == "Column":

        param_height = read_metric_parameter(element, "Height")
        results.append(("Qty: Height (m)", param_height))

    elif element_name in ("Slab", "Foundation"):

        param_thickness = read_metric_parameter(element, "Thickness")
        results.append(("Qty: Thickness (m)", param_thickness))

    bbox_long = bbox_short = bbox_vertical = ""

    try:
        bbox = element.get_BoundingBox(None)

        if bbox is not None:
            delta_x = abs(bbox.Max.X - bbox.Min.X)
            delta_y = abs(bbox.Max.Y - bbox.Min.Y)

            bbox_long = convert_quantity_value(
                max(delta_x, delta_y),
                "length"
            )
            bbox_short = convert_quantity_value(
                min(delta_x, delta_y),
                "length"
            )
            bbox_vertical = convert_quantity_value(
                abs(bbox.Max.Z - bbox.Min.Z),
                "length"
            )
    except:
        bbox_long = bbox_short = bbox_vertical = ""

    calculated_length = ""
    calculated_area = ""

    for label, stored_value in results:

        if label == "Qty: Length (m)":
            calculated_length = stored_value
        elif label == "Qty: Area (m2)":
            calculated_area = stored_value

    element_dims = resolve_element_dimensions(
        element_name,
        length_m=calculated_length,
        width_m=param_width,
        height_m=param_height,
        depth_m=param_depth,
        thickness_m=param_thickness,
        bbox_length_m=bbox_long,
        bbox_width_m=bbox_short,
        bbox_height_m=bbox_vertical
    )

    shuttering_area = compute_shuttering_area(
        element_name,
        length_m=element_dims.get("length", ""),
        width_m=element_dims.get("width", ""),
        height_m=element_dims.get("height", ""),
        area_m2=calculated_area
    )

    results.extend(
        [
            ("Qty: Dim L (m)", element_dims.get("length", "")),
            ("Qty: Dim W (m)", element_dims.get("width", "")),
            ("Qty: Dim H (m)", element_dims.get("height", "")),
            ("Qty: Shuttering (m2)", shuttering_area)
        ]
    )

    # P1: every element row counts once; TOTAL row sums to element count
    results.append(
        (
            "Qty: Count",
            1
        )
    )

    return results


def get_element_level(element):
    """
    Return the element's associated level name for level-wise grouping.

    Tries the standard reference/schedule level built-in parameters first,
    then falls back to the element's own LevelId. Returns "" when no level
    can be resolved so the cell stays empty rather than failing the export.
    """
    level_parameter_ids = []

    try:
        level_parameter_ids.append(
            DB.BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM
        )
    except:
        pass
    try:
        level_parameter_ids.append(
            DB.BuiltInParameter.LEVEL_PARAM
        )
    except:
        pass
    try:
        level_parameter_ids.append(
            DB.BuiltInParameter.SCHEDULE_LEVEL_PARAM
        )
    except:
        pass

    for built_in_parameter in level_parameter_ids:
        try:
            parameter = element.get_Parameter(built_in_parameter)
        except:
            parameter = None

        if parameter is None:
            continue

        try:
            if not parameter.HasValue:
                continue
            if parameter.StorageType != DB.StorageType.ElementId:
                continue
            level_id = parameter.AsElementId()
        except:
            continue

        if level_id is None:
            continue

        try:
            if level_id.IntegerValue == -1:
                continue
            level_element = doc.GetElement(level_id)
            if level_element is not None and level_element.Name:
                return str(level_element.Name)
        except:
            continue

    try:
        level_element = doc.GetElement(element.LevelId)
        if level_element is not None and level_element.Name:
            return str(level_element.Name)
    except:
        pass

    return ""


# ============================================================
# P2: CONCRETE GRADE RESOLUTION
# ============================================================

# Recognized characteristic compressive-strength grades (IS 456 series).
# Kept on one line so the regression harness can lift the constant.
CONCRETE_GRADE_VALUES = ("M10", "M15", "M20", "M25", "M30", "M35", "M40", "M45", "M50", "M55", "M60", "M65", "M70", "M75", "M80")

# Parameter names commonly carrying the mix in Indian structural
# models. Matched by exact name (case-insensitive) on the element
# first, then its type, via the existing scope resolver.
CONCRETE_GRADE_PARAMETER_HINTS = (
    "Concrete Grade",
    "Grade of Concrete",
    "Concrete Grade (fck)",
    "Grade",
    "Concrete Type",
    "Concrete Mix",
    "Mix",
    "Mix Design"
)


def normalize_concrete_grade(text):
    """
    P2: normalize a free-text fragment to a canonical concrete grade
    token ("M25"). Accepts M25 / m-25 / M 25 spellings. Returns ""
    when no recognizable grade token is present, so callers can fall
    through to the next resolution source.
    """
    try:
        candidate = str(text or "")
    except:
        return ""

    match = re.search(
        r"\bM\s*-?\s*(\d{2})\b",
        candidate,
        re.IGNORECASE
    )

    if not match:
        return ""

    normalized = "M" + match.group(1)

    if normalized in CONCRETE_GRADE_VALUES:
        return normalized

    return ""


def find_grade_parameter(element, hint):
    """
    P2: case-insensitive grade parameter lookup.

    Project parameter names arrive in any casing ("GRADE OF CONCRETE",
    "Grade of Concrete", ...), while the regular UI-selected parameter
    path matches exact names. Checks the element first, then its type
    and symbol, mirroring find_parameter_with_scope's scope order.
    """
    if element is None:
        return None

    lowered = str(hint or "").lower()

    candidates = [element]

    try:
        if element.Symbol is not None:
            candidates.append(element.Symbol)
    except:
        pass

    try:
        type_id = element.GetTypeId()

        if (
            type_id is not None
            and not type_id.Equals(DB.ElementId.InvalidElementId)
        ):
            type_element = doc.GetElement(type_id)

            if type_element is not None:
                candidates.append(type_element)
    except:
        pass

    for candidate in candidates:

        try:
            for parameter in candidate.Parameters:

                try:
                    definition = parameter.Definition

                    if not definition:
                        continue

                    if str(definition.Name).lower() == lowered:
                        return parameter

                except:
                    continue

        except:
            pass

    return None


def resolve_concrete_grade(element):
    """
    P2: resolve one element's concrete grade for grade-wise grouping.

    Tries, in order:
      1. A recognized grade parameter (see CONCRETE_GRADE_PARAMETER_HINTS)
         on the element or its type, read with the existing scope helpers.
      2. The Material parameter's target material name (Revit material
         names often carry the mix, e.g. "Concrete - M25").
      3. A grade token inside the element's identity text
         (element name | type | family | common labels).

    Returns the canonical token ("M25") or "(No Grade)" so every row
    still groups deterministically. Never raises.
    """
    for hint in CONCRETE_GRADE_PARAMETER_HINTS:

        parameter = find_grade_parameter(element, hint)

        if parameter is None:
            continue

        grade = normalize_concrete_grade(
            safe_parameter_value(parameter)
        )

        if grade:
            return grade

    try:
        material_parameter = element.LookupParameter("Material")

        material_id = material_parameter.AsElementId()

        if material_id is not None:
            material = doc.GetElement(material_id)

            if material is not None:
                grade = normalize_concrete_grade(material.Name)

                if grade:
                    return grade
    except:
        pass

    try:
        grade = normalize_concrete_grade(
            get_element_identity_text(element)
        )

        if grade:
            return grade
    except:
        pass

    return "(No Grade)"


def build_element_data():
    """
    Read actual values from the parameters currently selected in the UI.
    The current Selected / Export order is preserved.
    """
    data_result = {
        "Beam": [],
        "Column": [],
        "Slab": [],
        "Foundation": []
    }

    missing_values = 0
    total_rows = 0

    for element_name in control_map.keys():

        try:
            controls = control_map[element_name]
            selected = window.FindName(
                controls["selected"]
            )

            if not selected:
                continue

        except:
            continue

        selected_names = []

        try:
            for item in selected.Items:
                try:
                    selected_names.append(item.Name)
                except:
                    selected_names.append(
                        safe_text(item, "Unknown")
                    )
        except:
            selected_names = []

        elements = category_elements.get(
            element_name,
            []
        )

        # When "Export selected only" is active, restrict to the elements
        # currently selected in the Revit view.
        if export_only_flag and active_selection_ids:

            filtered = []

            for element in elements:

                try:
                    element_id = element.Id.IntegerValue
                except:
                    element_id = None

                if element_id is None:
                    continue

                if element_id in active_selection_ids:
                    filtered.append(element)

            elements = filtered

        for element in elements:

            try:
                row = {
                    "Element ID": str(
                        element.Id.IntegerValue
                    )
                }
            except:
                row = {
                    "Element ID": "N/A"
                }

            # P2: level grouping column, written directly after Element ID so
            # it sits in a deterministic column (B) on every element sheet.
            row["Level"] = get_element_level(element)

            # P2: concrete grade grouping column, written right after Level
            # so it sits in a deterministic column (C) on every element
            # sheet and feeds the BOQ by Grade sheet.
            row["Grade"] = resolve_concrete_grade(element)

            for parameter_name in selected_names:

                parameter = None

                try:
                    parameter, parameter_scope = (
                        find_parameter_with_scope(
                            element,
                            parameter_name
                        )
                    )
                except:
                    parameter = None

                value = safe_parameter_value(
                    parameter
                )

                if value == "":
                    missing_values += 1

                row[parameter_name] = value

            # Quantity takeoff columns (numeric, metric) are appended
            # after the selected parameters so they never interfere
            # with the parameter completeness audit.
            if quantities_flag:

                for column_label, quantity_value in (
                    get_element_quantities(element, element_name)
                ):
                    row[column_label] = quantity_value

            data_result[
                element_name
            ].append(row)

            total_rows += 1

    return (
        data_result,
        total_rows,
        missing_values
    )


def get_sample_values(data_result, max_rows=3):
    """
    Create a compact test summary instead of showing the entire dataset.
    """
    lines = []

    for element_name in (
        "Beam",
        "Column",
        "Slab",
        "Foundation"
    ):

        rows = data_result.get(
            element_name,
            []
        )

        if not rows:
            continue

        lines.append(
            "{}: {} row(s)".format(
                element_name,
                len(rows)
            )
        )

        for index, row in enumerate(
            rows[:max_rows]
        ):

            parts = []

            for key in row.keys():

                if key == "Element ID":
                    continue

                try:
                    parts.append(
                        "{}={}".format(
                            key,
                            row[key]
                        )
                    )
                except:
                    pass

            lines.append(
                "  Row {} | ID {} | {}".format(
                    index + 1,
                    row.get(
                        "Element ID",
                        "N/A"
                    ),
                    " | ".join(parts)
                )
            )

    if not lines:
        lines.append(
            "No element data available."
        )

    return "\n".join(lines)



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

    for category_name in ("Beam", "Column", "Slab", "Foundation"):

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
    """Natural sort: Level 2 sorts after Level 1."""

    try:
        level_text = str(level_name)
    except:
        level_text = ""

    match = re.search(r"(\d+)", level_text)

    number_part = int(match.group(1)) if match else 10 ** 9

    return (number_part, level_text.lower())


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


def build_site_detail_sheet(category_name, rows, project_name):
    """
    Site detail sheet, selection-only columns.

    Shows exactly the parameters the user ticked in the UI - nothing
    else. Every selected parameter gets its OWN column after SNO; the
    automatic SIZE (MM) / VOLUME / SHUTTERING / LEVEL columns and the
    SUM totals row are gone, so the sheet mirrors the checkbox
    selection cleanly.

    Layout: rows 1-3 merged title block, row 4 spacer, rows 5/6
    two-tier band (each header vertically merged), row 7+ one row per
    element with SNO followed by the selected values in UI order.

    meta carries the dynamic widths (per parameter count); it no
    longer exposes VOLUME/SHUTTERING column letters or a LEVEL feed,
    so the front Summary stays a simple element-count cover.
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

    total_cols = 1 + len(param_names)

    def merge_vertical(label):
        return ("MERGE_V", label)

    band_one = [merge_vertical("SNO")]

    for param_name in param_names:
        band_one.append(merge_vertical(str(param_name).upper()))

    band_two = ["" for _band_cell in param_names]

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

        table.append(out_values)
        item_number += 1

    meta = {
        "columns": {},
        "level_col": "",
        "total_row": len(table),
        "data_start": SITE_DETAIL_DATA_START_ROW,
        "data_end": len(table),
        "elements": len(data_rows),
        "widths": [7] + [18 for _name in param_names],
        "param_columns": list(param_names)
    }

    return (table, meta)


def build_site_summary_sheet(data_result, site_detail_meta, project_name):
    """
    Build the front Summary in the site format.

    Layout (1-based Excel rows):
      Row 1 : project                     (writer merges across width)
      Row 2 : RCC - CONCRETE FINISHING BOQ
      Row 3 : ITEM-WISE SUMMARY - CONCRETE AND SHUTTERING
      Row 4 : blank spacer row
      Row 5 : LEVEL | ITEM | <category groups> | TOTAL m3 | TOTAL sqm
              (band one; category names span their two columns)
      Row 6 :                  | VOL (m3) | SHUT (sqm) | ...
              (band two; LEVEL and ITEM are vertical merges)

    Every exported category contributes one VOL / SHUT column pair.
    Data rows hold live SUMIF formulas against each detail sheet's
    hidden LEVEL column (H), restricted to that sheet's real data
    rows, so Excel reconciles every figure against the model on load.
    The trailing TOTAL pair sums the category columns horizontally.

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

    out_rows = [
        [str(project_name or "")],
        ["RCC - CONCRETE FINISHING BOQ"],
        ["ITEM-WISE SUMMARY - CONCRETE AND SHUTTERING"],
        [],
        [
            ("MERGE_V", "SNO"),
            ("MERGE_V", "CATEGORY"),
            "ELEMENTS",
            "VOLUME (m3)",
            "SHUTTERING (m2)"
        ],
        ["", "", "", "", ""],
    ]

    first_data_row = len(out_rows) + 1

    item_number = 1

    for category_name in present_categories:

        category_meta = site_detail_meta.get(category_name, {})

        out_rows.append(
            [
                item_number,
                header_label_map[category_name],
                category_meta.get("elements", 0),
                aggregate_metric(category_name, "Qty: Volume (m3)"),
                aggregate_metric(category_name, "Qty: Shuttering (m2)")
            ]
        )

        item_number += 1

    total_row_number = len(out_rows) + 1

    vol_col = 4
    shut_col = 5

    vol_letter = xlsx_column_name(vol_col)
    shut_letter = xlsx_column_name(shut_col)

    out_rows.append(
        [
            "TOTAL",
            "",
            "",
            (
                "FORMULA",
                "SUM({0}{1}:{0}{2})".format(
                    vol_letter, first_data_row, total_row_number - 1)
            ),
            (
                "FORMULA",
                "SUM({0}{1}:{0}{2})".format(
                    shut_letter, first_data_row, total_row_number - 1)
            )
        ]
    )

    meta = {
        "present_categories": present_categories,
        "columns": {
            "Volume (m3)": vol_letter,
            "Shuttering (m2)": shut_letter
        },
        "total_columns": 5,
        "bands": (5, 6),
        "grid_start": first_data_row,
        "levels": []
    }

    return (out_rows, meta)


SITE_DETAIL_COLUMN_WIDTHS = [6, 30, 8, 8, 8, 12, 14, 14]


def write_site_xlsx(file_path, data_result, project_name="",
                    tool_version="", generated_stamp=""):
    """
    Write the v1.4.0 site-format workbook.

    Sheet plan mirrors the manual site BOQ:
      Summary                - level-wise CONCRETE / SHUTTERING grid
      Beam / Column / Slab /
      Foundation             - one detail sheet per populated category
                               with title blocks and one column per
                               user-selected parameter (no automatic
                               SIZE / VOLUME / SHUTTERING / LEVEL
                               columns and no SUM totals row).

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

        rows = data_result.get(category_name) or []

        if not rows:
            continue

        table, meta = build_site_detail_sheet(
            category_name,
            rows,
            project_name
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
        project_name
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

    summary_widths = [7, 24, 10, 14, 17]  # SNO|CATEGORY|ELEMENTS|VOL|SHUT


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


def choose_excel_output_path():
    """Show a standard Windows Save dialog for the XLSX output path."""
    desktop = Environment.GetFolderPath(
        Environment.SpecialFolder.DesktopDirectory
    )

    # Remember the previously used folder across sessions.
    saved = load_app_settings()
    last_dir = saved.get("last_dir", "")

    dialog = SaveFileDialog()
    dialog.Title = "Save RCC BOQ Excel Report"
    dialog.Filter = "Excel Workbook (*.xlsx)|*.xlsx"
    dialog.DefaultExt = "xlsx"
    dialog.AddExtension = True

    # Professional naming convention:
    # YYYYMMDD-<Project>-CONCRETE_FINISHING_BOQ.xlsx (user can still edit it).
    try:
        dialog.FileName = build_default_output_name(doc.Title)
    except:
        dialog.FileName = "RCC_BOQ_Report.xlsx"

    if last_dir and os.path.exists(last_dir):
        dialog.InitialDirectory = last_dir
    elif desktop:
        dialog.InitialDirectory = desktop

    result = dialog.ShowDialog()

    if result != DialogResult.OK:
        return None

    # Persist the chosen folder for the next export.
    try:
        saved["last_dir"] = os.path.dirname(
            dialog.FileName
        )
        save_app_settings(saved)
    except:
        pass

    return dialog.FileName


# ============================================================
# DOCUMENT
# ============================================================

doc = revit.doc


# ============================================================
# CATEGORY DEFINITIONS
# ============================================================

CATEGORY_INFO = {

    "Beam": DB.BuiltInCategory.OST_StructuralFraming,

    "Column": DB.BuiltInCategory.OST_StructuralColumns,

    "Slab": DB.BuiltInCategory.OST_Floors,

    "Foundation": DB.BuiltInCategory.OST_StructuralFoundation
}


# ============================================================
# COLLECT ELEMENTS
# ============================================================

def get_elements(category):

    try:

        collector = DB.FilteredElementCollector(doc)

        elements = (
            collector
            .OfCategory(category)
            .WhereElementIsNotElementType()
            .ToElements()
        )

        return list(elements)

    except:

        return []


# ============================================================
# GET ALL PARAMETERS
# ============================================================

def get_parameters(elements):

    parameter_names = set()

    for element in elements:

        try:

            parameters = element.Parameters

            for parameter in parameters:

                try:

                    definition = parameter.Definition

                    if definition:

                        name = definition.Name

                        if name:

                            parameter_names.add(
                                name
                            )

                except:

                    continue

        except:

            continue

    result = []

    for name in parameter_names:

        result.append(
            ParameterItem(name)
        )

    result.sort(
        key=lambda x: x.Name.lower()
    )

    return result


# ============================================================
# RCC ELEMENT CLASSIFICATION / FILTER ENGINE
# ============================================================

def normalize_label(value):
    try:
        text = str(value or '').lower()
    except:
        text = ''

    # Keep codes such as S1 / GS / CF intact while normalizing
    # spaces, underscores, hyphens, and punctuation.
    try:
        text = re.sub(r'[_\-]+', ' ', text)
        text = re.sub(r'[^a-z0-9]+', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
    except:
        pass

    return text


def get_element_identity_text(element):
    """
    Build a safe search string from the actual Revit element/type/family
    information. No project-specific parameter is required.
    """
    parts = []

    def add_part(value):
        try:
            if value is not None and str(value).strip() != '':
                parts.append(str(value))
        except:
            pass

    try:
        add_part(element.Name)
    except:
        pass

    type_element = None
    try:
        type_id = element.GetTypeId()
        if type_id is not None and not type_id.Equals(DB.ElementId.InvalidElementId):
            type_element = doc.GetElement(type_id)
    except:
        type_element = None

    if type_element is not None:
        try:
            add_part(type_element.Name)
        except:
            pass
        try:
            add_part(type_element.FamilyName)
        except:
            pass

    try:
        symbol = element.Symbol
        if symbol is not None:
            try:
                add_part(symbol.Name)
            except:
                pass
            try:
                add_part(symbol.FamilyName)
            except:
                pass
    except:
        pass

    # Include commonly useful model labels when available.
    common_parameter_names = (
        'Family Name', 'Family', 'Type Name', 'Family and Type',
        'Type', 'Mark', 'ID_UNMT', 'ITEM DES.', 'CODE_UNIMONT'
    )

    for parameter_name in common_parameter_names:
        try:
            parameter = find_parameter_on_element(element, parameter_name)
            if parameter is not None:
                value = safe_parameter_value(parameter)
                if value:
                    add_part(value)
        except:
            continue

    return normalize_label(' | '.join(parts))


def code_token_match(text, prefixes):
    try:
        token_text = text.replace('|', ' ')
        pattern = r'(?<![a-z0-9])(?:' + '|'.join(prefixes) + r')[0-9]*(?![a-z0-9])'
        return re.search(pattern, token_text) is not None
    except:
        return False


def classify_slab_subtype(element):
    """Classify logical slab subtypes regardless of Floor/Foundation storage."""
    text = get_element_identity_text(element)

    # Explicit logical slab names/codes take priority.
    if 'grade slab' in text or 'gradeslab' in text or code_token_match(text, ('gs',)):
        return 'Grade Slab'

    if 'fold slab' in text or 'foldslab' in text:
        return 'Fold Slab'

    if 'slab' in text or code_token_match(text, ('s',)):
        return 'Slab'

    return 'Other'


def is_pcc_element(element):
    """
    True when an element's identity carries a PCC token (plain cement
    concrete). PCC beds under Footings / Combined Footings / rafts are
    commonly modeled as floors in the model; they belong to the
    Foundation tab, not the Slab tab.
    """
    try:
        text = get_element_identity_text(element)
    except:
        return False

    return re.search(r'\bpcc\b', text) is not None


def classify_foundation_subtype(element):
    """Classify logical foundation subtypes from actual names/codes."""
    text = get_element_identity_text(element)

    # PCC (plain cement concrete) beds under Footings / Combined
    # Footings / rafts belong to Foundation as their own subtype, even
    # when modeled as floors or when the rest of the name carries slab
    # wording or a footing mark/code ("PCC F1", "PCC-CF2", "PCC Slab").
    if re.search(r'\bpcc\b', text):
        return 'PCC'

    # Explicit slab-like foundation elements stay in the Slab tab.
    if classify_slab_subtype(element) in ('Slab', 'Fold Slab', 'Grade Slab'):
        return 'Slab-like'

    if ('combined footing' in text or 'combine footing' in text or
            code_token_match(text, ('cf',))):
        return 'Combined Footing'

    if 'footing' in text or code_token_match(text, ('f',)):
        return 'Footing'

    if ('combined raft' in text or 'combine raft' in text):
        return 'Combined Raft'

    if 'raft' in text:
        return 'Raft'

    return 'Other'


def classify_element_group(element, logical_tab):
    if logical_tab == 'Slab':
        return classify_slab_subtype(element)
    if logical_tab == 'Foundation':
        return classify_foundation_subtype(element)
    return 'All'


SLAB_FILTER_OPTIONS = (
    'All Slab Types',
    'Slab',
    'Fold Slab',
    'Grade Slab',
    'Other'
)

FOUNDATION_FILTER_OPTIONS = (
    'All Foundation Types',
    'Footing',
    'Combined Footing',
    'PCC',
    'Raft',
    'Combined Raft',
    'Other'
)


def filter_elements(elements, logical_tab, filter_name):
    if logical_tab == 'Slab':
        if filter_name == 'All Slab Types':
            return [
                e for e in elements
                if classify_slab_subtype(e) in ('Slab', 'Fold Slab', 'Grade Slab', 'Other')
            ]

        return [
            e for e in elements
            if classify_slab_subtype(e) == filter_name
        ]

    if logical_tab == 'Foundation':
        if filter_name == 'All Foundation Types':
            return [
                e for e in elements
                if classify_foundation_subtype(e) != 'Slab-like'
            ]

        return [
            e for e in elements
            if classify_foundation_subtype(e) == filter_name
        ]

    return list(elements)


# Raw source collections are kept permanently so a filter can be changed
# without re-querying or destroying the original model collections.
all_beam_elements = get_elements(CATEGORY_INFO['Beam'])
all_column_elements = get_elements(CATEGORY_INFO['Column'])
all_floor_elements = get_elements(CATEGORY_INFO['Slab'])
all_foundation_elements = get_elements(CATEGORY_INFO['Foundation'])

category_elements = {
    'Beam': list(all_beam_elements),
    'Column': list(all_column_elements),
    'Slab': [
        # PCC beds are floors in the model but belong to Foundation.
        e for e in all_floor_elements
        if not is_pcc_element(e)
    ] + [
        e for e in all_foundation_elements
        if classify_slab_subtype(e) in ('Slab', 'Fold Slab', 'Grade Slab')
    ],
    'Foundation': [
        e for e in all_foundation_elements
        if classify_foundation_subtype(e) != 'Slab-like'
    ] + [
        # PCC beds modeled as floors join the Foundation tab too.
        e for e in all_floor_elements
        if is_pcc_element(e)
    ]
}

category_parameters = {}

for element_name in category_elements.keys():
    category_parameters[element_name] = get_parameters(
        category_elements[element_name]
    )

active_filters = {
    'Slab': 'All Slab Types',
    'Foundation': 'All Foundation Types'
}



# ============================================================
# LOAD XAML
# ============================================================

try:

    xaml_path = os.path.join(
        os.path.dirname(__file__),
        "ui.xaml"
    )

    if not os.path.exists(xaml_path):

        forms.alert(
            "ui.xaml nahi mila.\n\n{}".format(
                xaml_path
            ),
            title="RCC BOQ Error"
        )

    else:

        window = forms.WPFWindow(
            xaml_path
        )


        # ====================================================
        # BRAND THEME + THEME SELECTOR (v1.5.0)
        # Merge the shared Light/Dark brand dictionaries from
        # lib/Resources onto this dialog. The user can pick
        # Auto (follow Revit's theme), Light or Dark from the
        # footer ThemeSelector; the choice is saved to the
        # existing .rcc_boq_settings.json immediately and
        # restored on the next run (default: Auto).
        # Cosmetic only - if anything here fails (lib missing,
        # dictionary load error), the dialog still opens with
        # its default WPF look.
        # ====================================================

        # Mutable state holder (Python 2.7 has no nonlocal) so
        # the watcher handler can be swapped from any closure.
        _theme_watch_state = {"handler": None}

        def _start_theme_watching():
            """Subscribe to Revit's own Light/Dark flips (Auto mode)."""
            try:
                _theme_watch_state["handler"] = (
                    theme_manager.watch_theme_changes(window)
                )
            except:
                _theme_watch_state["handler"] = None

        def _stop_theme_watching():
            """Unsubscribe the Revit theme watcher (manual mode)."""
            try:
                theme_manager.stop_watching(
                    _theme_watch_state.get("handler")
                )
            except:
                pass
            _theme_watch_state["handler"] = None

        def _apply_search_foregrounds():
            """
            v1.7.4: pin the four search boxes' text/caret to the theme's
            primary brush via SetResourceReference.

            The XAML attribute `{DynamicResource TextPrimaryBrush}` on the
            TextBox style/template does not reliably reach the internal text
            view after the brand dictionaries are merged at runtime under
            pyRevit / IronPython. The status bar uses the same
            SetResourceReference pattern and is confirmed visible, so this
            helper applies it directly on each search box after the theme is
            in place.
            """
            try:
                from System.Windows.Controls import TextBox as _TextBox
            except:
                return

            for _sbox_name in (
                "BeamSearch",
                "ColumnSearch",
                "SlabSearch",
                "FoundationSearch"
            ):
                try:
                    _sbox = window.FindName(_sbox_name)
                except:
                    _sbox = None

                if _sbox is None:
                    continue

                try:
                    _sbox.SetResourceReference(
                        _TextBox.ForegroundProperty,
                        "TextPrimaryBrush"
                    )
                except:
                    pass

                try:
                    _sbox.SetResourceReference(
                        _TextBox.CaretBrushProperty,
                        "TextPrimaryBrush"
                    )
                except:
                    pass

        def _apply_theme_choice(choice):
            """
            Apply one canonical theme choice: 'Auto', 'Light' or
            'Dark'. Auto re-follows Revit; Light/Dark force the
            dictionaries and pause the watcher so Revit flips no
            longer override the manual choice.
            """
            try:
                if choice == "Light":
                    _stop_theme_watching()
                    theme_manager.apply_theme(window, "Light")
                elif choice == "Dark":
                    _stop_theme_watching()
                    theme_manager.apply_theme(window, "Dark")
                else:
                    theme_manager.apply_theme(window)
                    _start_theme_watching()
            except:
                pass

            # Keep the search-box text readable after every theme swap.
            _apply_search_foregrounds()

        try:

            import theme_manager

            saved_theme_choice = "Auto"

            try:
                saved_theme_choice = str(
                    load_app_settings().get("theme", "Auto") or "Auto"
                )
            except:
                saved_theme_choice = "Auto"

            if saved_theme_choice not in ("Auto", "Light", "Dark"):
                saved_theme_choice = "Auto"

            _apply_theme_choice(saved_theme_choice)

            # Ensure the search-box text is readable even on the very
            # first paint (the theme block above already ran the helper
            # through _apply_theme_choice; this is a harmless safety net).
            try:
                _apply_search_foregrounds()
            except:
                pass

            def _on_boq_window_closed(sender, args):

                _stop_theme_watching()

            window.Closed += (
                _on_boq_window_closed
            )

        except Exception:

            # Theme is cosmetic - fall back to the stock look quietly.
            # The selector below still works (its apply calls degrade
            # to no-ops when theme_manager is unavailable).
            pass

        # ====================================================
        # THEME SELECTOR (v1.5.0)
        # Footer combo: Auto (Revit) / Light / Dark. Saves the
        # canonical choice to the existing settings file on
        # every change so it survives restarts.
        # ====================================================

        theme_selector = window.FindName("ThemeSelector")

        if theme_selector:

            try:
                theme_selector.Items.Add("Auto (Revit)")
                theme_selector.Items.Add("Light")
                theme_selector.Items.Add("Dark")
            except:
                pass

            def on_theme_selection_changed(sender, args):

                try:
                    raw_choice = str(sender.SelectedItem or "")
                except:
                    return

                if raw_choice == "Light":
                    theme_choice = "Light"
                elif raw_choice == "Dark":
                    theme_choice = "Dark"
                elif raw_choice == "Auto (Revit)":
                    theme_choice = "Auto"
                else:
                    return

                _apply_theme_choice(theme_choice)

                # Persist immediately through the existing settings
                # system - never wait for an export to save it.
                try:
                    theme_settings = load_app_settings()
                    theme_settings["theme"] = theme_choice
                    save_app_settings(theme_settings)
                except:
                    pass

            theme_selector.SelectionChanged += (
                on_theme_selection_changed
            )

            # Reflect the saved choice. Setting SelectedIndex fires
            # SelectionChanged once; the handler re-applies the same
            # theme and re-saves the same value, which is harmless.
            try:
                active_theme = "Auto"

                try:
                    active_theme = str(
                        load_app_settings().get("theme", "Auto") or "Auto"
                    )
                except:
                    active_theme = "Auto"

                if active_theme not in ("Auto", "Light", "Dark"):
                    active_theme = "Auto"

                if active_theme == "Light":
                    theme_selector.SelectedIndex = 1
                elif active_theme == "Dark":
                    theme_selector.SelectedIndex = 2
                else:
                    theme_selector.SelectedIndex = 0
            except:
                pass


        # ====================================================
        # PROJECT NAME
        # ====================================================

        project_text = window.FindName(
            "ProjectName"
        )

        if project_text:

            try:

                project_name = (
                    doc.Title
                )

                project_text.Text = (
                    "Project: {}".format(
                        project_name
                    )
                )

            except:

                project_text.Text = (
                    "Project: Revit Project"
                )


        # ====================================================
        # STATUS
        # ====================================================

        status = window.FindName(
            "StatusText"
        )

        def set_status(message, kind="normal"):
            """
            Write a status message and tint it with the matching
            semantic brand brush:

                normal   -> primary text colour
                info     -> InfoBrush
                success  -> SuccessBrush
                warning  -> WarningBrush
                error    -> ErrorBrush

            SetResourceReference keeps a DynamicResource link, so the
            colour keeps following Light/Dark theme swaps while the
            dialog stays open. Cosmetic only - any failure leaves the
            plain brand text.
            """
            if not status:

                return

            try:
                status.Text = message
            except:
                pass

            brush_key = {
                "info": "InfoBrush",
                "success": "SuccessBrush",
                "warning": "WarningBrush",
                "error": "ErrorBrush"
            }.get(kind, "TextPrimaryBrush")

            try:
                from System.Windows.Controls import TextBlock

                status.SetResourceReference(
                    TextBlock.ForegroundProperty,
                    brush_key
                )
            except:
                pass

        if status:

            set_status(
                "Loading Revit parameters..."
            )


        # ====================================================
        # TAB CONTROL NAMES
        # ====================================================

        control_map = {

            "Beam": {
                "available": "BeamAvailable",
                "search": "BeamSearch",
                "selected": "BeamSelected",
                "add": "BeamAdd",
                "remove": "BeamRemove",
                "up": "BeamUp",
                "down": "BeamDown",
                "top": "BeamTop",
                "bottom": "BeamBottom"
            },

            "Column": {
                "available": "ColumnAvailable",
                "search": "ColumnSearch",
                "selected": "ColumnSelected",
                "add": "ColumnAdd",
                "remove": "ColumnRemove",
                "up": "ColumnUp",
                "down": "ColumnDown",
                "top": "ColumnTop",
                "bottom": "ColumnBottom"
            },

            "Slab": {
                "available": "SlabAvailable",
                "search": "SlabSearch",
                "selected": "SlabSelected",
                "add": "SlabAdd",
                "remove": "SlabRemove",
                "up": "SlabUp",
                "down": "SlabDown",
                "top": "SlabTop",
                "bottom": "SlabBottom"
            },

            "Foundation": {
                "available": "FoundationAvailable",
                "search": "FoundationSearch",
                "selected": "FoundationSelected",
                "add": "FoundationAdd",
                "remove": "FoundationRemove",
                "up": "FoundationUp",
                "down": "FoundationDown",
                "top": "FoundationTop",
                "bottom": "FoundationBottom"
            }
        }


        # ====================================================
        # RCC SUBTYPE FILTERS
        # ====================================================

        def filter_available_by_search(element_name):
            """
            Rebuild the Available list for a category, applying the
            current search query on top of the master parameter pool.
            Also respects the active subtype filter because the pool
            itself is already narrowed down by refresh_category_view.
            """
            try:
                controls = control_map[element_name]
                available = window.FindName(
                    controls["available"]
                )

                if not available:
                    return

                query = ""
                search_box = window.FindName(
                    controls["search"]
                )

                if search_box is not None:
                    try:
                        query = (
                            str(search_box.Text or "")
                            .strip()
                            .lower()
                        )
                    except:
                        query = ""

                pool = category_parameters.get(
                    element_name,
                    []
                )

                # v1.7.1: parameters already in the Selected list are
                # hidden from Available so the list only offers the
                # remaining parameters.
                selected_names = set()

                selected_box = window.FindName(
                    controls["selected"]
                )

                if selected_box is not None:
                    try:
                        for item in selected_box.Items:
                            try:
                                selected_names.add(item.Name)
                            except:
                                pass
                    except:
                        pass

                available.Items.Clear()

                for parameter in pool:

                    try:
                        name = parameter.Name
                    except:
                        name = safe_text(
                            parameter,
                            ""
                        )

                    if name is None:
                        name = ""

                    if name in selected_names:
                        continue

                    if (
                        not query
                        or query in name.lower()
                    ):
                        available.Items.Add(parameter)

            except:
                pass


        def refresh_category_view(element_name):

            if element_name == 'Slab':
                selected_filter = active_filters.get(
                    'Slab',
                    'All Slab Types'
                )
                # PCC beds are floors in the model but belong to
                # Foundation, so they are excluded here.
                base_elements = [
                    e for e in all_floor_elements
                    if not is_pcc_element(e)
                ]

                # Slab/Grade/Fold Slab can also be modeled as Structural
                # Foundation, so those logical slab elements are added here.
                base_elements.extend([
                    e for e in all_foundation_elements
                    if classify_slab_subtype(e) in (
                        'Slab', 'Fold Slab', 'Grade Slab'
                    )
                ])

                category_elements['Slab'] = filter_elements(
                    base_elements,
                    'Slab',
                    selected_filter
                )

            elif element_name == 'Foundation':
                selected_filter = active_filters.get(
                    'Foundation',
                    'All Foundation Types'
                )

                base_elements = list(all_foundation_elements)

                # PCC beds modeled as floors join the Foundation tab too.
                base_elements.extend([
                    e for e in all_floor_elements
                    if is_pcc_element(e)
                ])

                category_elements['Foundation'] = filter_elements(
                    base_elements,
                    'Foundation',
                    selected_filter
                )

            try:
                category_parameters[element_name] = get_parameters(
                    category_elements.get(element_name, [])
                )

                filter_available_by_search(element_name)
            except:
                pass

            try:
                if status:
                    set_status(
                        '{} filter: {} | Elements: {}'.format(
                            element_name,
                            active_filters.get(element_name, 'All'),
                            len(category_elements.get(element_name, []))
                        ),
                        "info"
                    )
            except:
                pass


        def setup_rcc_filters():

            slab_filter = window.FindName('SlabFilter')
            foundation_filter = window.FindName('FoundationFilter')

            if slab_filter:
                slab_filter.Items.Clear()
                for option in SLAB_FILTER_OPTIONS:
                    slab_filter.Items.Add(option)

                slab_filter.SelectedIndex = 0

                def on_slab_filter_changed(
                    sender,
                    args
                ):
                    try:
                        if sender.SelectedItem is None:
                            return
                        active_filters['Slab'] = str(
                            sender.SelectedItem
                        )
                        refresh_category_view('Slab')
                    except:
                        pass

                slab_filter.SelectionChanged += (
                    on_slab_filter_changed
                )

            if foundation_filter:
                foundation_filter.Items.Clear()
                for option in FOUNDATION_FILTER_OPTIONS:
                    foundation_filter.Items.Add(option)

                foundation_filter.SelectedIndex = 0

                def on_foundation_filter_changed(
                    sender,
                    args
                ):
                    try:
                        if sender.SelectedItem is None:
                            return
                        active_filters['Foundation'] = str(
                            sender.SelectedItem
                        )
                        refresh_category_view('Foundation')
                    except:
                        pass

                foundation_filter.SelectionChanged += (
                    on_foundation_filter_changed
                )


        setup_rcc_filters()


        # ====================================================
        # POPULATE PARAMETERS
        # ====================================================

        for element_name in control_map.keys():

            controls = control_map[
                element_name
            ]

            available = window.FindName(
                controls["available"]
            )

            selected = window.FindName(
                controls["selected"]
            )

            filter_available_by_search(
                element_name
            )

            if selected:

                selected.Items.Clear()

            search_box = window.FindName(
                controls["search"]
            )

            if search_box is not None:

                def on_search_changed(
                    sender,
                    args,
                    name=element_name
                ):
                    try:
                        filter_available_by_search(
                            name
                        )
                    except:
                        pass

                search_box.TextChanged += (
                    on_search_changed
                )


        # Ensure the initial logical views use the active filters.
        refresh_category_view('Slab')
        refresh_category_view('Foundation')

        # ====================================================
        # RESTORE SAVED SETTINGS
        # ====================================================
        # Re-apply the previously saved filters and parameter selections
        # so the user does not have to re-pick everything every session.

        saved_settings = load_app_settings()

        saved_filters = {}

        try:
            saved_filters = saved_settings.get(
                "filters",
                {}
            )
        except:
            saved_filters = {}

        # Apply saved subtype filters (validated against the options).
        saved_slab_filter = saved_filters.get(
            "Slab",
            "All Slab Types"
        )
        saved_foundation_filter = saved_filters.get(
            "Foundation",
            "All Foundation Types"
        )

        if saved_slab_filter in SLAB_FILTER_OPTIONS:
            active_filters["Slab"] = saved_slab_filter
        else:
            active_filters["Slab"] = "All Slab Types"

        if saved_foundation_filter in FOUNDATION_FILTER_OPTIONS:
            active_filters["Foundation"] = saved_foundation_filter
        else:
            active_filters["Foundation"] = "All Foundation Types"

        refresh_category_view('Slab')
        refresh_category_view('Foundation')

        # Sync the subtype combo boxes to the restored filters.
        try:
            slab_combo = window.FindName("SlabFilter")
            if slab_combo:
                try:
                    slab_combo.SelectedItem = saved_slab_filter
                except:
                    slab_combo.SelectedIndex = 0
        except:
            pass

        try:
            foundation_combo = window.FindName("FoundationFilter")
            if foundation_combo:
                try:
                    foundation_combo.SelectedItem = saved_foundation_filter
                except:
                    foundation_combo.SelectedIndex = 0
        except:
            pass

        # Restore the saved checkbox defaults ("Export selected only" and
        # "Open file after export").
        try:
            only_check = window.FindName("ExportOnlyCheck")
            if only_check:
                try:
                    only_check.IsChecked = bool(
                        saved_settings.get("export_only", False)
                    )
                except:
                    pass
        except:
            pass

        try:
            auto_check = window.FindName("AutoOpenCheck")
            if auto_check:
                try:
                    auto_check.IsChecked = bool(
                        saved_settings.get("auto_open", False)
                    )
                except:
                    pass
        except:
            pass

        # Restore the saved "Include quantities" default (enabled
        # unless the user turned it off in a previous session).
        try:
            qty_restore = window.FindName("QuantitiesCheck")
            if qty_restore:
                try:
                    qty_restore.IsChecked = bool(
                        saved_settings.get(
                            "include_quantities",
                            True
                        )
                    )
                except:
                    pass
        except:
            pass

        # Restore the saved "Site format" default (site-style workbook
        # on; the classic BOQ Summary / BOQ by Level / BOQ by Grade
        # workbook when off).
        try:
            site_restore = window.FindName("SiteFormatCheck")
            if site_restore:
                try:
                    site_restore.IsChecked = bool(
                        saved_settings.get(
                            "site_format",
                            True
                        )
                    )
                except:
                    pass
        except:
            pass

        # Restore the previously selected parameters in saved order.
        saved_selected = {}

        try:
            saved_selected = saved_settings.get(
                "selected",
                {}
            )
        except:
            saved_selected = {}

        for element_name in control_map.keys():

            controls = control_map[element_name]

            selected = window.FindName(
                controls["selected"]
            )

            if selected is None:
                continue

            saved_names = []

            try:
                saved_names = saved_selected.get(
                    element_name,
                    []
                )
            except:
                saved_names = []

            if not saved_names:
                continue

            name_to_item = {}

            for parameter in category_parameters.get(
                element_name,
                []
            ):

                try:
                    name_to_item[
                        parameter.Name
                    ] = parameter
                except:
                    pass

            restored = []

            for saved_name in saved_names:

                parameter = name_to_item.get(
                    saved_name
                )

                if parameter is not None:
                    selected.Items.Add(parameter)
                    restored.append(saved_name)

            # Keep the internal list consistent with what was restored.
            try:
                selected_parameters[
                    element_name
                ] = restored
            except:
                pass

        # v1.7.1: rebuild the Available lists so restored selections are
        # hidden from what still remains available to add.
        for element_name in control_map.keys():
            try:
                filter_available_by_search(element_name)
            except:
                pass

        # ====================================================
        # INTERNAL PARAMETER ORDER SYNC
        # ====================================================

        def sync_selected_parameters(
            element_name
        ):
            """
            Keep the internal selected_parameters list aligned with the
            exact order currently visible in the Selected / Export ListBox.
            This keeps the parallel data structure accurate after Add,
            Remove, and Up / Down / Top / Bottom reordering.
            """
            controls = control_map[
                element_name
            ]

            selected = window.FindName(
                controls["selected"]
            )

            if selected is None:
                return

            ordered_names = []

            try:
                for item in selected.Items:
                    try:
                        ordered_names.append(
                            item.Name
                        )
                    except:
                        ordered_names.append(
                            safe_text(
                                item,
                                "Unknown"
                            )
                        )
            except:
                ordered_names = []

            try:
                selected_parameters[
                    element_name
                ] = ordered_names
            except:
                pass


        # ====================================================
        # CAPTURE & SAVE SETTINGS
        # ====================================================

        def capture_and_save_settings():
            """
            Persist the current selections, subtype filters and the
            checkbox options to the JSON settings file so the next run
            restores them automatically.
            """
            settings = {}

            # Re-sync every category from its visible ListBox first.
            for element_name in control_map.keys():
                try:
                    sync_selected_parameters(element_name)
                except:
                    pass

            settings["selected"] = {}

            for element_name in selected_parameters.keys():
                settings["selected"][element_name] = list(
                    selected_parameters.get(element_name, [])
                )

            settings["filters"] = dict(
                active_filters
            )

            # v1.5.0: carry the theme selector state forward so an
            # export never wipes the theme preference saved on change.
            try:
                _theme_combo = window.FindName("ThemeSelector")

                if _theme_combo is not None:
                    if _theme_combo.SelectedIndex == 1:
                        settings["theme"] = "Light"
                    elif _theme_combo.SelectedIndex == 2:
                        settings["theme"] = "Dark"
                    else:
                        settings["theme"] = "Auto"
            except:
                pass

            # Persist the checkbox states as the new defaults.
            try:
                only_check = window.FindName("ExportOnlyCheck")
                if only_check:
                    try:
                        settings["export_only"] = bool(
                            only_check.IsChecked
                        )
                    except:
                        pass
            except:
                pass

            try:
                auto_check = window.FindName("AutoOpenCheck")
                if auto_check:
                    try:
                        settings["auto_open"] = bool(
                            auto_check.IsChecked
                        )
                    except:
                        pass
            except:
                pass

            # Persist the "Include quantities" choice as the new default.
            try:
                qty_save = window.FindName("QuantitiesCheck")
                if qty_save:
                    try:
                        settings["include_quantities"] = bool(
                            qty_save.IsChecked
                        )
                    except:
                        pass
            except:
                pass

            # Persist the "Site format" choice as the new default.
            try:
                site_save = window.FindName("SiteFormatCheck")
                if site_save:
                    try:
                        settings["site_format"] = bool(
                            site_save.IsChecked
                        )
                    except:
                        pass
            except:
                pass

            save_app_settings(settings)


        # ====================================================
        # ADD PARAMETERS
        # ====================================================

        def add_parameters(
            element_name
        ):

            controls = control_map[
                element_name
            ]

            available = window.FindName(
                controls["available"]
            )

            selected = window.FindName(
                controls["selected"]
            )

            if not available or not selected:
                return

            selected_items = list(
                available.SelectedItems
            )

            if not selected_items:
                return

            existing = []

            for item in selected.Items:

                existing.append(
                    item.Name
                )

            for item in selected_items:

                if item.Name not in existing:

                    selected.Items.Add(
                        item
                    )

            # keep the internal list aligned with the visible order
            sync_selected_parameters(
                element_name
            )

            # deselect
            available.UnselectAll()

            # v1.7.1: hide the just-added parameters from Available.
            try:
                filter_available_by_search(element_name)
            except:
                pass


        # ====================================================
        # REMOVE PARAMETERS
        # ====================================================

        def remove_parameters(
            element_name
        ):

            controls = control_map[
                element_name
            ]

            selected = window.FindName(
                controls["selected"]
            )

            if not selected:
                return

            selected_items = list(
                selected.SelectedItems
            )

            if not selected_items:
                return

            # remove from bottom to top
            indexes = []

            for item in selected_items:

                index = selected.Items.IndexOf(
                    item
                )

                indexes.append(
                    index
                )

            indexes.sort(
                reverse=True
            )

            for index in indexes:

                item = selected.Items[
                    index
                ]

                selected.Items.RemoveAt(
                    index
                )

            # keep the internal list aligned with the visible order
            sync_selected_parameters(
                element_name
            )

            selected.UnselectAll()

            # v1.7.1: bring the removed parameters back into Available.
            try:
                filter_available_by_search(element_name)
            except:
                pass


        # ====================================================
        # MOVE UP
        # ====================================================

        def move_up(
            element_name
        ):

            controls = control_map[
                element_name
            ]

            selected = window.FindName(
                controls["selected"]
            )

            if not selected:
                return

            indexes = []

            for item in selected.SelectedItems:

                indexes.append(
                    selected.Items.IndexOf(
                        item
                    )
                )

            indexes.sort()

            for index in indexes:

                if index <= 0:
                    continue

                item = selected.Items[
                    index
                ]

                selected.Items.RemoveAt(
                    index
                )

                selected.Items.Insert(
                    index - 1,
                    item
                )

                selected.SelectedItems.Add(
                    item
                )

            # keep the internal list aligned with the visible order
            sync_selected_parameters(
                element_name
            )


        # ====================================================
        # MOVE DOWN
        # ====================================================

        def move_down(
            element_name
        ):

            controls = control_map[
                element_name
            ]

            selected = window.FindName(
                controls["selected"]
            )

            if not selected:
                return

            indexes = []

            for item in selected.SelectedItems:

                indexes.append(
                    selected.Items.IndexOf(
                        item
                    )
                )

            indexes.sort(
                reverse=True
            )

            for index in indexes:

                if index >= (
                    selected.Items.Count - 1
                ):

                    continue

                item = selected.Items[
                    index
                ]

                selected.Items.RemoveAt(
                    index
                )

                selected.Items.Insert(
                    index + 1,
                    item
                )

                selected.SelectedItems.Add(
                    item
                )

            # keep the internal list aligned with the visible order
            sync_selected_parameters(
                element_name
            )


        # ====================================================
        # MOVE TOP
        # ====================================================

        def move_top(
            element_name
        ):

            controls = control_map[
                element_name
            ]

            selected = window.FindName(
                controls["selected"]
            )

            if not selected:
                return

            selected_items = list(
                selected.SelectedItems
            )

            if not selected_items:
                return

            selected_names = []

            for item in selected_items:

                selected_names.append(
                    item.Name
                )

            remaining = []

            for item in selected.Items:

                if item.Name not in selected_names:

                    remaining.append(
                        item
                    )

            selected.Items.Clear()

            for item in selected_items:

                selected.Items.Add(
                    item
                )

            for item in remaining:

                selected.Items.Add(
                    item
                )

            selected.UnselectAll()

            for item in selected_items:

                selected.SelectedItems.Add(
                    item
                )

            # keep the internal list aligned with the visible order
            sync_selected_parameters(
                element_name
            )


        # ====================================================
        # MOVE BOTTOM
        # ====================================================

        def move_bottom(
            element_name
        ):

            controls = control_map[
                element_name
            ]

            selected = window.FindName(
                controls["selected"]
            )

            if not selected:
                return

            selected_items = list(
                selected.SelectedItems
            )

            if not selected_items:
                return

            selected_names = []

            for item in selected_items:

                selected_names.append(
                    item.Name
                )

            remaining = []

            for item in selected.Items:

                if item.Name not in selected_names:

                    remaining.append(
                        item
                    )

            selected.Items.Clear()

            for item in remaining:

                selected.Items.Add(
                    item
                )

            for item in selected_items:

                selected.Items.Add(
                    item
                )

            selected.UnselectAll()

            for item in selected_items:

                selected.SelectedItems.Add(
                    item
                )

            # keep the internal list aligned with the visible order
            sync_selected_parameters(
                element_name
            )


        # ====================================================
        # CONNECT BUTTONS
        # ====================================================

        for element_name in control_map.keys():

            controls = control_map[
                element_name
            ]

            add_button = window.FindName(
                controls["add"]
            )

            remove_button = window.FindName(
                controls["remove"]
            )

            up_button = window.FindName(
                controls["up"]
            )

            down_button = window.FindName(
                controls["down"]
            )

            top_button = window.FindName(
                controls["top"]
            )

            bottom_button = window.FindName(
                controls["bottom"]
            )


            if add_button:

                add_button.Click += (
                    lambda sender,
                    args,
                    name=element_name:
                    add_parameters(name)
                )


            if remove_button:

                remove_button.Click += (
                    lambda sender,
                    args,
                    name=element_name:
                    remove_parameters(name)
                )


            if up_button:

                up_button.Click += (
                    lambda sender,
                    args,
                    name=element_name:
                    move_up(name)
                )


            if down_button:

                down_button.Click += (
                    lambda sender,
                    args,
                    name=element_name:
                    move_down(name)
                )


            if top_button:

                top_button.Click += (
                    lambda sender,
                    args,
                    name=element_name:
                    move_top(name)
                )


            if bottom_button:

                bottom_button.Click += (
                    lambda sender,
                    args,
                    name=element_name:
                    move_bottom(name)
                )

            # v1.7.1: double-click moves a parameter across the lists.
            available_box = window.FindName(
                controls["available"]
            )
            selected_box = window.FindName(
                controls["selected"]
            )

            if available_box:

                def on_available_double_click(
                    sender,
                    args,
                    _name=element_name
                ):
                    try:
                        add_parameters(_name)
                    except:
                        pass

                available_box.MouseDoubleClick += (
                    on_available_double_click
                )

            if selected_box:

                def on_selected_double_click(
                    sender,
                    args,
                    _name=element_name
                ):
                    try:
                        remove_parameters(_name)
                    except:
                        pass

                selected_box.MouseDoubleClick += (
                    on_selected_double_click
                )


        # ====================================================
        # APPLY / OK
        # ====================================================

        apply_button = window.FindName(
            "ApplyButton"
        )

        if apply_button:

            def apply_parameters(
                sender,
                args
            ):

                total = 0

                for name in selected_parameters.keys():

                    total += len(
                        selected_parameters[name]
                    )

                # ====================================================
                # PARAMETER METADATA ENGINE
                # ====================================================

                global parameter_metadata

                try:

                    parameter_metadata = (
                        build_parameter_metadata()
                    )

                    metadata_total = (
                        count_parameter_metadata(
                            parameter_metadata
                        )
                    )

                    if status:

                        set_status(
                            "Metadata captured | "
                            "Parameters: {}".format(
                                metadata_total
                            ),
                            "success"
                        )

                    forms.alert(
                        "Parameter metadata captured successfully.\n\n"
                        "Beam: {}\n"
                        "Column: {}\n"
                        "Slab: {}\n"
                        "Foundation: {}\n\n"
                        "Metadata records: {}".format(

                            len(
                                parameter_metadata["Beam"]
                            ),

                            len(
                                parameter_metadata["Column"]
                            ),

                            len(
                                parameter_metadata["Slab"]
                            ),

                            len(
                                parameter_metadata["Foundation"]
                            ),

                            metadata_total
                        ),

                        title="RCC BOQ - Parameter Metadata"
                    )

                except Exception as metadata_error:

                    if status:

                        set_status(
                            "Metadata error | {}".format(
                                safe_text(
                                    metadata_error,
                                    "Unknown error"
                                )
                            ),
                            "error"
                        )

                    forms.alert(
                        "Parameter Metadata Engine Error\n\n"
                        "{}\n\n"
                        "Existing parameter selection has not been "
                        "redesigned.".format(
                            str(metadata_error)
                        ),

                        title="RCC BOQ - Metadata Error"
                    )


            apply_button.Click += (
                apply_parameters
            )


        # ====================================================
        # CLOSE
        # ====================================================

        close_button = window.FindName(
            "CloseButton"
        )

        if close_button:

            def close_window(
                sender,
                args
            ):

                try:
                    capture_and_save_settings()
                except:
                    pass

                window.Close()

            close_button.Click += (
                close_window
            )


        # ====================================================
        # DYNAMIC EXCEL EXPORT - STEP 6A
        # ====================================================

        export_button = window.FindName(
            "ExportButton"
        )

        if export_button:

            def export_to_excel(
                sender,
                args
            ):

                total = 0

                for name in selected_parameters.keys():

                    total += len(
                        selected_parameters[name]
                    )

                if total == 0:

                    if status:
                        set_status(
                            "Excel export | "
                            "No parameters selected",
                            "warning"
                        )

                    forms.alert(
                        "Please select at least one parameter "
                        "before exporting Excel.",
                        title="RCC BOQ - Excel Export"
                    )

                    return

                try:

                    # Respect the "Export selected only" checkbox: collect
                    # the currently selected Revit elements up front.
                    global export_only_flag
                    global active_selection_ids

                    only_check = window.FindName(
                        "ExportOnlyCheck"
                    )

                    if only_check:
                        try:
                            export_only_flag = bool(
                                only_check.IsChecked
                            )
                        except:
                            export_only_flag = False
                    else:
                        export_only_flag = False

                    if export_only_flag:
                        active_selection_ids = (
                            get_selection_ids()
                        )
                    else:
                        active_selection_ids = set()

                    # Respect the "Include quantities" checkbox: when
                    # active, numeric quantity takeoff columns and the
                    # BOQ Summary sheet are added to the workbook.
                    global quantities_flag

                    qty_check = window.FindName(
                        "QuantitiesCheck"
                    )

                    if qty_check:
                        try:
                            quantities_flag = bool(
                                qty_check.IsChecked
                            )
                        except:
                            quantities_flag = True
                    else:
                        quantities_flag = True

                    # Always rebuild metadata before export so the
                    # workbook reflects the current selection/order.
                    global parameter_metadata
                    parameter_metadata = (
                        build_parameter_metadata()
                    )

                    (
                        element_data,
                        total_rows,
                        missing_values
                    ) = build_element_data()

                    if total_rows == 0:

                        if status:
                            set_status(
                                "Excel export | No element rows",
                                "warning"
                            )

                        forms.alert(
                            "No Beam, Column, Slab, or Foundation "
                            "element rows were found to export.",
                            title="RCC BOQ - Excel Export"
                        )

                        return

                    output_path = choose_excel_output_path()

                    if not output_path:

                        if status:
                            set_status(
                                "Excel export cancelled",
                                "info"
                            )

                        return

                    # Ensure the file always uses the XLSX extension.
                    if not output_path.lower().endswith(".xlsx"):
                        output_path += ".xlsx"

                    # v1.4.0 site-format export, user-selectable since
                    # v1.6.1 through the footer "Site format" checkbox.
                    # The module flag stays as the fallback default and
                    # the classic workbook engine remains available as
                    # the off state.
                    use_site_format = site_format_flag

                    site_check = window.FindName(
                        "SiteFormatCheck"
                    )

                    if site_check:
                        try:
                            use_site_format = bool(
                                site_check.IsChecked
                            )
                        except:
                            use_site_format = site_format_flag

                    if use_site_format:

                        sheet_rows = write_site_xlsx(
                            output_path,
                            element_data,
                            project_name=(
                                safe_text(doc.Title, "Revit Project")
                            ),
                            tool_version=(
                                "RCC BOQ Parameter Manager v{0}".format(
                                    SCRIPT_VERSION
                                )
                            ),
                            generated_stamp=time.strftime("%Y-%m-%d %H:%M")
                        )

                    else:

                        sheet_rows = write_basic_xlsx(
                            output_path,
                            element_data,
                            parameter_metadata,
                            project_name=(
                                safe_text(doc.Title, "Revit Project")
                            ),
                            tool_version=(
                                "RCC BOQ Parameter Manager v{0}".format(
                                    SCRIPT_VERSION
                                )
                            ),
                            generated_stamp=time.strftime("%Y-%m-%d %H:%M")
                        )

                    non_empty_sheets = 0

                    for sheet_name in (
                        "Beam",
                        "Column",
                        "Slab",
                        "Foundation"
                    ):

                        if len(
                            sheet_rows.get(
                                sheet_name,
                                []
                            )
                        ) > 1:
                            non_empty_sheets += 1

                    if status:

                        set_status(
                            "Excel exported | "
                            "Rows: {}".format(
                                total_rows
                            ),
                            "success"
                        )

                    # Optionally launch the workbook in Excel once written.
                    auto_check = window.FindName(
                        "AutoOpenCheck"
                    )

                    if auto_check:
                        try:
                            if auto_check.IsChecked:
                                import subprocess
                                _ = subprocess.Popen(
                                    ["start", "", output_path],
                                    shell=True
                                )
                            else:
                                pass
                        except:
                            try:
                                os.startfile(output_path)
                            except:
                                pass

                    # Summarize quantity takeoff coverage for the dialog.
                    quantity_columns = 0

                    for category_name in (
                        "Beam",
                        "Column",
                        "Slab",
                        "Foundation"
                    ):

                        category_table = sheet_rows.get(
                            category_name,
                            []
                        )

                        if not category_table:
                            continue

                        for header_text in category_table[0]:

                            try:
                                if header_text[:4] == "Qty:":
                                    quantity_columns += 1
                            except:
                                pass

                    # Build the workbook listing dynamically from the sheets
                    # actually written, so the dialog always matches the file.
                    sheets_listing = ", ".join(
                        list(sheet_rows.keys())
                    )

                    forms.alert(
                        "Version: {} · RCC BOQ\n\n"
                        "Everything's exported — here's your workbook.\n\n"
                        "File: {}\n"
                        "Selected parameters: {}\n"
                        "Element data rows: {}\n"
                        "Sheets with element data: {}\n"
                        "Quantity columns: {}\n\n"
                        "Workbook sheets: {}".format(
                            SCRIPT_VERSION,
                            output_path,
                            total,
                            total_rows,
                            non_empty_sheets,
                            quantity_columns,
                            sheets_listing
                        ),
                        title="RCC BOQ - Excel Export"
                    )

                except Exception as export_error:

                    if status:

                        set_status(
                            "Excel export error | {}".format(
                                safe_text(
                                    export_error,
                                    "Unknown error"
                                )
                            ),
                            "error"
                        )

                    forms.alert(
                        "RCC BOQ Excel Export Error\n\n"
                        "{}\n\n"
                        "Existing parameter selection, metadata, "
                        "and element-data functionality has not been redesigned.".format(
                            str(export_error)
                        ),
                        title="RCC BOQ - Excel Export Error"
                    )


            export_button.Click += (
                export_to_excel
            )


        # ====================================================
        # FINAL STATUS
        # ====================================================

        beam_count = len(
            category_elements["Beam"]
        )

        column_count = len(
            category_elements["Column"]
        )

        slab_count = len(
            category_elements["Slab"]
        )

        foundation_count = len(
            category_elements["Foundation"]
        )

        if status:

            set_status(
                "Parameters loaded | "
                "Beam: {} | "
                "Column: {} | "
                "Slab: {} | "
                "Foundation: {}".format(

                    len(category_elements.get('Beam', [])),
                    len(category_elements.get('Column', [])),
                    len(category_elements.get('Slab', [])),
                    len(category_elements.get('Foundation', []))
                )
            )


        # ====================================================
        # SHOW WINDOW
        # ====================================================

        window.ShowDialog()


except Exception as ex:

    forms.alert(

        "RCC BOQ STARTUP ERROR\n\n"
        "{}\n\n"
        "DETAILS:\n{}".format(

            str(ex),
            traceback.format_exc()
        ),

        title="RCC BOQ ERROR"
    )

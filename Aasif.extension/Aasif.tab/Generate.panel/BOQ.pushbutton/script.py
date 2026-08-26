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
__version__ = '1.3.0'
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
SCRIPT_VERSION = '1.3.0'

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

    # P1: per-category parameter dimension (pruned automatically when "")
    if element_name == "Column":
        results.append(
            (
                "Qty: Height (m)",
                read_metric_parameter(element, "Height")
            )
        )
    elif element_name in ("Slab", "Foundation"):
        results.append(
            (
                "Qty: Thickness (m)",
                read_metric_parameter(element, "Thickness")
            )
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


def build_xlsx_styles_xml():
    """
    Workbook styles used by the export engine:

    xf 0 - default body text
    xf 1 - header row: bold white on dark blue fill
    xf 2 - numeric quantity cells with #,##0.00 formatting
    xf 3 - totals label cells: bold on light gray with top border
    xf 4 - totals number cells: bold #,##0.00 on light gray
    """
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<numFmts count="0"/>'
        '<fonts count="3">'
        '<font><sz val="11"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><name val="Calibri"/></font>'
        '</fonts>'
        '<fills count="4">'
        '<fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FF305496"/><bgColor indexed="64"/></patternFill></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFF2F2F2"/><bgColor indexed="64"/></patternFill></fill>'
        '</fills>'
        '<borders count="2">'
        '<border><left/><right/><top/><bottom/><diagonal/></border>'
        '<border><left/><right/><top><style>thin</style></top><bottom/><diagonal/></border>'
        '</borders>'
        '<cellStyleXfs count="1">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>'
        '</cellStyleXfs>'
        '<cellXfs count="5">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>'
        '<xf numFmtId="4" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
        '<xf numFmtId="0" fontId="2" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>'
        '<xf numFmtId="4" fontId="2" fillId="3" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1"/>'
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

                # P2: Level is an engine-added grouping column, not a
                # selected parameter; it is not part of the audit.
                if key == "Level":
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


def write_basic_xlsx(file_path, data_result, parameter_metadata=None,
                     project_name="", tool_version="", generated_stamp=""):
    """
    Write a dependency-free XLSX workbook using Open XML parts.
    This avoids requiring Excel, openpyxl, or other external packages
    inside the pyRevit IronPython environment.

    The workbook contains one sheet per populated category (Beam, Column,
    Slab, Foundation - empty categories are skipped), a BOQ Summary sheet
    with live SUM formulas and a per-element Costing sheet when rate data
    is available.
    """
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

            has_value = False

            for row in rows:

                try:
                    value = row.get(key, "")
                except:
                    value = ""

                if value not in ("", None):
                    has_value = True
                    break

            if has_value or not rows:
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
            build_xlsx_styles_xml().encode("utf-8")
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


def classify_foundation_subtype(element):
    """Classify logical foundation subtypes from actual names/codes."""
    text = get_element_identity_text(element)

    # Explicit slab-like foundation elements stay in the Slab tab.
    if classify_slab_subtype(element) in ('Slab', 'Fold Slab', 'Grade Slab'):
        # PCC is intentionally treated as foundation even when a type name
        # contains both PCC and slab wording.
        if 'pcc' not in text:
            return 'Slab-like'

    if ('combined footing' in text or 'combine footing' in text or
            code_token_match(text, ('cf',))):
        return 'Combined Footing'

    if 'footing' in text or code_token_match(text, ('f',)):
        return 'Footing'

    if 'pcc' in text:
        return 'PCC'

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
    'Slab': list(all_floor_elements) + [
        e for e in all_foundation_elements
        if classify_slab_subtype(e) in ('Slab', 'Fold Slab', 'Grade Slab')
    ],
    'Foundation': [
        e for e in all_foundation_elements
        if classify_foundation_subtype(e) != 'Slab-like'
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

        if status:

            status.Text = (
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
                base_elements = list(all_floor_elements)

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

                category_elements['Foundation'] = filter_elements(
                    list(all_foundation_elements),
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
                    status.Text = (
                        '{} filter: {} | Elements: {}'.format(
                            element_name,
                            active_filters.get(element_name, 'All'),
                            len(category_elements.get(element_name, []))
                        )
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

                        status.Text = (
                            "Metadata captured | "
                            "Parameters: {}".format(
                                metadata_total
                            )
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

                        status.Text = (
                            "Metadata error | {}".format(
                                safe_text(
                                    metadata_error,
                                    "Unknown error"
                                )
                            )
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
                        status.Text = (
                            "Excel export | "
                            "No parameters selected"
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
                            status.Text = (
                                "Excel export | No element rows"
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
                            status.Text = (
                                "Excel export cancelled"
                            )

                        return

                    # Ensure the file always uses the XLSX extension.
                    if not output_path.lower().endswith(".xlsx"):
                        output_path += ".xlsx"

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

                        status.Text = (
                            "Excel exported | "
                            "Rows: {}".format(
                                total_rows
                            )
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
                        "Excel export successful.\n\n"
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

                        status.Text = (
                            "Excel export error | {}".format(
                                safe_text(
                                    export_error,
                                    "Unknown error"
                                )
                            )
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

            status.Text = (
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

# -*- coding: utf-8 -*-

"""
RCC BOQ Parameter Manager
=========================
Generates an RCC (Reinforced Cement Concrete) Bill of Quantities workbook
from the structural elements in the active Revit document.

Targets Revit 2025+ with pyRevit 6.10.0+ on the CP3123 (CPython 3.12.3) or
IP27 (IronPython 2.7) engine. The XLSX engine is dependency-free and is
covered by test_xlsx_writer.py.

The pure-Python engines live in Nudge.extension/lib/ (settings_engine,
quantity_engine, formwork_engine, costing_engine, export_engine -
PROJECT_STRUCTURE.md section 9). This script keeps the Revit-bound code
(classification, parameter discovery, WPF dialog, event wiring) and
imports the moved engines back from lib/ by plain module name.

__title__ = 'RCC BOQ'
__author__ = 'Aasif'
__version__ = '1.8.6'
__min_revit_ver__ = '2025'
__doc__ = 'RCC BOQ Parameter Manager - Beam / Column / Slab / Foundation BOQ export'
"""

from pyrevit import revit, forms
from Autodesk.Revit import DB

import os
import traceback
import re
import time
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
# script (both were aligned at v1.8.6 after drifting apart). Semantic
# versioning (MAJOR.MINOR.PATCH) - see PROJECT_STRUCTURE.md.
SCRIPT_VERSION = '1.8.6'

# ------------------------------------------------------------
# ENGINE GUARD (todo-list.md T-03)
# ------------------------------------------------------------
# The installed pyRevit build (master 6.5.3) stubs pyrevit.forms for
# CPython (_cpy.py raises PyRevitCPythonNotSupported for every member), and
# upstream pyRevit master (6.5.5, checked 2026-09-01) still ships the
# same stub, so NO upstream pyRevit build currently exposes a CPython-capable
# pyrevit.forms. Therefore form-based pushbuttons (BOQ, Brand Showcase)
# execute on the IP27 (IronPython 2.7) engine on this machine until a
# CPython forms backend ships in pyRevit. This guard makes that engine reality
# visible instead of silent: it logs the active engine to the pyRevit output
# window (the T-03 runtime-verification hook) and, on non-CP3123
# engines, surfaces a clear forms.alert warning rather than claiming a
# CP3123-only runtime that isn't actually active.

def _warn_if_not_cp3123():
    """Make the active Python engine visible at startup (T-03 runtime check).

    Logs to the pyRevit output window via pyrevit.script.get_output().print_html
    (the live click-through verification hook); if the engine is not the supported
    CP3123, shows a forms.alert warning instead of failing silently. Fully
    guarded: a failure here must never block the dialog or the export.
    """
    engine_label = 'CPython 3.x'
    is_ironpython = False
    is_cp3123 = False
    try:
        import sys as _sys
        is_ironpython = '.net' in _sys.version.lower()
        if is_ironpython:
            engine_label = 'IP27 (IronPython 2.7)'
        try:
            is_cp3123 = (
                not is_ironpython
                and _sys.version_info[:3] == (3, 12, 3)
            )
        except:
            is_cp3123 = False
    except:
        pass

    try:
        from pyrevit import script as _pyrevit_script
        _pyrevit_script.get_output().print_html(
            '<b>RCC BOQ engine:</b> {0}'.format(engine_label,)
        )
    except:
        pass

    if not is_cp3123:
        try:
            forms.alert(
                'RCC BOQ is working, but the engine is {0}, not the supported '
                'CP3123 (CPython 3.12.3). The installed pyRevit build stubs '
                'pyrevit.forms for CPython, so this dialog runs on IronPython '
                'until a CPython-capable forms backend ships in pyRevit. '
                'Live verification: the pyRevit output window shows the active '
                'engine each time the button runs. See todo-list.md T-03.'
            .format(engine_label,))
        except:
            pass

_warn_if_not_cp3123()

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
quantities_flag = True

# ============================================================
# FORMWORK ENGINE (P3) - moved to lib/formwork_engine.py
# ============================================================
# The P3 configurable shuttering rules now live in the
# dependency-free lib/formwork_engine.py module (rule functions +
# the DEFAULT_FORMWORK_RULES / formwork_rules module state +
# build_shuttering_formula). formwork_rules is the same dict object
# the moved engine reads, so the footer checkbox handlers keep
# mutating it in place.
from formwork_engine import (
    formwork_rules,
    compute_shuttering_area,
    normalize_formwork_rules,
    get_formwork_factor,
    is_formwork_enabled,
)


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
# SETTINGS PERSISTENCE - moved to lib/settings_engine.py
# ============================================================
# JSON settings persistence moved verbatim to the dependency-free
# lib/settings_engine.py module (os/json only); get_settings_path
# lives there too and backs load/save below.
from settings_engine import (
    load_app_settings,
    save_app_settings,
)


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


# safe_text moved to lib/export_engine.py - shared pure-Python
# safe-string helper used by the XLSX metadata-sheet builders there
# and by the Revit-bound readers here.
from export_engine import safe_text


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
# Dependency-free unit conversion (convert_quantity_value) and the
# dimension helper (resolve_element_dimensions) moved to
# lib/quantity_engine.py (meters_to_millimeters and
# build_section_description live there too - nothing in this file
# calls them anymore).
# read_metric_parameter and get_element_quantities stay here because
# they are Revit API-bound (element parameter/geometry reads).
from quantity_engine import (
    convert_quantity_value,
    resolve_element_dimensions,
)


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


# meters_to_millimeters and build_section_description moved to
# lib/quantity_engine.py (imported in the QUANTITY TAKEOFF ENGINE
# section above only where still needed).


# compute_shuttering_area, _safe_factor, normalize_formwork_rules,
# get_formwork_factor and is_formwork_enabled moved to
# lib/formwork_engine.py (imported in the FORMWORK ENGINE section
# above).


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
        area_m2=calculated_area,
        factor=get_formwork_factor(element_name),
        enabled=is_formwork_enabled()
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
# EXPORT ENGINE - moved to lib/export_engine.py
# ============================================================
# The dependency-free Open XML workbook writer (xlsx_cell and every
# build_* / write_* helper, styles + site constants) moved verbatim
# to lib/export_engine.py. build_costing_sheet went to
# lib/costing_engine.py and build_shuttering_formula to
# lib/formwork_engine.py. Only the names the remaining Revit-bound
# code actually calls are imported back here.
from export_engine import (
    write_basic_xlsx,
    write_site_xlsx,
    build_default_output_name,
)

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
            v1.7.6: paint every visual property of the four search boxes with
            concrete brushes (text, caret, selection, background, border).

            DynamicResource-driven properties — whether via the style, the
            template or XAML attributes — do not reliably reach TextBox
            internals under IronPython after the theme dictionaries are
            re-merged. Assigning real SolidColorBrush values via SetValue
            creates local values with the highest precedence and no resource
            lookup at all, so the box always matches the active theme exactly:
            background, border, text, caret and selection. Re-applied on every
            theme switch (theme name read from window.Tag).
            """
            try:
                from System.Windows.Controls import TextBox as _TextBox
                from System.Windows.Media import SolidColorBrush, Color
            except:
                return

            theme_name = "Light"

            try:
                _tag = str(getattr(window, "Tag", "") or "")

                if "Dark" in _tag:
                    theme_name = "Dark"
            except:
                pass

            if theme_name == "Dark":
                primary_hex = "EDEDED"
                surface_hex = "2B2B2B"
                border_hex = "3F3F3F"
            else:
                primary_hex = "1F1F1F"
                surface_hex = "FFFFFF"
                border_hex = "D6D6D6"

            try:
                text_brush = SolidColorBrush(
                    Color.FromRgb(
                        int(primary_hex[0:2], 16),
                        int(primary_hex[2:4], 16),
                        int(primary_hex[4:6], 16)
                    )
                )
                surface_brush = SolidColorBrush(
                    Color.FromRgb(
                        int(surface_hex[0:2], 16),
                        int(surface_hex[2:4], 16),
                        int(surface_hex[4:6], 16)
                    )
                )
                border_brush = SolidColorBrush(
                    Color.FromRgb(
                        int(border_hex[0:2], 16),
                        int(border_hex[2:4], 16),
                        int(border_hex[4:6], 16)
                    )
                )
                ember_brush = SolidColorBrush(
                    Color.FromRgb(0xF2, 0x99, 0x4A)
                )
                white_brush = SolidColorBrush(
                    Color.FromRgb(0xFF, 0xFF, 0xFF)
                )
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

                for _prop, _brush in (
                    (_TextBox.ForegroundProperty, text_brush),
                    (_TextBox.CaretBrushProperty, text_brush),
                    (_TextBox.SelectionBrushProperty, ember_brush),
                    (_TextBox.SelectionTextBrushProperty, white_brush),
                    (_TextBox.BackgroundProperty, surface_brush),
                    (_TextBox.BorderBrushProperty, border_brush)
                ):
                    try:
                        _sbox.SetValue(_prop, _brush)
                    except:
                        pass

                try:
                    _sbox.BorderThickness = 1
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

        # P3: restore the saved formwork (shuttering) rules so the
        # deduction percentages and the enabled state survive sessions.
        try:
            restored_formwork = normalize_formwork_rules(
                saved_settings.get("formwork", {})
            )
            formwork_rules["enabled"] = restored_formwork["enabled"]
            formwork_rules["deduction_pct"] = restored_formwork["deduction_pct"]

            # Mirror the saved enabled state onto the footer checkbox
            # so the dialog shows the real current setting.
            try:
                fw_restore = window.FindName("IncludeFormworkCheck")
                if fw_restore:
                    fw_restore.IsChecked = bool(
                        formwork_rules.get("enabled", True)
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

            # P3: persist the formwork rules, syncing "enabled" with
            # the footer "Include formwork" checkbox state.
            try:
                fw_save = window.FindName("IncludeFormworkCheck")
                if fw_save:
                    try:
                        formwork_rules["enabled"] = bool(
                            fw_save.IsChecked
                        )
                    except:
                        pass
            except:
                pass

            try:
                settings["formwork"] = {
                    "enabled": bool(
                        formwork_rules.get("enabled", True)
                    ),
                    "deduction_pct": dict(
                        formwork_rules.get("deduction_pct", {})
                    )
                }
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

            # Track which items are actually added (new, not duplicates)
            newly_added = []

            for item in selected_items:

                if item.Name not in existing:

                    selected.Items.Add(
                        item
                    )
                    newly_added.append(
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

            # Highlight (select) the newly added items in Selected
            try:
                selected.UnselectAll()
                for item in newly_added:
                    selected.SelectedItems.Add(
                        item
                    )
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

            available = window.FindName(
                controls["available"]
            )

            if not selected:
                return

            selected_items = list(
                selected.SelectedItems
            )

            if not selected_items:
                return

            # Track names of items being removed (for highlighting later)
            removed_names = []
            for item in selected_items:
                try:
                    removed_names.append(
                        item.Name
                    )
                except:
                    pass

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

            # Highlight (select) the returned items in Available
            try:
                if available and removed_names:
                    available.UnselectAll()
                    for item in available.Items:
                        try:
                            if item.Name in removed_names:
                                available.SelectedItems.Add(
                                    item
                                )
                        except:
                            pass
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

                    # P3: honour the footer "Include formwork" checkbox
                    # BEFORE the rows are built - get_element_quantities
                    # reads formwork_rules while it computes every row,
                    # so the flag must be current before
                    # build_element_data() runs, not just before the
                    # workbook writer is called.
                    fw_check = window.FindName(
                        "IncludeFormworkCheck"
                    )

                    if fw_check:
                        try:
                            formwork_rules["enabled"] = bool(
                                fw_check.IsChecked
                            )
                        except:
                            pass

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
                            generated_stamp=time.strftime("%Y-%m-%d %H:%M"),
                            include_formwork=is_formwork_enabled()
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

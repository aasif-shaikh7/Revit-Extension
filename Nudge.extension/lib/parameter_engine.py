# -*- coding: utf-8 -*-
"""Parameter engine (P8) - host-free parameter inspection and readers.

Moved verbatim from BOQ.pushbutton/script.py in the v1.24.1 split
(PROJECT_STRUCTURE.md section 9, the P8 landing point): safe value and
flag access, definition metadata, parameter lookup on an element or in a
prepared context, and the per-category parameter name lists, together
with the small ParameterItem display shim get_parameters returns.

Pure Python - no Revit or pyRevit symbol appears here. These functions
accept Revit objects but reach them only through duck-typed attribute
access inside try/except, which is why the harness can drive them with
plain stand-in objects.

Deliberately left in script.py because they genuinely need the host:
safe_is_project_parameter (reads doc.ParameterBindings), safe_element_id,
safe_is_built_in, safe_is_global, safe_parameter_value,
find_parameter_with_scope, build_element_parameter_context and
build_parameter_metadata.

Note: lib/export_engine.py carries its own behaviorally identical
safe_text, and lib/rest_api.py a different one that defaults to an empty
string. Consolidating the three is out of scope here so the XLSX engine
is not touched; see CHANGELOG v1.24.1.
"""


class ParameterItem(object):

    def __init__(self, name):
        self.Name = name

    def __str__(self):
        return self.Name

def safe_text(value, fallback="Unknown"):
    """Return a display-safe string without loading the XLSX engine."""
    try:
        if value is None:
            return fallback
        text = str(value)
        return text if text else fallback
    except:
        return fallback

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

def find_parameter_on_element(element, parameter_name, case_sensitive=True):
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

                if case_sensitive:
                    is_match = name == parameter_name
                else:
                    try:
                        is_match = name.lower() == parameter_name.lower()
                    except:
                        is_match = False

                if is_match:
                    return parameter

            except:
                continue

    except:
        return None

    return None

def find_parameter_in_context(parameter_context, parameter_name):
    """Return an indexed parameter with Instance-before-Type precedence."""
    try:
        key = str(parameter_name or "").lower()
    except:
        key = ""
    if not key or not isinstance(parameter_context, dict):
        return None, "Unknown"
    try:
        parameter = parameter_context.get("instance", {}).get(key)
    except:
        parameter = None
    if parameter is not None:
        return parameter, "Instance"
    try:
        parameter = parameter_context.get("type", {}).get(key)
    except:
        parameter = None
    if parameter is not None:
        return parameter, "Type"
    return None, "Unknown"

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

def get_parameters(elements, derived_names=None):

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

    for derived_name in (derived_names or ()):
        if derived_name:
            parameter_names.add(derived_name)

    result = []

    for name in parameter_names:

        result.append(
            ParameterItem(name)
        )

    result.sort(
        key=lambda x: x.Name.lower()
    )

    return result

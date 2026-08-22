# -*- coding: utf-8 -*-

from pyrevit import revit, forms
from Autodesk.Revit import DB

import os
import traceback
import re
import json
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


def build_xlsx_sheet_xml(rows):
    """Build worksheet XML for a 2D list of values."""
    row_xml = []
    max_columns = 0

    for row_number, values in enumerate(rows, 1):
        cells = []

        if len(values) > max_columns:
            max_columns = len(values)

        for column_number, value in enumerate(values, 1):
            cell_ref = "{}{}".format(
                xlsx_column_name(column_number),
                row_number
            )

            # Header row uses style 1.
            style_index = 1 if row_number == 1 else None

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

    if rows and len(rows) >= 1 and max_columns:
        auto_filter = (
            '<autoFilter ref="A1:{}{}"/>'.format(
                xlsx_column_name(max_columns),
                len(rows)
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
    """Minimal styles: normal + bold header."""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<numFmts count="0"/>'
        '<fonts count="2">'
        '<font><sz val="11"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><name val="Calibri"/></font>'
        '</fonts>'
        '<fills count="2">'
        '<fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        '</fills>'
        '<borders count="1">'
        '<border><left/><right/><top/><bottom/><diagonal/></border>'
        '</borders>'
        '<cellStyleXfs count="1">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>'
        '</cellStyleXfs>'
        '<cellXfs count="2">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
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
                if key != "Element ID":
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


def write_basic_xlsx(file_path, data_result, parameter_metadata=None):
    """
    Write a dependency-free XLSX workbook using Open XML parts.
    This avoids requiring Excel, openpyxl, or other external packages
    inside the pyRevit IronPython environment.

    When parameter_metadata is provided and contains at least one
    record, a dedicated "Parameter Metadata" sheet is appended.
    """
    sheet_names = [
        "Beam",
        "Column",
        "Slab",
        "Foundation"
    ]

    sheet_rows = {}

    for sheet_name in sheet_names:
        rows = data_result.get(sheet_name, [])

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

        sheet_rows[sheet_name] = table

    # Append a dedicated Parameter Metadata sheet built from the captured
    # metadata engine when at least one record exists. The workbook
    # writing paths below already work from the (now extended) sheet list.
    metadata_sheet = build_parameter_metadata_sheet(
        parameter_metadata
    )

    if len(metadata_sheet) > 1:
        sheet_names.append("Parameter Metadata")
        sheet_rows["Parameter Metadata"] = metadata_sheet

    # Append a data-quality report showing where parameter values are
    # missing, so repeated gaps can be diagnosed visually.
    missing_sheet = build_missing_values_summary(
        data_result
    )

    if len(missing_sheet) > 1:
        sheet_names.append("Missing Values Summary")
        sheet_rows["Missing Values Summary"] = missing_sheet

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
                    sheet_rows[sheet_name]
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

                    # Always rebuild metadata before export so the
                    # workbook reflects the current selection/order.
                    global parameter_metadata
                    parameter_metadata = (
                        build_parameter_metadata()
                    )

                    metadata_total = (
                        count_parameter_metadata(
                            parameter_metadata
                        )
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
                        parameter_metadata
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

                    forms.alert(
                        "Excel export successful.\n\n"
                        "File: {}\n"
                        "Selected parameters: {}\n"
                        "Metadata records: {}\n"
                        "Element data rows: {}\n"
                        "Missing / empty values: {}\n"
                        "Sheets with element data: {}\n\n"
                        "Workbook sheets: Beam, Column, Slab, Foundation, "
                        "Parameter Metadata and Missing Values Summary".format(
                            output_path,
                            total,
                            metadata_total,
                            total_rows,
                            missing_values,
                            non_empty_sheets
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

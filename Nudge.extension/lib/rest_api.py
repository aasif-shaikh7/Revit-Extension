# -*- coding: utf-8 -*-
"""Security and serialization helpers for the RCC BOQ Routes API.

This module deliberately does not import pyRevit or Autodesk.Revit symbols so
its authentication and bounded-output contracts can be tested with CPython.
The extension startup adapter supplies live Revit objects at runtime.
"""

from __future__ import absolute_import

import binascii
import os


API_NAME = "rcc-boq"
API_VERSION = "1.0.0"
EXTENSION_VERSION = "1.13.3"
TOKEN_BYTES = 32
MAX_SELECTION = 100
MAX_PARAMETERS = 250
TOKEN_DIRECTORY = "RCC_BOQ"
TOKEN_FILENAME = "rest_token.txt"


def token_file_path(local_app_data=None):
    """Return the per-user REST token path without exposing model data."""
    base = local_app_data or os.environ.get("LOCALAPPDATA")
    if not base:
        base = os.path.expanduser("~")
    return os.path.join(base, TOKEN_DIRECTORY, TOKEN_FILENAME)


def _new_token():
    token = binascii.hexlify(os.urandom(TOKEN_BYTES))
    if not isinstance(token, str):
        token = token.decode("ascii")
    return token


def load_or_create_token(path=None):
    """Load or atomically create a 256-bit per-user bearer token."""
    path = path or token_file_path()
    directory = os.path.dirname(path)
    if not os.path.isdir(directory):
        try:
            os.makedirs(directory)
        except OSError:
            if not os.path.isdir(directory):
                raise

    try:
        with open(path, "r") as token_file:
            token = token_file.read().strip()
        if len(token) == TOKEN_BYTES * 2:
            return token
    except IOError:
        pass

    token = _new_token()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        descriptor = os.open(path, flags, int("600", 8))
        try:
            os.write(descriptor, token.encode("ascii"))
        finally:
            os.close(descriptor)
        return token
    except OSError:
        # Another startup engine may have won the create race.
        with open(path, "r") as token_file:
            existing = token_file.read().strip()
        if len(existing) != TOKEN_BYTES * 2:
            raise ValueError("REST token file is invalid")
        return existing


def constant_time_equal(left, right):
    """Compare ASCII secrets without leaking the first differing position."""
    try:
        left = str(left or "")
        right = str(right or "")
    except Exception:
        return False
    mismatch = len(left) ^ len(right)
    compare_length = max(len(left), len(right))
    for index in range(compare_length):
        left_code = ord(left[index]) if index < len(left) else 0
        right_code = ord(right[index]) if index < len(right) else 0
        mismatch |= left_code ^ right_code
    return mismatch == 0


def request_is_authorized(request_data, expected_token):
    """Accept a token only from a parsed JSON object body."""
    if not isinstance(request_data, dict):
        return False
    return constant_time_equal(request_data.get("token"), expected_token)


def element_id_value(element_or_id):
    """Return an ElementId as a JSON-safe integer across Revit API versions."""
    candidate = getattr(element_or_id, "Id", element_or_id)
    for attribute in ("Value", "IntegerValue"):
        try:
            return int(getattr(candidate, attribute))
        except Exception:
            pass
    try:
        return int(candidate)
    except Exception:
        return None


def safe_text(value, default=""):
    try:
        if value is None:
            return default
        return str(value)
    except Exception:
        return default


def _definition_name(parameter):
    try:
        return safe_text(parameter.Definition.Name)
    except Exception:
        return ""


def parameter_value(parameter):
    """Read one Revit-like parameter as a bounded JSON scalar."""
    try:
        has_value = getattr(parameter, "HasValue", True) is not False
    except Exception:
        has_value = True

    # Varying Rebar dimensions can expose ``<varies>`` via display text while
    # reporting HasValue=False, so display accessors must run first.
    for reader in ("AsString", "AsValueString"):
        try:
            value = getattr(parameter, reader)()
            if value not in (None, ""):
                return safe_text(value)[:1000]
        except Exception:
            pass

    if not has_value:
        return ""

    storage = safe_text(getattr(parameter, "StorageType", "")).lower()
    try:
        if "integer" in storage:
            return int(parameter.AsInteger())
        if "double" in storage:
            return float(parameter.AsDouble())
        if "elementid" in storage:
            return element_id_value(parameter.AsElementId())
    except Exception:
        pass
    return ""


def _parameter_records(element, max_parameters=MAX_PARAMETERS):
    records = []
    seen = set()
    try:
        parameters = list(element.Parameters)
    except Exception:
        parameters = []
    for parameter in parameters:
        if len(records) >= max_parameters:
            break
        name = _definition_name(parameter)
        if not name or name in seen:
            continue
        seen.add(name)
        records.append({"name": name[:250], "value": parameter_value(parameter)})
    records.sort(key=lambda item: item["name"].lower())
    return records


def _category_name(element):
    try:
        return safe_text(element.Category.Name)
    except Exception:
        return ""


def _type_snapshot(doc, element):
    result = {"type_id": None, "type_name": "", "family_name": ""}
    try:
        type_id = element.GetTypeId()
        result["type_id"] = element_id_value(type_id)
        element_type = doc.GetElement(type_id) if doc is not None else None
    except Exception:
        element_type = None
    if element_type is not None:
        result["type_name"] = safe_text(getattr(element_type, "Name", ""))[:250]
        result["family_name"] = safe_text(
            getattr(element_type, "FamilyName", "")
        )[:250]
    return result


def element_snapshot(doc, element, include_parameters=True):
    """Serialize one element without geometry, file paths, or mutations."""
    result = {
        "element_id": element_id_value(element),
        "name": safe_text(getattr(element, "Name", ""))[:250],
        "category": _category_name(element)[:250],
        "unique_id": safe_text(getattr(element, "UniqueId", ""))[:250],
    }
    result.update(_type_snapshot(doc, element))
    if include_parameters:
        result["parameters"] = _parameter_records(element)
        result["parameters_truncated"] = _parameter_count(element) > MAX_PARAMETERS
    return result


def _parameter_count(element):
    try:
        return int(element.Parameters.Size)
    except Exception:
        try:
            return len(list(element.Parameters))
        except Exception:
            return 0


def document_snapshot(doc, uiapp=None):
    """Return non-sensitive active-document metadata (never its full path)."""
    application = getattr(uiapp, "Application", None)
    return {
        "title": safe_text(getattr(doc, "Title", ""))[:250] if doc else "",
        "is_family_document": bool(getattr(doc, "IsFamilyDocument", False)) if doc else False,
        "revit_version": safe_text(getattr(application, "VersionNumber", ""))[:50],
        "revit_build": safe_text(getattr(application, "VersionBuild", ""))[:100],
    }


def selection_snapshot(doc, selected_ids):
    """Return at most MAX_SELECTION lightweight selected-element records."""
    ids = list(selected_ids or [])
    items = []
    for selected_id in ids[:MAX_SELECTION]:
        try:
            element = doc.GetElement(selected_id)
        except Exception:
            element = None
        if element is not None:
            items.append(element_snapshot(doc, element, include_parameters=False))
    return {
        "count": len(ids),
        "returned": len(items),
        "truncated": len(ids) > MAX_SELECTION,
        "elements": items,
    }


def is_rebar_element(element):
    """Feature-detect Rebar using its category name without a DB dependency."""
    name = _category_name(element).strip().lower()
    return name in ("structural rebar", "rebar")


def rebar_snapshot(doc, element):
    """Return native Revit Rebar data; no fabricated bend/cutting formula."""
    result = element_snapshot(doc, element, include_parameters=True)
    named = {}
    # Do not derive key Rebar fields from the bounded diagnostic parameter
    # list: a family can have more than MAX_PARAMETERS entries.
    try:
        all_parameters = list(element.Parameters)
    except Exception:
        all_parameters = []
    for parameter in all_parameters:
        name = _definition_name(parameter)
        if name:
            named[name.lower()] = parameter_value(parameter)

    def first(*names):
        for name in names:
            value = named.get(name.lower(), "")
            if value not in (None, ""):
                return value
        return ""

    dimensions = {}
    for name in ("A", "B", "C", "C1", "C2", "D", "D1", "D2",
                 "E", "F", "G", "H", "J", "K", "O", "P", "Q", "R", "S", "V", "W"):
        value = first(name)
        if value not in (None, ""):
            dimensions[name] = value

    result["rebar"] = {
        "quantity": first("Quantity", "Bar Quantity"),
        "bar_length": first("Bar Length"),
        "total_bar_length": first("Total Bar Length", "Total Length"),
        "diameter": first("Bar Diameter", "Diameter"),
        "shape": first("Shape", "Rebar Shape"),
        "bar_mark": first("Bar Mark", "Schedule Mark", "Mark"),
        "host_mark": first("Host Mark"),
        "bend_diameter": first("Bend Diameter"),
        "start_hook": first("Hook At Start", "Start Hook"),
        "end_hook": first("Hook At End", "End Hook"),
        "dimensions": dimensions,
        "length_source": "Native Revit parameters; no custom bend deduction",
    }
    try:
        host_id = element.GetHostId()
        result["rebar"]["host_element_id"] = element_id_value(host_id)
    except Exception:
        result["rebar"]["host_element_id"] = None
    return result

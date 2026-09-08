# -*- coding: utf-8 -*-
"""Disabled pending Revit crash diagnosis: RCC BOQ Routes registration."""

from __future__ import absolute_import

import os
import sys

from pyrevit import routes


EXTENSION_DIRECTORY = os.path.dirname(__file__)
LIB_DIRECTORY = os.path.join(EXTENSION_DIRECTORY, "lib")
if LIB_DIRECTORY not in sys.path:
    sys.path.insert(0, LIB_DIRECTORY)

import rest_api


API = routes.API(rest_api.API_NAME)
TOKEN = rest_api.load_or_create_token()
NO_STORE_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
}


def _response(payload, status=200):
    return routes.make_response(payload, status=status, headers=NO_STORE_HEADERS)


def _authorized(request):
    return rest_api.request_is_authorized(getattr(request, "data", None), TOKEN)


def _reject_unauthorized():
    return _response({"ok": False, "error": "Unauthorized"}, status=401)


def _require_document(doc):
    if doc is None:
        return _response(
            {"ok": False, "error": "No active Revit document"}, status=409
        )
    return None


@API.route("/status", methods=["POST"])
def status(request):
    """Authenticate and report API health without entering Revit context."""
    if not _authorized(request):
        return _reject_unauthorized()
    return _response({
        "ok": True,
        "api": rest_api.API_NAME,
        "api_version": rest_api.API_VERSION,
        "extension_version": rest_api.EXTENSION_VERSION,
        "access": "local read-only",
    })


@API.route("/document", methods=["POST"])
def document(request, doc, uiapp):
    if not _authorized(request):
        return _reject_unauthorized()
    missing = _require_document(doc)
    if missing:
        return missing
    return _response({"ok": True, "document": rest_api.document_snapshot(doc, uiapp)})


@API.route("/selection", methods=["POST"])
def selection(request, doc, uidoc):
    if not _authorized(request):
        return _reject_unauthorized()
    missing = _require_document(doc)
    if missing:
        return missing
    try:
        selected_ids = uidoc.Selection.GetElementIds() if uidoc else []
    except Exception:
        selected_ids = []
    return _response({"ok": True, "selection": rest_api.selection_snapshot(doc, selected_ids)})


def _find_element(doc, element_id):
    try:
        # Document.GetElement has an integer overload on supported Revit builds.
        element = doc.GetElement(element_id)
        if element is not None:
            return element
    except Exception:
        pass
    try:
        from pyrevit import DB
        return doc.GetElement(DB.ElementId(int(element_id)))
    except Exception:
        return None


@API.route("/elements/<int:element_id>", methods=["POST"])
def element(request, doc, element_id):
    if not _authorized(request):
        return _reject_unauthorized()
    missing = _require_document(doc)
    if missing:
        return missing
    revit_element = _find_element(doc, element_id)
    if revit_element is None:
        return _response({"ok": False, "error": "Element not found"}, status=404)
    return _response({"ok": True, "element": rest_api.element_snapshot(doc, revit_element)})


@API.route("/rebar/<int:element_id>", methods=["POST"])
def rebar(request, doc, element_id):
    if not _authorized(request):
        return _reject_unauthorized()
    missing = _require_document(doc)
    if missing:
        return missing
    revit_element = _find_element(doc, element_id)
    if revit_element is None:
        return _response({"ok": False, "error": "Element not found"}, status=404)
    if not rest_api.is_rebar_element(revit_element):
        return _response({"ok": False, "error": "Element is not Structural Rebar"}, status=422)
    return _response({"ok": True, "element": rest_api.rebar_snapshot(doc, revit_element)})

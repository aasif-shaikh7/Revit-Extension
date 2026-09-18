# -*- coding: utf-8 -*-
"""Revit-bound model builder - turns an authoring spec into real elements.

Companion to Nudge.extension/lib/authoring_spec.py. Every rule that can be
decided without Revit lives in that pure module; this file holds only the
host calls, mirroring how the BOQ tool keeps its engines free of Revit
symbols (CLAUDE.md section 1, PROJECT_STRUCTURE.md section 9).

Run it through the pyRevit CLI, which supplies the Revit session:

    set RCC_AUTHORING_SPEC=C:\\path\\to\\spec.json
    pyrevit run scripts/revit_authoring.py --revit=2025

The spec path may also be passed through RCC_AUTHORING_SPEC as inline JSON.
Results (log lines, read-back rows, spec-versus-built findings) are written
as JSON to RCC_AUTHORING_RESULT so the caller can verify without a UI.

Nothing here touches an existing document: the builder always creates a new
project from a template and saves it to the path the spec names.
"""
import io
import json
import os
import sys
import traceback

# The pure engine lives in the extension lib folder, which is not on
# sys.path when this file runs as a standalone pyRevit CLI script.
# `pyrevit run` executes from its own temp working directory and does
# not always define __file__, so RCC_REPO_DIR is the reliable anchor and
# __file__ is only the convenience fallback.
_REPO_DIR = os.environ.get("RCC_REPO_DIR", "").strip()
if not _REPO_DIR:
    try:
        _REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    except NameError:
        _REPO_DIR = os.getcwd()
_LIB_DIR = os.path.join(_REPO_DIR, "Nudge.extension", "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import authoring_spec as SPEC  # noqa: E402

from pyrevit import HOST_APP, DB  # noqa: E402
from Autodesk.Revit.DB.Structure import StructuralType  # noqa: E402
from System.Collections.Generic import List  # noqa: E402


LIBRARY_ROOT = r"C:\ProgramData\Autodesk\RVT 2025\Libraries\English\US"

# Fallback family files, used only when the template carries no symbol for
# a kind. Each entry is (relative family path, BuiltInCategory name).
FAMILY_LIBRARY = {
    "column": (
        r"Structural Columns\Concrete\M_Concrete-Rectangular-Column.rfa",
        "OST_StructuralColumns",
    ),
    "beam": (
        r"Structural Framing\Concrete\M_Concrete-Rectangular Beam.rfa",
        "OST_StructuralFraming",
    ),
    "foundation": (
        r"Structural Foundations\M_Footing-Rectangular.rfa",
        "OST_StructuralFoundation",
    ),
}

CATEGORY_BY_KIND = {
    "column": "OST_StructuralColumns",
    "beam": "OST_StructuralFraming",
    "slab": "OST_Floors",
    "foundation": "OST_StructuralFoundation",
}

# Candidate type-parameter names per dimension, tried in order. Revit
# family authors name these differently; the builder reports which one it
# actually wrote rather than assuming any single name exists.
DIMENSION_PARAMETERS = {
    "width_mm": ("b", "Width", "B"),
    "depth_mm": ("h", "Height", "Depth", "H"),
    "length_mm": ("Length",),
    "size_x_mm": ("Width", "b"),
    "size_y_mm": ("Length", "h"),
    "thickness_mm": ("Thickness", "Foundation Thickness"),
}

_log_lines = []


def log(message):
    """Record one builder step for the JSON result and the console."""
    text = u"{0}".format(message)
    _log_lines.append(text)
    print(text)


def element_name(element):
    """Read an element's name through the API that works in every year."""
    try:
        return DB.Element.Name.GetValue(element)
    except Exception:
        try:
            return element.Name
        except Exception:
            return ""


def load_spec():
    """Read the authoring spec from RCC_AUTHORING_SPEC (path or inline)."""
    raw = os.environ.get("RCC_AUTHORING_SPEC", "").strip()
    if not raw:
        raise ValueError("RCC_AUTHORING_SPEC is not set")
    if os.path.isfile(raw):
        handle = io.open(raw, "r", encoding="utf-8")
        try:
            return json.loads(handle.read())
        finally:
            handle.close()
    return json.loads(raw)


def ensure_levels(doc, spec):
    """Return {level name: Level}, creating any level the spec declares."""
    existing = {}
    for level in DB.FilteredElementCollector(doc).OfClass(DB.Level).ToElements():
        existing[element_name(level)] = level
    log(u"Levels in template: {0}".format(u", ".join(sorted(existing)) or u"(none)"))

    for declared in spec.get("levels", []):
        name = declared["name"]
        if name in existing:
            continue
        level = DB.Level.Create(doc, SPEC.mm_to_feet(declared["elevation_mm"]))
        try:
            level.Name = name
        except Exception:
            log(u"  could not rename new level to {0}".format(name))
        existing[element_name(level)] = level
        log(u"  created level {0} at {1} mm".format(
            name, declared["elevation_mm"]))

    return existing


def set_type_dimension(symbol, field, millimeters):
    """Write one dimension onto a type, returning the parameter name used.

    Returns None when the family exposes none of the candidate names, so
    the caller logs a real miss instead of assuming the size was applied.
    """
    for parameter_name in DIMENSION_PARAMETERS.get(field, ()):
        parameter = symbol.LookupParameter(parameter_name)
        if parameter is None or parameter.IsReadOnly:
            continue
        try:
            if parameter.Set(SPEC.mm_to_feet(millimeters)):
                return parameter_name
        except Exception:
            continue
    return None


def find_symbol(doc, category_name, family_hint=None):
    """Return one FamilySymbol in a category, preferring a family hint."""
    category = getattr(DB.BuiltInCategory, category_name)
    symbols = (DB.FilteredElementCollector(doc)
               .OfCategory(category)
               .OfClass(DB.FamilySymbol)
               .ToElements())
    fallback = None
    for symbol in symbols:
        family = symbol.FamilyName or ""
        if fallback is None:
            fallback = symbol
        if family_hint and family_hint.lower() in family.lower():
            return symbol
    return fallback


def symbol_of_family(doc, family_name):
    """Return the first FamilySymbol belonging to a named family."""
    for symbol in (DB.FilteredElementCollector(doc)
                   .OfClass(DB.FamilySymbol).ToElements()):
        if (symbol.FamilyName or "") == family_name:
            return symbol
    return None


def load_family_symbol(doc, path):
    """Load one family file and return one of its symbols, or None.

    Document.LoadFamily has both a bool overload and an out-parameter
    overload, and IronPython resolves to the bool one here. Rather than
    depend on which overload binds, the family is looked up by name
    afterwards - the file's basename is the family name Revit registers.
    """
    if not os.path.isfile(path):
        log(u"  family file not found: {0}".format(path))
        return None

    family_name = os.path.splitext(os.path.basename(path))[0]
    log(u"  loading family: {0}".format(path))

    existing = symbol_of_family(doc, family_name)
    if existing is not None:
        log(u"  family '{0}' already present".format(family_name))
        return existing

    doc.LoadFamily(path)
    symbol = symbol_of_family(doc, family_name)
    log(u"  family '{0}' loaded: {1}".format(
        family_name, symbol is not None))
    return symbol


def ensure_base_symbol(doc, kind, family_path=None):
    """Return a usable base symbol for a kind, loading a family if needed.

    An explicit family_path wins over whatever the template carries: the
    family name is itself identity the BOQ classifier reads, so a caller
    that cares about it must be able to pin the family.
    """
    category_name = CATEGORY_BY_KIND[kind]

    if family_path:
        symbol = load_family_symbol(doc, family_path)
        if symbol is None:
            raise ValueError(
                "Could not load requested family: {0}".format(family_path))
        return symbol

    symbol = find_symbol(doc, category_name, "concrete")
    if symbol is None:
        symbol = find_symbol(doc, category_name)

    if symbol is None and kind in FAMILY_LIBRARY:
        relative, _category = FAMILY_LIBRARY[kind]
        path = os.path.join(LIBRARY_ROOT, relative)
        log(u"  no {0} symbol in template".format(kind))
        symbol = load_family_symbol(doc, path)

    if symbol is None:
        raise ValueError("No symbol available for kind '{0}'".format(kind))
    return symbol


def build_typed_symbol(doc, kind, element):
    """Duplicate a base symbol into a type named after the element spec.

    The type name is what the BOQ classifier reads, so the spec's name
    becomes the model's identity rather than a generic library name.
    """
    base = ensure_base_symbol(doc, kind, element.get("family_path"))
    type_name = element.get("type_name") or element.get("name")

    symbol = base
    try:
        symbol = base.Duplicate(type_name)
    except Exception:
        log(u"  could not duplicate {0} as '{1}'; using it as-is".format(
            element_name(base), type_name))

    applied = []
    for field in SPEC.REQUIRED_DIMENSIONS.get(kind, ()):
        if field == "length_mm":
            continue  # beam length comes from its placement curve
        value = element.get(field)
        if not value:
            continue
        used = set_type_dimension(symbol, field, value)
        applied.append(u"{0}->{1}".format(
            field, used if used else u"NOT APPLIED"))

    if not symbol.IsActive:
        symbol.Activate()
        doc.Regenerate()

    log(u"  type '{0}' from family '{1}' [{2}]".format(
        element_name(symbol), symbol.FamilyName, u", ".join(applied) or u"no dims"))
    return symbol


def stamp_identity(instance, element):
    """Write Mark and Comments so identity-driven routing can be tested."""
    pairs = (
        (DB.BuiltInParameter.ALL_MODEL_MARK, element.get("mark")),
        (DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS,
         element.get("comments")),
    )
    for built_in, value in pairs:
        if not value:
            continue
        parameter = instance.get_Parameter(built_in)
        if parameter is not None and not parameter.IsReadOnly:
            parameter.Set(value)


def create_column(doc, spec, element, levels):
    """Place one structural column between its declared levels."""
    symbol = build_typed_symbol(doc, "column", element)
    base = levels[element["base_level"]]
    point = DB.XYZ(SPEC.mm_to_feet(element["x_mm"]),
                   SPEC.mm_to_feet(element["y_mm"]),
                   base.Elevation)
    instance = doc.Create.NewFamilyInstance(
        point, symbol, base, StructuralType.Column)

    top = levels.get(element.get("top_level"))
    if top is not None:
        parameter = instance.get_Parameter(
            DB.BuiltInParameter.FAMILY_TOP_LEVEL_PARAM)
        if parameter is not None and not parameter.IsReadOnly:
            parameter.Set(top.Id)
    return instance


def create_beam(doc, spec, element, levels):
    """Place one structural beam along its declared length."""
    symbol = build_typed_symbol(doc, "beam", element)
    base = levels[element["base_level"]]
    z = base.Elevation
    start = DB.XYZ(SPEC.mm_to_feet(element["x_mm"]),
                   SPEC.mm_to_feet(element["y_mm"]), z)
    end = DB.XYZ(SPEC.mm_to_feet(element["x_mm"] + element["length_mm"]),
                 SPEC.mm_to_feet(element["y_mm"]), z)
    line = DB.Line.CreateBound(start, end)
    return doc.Create.NewFamilyInstance(
        line, symbol, base, StructuralType.Beam)


def create_foundation(doc, spec, element, levels):
    """Place one structural foundation footing at its declared level."""
    symbol = build_typed_symbol(doc, "foundation", element)
    base = levels[element["base_level"]]
    point = DB.XYZ(SPEC.mm_to_feet(element["x_mm"]),
                   SPEC.mm_to_feet(element["y_mm"]),
                   base.Elevation)
    return doc.Create.NewFamilyInstance(
        point, symbol, base, StructuralType.Footing)


def build_floor_type(doc, element):
    """Duplicate a floor type named after the spec and set its thickness."""
    base = None
    for floor_type in (DB.FilteredElementCollector(doc)
                       .OfClass(DB.FloorType).ToElements()):
        try:
            if floor_type.GetCompoundStructure() is not None:
                base = floor_type
                break
        except Exception:
            continue
    if base is None:
        raise ValueError("No floor type with a compound structure available")

    type_name = element.get("type_name") or element.get("name")
    floor_type = base
    try:
        floor_type = base.Duplicate(type_name)
    except Exception:
        log(u"  could not duplicate floor type as '{0}'".format(type_name))

    thickness = element.get("thickness_mm")
    if thickness:
        try:
            structure = floor_type.GetCompoundStructure()
            structure.SetLayerWidth(0, SPEC.mm_to_feet(thickness))
            floor_type.SetCompoundStructure(structure)
        except Exception:
            log(u"  could not set thickness {0} mm on '{1}'".format(
                thickness, type_name))

    log(u"  floor type '{0}'".format(element_name(floor_type)))
    return floor_type


def create_slab(doc, spec, element, levels):
    """Create one rectangular floor at its declared level."""
    floor_type = build_floor_type(doc, element)
    base = levels[element["base_level"]]

    x0 = SPEC.mm_to_feet(element["x_mm"])
    y0 = SPEC.mm_to_feet(element["y_mm"])
    x1 = SPEC.mm_to_feet(element["x_mm"] + element["size_x_mm"])
    y1 = SPEC.mm_to_feet(element["y_mm"] + element["size_y_mm"])
    corners = [DB.XYZ(x0, y0, 0.0), DB.XYZ(x1, y0, 0.0),
               DB.XYZ(x1, y1, 0.0), DB.XYZ(x0, y1, 0.0)]

    loop = DB.CurveLoop()
    for index in range(4):
        loop.Append(DB.Line.CreateBound(
            corners[index], corners[(index + 1) % 4]))

    loops = List[DB.CurveLoop]()
    loops.Add(loop)
    return DB.Floor.Create(doc, loops, floor_type.Id, base.Id)


BUILDERS = {
    "column": create_column,
    "beam": create_beam,
    "slab": create_slab,
    "foundation": create_foundation,
}


def read_back(doc):
    """Read every built structural element as {name, kind, volume_m3}."""
    rows = []
    for kind, category_name in sorted(CATEGORY_BY_KIND.items()):
        category = getattr(DB.BuiltInCategory, category_name)
        for instance in (DB.FilteredElementCollector(doc)
                         .OfCategory(category)
                         .WhereElementIsNotElementType()
                         .ToElements()):
            parameter = instance.get_Parameter(
                DB.BuiltInParameter.HOST_VOLUME_COMPUTED)
            volume = SPEC.cubic_feet_to_cubic_meters(
                parameter.AsDouble()) if parameter else None
            type_element = doc.GetElement(instance.GetTypeId())
            rows.append({
                "name": element_name(type_element) if type_element else "",
                "kind": kind,
                "element_id": instance.Id.IntegerValue,
                "volume_m3": volume,
            })
    return rows


def build_model(raw_spec):
    """Normalize, validate, build, read back and save. Returns a result."""
    spec = SPEC.normalize_model_spec(raw_spec)
    findings = SPEC.validate_model_spec(spec)
    if findings:
        return {"ok": False, "stage": "validate", "spec_findings": findings,
                "log": _log_lines}

    template = spec["template"]
    if not template or not os.path.isfile(template):
        return {"ok": False, "stage": "template",
                "spec_findings": ["Template not found: {0}".format(template)],
                "log": _log_lines}

    application = HOST_APP.app
    log(u"Revit {0} build {1}".format(
        application.VersionNumber, application.VersionBuild))
    log(u"Template: {0}".format(template))

    doc = application.NewProjectDocument(template)
    log(u"New project document created")

    transaction = DB.Transaction(doc, "Authoring: build declared model")
    transaction.Start()
    try:
        levels = ensure_levels(doc, spec)
        for element in spec["elements"]:
            log(u"Building {0} '{1}'".format(element["kind"], element["name"]))
            instance = BUILDERS[element["kind"]](doc, spec, element, levels)
            stamp_identity(instance, element)
            log(u"  created id={0}".format(instance.Id))
        transaction.Commit()
    except Exception:
        transaction.RollBack()
        log(u"Transaction rolled back")
        raise

    rows = read_back(doc)
    build_findings = SPEC.compare_actual_to_expected(spec, rows)

    output_path = spec["output_path"]
    options = DB.SaveAsOptions()
    options.OverwriteExistingFile = True
    doc.SaveAs(output_path, options)
    doc.Close(False)
    log(u"Saved: {0}".format(output_path))

    return {
        "ok": not build_findings,
        "stage": "built",
        "output_path": output_path,
        "expected": SPEC.summarize_expected_quantities(spec),
        "built_rows": rows,
        "build_findings": build_findings,
        "log": _log_lines,
    }


def main():
    """Entry point for `pyrevit run`; always writes a JSON result."""
    result_path = os.environ.get("RCC_AUTHORING_RESULT", "").strip()
    try:
        result = build_model(load_spec())
    except Exception:
        result = {"ok": False, "stage": "exception",
                  "traceback": traceback.format_exc(), "log": _log_lines}
        print(result["traceback"])

    if result_path:
        handle = io.open(result_path, "w", encoding="utf-8")
        try:
            handle.write(json.dumps(result, indent=2, ensure_ascii=False))
        finally:
            handle.close()


main()

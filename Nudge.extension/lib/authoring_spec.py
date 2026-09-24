# -*- coding: utf-8 -*-
"""Authoring spec engine - declarative structural model definitions.

Pure Python by design (PROJECT_STRUCTURE.md section 9, CLAUDE.md section 1).
This module holds the *declaration* of a structural model to build - element
kinds, dimensions, levels, placement, identity text - together with the
quantities those declarations imply. It never imports a Revit or pyRevit
symbol, so the harness can exercise every rule below outside Revit.

The Revit-bound builder that turns a normalized spec into real elements
lives in scripts/revit_authoring.py and is driven through `pyrevit run`.
The split mirrors the existing engines: pure rules here, host calls there.

First consumer: live-QA fixture generation. todo-list.md P10-03 needs a
model whose Floor/Foundation identities carry neither a known code nor
slab/foundation wording, which no production model has produced so far.
"""


MM_PER_FOOT = 304.8

CUBIC_FEET_TO_CUBIC_METERS = 0.028316846592

ELEMENT_KINDS = ("column", "beam", "slab", "foundation")

# Kinds whose volume comes from a cross-section carried along a length,
# versus kinds whose volume comes from a footprint times a thickness.
SECTION_KINDS = ("column", "beam")
FOOTPRINT_KINDS = ("slab", "foundation")

DEFAULT_LEVELS = (
    {"name": "Level 1", "elevation_mm": 0.0},
    {"name": "Level 2", "elevation_mm": 3000.0},
)

KIND_DEFAULTS = {
    "column": {"width_mm": 300.0, "depth_mm": 450.0},
    "beam": {"width_mm": 230.0, "depth_mm": 450.0, "length_mm": 4000.0},
    "slab": {"size_x_mm": 4000.0, "size_y_mm": 3000.0, "thickness_mm": 150.0},
    "foundation": {"size_x_mm": 1500.0, "size_y_mm": 1500.0, "thickness_mm": 450.0},
}

# Dimensions each kind must end up with a positive value for.
REQUIRED_DIMENSIONS = {
    "column": ("width_mm", "depth_mm"),
    "beam": ("width_mm", "depth_mm", "length_mm"),
    "slab": ("size_x_mm", "size_y_mm", "thickness_mm"),
    "foundation": ("size_x_mm", "size_y_mm", "thickness_mm"),
}

DEFAULT_TOLERANCE_M3 = 0.0005


def mm_to_feet(millimeters):
    """Convert a millimeter value into Revit internal feet."""
    return float(millimeters) / MM_PER_FOOT


def feet_to_mm(feet):
    """Convert Revit internal feet into millimeters."""
    return float(feet) * MM_PER_FOOT


def cubic_feet_to_cubic_meters(cubic_feet):
    """Convert a Revit internal volume into cubic meters."""
    return float(cubic_feet) * CUBIC_FEET_TO_CUBIC_METERS


def _positive_float(value, fallback=None):
    """Return value as a positive float, else fallback (None when invalid)."""
    try:
        number = float(value)
    except Exception:
        return fallback
    if number <= 0.0:
        return fallback
    return number


def _clean_text(value, fallback=""):
    """Return a stripped text value, else the fallback."""
    if value is None:
        return fallback
    try:
        text = u"{0}".format(value).strip()
    except Exception:
        return fallback
    return text if text else fallback


def _coordinate(value):
    """Return a placement coordinate as a float; non-numeric becomes 0.0."""
    try:
        return float(value)
    except Exception:
        return 0.0


def normalize_level_spec(raw, index=0):
    """Normalize one level declaration into {name, elevation_mm}."""
    raw = raw if isinstance(raw, dict) else {}
    name = _clean_text(raw.get("name"), "Level {0}".format(index + 1))
    try:
        elevation = float(raw.get("elevation_mm", 0.0))
    except Exception:
        elevation = 0.0
    return {"name": name, "elevation_mm": elevation}


def normalize_element_spec(raw, index=0):
    """Normalize one element declaration, filling kind defaults.

    Unknown kinds are preserved rather than dropped so validation can
    report them by name instead of silently building a smaller model.
    """
    raw = raw if isinstance(raw, dict) else {}
    kind = _clean_text(raw.get("kind")).lower()

    spec = {
        "kind": kind,
        "name": _clean_text(
            raw.get("name"),
            "{0}-{1}".format(kind or "element", index + 1)),
        "mark": _clean_text(raw.get("mark")),
        "comments": _clean_text(raw.get("comments")),
        "type_name": _clean_text(raw.get("type_name")),
        # Optional: force a specific family file instead of whatever the
        # template already carries. Needed when the family *name* itself
        # is part of what a test is about - the BOQ classifier reads it.
        "family_path": _clean_text(raw.get("family_path")),
        "base_level": _clean_text(
            raw.get("base_level"), DEFAULT_LEVELS[0]["name"]),
        "top_level": _clean_text(raw.get("top_level")),
        "x_mm": _coordinate(raw.get("x_mm")),
        "y_mm": _coordinate(raw.get("y_mm")),
    }

    # An absent dimension takes the kind default. A dimension that was
    # declared but is not a positive number is kept as None so validation
    # reports it, rather than silently standing in a default the caller
    # never asked for.
    defaults = KIND_DEFAULTS.get(kind, {})
    for field in sorted(defaults):
        if field in raw:
            spec[field] = _positive_float(raw.get(field), None)
        else:
            spec[field] = defaults[field]

    # A dimension supplied for a kind that does not define it is kept so
    # validation can flag the mismatch instead of quietly ignoring it.
    for field in sorted(raw):
        if field.endswith("_mm") and field not in spec:
            spec[field] = _positive_float(raw.get(field), None)

    return spec


def normalize_model_spec(raw):
    """Normalize a whole model declaration into a builder-ready spec."""
    raw = raw if isinstance(raw, dict) else {}

    raw_levels = raw.get("levels")
    if not isinstance(raw_levels, (list, tuple)) or not raw_levels:
        raw_levels = [dict(item) for item in DEFAULT_LEVELS]
    levels = [normalize_level_spec(item, i) for i, item in enumerate(raw_levels)]
    levels.sort(key=lambda item: item["elevation_mm"])

    raw_elements = raw.get("elements")
    if not isinstance(raw_elements, (list, tuple)):
        raw_elements = []
    elements = [normalize_element_spec(item, i)
                for i, item in enumerate(raw_elements)]

    return {
        "name": _clean_text(raw.get("name"), "Authored model"),
        "template": _clean_text(raw.get("template")),
        "output_path": _clean_text(raw.get("output_path")),
        "levels": levels,
        "elements": elements,
    }


def level_elevation_mm(spec, level_name):
    """Return the elevation of a named level, or None when absent."""
    for level in spec.get("levels", []):
        if level["name"] == level_name:
            return level["elevation_mm"]
    return None


def element_height_mm(spec, element):
    """Return the vertical extent a column spec spans between its levels.

    Returns None when either level reference cannot be resolved, so the
    caller reports a missing level instead of computing a wrong volume.
    """
    base = level_elevation_mm(spec, element.get("base_level"))
    top_name = element.get("top_level")
    if base is None or not top_name:
        return None
    top = level_elevation_mm(spec, top_name)
    if top is None:
        return None
    return top - base


def expected_element_volume_m3(spec, element):
    """Return the concrete volume one element declaration implies.

    Returns None when the declaration is incomplete; validate_model_spec
    reports why, and the caller never compares against a guessed number.
    """
    kind = element.get("kind")

    if kind == "column":
        height = element_height_mm(spec, element)
        if height is None or height <= 0.0:
            return None
        dims = (element.get("width_mm"), element.get("depth_mm"), height)
    elif kind == "beam":
        dims = (element.get("width_mm"), element.get("depth_mm"),
                element.get("length_mm"))
    elif kind in FOOTPRINT_KINDS:
        dims = (element.get("size_x_mm"), element.get("size_y_mm"),
                element.get("thickness_mm"))
    else:
        return None

    volume_mm3 = 1.0
    for value in dims:
        if not value or value <= 0.0:
            return None
        volume_mm3 *= float(value)
    return volume_mm3 / 1.0e9


def validate_model_spec(spec):
    """Return a list of findings describing why a spec cannot be built.

    An empty list means every declaration resolved. Findings are plain
    text so the runner can print them and the harness can assert on them.
    """
    findings = []

    levels = spec.get("levels", [])
    if not levels:
        findings.append("No levels declared")

    level_names = [level["name"] for level in levels]
    for name in sorted(set(level_names)):
        if level_names.count(name) > 1:
            findings.append("Duplicate level name: {0}".format(name))

    elements = spec.get("elements", [])
    if not elements:
        findings.append("No elements declared")

    element_names = [element.get("name") for element in elements]
    for name in sorted(set(element_names)):
        if element_names.count(name) > 1:
            findings.append("Duplicate element name: {0}".format(name))

    for element in elements:
        label = element.get("name")
        kind = element.get("kind")

        if kind not in ELEMENT_KINDS:
            findings.append("{0}: unknown kind '{1}'".format(label, kind))
            continue

        for field in REQUIRED_DIMENSIONS[kind]:
            if not element.get(field):
                findings.append(
                    "{0}: missing or non-positive {1}".format(label, field))

        base = element.get("base_level")
        if base not in level_names:
            findings.append(
                "{0}: base level '{1}' not declared".format(label, base))

        top = element.get("top_level")
        if kind == "column":
            if not top:
                findings.append("{0}: column needs a top_level".format(label))
            elif top not in level_names:
                findings.append(
                    "{0}: top level '{1}' not declared".format(label, top))
            else:
                height = element_height_mm(spec, element)
                if height is not None and height <= 0.0:
                    findings.append(
                        "{0}: top level is not above base level".format(label))
        elif top and top not in level_names:
            findings.append(
                "{0}: top level '{1}' not declared".format(label, top))

    return findings


def summarize_expected_quantities(spec):
    """Return {kind: {'count': n, 'volume_m3': v}} plus a 'total' entry."""
    summary = {}
    total_count = 0
    total_volume = 0.0

    for element in spec.get("elements", []):
        kind = element.get("kind")
        if kind not in ELEMENT_KINDS:
            continue
        volume = expected_element_volume_m3(spec, element)
        bucket = summary.setdefault(kind, {"count": 0, "volume_m3": 0.0})
        bucket["count"] += 1
        total_count += 1
        if volume is not None:
            bucket["volume_m3"] += volume
            total_volume += volume

    summary["total"] = {"count": total_count, "volume_m3": total_volume}
    return summary


def compare_actual_to_expected(spec, actual_rows,
                               tolerance_m3=DEFAULT_TOLERANCE_M3):
    """Compare what Revit built against what the spec declared.

    actual_rows is a list of {'name': ..., 'volume_m3': ...} read back
    from the built document. Returns a list of findings; an empty list
    means every declared element was created at its declared volume.
    """
    findings = []

    actual_by_name = {}
    for row in actual_rows or []:
        name = _clean_text((row or {}).get("name"))
        if not name:
            findings.append("Built element with no readable name")
            continue
        if name in actual_by_name:
            findings.append("Built element name appears twice: {0}".format(name))
            continue
        actual_by_name[name] = row

    for element in spec.get("elements", []):
        label = element.get("name")
        expected = expected_element_volume_m3(spec, element)

        if label not in actual_by_name:
            findings.append("{0}: declared but not built".format(label))
            continue

        if expected is None:
            findings.append(
                "{0}: built, but the spec implies no checkable volume".format(
                    label))
            continue

        try:
            actual = float(actual_by_name[label].get("volume_m3"))
        except Exception:
            findings.append("{0}: built volume is not readable".format(label))
            continue

        if abs(actual - expected) > tolerance_m3:
            findings.append(
                "{0}: volume {1:.4f} m3 differs from declared {2:.4f} m3".format(
                    label, actual, expected))

    declared_names = set(
        element.get("name") for element in spec.get("elements", []))
    for name in sorted(actual_by_name):
        if name not in declared_names:
            findings.append("{0}: built but never declared".format(name))

    return findings

# -*- coding: utf-8 -*-
"""Model change engine - P15: which elements changed between two issues.

P14's BOQ Revision sheet says how much each BOQ item moved - "M30 beams
381 -> 395 m3". It cannot say which beam. This module keeps one small
record per element in every revision snapshot and compares them, so the
workbook can list the elements behind the movement: added, deleted, or
modified - and what about them changed.

What counts as a change (decided 2026-09-25): the element's concrete,
shuttering or steel moved by 0.005 or more (m3, m2, kg - the same
tolerance the revision sheet uses), or its grade, level or family and
type changed. Other parameters - Mark, Comments - do not make an element
"modified": they do not move the BOQ.

Steel is kept per element: every rebar row adds its weight to the
element that hosts it, so a beam reads "steel 45 -> 52 kg" rather than
listing thousands of bars. Rebar with no host, or a host outside the
five concrete categories, is kept in one record per model, so its weight
is never lost from the totals.

An element is identified by its Revit element ID within its category. An
element deleted and drawn again gets a new ID: it shows as one Deleted
and one Added, which is what the model now actually contains.

Pure Python (re only): no Revit symbols. Order always comes from lists,
never from a dict, because the button runs on IronPython 2.7, where a
dict does not keep insertion order.
"""
import re

MODEL_CHANGES_SHEET_NAME = "Model Changes"

MODEL_CHANGES_HEADERS = (
    "Change", "Category", "Element ID", "Family and Type", "Level",
    "What changed", "Concrete Difference (m3)", "Shuttering Difference (m2)",
    "Steel Difference (kg)",
)

# The same threshold as the revision sheet: below it a difference is
# rounding, not a change.
CHANGE_TOLERANCE = 0.005

CHANGE_DELETED = "Deleted"
CHANGE_ADDED = "Added"
CHANGE_MODIFIED = "Modified"

# Categories in Detailed BOQ order; rebar with no concrete host last.
ELEMENT_CATEGORIES = ("Beam", "Column", "Structure Wall", "Slab", "Foundation")
UNHOSTED_CATEGORY = "Rebar"
UNHOSTED_ID = "(no host)"

_CHANGE_ORDER = (CHANGE_DELETED, CHANGE_ADDED, CHANGE_MODIFIED)


def _number(value):
    """The float in a cell, or None. None never reaches float(): IronPython
    answers float(None) with SystemError, not TypeError."""
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _text(value):
    try:
        return u"{0}".format(value if value is not None else u"").strip()
    except Exception:
        return u""


def _rounded(value):
    return round(value, 4) if value is not None else None


def build_element_records(data_result, rebar_rows=None, element_types=None):
    """One record per concrete element, plus unhosted steel - a list.

    `element_types` maps an element ID to its "Family: Type" text; script.py
    collects it while reading the elements, without adding a workbook
    column. Records come out in category order, then in row order.
    """
    data = data_result if isinstance(data_result, dict) else {}
    types = element_types if isinstance(element_types, dict) else {}

    records = []
    by_id = {}
    for category in ELEMENT_CATEGORIES:
        for row in data.get(category) or []:
            try:
                element_id = _text(row.get("Element ID", ""))
            except AttributeError:
                continue
            if not element_id or element_id == u"N/A":
                continue
            record = {
                "id": element_id,
                "category": category,
                "level": _text(row.get("Level", "")),
                "grade": _text(row.get("Grade", "")),
                "type": _text(types.get(element_id, "")),
                "concrete": _rounded(_number(row.get("Qty: Volume (m3)"))),
                "shuttering": _rounded(_number(row.get("Qty: Shuttering (m2)"))),
                "steel": None,
            }
            records.append(record)
            by_id[element_id] = record

    unhosted = 0.0
    found_unhosted = False
    for row in rebar_rows or []:
        try:
            weight = _number(row.get("Rebar: Total Weight (kg)"))
            host = _text(row.get("Rebar: Host Element ID", ""))
        except AttributeError:
            continue
        if weight is None:
            continue
        record = by_id.get(host) if host else None
        if record is None:
            unhosted += weight
            found_unhosted = True
            continue
        record["steel"] = (record["steel"] or 0.0) + weight

    for record in records:
        record["steel"] = _rounded(record["steel"])
    if found_unhosted:
        records.append({
            "id": UNHOSTED_ID, "category": UNHOSTED_CATEGORY, "level": u"",
            "grade": u"", "type": u"Rebar without a concrete host",
            "concrete": None, "shuttering": None, "steel": _rounded(unhosted),
        })
    return records


def _record_list(snapshot):
    """The element records of a snapshot, or None when it has none."""
    if not isinstance(snapshot, dict):
        return None
    records = snapshot.get("elements")
    if not isinstance(records, list):
        return None
    return [record for record in records if isinstance(record, dict)]


def has_element_records(snapshot):
    """True when a snapshot carries element records (format 2 and later)."""
    return _record_list(snapshot) is not None


def _key(record):
    return (_text(record.get("category", "")), _text(record.get("id", "")))


def _amount(record, field):
    return _number(record.get(field)) or 0.0


def _describe(before, after):
    """The changes between two records of one element, in words."""
    parts = []
    for field, label, unit in (("concrete", u"Concrete", u"m3"),
                               ("shuttering", u"Shuttering", u"m2"),
                               ("steel", u"Steel", u"kg")):
        old, new = _amount(before, field), _amount(after, field)
        if abs(new - old) >= CHANGE_TOLERANCE:
            parts.append(u"{0} {1:.3f} -> {2:.3f} {3}".format(label, old, new, unit))
    for field, label in (("grade", u"Grade"), ("level", u"Level"),
                         ("type", u"Type")):
        old, new = _text(before.get(field)), _text(after.get(field))
        if old != new:
            parts.append(u"{0} {1} -> {2}".format(
                label, old or u"(none)", new or u"(none)"))
    return parts


def _id_sort(value):
    text = _text(value)
    return (0, int(text), u"") if text.isdigit() else (1, 0, text)


def compare_elements(previous, current):
    """Every element that was added, deleted or modified - a sorted list.

    Each change carries the element's identity, what changed in words, and
    the three differences (current minus previous; a deleted element
    counts negative). Unchanged elements are left out.
    """
    old_records = _record_list(previous) or []
    new_records = _record_list(current) or []
    old_by_key = dict((_key(r), r) for r in old_records)
    new_by_key = dict((_key(r), r) for r in new_records)

    changes = []
    for record in old_records:
        if _key(record) not in new_by_key:
            changes.append((CHANGE_DELETED, record, None))
    for record in new_records:
        before = old_by_key.get(_key(record))
        if before is None:
            changes.append((CHANGE_ADDED, None, record))
        elif _describe(before, record):
            changes.append((CHANGE_MODIFIED, before, record))

    rank = list(ELEMENT_CATEGORIES) + [UNHOSTED_CATEGORY]

    def sort_key(change):
        kind, before, after = change
        record = after or before
        category = _text(record.get("category"))
        return (rank.index(category) if category in rank else len(rank),
                _CHANGE_ORDER.index(kind),
                _text(record.get("level")),
                _id_sort(record.get("id")))

    result = []
    for kind, before, after in sorted(changes, key=sort_key):
        record = after or before
        empty = {}
        old = before or empty
        new = after or empty
        if kind == CHANGE_MODIFIED:
            what = u"; ".join(_describe(old, new))
        elif kind == CHANGE_ADDED:
            what = u"New element"
        else:
            what = u"No longer in the model"
        result.append({
            "change": kind,
            "category": _text(record.get("category")),
            "id": _text(record.get("id")),
            "type": _text(new.get("type") or old.get("type")),
            "level": _text(new.get("level") or old.get("level")),
            "what": what,
            "concrete": round(_amount(new, "concrete") - _amount(old, "concrete"), 4),
            "shuttering": round(_amount(new, "shuttering") - _amount(old, "shuttering"), 4),
            "steel": round(_amount(new, "steel") - _amount(old, "steel"), 4),
        })
    return result


def change_counts(previous, current):
    """(deleted, added, modified) - the one-line story of the change."""
    changes = compare_elements(previous, current)
    return tuple(sum(1 for c in changes if c["change"] == kind)
                 for kind in _CHANGE_ORDER)


def elements_unchanged(previous, current):
    """True when no element was added, deleted or modified.

    A snapshot without element records (written before v1.40.0) cannot
    vouch for its elements, so against one that has them the answer is
    False: the first export after the upgrade files a revision that does.
    Two snapshots that both lack records are judged on their items alone
    by the caller.
    """
    if has_element_records(previous) != has_element_records(current):
        return False
    if not has_element_records(current):
        return True
    return not compare_elements(previous, current)


def build_model_changes_table(previous, current, row_offset=0):
    """The Model Changes sheet: one row per changed element, and a TOTAL.

    The three difference columns each hold one unit (m3, m2, kg), so their
    TOTAL is meaningful - it is the element-level story behind the BOQ
    Revision sheet's movement. `row_offset` is how far below its plain
    position each row lands (the site workbook's title bands). With
    nothing changed, or no element records on either side, the header
    comes back alone and the caller writes no sheet.
    """
    table = [list(MODEL_CHANGES_HEADERS)]
    if not (has_element_records(previous) and has_element_records(current)):
        return table
    changes = compare_elements(previous, current)
    if not changes:
        return table
    first = len(table) + 1 + row_offset
    for change in changes:
        table.append([
            change["change"], change["category"], change["id"], change["type"],
            change["level"], change["what"], change["concrete"],
            change["shuttering"], change["steel"],
        ])
    last = len(table) + row_offset
    total = [u"TOTAL", u"", u"", u"", u"", u""]
    for column in ("G", "H", "I"):
        total.append(("FORMULA", "SUM({0}{1}:{0}{2})".format(column, first, last)))
    table.append(total)
    return table


def build_model_changes_sheet(previous, current, row_offset=0, meta_lines=None):
    """The table with heading lines above it (the classic workbook).

    `meta_lines` are the revision_engine lines naming the two issues. They
    push the header down, and the TOTAL formulas are built knowing that.
    """
    meta = list(meta_lines or [])
    table = build_model_changes_table(previous, current, row_offset + len(meta))
    if len(table) <= 1:
        return table
    width = len(MODEL_CHANGES_HEADERS)
    return [[line] + [u""] * (width - 1) for line in meta] + table

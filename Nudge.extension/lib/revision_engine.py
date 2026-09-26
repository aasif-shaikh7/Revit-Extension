# -*- coding: utf-8 -*-
"""Revision engine - P14: what changed between two BOQ revisions.

A BOQ is never issued once. The drawing changes, a footing grows, a beam
is deleted, and the next issue has to say what moved - Rev 00 against
Rev 01, quantity by quantity, with the difference and the percentage
beside it. Without that sheet the reader has to diff two workbooks by
eye, which on a real project nobody does.

The comparison is not made by reading an old workbook back. The exported
XLSX carries live formulas (SUMIF against the element sheets), so its
quantity cells hold text like `SUMIF(Beam!...)`, not numbers - reading
them back would compare formulas, not concrete. Instead each export can
save a snapshot: the plain numbers behind that issue, one entry per BOQ
item, in a small JSON file under the user's profile. A snapshot is
therefore what a revision is in this tool, and the comparison is
snapshot against snapshot.

The item vocabulary - which items exist, how they are worded, in what
order - belongs to export_engine's Detailed BOQ. This module imports it
rather than restating it, so the two sheets can never describe the same
item in two ways.

Pure Python (os / json / re only): no Revit symbols, no third-party
packages, importable and testable outside Revit.
"""
import os
import json
import re

REVISION_SHEET_NAME = "BOQ Revision"

REVISION_HEADERS = (
    "Item No.", "Description", "Unit", "Previous Qty", "Current Qty",
    "Difference", "% Difference", "Status",
)

# Below this, a difference is rounding, not a change. Concrete is carried
# to 4 decimals of a cubic metre; 0.005 m3 is five litres, which no site
# measures and no BOQ should flag.
QUANTITY_TOLERANCE = 0.005

# Written into every snapshot so a later version can tell what it is
# reading. Bump it only when the stored shape changes. Format 2 (v1.40.0)
# adds "elements": one record per element, for P15's Model Changes sheet.
SNAPSHOT_FORMAT = 2

STATUS_NEW = "New"
STATUS_REMOVED = "Removed"
STATUS_INCREASED = "Increased"
STATUS_DECREASED = "Decreased"
STATUS_UNCHANGED = "Unchanged"

# Section letter -> band title, in Detailed BOQ order.
REVISION_SECTIONS = (
    ("A", "CONCRETE"),
    ("B", "CENTERING AND SHUTTERING"),
    ("C", "REINFORCEMENT"),
)


def _number(value):
    """The float in this cell, or None when there is not one.

    None is turned away before float() ever sees it. CPython answers
    float(None) with a TypeError; IronPython 2.7 - the engine the button
    runs on - answers with SystemError ("Object reference not set to an
    instance of an object"), which an except (TypeError, ValueError)
    never catches. On 2026-09-24 that killed a live export the moment an
    item was Removed, because a removed item has no current quantity.
    """
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _sum_field(rows, field, grade=None):
    """Total one Qty field over these rows, optionally for one grade.

    Returns None when no row carried the field at all, which is how an
    item that does not exist in this model is told apart from an item
    that measures zero.
    """
    from export_engine import NO_GRADE_LABEL

    total = 0.0
    found = False
    for row in rows or []:
        try:
            if grade is not None:
                row_grade = str(row.get("Grade", "") or "").strip()
                if (row_grade or NO_GRADE_LABEL) != grade:
                    continue
            value = _number(row.get(field, ""))
        except AttributeError:
            continue
        if value is None:
            continue
        total += value
        found = True
    return round(total, 4) if found else None


def build_snapshot(data_result, rebar_rows=None, revision="",
                   document="", exported="", element_types=None,
                   bbs_steel=None):
    """The plain numbers behind one issue of the BOQ.

    Same items, wording and order as the Detailed BOQ, but every quantity
    is a number computed here from the rows - never a formula - because a
    snapshot has to survive without the workbook it came from.

    `revision` is the label the issue is filed under (`Rev 00`),
    `document` the Revit document it was taken from, `exported` the date
    in ISO form. None of the three is invented: a caller that does not
    know one leaves it empty.

    `bbs_steel` is the model's BBS store (bbs_steel_engine): the steel
    read from separate BBS models joins the model's own rebar in section
    C, diameter by diameter, exactly as the Detailed BOQ adds it up.
    """
    from export_engine import (
        DETAILED_BOQ_CATEGORIES, NO_GRADE_LABEL, grades_in, boq_diameter_text)

    data = data_result if isinstance(data_result, dict) else {}
    items = []

    # A. Concrete, one item per category and grade present.
    for sheet_name, label in DETAILED_BOQ_CATEGORIES:
        rows = data.get(sheet_name) or []
        if not rows:
            continue
        for grade in grades_in(rows):
            quantity = _sum_field(rows, "Qty: Volume (m3)", grade)
            if quantity is None:
                continue
            if grade == NO_GRADE_LABEL:
                description = "Concrete in {0} - grade not recorded".format(label)
            else:
                description = "Concrete {0} in {1}".format(grade, label)
            items.append({
                "code": "A|{0}|{1}".format(sheet_name, grade),
                "description": description,
                "unit": "m3",
                "quantity": quantity,
            })

    # B. Centering and shuttering, one item per category.
    for sheet_name, label in DETAILED_BOQ_CATEGORIES:
        rows = data.get(sheet_name) or []
        if not rows:
            continue
        quantity = _sum_field(rows, "Qty: Shuttering (m2)")
        if quantity is None or quantity <= 0:
            continue
        items.append({
            "code": "B|{0}".format(sheet_name),
            "description": "Centering and shuttering to {0}".format(label),
            "unit": "m2",
            "quantity": quantity,
        })

    # C. Reinforcement, one item per diameter - the model's own rebar and
    # the steel read from its BBS models together.
    steel_rows = list(rebar_rows or [])
    if bbs_steel:
        from bbs_steel_engine import bbs_steel_rows
        steel_rows += bbs_steel_rows(bbs_steel)
    if steel_rows:
        from rebar_engine import build_rebar_diameter_summary_table
        for row in build_rebar_diameter_summary_table(steel_rows)[1:]:
            weight = _number(row[4])
            if not weight:
                continue
            diameter = boq_diameter_text(row[0])
            items.append({
                "code": "C|{0}".format(diameter),
                "description": "Reinforcement steel, {0} mm dia".format(diameter),
                "unit": "kg",
                "quantity": round(weight, 4),
            })

    # P15: one record per element - identity, grade, level, family and
    # type, and its concrete, shuttering and hosted steel - so the next
    # issue can say which elements moved, not only how much.
    from model_change_engine import build_element_records

    return {
        "format": SNAPSHOT_FORMAT,
        "revision": str(revision or ""),
        "document": str(document or ""),
        "exported": str(exported or ""),
        "items": items,
        "elements": build_element_records(
            data, rebar_rows, element_types),
    }


def snapshot_codes(snapshot):
    """The codes in a snapshot, in the order the snapshot lists them.

    Read from the items **list**, never from a dict: under IronPython
    2.7 - the engine the button actually runs on - a dict does not keep
    insertion order, and on 2026-09-24 a live export proved it, laying
    the sheet out Slab, Beam, Foundation, Wall, Column instead of the
    Detailed BOQ's own order. Python 3 keeps that order, so the harness
    could not have found this on its own.
    """
    codes = []
    if not isinstance(snapshot, dict):
        return codes
    for item in snapshot.get("items") or []:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code", "") or "").strip()
        if code and code not in codes:
            codes.append(code)
    return codes


def snapshot_items(snapshot):
    """{code: item} for a snapshot, tolerant of a file written by hand.

    A lookup only - for anything that has to come out in order, ask
    snapshot_codes.
    """
    result = {}
    if not isinstance(snapshot, dict):
        return result
    for item in snapshot.get("items") or []:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code", "") or "").strip()
        if not code:
            continue
        result[code] = item
    return result


def _section_of(code):
    """The section letter a code belongs to; anything odd goes last."""
    letter = code.split("|")[0].strip().upper() if code else ""
    for section, _title in REVISION_SECTIONS:
        if letter == section:
            return section
    return ""


def compare_snapshots(previous, current):
    """One record per item across both issues, in Detailed BOQ order.

    Each record carries `previous`, `current`, `difference`, `percent`
    and a `status`. An item only in the current issue is New, one only in
    the previous is Removed and shows a current quantity of 0 - it is
    listed, not dropped, because a vanished item is exactly what a
    revision sheet exists to show. `percent` is None when the previous
    quantity is zero: there is no percentage change from nothing, and
    printing one would be arithmetic with a hole in it.
    """
    old_items = snapshot_items(previous)
    new_items = snapshot_items(current)

    order = snapshot_codes(current)
    for code in snapshot_codes(previous):
        if code not in new_items:
            order.append(code)

    rank = [section for section, _title in REVISION_SECTIONS]

    def sort_key(index_code):
        index, code = index_code
        section = _section_of(code)
        return (rank.index(section) if section in rank else len(rank),
                code not in new_items,
                index)

    ordered = [code for _index, code in
               sorted(enumerate(order), key=sort_key)]

    records = []
    for code in ordered:
        new_item = new_items.get(code) or {}
        old_item = old_items.get(code) or {}
        source = new_item or old_item
        old_value = _number(old_item.get("quantity")) or 0.0
        new_value = _number(new_item.get("quantity")) or 0.0
        difference = round(new_value - old_value, 4)

        if abs(difference) < QUANTITY_TOLERANCE:
            status = STATUS_UNCHANGED
        elif code not in old_items:
            status = STATUS_NEW
        elif code not in new_items:
            status = STATUS_REMOVED
        elif difference > 0:
            status = STATUS_INCREASED
        else:
            status = STATUS_DECREASED

        percent = None
        if old_value:
            percent = round(difference / old_value * 100.0, 2)

        records.append({
            "code": code,
            "section": _section_of(code),
            "description": str(source.get("description", "") or ""),
            "unit": str(source.get("unit", "") or ""),
            "previous": round(old_value, 4),
            "current": round(new_value, 4),
            "difference": difference,
            "percent": percent,
            "status": status,
        })
    return records


def build_revision_table(previous, current, row_offset=0):
    """The BOQ Revision sheet: Previous, Current, Difference, % Difference.

    Difference and % Difference are live formulas, the way the rest of
    the workbook works, so a quantity corrected in Excel corrects them
    too. There is deliberately no TOTAL row: the column holds cubic
    metres, square metres and kilogrammes, and their sum would be a
    number with no meaning.

    `row_offset` is how far below its plain position each row lands - the
    site workbook's title bands push the table down - so the formulas
    point at where the numbers really are. A comparison with nothing in
    it returns the header alone.
    """
    table = [list(REVISION_HEADERS)]
    records = compare_snapshots(previous, current)
    if not records:
        return table

    by_section = {}
    for record in records:
        by_section.setdefault(record["section"], []).append(record)

    sections = list(REVISION_SECTIONS)
    if "" in by_section:
        sections.append(("", "OTHER ITEMS"))

    for letter, title in sections:
        rows = by_section.get(letter) or []
        if not rows:
            continue
        table.append([letter, title, "", "", "", "", "", ""])
        for index, record in enumerate(rows, 1):
            row_number = len(table) + 1 + row_offset
            table.append([
                "{0}.{1}".format(letter or "X", index),
                record["description"],
                record["unit"],
                record["previous"],
                record["current"],
                ("FORMULA", "E{0}-D{0}".format(row_number)),
                ("FORMULA",
                 'IF(D{0}=0,"",(E{0}-D{0})/D{0}*100)'.format(row_number)),
                record["status"],
            ])
    return table


def revision_meta_lines(previous, current):
    """Two lines naming the issues being compared, for a sheet heading.

    Empty fields are left out rather than filled in, so a snapshot saved
    without a date does not grow one here.
    """
    lines = []
    for label, snapshot in (("Previous", previous), ("Current", current)):
        if not isinstance(snapshot, dict):
            continue
        revision = str(snapshot.get("revision", "") or "").strip()
        exported = str(snapshot.get("exported", "") or "").strip()
        if not revision and not exported:
            continue
        text = u"{0}: {1}".format(
            label, revision_display_name(snapshot) or u"(unlabelled)")
        if exported:
            text += " exported {0}".format(exported)
        lines.append(text)
    return lines


def revision_title(previous, current):
    """`Rev 00 to Rev 01`, for the sheet's own heading; "" when unlabelled."""
    labels = []
    for snapshot in (previous, current):
        if not isinstance(snapshot, dict):
            return ""
        label = str(snapshot.get("revision", "") or "").strip()
        if not label:
            return ""
        labels.append(label)
    return "{0} to {1}".format(labels[0], labels[1])


def build_revision_sheet(previous, current, row_offset=0, with_meta=True):
    """The revision table with the two issues named above its header.

    The classic workbook's sheets are plain tables, so the heading lines
    have to be rows of the table itself; they push the header down, and
    the formulas are built knowing that. The site workbook has its own
    title band and passes with_meta=False. A comparison with nothing in
    it returns the header alone, so the caller can skip the sheet.
    """
    meta = revision_meta_lines(previous, current) if with_meta else []
    table = build_revision_table(previous, current, row_offset + len(meta))
    if len(table) <= 1:
        return table
    width = len(REVISION_HEADERS)
    heading = [[line] + [""] * (width - 1) for line in meta]
    return heading + table


def snapshot_is_unchanged(previous, current):
    """True when this issue measures exactly what the last one measured.

    A revision number should mean something changed. On 2026-09-22 a
    single debugging session ran thirteen exports of one model; filing a
    revision for each would have left Rev 00 to Rev 12 describing the
    same building. The quantities are compared at the tolerance the
    sheet uses, so rounding does not create an issue either.
    """
    old_items = snapshot_items(previous)
    new_items = snapshot_items(current)
    if set(old_items) != set(new_items):
        return False
    for code, item in new_items.items():
        before = _number(old_items[code].get("quantity")) or 0.0
        after = _number(item.get("quantity")) or 0.0
        if abs(after - before) >= QUANTITY_TOLERANCE:
            return False
    # P15 (v1.40.0): the same totals can hide a change - a beam moved to
    # another level, a type swapped, one element grown while another
    # shrank. An issue is only unchanged when its elements are too.
    from model_change_engine import elements_unchanged
    return elements_unchanged(previous, current)


def revision_change_counts(previous, current):
    """{status: how many items} - the one-line story of this revision."""
    counts = {}
    for record in compare_snapshots(previous, current):
        counts[record["status"]] = counts.get(record["status"], 0) + 1
    return counts


# ------------------------------------------------------------------
# The snapshot store
# ------------------------------------------------------------------

REVISION_LABEL_PATTERN = re.compile(r"^\s*rev\s*0*(\d+)\s*$", re.IGNORECASE)


def get_revisions_folder():
    """Where snapshots live: beside the crash trail, under the profile."""
    root = os.environ.get("LOCALAPPDATA", "") or os.path.expanduser("~")
    return os.path.join(root, "RCC_BOQ", "revisions")


def safe_folder_name(document):
    """A document title reduced to something a folder can be called.

    A Revit title can hold a path, a colon or a `..`, and a snapshot must
    land inside the document's own folder however the model is named, so
    everything but letters, digits, space, dot, dash and underscore
    becomes an underscore and no `..` survives.
    """
    text = str(document or "").strip()
    cleaned = re.sub(r"[^A-Za-z0-9 ._-]", "_", text)
    while ".." in cleaned:
        cleaned = cleaned.replace("..", "_")
    cleaned = re.sub(r"_{2,}", "_", cleaned).strip(" .")
    return cleaned[:80] or "document"


def document_folder(document):
    """The folder holding one document's revisions."""
    return os.path.join(get_revisions_folder(), safe_folder_name(document))


def revision_number(label):
    """`Rev 01` -> 1; anything else -> None."""
    match = REVISION_LABEL_PATTERN.match(str(label or ""))
    return int(match.group(1)) if match else None


def revision_label(number):
    """1 -> `Rev 01`."""
    try:
        return "Rev {0:02d}".format(int(number))
    except (TypeError, ValueError):
        return ""


def snapshot_filename(label):
    """`Rev 01` -> `rev_01.json`; a free-text label keeps its own name."""
    number = revision_number(label)
    if number is not None:
        return "rev_{0:02d}.json".format(number)
    return "{0}.json".format(safe_folder_name(label) or "revision")


def next_revision_label(existing):
    """The label the next issue should carry.

    `existing` may be labels or whole snapshots. Numbering continues from
    the highest number already filed, so a deleted Rev 01 does not let a
    second Rev 01 exist.
    """
    highest = None
    for entry in existing or []:
        label = entry.get("revision", "") if isinstance(entry, dict) else entry
        number = revision_number(label)
        if number is not None and (highest is None or number > highest):
            highest = number
    return revision_label(0 if highest is None else highest + 1)


def load_snapshot(path):
    """The snapshot in this file, or None when it cannot be read."""
    try:
        if not os.path.isfile(path):
            return None
        handle = open(path, "r")
        try:
            loaded = json.load(handle)
        finally:
            handle.close()
    except Exception:
        return None
    return loaded if isinstance(loaded, dict) else None


def save_snapshot(snapshot, document=None):
    """Write a snapshot into the document's folder; return its path or "".

    Written to a temporary file and renamed into place, the same way
    settings are: a crash halfway through a write cannot leave a
    half-snapshot that a later revision would silently compare against.
    """
    if not isinstance(snapshot, dict):
        return ""
    title = document if document is not None else snapshot.get("document", "")
    folder = document_folder(title)
    name = snapshot_filename(snapshot.get("revision", ""))
    path = os.path.join(folder, name)
    temp_path = path + ".tmp"

    try:
        payload = json.dumps(snapshot, indent=2)
    except Exception:
        return ""

    try:
        if not os.path.isdir(folder):
            os.makedirs(folder)
        handle = open(temp_path, "w")
        try:
            handle.write(payload)
        finally:
            handle.close()
    except Exception:
        return ""

    try:
        if os.path.exists(path):
            os.remove(path)
        os.rename(temp_path, path)
    except Exception:
        try:
            handle = open(path, "w")
            try:
                handle.write(payload)
            finally:
                handle.close()
            os.remove(temp_path)
        except Exception:
            return ""
    return path


def list_snapshots(document):
    """Every snapshot filed for this document, oldest revision first.

    A file that cannot be read is skipped rather than raised: one bad
    file must not hide the revisions around it.
    """
    folder = document_folder(document)
    result = []
    try:
        names = sorted(os.listdir(folder))
    except Exception:
        return result
    for name in names:
        if not name.lower().endswith(".json"):
            continue
        snapshot = load_snapshot(os.path.join(folder, name))
        if snapshot is None:
            continue
        snapshot["path"] = os.path.join(folder, name)
        result.append(snapshot)
    result.sort(key=lambda snap: (
        revision_number(snap.get("revision", "")) is None,
        revision_number(snap.get("revision", "")) or 0,
        str(snap.get("revision", "")),
    ))
    return result


def latest_snapshot(document):
    """The highest-numbered snapshot filed for this document, or None."""
    filed = list_snapshots(document)
    return filed[-1] if filed else None


# ------------------------------------------------------------------
# Choosing the issue to compare against, and naming issues (v1.37.0)
# ------------------------------------------------------------------

# Where the per-document choice lives in the settings file:
# {"revision_compare": {"<document folder name>": "Rev 01"}}. A document
# with no entry compares against its latest filed revision, as before.
COMPARE_SETTINGS_KEY = "revision_compare"

# A name is a short tag for an issue ("Client issue 1", "Tender"), not a
# note; it has to fit in a list row and a sheet heading.
MAX_NAME_LENGTH = 60


def clean_revision_name(name):
    """Whitespace collapsed, trimmed, and cut to MAX_NAME_LENGTH."""
    text = u" ".join(u"{0}".format(name or u"").split())
    return text[:MAX_NAME_LENGTH].rstrip()


def revision_display_name(snapshot):
    """`Rev 01 - Client issue 1`, or just `Rev 01` when it has no name."""
    if not isinstance(snapshot, dict):
        return u""
    label = u"{0}".format(snapshot.get("revision", "") or u"").strip()
    name = clean_revision_name(snapshot.get("name", u""))
    if label and name:
        return u"{0} - {1}".format(label, name)
    return label or name


def revision_list_text(snapshot):
    """One row of the dialog's list: label, date, how many items, name."""
    if not isinstance(snapshot, dict):
        return u""
    parts = [u"{0}".format(snapshot.get("revision", "") or u"(unlabelled)")]
    exported = u"{0}".format(snapshot.get("exported", "") or u"").strip()
    if exported:
        parts.append(exported)
    count = len(snapshot_codes(snapshot))
    parts.append(u"{0} item{1}".format(count, u"" if count == 1 else u"s"))
    name = clean_revision_name(snapshot.get("name", u""))
    if name:
        parts.append(name)
    return u"   |   ".join(parts)


def get_compare_choice(settings, document):
    """The label this document compares against, or "" for the latest."""
    if not isinstance(settings, dict):
        return ""
    table = settings.get(COMPARE_SETTINGS_KEY)
    if not isinstance(table, dict):
        return ""
    label = table.get(safe_folder_name(document), "")
    number = revision_number(label)
    return revision_label(number) if number is not None else ""


def set_compare_choice(settings, document, label):
    """A copy of settings with this document's choice set, or cleared.

    Any label that is not a revision - "", "Latest", junk - clears the
    choice, which means "the latest filed revision". Other documents'
    choices and every other setting are kept.
    """
    result = dict(settings) if isinstance(settings, dict) else {}
    table = result.get(COMPARE_SETTINGS_KEY)
    table = dict(table) if isinstance(table, dict) else {}
    key = safe_folder_name(document)
    number = revision_number(label)
    if number is None:
        table.pop(key, None)
    else:
        table[key] = revision_label(number)
    if table:
        result[COMPARE_SETTINGS_KEY] = table
    else:
        result.pop(COMPARE_SETTINGS_KEY, None)
    return result


def choose_previous(filed, choice):
    """The snapshot to compare against: the chosen one, else the latest.

    `filed` is list_snapshots() - oldest first. A choice that is no
    longer filed (its file was deleted) falls back to the latest rather
    than silently comparing against nothing.
    """
    filed = [snapshot for snapshot in (filed or []) if isinstance(snapshot, dict)]
    if not filed:
        return None
    wanted = revision_number(choice)
    if wanted is not None:
        for snapshot in filed:
            if revision_number(snapshot.get("revision", "")) == wanted:
                return snapshot
    return filed[-1]


def settle_current_issue(latest, current):
    """(current, is_new): what this export is, before anything is written.

    An export that measures exactly what the latest filed revision
    measured is that revision, not a new one - so it is not filed, and it
    must not be called by the next number either. Found live on
    2026-09-25: the sheet read "Current: Rev 03" while no Rev 03 was ever
    filed, and the next export would have claimed Rev 03 again. Such an
    export takes the latest's label and name; its date stays today's,
    because that is when this workbook was made. Returns a copy; the
    snapshot passed in is not changed.
    """
    if not isinstance(current, dict):
        return current, False
    if isinstance(latest, dict) and snapshot_is_unchanged(latest, current):
        settled = dict(current)
        settled["revision"] = latest.get("revision", "")
        if latest.get("name"):
            settled["name"] = latest.get("name")
        else:
            settled.pop("name", None)
        return settled, False
    return current, True


def set_revision_name(document, revision, name):
    """Give a filed revision a name; return the file written, or "".

    Only the name changes: the quantities, label and date are what that
    issue measured and stay exactly as filed.
    """
    wanted = revision_number(revision)
    if wanted is None:
        return ""
    for snapshot in list_snapshots(document):
        if revision_number(snapshot.get("revision", "")) != wanted:
            continue
        updated = dict(snapshot)
        updated.pop("path", None)
        cleaned = clean_revision_name(name)
        if cleaned:
            updated["name"] = cleaned
        else:
            updated.pop("name", None)
        return save_snapshot(updated, document)
    return ""

# -*- coding: utf-8 -*-
"""BBS steel engine - reinforcement measured in separate BBS models.

On many projects the reinforcement is not in the structural model the BOQ
is exported from. It lives in separate BBS (bar bending schedule) models:
one for the foundation, one for the columns, one per level for the beams
and for the slabs. On UMA NIWAS there are twenty of them and the
structural model has no rebar at all, so its BOQ showed no steel - and
priced none.

This engine keeps, per structural model, the list of its BBS models and
what was measured in each: rebar sets, and bars, length and kilograms per
diameter, weighed by the tool's own d^2/162 rule (rebar_engine). The
dialog reads a BBS model once - Revit takes a minute or more to open one,
longer when it upgrades an older file - and the export uses the stored
figures. It says so when a BBS model has changed since it was read, and it
never counts a model that could not be read.

The element a BBS model is for (foundation, column, beam, slab, stair)
comes from the model file, never from the rebar's host: on UMA NIWAS the
slab rebar is hosted on Structural Foundations, because that is how the
slabs are modelled. The dialog lets the owner correct a guess.

Pure Python (os / json / re / time only): no Revit symbols, no third-party
packages. Order always comes from lists, never from a dict, because
IronPython 2.7 - the engine the button runs on - does not keep a dict in
insertion order; and no float() ever sees None.
"""
import os
import json
import re
import time

BBS_STEEL_SHEET_NAME = "BBS Steel"

# Written into every store so a later version can tell what it is reading.
BBS_STORE_FORMAT = 1

# The elements a BBS model can be for, in the order they are built - which
# is also the order the BBS Steel sheet lists them.
BBS_GROUPS = ("Foundation", "Column", "Wall", "Beam", "Slab", "Stair", "Other")

# Words in a BBS model's file name, checked in this order. Stair comes
# before Slab so a "STAIR SLAB" model is a stair.
_GROUP_WORDS = (
    ("STAIR", "Stair"),
    ("SLAB", "Slab"),
    ("BEAM", "Beam"),
    ("COLUMN", "Column"),
    ("WALL", "Wall"),
    ("FOUNDATION", "Foundation"),
    ("FOOTING", "Foundation"),
    ("RAFT", "Foundation"),
    ("PILE", "Foundation"),
)

_LEVEL_PATTERN = re.compile(
    r"\b(PLINTH|GROUND|BASEMENT|TERRACE|ROOF|PARAPET|\d+\s*(?:ST|ND|RD|TH))"
    r"\s+(LEVEL|FLOOR)\b")

STATUS_READ = "read"
STATUS_UNREAD = "unread"
STATUS_CHANGED = "changed"
STATUS_MISSING = "missing"
STATUS_ERROR = "error"


def _number(value):
    """The float in this value, or None. None never reaches float()."""
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


# ------------------------------------------------------------------
# What a BBS model is for, from its file name
# ------------------------------------------------------------------

def detect_bbs_group(file_name):
    """`...-1ST LEVEL BBS BEAM-06-09-2025.rvt` -> `Beam`; unknown -> `Other`."""
    upper = _text(os.path.basename(_text(file_name))).upper()
    for word, group in _GROUP_WORDS:
        if word in upper:
            return group
    return "Other"


def detect_bbs_level(file_name):
    """`...-1ST LEVEL BBS BEAM...` -> `1ST LEVEL`; no level named -> ``."""
    upper = _text(os.path.basename(_text(file_name))).upper()
    match = _LEVEL_PATTERN.search(upper)
    if not match:
        return u""
    return u"{0} {1}".format(re.sub(r"\s+", u"", match.group(1)), match.group(2))


def level_sort_key(level):
    """Basement, plinth / ground, 1st, 2nd ... terrace, roof; unnamed last."""
    upper = _text(level).upper()
    if not upper:
        return 999
    if upper.startswith("BASEMENT"):
        return -1
    if upper.startswith("PLINTH") or upper.startswith("GROUND"):
        return 0
    digits = re.match(r"(\d+)", upper)
    if digits:
        return int(digits.group(1))
    if upper.startswith("TERRACE"):
        return 900
    if upper.startswith("ROOF"):
        return 901
    return 902


def group_sort_key(group):
    try:
        return BBS_GROUPS.index(group)
    except ValueError:
        return len(BBS_GROUPS)


# ------------------------------------------------------------------
# The store: one small JSON file per structural model
# ------------------------------------------------------------------

def get_bbs_folder():
    """Where the stores live: beside the revisions, under the profile."""
    root = os.environ.get("LOCALAPPDATA", "") or os.path.expanduser("~")
    return os.path.join(root, "RCC_BOQ", "bbs")


def bbs_store_path(document):
    """The store of one structural model, named after its document title."""
    from revision_engine import safe_folder_name
    return os.path.join(get_bbs_folder(), safe_folder_name(document) + ".json")


def empty_store(document=""):
    return {"format": BBS_STORE_FORMAT, "document": _text(document), "files": []}


def load_bbs_store(document):
    """This model's store, or an empty one when there is none to read."""
    try:
        path = bbs_store_path(document)
        if not os.path.isfile(path):
            return empty_store(document)
        handle = open(path, "r")
        try:
            loaded = json.load(handle)
        finally:
            handle.close()
    except Exception:
        return empty_store(document)
    if not isinstance(loaded, dict) or not isinstance(loaded.get("files"), list):
        return empty_store(document)
    loaded["files"] = [entry for entry in loaded["files"]
                       if isinstance(entry, dict) and _text(entry.get("path"))]
    return loaded


def save_bbs_store(store, document=None):
    """Write the store; return its path, or "" when it could not be written.

    Written to a temporary file and renamed into place, like the revision
    snapshots: a crash halfway through a write - reading twenty models is a
    long job - must not leave a half-written list behind.
    """
    if not isinstance(store, dict):
        return ""
    title = document if document is not None else store.get("document", "")
    path = bbs_store_path(title)
    temp_path = path + ".tmp"
    try:
        payload = json.dumps(store, indent=2)
    except Exception:
        return ""
    try:
        folder = os.path.dirname(path)
        if not os.path.isdir(folder):
            os.makedirs(folder)
        handle = open(temp_path, "w")
        try:
            handle.write(payload)
        finally:
            handle.close()
        if os.path.exists(path):
            os.remove(path)
        os.rename(temp_path, path)
    except Exception:
        return ""
    return path


def _same_path(first, second):
    return (os.path.normcase(os.path.abspath(_text(first)))
            == os.path.normcase(os.path.abspath(_text(second))))


def add_bbs_files(store, paths):
    """Add BBS models by path; one already listed is not added twice.

    Returns how many were added. Each new model is unread until the dialog
    reads it.
    """
    added = 0
    files = store.setdefault("files", [])
    for path in paths or []:
        path = _text(path)
        if not path:
            continue
        if any(_same_path(path, entry.get("path")) for entry in files):
            continue
        name = os.path.basename(path)
        files.append({
            "path": path,
            "name": name,
            "group": detect_bbs_group(name),
            "level": detect_bbs_level(name),
        })
        added += 1
    return added


def remove_bbs_file(store, index):
    files = store.get("files") or []
    if 0 <= index < len(files):
        files.pop(index)
        return True
    return False


def set_bbs_group(store, index, group):
    files = store.get("files") or []
    if 0 <= index < len(files) and group in BBS_GROUPS:
        files[index]["group"] = group
        return True
    return False


# ------------------------------------------------------------------
# Readings
# ------------------------------------------------------------------

def file_signature(path):
    """(size in bytes, modified time in whole seconds), or None if missing."""
    try:
        return [int(os.path.getsize(path)), int(os.path.getmtime(path))]
    except Exception:
        return None


def entry_status(entry, signature=False):
    """What the export can do with this BBS model's figures.

    `signature` is the model file's current file_signature; left out, it is
    looked up. read - counted; changed - counted, but the file has changed
    since; missing - counted, but the file is gone; unread / error - not
    counted.
    """
    if _text(entry.get("error")):
        return STATUS_ERROR
    if not _text(entry.get("read")):
        return STATUS_UNREAD
    if signature is False:
        signature = file_signature(entry.get("path"))
    if signature is None:
        return STATUS_MISSING
    if list(signature) != list(entry.get("signature") or []):
        return STATUS_CHANGED
    return STATUS_READ


def needs_reading(entry, signature=False):
    """True for a model that is unread, changed, or failed last time."""
    return entry_status(entry, signature) in (
        STATUS_UNREAD, STATUS_CHANGED, STATUS_ERROR)


def summarize_steel(values):
    """Per-diameter totals of one BBS model's rebar sets.

    `values` holds one rebar_engine.build_rebar_quantity_values() result
    per rebar set. Returns (diameters, sets, unweighed): diameters is a
    list of [diameter mm, bars, length m, kg] in diameter order, and
    unweighed counts the sets with no diameter or no length, which weigh
    nothing and are reported rather than guessed.
    """
    order = []
    totals = []
    sets = 0
    unweighed = 0
    for value in values or []:
        sets += 1
        diameter = _number(value.get("Diameter (mm)"))
        weight = _number(value.get("Total Weight (kg)"))
        if diameter is None or weight is None:
            unweighed += 1
            continue
        diameter = round(diameter, 3)
        bars = _number(value.get("Quantity")) or 0.0
        length = _number(value.get("Total Length (m)")) or 0.0
        if diameter not in order:
            order.append(diameter)
            totals.append([diameter, 0, 0.0, 0.0])
        row = totals[order.index(diameter)]
        row[1] += int(bars)
        row[2] += length
        row[3] += weight
    diameters = []
    for row in sorted(totals, key=lambda item: item[0]):
        diameters.append([row[0], row[1], round(row[2], 4), round(row[3], 3)])
    return diameters, sets, unweighed


def record_bbs_reading(entry, values, signature=None, read_at="", revit=""):
    """Put a successful reading on the entry, replacing any earlier one."""
    diameters, sets, unweighed = summarize_steel(values)
    entry["diameters"] = diameters
    entry["sets"] = sets
    entry["unweighed"] = unweighed
    entry["total_kg"] = round(sum(row[3] for row in diameters), 3)
    entry["signature"] = list(signature) if signature else []
    entry["read"] = _text(read_at) or time.strftime("%Y-%m-%d %H:%M")
    entry["revit"] = _text(revit)
    entry["error"] = u""
    return entry


def record_bbs_error(entry, message):
    """A failed read counts nothing: the earlier figures are dropped too."""
    for key in ("diameters", "sets", "unweighed", "total_kg", "signature",
                "read", "revit"):
        entry.pop(key, None)
    entry["error"] = _text(message)[:300] or u"Could not be read"
    return entry


def counted_entries(store):
    """The BBS models whose steel goes into the BOQ, in list order."""
    counted = []
    for entry in (store or {}).get("files") or []:
        if _text(entry.get("error")) or not _text(entry.get("read")):
            continue
        counted.append(entry)
    return counted


def bbs_total_kg(store):
    return round(sum(_number(entry.get("total_kg")) or 0.0
                     for entry in counted_entries(store)), 3)


def bbs_steel_rows(store):
    """The BBS steel as rows shaped like the Rebar sheet's.

    One row per model and diameter, carrying the four fields the diameter
    summary adds up, so the Detailed BOQ, the revision snapshot and the
    Dashboard take BBS steel through the very code that takes the model's
    own rebar - one diameter, one BOQ item, whatever its source.
    """
    rows = []
    for entry in counted_entries(store):
        for diameter, bars, length, kg in entry.get("diameters") or []:
            rows.append({
                "Rebar: Diameter (mm)": diameter,
                "Rebar: Quantity": bars,
                "Rebar: Total Length (m)": length,
                "Rebar: Total Weight (kg)": kg,
                "Rebar: Source": u"BBS model: {0}".format(_text(entry.get("name"))),
            })
    return rows


def bbs_warnings(store):
    """[issue, count, unit, note] for each kind of BBS model not in order."""
    counts = []
    labels = (
        (STATUS_UNREAD, u"BBS model not read yet",
         u"Not counted - read it on the BBS Steel tab"),
        (STATUS_ERROR, u"BBS model could not be read",
         u"Not counted - see the BBS Steel sheet"),
        (STATUS_CHANGED, u"BBS model changed since it was read",
         u"Counted as last read - read it again"),
        (STATUS_MISSING, u"BBS model file not found",
         u"Counted as last read - check the path"),
    )
    statuses = [entry_status(entry) for entry in (store or {}).get("files") or []]
    for status, issue, note in labels:
        count = statuses.count(status)
        if count:
            counts.append([issue, count, u"models", note])
    return counts


# ------------------------------------------------------------------
# Text for the dialog
# ------------------------------------------------------------------

STATUS_TEXT = (
    (STATUS_READ, u"read"),
    (STATUS_UNREAD, u"not read yet"),
    (STATUS_CHANGED, u"CHANGED since it was read"),
    (STATUS_MISSING, u"FILE NOT FOUND"),
    (STATUS_ERROR, u"could not be read"),
)


def status_text(status):
    for key, text in STATUS_TEXT:
        if key == status:
            return text
    return status


def bbs_list_text(entry):
    """One line of the dialog's list."""
    status = entry_status(entry)
    parts = [_text(entry.get("group")) or u"Other"]
    if _text(entry.get("level")):
        parts.append(_text(entry.get("level")))
    parts.append(_text(entry.get("name")))
    if status in (STATUS_READ, STATUS_CHANGED, STATUS_MISSING):
        sets = int(_number(entry.get("sets")) or 0)
        parts.append(u"{0:,.2f} kg in {1} set{2}".format(
            _number(entry.get("total_kg")) or 0.0, sets, u"" if sets == 1 else u"s"))
        parts.append(u"read {0}".format(_text(entry.get("read"))))
    if status != STATUS_READ:
        parts.append(status_text(status))
    return u"  |  ".join(parts)


def bbs_summary_text(store):
    """What the next export will do with the BBS models."""
    files = (store or {}).get("files") or []
    if not files:
        return (u"No BBS models added. Add them when this model's "
                u"reinforcement lives in separate BBS models.")
    counted = counted_entries(store)
    waiting = len([entry for entry in files if needs_reading(entry)])
    text = u"{0} BBS model{1}, {2} read: {3:,.3f} t of steel.".format(
        len(files), u"" if len(files) == 1 else u"s", len(counted),
        bbs_total_kg(store) / 1000.0)
    if waiting:
        text += u" {0} to read - click Read new and changed.".format(waiting)
    text += (u" The next export adds this steel to the Detailed BOQ "
             u"(section C), the Dashboard and a BBS Steel sheet.")
    return text


# ------------------------------------------------------------------
# The BBS Steel sheet
# ------------------------------------------------------------------

def _diameter_heading(diameter):
    from export_engine import boq_diameter_text
    return u"{0} mm (kg)".format(boq_diameter_text(diameter))


def build_bbs_steel_table(store):
    """The BBS Steel sheet as a plain table.

    One row per BBS model - element, level, file, sets, kg per diameter,
    total - grouped foundation, column, wall, beam, slab, stair, each group
    followed by its total, and a GRAND TOTAL. A model that is not counted
    still gets its row, with no figures and the reason in Status, so a
    missing model is seen rather than silently left out. A header-only
    table means there were no BBS models.
    """
    files = list((store or {}).get("files") or [])
    diameters = []
    for entry in counted_entries(store):
        for row in entry.get("diameters") or []:
            if row[0] not in diameters:
                diameters.append(row[0])
    diameters.sort()

    headers = ([u"Element", u"Level", u"BBS Model", u"Rebar Sets"]
               + [_diameter_heading(d) for d in diameters]
               + [u"Total (kg)", u"Total (t)", u"Read On", u"Status"])
    table = [headers]
    if not files:
        return table

    ordered = sorted(
        range(len(files)),
        key=lambda i: (group_sort_key(_text(files[i].get("group")) or "Other"),
                       level_sort_key(files[i].get("level")),
                       _text(files[i].get("name")).upper(), i))

    def figure_cells(sets, by_diameter, total):
        cells = [sets]
        for position in range(len(diameters)):
            # A diameter a model does not use is left blank, not 0.00.
            weight = round(by_diameter[position], 2)
            cells.append(weight if weight else u"")
        cells.append(round(total, 2))
        cells.append(round(total / 1000.0, 3))
        return cells

    grand = [0, [0.0] * len(diameters), 0.0]
    current_group = None
    group_totals = None

    def close_group():
        if current_group is None:
            return
        table.append([u"{0} TOTAL".format(current_group).upper(), u"", u""]
                     + figure_cells(group_totals[0], group_totals[1],
                                    group_totals[2])
                     + [u"", u""])

    for index in ordered:
        entry = files[index]
        group = _text(entry.get("group")) or u"Other"
        if group != current_group:
            close_group()
            current_group = group
            group_totals = [0, [0.0] * len(diameters), 0.0]
        status = entry_status(entry)
        counted = status in (STATUS_READ, STATUS_CHANGED, STATUS_MISSING)
        note = u"" if status == STATUS_READ else status_text(status)
        if status == STATUS_ERROR:
            note = u"Could not be read: {0}".format(_text(entry.get("error")))
        unweighed = int(_number(entry.get("unweighed")) or 0)
        if counted and unweighed:
            note = (note + u"; " if note else u"") + (
                u"{0} sets with no diameter or length, not weighed".format(unweighed))
        if not counted:
            table.append([group, _text(entry.get("level")), _text(entry.get("name"))]
                         + [u""] * (len(diameters) + 3)
                         + [u"", note])
            continue
        by_diameter = [0.0] * len(diameters)
        for diameter, _bars, _length, kg in entry.get("diameters") or []:
            by_diameter[diameters.index(diameter)] += _number(kg) or 0.0
        sets = int(_number(entry.get("sets")) or 0)
        total = sum(by_diameter)
        table.append([group, _text(entry.get("level")), _text(entry.get("name"))]
                     + figure_cells(sets, by_diameter, total)
                     + [_text(entry.get("read")), note])
        for totals in (group_totals, grand):
            totals[0] += sets
            for position in range(len(diameters)):
                totals[1][position] += by_diameter[position]
            totals[2] += total
    close_group()
    table.append([u"GRAND TOTAL", u"", u""]
                 + figure_cells(grand[0], grand[1], grand[2]) + [u"", u""])
    return table


def bbs_numeric_columns(table):
    """1-based columns styled as quantities: the kg columns to Total (t).

    Rebar Sets is a count and stays a plain number, not "8,652.00".
    """
    if not table:
        return []
    return list(range(5, len(table[0]) - 1))

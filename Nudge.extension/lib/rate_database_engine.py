# -*- coding: utf-8 -*-
"""Rate database engine (P12) - configurable rates, never hard-coded.

A rate database is a list of entries: Item Code, Description, Unit, Rate,
Currency, Location, Vendor, Effective Date and Source. The same item code
may appear more than once - at another location, or from a later date -
so a lookup answers "what is the rate for this item, here, on this day?"
rather than "what is the rate for this item?".

No rate lives in this module. Every figure comes from the project's
settings document; a caller that has none gets an empty database, and an
item it cannot price stays blank. Pure Python, no Revit symbols.
"""
import datetime

RATE_DATABASE_SHEET_NAME = "Rate Database"
RATE_DATABASE_SETTINGS_KEY = "rate_database"

RATE_DATABASE_HEADERS = (
    "Item Code", "Description", "Unit", "Rate", "Currency",
    "Location", "Vendor", "Effective Date", "Source", "Status",
)

RATE_TEXT_FIELDS = (
    "item_code", "description", "unit", "currency",
    "location", "vendor", "source",
)

# A source that says it is a sample is shown as one on every sheet, so a
# test figure cannot pass for a quoted rate.
SAMPLE_SOURCE_MARK = "SAMPLE"

STATUS_READY = "Ready"
STATUS_SAMPLE = "Sample - not a real rate"
STATUS_INPUT_REQUIRED = "Input required"


def _text(raw, key):
    try:
        return str(raw.get(key, "") or "").strip()
    except Exception:
        return ""


def _rate_value(value):
    """A non-negative, finite number, or None.

    Blank, negative, boolean and non-numeric all refuse: a rate database
    that reads a typo as zero prices work for free.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    if number < 0:
        return None
    return number


def normalize_effective_date(value):
    """Return the date as 'YYYY-MM-DD', or '' when it is not a real date.

    Only the ISO form is accepted. '03/04/2026' is the 3rd of April to one
    reader and the 4th of March to another, and a rate schedule chosen by
    date must not depend on who typed it.
    """
    try:
        text = str(value or "").strip()
    except Exception:
        return ""
    if len(text) != 10:
        return ""
    try:
        return datetime.datetime.strptime(text, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return ""


def is_sample_entry(entry):
    """True when the entry's source marks it as a sample, not a real rate."""
    return SAMPLE_SOURCE_MARK in _text(entry or {}, "source").upper()


def normalize_rate_entry(raw):
    """Normalize one rate entry.

    Text fields are trimmed; the rate is kept as a number or None - never
    defaulted. A readable date becomes ISO. A date that was typed but could
    not be read keeps its typed text and sets `date_invalid`, so the sheet
    shows the owner's own text flagged instead of quietly treating the rate
    as undated - and normalizing twice gives the same entry.
    """
    raw = raw if isinstance(raw, dict) else {}
    entry = dict((key, _text(raw, key)) for key in RATE_TEXT_FIELDS)
    entry["rate"] = _rate_value(raw.get("rate"))
    typed_date = _text(raw, "effective_date")
    iso_date = normalize_effective_date(typed_date)
    entry["date_invalid"] = bool(typed_date) and not iso_date
    entry["effective_date"] = iso_date or typed_date
    return entry


def rate_entry_status(entry):
    """What the entry lacks, or whether it is ready - or only a sample."""
    entry = normalize_rate_entry(entry)
    missing = []
    for key, label in (("item_code", "item code"), ("unit", "unit")):
        if not entry[key]:
            missing.append(label)
    if entry["rate"] is None:
        missing.append("rate")
    if entry["date_invalid"]:
        missing.append("effective date (use YYYY-MM-DD)")
    if missing:
        return "{0}: {1}".format(STATUS_INPUT_REQUIRED, ", ".join(missing))
    if is_sample_entry(entry):
        return STATUS_SAMPLE
    return STATUS_READY


def _same(left, right):
    return left.strip().upper() == right.strip().upper()


def find_rate_entry_conflict(entries, candidate, ignore_index=-1):
    """Index of another entry with the same code, location and date, or -1.

    One code may carry many rates - one per location and per effective
    date - but two rates for the same code, place and day leave nobody sure
    which the BOQ means. The place is the first level of the location, so
    'Gujarat' and 'Gujarat, India' are the same place. Codes and places
    compare case-insensitively.
    `ignore_index` is the entry being updated, which may keep its own key.
    """
    wanted = normalize_rate_entry(candidate)
    if not wanted["item_code"]:
        return -1
    for index, raw in enumerate(list(entries or [])):
        if index == ignore_index or not isinstance(raw, dict):
            continue
        entry = normalize_rate_entry(raw)
        if (_same(entry["item_code"], wanted["item_code"])
                and _same(_entry_place(entry), _entry_place(wanted))
                and entry["effective_date"] == wanted["effective_date"]):
            return index
    return -1


def location_levels(location):
    """Split a location into levels, most specific first.

    'Navsari, Gujarat, India' -> ['Navsari', 'Gujarat', 'India']. Any
    city, state or country in the world works; nothing here knows a place
    name.
    """
    try:
        text = str(location or "")
    except Exception:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


def _entry_place(entry):
    """The place an entry's rate belongs to: the first level of its location.

    An entry saved as 'Gujarat, India' is a Gujarat rate; one saved as
    'India' is a country rate.
    """
    levels = location_levels(entry.get("location", ""))
    return levels[0] if levels else ""


def find_rate(entries, item_code, location="", on_date=""):
    """The entry that prices this item here on this day, or None.

    - Only entries with this code and a usable rate are considered.
    - The project location is searched level by level, most specific
      first: for 'Navsari, Gujarat, India' a Navsari rate, else a Gujarat
      rate, else an India rate, else a general rate (an entry with no
      location). The first level that has a rate decides.
    - A sibling place is never borrowed: a Surat rate does not price a
      Navsari job unless Surat is one of the job's own levels. Put the rate
      at the level it is true for - a state or country rate reaches every
      city under it.
    - Entries dated after `on_date` are not yet in force. Of the rest, the
      latest date wins; an undated entry ranks below any dated one.
    - Two equally good entries (same code, place and date) are a conflict,
      and a conflict prices nothing rather than guessing.
    """
    try:
        code = str(item_code or "").strip()
    except Exception:
        return None
    if not code:
        return None
    cutoff = normalize_effective_date(on_date)

    usable = []
    for raw in list(entries or []):
        if not isinstance(raw, dict):
            continue
        entry = normalize_rate_entry(raw)
        if entry["rate"] is None or entry["date_invalid"]:
            continue
        if not _same(entry["item_code"], code):
            continue
        if cutoff and entry["effective_date"] and entry["effective_date"] > cutoff:
            continue
        usable.append(entry)

    pool = []
    for level in location_levels(location) + [""]:
        pool = [e for e in usable if _same(_entry_place(e), level)]
        if pool:
            break
    if not pool:
        return None

    best_date = max(e["effective_date"] for e in pool)
    best = [e for e in pool if e["effective_date"] == best_date]
    return best[0] if len(best) == 1 else None


def build_rate_database_sheet(entries):
    """The Rate Database table: headers plus one row per entry, in order.

    An incomplete entry keeps its row with a status naming what is missing,
    and a sample entry is labelled as one on its own row.
    """
    table = [list(RATE_DATABASE_HEADERS)]
    for raw in list(entries or []):
        if not isinstance(raw, dict):
            continue
        entry = normalize_rate_entry(raw)
        table.append([
            entry["item_code"],
            entry["description"],
            entry["unit"],
            "" if entry["rate"] is None else entry["rate"],
            entry["currency"],
            entry["location"],
            entry["vendor"],
            entry["effective_date"],
            entry["source"],
            rate_entry_status(raw),
        ])
    return table


def load_rate_database(settings):
    """Read the saved rate entries out of the settings document.

    Returns normalized entries, never None; anything that is not a list of
    dictionaries is ignored, so a corrupt settings file cannot stop an
    export.
    """
    try:
        raw = (settings or {}).get(RATE_DATABASE_SETTINGS_KEY)
    except AttributeError:
        return []
    if not isinstance(raw, list):
        return []
    return [normalize_rate_entry(item) for item in raw if isinstance(item, dict)]


PROJECT_LOCATION_SETTINGS_KEY = "project_location"


def get_project_location(settings, project_key):
    """The location saved for this project, or ''.

    Kept per project (the document title), because one office prices a
    Navsari job and a Dubai job from the same rate database.
    """
    try:
        saved = (settings or {}).get(PROJECT_LOCATION_SETTINGS_KEY)
        if not isinstance(saved, dict):
            return ""
        return str(saved.get(str(project_key or ""), "") or "").strip()
    except Exception:
        return ""


def set_project_location(settings, project_key, location):
    """Return the settings document with this project's location stored.

    A blank location removes the project's entry; other projects keep
    theirs.
    """
    document = settings if isinstance(settings, dict) else {}
    saved = document.get(PROJECT_LOCATION_SETTINGS_KEY)
    saved = dict(saved) if isinstance(saved, dict) else {}
    key = str(project_key or "").strip()
    try:
        place = ", ".join(location_levels(location))
    except Exception:
        place = ""
    if key:
        if place:
            saved[key] = place
        else:
            saved.pop(key, None)
    document[PROJECT_LOCATION_SETTINGS_KEY] = saved
    return document


def save_rate_database(settings, entries):
    """Return the settings document with these rate entries stored.

    Only the declared fields are written, and an entry with nothing in it
    is dropped. An unreadable date is stored as typed, so the owner sees
    their own text flagged rather than finding it silently erased.
    """
    document = settings if isinstance(settings, dict) else {}
    stored = []
    for raw in list(entries or []):
        if not isinstance(raw, dict):
            continue
        entry = normalize_rate_entry(raw)
        row = {}
        for key in RATE_TEXT_FIELDS:
            if entry[key]:
                row[key] = entry[key]
        if entry["rate"] is not None:
            row["rate"] = entry["rate"]
        if entry["effective_date"]:
            row["effective_date"] = entry["effective_date"]
        if row:
            stored.append(row)
    document[RATE_DATABASE_SETTINGS_KEY] = stored
    return document

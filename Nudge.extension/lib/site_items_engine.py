# -*- coding: utf-8 -*-
"""Site items engine (P7) - non-model structural line items.

Pure Python by design (PROJECT_STRUCTURE.md section 9, CLAUDE.md section 1).
PRD Phase 7 covers items that are not explicitly modelled - consumables,
temporary works, site items - carried as Item Code, Description, Quantity,
Unit, Rate and Remarks alongside the model-derived quantities.

This module owns only the rules: normalizing what the user typed, saying
what is unusable and why, pricing what can be priced, and producing the
export table. Settings persistence, the dialog and the workbook writer
live elsewhere.

It never invents a number. A quantity or rate that is absent or not a
positive value leaves Amount blank and produces a finding naming the
field, the same discipline lib/assembly_engine.py uses when a factor is
missing - a silently assumed 0 would price real work at nothing.

P6 assembly is a different thing: it derives binding wire, cover blocks
and labour as factors of rebar weight. These items are typed in.
"""


SITE_ITEM_HEADERS = (
    "Item Code",
    "Description",
    "Quantity",
    "Unit",
    "Rate",
    "Amount",
    "Remarks",
)

TOTAL_LABEL = "TOTAL"

AMOUNT_DECIMALS = 2


DEFAULT_KEY = "default"

DOCUMENTS_KEY = "by_document"

SOURCE_DOCUMENT = "document"
SOURCE_DEFAULT = "default"
SOURCE_EMPTY = "empty"


def _text(value, fallback=""):
    """Return a stripped text value, else the fallback."""
    if value is None:
        return fallback
    try:
        text = u"{0}".format(value).strip()
    except Exception:
        return fallback
    return text if text else fallback


def _positive_number(value):
    """Return value as a positive float, or None when it is not one.

    None is the honest answer for blank, non-numeric and non-positive
    input alike; validate_site_items says which field it was.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        number = float(u"{0}".format(value).strip())
    except (TypeError, ValueError, AttributeError):
        return None
    if number != number:          # NaN
        return None
    if number <= 0.0:
        return None
    return number


def normalize_site_item(raw, index=0):
    """Normalize one typed line item.

    Unusable values become None rather than a default, so validation can
    report them instead of the export quietly pricing something wrong.
    """
    raw = raw if isinstance(raw, dict) else {}
    return {
        "code": _text(raw.get("code")),
        "description": _text(raw.get("description")),
        "quantity": _positive_number(raw.get("quantity")),
        "unit": _text(raw.get("unit")),
        "rate": _positive_number(raw.get("rate")),
        "remarks": _text(raw.get("remarks")),
        "row": index + 1,
    }


def normalize_site_items(raw_items):
    """Normalize a whole list of typed line items."""
    if not isinstance(raw_items, (list, tuple)):
        return []
    return [normalize_site_item(item, i) for i, item in enumerate(raw_items)]


def site_item_amount(item):
    """Return Quantity x Rate, or None when either is unusable."""
    item = item if isinstance(item, dict) else {}
    quantity = item.get("quantity")
    rate = item.get("rate")
    if quantity is None or rate is None:
        return None
    return round(quantity * rate, AMOUNT_DECIMALS)


def site_item_label(item):
    """Name one line: its code, else its description, else its row number.

    Public because the Costing sheet needs exactly the same answer; a
    second copy of this rule would be free to drift from this one.
    """
    item = item if isinstance(item, dict) else {}
    return (item.get("code")
            or item.get("description")
            or "Row {0}".format(item.get("row")))


def validate_site_items(items):
    """Return plain-text findings for every unusable line item.

    An empty list means every item is complete and priceable. Findings
    are text so the dialog can show them and the harness can assert on
    them, matching how the classifier audit reports.
    """
    findings = []
    items = items or []

    codes = [item.get("code") for item in items if item.get("code")]
    for code in sorted(set(codes)):
        if codes.count(code) > 1:
            findings.append("Duplicate item code: {0}".format(code))

    for item in items:
        label = site_item_label(item)

        if not item.get("description"):
            findings.append("{0}: missing description".format(label))
        if item.get("quantity") is None:
            findings.append(
                "{0}: quantity is missing or not a positive number".format(label))
        if not item.get("unit"):
            findings.append("{0}: missing unit".format(label))
        if item.get("rate") is None:
            findings.append(
                "{0}: rate is missing or not a positive number".format(label))

    return findings


def priceable_site_items(items):
    """Return only the items that carry both a quantity and a rate."""
    return [item for item in (items or []) if site_item_amount(item) is not None]


def summarize_site_items(items):
    """Return counts and the priced total.

    unpriced_count is reported separately so a caller never reads the
    total as covering every line.
    """
    items = items or []
    total = 0.0
    priced = 0

    for item in items:
        amount = site_item_amount(item)
        if amount is None:
            continue
        priced += 1
        total += amount

    return {
        "count": len(items),
        "priced_count": priced,
        "unpriced_count": len(items) - priced,
        "amount_total": round(total, AMOUNT_DECIMALS),
    }


def build_site_items_table(items, include_total=True):
    """Return the export table: headers, one row per item, then TOTAL.

    A blank Amount cell is a real statement - that line could not be
    priced - and the TOTAL row sums only the lines that could.
    """
    items = items or []
    table = [list(SITE_ITEM_HEADERS)]

    for item in items:
        amount = site_item_amount(item)
        table.append([
            item.get("code", ""),
            item.get("description", ""),
            item.get("quantity") if item.get("quantity") is not None else "",
            item.get("unit", ""),
            item.get("rate") if item.get("rate") is not None else "",
            amount if amount is not None else "",
            item.get("remarks", ""),
        ])

    if include_total and items:
        summary = summarize_site_items(items)
        table.append([TOTAL_LABEL, "", "", "", "", summary["amount_total"], ""])

    return table


# ------------------------------------------------------------
# Store: a reusable default list plus a per-document list
#
# Owner decision (2026-09-19): a default list seeds a project the first
# time it is opened, and the project's own list is editable from there.
#
# The default therefore only ever SEEDS. Editing it later never reaches
# a document that already has its own list - otherwise changing the
# default would silently alter the BOQ of a project that was already
# priced and issued. Re-seeding is an explicit act:
# forget_document_site_items.
# ------------------------------------------------------------


def _document_key(document_title):
    """Return the store key for a document title, or '' when unusable."""
    return _text(document_title)


def normalize_site_items_store(raw):
    """Normalize the whole stored shape, tolerating anything on disk.

    A settings file written by an older build, hand-edited, or truncated
    must degrade to an empty store rather than raise while the dialog is
    opening.
    """
    raw = raw if isinstance(raw, dict) else {}

    documents = {}
    raw_documents = raw.get(DOCUMENTS_KEY)
    if isinstance(raw_documents, dict):
        for title, items in raw_documents.items():
            key = _document_key(title)
            if key:
                documents[key] = normalize_site_items(items)

    return {
        DEFAULT_KEY: normalize_site_items(raw.get(DEFAULT_KEY)),
        DOCUMENTS_KEY: documents,
    }


def resolve_site_items(store, document_title):
    """Return the items to show for one document, and where they came from.

    source is 'document' when the project has its own saved list,
    'default' when the default list is seeding it for the first time,
    and 'empty' when there is nothing to show. The caller needs the
    distinction: a seeded list is a starting point the user has not
    accepted yet.
    """
    store = normalize_site_items_store(store)
    key = _document_key(document_title)

    if key and key in store[DOCUMENTS_KEY]:
        return {"items": store[DOCUMENTS_KEY][key], "source": SOURCE_DOCUMENT}

    seeded = store[DEFAULT_KEY]
    if seeded:
        return {"items": [dict(item) for item in seeded], "source": SOURCE_DEFAULT}

    return {"items": [], "source": SOURCE_EMPTY}


def save_site_items(store, document_title, items):
    """Return a new store with this document's own list replaced.

    The default list is untouched: saving a project never edits the
    template other projects will be seeded from.
    """
    store = normalize_site_items_store(store)
    key = _document_key(document_title)
    if not key:
        return store

    documents = dict(store[DOCUMENTS_KEY])
    documents[key] = normalize_site_items(items)
    return {DEFAULT_KEY: store[DEFAULT_KEY], DOCUMENTS_KEY: documents}


def set_default_site_items(store, items):
    """Return a new store with a different default list.

    Documents that already carry their own list keep it. The new default
    applies only to documents opened for the first time from now on.
    """
    store = normalize_site_items_store(store)
    return {
        DEFAULT_KEY: normalize_site_items(items),
        DOCUMENTS_KEY: dict(store[DOCUMENTS_KEY]),
    }


def forget_document_site_items(store, document_title):
    """Return a new store with this document's list removed.

    The next resolve for that document seeds from the default again.
    This is the only way a changed default reaches an existing project,
    and it is deliberately explicit.
    """
    store = normalize_site_items_store(store)
    key = _document_key(document_title)
    documents = dict(store[DOCUMENTS_KEY])
    documents.pop(key, None)
    return {DEFAULT_KEY: store[DEFAULT_KEY], DOCUMENTS_KEY: documents}

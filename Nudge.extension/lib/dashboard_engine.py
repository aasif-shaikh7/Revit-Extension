# -*- coding: utf-8 -*-
"""Dashboard engine - P16: the whole BOQ on one page.

The workbook has a sheet for every view of the structure - by element, by
level, by grade, priced, revised. Someone opening it for the first time
wants five numbers and to know whether anything is wrong. The Dashboard
sheet gives them, right after the Summary cover:

  KEY FIGURES          concrete (m3), reinforcement (t), shuttering (m2),
                       structural elements, rebar sets
  CONCRETE BY GRADE    m3 per grade, an unrecorded grade last
  ELEMENTS             count per category, with its concrete and shuttering
  ESTIMATED COST       concrete, shuttering, steel and total, priced from
                       the rate database exactly as the Detailed BOQ is
  WARNINGS             what needs attention before the BOQ is issued
  SINCE <revision>     what moved since the issue it is compared against

Every figure is computed from the same plain numbers as the revision
snapshot (revision_engine.build_snapshot), which uses the Detailed BOQ's
own items, so the dashboard and the BOQ can never disagree about a
quantity. Figures are values, not formulas: the dashboard reports the
export as it was made.

Pure Python: no Revit symbols. Order comes from lists, never from a dict
(IronPython 2.7 does not keep a dict in insertion order), and no float()
sees None.
"""

DASHBOARD_SHEET_NAME = "Dashboard"

DASHBOARD_HEADERS = ("Section", "Item", "Value", "Unit", "Note")

SECTION_KEY = u"KEY FIGURES"
SECTION_GRADE = u"CONCRETE BY GRADE"
SECTION_ELEMENTS = u"ELEMENTS"
SECTION_COST = u"ESTIMATED COST"
SECTION_WARNINGS = u"WARNINGS"

ELEMENT_CATEGORIES = ("Beam", "Column", "Structure Wall", "Slab", "Foundation")


def _number(value):
    """The float in a cell, or None. None never reaches float()."""
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


def _grade_of(code):
    parts = code.split("|")
    return parts[2] if len(parts) > 2 else u""


def _category_of(code):
    parts = code.split("|")
    return parts[1] if len(parts) > 1 else u""


def _item_codes(item):
    """The rate codes an item is priced by - the Detailed BOQ's own."""
    from export_engine import NO_GRADE_LABEL
    from rate_database_engine import boq_rate_codes

    code = _text(item.get("code"))
    section = code.split("|")[0] if code else u""
    if section == u"A":
        grade = _grade_of(code)
        return "concrete", boq_rate_codes(
            "concrete", _category_of(code),
            u"" if grade == NO_GRADE_LABEL else grade)
    if section == u"B":
        return "shuttering", boq_rate_codes("shuttering", _category_of(code))
    if section == u"C":
        return "steel", boq_rate_codes("steel", diameter=_category_of(code))
    return "", []


def _estimate(items, rate_database, project_location, rate_date):
    """Priced totals: (per-group amounts, total, currency, priced, count)."""
    from rate_database_engine import price_boq_item

    groups = [("concrete", u"Concrete"), ("shuttering", u"Shuttering"),
              ("steel", u"Reinforcement steel")]
    amounts = dict((key, 0.0) for key, _label in groups)
    currencies = []
    priced = 0
    for item in items:
        kind, codes = _item_codes(item)
        quantity = _number(item.get("quantity"))
        if not kind or quantity is None:
            continue
        rate, _code, _note, currency = price_boq_item(
            rate_database, codes, item.get("unit", ""),
            project_location, rate_date)
        if rate is None:
            continue
        priced += 1
        amounts[kind] += quantity * rate
        if currency not in currencies:
            currencies.append(currency)
    total = sum(amounts[key] for key, _label in groups)
    return groups, amounts, total, currencies, priced


def build_dashboard_table(data_result, rate_database=None, project_location="",
                          rate_date="", unmapped_report=None,
                          revision_snapshots=None, bbs_steel=None):
    """The Dashboard sheet as a plain table: header, then one row per figure.

    A section's name is written on its first row only. `unmapped_report`
    is the P10 table (header + rows, Issue in the fourth column);
    `revision_snapshots` is the (previous, current) pair the BOQ Revision
    sheet uses, or None. `bbs_steel` is the model's BBS store: its steel
    is in the figures and the cost, as it is in the Detailed BOQ.
    """
    from export_engine import NO_GRADE_LABEL, identity_sort_key
    from revision_engine import build_snapshot

    data = data_result if isinstance(data_result, dict) else {}
    rebar_rows = data.get("Rebar") or []
    items = build_snapshot(data, rebar_rows, bbs_steel=bbs_steel)["items"]
    from bbs_steel_engine import bbs_total_kg, bbs_warnings, counted_entries
    bbs_kg = bbs_total_kg(bbs_steel)
    bbs_files = list((bbs_steel or {}).get("files") or [])

    table = [list(DASHBOARD_HEADERS)]

    def section(name, rows):
        for index, row in enumerate(rows):
            table.append([name if index == 0 else u""] + list(row))

    def total(prefix):
        return round(sum(_number(i.get("quantity")) or 0.0 for i in items
                         if _text(i.get("code")).startswith(prefix)), 2)

    element_rows = [(category, data.get(category) or [])
                    for category in ELEMENT_CATEGORIES]
    element_count = sum(len(rows) for _category, rows in element_rows)

    # KEY FIGURES
    steel_kg = total(u"C|")
    steel_note = u"{0:,.2f} kg".format(steel_kg) if steel_kg else u""
    if bbs_kg:
        steel_note += u", of which {0:,.2f} kg from BBS models".format(bbs_kg)
    key_rows = [
        [u"Concrete", total(u"A|"), u"m3", u""],
        [u"Reinforcement steel", round(steel_kg / 1000.0, 3), u"t", steel_note],
        [u"Shuttering", total(u"B|"), u"m2", u""],
        [u"Structural elements", element_count, u"nos",
         u"Beams, columns, walls, slabs and foundations"],
    ]
    # v1.46.0: a model with no rebar of its own shows its BBS models' bars
    # on the Rebar sheets, so it counts their sets here.
    bbs_sets = sum(int(entry.get("sets") or 0)
                   for entry in counted_entries(bbs_steel))
    if rebar_rows:
        key_rows.append([u"Rebar sets", len(rebar_rows), u"nos", u""])
    elif bbs_sets:
        key_rows.append([u"Rebar sets", bbs_sets, u"nos",
                         u"From the BBS models - see the Rebar sheet"])
    else:
        key_rows.append([u"Rebar sets", 0, u"nos", u"No rebar in this model"])
    if bbs_files:
        key_rows.append([u"BBS models", len(counted_entries(bbs_steel)), u"nos",
                         u"{0} of {1} counted - see the BBS Steel sheet".format(
                             len(counted_entries(bbs_steel)), len(bbs_files))])
    section(SECTION_KEY, key_rows)

    # CONCRETE BY GRADE - grades in number order, an unrecorded one last.
    grade_totals = []
    for item in items:
        code = _text(item.get("code"))
        if not code.startswith(u"A|"):
            continue
        grade = _grade_of(code)
        quantity = _number(item.get("quantity")) or 0.0
        for entry in grade_totals:
            if entry[0] == grade:
                entry[1] += quantity
                break
        else:
            grade_totals.append([grade, quantity])
    grade_totals.sort(key=lambda entry: (entry[0] == NO_GRADE_LABEL,
                                         identity_sort_key(entry[0])))
    if grade_totals:
        section(SECTION_GRADE, [
            [grade if grade != NO_GRADE_LABEL else u"Grade not recorded",
             round(quantity, 2), u"m3",
             u"Not priced until the grade is recorded"
             if grade == NO_GRADE_LABEL else u""]
            for grade, quantity in grade_totals])

    # ELEMENTS
    element_lines = []
    for category, rows in element_rows:
        if not rows:
            continue
        concrete = sum(_number(i.get("quantity")) or 0.0 for i in items
                       if _text(i.get("code")).startswith(u"A|" + category + u"|"))
        shutter = sum(_number(i.get("quantity")) or 0.0 for i in items
                      if _text(i.get("code")) == u"B|" + category)
        element_lines.append([category, len(rows), u"nos",
                              u"{0:,.2f} m3 concrete, {1:,.2f} m2 shuttering".format(
                                  concrete, shutter)])
    if element_lines:
        section(SECTION_ELEMENTS, element_lines)

    # ESTIMATED COST
    entries = list(rate_database or [])
    priceable = [i for i in items if _item_codes(i)[1]]
    if not entries:
        section(SECTION_COST, [[u"Not estimated", u"", u"",
                                u"The rate database is empty - add rates on the "
                                u"Rate Database tab"]])
    else:
        groups, amounts, grand, currencies, priced = _estimate(
            items, entries, project_location, rate_date)
        unit = currencies[0] if len(currencies) == 1 else u""
        basis = u"Without GST unless the rates include it; {0} of {1} BOQ items priced".format(
            priced, len(items))
        cost_rows = [[label, round(amounts[key], 2), unit, u""]
                     for key, label in groups]
        if len(currencies) > 1:
            cost_rows.append([u"Total", u"", u"",
                              u"Mixed currencies ({0}) - no total".format(
                                  u", ".join(c or u"none given" for c in currencies))])
        else:
            cost_rows.append([u"Total", round(grand, 2), unit, basis])
        section(SECTION_COST, cost_rows)

    # WARNINGS
    warnings = []
    no_grade_rows = 0
    no_volume_rows = 0
    for _category, rows in element_rows:
        for row in rows:
            try:
                grade = _text(row.get("Grade", ""))
                volume = _number(row.get("Qty: Volume (m3)"))
            except AttributeError:
                continue
            if not grade or grade == NO_GRADE_LABEL:
                no_grade_rows += 1
            if not volume:
                no_volume_rows += 1
    if no_grade_rows:
        no_grade_m3 = round(sum(q for g, q in grade_totals if g == NO_GRADE_LABEL), 2)
        warnings.append([u"Concrete grade not recorded", no_grade_rows, u"elements",
                         u"{0:,.2f} m3 cannot be priced".format(no_grade_m3)])
    if no_volume_rows:
        warnings.append([u"No concrete volume", no_volume_rows, u"elements",
                         u"Measured as zero in the BOQ"])
    if entries:
        unpriced = len(items) - _estimate(items, entries, project_location,
                                          rate_date)[4]
        if unpriced:
            warnings.append([u"BOQ items without a rate", unpriced, u"items",
                             u"See Rate Note on the Detailed BOQ"])
    issues = []
    for row in list(unmapped_report or [])[1:]:
        try:
            issue = _text(row[3])
        except (IndexError, TypeError):
            continue
        if not issue:
            continue
        for entry in issues:
            if entry[0] == issue:
                entry[1] += 1
                break
        else:
            issues.append([issue, 1])
    for issue, count in issues:
        warnings.append([issue, count, u"rows", u"Unmapped Elements sheet"])
    warnings.extend(bbs_warnings(bbs_steel))
    if rebar_rows and bbs_kg:
        warnings.append([u"Rebar in this model and in BBS models", len(rebar_rows),
                         u"sets", u"Both are counted - check the same bars are "
                         u"not in both"])
    if not warnings:
        warnings.append([u"None", u"", u"", u"Nothing needs attention"])
    section(SECTION_WARNINGS, warnings)

    # SINCE THE PREVIOUS ISSUE
    if revision_snapshots:
        from revision_engine import revision_display_name
        from model_change_engine import change_counts, has_element_records
        previous, current = revision_snapshots[0], revision_snapshots[1]

        def moved(prefix):
            def summed(snapshot):
                return sum(_number(i.get("quantity")) or 0.0
                           for i in (snapshot or {}).get("items") or []
                           if _text(i.get("code")).startswith(prefix))
            return round(summed(current) - summed(previous), 2)

        since = [
            [u"Concrete", moved(u"A|"), u"m3", u""],
            [u"Reinforcement steel", round(moved(u"C|") / 1000.0, 3), u"t", u""],
            [u"Shuttering", moved(u"B|"), u"m2", u""],
        ]
        if has_element_records(previous) and has_element_records(current):
            deleted, added, modified = change_counts(previous, current)
            since.append([u"Elements added / deleted / modified",
                          u"{0} / {1} / {2}".format(added, deleted, modified),
                          u"nos", u"Model Changes sheet"])
        section(u"SINCE {0}".format(
            revision_display_name(previous) or u"LAST ISSUE").upper(), since)

    return table

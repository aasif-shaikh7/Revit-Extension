# -*- coding: utf-8 -*-
"""P9/P10 validation engine - pure model-quality checks; no Revit symbols.

P10 (Unmapped Element Report) landed here first as the foundation of the
P9 validation engine (PROJECT_STRUCTURE.md section 9). It inspects only the
element rows the exporter already built plus plain routing-audit
dictionaries, so it adds no Revit reads and runs under CP3123 and IP27.

P9 adds the part PRD section 12 asks for on top of those findings: a
severity for each issue and a compact summary - counts plus a few short
lines - rather than a wall of raw rows. The same findings therefore serve
two audiences: the workbook sheet lists every one of them for fixing the
model, while the summary is what a person can read before deciding whether
to export at all.
"""

UNMAPPED_SHEET_NAME = "Unmapped Elements"

UNMAPPED_HEADERS = ("Category", "Element ID", "Level", "Issue", "Detail")

NO_GRADE = "(No Grade)"

CONCRETE_CATEGORIES = ("Beam", "Column", "Structure Wall", "Slab", "Foundation")

ISSUE_MISSING_GRADE = "Missing concrete grade"
ISSUE_MISSING_VOLUME = "Missing or zero volume"
ISSUE_MISSING_MATERIAL = "Missing structural material"
ISSUE_UNCERTAIN_ROUTING = "Uncertain Slab/Foundation mapping"
ISSUE_DUPLICATE_ROUTING = "Duplicate routing source"

SEVERITY_ERROR = "Error"
SEVERITY_WARNING = "Warning"

# What separates the two: an error means a number in the BOQ is wrong or
# missing, a warning means the numbers are right but something the BOQ
# groups or attributes them by is not. A missing volume contributes no
# concrete at all, and a duplicated routing source can be counted twice -
# both change a total. A missing grade, a missing material or an uncertain
# Slab/Foundation route still carry their full quantity; what suffers is
# which heading it lands under.
ISSUE_SEVERITY = {
    ISSUE_MISSING_VOLUME: SEVERITY_ERROR,
    ISSUE_DUPLICATE_ROUTING: SEVERITY_ERROR,
    ISSUE_MISSING_GRADE: SEVERITY_WARNING,
    ISSUE_MISSING_MATERIAL: SEVERITY_WARNING,
    ISSUE_UNCERTAIN_ROUTING: SEVERITY_WARNING,
}

# An issue this engine does not know is reported, not silently dropped.
# Treating it as an error would overstate it; hiding it would lose it.
UNKNOWN_ISSUE_SEVERITY = SEVERITY_WARNING

MISSING_GRADE_DETAIL = (
    "Neither GRADE OF CONCRETE nor Grade contains a recognized "
    "IS 456 grade (M10-M80) on the element or its type"
)


def _text(value):
    """Return stripped display text, never None."""
    try:
        return str(value if value is not None else "").strip()
    except Exception:
        return ""


def _is_missing_material(value):
    """True when a resolved material name gives the BOQ nothing to use."""
    return _text(value) in ("", "<By Category>", "<None>")


def _is_missing_volume(value):
    """True when a volume cell adds nothing to the BOQ concrete total."""
    if value in ("", None):
        return True
    try:
        return float(value) <= 0
    except (TypeError, ValueError):
        return True


def collect_routing_findings(detail_results, duplicate_ids=None):
    """Flatten classifier audit rows into plain, Revit-free findings.

    detail_results are the dictionaries returned by the Revit-bound
    classification_audit_detail_results(); only their plain text keys are
    read. duplicate_ids lists the source/destination duplicate Element IDs.
    """
    duplicates = set(_text(value) for value in (duplicate_ids or []))
    findings = []
    seen = set()

    def add(element_id, issue, detail):
        key = (element_id, issue)
        if key in seen:
            return
        seen.add(key)
        findings.append({
            "element_id": element_id,
            "issue": issue,
            "detail": detail,
        })

    for result in detail_results or []:
        try:
            element_id = _text(result.get("element_id"))
            subtype = _text(result.get("subtype"))
            logical_group = _text(result.get("logical_group"))
            family = _text(result.get("family"))
            type_name = _text(result.get("type_name"))
            reason = _text(result.get("reason"))
        except AttributeError:
            continue

        identity = " / ".join(
            part for part in (family, type_name) if part
        ) or "-"

        if subtype == "Other" or logical_group not in ("Slab", "Foundation"):
            add(
                element_id,
                ISSUE_UNCERTAIN_ROUTING,
                "{0} | Family/Type: {1}".format(
                    reason or "Unknown identity", identity
                )
            )

        if element_id in duplicates:
            add(
                element_id,
                ISSUE_DUPLICATE_ROUTING,
                "Collected more than once during Slab/Foundation routing; "
                "exported once"
            )

    for duplicate_id in sorted(duplicates):
        add(
            duplicate_id,
            ISSUE_DUPLICATE_ROUTING,
            "Collected more than once during Slab/Foundation routing; "
            "exported once"
        )

    return findings


def build_unmapped_element_report(data_result, routing_findings=None,
                                  element_materials=None):
    """Return the P10 report table: headers plus one row per finding.

    Only elements present in this export are reported, so Slab/Foundation
    subtype filters and "Export selected only" never list elements that are
    absent from the workbook. Grade and volume are judged only when the row
    carries those columns. A header-only table means nothing was found.

    element_materials maps Element ID to the resolved structural material
    name. Material is judged only for IDs present in that mapping, so an
    export that never resolved materials reports no material findings.
    """
    data = data_result if isinstance(data_result, dict) else {}
    table = [list(UNMAPPED_HEADERS)]
    exported = {}
    materials = element_materials if isinstance(element_materials, dict) else None

    for category in CONCRETE_CATEGORIES:
        for row in data.get(category) or []:
            try:
                element_id = _text(row.get("Element ID"))
                level = _text(row.get("Level"))
            except AttributeError:
                continue

            if element_id not in exported:
                exported[element_id] = (category, level)

            if "Grade" in row:
                grade = _text(row.get("Grade"))
                if not grade or grade == NO_GRADE:
                    table.append([
                        category, element_id, level, ISSUE_MISSING_GRADE,
                        MISSING_GRADE_DETAIL
                    ])

            if (
                materials is not None
                and element_id in materials
                and _is_missing_material(materials.get(element_id))
            ):
                table.append([
                    category, element_id, level, ISSUE_MISSING_MATERIAL,
                    "No Structural Material on the element or its type; "
                    "material-wise quantities cannot use this element"
                ])

            if (
                "Qty: Volume (m3)" in row
                and _is_missing_volume(row.get("Qty: Volume (m3)"))
            ):
                table.append([
                    category, element_id, level, ISSUE_MISSING_VOLUME,
                    "Revit reported no positive computed volume; this "
                    "element adds no concrete to the BOQ"
                ])

    for finding in routing_findings or []:
        try:
            element_id = _text(finding.get("element_id"))
            issue = _text(finding.get("issue"))
            detail = _text(finding.get("detail"))
        except AttributeError:
            continue
        if not issue or element_id not in exported:
            continue
        category, level = exported[element_id]
        table.append([category, element_id, level, issue, detail])

    return table


def issue_severity(issue):
    """Return the severity for one issue label."""
    return ISSUE_SEVERITY.get(_text(issue), UNKNOWN_ISSUE_SEVERITY)


def summarize_validation_findings(report_table):
    """Count the report's findings by issue, worst first.

    Takes the table build_unmapped_element_report() returns - headers plus
    one row per finding - so the summary and the workbook sheet can never
    disagree about what was found. A header-only table summarizes to zero
    of everything.

    Returns a list of dicts: issue, severity, count, and categories, a
    count per element category so a line can say where the trouble is
    without listing every Element ID.
    """
    rows = list(report_table or [])[1:]
    order = []
    grouped = {}

    for row in rows:
        try:
            category = _text(row[0])
            issue = _text(row[3])
        except (IndexError, TypeError):
            continue
        if not issue:
            continue
        if issue not in grouped:
            grouped[issue] = {
                "issue": issue,
                "severity": issue_severity(issue),
                "count": 0,
                "categories": {},
            }
            order.append(issue)
        entry = grouped[issue]
        entry["count"] += 1
        if category:
            entry["categories"][category] = (
                entry["categories"].get(category, 0) + 1)

    summary = [grouped[issue] for issue in order]
    # Errors first, then the biggest counts; the issue label breaks ties so
    # the same findings always summarize in the same order.
    summary.sort(key=lambda entry: (
        0 if entry["severity"] == SEVERITY_ERROR else 1,
        -entry["count"],
        entry["issue"],
    ))
    return summary


def count_validation_findings(report_table):
    """Return (errors, warnings, total) for one report table."""
    errors = 0
    warnings = 0
    for entry in summarize_validation_findings(report_table):
        if entry["severity"] == SEVERITY_ERROR:
            errors += entry["count"]
        else:
            warnings += entry["count"]
    return errors, warnings, errors + warnings


def build_validation_report_lines(report_table, max_lines=8):
    """Build the compact pre-export report PRD section 12 asks for.

    One line per issue, worst first, each naming the categories it came
    from. PRD section 12 is explicit that this stays compact - the full
    list belongs in the workbook sheet, not in a dialog - so the lines are
    capped and the remainder is counted rather than printed.
    """
    try:
        limit = max(1, int(max_lines))
    except (TypeError, ValueError):
        limit = 8

    entries = summarize_validation_findings(report_table)
    lines = []

    for entry in entries[:limit]:
        categories = entry["categories"]
        if categories:
            named = sorted(
                categories.items(), key=lambda item: (-item[1], item[0]))
            where = " ({0})".format(
                ", ".join("{0} {1}".format(name, count)
                          for name, count in named))
        else:
            where = ""
        lines.append("{0}: {1} x {2}{3}".format(
            entry["severity"], entry["count"], entry["issue"], where))

    if len(entries) > limit:
        lines.append("...and {0} more issue type(s)".format(
            len(entries) - limit))

    return lines


def build_validation_report(report_table, max_lines=8):
    """Return the whole compact report as one dict.

    `ok` is about errors only. A warning is worth reading before export but
    is not a reason to stop: the quantities it describes are still right.
    """
    errors, warnings, total = count_validation_findings(report_table)
    lines = build_validation_report_lines(report_table, max_lines=max_lines)

    if total:
        headline = "{0} error(s), {1} warning(s) in {2} finding(s)".format(
            errors, warnings, total)
    else:
        headline = "No validation findings"

    return {
        "ok": errors == 0,
        "errors": errors,
        "warnings": warnings,
        "total": total,
        "headline": headline,
        "lines": lines,
        "text": "\n".join([headline] + lines) if lines else headline,
        "issues": summarize_validation_findings(report_table),
    }

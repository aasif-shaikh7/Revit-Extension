# -*- coding: utf-8 -*-
"""P9/P10 validation engine - pure model-quality checks; no Revit symbols.

P10 (Unmapped Element Report) lands here first as the foundation of the
planned P9 validation engine (PROJECT_STRUCTURE.md section 9). It inspects
only the element rows the exporter already built plus plain routing-audit
dictionaries, so it adds no Revit reads and runs under CP3123 and IP27.
"""

UNMAPPED_SHEET_NAME = "Unmapped Elements"

UNMAPPED_HEADERS = ("Category", "Element ID", "Level", "Issue", "Detail")

NO_GRADE = "(No Grade)"

CONCRETE_CATEGORIES = ("Beam", "Column", "Structure Wall", "Slab", "Foundation")

ISSUE_MISSING_GRADE = "Missing concrete grade"
ISSUE_MISSING_VOLUME = "Missing or zero volume"
ISSUE_UNCERTAIN_ROUTING = "Uncertain Slab/Foundation mapping"
ISSUE_DUPLICATE_ROUTING = "Duplicate routing source"


def _text(value):
    """Return stripped display text, never None."""
    try:
        return str(value if value is not None else "").strip()
    except Exception:
        return ""


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


def build_unmapped_element_report(data_result, routing_findings=None):
    """Return the P10 report table: headers plus one row per finding.

    Only elements present in this export are reported, so Slab/Foundation
    subtype filters and "Export selected only" never list elements that are
    absent from the workbook. Grade and volume are judged only when the row
    carries those columns. A header-only table means nothing was found.
    """
    data = data_result if isinstance(data_result, dict) else {}
    table = [list(UNMAPPED_HEADERS)]
    exported = {}

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
                        "No grade parameter, material name or identity "
                        "token resolved to an IS 456 grade (M10-M80)"
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

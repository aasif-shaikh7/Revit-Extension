# -*- coding: utf-8 -*-
"""Pure P6 structural assembly rules; no Revit API dependencies."""

ASSEMBLY_PROFILE_VERSION = "1.0.0"

DEFAULT_ASSEMBLY_PROFILE = {
    "id": "global-custom",
    "name": "Global / Custom",
    "edition": "1.0.0",
    "source": "Project specification / applicable local SOR",
    "binding_wire_factor": None,
    "cover_block_factor": None,
    "labour_factor": None,
}


def normalize_assembly_profile(raw_profile=None):
    """Return a complete, safe profile without inventing missing factors."""
    raw = raw_profile if isinstance(raw_profile, dict) else {}
    result = {}
    for key in ("id", "name", "edition", "source"):
        try:
            value = raw.get(key, DEFAULT_ASSEMBLY_PROFILE[key])
            result[key] = str(value or "").strip() or DEFAULT_ASSEMBLY_PROFILE[key]
        except (TypeError, ValueError):
            result[key] = DEFAULT_ASSEMBLY_PROFILE[key]
    for key in ("binding_wire_factor", "cover_block_factor", "labour_factor"):
        try:
            value = float(raw.get(key, DEFAULT_ASSEMBLY_PROFILE[key]))
            result[key] = value if value >= 0 else None
        except (TypeError, ValueError):
            result[key] = None
    return result


def _assembly_sum(rows, key):
    total = 0.0
    found = False
    for row in rows or []:
        try:
            value = float(row.get(key, ""))
            total += value
            found = True
        except (TypeError, ValueError, AttributeError):
            pass
    return round(total, 6) if found else ""


def build_structural_assembly_table(data_result, profile=None):
    """Build auditable category/component quantities from existing take-offs."""
    profile = normalize_assembly_profile(profile)
    headers = ["Category", "Component", "Quantity", "Unit", "Basis", "Status", "Profile", "Source"]
    table = [headers]
    rebar_by_host = {}
    for row in data_result.get("Rebar", []) or []:
        host = str(row.get("Rebar: Host Category", "") or "")
        mapped = {"Structural Framing": "Beam", "Structural Columns": "Column",
                  "Walls": "Structure Wall", "Floors": "Slab",
                  "Structural Foundations": "Foundation"}.get(host)
        if mapped:
            try:
                rebar_by_host[mapped] = rebar_by_host.get(mapped, 0.0) + float(
                    row.get("Rebar: Total Weight (kg)", ""))
            except (TypeError, ValueError):
                pass
    for category in ("Beam", "Column", "Structure Wall", "Slab", "Foundation"):
        rows = data_result.get(category, []) or []
        if not rows:
            continue
        measured = (
            ("Concrete", _assembly_sum(rows, "Qty: Volume (m3)"), "m3", "Model volume"),
            ("Reinforcement", round(rebar_by_host.get(category, 0.0), 6) or "", "kg", "Hosted Rebar weight"),
            ("Formwork", _assembly_sum(rows, "Qty: Shuttering (m2)"), "m2", "Formwork rule"),
        )
        for component, quantity, unit, basis in measured:
            table.append([category, component, quantity, unit, basis,
                          "Measured" if quantity != "" else "Unavailable", profile["name"], profile["source"]])
        for component, key, unit in (("Binding Wire", "binding_wire_factor", "kg"),
                                     ("Cover Blocks", "cover_block_factor", "each"),
                                     ("Labour", "labour_factor", "day")):
            factor = profile[key]
            steel = rebar_by_host.get(category)
            quantity = round(steel * factor, 6) if factor is not None and steel is not None else ""
            table.append([category, component, quantity, unit, "Configurable factor x Rebar kg",
                          "Assumption" if quantity != "" else "Input required", profile["name"], profile["source"]])
    return table

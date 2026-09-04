# -*- coding: utf-8 -*-
"""Formwork engine - configurable shuttering rules (P3).

Moved verbatim from BOQ.pushbutton/script.py in the v1.8.6 module split
(PROJECT_STRUCTURE.md section 9). Pure Python: re only - no Revit
symbols. Owns the DEFAULT_FORMWORK_RULES / formwork_rules module state;
script.py imports the same dict object, so the dialog checkbox handlers
keep mutating it in place exactly as before.
"""
import re



# P3 slice 2: configurable formwork (shuttering) rules. The site-format
# workbook's SHUTTERING column obeys these rules: "enabled" switches the
# formwork takeoff off entirely, and the per-category "deduction_pct"
# (0-100) applies a deterministic percentage deduction - e.g. a junction
# allowance where beams frame into columns. Persisted in the settings
# JSON under the "formwork" key; the IncludeFormworkCheck checkbox
# controls "enabled" from the dialog footer.
DEFAULT_FORMWORK_RULES = {
    "enabled": True,
    "deduction_pct": {
        "Column": 0.0,
        "Beam": 0.0,
        "Structure Wall": 0.0,
        "Slab": 0.0,
        "Foundation": 0.0
    }
}

# Runtime copy the dialog and export mutate; seeded from the defaults so
# a missing/invalid settings entry still yields sane behaviour.
formwork_rules = {
    "enabled": DEFAULT_FORMWORK_RULES["enabled"],
    "deduction_pct": dict(DEFAULT_FORMWORK_RULES["deduction_pct"])
}



def compute_shuttering_area(
        category_name,
        length_m="",
        width_m="",
        height_m="",
        area_m2="",
        factor=1.0,
        enabled=True):
    """
    P3/site-format formwork (SHUTTERING) rules, deterministic and pure.

      Column     : perimeter of the four sides x height
                   = 2 * (L + W) * H
      Beam       : soffit width plus two side faces along the length
                   = (W + 2 * H) * L
      Structure Wall: gross two-face contact area = 2 * L * H
      Slab       : soffit contact area = plan area
      Foundation : footing side faces = 2 * (L + W) * H

    factor (>= 0) scales the raw contact area - the caller converts the
    configurable per-category deduction percentage (junction allowance)
    into a multiplier, keeping this function geometry-only.

    enabled=False short-circuits to "" so the SHUTTERING column goes
    blank when the user turns formwork off.

    Returns the area rounded to 2 decimals, or "" when the dimensions
    required by the rule are unavailable so the cell stays blank.
    """
    if not enabled:
        return ""

    def to_float(value):
        try:
            return float(value)
        except:
            return None

    if category_name == "Slab":

        area_value = to_float(area_m2)

        if area_value is not None and area_value > 0:
            scaled_area = area_value * _safe_factor(factor)

            if scaled_area <= 0:
                return ""

            return round(scaled_area, 2)

        return ""

    length_value = to_float(length_m)
    width_value = to_float(width_m)
    height_value = to_float(height_m)

    if height_value is None:
        return ""

    if length_value is None:
        return ""

    if category_name == "Structure Wall":
        shuttering = 2.0 * length_value * height_value

    elif width_value is None:
        return ""

    elif category_name == "Column":
        shuttering = 2.0 * (length_value + width_value) * height_value

    elif category_name == "Beam":
        shuttering = (width_value + 2.0 * height_value) * length_value

    elif category_name == "Foundation":
        shuttering = 2.0 * (length_value + width_value) * height_value

    else:
        return ""

    shuttering *= _safe_factor(factor)

    if shuttering <= 0:
        return ""

    return round(shuttering, 2)


def _safe_factor(factor):
    """
    P3: clamp the configurable deduction multiplier to a sane range.
    Negative factors are treated as 1.0 (no deduction); anything that
    fails to parse also falls back to 1.0 so a bad settings value can
    never zero out or invert the takeoff silently.
    """
    try:
        multiplier = float(factor)
    except:
        return 1.0

    if multiplier < 0.0:
        return 1.0

    return multiplier


def normalize_formwork_rules(raw_rules):
    """
    P3: merge a raw settings-JSON fragment into clean formwork rules.

    Anything missing or invalid falls back to the defaults, percentages
    are clamped to 0-100, and unknown categories are ignored - so a
    hand-edited or older settings file can never break the export.
    """
    clean = {
        "enabled": DEFAULT_FORMWORK_RULES["enabled"],
        "deduction_pct": dict(DEFAULT_FORMWORK_RULES["deduction_pct"])
    }

    if not isinstance(raw_rules, dict):
        return clean

    clean["enabled"] = bool(raw_rules.get("enabled", True))

    raw_percentages = raw_rules.get("deduction_pct", {})

    if isinstance(raw_percentages, dict):

        for category in (
            "Column", "Beam", "Structure Wall", "Slab", "Foundation"
        ):

            try:
                value = float(
                    raw_percentages.get(category, 0.0)
                )
            except:
                value = 0.0

            if value < 0.0:
                value = 0.0

            if value > 100.0:
                value = 100.0

            clean["deduction_pct"][category] = value

    return clean


def get_formwork_factor(category_name):
    """
    P3: multiplier for one category from the runtime formwork rules:
    1.0 with no deduction, 1 - pct/100 with a configured junction
    allowance. Never throws; defaults to no deduction.
    """
    try:
        percentage = float(
            formwork_rules.get("deduction_pct", {}).get(
                category_name, 0.0
            )
        )
    except:
        percentage = 0.0

    if percentage < 0.0:
        percentage = 0.0

    if percentage > 100.0:
        percentage = 100.0

    return 1.0 - (percentage / 100.0)


def is_formwork_enabled():
    """
    P3: whether the formwork takeoff is switched on. Reads the runtime
    rules dict; defaults to True when the entry is missing/invalid.
    """
    try:
        return bool(formwork_rules.get("enabled", True))
    except:
        return True


def build_shuttering_formula(category_name, l_col, w_col, h_col, factor):
    """
    Build an Excel formula string for shuttering area based on category.

    Formulas (matching compute_shuttering_area logic):
      Column:    2*(L+W)*H
      Beam:      (W+2*H)*L
      Structure Wall: 2*L*H (gross two-face area)
      Slab:      L*W (soffit = plan area)
      Foundation: 2*(L+W)*H

    factor is (1 - deduction_pct/100), applied as a multiplier.
    Returns a formula string like "=ROUND(2*(F7+G7)*H7*0.95, 2)".
    """
    try:
        factor_val = float(factor)
        if factor_val < 0 or factor_val > 1:
            factor_val = 1.0
    except:
        factor_val = 1.0

    factor_str = "*{0}".format(factor_val) if factor_val != 1.0 else ""

    if category_name == "Column":
        return "=ROUND(2*({0}+{1})*{2}{3}, 2)".format(l_col, w_col, h_col, factor_str)
    elif category_name == "Beam":
        return "=ROUND(({1}+2*{2})*{0}{3}, 2)".format(l_col, w_col, h_col, factor_str)
    elif category_name == "Structure Wall":
        return "=ROUND(2*{0}*{2}{3}, 2)".format(l_col, w_col, h_col, factor_str)
    elif category_name == "Slab":
        return "=ROUND({0}*{1}{2}, 2)".format(l_col, w_col, factor_str)
    elif category_name == "Foundation":
        return "=ROUND(2*({0}+{1})*{2}{3}, 2)".format(l_col, w_col, h_col, factor_str)
    return ""

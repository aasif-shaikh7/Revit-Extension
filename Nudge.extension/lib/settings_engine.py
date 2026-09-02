# -*- coding: utf-8 -*-
"""Settings engine - JSON persistence for the RCC BOQ tool.

Moved verbatim from BOQ.pushbutton/script.py in the v1.8.6 module split
(PROJECT_STRUCTURE.md section 9). Pure Python: os / json only - no
Revit symbols, importable in plain Python.
"""
import os
import json



def get_settings_path():
    """Return the JSON settings path stored in the user profile folder."""
    home = ""

    try:
        home = os.path.expanduser("~")
    except:
        home = ""

    return os.path.join(
        home,
        ".rcc_boq_settings.json"
    )


def load_app_settings():
    """Load saved settings (selections, filters, last folder) or empty dict."""
    result = {}

    try:
        path = get_settings_path()

        if os.path.exists(path):

            with open(path, "r") as handle:

                loaded = json.load(handle)

                if isinstance(loaded, dict):
                    result = loaded

    except:
        pass

    return result


def save_app_settings(settings):
    """Persist the given settings dict to the JSON settings file."""
    try:
        path = get_settings_path()

        with open(path, "w") as handle:

            json.dump(
                settings,
                handle,
                indent=2
            )

    except:
        pass


# ============================================================
# PARAMETER METADATA ENGINE
# ============================================================

# Stores metadata in the same Beam / Column / Slab / Foundation
# structure used by the existing parameter-selection system.
parameter_metadata = {
    "Beam": [],
    "Column": [],
    "Slab": [],
    "Foundation": []
}


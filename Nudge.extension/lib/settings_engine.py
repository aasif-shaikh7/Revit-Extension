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


def get_backup_path():
    """The previous settings file, kept beside the live one."""
    return get_settings_path() + ".bak"


def _read_settings_file(path):
    """The dict in this file, or None when it cannot be read."""
    try:
        if not os.path.exists(path):
            return None
        with open(path, "r") as handle:
            loaded = json.load(handle)
        return loaded if isinstance(loaded, dict) else None
    except:
        return None


def load_app_settings():
    """Load saved settings (selections, filters, last folder) or empty dict.

    A settings file that is missing, empty or corrupt falls back to the
    backup written by the previous save, so a half-written file cannot
    cost the user their parameter selections and rates.
    """
    result = _read_settings_file(get_settings_path())

    if result is None:
        result = _read_settings_file(get_backup_path())

    return result if result is not None else {}


def save_app_settings(settings):
    """Persist the given settings dict to the JSON settings file.

    Written through a temporary file, with the previous file kept as
    `.bak`: a crash in the middle of a write can never leave a truncated
    settings file, and the last good copy is always one file away. On
    2026-09-22 a wiped list cost the owner six Rebar parameters with no
    copy to go back to.
    """
    path = get_settings_path()
    temp_path = path + ".tmp"

    try:
        payload = json.dumps(settings, indent=2)
    except:
        return

    try:
        with open(temp_path, "w") as handle:
            handle.write(payload)
    except:
        return

    try:
        if os.path.exists(path):
            backup = get_backup_path()
            if os.path.exists(backup):
                os.remove(backup)
            os.rename(path, backup)
    except:
        pass

    try:
        os.rename(temp_path, path)
    except:
        # The rename is the only step that must not fail silently in a
        # way that leaves nothing behind: fall back to a direct write.
        try:
            with open(path, "w") as handle:
                handle.write(payload)
            os.remove(temp_path)
        except:
            pass


# ============================================================
# PARAMETER METADATA ENGINE
# ============================================================

# Stores metadata in the same structural-category shape used by selection.
# structure used by the existing parameter-selection system.
parameter_metadata = {
    "Beam": [],
    "Column": [],
    "Structure Wall": [],
    "Slab": [],
    "Foundation": [],
    "Rebar": []
}

# -*- coding: utf-8 -*-
"""Rate Database tab (P12) - the dialog's handlers for this tab.

Moved out of BOQ.pushbutton/script.py in the P8 split (v1.38.0), where
this tab alone had grown script.py by a few hundred lines. The handler
code is the code that ran there, unchanged except for its indentation
and one thing: the document now arrives as its title string, so nothing
in lib/ holds a Revit object.

WPF-bound, not an engine: the handlers read and write the dialog's
controls through `host.window`, so only the dialog loads this module.
It imports no Revit or pyRevit symbol. The list it edits - rate_db_state and rate_db_ready -
belongs to script.py and is passed in by reference, because the export
and the settings save read the same objects.

    handlers = attach(host)
    handlers["wire_controls"]()

`host` carries: window, document_title, set_status, load_app_settings, ParameterItem, safe_text, rate_db_state, rate_db_ready.
"""


def attach(host):
    """Build this tab's handlers around one open dialog.

    Returns the entry points script.py calls; every other handler is
    reached through the controls it is wired to.
    """
    window = host.window
    document_title = host.document_title
    set_status = host.set_status
    load_app_settings = host.load_app_settings
    ParameterItem = host.ParameterItem
    safe_text = host.safe_text
    rate_db_state = host.rate_db_state
    rate_db_ready = host.rate_db_ready

    # ------------------------------------------------------------
    # P12: RATE DATABASE TAB
    #
    # The rates live in rate_db_state, with the same contract as the
    # Rate Analysis tab: every handler rewrites the list and redraws,
    # so what is on screen is what is saved and exported. The
    # project's location is kept per document.
    # ------------------------------------------------------------

    RATE_DB_FIELD_CONTROLS = (
        ("item_code", "RateDbItemCode"),
        ("description", "RateDbDescription"),
        ("unit", "RateDbUnit"),
        ("rate", "RateDbRate"),
        ("currency", "RateDbCurrency"),
        ("location", "RateDbLocation"),
        ("vendor", "RateDbVendor"),
        ("effective_date", "RateDbEffectiveDate"),
        ("source", "RateDbSourceText"),
    )

    def rate_db_display_text(entry):
        """One readable line: code, rate, where, from when, status."""
        from rate_database_engine import rate_entry_status

        if entry.get("rate") is None:
            rate_text = "no rate"
        else:
            rate_text = u"{0:.2f} {1} / {2}".format(
                entry["rate"], entry.get("currency") or "",
                entry.get("unit") or "unit").replace("  ", " ")
        return u"{0}  |  {1}  |  {2}  |  from {3}  |  {4}".format(
            entry.get("item_code") or "(no code)",
            rate_text,
            entry.get("location") or "any location",
            entry.get("effective_date") or "(no date)",
            rate_entry_status(entry)
        )

    def rate_db_refresh(select_index=-1):
        """Redraw the list and the summary line."""
        from rate_database_engine import (
            STATUS_READY, STATUS_SAMPLE, rate_entry_status)

        try:
            list_box = window.FindName("RateDbList")
            if list_box is not None:
                list_box.Items.Clear()
                for entry in rate_db_state:
                    list_box.Items.Add(
                        ParameterItem(rate_db_display_text(entry))
                    )
                if 0 <= select_index < len(rate_db_state):
                    list_box.SelectedIndex = select_index
        except:
            pass

        try:
            summary_box = window.FindName("RateDbSummary")
            if summary_box is None:
                return
            if not rate_db_state:
                summary_box.Text = (
                    "No rates. Rates added here export to their own "
                    "Rate Database sheet."
                )
                return
            statuses = [rate_entry_status(e) for e in rate_db_state]
            ready = statuses.count(STATUS_READY)
            samples = statuses.count(STATUS_SAMPLE)
            pending = len(statuses) - ready - samples
            text = "{0} rate(s) | {1} ready".format(len(statuses), ready)
            if samples:
                text += " | {0} sample - not real rates".format(samples)
            if pending:
                text += " | {0} need input".format(pending)

            # Rates for a place that is not one of this project's
            # levels never price it - right for a Dubai rate on a
            # Navsari job, wrong for a misspelt 'Gujrat'. Say which.
            from rate_database_engine import unmatched_places
            location_box = window.FindName("RateDbProjectLocation")
            project_location = (
                location_box.Text if location_box is not None else "")
            others = unmatched_places(rate_db_state, project_location)
            if others:
                text += (
                    u" | Not used for this project: {0} - check the "
                    u"spelling if one should apply here".format(
                        ", ".join(others)))
            summary_box.Text = text
        except:
            pass

    def rate_db_fill_fields(entry):
        """Load one rate into the entry boxes for editing."""
        for key, control_name in RATE_DB_FIELD_CONTROLS:
            try:
                control = window.FindName(control_name)
                if control is None:
                    continue
                value = entry.get(key)
                control.Text = "" if value is None else str(value)
            except:
                pass

    def rate_db_read_fields():
        """Read the boxes: (normalized entry, problem text or '')."""
        from rate_database_engine import normalize_rate_entry

        values = {}
        for key, control_name in RATE_DB_FIELD_CONTROLS:
            try:
                control = window.FindName(control_name)
                values[key] = control.Text if control is not None else ""
            except:
                values[key] = ""
        entry = normalize_rate_entry(values)

        problem = ""
        if not entry.get("item_code"):
            problem = "Give the rate an item code"
        elif (safe_text(values.get("rate"), "").strip()
                and entry.get("rate") is None):
            problem = "Rate must be a number, zero or more"
        elif entry.get("date_invalid"):
            problem = "Effective Date must be YYYY-MM-DD, e.g. 2026-09-22"
        return entry, problem

    def rate_db_clear_fields(sender=None, args=None):
        for _key, control_name in RATE_DB_FIELD_CONTROLS:
            try:
                control = window.FindName(control_name)
                if control is not None:
                    control.Text = ""
            except:
                pass
        set_status("Rate database | Fields cleared", "info")

    def rate_db_selected_index():
        try:
            list_box = window.FindName("RateDbList")
            if list_box is None:
                return -1
            return int(list_box.SelectedIndex)
        except:
            return -1

    def rate_db_add(sender=None, args=None):
        """Add the typed rate. Refuses a bad figure or a duplicate."""
        entry, problem = rate_db_read_fields()
        if problem:
            set_status("Rate database | " + problem, "warning")
            return

        # One code may have many rates - one per place and date - but
        # not two for the same place and day.
        from rate_database_engine import find_rate_entry_conflict

        if find_rate_entry_conflict(rate_db_state, entry) >= 0:
            set_status(
                "Rate database | {0} already has a rate for this "
                "location and date - select it and use Update "
                "selected".format(entry["item_code"]),
                "warning"
            )
            return

        rate_db_state.append(entry)
        rate_db_refresh(len(rate_db_state) - 1)
        set_status(
            "Rate database | Added {0}".format(entry["item_code"]),
            "success"
        )

    def rate_db_update(sender=None, args=None):
        index = rate_db_selected_index()
        if not (0 <= index < len(rate_db_state)):
            set_status(
                "Rate database | Select a rate to update", "warning")
            return

        entry, problem = rate_db_read_fields()
        if problem:
            set_status("Rate database | " + problem, "warning")
            return

        from rate_database_engine import find_rate_entry_conflict

        if find_rate_entry_conflict(rate_db_state, entry, index) >= 0:
            set_status(
                "Rate database | Another rate already covers {0} for "
                "this location and date".format(entry["item_code"]),
                "warning"
            )
            return

        rate_db_state[index] = entry
        rate_db_refresh(index)
        set_status(
            "Rate database | Updated {0}".format(entry["item_code"]),
            "success"
        )

    def rate_db_remove(sender=None, args=None):
        index = rate_db_selected_index()
        if not (0 <= index < len(rate_db_state)):
            set_status(
                "Rate database | Select a rate to remove", "warning")
            return

        removed = rate_db_state.pop(index)
        rate_db_refresh()
        set_status(
            "Rate database | Removed {0}".format(
                removed.get("item_code") or "rate"),
            "info"
        )

    def rate_db_selection_changed(sender=None, args=None):
        index = rate_db_selected_index()
        if 0 <= index < len(rate_db_state):
            rate_db_fill_fields(rate_db_state[index])

    def rate_db_load_saved():
        """Load the saved rates and this project's location."""
        settings = {}
        try:
            from rate_database_engine import (
                get_project_location, load_rate_database)

            settings = load_app_settings()
            del rate_db_state[:]
            rate_db_state.extend(load_rate_database(settings))
            # Only now does the list on screen stand for the saved one.
            rate_db_ready[0] = True

            location_box = window.FindName("RateDbProjectLocation")
            if location_box is not None:
                location_box.Text = get_project_location(
                    settings, document_title)
        except:
            del rate_db_state[:]

        try:
            source_box = window.FindName("RateDbSource")
            if source_box is not None:
                source_box.Text = (
                    "Showing the saved rates; they are written back "
                    "when you export or close."
                    if rate_db_state
                    else "No rates saved yet."
                )
        except:
            pass

        rate_db_refresh()

    def rate_db_wire_controls():
        """Attach the tab's handlers once the window exists."""
        try:
            for control_name, handler in (
                ("RateDbAdd", rate_db_add),
                ("RateDbUpdate", rate_db_update),
                ("RateDbRemove", rate_db_remove),
                ("RateDbClear", rate_db_clear_fields),
            ):
                control = window.FindName(control_name)
                if control is not None:
                    control.Click += handler

            list_box = window.FindName("RateDbList")
            if list_box is not None:
                list_box.SelectionChanged += rate_db_selection_changed

            # Re-check which rates apply once the location is edited.
            location_box = window.FindName("RateDbProjectLocation")
            if location_box is not None:
                location_box.LostFocus += (
                    lambda sender, args: rate_db_refresh(
                        rate_db_selected_index()))
        except:
            pass

    return {
        "wire_controls": rate_db_wire_controls,
        "load_saved": rate_db_load_saved,
        "refresh": rate_db_refresh,
    }

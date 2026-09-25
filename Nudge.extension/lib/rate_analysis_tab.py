# -*- coding: utf-8 -*-
"""Rate Analysis tab (P11) - the dialog's handlers for this tab.

Moved out of BOQ.pushbutton/script.py in the P8 split (v1.38.0), where
this tab alone had grown script.py by a few hundred lines. The handler
code is the code that ran there, unchanged except for its indentation
and one thing: the document now arrives as its title string, so nothing
in lib/ holds a Revit object.

WPF-bound, not an engine: the handlers read and write the dialog's
controls through `host.window`, so only the dialog loads this module.
It imports no Revit or pyRevit symbol. The list it edits - rate_analysis_state and rate_analysis_ready -
belongs to script.py and is passed in by reference, because the export
and the settings save read the same objects.

    handlers = attach(host)
    handlers["wire_controls"]()

`host` carries: window, set_status, load_app_settings, ParameterItem, rate_analysis_state, rate_analysis_ready.
"""


def attach(host):
    """Build this tab's handlers around one open dialog.

    Returns the entry points script.py calls; every other handler is
    reached through the controls it is wired to.
    """
    window = host.window
    set_status = host.set_status
    load_app_settings = host.load_app_settings
    ParameterItem = host.ParameterItem
    rate_analysis_state = host.rate_analysis_state
    rate_analysis_ready = host.rate_analysis_ready

    # ------------------------------------------------------------
    # P11: RATE ANALYSIS TAB
    #
    # The build-ups live in rate_analysis_state. Every handler
    # rewrites it and redraws, so the list on screen is exactly what
    # is saved and exported - the same contract the Site Items tab
    # uses.
    # ------------------------------------------------------------

    RATE_FIELD_CONTROLS = (
        ("item_code", "RateItemCode"),
        ("description", "RateDescription"),
        ("unit", "RateUnit"),
        ("material", "RateMaterial"),
        ("wastage_pct", "RateWastagePct"),
        ("labour", "RateLabour"),
        ("machinery", "RateMachinery"),
        ("overheads_pct", "RateOverheadsPct"),
    )

    def rate_display_text(analysis):
        """One readable line: the item, and its rate or what is missing."""
        from costing_engine import compute_analysed_rate

        rate, missing = compute_analysed_rate(analysis)
        if rate is None:
            tail = "rate pending - needs {0}".format(", ".join(missing))
        else:
            tail = "rate {0:.2f} / {1}".format(
                rate, analysis.get("unit") or "unit")

        return u"{0}  |  {1}  |  {2}".format(
            analysis.get("item_code") or "(no code)",
            analysis.get("description") or "(no description)",
            tail
        )

    def rate_refresh(select_index=-1):
        """Redraw the list and the summary line."""
        from costing_engine import compute_analysed_rate

        try:
            list_box = window.FindName("RateList")
            if list_box is not None:
                list_box.Items.Clear()
                for analysis in rate_analysis_state:
                    list_box.Items.Add(
                        ParameterItem(rate_display_text(analysis))
                    )
                if 0 <= select_index < len(rate_analysis_state):
                    list_box.SelectedIndex = select_index
        except:
            pass

        try:
            summary_box = window.FindName("RateSummary")
            if summary_box is None:
                return

            if not rate_analysis_state:
                summary_box.Text = (
                    "No rate build-ups. Items added here export to their "
                    "own Rate Analysis sheet."
                )
                return

            priced = 0
            pending = 0
            for analysis in rate_analysis_state:
                if compute_analysed_rate(analysis)[0] is None:
                    pending += 1
                else:
                    priced += 1

            text = "{0} item(s) | {1} priced".format(
                len(rate_analysis_state), priced)
            if pending:
                text += (
                    " | {0} awaiting a figure - those export with a "
                    "blank rate rather than a zero".format(pending)
                )
            summary_box.Text = text
        except:
            pass

    def rate_fill_fields(analysis):
        """Load one build-up into the entry boxes for editing."""
        for key, control_name in RATE_FIELD_CONTROLS:
            try:
                control = window.FindName(control_name)
                if control is None:
                    continue
                value = analysis.get(key)
                control.Text = "" if value is None else str(value)
            except:
                pass

    def rate_read_fields():
        """Read the entry boxes into a normalized build-up."""
        from costing_engine import normalize_rate_analysis

        values = {}
        for key, control_name in RATE_FIELD_CONTROLS:
            try:
                control = window.FindName(control_name)
                values[key] = control.Text if control is not None else ""
            except:
                values[key] = ""
        return normalize_rate_analysis(values)

    def rate_clear_fields(sender=None, args=None):
        for _key, control_name in RATE_FIELD_CONTROLS:
            try:
                control = window.FindName(control_name)
                if control is not None:
                    control.Text = ""
            except:
                pass
        set_status("Rate analysis | Fields cleared", "info")

    def rate_selected_index():
        try:
            list_box = window.FindName("RateList")
            if list_box is None:
                return -1
            return int(list_box.SelectedIndex)
        except:
            return -1

    def rate_add(sender=None, args=None):
        """Add the typed build-up. An item needs at least a code."""
        analysis = rate_read_fields()

        if not analysis.get("item_code"):
            set_status(
                "Rate analysis | Give the item a code before adding it",
                "warning"
            )
            return

        # Selecting a line fills the boxes, so pressing Add instead of
        # Update made a silent second copy. One code, one rate.
        from costing_engine import find_rate_code_conflict

        if find_rate_code_conflict(
                rate_analysis_state, analysis["item_code"]) >= 0:
            set_status(
                "Rate analysis | {0} is already in the list - select it "
                "and use Update selected to change it".format(
                    analysis["item_code"]),
                "warning"
            )
            return

        rate_analysis_state.append(analysis)
        rate_refresh(len(rate_analysis_state) - 1)
        set_status(
            "Rate analysis | Added {0}".format(analysis["item_code"]),
            "success"
        )

    def rate_update(sender=None, args=None):
        index = rate_selected_index()
        if not (0 <= index < len(rate_analysis_state)):
            set_status(
                "Rate analysis | Select an item to update", "warning")
            return

        analysis = rate_read_fields()
        if not analysis.get("item_code"):
            set_status(
                "Rate analysis | Give the item a code before updating it",
                "warning"
            )
            return

        # The line may keep its own code; it may not take another's.
        from costing_engine import find_rate_code_conflict

        if find_rate_code_conflict(
                rate_analysis_state, analysis["item_code"], index) >= 0:
            set_status(
                "Rate analysis | Another line already uses {0}".format(
                    analysis["item_code"]),
                "warning"
            )
            return

        rate_analysis_state[index] = analysis
        rate_refresh(index)
        set_status(
            "Rate analysis | Updated {0}".format(analysis["item_code"]),
            "success"
        )

    def rate_remove(sender=None, args=None):
        index = rate_selected_index()
        if not (0 <= index < len(rate_analysis_state)):
            set_status(
                "Rate analysis | Select an item to remove", "warning")
            return

        removed = rate_analysis_state.pop(index)
        rate_refresh()
        set_status(
            "Rate analysis | Removed {0}".format(
                removed.get("item_code") or "item"),
            "info"
        )

    def rate_selection_changed(sender=None, args=None):
        index = rate_selected_index()
        if 0 <= index < len(rate_analysis_state):
            rate_fill_fields(rate_analysis_state[index])

    def rate_load_saved():
        """Load the saved build-ups into the tab."""
        try:
            from costing_engine import load_rate_analysis

            del rate_analysis_state[:]
            rate_analysis_state.extend(
                load_rate_analysis(load_app_settings())
            )
            # Only now does the list on screen stand for the saved one.
            rate_analysis_ready[0] = True
        except:
            del rate_analysis_state[:]

        try:
            source_box = window.FindName("RateSource")
            if source_box is not None:
                source_box.Text = (
                    "Showing the saved build-ups; they are written back "
                    "when you export or close."
                    if rate_analysis_state
                    else "No rate build-ups saved yet."
                )
        except:
            pass

        rate_refresh()

    def rate_wire_controls():
        """Attach the tab's handlers once the window exists."""
        try:
            for control_name, handler in (
                ("RateAdd", rate_add),
                ("RateUpdate", rate_update),
                ("RateRemove", rate_remove),
                ("RateClear", rate_clear_fields),
            ):
                control = window.FindName(control_name)
                if control is not None:
                    control.Click += handler

            list_box = window.FindName("RateList")
            if list_box is not None:
                list_box.SelectionChanged += rate_selection_changed
        except:
            pass

    return {
        "wire_controls": rate_wire_controls,
        "load_saved": rate_load_saved,
    }

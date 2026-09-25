# -*- coding: utf-8 -*-
"""Site Items tab (P7) - the dialog's handlers for this tab.

Moved out of BOQ.pushbutton/script.py in the P8 split (v1.38.0), where
this tab alone had grown script.py by a few hundred lines. The handler
code is the code that ran there, unchanged except for its indentation
and one thing: the document now arrives as its title string, so nothing
in lib/ holds a Revit object.

WPF-bound, not an engine: the handlers read and write the dialog's
controls through `host.window`, so only the dialog loads this module.
It imports no Revit or pyRevit symbol. The list it edits - site_items_state, site_items_ready, site_items_source and
site_items_dirty -
belongs to script.py and is passed in by reference, because the export
and the settings save read the same objects.

    handlers = attach(host)
    handlers["wire_controls"]()

`host` carries: window, document_title, set_status, load_app_settings, save_app_settings, ParameterItem, safe_text, site_items_state, site_items_ready, site_items_source, site_items_dirty.
"""

from site_items_engine import (
    normalize_site_item,
    resolve_site_items,
    set_default_site_items,
    site_item_amount,
    summarize_site_items,
    validate_site_items,
)


def attach(host):
    """Build this tab's handlers around one open dialog.

    Returns the entry points script.py calls; every other handler is
    reached through the controls it is wired to.
    """
    window = host.window
    document_title = host.document_title
    set_status = host.set_status
    load_app_settings = host.load_app_settings
    save_app_settings = host.save_app_settings
    ParameterItem = host.ParameterItem
    safe_text = host.safe_text
    site_items_state = host.site_items_state
    site_items_ready = host.site_items_ready
    site_items_source = host.site_items_source
    site_items_dirty = host.site_items_dirty

    # ------------------------------------------------------------
    # P7 - Site / Non-Model Items tab
    #
    # The list lives in site_items_state. Every handler rewrites it
    # and then redraws, so what is on screen is always exactly what
    # gets exported and saved.
    # ------------------------------------------------------------

    def site_items_display_text(item):
        """One readable line for the list box."""
        amount = site_item_amount(item)
        quantity = item.get("quantity")
        rate = item.get("rate")
        return u"{0}  |  {1}  |  {2} {3} x {4} = {5}".format(
            item.get("code") or "(no code)",
            item.get("description") or "(no description)",
            "-" if quantity is None else quantity,
            item.get("unit") or "-",
            "-" if rate is None else rate,
            "-" if amount is None else "{0:.2f}".format(amount)
        )

    def site_items_source_text():
        """Say where the list came from and whether it is saved."""
        if site_items_dirty[0]:
            return ("Edited - saved to this project when you export or "
                    "close.")
        if site_items_source[0] == "document":
            return "Showing this project's own saved list."
        if site_items_source[0] == "default":
            return ("Started from the default list. It becomes this "
                    "project's own list when you export or close.")
        return "No site items saved for this project yet."

    def site_items_refresh(select_index=-1):
        """Redraw the list, the source label and the summary line."""
        try:
            source_box = window.FindName("SiteItemSource")

            if source_box is not None:
                source_box.Text = site_items_source_text()
        except:
            pass

        try:
            list_box = window.FindName("SiteItemList")

            if list_box is not None:
                list_box.Items.Clear()
                for item in site_items_state:
                    list_box.Items.Add(
                        ParameterItem(site_items_display_text(item))
                    )
                if 0 <= select_index < len(site_items_state):
                    list_box.SelectedIndex = select_index

            summary_box = window.FindName("SiteItemSummary")

            if summary_box is not None:
                if not site_items_state:
                    summary_box.Text = (
                        "No site items. Add one above, or leave this tab "
                        "empty - the workbook simply omits the sheet."
                    )
                else:
                    totals = summarize_site_items(site_items_state)
                    findings = validate_site_items(site_items_state)
                    text = "{0} item(s) | {1} priced, total {2:.2f}".format(
                        totals["count"],
                        totals["priced_count"],
                        totals["amount_total"]
                    )
                    if totals["unpriced_count"]:
                        text += (
                            " | {0} awaiting a quantity or rate, exported "
                            "with a blank Amount".format(
                                totals["unpriced_count"]
                            )
                        )
                    if findings:
                        text += " || " + " / ".join(findings[:3])
                        if len(findings) > 3:
                            text += " / +{0} more".format(len(findings) - 3)
                    summary_box.Text = text
        except:
            pass

    def site_items_fill_fields(item):
        """Load one item back into the six text boxes."""
        try:
            for field_name, value in (
                ("SiteItemCode", item.get("code", "")),
                ("SiteItemDescription", item.get("description", "")),
                ("SiteItemUnit", item.get("unit", "")),
                ("SiteItemQuantity", item.get("quantity")),
                ("SiteItemRate", item.get("rate")),
                ("SiteItemRemarks", item.get("remarks", "")),
            ):
                field = window.FindName(field_name)
                if field is not None:
                    field.Text = (
                        "" if value is None else u"{0}".format(value)
                    )
        except:
            pass

    def site_items_read_fields():
        """Return one normalized item built from the text boxes."""
        values = {}
        for key, field_name in (
            ("code", "SiteItemCode"),
            ("description", "SiteItemDescription"),
            ("unit", "SiteItemUnit"),
            ("quantity", "SiteItemQuantity"),
            ("rate", "SiteItemRate"),
            ("remarks", "SiteItemRemarks"),
        ):
            try:
                field = window.FindName(field_name)
                values[key] = field.Text if field is not None else ""
            except:
                values[key] = ""
        return normalize_site_item(values, len(site_items_state))

    def site_items_clear_fields():
        """Empty the entry boxes and drop the list selection."""
        site_items_fill_fields({})
        try:
            list_box = window.FindName("SiteItemList")
            if list_box is not None:
                list_box.SelectedIndex = -1
        except:
            pass

    def site_items_selected_index():
        """Return the selected row index, or -1."""
        try:
            list_box = window.FindName("SiteItemList")
            if list_box is None:
                return -1
            return list_box.SelectedIndex
        except:
            return -1

    def site_items_add(sender=None, args=None):
        """Append what is typed as a new line."""
        item = site_items_read_fields()

        if not item.get("code") and not item.get("description"):
            set_status(
                "Site items | Enter at least an item code or a description",
                "warning"
            )
            return

        site_items_state.append(item)
        site_items_dirty[0] = True
        site_items_refresh(len(site_items_state) - 1)
        site_items_clear_fields()
        set_status("Site items | Added", "success")

    def site_items_update(sender=None, args=None):
        """Replace the selected line with what is typed."""
        index = site_items_selected_index()

        if not (0 <= index < len(site_items_state)):
            set_status("Site items | Select a line to update", "warning")
            return

        site_items_state[index] = site_items_read_fields()
        site_items_dirty[0] = True
        site_items_refresh(index)
        set_status("Site items | Updated", "success")

    def site_items_remove(sender=None, args=None):
        """Delete the selected line."""
        index = site_items_selected_index()

        if not (0 <= index < len(site_items_state)):
            set_status("Site items | Select a line to remove", "warning")
            return

        del site_items_state[index]
        site_items_dirty[0] = True
        site_items_refresh()
        site_items_clear_fields()
        set_status("Site items | Removed", "success")

    def site_items_clear(sender=None, args=None):
        """Clear the entry boxes without touching the list."""
        site_items_clear_fields()
        set_status("Site items | Fields cleared", "info")

    def site_items_selection_changed(sender, args):
        """Load the clicked line into the entry boxes for editing."""
        index = site_items_selected_index()
        if 0 <= index < len(site_items_state):
            site_items_fill_fields(site_items_state[index])

    def site_items_save_default(sender=None, args=None):
        """Make this list the starting point for NEW projects only."""
        try:
            settings = load_app_settings()
            if not isinstance(settings, dict):
                settings = {}
            settings["site_items"] = set_default_site_items(
                settings.get("site_items"),
                site_items_state
            )
            save_app_settings(settings)
            set_status(
                "Site items | Saved as the default for new projects; "
                "projects with their own list are unchanged",
                "success"
            )
        except:
            set_status("Site items | Could not save the default", "warning")

    def site_items_load_for_document():
        """Fill the tab from the store for the active document."""
        try:
            resolved = resolve_site_items(
                load_app_settings().get("site_items"),
                document_title
            )
            del site_items_state[:]
            site_items_state.extend(resolved.get("items", []))

            site_items_source[0] = resolved.get("source", "")
            site_items_dirty[0] = False

            site_items_ready[0] = True
            site_items_refresh()
        except:
            pass

    def site_items_wire_controls():
        """Attach the tab's handlers once the window exists."""
        try:
            for control_name, handler in (
                ("SiteItemAdd", site_items_add),
                ("SiteItemUpdate", site_items_update),
                ("SiteItemRemove", site_items_remove),
                ("SiteItemClear", site_items_clear),
                ("SiteItemSaveDefault", site_items_save_default),
            ):
                control = window.FindName(control_name)
                if control is not None:
                    control.Click += handler

            list_box = window.FindName("SiteItemList")

            if list_box is not None:
                list_box.SelectionChanged += site_items_selection_changed
        except:
            pass

    return {
        "wire_controls": site_items_wire_controls,
        "load_for_document": site_items_load_for_document,
    }

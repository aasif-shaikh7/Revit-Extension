# -*- coding: utf-8 -*-
"""Revision tab (P14) - the dialog's handlers for this tab.

Moved out of BOQ.pushbutton/script.py in the P8 split (v1.38.0), where
this tab alone had grown script.py by a few hundred lines. The handler
code is the code that ran there, unchanged except for its indentation
and one thing: the document now arrives as its title string, so nothing
in lib/ holds a Revit object.

WPF-bound, not an engine: the handlers read and write the dialog's
controls through `host.window`, so only the dialog loads this module.
It imports no Revit or pyRevit symbol. The list it edits - the files revision_engine keeps per document (the tab holds no
state of its own beyond what it shows) -
belongs to script.py and is passed in by reference, because the export
and the settings save read the same objects.

    handlers = attach(host)
    handlers["wire_controls"]()

`host` carries: window, document_title, set_status, load_app_settings, save_app_settings, ParameterItem, safe_text.
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
    save_app_settings = host.save_app_settings
    ParameterItem = host.ParameterItem
    safe_text = host.safe_text

    # ====================================================
    # P14 REVISION TAB (v1.37.0)
    # The revisions filed for this model (newest first), which
    # one the next export is compared against, and a short name
    # per revision. The choice is saved per model under
    # "revision_compare"; renaming touches only the name, never
    # the quantities a revision recorded. Guarded throughout: a
    # failure here must not stop the dialog or an export.
    # ====================================================

    revision_tab_state = {
        "rows": [],        # snapshots in list order, newest first
        "choices": [""],   # selector index -> label ("" = latest)
        "loading": False,
    }

    def revision_tab_document():
        return document_title

    def revision_tab_summary():
        """One line saying what the next export will do."""
        from revision_engine import (
            choose_previous, get_compare_choice,
            next_revision_label, revision_display_name)

        summary_box = window.FindName("RevisionSummary")
        if summary_box is None:
            return
        rows = revision_tab_state["rows"]
        if not rows:
            summary_box.Text = (
                "No revisions filed for this model yet. The first "
                "export files Rev 00; from the second on, the workbook "
                "gets a BOQ Revision sheet.")
            return
        filed = list(reversed(rows))
        choice = get_compare_choice(
            load_app_settings(), revision_tab_document())
        target = choose_previous(filed, choice)
        summary_box.Text = (
            u"{0} revision{1} filed. The next export is compared "
            u"against {2}{3}, and is filed as {4} if anything "
            u"changed.".format(
                len(filed), u"" if len(filed) == 1 else u"s",
                revision_display_name(target),
                u"" if choice else u" (the latest)",
                next_revision_label(filed)))

    def revision_tab_refresh(select_label=None):
        """Reload the filed revisions and redraw list and selector."""
        from revision_engine import (
            document_folder, get_compare_choice, list_snapshots,
            revision_display_name, revision_list_text, revision_number)

        document = revision_tab_document()
        try:
            filed = list_snapshots(document)
        except:
            filed = []
        rows = list(reversed(filed))
        revision_tab_state["rows"] = rows
        revision_tab_state["loading"] = True
        try:
            list_box = window.FindName("RevisionList")
            if list_box is not None:
                list_box.Items.Clear()
                selected = -1
                for index, snapshot in enumerate(rows):
                    list_box.Items.Add(
                        ParameterItem(revision_list_text(snapshot)))
                    if (select_label is not None
                            and revision_number(snapshot.get("revision"))
                            == revision_number(select_label)):
                        selected = index
                list_box.SelectedIndex = selected

            selector = window.FindName("RevisionCompareSelector")
            if selector is not None:
                selector.Items.Clear()
                choices = [""]
                selector.Items.Add(
                    u"Latest ({0})".format(
                        revision_display_name(rows[0]))
                    if rows else u"Latest")
                for snapshot in rows:
                    choices.append(snapshot.get("revision", ""))
                    selector.Items.Add(revision_display_name(snapshot))
                revision_tab_state["choices"] = choices
                wanted = get_compare_choice(load_app_settings(), document)
                index = 0
                for position, label in enumerate(choices):
                    if wanted and label and (
                            revision_number(label)
                            == revision_number(wanted)):
                        index = position
                selector.SelectedIndex = index
        except:
            pass
        finally:
            revision_tab_state["loading"] = False

        try:
            folder_box = window.FindName("RevisionFolder")
            if folder_box is not None:
                folder_box.Text = u"Stored in: {0}".format(
                    document_folder(document))
        except:
            pass
        try:
            revision_tab_summary()
        except:
            pass

    def revision_compare_changed(sender, args):
        if revision_tab_state["loading"]:
            return
        try:
            from revision_engine import set_compare_choice
            index = sender.SelectedIndex
            choices = revision_tab_state["choices"]
            if index < 0 or index >= len(choices):
                return
            save_app_settings(set_compare_choice(
                load_app_settings(), revision_tab_document(),
                choices[index]))
            revision_tab_summary()
        except:
            pass

    def revision_list_changed(sender, args):
        try:
            name_box = window.FindName("RevisionName")
            index = sender.SelectedIndex
            rows = revision_tab_state["rows"]
            if name_box is None:
                return
            if 0 <= index < len(rows):
                name_box.Text = rows[index].get("name", u"") or u""
            else:
                name_box.Text = u""
        except:
            pass

    def revision_save_name(sender, args):
        try:
            from revision_engine import set_revision_name
            list_box = window.FindName("RevisionList")
            name_box = window.FindName("RevisionName")
            index = list_box.SelectedIndex if list_box is not None else -1
            rows = revision_tab_state["rows"]
            if not 0 <= index < len(rows):
                set_status("Select a revision in the list first.",
                           "warning")
                return
            label = rows[index].get("revision", "")
            name = name_box.Text if name_box is not None else u""
            if set_revision_name(revision_tab_document(), label, name):
                revision_tab_refresh(select_label=label)
                set_status(u"{0} renamed.".format(label), "success")
            else:
                set_status(u"{0} could not be renamed.".format(label),
                           "warning")
        except:
            set_status("The revision name could not be saved.",
                       "warning")

    def revision_tab_wire_controls():
        """Attach the tab's handlers once the window exists."""
        try:
            selector = window.FindName("RevisionCompareSelector")
            if selector is not None:
                selector.SelectionChanged += revision_compare_changed
            list_box = window.FindName("RevisionList")
            if list_box is not None:
                list_box.SelectionChanged += revision_list_changed
            save_button = window.FindName("RevisionSaveName")
            if save_button is not None:
                save_button.Click += revision_save_name
            refresh_button = window.FindName("RevisionRefresh")
            if refresh_button is not None:
                refresh_button.Click += (
                    lambda sender, args: revision_tab_refresh())
        except:
            pass

    return {
        "wire_controls": revision_tab_wire_controls,
        "refresh": revision_tab_refresh,
    }

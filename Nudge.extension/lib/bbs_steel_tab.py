# -*- coding: utf-8 -*-
"""BBS Steel tab (v1.42.0) - the dialog's handlers for this tab.

The list of this model's separate BBS models, and the reading of them.
Reading opens each model in the background, weighs its rebar and closes
it without saving; that part is Revit-bound and lives in script.py
(read_bbs_model), handed in through `host`. What was read is kept by
bbs_steel_engine in a small file per model, which the export uses.

WPF-bound, not an engine: the handlers read and write the dialog's
controls through `host.window`, so only the dialog loads this module. It
imports no Revit or pyRevit symbol.

    handlers = attach(host)
    handlers["wire_controls"]()

`host` carries: window, document_title, set_status, ParameterItem,
read_bbs_model, pump_dialog.
"""


def attach(host):
    """Build this tab's handlers around one open dialog.

    Returns the entry points script.py calls; every other handler is
    reached through the controls it is wired to.
    """
    window = host.window
    document_title = host.document_title
    set_status = host.set_status
    ParameterItem = host.ParameterItem
    read_bbs_model = host.read_bbs_model
    pump_dialog = host.pump_dialog

    bbs_tab_state = {
        "store": None,
        "loading": False,
    }

    def bbs_store():
        if bbs_tab_state["store"] is None:
            from bbs_steel_engine import load_bbs_store
            bbs_tab_state["store"] = load_bbs_store(document_title)
        return bbs_tab_state["store"]

    def bbs_save():
        from bbs_steel_engine import save_bbs_store
        return save_bbs_store(bbs_store(), document_title)

    def bbs_selected_index():
        list_box = window.FindName("BbsList")
        if list_box is None:
            return -1
        return list_box.SelectedIndex

    def bbs_show_group(index):
        """Show the selected model's element in the selector, saving nothing."""
        from bbs_steel_engine import BBS_GROUPS
        selector = window.FindName("BbsGroupSelector")
        if selector is None:
            return
        files = bbs_store().get("files") or []
        bbs_tab_state["loading"] = True
        try:
            if 0 <= index < len(files):
                group = files[index].get("group") or "Other"
                selector.SelectedIndex = (
                    list(BBS_GROUPS).index(group) if group in BBS_GROUPS else -1)
            else:
                selector.SelectedIndex = -1
        finally:
            bbs_tab_state["loading"] = False

    def bbs_refresh(select_index=None):
        """Redraw the tab from the store.

        The store is read from disk once, when the dialog opens; after that
        the handlers change the same object and save it, so a redraw in the
        middle of a read never swaps it for a copy the read is not writing.
        """
        from bbs_steel_engine import (
            BBS_GROUPS, bbs_list_text, bbs_store_path, bbs_summary_text)

        files = bbs_store().get("files") or []
        bbs_tab_state["loading"] = True
        try:
            selector = window.FindName("BbsGroupSelector")
            if selector is not None and selector.Items.Count == 0:
                for group in BBS_GROUPS:
                    selector.Items.Add(group)
            list_box = window.FindName("BbsList")
            if list_box is not None:
                list_box.Items.Clear()
                for entry in files:
                    list_box.Items.Add(ParameterItem(bbs_list_text(entry)))
                if select_index is not None and 0 <= select_index < len(files):
                    list_box.SelectedIndex = select_index
                else:
                    list_box.SelectedIndex = -1
        except:
            pass
        finally:
            bbs_tab_state["loading"] = False

        try:
            bbs_show_group(bbs_selected_index())
        except:
            pass
        try:
            summary_box = window.FindName("BbsSummary")
            if summary_box is not None:
                summary_box.Text = bbs_summary_text(bbs_store())
            folder_box = window.FindName("BbsFolder")
            if folder_box is not None:
                folder_box.Text = u"Stored in: {0}".format(
                    bbs_store_path(document_title))
        except:
            pass

    def bbs_add(sender, args):
        try:
            from System.Windows.Forms import OpenFileDialog, DialogResult
            from bbs_steel_engine import add_bbs_files
            dialog = OpenFileDialog()
            dialog.Title = "Add BBS models"
            dialog.Filter = "Revit models (*.rvt)|*.rvt"
            dialog.Multiselect = True
            if dialog.ShowDialog() != DialogResult.OK:
                return
            added = add_bbs_files(bbs_store(), list(dialog.FileNames))
            if added and not bbs_save():
                set_status("The BBS model list could not be saved.", "warning")
                return
            bbs_refresh()
            if added:
                set_status(
                    u"{0} BBS model{1} added. Check the element of each, then "
                    u"click Read new and changed.".format(
                        added, u"" if added == 1 else u"s"), "success")
            else:
                set_status("Those BBS models are already in the list.",
                           "warning")
        except:
            set_status("The BBS models could not be added.", "warning")

    def bbs_remove(sender, args):
        try:
            from bbs_steel_engine import remove_bbs_file
            index = bbs_selected_index()
            if not remove_bbs_file(bbs_store(), index):
                set_status("Select a BBS model in the list first.", "warning")
                return
            bbs_save()
            bbs_refresh()
            set_status("BBS model removed from the list. The file itself "
                       "is untouched.", "success")
        except:
            set_status("The BBS model could not be removed.", "warning")

    def bbs_list_changed(sender, args):
        if bbs_tab_state["loading"]:
            return
        try:
            bbs_show_group(bbs_selected_index())
        except:
            pass

    def bbs_group_changed(sender, args):
        if bbs_tab_state["loading"]:
            return
        try:
            from bbs_steel_engine import BBS_GROUPS, set_bbs_group
            index = bbs_selected_index()
            position = sender.SelectedIndex
            if not 0 <= position < len(BBS_GROUPS):
                return
            if set_bbs_group(bbs_store(), index, BBS_GROUPS[position]):
                bbs_save()
                bbs_refresh(select_index=index)
        except:
            pass

    def bbs_read(only_needed):
        """Read the BBS models, one at a time, saving after each.

        Saving after each model means a crash or a closed Revit loses at
        most the model being read. The dialog is disabled meanwhile, so
        nothing else can be clicked while Revit has a model open.
        """
        from bbs_steel_engine import (
            STATUS_MISSING, entry_status, file_signature, needs_reading,
            record_bbs_error, record_bbs_reading)

        files = bbs_store().get("files") or []
        todo = []
        for index, entry in enumerate(files):
            signature = file_signature(entry.get("path"))
            if signature is None:
                continue
            if only_needed and not needs_reading(entry, signature):
                continue
            todo.append(index)
        if not todo:
            missing = len([entry for entry in files
                           if entry_status(entry) == STATUS_MISSING])
            set_status(
                u"Nothing to read{0}.".format(
                    u" - {0} model file{1} not found".format(
                        missing, u"" if missing == 1 else u"s")
                    if missing else u": every BBS model is read and unchanged"),
                "warning" if missing else "success")
            return

        failed = 0
        window.IsEnabled = False
        try:
            for count, index in enumerate(todo, 1):
                entry = files[index]
                set_status(
                    u"Reading BBS model {0} of {1}: {2} - Revit takes a "
                    u"minute or more per model.".format(
                        count, len(todo), entry.get("name", u"")), "info")
                pump_dialog()
                signature = file_signature(entry.get("path"))
                try:
                    reading = read_bbs_model(entry.get("path"))
                    record_bbs_reading(entry, reading.get("values") or [],
                                       signature=signature,
                                       revit=reading.get("revit", u""))
                except Exception as error:
                    failed += 1
                    record_bbs_error(entry, error)
                bbs_save()
                bbs_refresh(select_index=index)
                pump_dialog()
        finally:
            window.IsEnabled = True

        if failed:
            set_status(
                u"{0} of {1} BBS models read; {2} could not be read - see "
                u"the list.".format(len(todo) - failed, len(todo), failed),
                "warning")
        else:
            set_status(
                u"{0} BBS model{1} read. The next export includes the "
                u"steel.".format(len(todo), u"" if len(todo) == 1 else u"s"),
                "success")

    def bbs_tab_wire_controls():
        """Attach the tab's handlers once the window exists."""
        try:
            for name, handler in (
                    ("BbsAdd", bbs_add),
                    ("BbsRemove", bbs_remove),
                    ("BbsReadChanged", lambda sender, args: bbs_read(True)),
                    ("BbsReadAll", lambda sender, args: bbs_read(False))):
                button = window.FindName(name)
                if button is not None:
                    button.Click += handler
            list_box = window.FindName("BbsList")
            if list_box is not None:
                list_box.SelectionChanged += bbs_list_changed
            selector = window.FindName("BbsGroupSelector")
            if selector is not None:
                selector.SelectionChanged += bbs_group_changed
        except:
            pass

    return {
        "wire_controls": bbs_tab_wire_controls,
        "refresh": bbs_refresh,
    }

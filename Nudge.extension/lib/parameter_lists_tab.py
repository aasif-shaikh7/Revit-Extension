# -*- coding: utf-8 -*-
"""Parameter lists - the six category tabs' Available / Selected handlers.

Moved out of BOQ.pushbutton/script.py in the P8 split (v1.39.0): the
search filter, the Slab / Foundation subtype filters, the list refresh,
Add and Remove, and the four Move buttons. The code is the code that ran
there, unchanged except for its indentation.

WPF-bound, not an engine: the handlers read and write the dialog's list
boxes through `host.window`, so only the dialog loads this module. It
imports no Revit or pyRevit symbol. The Revit-reading helpers it needs
(get_parameters, filter_elements) and the dictionaries it edits
(category_parameters, selected_parameters, active_filters, ...) belong
to script.py and are handed over by reference: the export and the
settings save read the same objects.

Handlers that script.py defines once per category inside its wiring
loops - search box, double-click - and apply_parameters, which it
defines inside an if, stay in script.py; they call these by name.

    handlers = attach(host)
    add_parameters = handlers["add_parameters"]

`host` carries: window, status, set_status, safe_text, control_map, category_elements, category_parameters, selected_parameters, active_filters, logical_slab_elements, logical_foundation_elements, filter_elements, get_parameters, capture_and_save_settings, show_category_counts, SLAB_FILTER_OPTIONS, FOUNDATION_FILTER_OPTIONS, REBAR_DERIVED_PARAMETERS, STRUCTURE_WALL_DERIVED_PARAMETERS.
"""


def attach(host):
    """Build the parameter-list handlers around one open dialog.

    Returns every handler by name; script.py binds each to its old name,
    so its wiring and its callers do not change.
    """
    window = host.window
    status = host.status
    set_status = host.set_status
    safe_text = host.safe_text
    control_map = host.control_map
    category_elements = host.category_elements
    category_parameters = host.category_parameters
    selected_parameters = host.selected_parameters
    active_filters = host.active_filters
    logical_slab_elements = host.logical_slab_elements
    logical_foundation_elements = host.logical_foundation_elements
    filter_elements = host.filter_elements
    get_parameters = host.get_parameters
    capture_and_save_settings = host.capture_and_save_settings
    show_category_counts = host.show_category_counts
    SLAB_FILTER_OPTIONS = host.SLAB_FILTER_OPTIONS
    FOUNDATION_FILTER_OPTIONS = host.FOUNDATION_FILTER_OPTIONS
    REBAR_DERIVED_PARAMETERS = host.REBAR_DERIVED_PARAMETERS
    STRUCTURE_WALL_DERIVED_PARAMETERS = host.STRUCTURE_WALL_DERIVED_PARAMETERS

    def filter_available_by_search(element_name):
        """
        Rebuild the Available list for a category, applying the
        current search query on top of the master parameter pool.
        Also respects the active subtype filter because the pool
        itself is already narrowed down by refresh_category_view.
        """
        try:
            controls = control_map[element_name]
            available = window.FindName(
                controls["available"]
            )

            if not available:
                return

            query = ""
            search_box = window.FindName(
                controls["search"]
            )

            if search_box is not None:
                try:
                    query = (
                        str(search_box.Text or "")
                        .strip()
                        .lower()
                    )
                except:
                    query = ""

            pool = category_parameters.get(
                element_name,
                []
            )

            # v1.7.1: parameters already in the Selected list are
            # hidden from Available so the list only offers the
            # remaining parameters.
            selected_names = set()

            selected_box = window.FindName(
                controls["selected"]
            )

            if selected_box is not None:
                try:
                    for item in selected_box.Items:
                        try:
                            selected_names.add(item.Name)
                        except:
                            pass
                except:
                    pass

            available.Items.Clear()

            for parameter in pool:

                try:
                    name = parameter.Name
                except:
                    name = safe_text(
                        parameter,
                        ""
                    )

                if name is None:
                    name = ""

                if name in selected_names:
                    continue

                if (
                    not query
                    or query in name.lower()
                ):
                    available.Items.Add(parameter)

        except:
            pass

    def refresh_category_view(element_name):

        if element_name == 'Slab':
            selected_filter = active_filters.get(
                'Slab',
                'All Slab Types'
            )
            # Use the same precomputed logical collection as export.
            base_elements = list(logical_slab_elements)

            category_elements['Slab'] = filter_elements(
                base_elements,
                'Slab',
                selected_filter
            )

        elif element_name == 'Foundation':
            selected_filter = active_filters.get(
                'Foundation',
                'All Foundation Types'
            )

            # Use the same precomputed logical collection as export.
            base_elements = list(logical_foundation_elements)

            category_elements['Foundation'] = filter_elements(
                base_elements,
                'Foundation',
                selected_filter
            )

        try:
            derived_names = ()
            if element_name == "Structure Wall":
                derived_names = STRUCTURE_WALL_DERIVED_PARAMETERS
            elif element_name == "Rebar":
                derived_names = REBAR_DERIVED_PARAMETERS
            category_parameters[element_name] = get_parameters(
                category_elements.get(element_name, []),
                derived_names
            )

            filter_available_by_search(element_name)
        except:
            pass

        # A subtype filter changes how many elements the tab holds, so
        # the count on the tab follows it (v1.34.3).
        try:
            show_category_counts()
        except:
            pass

        try:
            if status:
                set_status(
                    '{} filter: {} | Elements: {}'.format(
                        element_name,
                        active_filters.get(element_name, 'All'),
                        len(category_elements.get(element_name, []))
                    ),
                    "info"
                )
        except:
            pass

    def setup_rcc_filters():

        slab_filter = window.FindName('SlabFilter')
        foundation_filter = window.FindName('FoundationFilter')

        if slab_filter:
            slab_filter.Items.Clear()
            for option in SLAB_FILTER_OPTIONS:
                slab_filter.Items.Add(option)

            slab_filter.SelectedIndex = 0

            def on_slab_filter_changed(
                sender,
                args
            ):
                try:
                    if sender.SelectedItem is None:
                        return
                    active_filters['Slab'] = str(
                        sender.SelectedItem
                    )
                    refresh_category_view('Slab')
                except:
                    pass

            slab_filter.SelectionChanged += (
                on_slab_filter_changed
            )

        if foundation_filter:
            foundation_filter.Items.Clear()
            for option in FOUNDATION_FILTER_OPTIONS:
                foundation_filter.Items.Add(option)

            foundation_filter.SelectedIndex = 0

            def on_foundation_filter_changed(
                sender,
                args
            ):
                try:
                    if sender.SelectedItem is None:
                        return
                    active_filters['Foundation'] = str(
                        sender.SelectedItem
                    )
                    refresh_category_view('Foundation')
                except:
                    pass

            foundation_filter.SelectionChanged += (
                on_foundation_filter_changed
            )

    def sync_selected_parameters(
        element_name
    ):
        """
        Keep the internal selected_parameters list aligned with the
        exact order currently visible in the Selected / Export ListBox.
        This keeps the parallel data structure accurate after Add,
        Remove, and Up / Down / Top / Bottom reordering.
        """
        controls = control_map[
            element_name
        ]

        selected = window.FindName(
            controls["selected"]
        )

        if selected is None:
            return

        ordered_names = []

        try:
            for item in selected.Items:
                try:
                    ordered_names.append(
                        item.Name
                    )
                except:
                    ordered_names.append(
                        safe_text(
                            item,
                            "Unknown"
                        )
                    )
        except:
            ordered_names = []

        try:
            selected_parameters[
                element_name
            ] = ordered_names
        except:
            pass

    def add_parameters(
        element_name
    ):

        controls = control_map[
            element_name
        ]

        available = window.FindName(
            controls["available"]
        )

        selected = window.FindName(
            controls["selected"]
        )

        if not available or not selected:
            return

        selected_items = list(
            available.SelectedItems
        )

        if not selected_items:
            return

        existing = []

        for item in selected.Items:

            existing.append(
                item.Name
            )

        # Track which items are actually added (new, not duplicates)
        newly_added = []

        for item in selected_items:

            if item.Name not in existing:

                selected.Items.Add(
                    item
                )
                newly_added.append(
                    item
                )

        # keep the internal list aligned with the visible order
        sync_selected_parameters(
            element_name
        )

        # deselect
        available.UnselectAll()

        # v1.7.1: hide the just-added parameters from Available.
        try:
            filter_available_by_search(element_name)
        except:
            pass

        # Highlight (select) the newly added items in Selected
        try:
            selected.UnselectAll()
            for item in newly_added:
                selected.SelectedItems.Add(
                    item
                )
        except:
            pass

        # Persist immediately after every successful list mutation.
        # A pyRevit reload or Revit shutdown can then never discard the
        # user's newly selected parameters or their visible order.
        try:
            capture_and_save_settings()
        except:
            pass

    def remove_parameters(
        element_name
    ):

        controls = control_map[
            element_name
        ]

        selected = window.FindName(
            controls["selected"]
        )

        available = window.FindName(
            controls["available"]
        )

        if not selected:
            return

        selected_items = list(
            selected.SelectedItems
        )

        if not selected_items:
            return

        # Track names of items being removed (for highlighting later)
        removed_names = []
        for item in selected_items:
            try:
                removed_names.append(
                    item.Name
                )
            except:
                pass

        # remove from bottom to top
        indexes = []

        for item in selected_items:

            index = selected.Items.IndexOf(
                item
            )

            indexes.append(
                index
            )

        indexes.sort(
            reverse=True
        )

        for index in indexes:

            item = selected.Items[
                index
            ]

            selected.Items.RemoveAt(
                index
            )

        # keep the internal list aligned with the visible order
        sync_selected_parameters(
            element_name
        )

        selected.UnselectAll()

        # v1.7.1: bring the removed parameters back into Available.
        try:
            filter_available_by_search(element_name)
        except:
            pass

        # Highlight (select) the returned items in Available
        try:
            if available and removed_names:
                available.UnselectAll()
                for item in available.Items:
                    try:
                        if item.Name in removed_names:
                            available.SelectedItems.Add(
                                item
                            )
                    except:
                        pass
        except:
            pass

        try:
            capture_and_save_settings()
        except:
            pass

    def move_up(
        element_name
    ):

        controls = control_map[
            element_name
        ]

        selected = window.FindName(
            controls["selected"]
        )

        if not selected:
            return

        indexes = []

        for item in selected.SelectedItems:

            indexes.append(
                selected.Items.IndexOf(
                    item
                )
            )

        indexes.sort()

        for index in indexes:

            if index <= 0:
                continue

            item = selected.Items[
                index
            ]

            selected.Items.RemoveAt(
                index
            )

            selected.Items.Insert(
                index - 1,
                item
            )

            selected.SelectedItems.Add(
                item
            )

        # keep the internal list aligned with the visible order
        sync_selected_parameters(
            element_name
        )

        try:
            capture_and_save_settings()
        except:
            pass

    def move_down(
        element_name
    ):

        controls = control_map[
            element_name
        ]

        selected = window.FindName(
            controls["selected"]
        )

        if not selected:
            return

        indexes = []

        for item in selected.SelectedItems:

            indexes.append(
                selected.Items.IndexOf(
                    item
                )
            )

        indexes.sort(
            reverse=True
        )

        for index in indexes:

            if index >= (
                selected.Items.Count - 1
            ):

                continue

            item = selected.Items[
                index
            ]

            selected.Items.RemoveAt(
                index
            )

            selected.Items.Insert(
                index + 1,
                item
            )

            selected.SelectedItems.Add(
                item
            )

        # keep the internal list aligned with the visible order
        sync_selected_parameters(
            element_name
        )

        try:
            capture_and_save_settings()
        except:
            pass

    def move_top(
        element_name
    ):

        controls = control_map[
            element_name
        ]

        selected = window.FindName(
            controls["selected"]
        )

        if not selected:
            return

        selected_items = list(
            selected.SelectedItems
        )

        if not selected_items:
            return

        selected_names = []

        for item in selected_items:

            selected_names.append(
                item.Name
            )

        remaining = []

        for item in selected.Items:

            if item.Name not in selected_names:

                remaining.append(
                    item
                )

        selected.Items.Clear()

        for item in selected_items:

            selected.Items.Add(
                item
            )

        for item in remaining:

            selected.Items.Add(
                item
            )

        selected.UnselectAll()

        for item in selected_items:

            selected.SelectedItems.Add(
                item
            )

        # keep the internal list aligned with the visible order
        sync_selected_parameters(
            element_name
        )

        try:
            capture_and_save_settings()
        except:
            pass

    def move_bottom(
        element_name
    ):

        controls = control_map[
            element_name
        ]

        selected = window.FindName(
            controls["selected"]
        )

        if not selected:
            return

        selected_items = list(
            selected.SelectedItems
        )

        if not selected_items:
            return

        selected_names = []

        for item in selected_items:

            selected_names.append(
                item.Name
            )

        remaining = []

        for item in selected.Items:

            if item.Name not in selected_names:

                remaining.append(
                    item
                )

        selected.Items.Clear()

        for item in remaining:

            selected.Items.Add(
                item
            )

        for item in selected_items:

            selected.Items.Add(
                item
            )

        selected.UnselectAll()

        for item in selected_items:

            selected.SelectedItems.Add(
                item
            )

        # keep the internal list aligned with the visible order
        sync_selected_parameters(
            element_name
        )

        try:
            capture_and_save_settings()
        except:
            pass

    return {
        "filter_available_by_search": filter_available_by_search,
        "refresh_category_view": refresh_category_view,
        "setup_rcc_filters": setup_rcc_filters,
        "sync_selected_parameters": sync_selected_parameters,
        "add_parameters": add_parameters,
        "remove_parameters": remove_parameters,
        "move_up": move_up,
        "move_down": move_down,
        "move_top": move_top,
        "move_bottom": move_bottom,
    }

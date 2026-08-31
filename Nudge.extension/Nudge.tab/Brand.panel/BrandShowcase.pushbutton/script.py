# -*- coding: utf-8 -*-
"""Brand Showcase — demonstrates the toolkit's brand styles/resources live.

Opens a WPF panel styled entirely from the shared brand resource
dictionaries in lib/Resources, auto-detecting Revit's current Light/Dark
theme. Includes a toggle button to flip themes on the fly, so this
button doubles as a visual QA tool for the style guide itself.
"""

import traceback
import clr
clr.AddReference('PresentationFramework')
from pyrevit import forms, script

logger = script.get_logger()


class BrandShowcaseWindow(forms.WPFWindow):
    def __init__(self, xaml_file):
        forms.WPFWindow.__init__(self, xaml_file)
        # Handlers must not depend on the command scope — pyRevit tears
        # the scope down once the script returns, and a modeless window
        # outlives it. Keep the module on the instance instead.
        self._tm = theme_manager
        # Strong references to every handler — some engines collect
        # delegate targets reachable only through the .NET event.
        self._handlers = (
            self._on_theme_changed,
            self._on_closed,
            self.toggle_theme_click,
        )
        theme = self._tm.apply_theme(self)
        self._theme_watcher = self._tm.watch_theme_changes(
            self, callback=self._on_theme_changed
        )
        # Drop the theme listener and the keep-alive slot on close so
        # repeated open/close cycles don't accumulate anything.
        self.Closed += self._on_closed
        self._set_theme_label(theme)
        # Explicit wiring — more reliable than XAML Click="..." on
        # dynamically-loaded (non-compiled) XAML in pyRevit.
        self.ToggleThemeBtn.Click += self.toggle_theme_click
        # Modeless: register on the engine-persistent holder, otherwise
        # the window stays visible but its buttons stop responding once
        # the command that opened it has ended.
        self._tm.keep_alive(self)

    def _on_closed(self, sender, args):
        self._tm.stop_watching(self._theme_watcher)
        self._tm.release(self)

    def _set_theme_label(self, theme):
        self.ThemeLabel.Text = "Current theme: {0}".format(theme)

    def _on_theme_changed(self, new_theme):
        self._set_theme_label(new_theme)

    def toggle_theme_click(self, sender, args):
        try:
            new_theme = self._tm.toggle_theme(self)
            self._set_theme_label(new_theme)
        except Exception:
            # Guidelines §5: plain-language headline, technical detail
            # collapsed under the details toggle — never a raw stack dump.
            forms.alert(
                "The theme didn't switch. Try again?",
                title="Brand Showcase — Toggle Theme",
                expanded=traceback.format_exc()
            )


if __name__ == '__main__':
    try:
        import theme_manager
        # Local module-global reference as well — belt and braces
        # against engines that collect unreferenced windows.
        window = BrandShowcaseWindow('ui.xaml')
        window.show(modal=False)
    except Exception as ex:
        # Guaranteed-visible error, regardless of output console state.
        forms.alert(
            "Brand Showcase failed to open:\n\n{0}\n\n{1}".format(
                str(ex), traceback.format_exc()
            ),
            title="Brand Showcase — Error",
            expanded=traceback.format_exc()
        )

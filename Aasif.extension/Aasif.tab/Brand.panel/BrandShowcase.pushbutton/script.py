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
from System.Windows import MessageBox
from pyrevit import forms, script

logger = script.get_logger()


class BrandShowcaseWindow(forms.WPFWindow):
    def __init__(self, xaml_file):
        forms.alert("DEBUG BUILD 3 — script.py loaded fresh.", title="Canary Check")
        forms.WPFWindow.__init__(self, xaml_file)
        theme = theme_manager.apply_theme(self)
        theme_manager.watch_theme_changes(self, callback=self._on_theme_changed)
        self._set_theme_label(theme)
        # Explicit wiring — more reliable than XAML Click="..." on
        # dynamically-loaded (non-compiled) XAML in pyRevit.
        self.ToggleThemeBtn.Click += self.toggle_theme_click
        self.TestPlainBtn.Click += self.test_plain_click

    def test_plain_click(self, sender, args):
        MessageBox.Show(self, "Plain button click received.", "Isolation Test")

    def _set_theme_label(self, theme):
        self.ThemeLabel.Text = "Current theme: {0}".format(theme)

    def _on_theme_changed(self, new_theme):
        self._set_theme_label(new_theme)

    def toggle_theme_click(self, sender, args):
        try:
            new_theme = theme_manager.toggle_theme(self)
            self._set_theme_label(new_theme)
            MessageBox.Show(self, "Toggled to: {0}".format(new_theme), "Toggle Theme")
        except Exception as ex:
            MessageBox.Show(
                self,
                "Toggle failed:\n\n{0}\n\n{1}".format(str(ex), traceback.format_exc()),
                "Toggle Theme — Error"
            )


if __name__ == '__main__':
    try:
        import theme_manager
        BrandShowcaseWindow('ui.xaml').show(modal=False)
    except Exception as ex:
        # Guaranteed-visible error, regardless of output console state.
        forms.alert(
            "Brand Showcase failed to open:\n\n{0}\n\n{1}".format(
                str(ex), traceback.format_exc()
            ),
            title="Brand Showcase — Error",
            expanded=traceback.format_exc()
        )

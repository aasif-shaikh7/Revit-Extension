# -*- coding: utf-8 -*-
"""
Brand theme manager for pyRevit toolkit UI.

Detects whether Revit is running in Light or Dark theme and merges the
matching brand resource dictionaries (colors, typography, controls) into
a WPF window's Resources. Works from any pyRevit script (IronPython or
CPython engine) since it only relies on pythonnet / .NET, not pyRevit-
specific APIs.

Usage (inside a pyRevit forms.WPFWindow subclass):

    import theme_manager

    class MyForm(forms.WPFWindow):
        def __init__(self, xaml_file):
            forms.WPFWindow.__init__(self, xaml_file)
            theme_manager.apply_theme(self)
            self._watcher = theme_manager.watch_theme_changes(self)
            self.Closed += lambda s, a: theme_manager.stop_watching(self._watcher)
            theme_manager.keep_alive(self)  # REQUIRED for show(modal=False)
"""

import os
import clr

clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')

from System.Windows.Markup import XamlReader
from System.IO import FileStream, FileMode, FileAccess

try:
    # Revit 2024+ exposes the active UI theme directly.
    from Autodesk.Revit.UI import UIThemeManager
    HAS_REVIT_THEME_API = True
except Exception:
    HAS_REVIT_THEME_API = False

THEME_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Resources")


def _load_dictionary(xaml_path):
    """Load a .xaml ResourceDictionary file from disk."""
    fs = FileStream(xaml_path, FileMode.Open, FileAccess.Read)
    try:
        return XamlReader.Load(fs)
    finally:
        fs.Close()


def get_current_theme():
    """
    Return 'Light' or 'Dark' based on Revit's active UI theme.
    Falls back to the Windows OS app theme setting if the Revit API
    isn't available (pre-2024), and defaults to 'Light' as a last resort.
    """
    if HAS_REVIT_THEME_API:
        try:
            current = str(UIThemeManager.CurrentTheme)  # 'Light' or 'Dark'
            if current in ("Light", "Dark"):
                return current
        except Exception:
            pass

    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path)
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return "Light" if value == 1 else "Dark"
    except Exception:
        return "Light"


def apply_theme(window, theme=None):
    """
    Merge the brand color/typography/control dictionaries onto a window.
    `window` is any System.Windows.Window (e.g. a pyRevit forms.WPFWindow).
    Pass `theme='Light'` / `theme='Dark'` to force a theme instead of
    auto-detecting.
    """
    theme = theme or get_current_theme()
    theme = "Dark" if str(theme).lower().startswith("dark") else "Light"

    resources = window.Resources
    resources.MergedDictionaries.Clear()

    color_file = os.path.join(THEME_DIR, "Brand.Colors.{0}.xaml".format(theme))
    typography_file = os.path.join(THEME_DIR, "Brand.Typography.xaml")
    controls_file = os.path.join(THEME_DIR, "Brand.Controls.xaml")

    for f in (color_file, typography_file, controls_file):
        resources.MergedDictionaries.Add(_load_dictionary(f))

    # Stash the active theme name on the window so toggle_theme() and
    # your own code can check it later (e.g. window.Tag == "Dark").
    window.Tag = theme
    return theme


def toggle_theme(window):
    """Flip between Light and Dark on demand (e.g. wired to a button click)."""
    current = getattr(window, "Tag", None) or get_current_theme()
    new_theme = "Dark" if str(current) == "Light" else "Light"
    return apply_theme(window, new_theme)


def watch_theme_changes(window, callback=None):
    """
    Optional: auto re-apply the theme if the user flips Revit's own
    Light/Dark setting while the toolkit window is still open.
    Only available where the Revit event exists; silently does nothing
    on engines/versions without it.

    Returns the subscribed .NET handler (or None) so the caller can
    unsubscribe via stop_watching() when the window closes.
    """
    if not HAS_REVIT_THEME_API:
        return None

    def _on_change(sender, args):
        new_theme = apply_theme(window)
        if callback:
            callback(new_theme)

    try:
        UIThemeManager.CurrentThemeChanged += _on_change
        return _on_change
    except Exception:
        return None


def stop_watching(handler):
    """
    Unsubscribe a watcher returned by watch_theme_changes(). Call it
    from the window's Closed event so repeated open/close cycles don't
    accumulate dead handlers. Silently ignores None / unsupported hosts.
    """
    if not HAS_REVIT_THEME_API or handler is None:
        return
    try:
        UIThemeManager.CurrentThemeChanged -= handler
    except Exception:
        pass


# ------------------------------------------------------------
# Modeless-window lifetime (pyRevit quirk)
# ------------------------------------------------------------
# pyRevit tears a command's scope down once the script returns. A
# modeless window (window.show(modal=False)) whose only references
# live in that scope stays VISIBLE, but its Python-side event wiring
# dies — buttons stop responding. Holding the window on this module
# (which persists in the engine's sys.modules for the whole session)
# keeps the window, its class and its bound handlers alive.
_ACTIVE_WINDOWS = []


def keep_alive(window):
    """Keep a modeless window responsive after the command scope ends.

    Call it before ``window.show(modal=False)``. Returns the window so
    it can be assigned inline. Pair with :func:`release` on close.
    """
    if window not in _ACTIVE_WINDOWS:
        _ACTIVE_WINDOWS.append(window)
    return window


def release(window):
    """Drop a window kept alive by :func:`keep_alive` (call on close)."""
    if window in _ACTIVE_WINDOWS:
        _ACTIVE_WINDOWS.remove(window)

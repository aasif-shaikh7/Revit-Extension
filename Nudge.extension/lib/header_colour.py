# -*- coding: utf-8 -*-
"""Header colour - the owner's own choice of colour for the dialog header.

The header band was fixed at the owner's red (#C8102E, v1.33.0). This
module lets the owner pick another one from inside the dialog: a short
list of presets, or any hex colour typed by hand.

Any colour must keep the title readable. For every background there is
always a text colour - white or black - that reaches the WCAG AA 4.5:1 a
person needs (the worst case, a mid tone, still allows 4.58:1 one way or
the other), so no colour has to be refused: the text
simply flips to whichever reads better. The harness checks that promise
across the whole colour cube, not only on the presets.

Pure Python (re only): no Revit, no WPF. The dialog code turns the hex
strings into brushes.
"""
import re

SETTINGS_KEY = "header_colour"

DEFAULT_HEADER_COLOUR = "#C8102E"

# Shown in this order. Each is dark enough for white text; the harness
# measures every one.
HEADER_PRESETS = (
    ("Red (default)", "#C8102E"),
    ("Maroon", "#7A1F2B"),
    ("Navy", "#1F3864"),
    ("Teal", "#0F5257"),
    ("Forest", "#1E5631"),
    ("Plum", "#5B2A5E"),
    ("Brown", "#6B3E26"),
    ("Charcoal", "#2F2F2F"),
)

CUSTOM_LABEL = "Custom..."

# Title and subtitle pairs. The subtitle is a shade softer than the
# title but must pass on its own; when it would not, the title colour
# is used for both.
LIGHT_TEXT = ("#FFFFFF", "#FFEDEF")
# Pure black, not a soft #111111: against white, black is what keeps the
# worst case - a mid tone near #877850 - above 4.5:1. With #111111 that
# colour only reached 4.35:1 (measured), and the promise above would fail.
DARK_TEXT = ("#000000", "#2B2B2B")

MIN_TEXT_CONTRAST = 4.5

_HEX = re.compile(r"^#?([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")


def normalize_hex(text):
    """`c8102e`, `#C8102E` or `#C12` -> `#C8102E` / `#CC1122`; else None."""
    match = _HEX.match(str(text or "").strip())
    if not match:
        return None
    digits = match.group(1).upper()
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    return "#" + digits


def _channel(value):
    value = value / 255.0
    if value <= 0.03928:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_colour):
    """WCAG 2 relative luminance of a `#RRGGBB` colour."""
    colour = normalize_hex(hex_colour)
    if colour is None:
        raise ValueError("not a colour: {0!r}".format(hex_colour))
    red = int(colour[1:3], 16)
    green = int(colour[3:5], 16)
    blue = int(colour[5:7], 16)
    return (0.2126 * _channel(red) + 0.7152 * _channel(green)
            + 0.0722 * _channel(blue))


def contrast_ratio(first, second):
    """WCAG 2 contrast ratio between two colours, 1.0 to 21.0."""
    one = relative_luminance(first)
    two = relative_luminance(second)
    lighter, darker = max(one, two), min(one, two)
    return (lighter + 0.05) / (darker + 0.05)


def header_text_colours(background):
    """(title, subtitle) colours that read on this header background.

    Near-white or near-black, whichever reads better on this colour. The
    subtitle keeps its softer shade only while that shade still passes
    4.5:1 on its own.
    """
    colour = normalize_hex(background) or DEFAULT_HEADER_COLOUR
    light = contrast_ratio(colour, LIGHT_TEXT[0])
    dark = contrast_ratio(colour, DARK_TEXT[0])
    title, subtitle = LIGHT_TEXT if light >= dark else DARK_TEXT
    if contrast_ratio(colour, subtitle) < MIN_TEXT_CONTRAST:
        subtitle = title
    return title, subtitle


def resolve_header_colour(saved):
    """The colour to paint: the saved one when it is a colour, else the default."""
    return normalize_hex(saved) or DEFAULT_HEADER_COLOUR


def preset_index(hex_colour):
    """Position of this colour in HEADER_PRESETS, or None for a custom colour."""
    colour = normalize_hex(hex_colour)
    for index, (_label, preset) in enumerate(HEADER_PRESETS):
        if preset == colour:
            return index
    return None


def is_default(hex_colour):
    """True when this is the shipped red, so the theme's own brushes apply."""
    return normalize_hex(hex_colour) == DEFAULT_HEADER_COLOUR

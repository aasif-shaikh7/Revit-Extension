# Brand Guidelines
### [Toolkit Name] — Revit Extension Toolkit

*Active toolkit name: Nudge. Earlier naming options are retained below as decision history.*

---

## 1. Brand Overview

**What we are:** A Revit add-in toolkit that makes everyday modeling, documentation, and QA tasks faster — without asking users to leave the workflow they already know.

**Personality:** Friendly & approachable. We talk like a helpful colleague standing next to someone at their desk — not a software manual, not a sales pitch. Plain language, clear next steps, zero jargon-for-jargon's-sake.

**Visual promise:** Feels native to Revit (so it never feels like a bolted-on plugin), but noticeably more polished — the "premium tool in the toolbox" rather than a generic ribbon button.

---

## 2. Naming Options

Pick one, or use these as a springboard:

| Name | Why it works |
|---|---|
| **Forma** | Short, architectural, easy to say out loud in a team meeting |
| **Anvil** | Craftsman/toolkit feel, sturdy and premium, memorable |
| **Kitbash** | Playful, implies a toolkit of parts you assemble |
| **Trueline** | Evokes precision/drafting, still friendly to say |
| **Nudge** | Very approachable, implies small smart assists inside Revit |

*This document uses "the Toolkit" as a placeholder — do a find/replace once you land on a name.*

---

## 3. Voice & Tone

### Principles
1. **Talk like a person, not a changelog.** "Fixed the wall-join bug that was driving you nuts" beats "Resolved geometry intersection anomaly."
2. **Lead with the outcome, not the mechanism.** Tell users what they get before how it works.
3. **Short sentences. Active voice. Contractions are fine.**
4. **Confident, never condescending.** Assume the user is a skilled architect/engineer who is simply busy — never talk down.
5. **Humor in small doses only** — a light touch in empty states or tooltips, never in error messages involving lost work.

### Do / Don't

| Do | Don't |
|---|---|
| "Nice — 42 duplicate views cleaned up." | "Operation completed successfully. 42 items processed." |
| "Something didn't load. Try again?" | "Error: Exception 0x8007 — see log." |
| "This one's still in beta — expect rough edges." | "This feature is currently undergoing quality assurance validation." |
| "You're about to delete 12 sheets. Sure?" | "Confirm deletion of selected elements (12)." |

### Where voice shows up
- Ribbon tooltips and button labels
- Dialog copy and empty states
- Error/warning messages
- Release notes
- Onboarding / first-run walkthrough
- Website & docs

---

## 4. Visual Identity

### 4.1 Design intent
Match Revit's own chrome closely enough that the Toolkit feels installed, not injected — same corner radii logic, same density, same iconography weight as the native ribbon — then layer in one confident accent color and slightly more generous spacing to signal "premium."

### 4.2 Color Palette

**The owner's palette (v1.33.0-v1.34.1).** Chosen colour by colour in a live picker after
thirteen proposed designs were turned down, and measured for contrast before it shipped. Every
value below is a token in `Nudge.extension/lib/Resources/Brand.Colors.Light.xaml` and its Dark
twin; nothing in the code carries a hex of its own.

The earlier "Ember" amber (`#F2994A`) was dropped because white text on it reads at **2.23:1**,
under the 4.5:1 a person needs. Text contrast is now a release gate - `test_xlsx_writer.py` fails
if any pair falls below it.

| Token | Light | Dark | Use |
|---|---|---|---|
| `HeaderBandBrush` | `#C8102E` | `#C8102E` | The header band behind the title; white text on it, 5.9:1. **Default only** - since v1.36.0 the owner picks the header colour in the dialog footer (eight presets or any hex), and the title turns white or black to stay at 4.5:1 or better (`lib/header_colour.py`). Since v1.36.1 the workbook's header rows follow the same choice |
| `PrimaryBrush` | `#F4A582` | `#F4A582` | Export button, ticked boxes. Text and tick are **black** (9.5:1); white would be 2.0:1 |
| `PrimaryHoverBrush` / `PrimaryPressedBrush` | `#E98E68` / `#DB7B54` | same | Hover and pressed |
| `SelectedBrush` | `#C6F432` | `#C6F432` | Selected list item, black text, 14.7:1 |
| `AccentBrush` | `#111111` | `#EDEDED` | The rule under the header and the active tab. Black vanishes on Revit's dark grey, hence the light value there |
| `TabStripBrush` / `TabHoverBrush` | `#FFE699` / `#FFD966` | `#3D3317` / `#4D4020` | The tab strip: Excel's "Gold, Accent 4" tints in Light, a deep gold in Dark |

**In the exported workbook** (`lib/export_engine.py`): `THEME_HEADER #C8102E` for the title and
header rows with white text, `THEME_BAND` / `THEME_SUBBAND #DAE9F8` for the site band rows (Excel's
own "Dark Blue, Text 2, Lighter 90%", read from the owner's Excel), `THEME_TOTALS #EEF9CC` for
TOTAL rows.

**Light mode (matches Revit light theme)**

| Token | Hex | Use |
|---|---|---|
| Surface | `#FFFDF9` | Panels, dialogs (the owner's "warm" ground) |
| Surface-alt | `#F6F1EA` | Footer and strip backgrounds |
| Border | `#E2D9CC` | Dividers, input borders |
| Text primary | `#1E2329` | Body text |
| Text secondary | `#5B6470` | Captions, hints (6.0:1 on surface) |

**Dark mode (matches Revit dark theme)**

| Token | Hex | Use |
|---|---|---|
| Surface | `#2B2B2B` | Panels, dialogs (Revit's own dark grey) |
| Surface-alt | `#232323` | Footer and strip backgrounds |
| Border | `#40454C` | Dividers, input borders |
| Text primary | `#EDEDED` | Body text |
| Text secondary | `#A0A0A0` | Captions, hints (5.4:1 on surface) |

**System colors (both modes)**

| Purpose | Hex |
|---|---|
| Success | `#15803D` light / `#4CC38A` dark |
| Warning | `#A16207` light / `#E0A62B` dark |
| Error | `#C62828` light / `#EF6B61` dark |
| Info | `#0369A1` light / `#5DADE2` dark |

The header red and the error red are close relatives. Errors are told apart by where they appear
(the footer status line, never the band) and by their words, never by colour alone.

### 4.3 Typography

- **UI text:** Consolas, the owner's pick (fallbacks: Cascadia Mono, Segoe UI). It is wider
  than a proportional face, which is why the dialog footer wraps to two rows.
- **Marketing / docs / website:** Inter — modern, geometric, pairs cleanly with Segoe UI without clashing.
- **Weights:** Regular for body, Semibold for labels/headers, avoid Bold except for critical alerts.
- **Sizing (UI):** 12px body, 13px labels, 16–18px dialog titles. Keep it dense — Revit users are used to information-rich panels.

### 4.4 Iconography

- Line-weight icons at 1.5–2px stroke, matching Revit's native ribbon icon weight so custom buttons don't stick out.
- 24×24px grid for ribbon icons, 16×16px for inline/list icons.
- Single accent color for active/selected icon states only — keep the rest monochrome (matches surrounding theme) so the toolkit doesn't look "busy" next to native tools.
- Rounded terminals, no sharp caps — softens the toolkit against Revit's more mechanical native icon set.

### 4.5 Spacing & Elevation

- Base unit: 4px grid.
- Dialog padding: 16–20px (slightly more generous than Revit's native 8–12px — this is where "premium" shows up).
- Corner radius: 4px for buttons/inputs, 8px for dialog/panel containers, 0px for anything docked to Revit's own chrome.
- Elevation: subtle 1–2px soft shadow on floating panels only (opacity ~12%); no shadows on docked/pinned elements, to stay flush with Revit's flat native surfaces.

---

## 5. UI Component Notes

- **Buttons:** Primary = `PrimaryBrush` fill with `PrimaryForegroundBrush` text (black on the current peach). Secondary = outline, neutral text. Never more than one primary button per dialog.
- **Dialogs:** Title in Semibold, one clear primary action bottom-right, cancel/secondary to its left — matches Windows/Revit convention, don't reinvent it.
- **Empty states:** Always paired with one friendly line of copy + one clear action, never just a blank panel or icon.
- **Errors:** Plain-language headline, technical detail collapsed under a "details" toggle for support/debugging — never dump a stack trace into the primary message.
- **Loading states:** Use short, specific status text ("Scanning 240 views…") over generic spinners where possible.

---

## 6. Do's and Don'ts Summary

**Do**
- Keep every dialog feeling like it belongs in Revit's own UI
- Use the accent sparingly — it should mean "this is the toolkit talking to you," not decorate everything
- Write copy the way you'd explain it to a teammate over Slack

**Don't**
- Don't introduce a second accent color without a strong reason
- Don't use Revit's own blue as an accent — it reads as native UI, not the toolkit's own actions
- Don't let error messages be colder or more technical than the rest of the voice

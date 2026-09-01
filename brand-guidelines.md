# Brand Guidelines
### [Toolkit Name] — Revit Extension Toolkit

*Working name to be finalized. See naming options below.*

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

**Primary accent — Ember**
A warm amber/orange. Distinct from Autodesk's own blue chrome, so the Toolkit's actions are always identifiable at a glance, and it reads as "tool," not "tech."

| Token | Hex | Use |
|---|---|---|
| Ember 500 (primary) | `#F2994A` | Primary buttons, active states, key icons |
| Ember 600 (hover/pressed) | `#D97C2B` | Hover/pressed states |
| Ember 100 (tint) | `#FCE8D5` | Light-mode highlight backgrounds |
| Ember 900 (deep) | `#7A3F14` | Dark-mode accent text on light chips |

**Light mode (matches Revit light theme)**

| Token | Hex | Use |
|---|---|---|
| Surface | `#FFFFFF` | Panels, dialogs |
| Surface-alt | `#F3F3F3` | Ribbon/toolbar background |
| Border | `#D6D6D6` | Dividers, input borders |
| Text primary | `#1F1F1F` | Body text |
| Text secondary | `#6B6B6B` | Captions, hints |

**Dark mode (matches Revit dark theme)**

| Token | Hex | Use |
|---|---|---|
| Surface | `#2B2B2B` | Panels, dialogs |
| Surface-alt | `#232323` | Ribbon/toolbar background |
| Border | `#3F3F3F` | Dividers, input borders |
| Text primary | `#EDEDED` | Body text |
| Text secondary | `#A0A0A0` | Captions, hints |

**System colors (both modes)**

| Purpose | Hex |
|---|---|
| Success | `#3FB68B` |
| Warning | `#E0A62B` |
| Error | `#E4574C` |
| Info | `#4C9BE4` |

### 4.3 Typography

- **UI text:** Segoe UI Variable (Windows-native, matches Revit exactly). Fallback: Segoe UI.
- **Marketing / docs / website:** Inter — modern, geometric, pairs cleanly with Segoe UI without clashing.
- **Weights:** Regular for body, Semibold for labels/headers, avoid Bold except for critical alerts.
- **Sizing (UI):** 12px body, 13px labels, 16–18px dialog titles. Keep it dense — Revit users are used to information-rich panels.

### 4.4 Iconography

- Line-weight icons at 1.5–2px stroke, matching Revit's native ribbon icon weight so custom buttons don't stick out.
- 24×24px grid for ribbon icons, 16×16px for inline/list icons.
- Single accent color (Ember) for active/selected icon states only — keep the rest monochrome (matches surrounding theme) so the toolkit doesn't look "busy" next to native tools.
- Rounded terminals, no sharp caps — softens the toolkit against Revit's more mechanical native icon set.

### 4.5 Spacing & Elevation

- Base unit: 4px grid.
- Dialog padding: 16–20px (slightly more generous than Revit's native 8–12px — this is where "premium" shows up).
- Corner radius: 4px for buttons/inputs, 8px for dialog/panel containers, 0px for anything docked to Revit's own chrome.
- Elevation: subtle 1–2px soft shadow on floating panels only (opacity ~12%); no shadows on docked/pinned elements, to stay flush with Revit's flat native surfaces.

---

## 5. UI Component Notes

- **Buttons:** Primary = Ember fill, white text. Secondary = outline, neutral text. Never more than one primary button per dialog.
- **Dialogs:** Title in Semibold, one clear primary action bottom-right, cancel/secondary to its left — matches Windows/Revit convention, don't reinvent it.
- **Empty states:** Always paired with one friendly line of copy + one clear action, never just a blank panel or icon.
- **Errors:** Plain-language headline, technical detail collapsed under a "details" toggle for support/debugging — never dump a stack trace into the primary message.
- **Loading states:** Use short, specific status text ("Scanning 240 views…") over generic spinners where possible.

---

## 6. Do's and Don'ts Summary

**Do**
- Keep every dialog feeling like it belongs in Revit's own UI
- Use Ember sparingly — it should mean "this is the toolkit talking to you," not decorate everything
- Write copy the way you'd explain it to a teammate over Slack

**Don't**
- Don't introduce a second accent color without a strong reason
- Don't use Revit's own blue as an accent — it reads as native UI, not the toolkit's own actions
- Don't let error messages be colder or more technical than the rest of the voice

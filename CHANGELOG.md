# Changelog

**Document:** `CHANGELOG.md`
**Status:** Active — records only what has actually been established

All notable changes to the Revit-Extension (RCC BOQ) will be documented in this file.

The extension uses **semantic versioning** (`MAJOR.MINOR.PATCH`, see `PROJECT_STRUCTURE.md`
§Versioning). This changelog records only what has actually been established — commits in git and,
where applicable, what the XLSX harness verifies.

The format is inspired by [Keep a Changelog](https://keepachangelog.com/). Development history that
predates the first semantic release is recorded under "Established so far" and retrospectively
tagged `v0.x`.

**Verification vocabulary** used in this file:
- **Tested** — verified by `python test_xlsx_writer.py` (engine) when labelled `(harness)`.
- **Unverified** — present in code but not run in a live Revit session by an agent; the project
  owner confirms in-Revit behavior on a real project.

Nothing below claims a live Revit feature was verified by an agent when only the harness ran.

---

## [v1.7.7] - 2026-08-31

### Fixed
- **Search box text size**: `BrandTextBox` FontSize 12→14, Padding 8,6→10,7, FontFamily explicitly "Segoe UI" (was `BrandFontFamily` dynamic resource which may not resolve under IronPython, causing small/blurry text)

---

## [Unreleased] — Search-box full visual paint (background + border) — code `v1.7.6`

**Fix (unreleased; code `v1.7.6`).** The four search boxes are now painted entirely with
concrete theme brushes via `SetValue` — text, caret, **background and border** included —
re-applied on every theme switch. No visual property is left dependent on runtime dynamic
resources after the Brand dictionaries merge (the IronPython quirk can otherwise leave a box
that looks "not proper"). Light: `#FFFFFF` surface / `#D6D6D6` border / `#1F1F1F` text; Dark:
`#2B2B2B` surface / `#3F3F3F` border / `#EDEDED` text.

**Tested (off-Revit).** `python -m py_compile` clean; `python test_xlsx_writer.py` ends
`RESULT: all checks passed` (engine untouched). **Unverified live** — owner to reload and
confirm the search boxes look proper in both themes.

---

## [Unreleased] — Search-box text visibility fix (round 4, concrete brush) — code `v1.7.5`

**Fix (unreleased; code `v1.7.5`).** Dynamic-resource `Foreground` does not reliably reach the
TextBox's internal text editor under IronPython after the theme dictionaries are re-merged —
the typed text fell back to the system window-text colour and became invisible on Light.
`BrandTextBox` now uses the **default WPF TextBox template** (text renders straight from
`Foreground`), and `_apply_search_foregrounds()` assigns **concrete `SolidColorBrush` values via
`SetValue`** on all four search boxes: `Foreground`/`CaretBrush` = theme primary (`#1F1F1F` /
`#EDEDED` from `window.Tag`), `SelectionBrush` = Ember, `SelectionTextBrush` = white. Local
`SetValue` needs no resource lookup, so the text and caret are always visible; re-applied on
every theme switch.

**Tested (off-Revit).** `Brand.Controls.xaml` well-formed; `python -m py_compile` clean;
`python test_xlsx_writer.py` ends `RESULT: all checks passed` (engine untouched).
**Unverified live** — owner to reload and confirm visible search text + caret in both themes.

---

## [Unreleased] — Search-box text visibility fix (round 3, programmatic) — code `v1.7.4`

**Fix (unreleased; code `v1.7.4`).** Template-only (v1.7.2) and element-XAML (v1.7.3)
`DynamicResource` foreground fixes did not make the typed search text visible on the live
IronPython dialog. `script.py` now applies the same **`SetResourceReference`** pattern the
confirmed-visible status bar uses: `_apply_search_foregrounds()` pins
`TextBox.ForegroundProperty` / `CaretBrushProperty` to `TextPrimaryBrush` on all four search
boxes after every theme apply/switch (plus a first-paint safety net). The reference resolves
after the brand dictionaries are merged, so text and caret render regardless of theme.

**Tested (off-Revit).** `python -m py_compile` clean; `python test_xlsx_writer.py` ends
`RESULT: all checks passed` (engine untouched). **Unverified live** — owner to reload and
confirm visible search text / caret in both themes.

---

## [Unreleased] — Search-box text visibility fix (round 2) — code `v1.7.3`

**Fix (unreleased; code `v1.7.3`).** Round 1's template-only change was not enough on the live
dialog. The four search `TextBox`es now set `Foreground` and `CaretBrush` **directly on the
element** in `ui.xaml` — the same pattern the visible list boxes use — so the typed text and
caret always render in `TextPrimaryBrush` after the runtime theme dictionary merge.

**Tested (off-Revit).** `ui.xaml` well-formed; `python -m py_compile` clean;
`python test_xlsx_writer.py` ends `RESULT: all checks passed` (engine untouched).
**Unverified live** — owner to reload and confirm visible text + caret in both themes.

---

## [Unreleased] — Search-box text visibility fix — code `v1.7.2`

**Fix (unreleased; code `v1.7.2`).** Typed text in the four search boxes could be invisible
after the runtime brand dictionaries are merged: the custom TextBox template's text view was
not explicitly inheriting the control's foreground. `BrandTextBox` now sets
`CaretBrush`/`SelectionBrush`/`SelectionTextBrush` and applies
`TextElement.Foreground="{TemplateBinding Foreground}"` on `PART_ContentHost`, so the input and
the caret always render in `TextPrimaryBrush`. Disabled text dims the caret too.

**Tested (off-Revit).** `Brand.Controls.xaml` well-formed; `python -m py_compile` clean;
`python test_xlsx_writer.py` ends `RESULT: all checks passed` (engine untouched).
**Unverified live** — owner to reload and confirm visible text + caret in both themes.

---

## [Unreleased] — Double-click move + no duplicates between lists — code `v1.7.1`

**New UI (unreleased; code `v1.7.1`).** The parameter picker now supports fast mouse-only
selection:
- **Double-click** on an Available parameter adds it to Selected; double-click on a Selected
  parameter removes it back. Wired for all four categories on top of the existing buttons.
- **Available hides anything already Selected** — `filter_available_by_search` excludes the
  category's selected names while rebuilding the list, so a parameter appears in only one list
  at a time. Add/Remove/search/filter/restore all stay consistent with the single-set rule.

**Tested (off-Revit).** `python -m py_compile` clean; `python test_xlsx_writer.py` ends
`RESULT: all checks passed` (engine untouched). **Unverified live** — owner to reload in
Revit 2025 and confirm the double-click moves and the single-set rule.

---

## [Unreleased] — PCC beds belong to the Foundation tab — code `v1.7.0`

**New classification (unreleased; code `v1.7.0`).** PCC (plain cement concrete) beds under
footings / combined footings, which are commonly modeled as **floors** in Revit, now appear in
the **Foundation** tab instead of the Slab tab.

- New `is_pcc_element` — word-boundary `pcc` token check on the element identity
  (name / type / family / common labels).
- `classify_foundation_subtype` checks PCC **first**, so "PCC F1", "PCC-CF2" or "PCC Slab"
  classify as the Foundation **PCC** subtype regardless of modeling storage or other tokens.
- `category_elements` / `refresh_category_view`: PCC floors move from Slab to Foundation in the
  initial state and after every filter change. The Foundation **PCC** filter lists them, and
  they flow into the element sheets, BOQ by Level, BOQ by Grade and Costing.
- Version bumped to **1.7.0** (`__version__` + `SCRIPT_VERSION`).

**Tested (off-Revit).** `python -m py_compile` clean; `python test_xlsx_writer.py` ends
`RESULT: all checks passed` (engine untouched). **Unverified live** — owner to reload in
Revit 2025 and confirm PCC beds show under Foundation (and no longer under Slab).

---

## [Unreleased] — Grade fix (case-insensitive) + classic column cleanup — code `v1.6.2`

**Fix.** The engine `Grade` column showed `(No Grade)` on projects whose shared parameter is
named in another casing (`GRADE OF CONCRETE`): the grade lookup was case-sensitive. Grade hints
now resolve case-insensitively (element → Symbol → type), so `Grade of Concrete` matches
`GRADE OF CONCRETE` and the column carries the real grade (`M40`).

**Cleanup.** The classic workbook no longer emits the `Qty: Dim L/W/H (m)` and
`Qty: Shuttering (m2)` columns — they exist to feed the site-format workbook. Volume / Area /
Length / Height / Thickness / Count remain in the classic export.

**Tested (off-Revit).** `python -m py_compile` clean; `python test_xlsx_writer.py` ends
`RESULT: all checks passed`. **Confirmed (live, 2026-08-31).** Owner re-exported and confirmed.

---

## [Unreleased] — Concrete-grade BOQ grouping (P2 complete) — confirmed live (2026-08-31)

**New engine (unreleased; code `v1.6.0`).** P2's remaining half: the classic workbook gains a
**BOQ by Grade** sheet — quantities grouped per concrete grade (M20/M25/M30/…) x category with
live SUMIF formulas, right after BOQ by Level.

- Every element row carries an engine-added `Grade` column (column C, right after Level),
  resolved by `resolve_concrete_grade`: recognized grade parameters (Concrete Grade / Grade of
  Concrete / Grade / Concrete Type / Concrete Mix / Mix / Mix Design) → the Material parameter's
  target material name → a grade token in the element identity text (`M25` / `m-30` / `M 40`
  spellings normalize against the IS 456 M10–M80 series) → `(No Grade)`.
- `BOQ by Grade` mirrors the level sheet's contract: one row per Grade x Category, static
  Elements counts, live SUMIF per available metric, placed between BOQ by Level and Costing.
  Level/Grade grouping columns are prune-protected so the formulas always resolve; the
  missing-values audit and the site-format writer exclude the column like Level.
- Version bumped to **1.6.0** (`__version__` + `SCRIPT_VERSION`).

**Tested (harness).** `python test_xlsx_writer.py` ends `RESULT: all checks passed` — new
assertions cover Grade placement, headers, grouped rows incl. `(No Grade)`, 9 live SUMIF cells,
static counts, token normalization and the 8-sheet order; `script.py` compiles clean under
CPython 3.12.

**Confirmed (live, 2026-08-31).** Owner verified on a real model in Revit 2025: grades resolve
sensibly, the BOQ by Grade sheet works, and the rest of the export is unchanged.

---

## [Unreleased] — Site format toggle in the dialog — code `v1.6.1`, quick re-test pending

**New UI (unreleased; code `v1.6.1`).** The site-vs-classic writer choice moves out of the
hard-coded `site_format_flag` into the dialog: a fourth footer checkbox, **"Site format"**
(`SiteFormatCheck`), selects the writer at export time — checked (default) produces the manual
site-style workbook, unchecked produces the classic workbook with BOQ Summary, BOQ by Level and
the new BOQ by Grade sheets. The choice persists through the existing settings file
(`"site_format"` key) and is restored on the next run; the module flag remains the fallback
default. Same guarded wiring pattern as the other three checkboxes.

**Tested (off-Revit).** `python -m py_compile` clean; `python test_xlsx_writer.py` ends
`RESULT: all checks passed` (both writers unchanged); `ui.xaml` parses as well-formed XML.

**Confirmed (live, 2026-08-31).** Owner flipped the checkbox and confirmed both workbooks
export correctly; everything else in v1.6.0 is also live-confirmed.

---

## [Unreleased] — Theme selector + every control on the brand palette — confirmed live (2026-08-31)

**New UI (unreleased; code `v1.5.0`).** The BOQ Parameter Manager dialog gains a manual
**Theme selector** (Auto / Light / Dark) with persistence, and the brand kit itself now themes
every control the dialog uses — closing the gaps the v1.4.2 pass left on system chrome
(TabItem headers, GroupBox frames, ListBox selection, ComboBox dropdown, ScrollBars).

- **`lib/Resources/Brand.Colors.Light.xaml` / `Brand.Colors.Dark.xaml`** — new semantic
  interactive-state keys, identical in both files (verified 42-key parity): `HoverBrush`,
  `PressedBrush`, `ItemHoverBrush`, `SelectedBrush` (Ember tint; Ember-deep text in Light,
  Ember-500 text in Dark), `SelectedTextBrush`, `FocusBrush` (Ember 500), `DisabledBrush`,
  `DisabledTextBrush`, `ControlBackgroundBrush` (inputs sit slightly lighter than the Dark
  surface), `HeadingBrush`, `LabelBrush`, plus `Ember700Color` / `EmberPressedBrush` for the
  primary button's pressed state.
- **`lib/Resources/Brand.Controls.xaml`** — primary/secondary buttons gain pressed states;
  `BrandTextBox` gains hover/focus (Ember border) and disabled states; `BrandCheckBox` gets a
  full template (16 px Ember check box, white tick, disabled dimming); `BrandComboBox` gets a
  complete template (brand toggle button, arrow, rounded bordered dropdown popup) and
  `ComboBoxItem` implicit rows; new **implicit** styles for `TabItem` (folder-tab fill that
  connects to the content pane + Ember underline on the selected tab; hover background only on
  unselected tabs), `TabControl` (themed header strip band on `SurfaceAltBrush` so the tab row
  reads as a deliberate header band instead of system chrome), `GroupBox` (bordered surface
  panel with brand header text), `ListBoxItem` (Ember-tinted selection + neutral hover +
  disabled state) and `Separator`; implicit slim `ScrollBar` (Track + thumb, horizontal trigger
  variant). Implicit styles apply wherever the dictionaries are merged — the consuming
  `ui.xaml` control declarations did not change.
- **`Generate.panel/BOQ.pushbutton/ui.xaml`** — one addition only: `Theme:` label +
  `ThemeSelector` combo (`Auto (Revit)` / `Light` / `Dark`) at the head of the footer options
  row. No layout, dimension, tab, control-name or wiring changes.
- **`Generate.panel/BOQ.pushbutton/script.py`** — the guarded brand-theme block now reads the
  saved choice from the existing `.rcc_boq_settings.json` (`"theme"` key; default **Auto**)
  and applies it; the footer combo re-applies on change, saves the choice **immediately**
  through the same settings system (never waits for an export), and `capture_and_save_settings`
  carries the combo state forward so exports cannot wipe the preference. Auto mode keeps the
  pre-1.5 behavior — the dialog follows Revit's own Light/Dark setting and re-applies on
  Revit's theme flip; choosing Light/Dark pauses that watcher until Auto is picked again.
  Watcher state lives in a dict holder because Python 2.7 has no `nonlocal`. Everything stays
  guarded: if `theme_manager` or the dictionaries are missing, the dialog opens on the stock
  look and the selector degrades to a no-op. All ten status messages now route through a
  `set_status(message, kind)` helper that tints the footer status line with the matching
  semantic brush (success export green, export/metadata errors red, no-selection/no-rows
  warnings amber, filter/cancelled info blue, loading/loaded primary text) via
  `SetResourceReference`, keeping the DynamicResource link so the colour follows theme swaps.
- Version bumped to **1.5.0** (`__version__` + `SCRIPT_VERSION`).

**Tested (off-Revit).** A one-shot consistency check verified XML well-formedness of all five
touched XAML files, resolved every `DynamicResource` reference in both windows against the
merged dictionaries, resolved all intra-dictionary `StaticResource` references, confirmed
identical Light/Dark key sets (42 keys), and confirmed the `ThemeSelector` XAML/Python wiring;
the file was deleted after the run. `python -m py_compile` on `script.py` is clean, and
`python test_xlsx_writer.py` still ends with `RESULT: all checks passed` (engine untouched).

**Confirmed (UI, 2026-08-31).** Owner verified in Revit 2025 — dialog opens styled in both
themes, every control (tab headers, group boxes, list selection, combo dropdowns, scrollbars,
focus/disabled states) reads correctly, switching Auto → Light → Dark applies instantly without
reopening, the choice survives close/reopen, and Auto still follows Revit's own theme flip.

**Cost / limits.** `Auto` is the default theme (slight deviation from the original "Light
default" ask — chosen to preserve the v1.4.2 follow-Revit behavior; strict Light default is a
one-line change if wanted). Sora still renders only where installed. The installed pyRevit
(master `6.5.3`) still runs the dialog on the IronPython backend; all new code is 2.7-safe
(no `nonlocal`, no f-strings).

---

## [Unreleased] — BOQ Parameter Manager dialog consumes the brand theme — confirmed live (2026-08-31)

**New UI (unreleased; code `v1.4.2`).** The written "next step" of the Brand UI system: the BOQ
Parameter Manager dialog (`Generate.panel/BOQ.pushbutton/ui.xaml`) now consumes the shared
Light/Dark resource dictionaries instead of default WPF chrome — until now the Ember palette
reached only the exported workbook.

- **`ui.xaml`** — restyled entirely through `DynamicResource` references to the brand keys (no
  `StaticResource`, because the dictionaries are merged at runtime by `theme_manager.apply_theme`,
  which replaces the window's merged dictionaries): window and TabControl surfaces
  (`SurfaceBrush`), the brand type scale on the header/project/status text (`BrandHeaderText` /
  `BrandBodyText` / `BrandLabelText`), `BrandTextBox` on the four search boxes, `BrandComboBox` on
  the two filters, `BrandCheckBox` on the three options, `BrandSecondaryButton` on all
  Add/Remove/Up/Down/Top/Bottom + OK/Close buttons and `BrandPrimaryButton` (Ember fill) on
  Export Excel; the list boxes carry Surface/TextPrimary/Border brushes; the footer band uses
  `SurfaceAltBrush` + `BorderBrush2`. Control names, layout, tooltips and all Python wiring are
  untouched (46 `x:Name`s preserved; mechanical patch applied with per-pattern count assertions).
- **`script.py`** — guarded block right after the window is built: `theme_manager.apply_theme(window)`
  merges the dictionaries (theme auto-detected via guarded `UIThemeManager` → Windows app-theme
  registry → Light), `watch_theme_changes` re-applies if Revit's theme flips while the dialog is
  open, and the watcher is unsubscribed via `stop_watching` on the dialog's Closed event. The whole
  block degrades to the stock look if `theme_manager` or the dictionaries are unavailable. The
  dialog is modal (`ShowDialog`), so plain locals outlive the session — no `keep_alive` registration
  (that fix is for modeless windows only).
- Version bumped to **1.4.2** (`__version__` + `SCRIPT_VERSION`).

**Confirmed (UI, 2026-08-31).** Owner verified live on Revit 2025: dialog opens styled, both
themes are readable, the theme follows Revit's setting, and tabs/selection/filters/reorder/export
behave exactly as before. The XLSX engine is untouched: `python test_xlsx_writer.py` still ends
with `RESULT: all checks passed`, and `script.py` compiles clean under CPython 3.12.

**Known limits.** TabItem headers and GroupBox chrome keep their system-theme look (the brand kit
ships no TabItem/GroupBox styles); Sora renders only where the font is installed (Segoe UI
fallback); same engine reality as the showcase — the installed pyRevit (master `6.5.3`) stubs
`pyrevit.forms` for CPython, so the dialog runs the IronPython backend on this machine today.

---

## [Unreleased] — BOQ Parameter Manager: Level Sync-style header/footer composition — live QA pending

**New UI (unreleased; code `v1.4.3`).** The BOQ dialog's header and footer are restyled to match the
Level Sync Studio dialog's cleaner composition: primary action in the header, simplified footer.

- **`ui.xaml` header** — rebuilt as a `DockPanel`: a `StackPanel` on the left carries the title
  (`BrandHeaderText`), a new subtitle ("Structural Bill of Quantities — pick the parameters to export
  for Beam, Column, Slab and Foundation."), and the project name (`BrandBodyText`); the **Export
  Excel** button (`BrandPrimaryButton`) is docked **right** in the header so the primary action is
  always visible without scrolling. The header sits above the tab strip exactly like the Level Sync
  dialog.
- **`ui.xaml` footer** — simplified: the redundant **OK / Apply** button is removed (its `Click`
  handler in `script.py` is guarded by `if apply_button:`, so the missing name resolves to `None` and
  degrades gracefully); **Close** stays docked right with the options panel. The footer now mirrors
  Level Sync's minimal band.
- **`ui.xaml` tabs** — `TabControl` gets `BorderThickness="0"` for a plain underline tab strip.
- Version bumped to **1.4.3** (`__version__` + `SCRIPT_VERSION`).

**Unverified (UI).** Live confirmation on Revit 2025 is pending with the project owner: dialog opens
with the new header/footer, Export is reachable in the header, tabs/selection/filters/reorder/export
behave exactly as before. The XLSX engine is untouched: `python test_xlsx_writer.py` ends with
`RESULT: all checks passed`, `script.py` compiles clean, and the XAML parses as well-formed XML.

**Cost / limits.** Same engine reality as v1.4.2 — the dialog runs the IronPython backend; ApplyButton
wiring stays in `script.py` as dead code behind the `if apply_button:` guard.

---

## [Unreleased] — Brand UI system: shared theme resources + Brand Showcase — live QA pending

**New infrastructure (unreleased; commit `b1f3c38` + cleanup).** Turns
`docs/reference/brand-guidelines.md` from a document into the toolkit's actual UI surface: one
shared Light/Dark theme system for every WPF dialog.

- **`Aasif.extension/lib/Resources/`** — four brand resource dictionaries:
  `Brand.Colors.Light.xaml` / `Brand.Colors.Dark.xaml` (the Ember accent ramp
  `F2994A` / `D97C2B` / `FCE8D5` / `7A3F14` plus Light/Dark surface, border and text neutrals and
  the shared system success/warning/error/info colors), `Brand.Typography.xaml` (Sora with a
  Segoe UI Variable → Segoe UI fallback; header 18 / subheader 14 / label 13 / body 12 /
  caption 11, SemiBold labels, default TextBlock style) and `Brand.Controls.xaml` (Ember primary
  button with hover/pressed trigger, outline secondary button, TextBox, CheckBox, ComboBox
  chrome, status chips, dialog/ribbon containers).
- **`Aasif.extension/lib/theme_manager.py`** — `get_current_theme()` (guarded `UIThemeManager`
  lookup, falling back to the Windows `AppsUseLightTheme` registry value and then Light),
  `apply_theme()` (merges the color + typography + controls dictionaries into any `Window` and
  stashes the active theme on `window.Tag`), `toggle_theme()`, `watch_theme_changes()` (re-applies
  when Revit's own theme flips; silent no-op where the event is absent) and `stop_watching()`
  (unsubscribes the watcher from the window's Closed event so repeated open/close cycles don't
  accumulate dead handlers). Host-independent apart from the guarded Revit call site —
  pythonnet/.NET only, no pyRevit API dependency.
- **`Aasif.tab ▶ Brand.panel ▶ BrandShowcase.pushbutton`** — a live preview of every brand style
  that doubles as a Light/Dark visual QA tool (theme label + toggle; the window re-themes itself
  if Revit's theme changes while it is open, and unsubscribes its listener on close). Click
  handlers are wired explicitly in Python (`self.ToggleThemeBtn.Click += ...`) because XAML
  `Click=` attributes do not bind on dynamically-loaded XAML in pyRevit.
- **Debug scaffolding removed (cleanup).** The wiring investigation left a "DEBUG BUILD 3" canary
  alert that popped on every open, a temporary TEST isolation button and a per-toggle modal
  confirmation; all are gone. The toggle error path now follows guidelines §5 — a plain-language
  headline with the traceback collapsed under the details toggle.
- **Modeless-lifetime fix (owner feedback, 2026-08-28).** The Light/Dark toggle (and every other
  handler) was dead in the open window. Root cause: pyRevit tears a command's scope down once the
  script returns, and a `show(modal=False)` window outlives that scope — it stays visible but its
  Python-side event wiring does not. `theme_manager` now carries an engine-persistent holder
  (`keep_alive` / `release` — the module persists in the engine's `sys.modules` for the session);
  the showcase registers itself before showing, releases its slot on close, keeps strong references
  to all handlers on the instance, and reads `theme_manager` through the instance (`self._tm`) so
  no handler depends on the command scope.
- **Stray helper removed.** `_patch_summary2.py` — the one-shot patch that rewrote
  `build_site_summary_sheet` for the per-category VOLUME + SHUTTERING aggregation (already
  applied and committed in `b940f96`) — is deleted; the repo root keeps no throwaway helpers.
- **Engine reality check (diagnosis byproduct — owner attention needed).** The showcase window can
  only have opened via the **IronPython (`forms/_ipy.py`) backend**: the installed pyRevit build
  (master clone, `6.5.3`) ships `pyrevit/forms/_cpy.py` as a **stub** that raises
  `PyRevitCPythonNotSupported` for `WPFWindow` and `alert` on any CPython engine, and the machine
  carries no other `pyrevit.forms` backend. Both UI buttons (Brand Showcase and the BOQ dialog,
  which owner-confirmed working) therefore effectively run **IP27** today — the CP3123-only
  decision (T-03) does not describe the runtime yet. Before any CP3123 switch, the installed build
  needs a CPython-capable `pyrevit.forms` (or the dialogs move to raw WPF wiring without
  `pyrevit.forms`).

**Unverified (live).** This is WPF/pyRevit UI — the XLSX harness cannot execute it and the engine
is untouched. Pending owner confirmation on Revit 2025 / CP3123: the showcase opens fully styled,
the toggle flips Light/Dark instantly, and the theme follows Revit's own setting. The natural next
step after that is applying the same dictionaries to the **BOQ Parameter Manager** dialog
(`Generate.panel/BOQ.pushbutton/ui.xaml`), which currently applies the Ember palette only to the
exported workbook.

---

## [Unreleased] — v1.4.0 site-format export: manual site look + formwork (SHUTTERING) — P3 increment

**New feature (unreleased; code `v1.4.1`, tag pending).** Reproduces the hand-made site BOQ that the
owner supplied as screenshots (title blocks, light-blue two-tier headers, MM sizes,
VOLUME + SHUTTERING columns, level-wise front Summary).

- **Formwork engine (P3, first slice)** — `compute_shuttering_area`: Column `2(L+W)H`,
  Beam `(W+2H)L`, Slab soffit = plan area, Foundation footing sides `2(L+W)H`. Dimensions resolve in
  `resolve_element_dimensions` (parameters Width/Depth/Height/Thickness with bounding-box fallback);
  element rows carry `Qty: Dim L/W/H (m)` and `Qty: Shuttering (m2)`.
- **Site-format workbook writer** (`write_site_xlsx` + `build_xlsx_sheet_xml_site`): merged title
  blocks per sheet, two-tier banded headers (SIZE MM / QTY groups, `mergeCells`), whole-millimetre
  integer columns, VOLUME/SHUTTERING figures, bordered TOTAL rows with live SUMs, gridlines off,
  panes frozen below the header band. Front `Summary` = LEVEL × category grid with live SUMIF
  formulas against each detail sheet's hidden LEVEL column, closing with TOTAL m3/sqm pairs.
- **Owner feedback round (2026-08-27):** merged-cell XML no longer emits degenerate /
  overlapping spans (root cause of Excel's "We found a problem with some content…" repair
  prompt); band, data and TOTAL cells now carry a full thin-border box grid; DESCRIPTION is
  built strictly from the parameters selected for that category in the UI (selection order
  preserved), closing with the `W X L` millimetre cross-section.
- **Owner feedback round 2 (2026-08-27):** every selected parameter now
  lands in its OWN sheet column between SNO and SIZE (MM) - the combined
  DESCRIPTION cell is gone; column widths adapt to the parameter count;
  dimension feeds switched to unrounded `_site_dim_value` so MM sizes can
  never drift (6.096 m must print 6096, not 6100).
- **Owner feedback round 3 (2026-08-27):** the site workbook now exports
  ONLY the parameters the user ticked in the UI. Every detail sheet is
  `SNO` + one column per selected parameter (UI order preserved); the
  automatic `SIZE (MM) L/B/D`, `VOLUME`, `SHUTTERING` and `LEVEL` columns
  and the SUM totals row are removed. Because no quantitative feed remains,
  the front `Summary` becomes a simple per-category element-count cover
  (`SNO | CATEGORY | ELEMENTS`) instead of the level-vs-concrete SUMIF grid.
- **Brand pass `docs/reference/brand-guidelines.md` (2026-08-27):** the
  exported workbook drops Revit's own blue and applies the **Ember** accent
  ramp (header fill `F2994A`, band tint `FCE8D5`, sub-band `FFF0E3`) declared
  as `EMBER_*` constants at the top of the site-format section; UI fonts
  switch from Calibri to Windows-native **Segoe UI**. Voice pass: the export
  success alert now leads with outcome copy ("Everything's exported — here's
  your workbook.") and the empty workbook states with one friendly line plus
  the next step, instead of terse all-caps messages.
- **Switch:** `site_format_flag = True` selects the site writer at export time; the classic
  (v1.3.0-style) workbook remains available as rollback via `write_basic_xlsx(site_format=False)` —
  which itself now honours the flag when called directly.
- Version bumped to **1.4.1** (`__version__` + `SCRIPT_VERSION`).

**Tested (harness).** `python test_xlsx_writer.py` passes every check end-to-end: shuttering rules
per category, dimension fallbacks, natural level sort, detail/summary builders (`MERGE_V` markers,
MM integers, selection-driven parameter columns (one per selected parameter)), mergeCells part, live SUMIF/SUM
wiring, site + classic workbook XML validity, styles, plus a merge-grid integrity pass asserting
zero degenerate / duplicate / overlapping spans on every site sheet (Excel-repair regression
guard) and a bordered-grid check over the first data row. `script.py` also compiles clean under
CPython 3.12.

**Not yet released.** Live Revit confirmation on CP3123 still required before tagging; `v1.3.0`
remains tag-pending as well.

---

## [Unreleased] — Professional output: Summary cover + site naming convention (code v1.3.0, tag pending)

**New feature (P13-direction, first increment).**

- **Site naming convention** for exports, mirroring workbooks like
  `20260312-CHHANYADO_HOSPITAL_SURAT-CONCRETE_FINISHING_BOQ.xlsm`: the Save dialog now suggests
  **`YYYYMMDD-<Project>-CONCRETE_FINISHING_BOQ.xlsx`**, built from today's date plus the Revit
  document title (`sanitize_file_name` strips Windows-forbidden characters). The name stays
  editable before saving.
- **Front `Summary` cover sheet** (first tab): project name, generation stamp, tool version, and a
  listing of every sheet in the workbook.
- **3D view:** a true/embedded Revit 3D view inside Excel is **not feasible** through the supported
  API. The realistic option is an *Experimental* snapshot of the current 3D view embedded as an
  image sheet via window capture — implemented only if the project owner opts in.

**Tested (harness).** Cover title/meta/listing checks, file-name sanitization, and the default-name
convention regex all pass alongside every existing check.

**Not yet released.** `v1.3.0` tag is withheld until live Revit confirmation on CP3123.

---

## [1.2.0] — 2026-08-26

**Released.** P2 level-wise grouping (Level column + BOQ by Level SUMIF sheet) and the CP3123-only
engine decision — confirmed live in Revit 2025 by the project owner (points 1–4 passed, no
regression). Tag `v1.2.0`.

---

## [1.1.0] — 2026-08-26

**Released.** P1 quantity engine increment (category-aware quantities, Count, Column Height,
Slab/Foundation Thickness) — confirmed live by the project owner. Tag `v1.1.0`.

---

**New feature (P2, first increment).**

- Every element row now carries an engine-added **`Level`** column, written directly after
  `Element ID` (deterministic column B). The level name is resolved from the reference/schedule
  level built-in parameters with an `element.LevelId` fallback; unresolvable levels stay empty.
- New **`BOQ by Level`** sheet (between BOQ Summary and Costing): one row per
  **Level x Category**, with a static per-group `Elements` count and **live SUMIF formulas**
  against each category sheet's Level column — so grouped totals stay in sync with the element
  data.
- The missing-values audit excludes the engine-added Level column (it is grouping metadata, not a
  selected parameter).

**Engine decision (T-03 closed).** Only one engine is supported going forward: **CP3123 (CPython
3.12.3)** — the modern runtime. **IP27 (IronPython 2.7)** is legacy/EOL Python and is documented as
best-effort/untested rather than a support target. Code remains 2.7-syntax-safe so IP27 may still
work, but no parity testing is promised.

**Tested (harness).** `python test_xlsx_writer.py` asserts: Level column placement on element
sheets; the BOQ by Level header set; grouped rows for every collected level (including
`(No Level)`); exactly 9 live SUMIF metric cells for the sample layout (Beam has no Area column,
Foundation has no Length column); static Elements counts; and the sheet order
Beam / Column / Foundation / BOQ Summary / BOQ by Level / Costing. All checks pass.

**Released as `v1.2.0`.** Both increments confirmed live in Revit 2025 on CP3123 by the project
owner (parameter columns, level grouping, export — all correct, no regression).

---

## [Unreleased] — P1 Structural Quantity Engine (code v1.1.0, release tag pending)

**New feature (P1, first increment).** The quantity engine is now category-aware and adds
per-element **Count**, plus per-category parameter dimensions:

- **Calculated quantity (geometry/computed):** `Qty: Volume (m3)`, `Qty: Area (m2)`,
  `Qty: Length (m)` — unchanged and preserved.
- **Parameter quantity (from model, by name):** `Qty: Height (m)` for **Column**; `Qty: Thickness
  (m)` for **Slab** and **Foundation**. Read via `LookupParameter` on the element, its Symbol and
  its type; absent dimensions return `""` and are pruned automatically (existing behaviour).
- **Count:** `Qty: Count` = 1 per element row; the sheet TOTAL row sums to the element count.
  The BOQ Summary's `Elements` column is already the per-category count.
- `get_element_quantities(element)` is now `get_element_quantities(element, element_name)`; the
  value reader distinguishes **Calculated vs Parameter** quantity explicitly in the docstring.

**Tested (harness).** `python test_xlsx_writer.py` now asserts the P1 `Count` column on populated
sheets, `Height (m)` on Column and `Thickness (m)` on Foundation. All checks pass.

**Released as `v1.1.0`.** Live Revit gathering of real `Height`/`Thickness`/`Count` values confirmed
by the project owner.

---

## [1.0.1] — 2026-08-26

**Bug fix.** Element-referencing parameters exported as raw numeric ElementId.

- **Reported (live, Revit 2025):** Beam/Column/Slab/Foundation tabs work with no regression, but
  for parameters such as **Type, Level, Top Level, Base Level, Reference Level, Cover Type** the
  Excel cells showed the raw **ElementId number** instead of the element's name/value.
- **Fixed:** `safe_parameter_value` now resolves `StorageType.ElementId` parameters to the
  referenced element's **name** — preferred Revit `AsValueString()`, then `doc.GetElement(id).Name`
  (e.g. a Level shows "Level 1", a Type shows its type-family name), with the numeric id kept only
  as a last fallback. This is a single, bounded change to the value reader, so it also improves the
  classification/identity text that uses the same reader.
- Version bumped `1.0.0` → `1.0.1` (PATCH, backward-compatible bug fix).

**Tested (harness).** `python test_xlsx_writer.py` passes; `script.py` syntax valid. Live element-name
resolution requires a Revit session (project-owner confirmation; recorded in `done-list.md`).

---

## [Unreleased] — Roadmap planned (planning only, no code change)

Adopted the **Structural BOQ Development Roadmap** (see `PRD.md` §12–§18). This is documentation
only; the version stays `1.0.0` because no code changed.

- `PRD.md` — added the 16-phase Structural BOQ roadmap, feature rating system + priority ranking,
  architecture principle (keep `script.py` modular), error handling, testing workflow, regression
  protection, and the source-of-truth rule.
- `todo-list.md` — restructured around the phased roadmap (P0–P16), with P1 (quantity engine) next.
- `README.md` — added a Development Roadmap section and updated the project status.
- `CLAUDE.md` / `AI_DEVELOPMENT_GUIDE.md` — added source-of-truth, roadmap-discipline and testing
  workflow rules.
- `PROJECT_STRUCTURE.md` — added a Roadmap→Architecture section mapping each phase to its intended
  landing point.

No engine change → next semantic release is still a feature release when a real phase (e.g. P1)
is implemented.

---

## [1.0.0] — 2026-08-26

**First semantic release.** Adds version control to the extension and its pushbutton.

- `script.py` declares module metadata in its docstring — `__title__`, `__author__`,
  `__version__ = '1.0.0'`, `__min_revit_ver__ = '2025'` — and exposes a runtime `SCRIPT_VERSION`
  constant.
- The Excel export alert now reports the running version.
- Git tags `v0.1.0` … `v0.3.1` were added to the earlier commits to make development history
  visible.

**Tested (harness).** `python test_xlsx_writer.py` passes; `script.py` syntax is valid.

---

## Established so far

### `98fb30b` — Quantity takeoff and BOQ Summary sheet

**Quantity takeoff engine added.** `convert_quantity_value` converts Revit internal units to metric,
preferring `UnitUtils.ConvertFromInternalUnits` with `UnitTypeId`, falling back to
`DisplayUnitType`, then to deterministic foot-based constants. `get_element_quantities` appends
`Qty: Volume (m3)`, `Qty: Area (m2)`, `Qty: Length (m)` columns after the selected parameters so they
never disturb the parameter completeness audit.

**BOQ Summary sheet added.** The export inserts a `BOQ Summary` sheet — one row per populated
category plus a `GRAND TOTAL` — whose values are live cross-sheet `SUM()` formulas referencing the
element sheets. Empty categories do not produce a sheet. The workbook sets `fullCalcOnLoad`.

**Tested (harness).** `test_xlsx_writer.py` asserts sheet order, presence of `SUM(` formulas on the
Beam sheet, a BOQ Summary that references `Beam!` by formula, a `GRAND TOTAL` row, the auto-filter
range excluding the totals row, and the dark-blue header fill style.

### 0ab717c — Parameter metadata and Missing Values summary

**Parameter metadata capture added.** Per-parameter facts (storage type, built-in status, definition
info, data type, group, GUID) are collected into a metadata structure for the element sheets.

**Missing-values audit added.** `build_missing_values_summary` reports, per selected parameter that
has at least one empty value, the category, total elements, missing count, filled count, and fill
percentage. Completely-empty columns are pruned from the element sheets but still reported.

**Costing sheet introduced.** `build_costing_sheet` — per element row, Category, Element ID,
Quantity, Rate, and an Amount formula `Qty*Rate`, with a `SUM` `TOTAL` row. Rates are not hard-coded;
they come from whichever selected parameter name is recognized as a rate/price column.

**Note.** The metadata and missing-values functions exist and are exercised by the harness, while the
finalized workbook drops formerly-empty/tab duplicates; the harness explicitly checks that
`Parameter Metadata` and `Missing Values Summary` are **not** emitted as blank tabs.

### f14903b — BOQ pushbutton icon

**Icon added.** `icon.png` added to `BOQ.pushbutton` so the Generate panel button has a real icon.

### `09dab85` — RCC BOQ Parameter Manager UI

**Initial tool added.** `Aasif.extension/Aasif.tab/Generate.panel/BOQ.pushbutton` with `script.py`
and `ui.xaml`. Introduced the four-category dialog (Beam, Column, Slab, Foundation), per-category
parameter discovery from real elements, search + Add/Remove selection, WPF `ui.xaml` layout, status
bar, and the first dependency-free Open XML XLSX writer with element sheets and a `SaveFileDialog`.

**Tested (harness).** The XLSX engine functions are extracted from the real `script.py` and a sample
workbook is validated end-to-end.

---

## Open / unverified items

- In-Revit behavior of the dialog (parameter discovery, filters, selection, export scope, settings
  persistence, output path) — **Unverified by agent**; requires a live Revit 2025+ project on
  CP3123 and/or IP27 to certify, and is the project owner's confirmation step.
- `convert_quantity_value` numeric accuracy on actual Revit material units — the harness uses fixed
  sample data; real-model confirmation is pending.
- Dual-engine parity (CPython 3.12.3 vs IronPython 2.7) has not been executed by an agent.

Any of the above moving to "Tested" must be recorded here in the same change that establishes it.
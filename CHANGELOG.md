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

## [Unreleased] — BOQ Parameter Manager dialog consumes the brand theme — live QA pending

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

**Unverified (UI).** WPF resource loading and theme detection cannot run outside Revit; live
confirmation on Revit 2025 is pending with the project owner: dialog opens styled, both themes are
readable, the theme follows Revit's setting, and tabs/selection/filters/reorder/export behave exactly
as before. The XLSX engine is untouched: `python test_xlsx_writer.py` still ends with
`RESULT: all checks passed`, and `script.py` compiles clean under CPython 3.12.

**Known limits.** TabItem headers and GroupBox chrome keep their system-theme look (the brand kit
ships no TabItem/GroupBox styles); Sora renders only where the font is installed (Segoe UI
fallback); same engine reality as the showcase — the installed pyRevit (master `6.5.3`) stubs
`pyrevit.forms` for CPython, so the dialog runs the IronPython backend on this machine today.

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
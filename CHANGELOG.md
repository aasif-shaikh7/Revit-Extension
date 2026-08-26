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
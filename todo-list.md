# Revit-Extension — Todo List

**Document:** `todo-list.md`
**Status:** Active — the queue of work not yet finished
**Companion to:** `done-list.md`, which holds everything finished

---

## How to read this

Each open item is in one of these phases and moves down only when the previous phase is actually
true:

```text
todo      → decided but not started
pending   → design/requirement agreed
building  → code being written
testing   → code exists, being verified
done      → moved to done-list.md (for the engine: harness passes; for the UI: project-owner confirm)
```

Work follows the **Development Roadmap** in `PRD.md` (Phases 1–16). Phases are taken in order and
the next phase starts only after the previous one is stable in Revit — except when the actual
source code suggests a better order. In case of conflict, **the code wins over this document**.

An agent can move only the **engine-side** items toward `done` by running `test_xlsx_writer.py`.
Everything about the live Revit dialog stops at `testing` until the project owner runs it in Revit
2025+ on a real project.

**Verification states used:** `Unverified`, `Experimental`, `Tested (harness)`, `Tested (live)`,
`Supported`.

**Feature ratings** (Priority / Benefit / Complexity / Implementation Ease) are defined in `PRD.md`
§Feature Rating.

---

## Roadmap phase status

| Phase | Feature | Rating (P/B/C/E) | Status |
|---|---|---|---|
| P0 | Live-Revit confirmation of the current dialog | — | **done** (`v1.0.1`) |
| P1 | Structural Quantity Engine (extend, don't duplicate) | 5/5/3/4 | **done** (`v1.1.0`) |
| P2 | Structural BOQ Grouping (level done; material/grade pending) | 4/4/2/5 | `in progress` |
| P3 | Formwork Engine (configurable rules) | 5/5/3/4 | `todo` |
| P4 | Rebar Quantity Engine | 5/5/3/3 | `todo` |
| P5 | Rebar Diameter Summary + BBS | 4/5/5/2 | `todo` |
| P6 | Structural BOQ Assembly (concrete/rebar/formwork/wire/blocks/labour) | 4/5/4/3 | `todo` |
| P7 | Site / Manual Structural Items | 4/4/2/4 | `todo` |
| P8 | Structural Rule Engine (keep `script.py` modular) | 5/5/5/2 | `todo` |
| P9 | Validation Engine (compact report) | 4/4/3/4 | `todo` |
| P10 | Unmapped Element Report | 4/4/2/4 | `todo` |
| P11 | Structural Rate Analysis (material/labour/machinery/wastage/overheads) | 4/5/5/2 | `todo` |
| P12 | Structural Rate Database (configurable, not hard-coded) | 4/5/4/2 | `todo` |
| P13 | Professional Excel BOQ (extend existing XLSX engine) | 5/5/3/4 | `todo` |
| P14 | BOQ Revision (Rev 00/01/02 comparison) | 4/5/4/2 | `todo` |
| P15 | Model Change Detection (added/modified/deleted) | 3/5/5/1 | `todo` |
| P16 | Structural Dashboard | 3/4/3/4 | `todo` |

---

## P0 — Confirm the current dialog in Revit 2025 (before any new phase)

### T-01 — Confirm live-Revit behavior of the dialog — **done** (`v1.0.1`)
**State:** **Confirmed live in Revit 2025** by the project owner with **no regression** (tabs,
parameter loading, filters, reorder, export). One issue was found and fixed in `v1.0.1`:
element-referencing parameters (Type, Level, Base/Top/Reference Level, Cover Type) now export the
referenced element's **name** instead of the raw ElementId. **Acceptance met** — owner confirmed the
fix in the same Revit session. Remaining for full P0 closure: dual-engine parity (CP3123 vs IP27) is
still pending (T-03).

### T-02 — Quantity accuracy on real materials — `testing`
**State:** Metric conversion logic is deterministic and harness-tested with sample data, but true
`Qty: Volume/Area/Length` values on actual Revit elements are **Unverified**.
**Acceptance:** compare at least one beam/column/slab/foundation quantity against a known-correct
value in Revit; record any engine adjustments.

### T-03 — Dual-engine parity — **closed by decision** (`1.2.0`)
**Decision (owner, 2026-08-26):** only ONE engine is supported — **CP3123 (CPython 3.12.3)**, the
modern runtime. **IP27 (IronPython 2.7)** is legacy EOL Python and is documented as best-effort /
untested, not a support target. The code stays 2.7-syntax-safe so IP27 may still work, but no
parity testing is promised or tracked here.

---

## P2 — Structural BOQ Grouping (started)

### P2-01 — Level-wise BOQ grouping — **done** (`v1.2.0`)
**Built:** every element row carries an engine-added `Level` column (deterministic column B),
resolved from reference/schedule level parameters with a `LevelId` fallback. A new `BOQ by Level`
sheet groups quantities per Level x Category using live SUMIF formulas against the category
sheets; Elements is a static per-group count. Missing-values audit excludes the Level column.
**Tested (harness):** Level placement, grouped rows for every collected level (incl. `(No Level)`),
9 live SUMIF cells for the sample layout, static counts, final sheet order
Beam/Column/Foundation/BOQ Summary/BOQ by Level/Costing.
**Confirmed live (`v1.2.0`).** Owner verified Level resolution, grouped totals and the full export
in Revit 2025; tagged `v1.2.0`.

---

## Professional output — Summary cover + site naming (started)

### OUT-01 — Site naming convention + front Summary cover — `testing` (code v1.3.0)
**Built:** Save dialog suggests `YYYYMMDD-<Project>-CONCRETE_FINISHING_BOQ.xlsx`
(`sanitize_file_name` + document title); a front `Summary` cover sheet carries project name,
generation stamp, tool version and the sheet listing.
**Tested (harness):** cover meta/listing checks, sanitization and default-name regex all pass.
**Remaining:** live Revit confirmation of the suggested filename and cover contents; then tag
`v1.3.0`.

### OUT-02 — 3D view snapshot — `decision pending`
A true/embedded Revit 3D view inside Excel is **not feasible** via the supported API. The realistic
option is an *Experimental* image sheet capturing the current 3D view (window screenshot) — only if
the owner opts in. Exact column styling from
`20260312-CHHANYADO_HOSPITAL_SURAT-CONCRETE_FINISHING_BOQ.xlsm` also needs a layout reference
(screenshot/sheet dump) since binary workbooks cannot be read here.

---

## Site-format export — manual site BOQ look (started)

### SF-01 — Site workbook + P3 shuttering (first slice) — `engine done` (code v1.4.1)
**Built:** pure helpers — `meters_to_millimeters`, `build_section_description`
("`W X L`" mm strings), `_site_dim_value` (unrounded dims), `resolve_element_dimensions`
(param-first with bbox fallback; Column pair sorted W<=L) and `compute_shuttering_area`
(Column `2(L+W)H`, Beam `(W+2H)L`, Slab soffit, Foundation footing sides). Quantity rows
carry `Qty: Dim L/W/H (m)` + `Qty: Shuttering (m2)`; `write_site_xlsx` +
`build_xlsx_sheet_xml_site` render merged title blocks, two-tier light-blue header bands,
MM integer columns, VOLUME/SHUTTERING figures, bordered TOTAL rows and a front level-wise
Summary with live SUMIF formulas against each detail sheet's LEVEL feed column.
Dispatch sits behind `site_format_flag = True`; classic workbook stays as rollback
(`write_basic_xlsx(site_format=False)`).
**Fixed (owner feedback):** export no longer triggers Excel's repair dialog — the merge grid is
mechanically validated free of degenerate/duplicate/overlapping spans; DESCRIPTION now follows
exactly the parameters selected per category (UI selection order kept) with one column per selected parameter plus adaptive widths;
full thin-border box applied to band, data and TOTAL cells.
**Tested (harness):** full suite green — shuttering rules, dim fallbacks, level ordering,
param-driven description format, SUMIF criteria, merge-span integrity (zero bad spans),
bordered-grid styles and XML parts all pass; `script.py` compiles clean under CPython 3.12.
**Remaining:** live Revit confirmation on CP3123 (parameter-backed dims vs bbox fallback;
shuttering overlap handling at frame intersections), then tag `v1.4.0`.

---

## P1 — Structural Quantity Engine (next phase)

### P1-01 — Extend quantity engine per category — **done** (`v1.1.0`)
**Goal:** Keep the existing dependency-free engine and extend it per category — Beam (Volume, Area,
Length, Count), Column (Volume, Area, Height/Length, Count), Slab (Volume, Area, Thickness, Count),
Foundation (Volume, Area, Thickness/Count).
**Notes:** distinguishes **Parameter Quantity** (Height/Thickness, read by name) vs **Calculated
Quantity** (Volume/Area/Length); never creates a duplicate engine.
**What landed (first increment, code v1.1.0):** `get_element_quantities(element, element_name)` is
category-aware; adds `Qty: Height (m)` for Column, `Qty: Thickness (m)` for Slab/Foundation (pruned
if absent), and `Qty: Count` (=1/row, TOTAL sums to count). Harness asserts Count + Height +
Thickness columns.
**Confirmed live (`v1.1.0`).** Owner verified real Height/Thickness/Count values in Revit 2025;
tagged `v1.1.0`.

### P1-02 — Element Count column — **done** (`v1.1.0`) — implemented in P1-01
**Built** as part of `get_element_quantities`: `Qty: Count` = 1 per element row; the sheet TOTAL row
sums to the element count, and the BOQ Summary already reports the per-category count in its
`Elements` column. **Tested (harness):** asserts a Count quantity column on each populated sheet.
**Remaining:** live Revit confirmation with P1-01.

---

## Open queue (cross-cutting, draft)

### T-04 — Configuration schema / engineering notes doc — `draft`
**State:** Settings live in `.rcc_boq_settings.json` and are documented only implicitly.
**Plan:** add a short config reference (keys, defaults, how to reset) near the docs.

### T-05 — Category registry — `draft`
**State:** The four categories are hard-coded tabs.
**Plan:** decide only when a fifth category is actually requested.

### T-06 — Rate database (supersedes the simple rate parameter) — `draft`
**State:** Rates come from a single recognized parameter.
**Plan:** becomes Phase 12 (P12) work; keep current behaviour until then.

---

## Rule for the agent

Never mark an engine change `done` without running `python test_xlsx_writer.py`. Never mark any
live-Revit item `done` yourself — that is the project owner's confirmation. Work one roadmap phase
at a time; do not jump to P4+ (rebar / BBS / rate analysis) before P1–P3 are stable in Revit.
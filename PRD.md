# Revit-Extension — Product Requirements Document v0.1

**Document:** `PRD.md`
**Project status:** Product definition / working single-tool extension
**Target platform:** Autodesk Revit, structural / RCC (Reinforced Cement Concrete) workspace
**Minimum Revit version:** 2025 and above
**Runtime:** pyRevit 6.10.0 and above — CP3123 (CPython 3.12.3) and IP27 (IronPython 2.7) engines
**Technology:** Python (pyRevit API), WPF `ui.xaml` for the dialog, dependency-free Open XML XLSX writer
**Primary development method:** AI-assisted development with human product direction and testing

---

## 1. Product Vision

The extension removes the repetitive step of manually selecting structural parameters and quantities
in Revit and assembling a BOQ by hand.

The product provides a single dialog — the **RCC BOQ Parameter Manager** — that lets an engineer:

1. pick which parameters matter for each structural category,
2. filter what is exported,
3. send a real `.xlsx` workbook to a costing sheet or client,
4. with metric quantities and costing already computed.

This is **not a general Revit scheduling tool**. It is deliberately narrow: the four structural
categories used in RCC takeoff — **Beam, Column, Slab, Foundation** — and a repeatable export of
their parameter data and quantities.

---

# 2. Product Goals

### Primary goals

1. Present the real parameters that exist on the current document's elements — a discovery-based
   list, never a hard-coded fixture.
2. Let the user build a per-category **export selection** (which parameter columns to include).
3. Keep Beam / Column / Slab / Foundation structurally separate tabs so a selection stays scoped.
4. Classify Slab and Foundation elements logically by their real names/codes even when a floor is
   actually stored as a Structural Foundation (and vice-versa).
5. Export a dependency-free, real `.xlsx` workbook — no Excel installed, no `openpyxl`.
6. Append numeric metric quantity takeoff columns (`Qty: Volume (m3)`, `Qty: Area (m2)`,
   `Qty: Length (m)`) from Revit's internal units.
7. Produce a **BOQ Summary** sheet with live cross-sheet `SUM()` formulas and a `GRAND TOTAL` row.
8. Produce a **Costing** sheet (Quantity × Rate = Amount, with a `TOTAL`).
9. Restrict an export to only the elements currently selected in the Revit view when requested.
10. Persist parameter selection, filters, and last output folder between runs.
11. Stay verifiable outside Revit: the pure-Python engine must remain dependency-free and
    covered by `test_xlsx_writer.py`.

### Non-goals for the current scope

This release will not try to:

- Replace native Revit schedules/schemas.
- Support every Revit category.
- Implement a costing database or live rate tables (rates come from a single chosen parameter).
- Build an installer or bundle a custom UI shell beyond the WPF dialog.
- Add multi-language or team-shared live settings.

---

## 3. Target Users

### Primary user

A structural engineer or quantity surveyor preparing an **RCC BOQ** from a Revit 2025+ project:
someone who must repeatedly pull beams, columns, slabs, and foundations out of a model with the
same columns, in a way that lands in Excel with quantities and a costing summary.

### Secondary user

A Revit automation developer who maintains or extends the extension and relies on the
dependency-free engine's tests.

---

## 4. Platform Scope

### Supported

- Autodesk Revit **2025 and above**.
- pyRevit **6.10.0 and above**, both the CP3123 (CPython 3.12.3) and IP27 (IronPython 2.7) engines.

The script targets the Revit `DB` API via pyRevit and the RevitPythonShell-style
`from pyrevit import revit, forms`, with safe fallbacks where a newer Revit API (e.g.
`ParameterUtils.IsBuiltInParameter`, `UnitTypeId`) may or may not be present.

### Explicitly out of scope

- Revit versions older than 2025 (untested; safe-path code exists but is not the target).
- Non-RCC disciplines.

---

---

## 5. Functional Requirements

### 5.1 Categories and discovery

For each of **Beam, Column, Slab, Foundation**, the dialog discovers the actual parameters on the
elements of that category in the current document and lists them alphabetically as
"Available Parameters". Selection is per-category; there is no cross-category column inheritance.

| Tab | Revit BuiltInCategory |
| --- | --- |
| Beam | `OST_StructuralFraming` |
| Column | `OST_StructuralColumns` |
| Slab | `OST_Floors` (plus logical slabs stored as foundations) |
| Foundation | `OST_StructuralFoundation` |

### 5.2 Search and selection

Each tab has a search box that live-filters the available parameters by name, and
Add → / Remove buttons to move parameters between **Available** and **Selected / Export**.

### 5.3 Logical classification (Slab / Foundation)

Elements are classified by name/code, independent of how they are stored:

- **Slab subtypes:** Slab, Fold Slab, Grade Slab, Other.
- **Foundation subtypes:** Footing, Combined Footing, PCC, Raft, Combined Raft, Other.

Codes such as `S1`, `CF`, `GS` are matched as tokens; a floor stored as a Structural Foundation
with a slab-like name is still classified as a slab element (unless it is PCC).

### 5.4 Export scope

When **Export selected only** is on, element rows are restricted to the integer ElementIds selected
in the active Revit view. Otherwise all elements of the applied filters export.

### 5.5 Quantity takeoff

When **Include quantities** is on (default), each element row appends after the chosen parameters:

```
Qty: Volume (m3)
Qty: Area (m2)
Qty: Length (m)
```

Values are rounded to 4 decimals in metric, converted from Revit internal units via
`UnitUtils.ConvertFromInternalUnits` (UnitTypeId, then DisplayUnitType), with deterministic
foot-based constants as the final fallback.

### 5.6 Excel workbook (dependency-free)

The XLSX is written from Open XML parts directly (`zipfile` + string-built XML), so it needs no
Excel, `openpyxl`, or other package inside the pyRevit environment.

The workbook contains:

- one element sheet per **populated** category (empty categories are skipped — no empty tabs),
- a **BOQ Summary** sheet with live `SUM()` formulas across the element sheets and a
  `GRAND TOTAL` row,
- a **Costing** sheet (Category, Element ID, Quantity, Rate, Amount = Quantity × Rate) with a
  `TOTAL` row.

Quantity columns are real numbers with the `#,##0.00` number format; an auto-filter ranges over the
data (excluding the totals row); the workbook requests `fullCalcOnLoad` so Excel recalculates the
live formulas on open.

### 5.7 Costing rule

The Costing sheet finds each category's rate column by recognizing a rate/price parameter name and
uses the first available quantity metric. Amount is a formula `C<row>*D<row>`; the sheet ends with a
`SUM` `TOTAL` row. No hard-coded rate values exist anywhere.

### 5.8 Settings persistence

The last parameter selection (per category), export flags, filters, and last output folder are saved
as JSON under the user profile (`.rcc_boq_settings.json`) and restored on the next run. Failures to
read/write the file are silent and never block the tool.

### 5.9 Feedback and safety

- A status bar shows element counts per category and export errors.
- A success alert reports the output path, selected parameters, data rows, sheets, and quantity
  column totals.
- Startup and export failures surface a clear Revit message rather than an unhandled exception.

---

# 6. Data-Driven Principles

- **No hard-coded parameter lists** for the element sheets — everything comes from Revit's real
  objects.
- **No fabricated APIs** — every Revit call is real `Autodesk.Revit.DB`; conditional paths simply
  reflect that different Revit versions expose different members.
- **No external runtime dependencies** — the XLSX engine is pure-Python so it is testable and
  portable.
- **Empty classification** is explicit — `Other` is a real bucket, never a silent drop.

---

# 7. Non-Functional Requirements

- **Testability:** the pure-Python engine must be extractable and runnable by
  `test_xlsx_writer.py` in any Python 3.x.
- **Compatibility:** safe fallbacks must keep the tool working on both CP3123 and IP27 engines on
  Revit 2025+, and degrade gracefully rather than crash on API members absent on a given engine.
- **Performance:** element/parameter discovery uses `FilteredElementCollector` once per category; no
  per-row Revit API calls beyond parameter reads.
- **Determinism:** quantity conversion constants are fixed so the same model yields the same numbers
  regardless of `UnitUtils` availability.

---

# 8. Product Success Criteria

The project is successful when an engineer can:

> Open a Revit 2025+ RCC model, run BOQ, select the four categories' parameters, and receive a real
> `.xlsx` workbook — with quantities and a costing summary — in a few clicks, with no Excel and no
> external packages required.

The first release milestone is not "a fancier dialog". It is:

> **"I exported my beams, columns, slabs, and foundations into a correct workbook that my cost side
> can use directly."**

---

# 9. Recommended Repository Documentation

```text
README.md
PRD.md
PROJECT_STRUCTURE.md
AI_DEVELOPMENT_GUIDE.md
CLAUDE.md
CHANGELOG.md
done-list.md
todo-list.md
test_xlsx_writer.py
```

The PRD defines **what** we are building. `PROJECT_STRUCTURE.md` defines **how** the code is
organised. The AI development guide defines **how coding agents must change the project**.

---

# 10. Remaining Architectural Questions

- **Which Revit-2025 APIs are guaranteed on both engines?** Some members (e.g.
  `ParameterUtils.IsBuiltInParameter`, `UnitTypeId`) are guarded; the exact floor of what
  pyRevit 6.10.0 exposes on each engine is a verification item.
- **Where should categories live going forward?** The four hard-coded tabs are fine for RCC; widening
  to more categories would need a data-driven category registry.

---

# 11. Final Technical Direction

```text
Revit 2025+ (host)
       │
       ▼
pyRevit 6.10.0+ (CP3123 / IP27)
       │
       ▼
BOQ.pushbutton (script.py + ui.xaml)
       │
       ├── Category collection (Beam/Column/Slab/Foundation)
       ├── Logical classification (Slab / Foundation subtypes)
       ├── Parameter discovery + selection
       ├── Metric quantity takeoff
       └── Dependency-free Open XML XLSX writer
           ├── Element sheets
           ├── BOQ Summary (live SUM, GRAND TOTAL)
           └── Costing (Qty × Rate = Amount)
```

The design is **dependency-free, data-driven, discoverable, and testable**. The first priority is
keeping the exported workbook a complete, correct BOQ report.
# Revit-Extension — Product Requirements Document v0.1

**Document:** `PRD.md`
**Project status:** Product definition / working BOQ tool, actively extended
**Current version:** `v1.35.0`
**Target platform:** Autodesk Revit, structural / RCC (Reinforced Cement Concrete) workspace
**Minimum Revit version:** 2025 and above
**Runtime:** pyRevit 6.10.0 and above — the BOQ pushbutton runs on **IP27 (IronPython 2.7.12)**
today; **CP3123 (CPython 3.12.3) remains the target engine**
> **Engine caveat (T-03):** `script.py` carries no `#! python3` first line, so pyRevit loads it on
> its default engine, IP27. The modules under `Nudge.extension/lib/` are CPython-clean — 19 of the
> 21 import and write a workbook on CP3123 (measured 2026-09-24), the other two
> (`revision_engine.py`, `header_colour.py`) only on Python 3.12.10 so far — so only `script.py`'s pyRevit/WPF
> layer keeps the tool on IronPython. pyRevit 6.10.0+ *documents* both engines, but `pyrevit.forms`
> is still IronPython-only upstream (the CPython `_cpy.py` backend is a stub that raises
> `PyRevitCPythonNotSupported`), on the currently-installed build (`6.5.3`) and upstream
> master (`6.5.5`) alike. See `todo-list.md` T-03.
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

This is **not a general Revit scheduling tool**. It is deliberately narrow: the six structural
categories used in RCC takeoff — **Beam, Column, Structure Wall, Slab, Foundation, Rebar** — and a repeatable export of
their parameter data and quantities.

**Project direction.** The agreed, incremental direction is to evolve from
**Parameter Selection + Basic Quantity Export** into a **Professional Structural BOQ System**:
concrete, reinforcement, formwork, grouping, rate analysis, validation and a complete Excel BOQ —
built one roadmap phase at a time **on top of the existing working project**, never as a rewrite.

**Structural scope only.** Beam, Column, Structure Wall, Slab, Foundation, Rebar + RCC concrete, reinforcement, formwork,
binding wire, cover blocks, structural labour, materials, wastage, rate analysis, costing and BOQ
export. Architecture, Doors, Windows, Plumbing, Electrical, HVAC and other MEP modules are **out of
scope** for now.

---

# 2. Product Goals

### Primary goals

1. Present the real parameters that exist on the current document's elements — a discovery-based
   list, never a hard-coded fixture.
2. Let the user build a per-category **export selection** (which parameter columns to include).
3. Keep Beam / Column / Structure Wall / Slab / Foundation / Rebar separate tabs so a selection stays scoped.
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
- Implement a costing database beyond the P11 rate analysis and P12 rate database sheets (the
  Costing sheet itself still takes its rate from a single chosen parameter).
- Build an installer or bundle a custom UI shell beyond the WPF dialog.
- Add multi-language or team-shared live settings.

---

## 3. Target Users

### Primary user

A structural engineer or quantity surveyor preparing an **RCC BOQ** from a Revit 2025+ project:
someone who must repeatedly pull beams, columns, structural walls, slabs, and foundations out of a model with the
same columns, in a way that lands in Excel with quantities and a costing summary.

### Secondary user

A Revit automation developer who maintains or extends the extension and relies on the
dependency-free engine's tests.

---

## 4. Platform Scope

### Supported

- Autodesk Revit **2025 and above**.
- pyRevit **6.10.0 and above** with CP3123 (CPython 3.12.3) as the product target. The tool runs on
  IP27 today because `script.py` has no `#! python3` first line and the inspected pyRevit forms
  backend is IP27-only; the `lib/` engines are already CPython-clean.

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

For each of **Beam, Column, Structure Wall, Slab, Foundation, Rebar**, the dialog discovers the actual parameters on the
elements of that category in the current document and lists them alphabetically as
"Available Parameters". Selection is per-category; there is no cross-category column inheritance.

| Tab | Revit BuiltInCategory |
| --- | --- |
| Beam | `OST_StructuralFraming` |
| Column | `OST_StructuralColumns` |
| Structure Wall | `OST_Walls`, restricted to elements with Revit's Structural flag enabled |
| Slab | `OST_Floors` (plus logical slabs stored as foundations) |
| Foundation | `OST_StructuralFoundation` plus logical foundations stored as floors |
| Rebar | `OST_Rebar` |

The dialog carries ten tabs in total: the six category tabs above, in the order Beam, Column,
Structure Wall, Rebar, Slab, Foundation, followed by four configuration tabs — Assembly Profile,
Site Items, Rate Analysis and Rate Database — which hold user-entered data rather than discovered
parameters.

### 5.2 Search and selection

Each tab has a search box that live-filters the available parameters by name, and
Add → / Remove buttons to move parameters between **Available** and **Selected / Export**.

### 5.3 Logical classification (Slab / Foundation)

Floors and Structural Foundations are kept as separate raw collections, then passed through one
central classifier. Physical category never overrides an explicit construction identity:

- **Slab subtypes:** Slab (including Chajja, Lobby floors and Ramp floors), Fold Slab, Grade Slab,
  Other.
- **Foundation subtypes:** Footing, Combined Footing, PCC, Raft, Combined Raft, Other.

Foundation identity has priority over generic slab wording. Codes use exact boundaries:
`F1`/`CF2` are foundations and `S1`/`GS` are slabs, while bare `F`, `SF`, `FLOOR` and `FOLD`
are not footing codes. Parameter discovery, subtype filters and Excel export consume the same
logical collections.

Before export, the classifier reconciles raw counts against logical Slab/Foundation counts,
checks that their ElementId intersection is empty, reports duplicates/unclassified rows, and
retains unknown identities as `Other` instead of silently dropping them.

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

Structure Wall adds Length, Height and Thickness dimensions. Its initial formwork contract is gross
two-face contact area `2 × Length × Height`; opening and intersection deductions remain future
rule-engine work.

### 5.6 Excel workbook (dependency-free)

The XLSX is written from Open XML parts directly (`zipfile` + string-built XML), so it needs no
Excel, `openpyxl`, or other package inside the pyRevit environment.

The workbook can contain, in order:

- one element sheet per **populated** category (empty categories are skipped — no empty tabs),
- **Rebar Summary** and **Rebar BBS**,
- **Structural Assembly**,
- **Rate Analysis** and **Rate Database**,
- a **BOQ Summary** sheet with live `SUM()` formulas across the element sheets and a
  `GRAND TOTAL` row, plus **BOQ by Level** and **BOQ by Grade**,
- **Concrete Summary** and **Formwork Summary**,
- **Detailed BOQ**, priced from the rate database,
- **BOQ Revision** (`Previous Qty`, `Current Qty`, `Difference`, `% Difference`, `Status`),
  written from the second export of a model onwards,
- **Site Items**,
- **Unmapped Elements**,
- a **Costing** sheet (Category, Element ID, Quantity, Rate, Amount = Quantity × Rate) with a
  `TOTAL` row.

A sheet is written only when it has data. The Site format omits **BOQ Summary**, **BOQ by Level**,
**BOQ by Grade** and **Costing**; the Classic format omits the site title bands.

Quantity columns are real numbers with the `#,##0.00` number format; an auto-filter ranges over the
data (excluding the totals row); the workbook requests `fullCalcOnLoad` so Excel recalculates the
live formulas on open.

### 5.7 Costing rule

The Costing sheet finds each category's rate column by recognizing a rate/price parameter name and
uses the first available quantity metric. Amount is a formula `C<row>*D<row>`; the sheet ends with a
`SUM` `TOTAL` row. No hard-coded rate values exist anywhere.

### 5.8 Settings persistence

The last parameter selection (per category), export flags, filters, and last output folder are saved
as JSON under the user profile (`.rcc_boq_settings.json`) and restored on the next run. The write is
atomic and keeps a `.bak` copy of the previous file. Failures to read/write the file are silent and
never block the tool.

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
- **Compatibility:** keep syntax and guarded fallbacks IP27-safe, because the tool still runs on
  IP27, while CP3123 remains the target engine; keep the `lib/` engines CPython-clean; degrade
  gracefully on unavailable API members and do not claim unverified parity.
- **Performance:** element/parameter discovery uses `FilteredElementCollector` once per category; no
  per-row Revit API calls beyond parameter reads.
- **Determinism:** quantity conversion constants are fixed so the same model yields the same numbers
  regardless of `UnitUtils` availability.

---

# 8. Product Success Criteria

The project is successful when an engineer can:

> Open a Revit 2025+ RCC model, run BOQ, select the six categories' parameters, and receive a real
> `.xlsx` workbook — with quantities and a costing summary — in a few clicks, with no Excel and no
> external packages required.

The first release milestone is not "a fancier dialog". It is:

> **"I exported my beams, columns, structural walls, slabs, and foundations into a correct workbook that my cost side
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
- **Where should categories live going forward?** The six hard-coded category tabs are workable for RCC;
  further expansion should first introduce a data-driven category registry.

---

# 11. Final Technical Direction

```text
Revit 2025+ (host)
       │
       ▼
pyRevit 6.10.0+ (runs on IP27 today; CP3123 target)
       │
       ▼
BOQ.pushbutton (script.py + ui.xaml)
       │
       ├── Category collection (Beam/Column/Structure Wall/Slab/Foundation/Rebar)
       ├── Logical classification (Slab / Foundation subtypes)
       ├── Parameter discovery + selection
       ├── Metric quantity takeoff
       └── Nudge.extension/lib/ engines
           └── Dependency-free Open XML XLSX writer
               ├── Element sheets (one per populated category)
               ├── Rebar Summary, Rebar BBS
               ├── Structural Assembly
               ├── Rate Analysis, Rate Database
               ├── BOQ Summary (live SUM, GRAND TOTAL), BOQ by Level, BOQ by Grade
               ├── Concrete Summary, Formwork Summary
               ├── Detailed BOQ
               ├── BOQ Revision (Previous/Current/Difference/%)
               ├── Site Items
               ├── Unmapped Elements
               └── Costing (Qty × Rate = Amount)
```

The design is **dependency-free, data-driven, discoverable, and testable**. The first priority is
keeping the exported workbook a complete, correct BOQ report.

---

# 12. Development Roadmap (evolving into a Professional Structural BOQ System)

The project evolves incrementally from **Parameter Selection + Basic Quantity Export** into a
**Professional Structural BOQ System**. Every phase builds on the existing working project and
is **not a rewrite**. A phase starts only after the previous one is stable on a real Revit 2025
project.

- **Phase 1 — Structural Quantity Engine.** Extend the existing quantity engine per category. Beam:
  Volume, Area, Length, Count, dimensions where available. Column: Volume, Area, Height/Length,
  Count, dimensions. Slab: Volume, Area, Thickness where available, Count. Foundation: Volume, Area,
  Dimensions, Count. Distinguish **Parameter Quantity** vs **Calculated Quantity** where necessary.
- **Phase 2 — Structural BOQ Grouping.** Level-wise (Foundation, Ground, First, Second, Roof…),
  material-wise (Concrete, Reinforcement, Steel…), concrete grade-wise (M20, M25, M30, M35, M40…)
  read from the model where possible. Also consider wastage, selected-element BOQ and view-based BOQ.
- **Phase 3 — Formwork Engine.** Dedicated, configurable per-category rules: Beam (bottom, sides,
  ends where applicable), Column (four sides), Slab (bottom, edge where applicable), Foundation
  (sides where applicable). Rules must be configurable — no one universal formula.
- **Phase 4 — Rebar Quantity Engine (done, closed at `v1.19.0`).** A dedicated `OST_Rebar` tab/sheet extracts
  Bar Mark, Diameter, Shape, Quantity, Bar Length, Total Length, Host Element/Category/ID and Level.
  All automatic fields are exposed in Rebar's Available Parameters list. The pure engine computes
  Unit Weight with `d²/162 kg/m` and Total Weight. The `v1.19.0` read-only native Revit audit closed
  the phase.
- **Phase 5 — Rebar Summary / BBS (done at `v1.19.1`).** Diameter-wise summary includes Diameter,
  Number of Bars, Total Length, Unit Weight and Total Weight in kg/ton. The BBS includes Bar Mark,
  Shape, Diameter, A-H, Bend Diameter, start/end hooks, Quantity, Cutting Length, Total Length,
  Unit/Total Weight, Host and Level. Revit Bar Length is authoritative for cutting length because
  its shape definition owns repeated segments, bend radii and hooks; no universal deduction is
  guessed. Variable sets keep Cutting Length blank, remain separate by Rebar Element ID, preserve
  varying A-H markers and expose a clearly labelled per-set average; Rebar Level falls back to its
  host. The owner's `v1.12.4` workbook live-verifies the per-set BBS behavior and reconciled totals.
  The `v1.11.2` patch also persists selected export parameters and their order across dialog close,
  pyRevit reload and Revit restart.
  The `v1.11.3` patch reads Beam section width/depth from built-in or controlled family/type
  parameters and rejects rotated bounding-box dimensions for shuttering calculations.
  The `v1.12.0` performance pass indexes each instance once and each shared Revit type once for
  Selected parameter, grade and identity resolution during export.
  The `v1.12.1` measured follow-up skips Site-only Grade resolution, caches Level names and avoids
  unnecessary framing bounding-box reads.
  The `v1.12.2` completion report exposes compact Element ID/details for routing findings without
  dumping healthy classification rows. `v1.12.3` uses built-in system-family Type/Family fallbacks
  and routes the owner's live-verified `LOBBY` and `ramp` Floor types to `Slab / Slab`.
  `v1.12.4` live-verifies that distinct varying Rebar sets no longer collapse into one misleading
  BBS average.
- **Local integration foundation (`v1.14.1` MCP complete).** An out-of-process localhost ASP.NET Core
  Gateway communicates with a Revit 2025 .NET add-in over a current-user-only Named Pipe. Revit reads
  are marshalled through `ExternalEvent`; only token-protected status, document, selection, element
  and Rebar snapshots are allowed. The interface excludes model writes, document paths and arbitrary
  execution and bounds returned collections. The earlier pyRevit Routes prototype remains disabled
  after host instability. Live Revit 2025 `v1.13.1` testing verifies startup, authentication,
  document, selection, element and varying-Rebar reads plus 404/422 boundaries. `v1.13.3` mirrors
  the proven BOQ rule that maps a Rebar dimension with `HasValue=false` to `Varies`; multi-instance
  ownership and clean shutdown are also live-verified. `v1.14.0` adds a dependency-free STDIO MCP
  adapter over the same five read-only calls; `v1.14.1` hardens BOM handling and initialization
  state. A fresh Codex session discovered and invoked the registered status tool, and live Revit QA
  verified document, empty/non-empty selection, element and varying-Rebar calls.
- **Phase 6 — Structural BOQ Assembly (done).** Configurable assemblies e.g. RCC Beam → Concrete,
  Reinforcement, Formwork, Binding Wire, Cover Blocks, Labour (similarly for columns, slabs,
  foundations), with support for future custom components.
- **Phase 7 — Site / Non-Model Structural Items (done).** Items not explicitly modeled (binding wire,
  cover blocks, consumables, site items, temporary works) with Item Code, Description, Quantity,
  Unit, Rate, Remarks, coexisting with model-derived quantities.
- **Phase 8 — Structural Rule Engine (open).** Configurable rules (`IF Category = Structural Column THEN
  Concrete = Volume`, `THEN Formwork = Column Formwork Rule`, `IF Rebar Exists THEN Rebar Quantity =
  Rebar Weight`). Modular and structural-only; prevents `script.py` becoming a large hard-coded
  condition pile. Still the open phase — `script.py` is 6,577 lines.
- **Phase 9 — Validation Engine (done).** Before export validate missing parameters/materials/concrete
  grade, zero volume/area/quantity, missing rebar/mapping, invalid/unclassified elements, duplicate
  marks. Compact report (errors/warnings count + short lines) — no huge raw debug in the main dialog.
- **Phase 10 — Unmapped Element Report (done).** Identify elements that cannot be processed (Beam B12 →
  missing material, Column C08 → missing concrete grade, Foundation F22 → missing BOQ mapping) so
  the user can fix the model.

- **Phase 11 — Structural Rate Analysis (done, `v1.26.x`).** Only after quantities are stable.
  Material, Labour, Machinery, Wastage, Overheads. `Quantity × Rate = Amount`.
- **Phase 12 — Structural Rate Database (built in `v1.30.0`–`v1.32.0`; waiting on the owner's real
  rates).** Configurable Item Code, Description, Unit, Rate, Currency, Location, Vendor, Effective
  Date, with lookup by city/state/country and effective date. Rates are never hard-coded.
- **Phase 13 — Professional Excel BOQ (done, `v1.27.0`–`v1.29.0`).** The XLSX engine now writes the
  Detailed BOQ plus Concrete Summary and Formwork Summary alongside the element, Rebar, assembly,
  grouping and costing sheets in both the Classic and Site formats, using live formulas where
  appropriate.
- **Phase 14 — BOQ Revision (engine and both sheets done, `v1.35.0`; no dialog tab).** Each
  export files a snapshot of its own numbers under `%LOCALAPPDATA%\RCC_BOQ\revisions\`, and
  from the second export onwards a `BOQ Revision` sheet gives Previous vs Current Quantity,
  Difference, Percentage Difference and a status per item. Choosing *which* issue to compare
  against, rather than always the latest, is the remaining slice.
- **Phase 15 — Model Change Detection (not started).** Detect added/modified/deleted structural
  elements and BOQ impact. High complexity; only after the core BOQ system is mature.
- **Phase 16 — Structural Dashboard (not started).** Concrete, Rebar (Ton), Formwork, Elements,
  Estimated Cost, Warnings.

Only **Structural** scope is in the current roadmap; Architecture / Doors / Windows / Plumbing /
Electrical / HVAC / MEP are not.

---

# 13. Feature Rating System

Every candidate feature is evaluated on four axes with ⭐ ratings (⭐⭐⭐⭐⭐ = very high, ⭐ = very low):

- **Priority** — how urgently it should be implemented
- **Benefit** — practical project/tender/BOQ value
- **Complexity** — technical difficulty
- **Implementation Ease** — how safely it integrates without destabilizing the project

## Priority ranking

| # | Feature | Priority | Benefit | Complexity | Ease |
|---:|---|---|---|---|---|
| 1 | Existing quantity engine enhancement | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| 2 | Beam/Column/Structure Wall/Slab/Foundation/Rebar BOQ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| 3 | Parameter mapping enhancement | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| 4 | Existing Excel export enhancement | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| 5 | Level-wise BOQ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| 6 | Material-wise BOQ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| 7 | Concrete grade-wise BOQ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| 8 | Wastage | ⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐⭐ |
| 9 | Formwork Engine | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| 10 | Rebar Quantity Engine | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| 11 | Rebar Diameter Summary | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ |
| 12 | Validation Engine | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| 13 | Unmapped Element Report | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ |
| 14 | Rule Engine | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| 15 | Structural Assembly | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| 16 | Site/Manual Structural Items | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ |
| 17 | Rate Analysis | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| 18 | Rate Database | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ |
| 19 | BBS | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| 20 | Revision System | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ |
| 21 | Model Change Detection | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ |
| 22 | Dashboard | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |

# 14. Architecture Principle — keep `script.py` modular

Do not turn `script.py` into one giant calculation file. The modularization has happened, but the
engines live in `Nudge.extension/lib/` rather than inside the pushbutton folder:

```text
Nudge.extension/
├── Nudge.tab/Generate.panel/BOQ.pushbutton/
│   ├── script.py
│   └── ui.xaml
└── lib/                       (19 modules)
    ├── quantity_engine.py
    ├── rebar_engine.py
    ├── formwork_engine.py
    ├── rule_engine.py
    ├── validation_engine.py
    ├── export_validation.py
    ├── costing_engine.py
    ├── rate_database_engine.py
    ├── revision_engine.py
    ├── header_colour.py
    ├── assembly_engine.py
    ├── site_items_engine.py
    ├── export_engine.py
    ├── settings_engine.py
    ├── parameter_engine.py
    ├── authoring_spec.py
    ├── stack_runner.py
    ├── crash_trail.py
    ├── agent_export_job.py
    ├── rest_api.py
    ├── theme_manager.py
    └── Resources/             (brand resource dictionaries)
```

However, do **not** split files merely for the sake of splitting. Inspect the existing code first
and modularize only when it genuinely improves maintainability without breaking the current
architecture. The pure-Python engine dependency rule in `PROJECT_STRUCTURE.md` still applies.

---

# 15. Error Handling

One invalid Revit element must never crash the whole BOQ. Safely handle missing/invalid parameters,
missing materials, missing volume/area/level/type, invalid/deleted elements and unsupported
categories. Valid elements keep processing while problematic elements are reported separately.

---

# 16. Testing Workflow

For every major change:

1. Explain what will change.
2. Modify the minimum required code.
3. Provide the complete updated file(s).
4. The user tests in Revit 2025.
5. The user reports success or error.
6. Only after a successful test does the next major phase begin.

Never assume code works before it is tested. Engine changes still run `python test_xlsx_writer.py`
first; the harness prints its own check count and currently ends with
`RESULT: all 414 checks passed`.

---

# 17. Regression Protection

After every change verify: WPF startup; Beam/Column/Structure Wall/Slab/Foundation/Rebar tabs; parameter loading,
selection, multi-selection, Add/Remove, Up/Down/Top/Bottom; parameter order preservation; filter
system; saved settings; export selected only; auto-open; include quantities; Excel export; BOQ
Summary; Costing; XLSX formulas; the existing regression test. Do not sacrifice a working feature
for a new one without explicitly explaining why.

---

# 18. Source-of-Truth Rule

The attached existing working project is more important than this document. If this document and the
actual source code disagree, **trust the actual source code**. Do not invent functionality, do not
remove working functionality, do not rewrite from scratch, and do not jump straight to advanced
features. Build the Structural BOQ system incrementally on the existing project.

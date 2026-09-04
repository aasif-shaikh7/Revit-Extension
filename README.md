# Revit-Extension

**Document:** `README.md`
**Status:** Project overview, vision, and status — for the pyRevit RCC BOQ extension

---

This repository contains a **pyRevit extension** that runs inside Autodesk Revit and
automates the generation of **RCC (Reinforced Cement Concrete) BOQ** workbooks.

Right now it ships two buttons — **BOQ** in the **Generate** panel of the **Nudge** tab, which
opens the **RCC BOQ Parameter Manager**, and **Brand Showcase** in the **Brand** panel — a live
preview of the toolkit's brand/theme system that doubles as a Light/Dark visual QA tool.

**Target environment:**

- **Revit 2025 and above**
- **pyRevit 6.10.0 and above** on the **CP3123 (CPython 3.12.3)** engine — the single supported
  runtime. The legacy **IP27 (IronPython 2.7)** engine is best-effort/untested (code stays
  2.7-syntax-safe but is not a support target).
> **Engine caveat (T-03, confirmed 2026-09-01):** pyRevit still ships `pyrevit.forms` only
> for IronPython — upstream master `6.5.5` carries the same CPython stub as the installed
> build (`6.5.3`). So today the BOQ dialog **runs on IP27** despite the CP3123-only product
> decision, until a CPython-capable `pyrevit.forms` ships upstream. From `v1.9.3`, the known IP27
> fallback is silent so a healthy run does not force-open pyRevit output; only an unexpected engine
> raises a warning. See `todo-list.md` T-03/T-10.

---

## Project Status

**Status: Working single-tool extension, actively extended**

The extension is functional and installed under the standard pyRevit extension layout
(`*.extension` / `*.tab` / `*.panel` / `*.pushbutton`). The core Excel writer is covered by a
standalone regression harness, and the Revit-facing functionality is being expanded feature by feature.

See:

- [`PRD.md`](PRD.md) — what is being built and why
- [`PROJECT_STRUCTURE.md`](PROJECT_STRUCTURE.md) — where code lives and the rules that keep it testable
- [`docs/reference/`](docs/reference) — reference documentation from a previous project (kept for study, not Revit)

> **Note.** The `docs/reference/` folder holds the older Kestrel (Android) documentation that used to
> live at the repository root. It is preserved for reference and its structure inspired these
> Revit-specific documents. Nothing in `docs/reference/` describes this extension.

---

## Why RCC BOQ

Structural engineers and quantity surveyors repeatedly select the same **parameters** and
**quantities** from structural elements — beams, columns, structural walls, slabs, and foundations — and send them to a
costing sheet or a client workbook.

Doing that by hand in Revit is slow, repetitive and error prone:

- you scroll through dozens of parameters to find the ones that matter
- you re-select them for every new project or element type
- you copy values out one row at a time

The BOQ pushbutton turns the selection and export into one repeatable step and produces a real
`.xlsx` workbook **without requiring Excel or any external Python package**.

---

## The Vision

```text
Revit Project
      │
      ▼
Nudge tab ▶ Generate panel ▶ BOQ pushbutton
      │
      ▼
RCC BOQ Parameter Manager
      │  (choose Beam / Column / Structure Wall / Slab / Foundation / Rebar parameters)
      ▼
Revit element data + metric quantities
      │
      ▼
Dependency-free XLSX (Open XML):
      Element sheets  ▶  BOQ Summary  ▶  Costing
```

The user opens the manager, picks the columns they want per category, optionally limits the export
to the current selection or filters slab/foundation subtypes, and gets a real Excel workbook with
numeric quantities and live SUM formulas — with no `openpyxl`, no Excel automation, and no
dependencies imported into the pyRevit host.

---

## What It Does

**RCC BOQ Parameter Manager** (`BOQ.pushbutton`):

- **One dialog, six structural categories** — Beam, Column, Structure Wall, Slab, Foundation, Rebar.
- **Structural-only wall collection.** The Structure Wall tab reads `OST_Walls` whose Revit
  **Structural** flag is enabled; architectural walls are excluded.
- **P4 Rebar quantity takeoff.** A dedicated Rebar tab/sheet collects `OST_Rebar` and exports Bar
  Mark, Diameter, Shape, Quantity, Bar Length, Total Length, Host ID/category, Level, Unit Weight
  and Total Weight. These automatic fields are also visible in Rebar's Available Parameters list.
  Steel unit weight uses the standard `d²/162 kg/m` rule.
- **Parameter discovery, not hard-coded lists.** The "Available Parameters" box for a category is
  built from the actual parameters found on the real elements in the current document.
- **Add / Remove selection** with a live search box per tab.
- **Central logical classification** for Slab and Foundation. Floors and Structural Foundations
  are both routed by construction identity, not physical category: `S1`, `GS`, Grade/Fold Slab
  and Chajja go to Slab; exact `F<number>` / `CF<number>`, PCC and raft identities go to
  Foundation. A pre-export audit prevents duplicate or missing element IDs and retains unknowns
  under a controlled `Other` subtype.
- **Export scope** — optionally restrict output to exactly the elements selected in the current
  Revit view.
- **Quantity takeoff** (toggleable) — numeric metric volume/area/length columns plus category-aware
  dimensions. Structure Wall exports Length, Height and Thickness and uses gross two-face
  shuttering `2 × Length × Height` (openings/intersections are not deducted yet).
- **Dependency-free XLSX writer** — builds the workbook from Open XML parts directly, so it runs
  inside the pyRevit environment without external packages.
- **BOQ Summary sheet** — live cross-sheet `SUM()` formulas plus a `GRAND TOTAL` row.
- **Costing sheet** — per-element Quantity × Rate with a `TOTAL` amount, driven from a user
  rate/price parameter on each category.
- **Settings persistence** — the last parameter selection, filters, and output folder are stored in
  a JSON settings file under the user profile and restored on the next run.

---

## How to Use It

1. Install the extension so `Nudge.extension` is picked up by pyRevit (see the layout below).
2. Open a Revit 2025+ project; ensure the structural elements for the categories you want exist.
3. In the **Generate** panel click **BOQ**.
4. For each category tab, search and move parameters to **Available → Selected / Export**.
5. Optionally narrow Slab/Foundation by subtype and tick **Export selected only**.
6. Click **Export Excel**, choose the `.xlsx` destination.
7. Optionally tick **Open file after export** / **Include quantities** before exporting.

---

## Installation / Layout

A pyRevit extension is read from a folder named `*.extension` with a `*.tab`, a `*.panel`, and
one or more `*.pushbutton` folders:

```text
Revit-Extension/
│
├── Nudge.extension/
│   ├── Nudge.tab/
│   │   ├── Generate.panel/
│   │   │   └── BOQ.pushbutton/
│   │   │       ├── script.py     <- Revit collection, classification and UI orchestration
│   │   │       ├── ui.xaml        <- WPF window definition
│   │   │       └── icon.png       <- pushbutton icon
│   │   └── Brand.panel/
│   │       └── BrandShowcase.pushbutton/   <- brand/theme live preview + Light/Dark QA
│   └── lib/
│       ├── settings_engine.py    <- persisted selections/options
│       ├── quantity_engine.py    <- metric dimensions
│       ├── formwork_engine.py    <- shuttering rules/formulas
│       ├── rebar_engine.py      <- P4 rebar length/weight calculations
│       ├── costing_engine.py     <- costing tables
│       ├── export_engine.py      <- dependency-free Open XML XLSX writer
│       ├── theme_manager.py      <- Revit Light/Dark theme detection + dictionary merging
│       └── Resources/            <- brand resource dictionaries (colors/typography/controls)
│
├── docs/
│   └── reference/                 <- older Kestrel docs, kept for study
│
├── README.md
├── PRD.md
├── PROJECT_STRUCTURE.md
├── AI_DEVELOPMENT_GUIDE.md
├── CLAUDE.md
├── CHANGELOG.md
├── done-list.md
├── todo-list.md
└── test_xlsx_writer.py           <- standalone regression harness (pure Python)
```

Register the root folder as an **extension search path** in pyRevit settings, then reload. Further
detail is in [`PROJECT_STRUCTURE.md`](PROJECT_STRUCTURE.md).

---

## Testing

A feature is not *done* because `script.py` is syntactically valid.

The XLSX writer is the only part that runs outside Revit, so it is tested at two levels:

```text
Standalone regression (test_xlsx_writer.py)
    ↓
In-Revit / on-project verification (manual, by the project owner)
```

`test_xlsx_writer.py` extracts pure-Python functions from the real `lib/` engines plus bounded
Revit-facing helpers from `script.py`, builds sample workbooks, and XML-validates every part (sheet order, SUM
formulas, auto-filter range, styles, GRAND TOTAL). It runs in any Python 3.x:

```bash
python test_xlsx_writer.py
```

The pure-Python engines (unit conversion, sheets, styles and formulas) stay dependency-free and
unit-testable. The Revit-bound classifier is separately extracted into the harness with fake
elements for routing matrices. Forms/UI and real Revit API access still require a live Revit
session. See [`CHANGELOG.md`](CHANGELOG.md).

---

## Development Roadmap

The project is evolving from **Parameter Selection + Basic Quantity Export** into a
**Professional Structural BOQ System** — building on the existing working pushbutton, one phase at a
time, never as a rewrite.

```text
P1  Quantity Engine (extend existing)
P2  BOQ Grouping (level / material / concrete grade)
P3  Formwork Engine
P3.5 Structure Wall category integration
P4  Rebar Quantity Engine
P5  Rebar Summary / BBS
P6  Structural BOQ Assembly
P7  Site / Manual Structural Items
P8  Structural Rule Engine
P9  Validation Engine
P10 Unmapped Element Report
P11 Rate Analysis
P12 Rate Database
P13 Professional Excel BOQ
P14 BOQ Revision
P15 Model Change Detection
P16 Structural Dashboard
```

Only **structural** scope is in the roadmap (Beam/Column/Structure Wall/Slab/Foundation/Rebar + concrete, reinforcement,
formwork, rates, costing). Each phase starts only after the previous one is stable on a live Revit
2025 project. Phases are rated (priority / benefit / complexity / ease) in [`PRD.md`](PRD.md) §13,
and the current status is tracked in [`todo-list.md`](todo-list.md).

---

## Versioning

The extension follows **semantic versioning** (`MAJOR.MINOR.PATCH`) as recommended by GitHub
([https://semver.org/](https://semver.org/)). The current version is declared in `script.py` on the pushbutton — in the
pyRevit docstring (`__version__`) and the runtime `SCRIPT_VERSION` constant — and is shown in the
Excel export dialog.

Every release is tagged with git (`vMAJOR.MINOR.PATCH`); the pre-release development history is
tagged `v0.x`. Full bump rules are in `PROJECT_STRUCTURE.md` §Versioning.

---

## Reporting Bugs

Include as much as can be reproduced:

- Revit version (2025+)
- pyRevit version and engine (CP3123 vs IP27)
- structural category and the element/type affected
- the exact steps: category, parameters, export options
- the generated file (or a portion) and any error message/traceback

---

## License

This extension is provided for use on the structural/RCC workspace it was built for. The project
owner remains responsible for production review and release readiness.

---

## A Final Note

Revit automation lives inside a host application that changes between releases, and pyRevit offers a
choice of Python engines (CPython + IronPython). The honest goal of this repository is to keep the
**pure-Python core** (unit conversion, classification, the XLSX writer) free of host dependencies so
that the necessarily-live parts (selection, filters, dialog) stay small and concrete wherever
possible.

If the extension eventually saves the engineer a workbook every day, that is the measure of success.

---

## Project Status (short)

**Working BOQ pushbutton, evolving into a Professional Structural BOQ System.** P1 quantity,
P2 grouping and P3 formwork are complete; the owner confirmed `v1.8.10` Slab/Foundation routing in
Revit 2025 on 2026-09-03. Structure Wall `v1.9.3` is live-confirmed. Version `v1.10.1` continues P4
with a dedicated Rebar tab, quantity/host fields and `d²/162` weight calculation; the harness passes
and live Revit 2025 verification is pending.

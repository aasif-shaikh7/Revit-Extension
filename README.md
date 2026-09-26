# Revit-Extension

**Document:** `README.md`
**Status:** Project overview, vision, and status — for the pyRevit RCC BOQ extension

---

This repository contains a **pyRevit extension** that runs inside Autodesk Revit and
automates the generation of **RCC (Reinforced Cement Concrete) BOQ** workbooks.

The pyRevit extension ships **BOQ** and **Brand Showcase**. The separately installed native
`RccBoq.RestBridge` add-in also provides an **Agent Bridge** button under Revit Add-Ins for viewing
bridge state and granting or revoking short controlled-write sessions.

**Target environment:**

- **Revit 2025 and above**
- **pyRevit 6.10.0 and above**. The BOQ pushbutton currently runs on **IP27 (IronPython
  2.7.12)**: `script.py` carries no `#! python3` first line, so pyRevit loads it on its default
  engine. **CP3123 (CPython 3.12.3)** stays the target engine.
> **Engine note:** the engine modules under `Nudge.extension/lib/` are CPython-clean — 19 of the
> 24 import and write a workbook on CP3123 (measured 2026-09-24), and `revision_engine.py`,
> `header_colour.py`, `model_change_engine.py`, `dashboard_engine.py` and `bbs_steel_engine.py`
> have so far only been measured on Python 3.12.10 in the harness. Only `script.py`'s pyRevit/WPF
> layer keeps the tool on IronPython, because pyRevit still ships `pyrevit.forms` for IronPython
> only — upstream master `6.5.5` carries the same CPython stub as the installed build (`6.5.3`).
> From `v1.9.3`, the known IP27 fallback is silent so a healthy run does not force-open pyRevit
> output; only an unexpected engine raises a warning. See `todo-list.md` T-03/T-10.

---

## Project Status

**Status: Working BOQ tool plus a theme-QA button, actively extended**

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
      │  (11 tabs: Beam / Column / Structure Wall / Rebar / Slab / Foundation /
      │   Assembly Profile / Site Items / Rate Analysis / Rate Database / Revision)
      ▼
Revit element data + metric quantities
      │
      ▼
Dependency-free XLSX (Open XML):
      Summary ▶ Dashboard ▶ Element sheets ▶ Rebar Summary ▶ Rebar BBS ▶ Structural Assembly ▶
      Rate Analysis ▶ Rate Database ▶ BOQ Summary ▶ BOQ by Level ▶ BOQ by Grade ▶
      Concrete Summary ▶ Formwork Summary ▶ Detailed BOQ ▶ BOQ Revision ▶ Model Changes ▶
      Site Items ▶
      Unmapped Elements ▶ Costing
```

The user opens the manager, picks the columns they want per category, optionally limits the export
to the current selection or filters slab/foundation subtypes, and gets a real Excel workbook with
numeric quantities and live SUM formulas — with no `openpyxl`, no Excel automation, and no
dependencies imported into the pyRevit host.

---

## What It Does

**RCC BOQ Parameter Manager** (`BOQ.pushbutton`):

- **One dialog, twelve tabs** — the six structural categories (Beam, Column, Structure Wall, Rebar,
  Slab, Foundation) plus Assembly Profile, Site Items, Rate Analysis, Rate Database, Revision and
  BBS Steel.
- **Structural-only wall collection.** The Structure Wall tab reads `OST_Walls` whose Revit
  **Structural** flag is enabled; architectural walls are excluded.
- **P4 Rebar quantity takeoff.** A dedicated Rebar tab/sheet collects `OST_Rebar` and exports Bar
  Mark, Diameter, Shape, Quantity, Bar Length, Total Length, Host ID/category, Level, Unit Weight
  and Total Weight. These automatic fields are also visible in Rebar's Available Parameters list.
  Steel unit weight uses the standard `d²/162 kg/m` rule.
- **P5 shape-aware BBS.** `Rebar BBS` exports A-H dimensions, Bend Diameter, hooks and Revit's
  authoritative Bar Length as Cutting Length, then aggregates Quantity/Length/Weight for matching
  geometry and hosts. Variable sets remain separate by Rebar Element ID, preserve `Varies` in A-H,
  and expose their own Average Bar Length with an explicit status instead of inventing a cutting
  length. `Rebar Summary` totals bars, length, kilograms and tonnes by diameter.
- **Steel from separate BBS models (`v1.42.0`).** When the reinforcement lives in separate BBS
  models rather than in the structural model, the BBS Steel tab lists them and reads each once:
  opened in the background (detached if workshared), its rebar weighed by the same code and
  `d²/162` rule as the Rebar sheet, closed without saving. The element a model is for comes from
  its file name and can be corrected, never from the rebar's host. The export adds that steel to
  the Detailed BOQ's reinforcement items, the revision snapshot and the Dashboard, and writes a
  `BBS Steel` sheet (per model, per diameter, element totals); a model that changed since it was
  read, or could not be read, is named in the Dashboard's warnings.
- **Beam Cut Length (`v1.43.0`).** The Beam sheet shows Revit's Cut Length (after the joins cut
  the beam back) beside the drawn Length, and the Rebar sheets show each bar's `Beam Cut Length`
  - of its host beam, or, for a beam bar hosted on a column (`v1.45.0`), of the beam it lies in.
- **Rebar sheets from the BBS models (`v1.44.0`-`v1.46.0`).** Reading a BBS model keeps every
  bar's row, with the Rebar tab's chosen parameters. A structural model with no rebar of its own
  then shows those bars in its `Rebar`, `Rebar Summary` and `Rebar BBS` sheets, laid out as a
  BBS model's own export lays them out, plus the BBS model each bar came from. The BOQ still
  counts the steel once, from the BBS totals.
- **Parameter discovery, not hard-coded lists.** The "Available Parameters" box for a category is
  built from the actual parameters found on the real elements in the current document.
- **Add / Remove selection** with a live search box per tab.
- **Central logical classification** for Slab and Foundation. Floors and Structural Foundations
  are both routed by construction identity, not physical category: `S1`, `GS`, Grade/Fold Slab
  and Chajja go to Slab; exact `F<number>` / `CF<number>` / `WF<number>` codes (optionally with one
  variant letter, such as `F2A`), PCC and raft identities go to Foundation. A pre-export audit prevents duplicate or missing element IDs and retains unknowns
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
- **Grouped, assembled and priced sheets** — `BOQ by Level`, `BOQ by Grade`, `Concrete Summary`,
  `Formwork Summary`, `Structural Assembly`, `Site Items`, `Rate Analysis`, `Rate Database`,
  `Detailed BOQ`, `BOQ Revision`, `Model Changes` and `Unmapped Elements` are written when the
  relevant data exists. The Site
  format omits `BOQ Summary`, `BOQ by Level`, `BOQ by Grade` and `Costing`; the Classic format
  omits the site title bands.
- **Rate database** — the Rate Database tab and sheet resolve a rate by city/state/country and
  effective date, and the `Detailed BOQ` is priced from it. No rate is hard-coded.
- **BOQ revision** — each export files the plain numbers behind it as a snapshot, and from the
  second export onwards a `BOQ Revision` sheet gives `Previous Qty`, `Current Qty`,
  `Difference`, `% Difference` and a status per item. An export that measures what the last one
  measured does not become a new revision.
- **Model changes** — a `Model Changes` sheet lists the elements behind that movement: each one
  added, deleted or modified (concrete, shuttering or hosted steel by 0.005 or more, or its grade,
  level or family and type), with what changed in words and a TOTAL per difference column.
- **Dashboard** — right after the Summary cover: concrete, steel (t), shuttering and element
  counts; concrete by grade; the estimated cost from the rate database (always equal to the
  Detailed BOQ's amounts); warnings; and what moved since the previous issue.
- **Owner theme** — the dialog uses a red header band, peach buttons with black text, a lime
  selection colour, a gold tab strip and Consolas; the workbook uses red titles and headers,
  banded rows, lime-tint totals, Indian digit grouping and A4 landscape one page wide.
- **Settings persistence** — the last parameter selection, filters, and output folder are stored in
  a JSON settings file under the user profile and restored on the next run. The save is atomic and
  keeps a `.bak` backup of the previous file.

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

## Local REST + MCP Integration (`v2.5.0`)

The integration uses a Revit 2025 .NET add-in plus an out-of-process ASP.NET Core Gateway at
`http://127.0.0.1:48885/rcc-boq`. Revit API work is marshalled through `ExternalEvent` and a
current-user-only Named Pipe. The closed operation allow-list supports bounded reads, controlled
text-parameter edits and controlled structural-material type assignments; arbitrary Revit calls and
code evaluation remain forbidden.

Close Revit 2025, then build and install the bridge for the current Windows user:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_rest_bridge.ps1
```

The installer publishes the Gateway and STDIO MCP server below
`%LOCALAPPDATA%\RCC_BOQ\RestBridge\v2.5.0` and creates
`%APPDATA%\Autodesk\Revit\Addins\2025\RccBoq.RestBridge.addin`. Restart Revit after installation.

The first extension startup creates a random token at
`%LOCALAPPDATA%\RCC_BOQ\rest_token.txt`. Do not copy or publish this file. The supplied client reads
it automatically and sends an authenticated local `GET` request:

```powershell
python scripts/rcc_boq_rest_client.py status
python scripts/rcc_boq_rest_client.py document
python scripts/rcc_boq_rest_client.py selection
python scripts/rcc_boq_rest_client.py element 3411763
python scripts/rcc_boq_rest_client.py rebar 3411763
python scripts/rcc_boq_rest_client.py materials
python scripts/rcc_boq_rest_client.py last-validation
python scripts/rcc_boq_rest_client.py start-export --format site
python scripts/rcc_boq_rest_client.py start-export --format site --apply
python scripts/rcc_boq_rest_client.py export-status
python scripts/rcc_boq_rest_client.py set-parameter 3411763 --parameter-name Comments --value QA
python scripts/rcc_boq_rest_client.py set-parameter 3411763 --parameter-name Comments --value "Rollback probe" --expected-current-value "" --force-rollback --apply
$materialId = 123456 # replace with an ID returned by the materials command
python scripts/rcc_boq_rest_client.py set-structural-material 3070326 --material-id $materialId --expected-current-material-id 0
python scripts/rcc_boq_rest_client.py set-structural-material 3070326 --material-id $materialId --expected-current-material-id 0 --apply
```

Available REST endpoints are `GET /status`, `/document`, `/selection`,
`/elements/<element_id>`, `/rebar/<element_id>`, `/materials`, `/boq/last-validation` and
`/boq/export-status`, plus `POST /boq/export`, `/elements/<element_id>/parameter` and
`/element-types/<element_id>/structural-material`, below the `/rcc-boq` root. Writes and Agent
exports default to dry-run. Actual apply also requires a write session enabled from Revit's Agent
Bridge button; the bridge never saves the document. The material catalog is limited to 1,000
active-document materials. Structural-material assignment accepts only an explicit catalog material ID and
an ElementType in Structural Foundations, Floors, Structural Framing, Structural Columns or Walls;
`expected_current_material_id=0` means the current material must be blank. Selection output is
limited to 100 elements and parameter output to 250 values per element. Document paths and API
tokens are never returned.

For family types, assignment uses Revit's built-in Structural Material parameter. For system types
where that parameter is derived/read-only, the bridge accepts only one unambiguous compound-structure
layer whose function is `Structure`, assigns its material, and designates that layer as the
structural-material source. It never adds, removes or reorders compound-structure layers.

Register the installed controlled MCP server with Codex, then restart Codex:

```powershell
codex mcp remove rcc-boq-v2
codex mcp add rcc-boq-v2 -- "$env:LOCALAPPDATA\RCC_BOQ\RestBridge\v2.5.0\Mcp\RccBoq.RestMcp.exe"
codex mcp list
```

The MCP tools are `rcc_boq_status`, `rcc_boq_document`, `rcc_boq_selection`,
`rcc_boq_element`, `rcc_boq_rebar`, `rcc_boq_materials`, `rcc_boq_last_export_validation`,
`rcc_boq_export_status`, `rcc_boq_start_export`, `rcc_boq_set_parameter` and
`rcc_boq_set_structural_material`. The MCP process reads the same per-user token itself; the token is
not stored in agent configuration or emitted in tool results. Both write tools are explicitly
annotated non-read-only/destructive and default to dry-run.
Every successful BOQ export is reread before publication and compared cell-for-cell with its
canonical Revit-derived rows. The completion dialog shows `Workbook validation: PASS`; the Agent
Bridge returns only the fixed, bounded latest report and never accepts an arbitrary workbook path.
An applied Agent export posts the same BOQ command in hidden one-shot mode and writes a unique file
below `%LOCALAPPDATA%\RCC_BOQ\AgentExports`. It does not overwrite a requested path, open Excel or
save the Revit document. Poll `rcc_boq_export_status` until `completed`, then read
`rcc_boq_last_export_validation`.

For isolated native QA while another Revit process keeps the Primary bridge, save the Primary
manifest, install the Secondary build, start only the test Revit, then immediately copy the saved
manifest back:

```powershell
$manifest = "$env:APPDATA\Autodesk\Revit\Addins\2025\RccBoq.RestBridge.addin"
Copy-Item $manifest "$env:TEMP\RccBoq.RestBridge.addin.primary"
powershell -ExecutionPolicy Bypass -File scripts\install_rest_bridge.ps1 -BridgeChannel Secondary
# Start the dedicated test Revit process here and wait until port 48886 answers.
Copy-Item "$env:TEMP\RccBoq.RestBridge.addin.primary" $manifest -Force
python scripts\rcc_boq_rest_client.py status --base-url http://127.0.0.1:48886
```

Do not restore by re-running the installer for Primary while the Primary Revit is running: its
add-in and Gateway files are locked, the copy fails, and the shared manifest stays on Secondary.

The Secondary channel is fixed to loopback port `48886` with its own current-user mutex and Named
Pipe. It shares no Revit API context with the Primary channel on `48885`.

Host-free verification:

```powershell
dotnet build RccBoq.RestBridge\src\RccBoq.RestGateway\RccBoq.RestGateway.csproj -c Release
dotnet build RccBoq.RestBridge\src\RccBoq.RestRevit\RccBoq.RestRevit.csproj -c Release
dotnet run --project RccBoq.RestBridge\src\RccBoq.RestCore.Tests\RccBoq.RestCore.Tests.csproj -c Release
dotnet run --project RccBoq.RestBridge\src\RccBoq.RestMcp.Tests\RccBoq.RestMcp.Tests.csproj -c Release
python test_rest_api.py
python test_xlsx_writer.py
```

---

## Installation / Layout

A pyRevit extension is read from a folder named `*.extension` with a `*.tab`, a `*.panel`, and
one or more `*.pushbutton` folders:

```text
Revit-Extension/
│
├── Nudge.extension/
│   ├── startup.disabled.py                <- disabled legacy pyRevit Routes prototype
│   ├── Nudge.tab/
│   │   ├── Generate.panel/
│   │   │   └── BOQ.pushbutton/
│   │   │       ├── script.py     <- Revit collection, classification and UI orchestration
│   │   │       ├── ui.xaml        <- WPF window definition
│   │   │       └── icon.png       <- pushbutton icon
│   │   └── Brand.panel/
│   │       └── BrandShowcase.pushbutton/   <- brand/theme live preview + Light/Dark QA
│   └── lib/                       <- 24 dependency-free engine modules + 6 dialog-tab modules
│       ├── agent_export_job.py   <- headless Agent export job state
│       ├── assembly_engine.py    <- P6 structural assembly components
│       ├── authoring_spec.py     <- authoring/spec definitions
│       ├── costing_engine.py     <- costing tables
│       ├── crash_trail.py        <- export crash breadcrumb trail
│       ├── export_engine.py      <- dependency-free Open XML XLSX writer
│       ├── export_validation.py  <- canonical cell-for-cell workbook validation
│       ├── formwork_engine.py    <- shuttering rules/formulas
│       ├── parameter_engine.py   <- parameter discovery/normalisation
│       ├── quantity_engine.py    <- metric dimensions
│       ├── rate_database_engine.py <- P12 rate lookup by location and date
│       ├── rebar_engine.py       <- P4 rebar length/weight calculations
│       ├── revision_engine.py    <- P14 snapshots + Previous/Current comparison
│       ├── model_change_engine.py <- P15 element-level Added/Deleted/Modified
│       ├── dashboard_engine.py   <- P16 the whole BOQ on one page
│       ├── bbs_steel_engine.py   <- steel read from separate BBS models, kept per model
│       ├── header_colour.py      <- dialog header colour presets + readable text
│       ├── *_tab.py              <- dialog handlers moved out of script.py: the data tabs
│       │                            (and the BBS Steel tab) and the parameter lists
│       ├── rest_api.py           <- token/authentication + bounded serializers
│       ├── rule_engine.py        <- P8 structural rules
│       ├── settings_engine.py    <- persisted selections/options
│       ├── site_items_engine.py  <- P7 site / non-model items
│       ├── stack_runner.py       <- runs the writers on a 64 MB-stack thread
│       ├── theme_manager.py      <- Revit Light/Dark theme detection + dictionary merging
│       ├── validation_engine.py  <- P9/P10 validation + unmapped elements
│       └── Resources/            <- brand resource dictionaries (Brand.Colors.Light/Dark,
│                                    Brand.Typography, Brand.Controls)
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
├── scripts/rcc_boq_rest_client.py <- local REST smoke-test/client utility
├── scripts/install_rest_bridge.ps1 <- build/install the Revit add-in, Gateway and MCP server
├── RccBoq.RestBridge/              <- .NET Core, Gateway, MCP and Revit add-in projects
├── test_rest_api.py              <- REST security/serialization regression tests
└── test_xlsx_writer.py           <- standalone XLSX regression harness (pure Python)
```

Register the root folder as an **extension search path** in pyRevit settings, then reload. Further
detail is in [`PROJECT_STRUCTURE.md`](PROJECT_STRUCTURE.md).

---

## Testing

A feature is not *done* because `script.py` is syntactically valid.

The `lib/` engines are the parts that run outside Revit, so the project is tested at two levels:

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

The harness prints its own check count; the current run ends with
`RESULT: all 471 checks passed`.

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
P1  Quantity Engine (extend existing)            done
P2  BOQ Grouping (level / material / concrete grade)  done
P3  Formwork Engine                              done
P3.5 Structure Wall category integration         done
P4  Rebar Quantity Engine                        done
P5  Rebar Summary / BBS                          done
P6  Structural BOQ Assembly                      done
P7  Site / Manual Structural Items               done
P8  Structural Rule Engine                       open (script.py is 5,508 lines)
P9  Validation Engine                            done
P10 Unmapped Element Report                      done
P11 Rate Analysis                                done
P12 Rate Database                                done; Gujarat R&B SOR 2024-25 rates entered
P13 Professional Excel BOQ                       done
P14 BOQ Revision                                 done
P15 Model Change Detection                       done
P16 Structural Dashboard                         done
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

The intent is to tag every release with git (`vMAJOR.MINOR.PATCH`), with the pre-release development
history tagged `v0.x`. Tagging lapsed after `v1.7.7` and resumed at `v1.34.3`; the releases in
between carry no tag and are reachable only by their commits, with `CHANGELOG.md` as their record. Full bump rules are in `PROJECT_STRUCTURE.md` §Versioning.

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

**Working BOQ pushbutton, evolving into a Professional Structural BOQ System.** The current version
is `v1.47.0`. Every phase is done except the open-ended P8 split (`script.py` after
`v1.38.0`–`v1.39.0` moved the dialog handlers into `lib/`). P12's rate database holds real
Gujarat R&B SOR 2024-25 rates since 2026-09-25. `v1.42.0` brings the steel of separate BBS models
into the BOQ (BBS Steel tab and sheet).

Since `v1.23.2` the following shipped. `v1.26.x` added P11 rate analysis (engine, sheet and tab).
`v1.27.0`–`v1.29.0` added the P13 `Detailed BOQ` plus `Concrete Summary` and `Formwork Summary` in
both the Classic and Site formats. `v1.30.0`–`v1.32.0` added the P12 rate database: lookup by
city/state/country and effective date, its own tab and sheet, and a `Detailed BOQ` priced from it.
`v1.32.1` fixed a Revit stack-overflow crash on BBS exports by running the writers on a 64 MB-stack
thread (`lib/stack_runner.py`). `v1.33.0`–`v1.34.1` applied the owner's theme — dialog: red header
band `#C8102E`, peach button `#F4A582` with black text, lime selection `#C6F432`, gold tab strip
`#FFE699`, Consolas; workbook: red title and header, `#DAE9F8` band rows, lime-tint totals, Indian
digit grouping, A4 landscape one page wide. `v1.34.2` made the settings save atomic with a `.bak`
backup and gave the harness its own printed check count; `v1.34.3` put the model's element
count on each category tab; `v1.35.0` added the P14 `BOQ Revision` sheet and the snapshot behind
it.

Version `v1.23.2`
routes owner-confirmed footing codes with a variant letter (`F2A`) and wall-footing codes (`WF1`)
to Foundation / Footing. Version `v1.23.1`
fixes the Classic `BOQ Summary` GRAND TOTAL, which previously omitted the last category row
(Foundation). Version `v1.23.0`
adds a bounded material catalog and a guarded, dry-run-first Structural Material type assignment
through Agent Bridge `v2.5.0`; isolated live assignment, rollback, export and save/reopen persistence
checks pass. Version `v1.22.2` uses only the
owner-confirmed `GRADE OF CONCRETE` and `Grade` Text parameters as authoritative grade sources;
material/name inference is deliberately excluded. Version `v1.22.0`
adds missing structural material to the Unmapped Element Report. Version `v1.21.1`
lists workbook sheets in their real order in the export popup. Version `v1.21.0`
adds the P10 Unmapped Element Report: an `Unmapped Elements` sheet in Classic and Site workbooks
listing exported elements with missing concrete grade, missing/zero volume or uncertain
Slab/Foundation routing, backed by the new pure `lib/validation_engine.py`. Version `v1.20.0`
widens the Agent Bridge write-consent window to 1 hour and derives the consent dialog text from the
single duration constant, installed as Agent Bridge `v2.4.0`. Version `v1.19.1`
preserves Selected/export column order under IP27 with ordered row dictionaries. Version `v1.19.0`
added isolated multi-Revit rollback QA through Agent Bridge `v2.3.0`. Version `v1.18.2` hardened live
headless export against optional .NET null values and Windows ZIP-handle locks.
Version `v1.18.1` fixed live pyRevit command discovery in Agent Bridge `v2.2.1`; `v1.18.0` added
consent-gated fixed-folder headless export and job polling. Version
`v1.17.0` added canonical cell-for-cell validation and a bounded last-validation tool. The earlier
`v1.16.0` foundation provides bounded reads plus a dry-run-first,
consent-gated parameter write. Live Revit QA verifies v2 startup beside v1, bounded reads, dry-run,
the consent-off write guard, a consent-enabled write/read-back/restore cycle, stale-value rejection,
manual revocation, automatic expiry and Codex registration. Native Site and Classic headless exports
both pass canonical cell-for-cell validation. The isolated Secondary channel also passes native
forced-failure transaction rollback QA with fresh parameter read-back and no document save.
The earlier `v1.14.1` release established the dependency-free STDIO
MCP adapter over the token-protected localhost .NET Gateway and Revit add-in. Revit 2025 live
testing of `v1.13.1` verified startup, authentication, document, empty selection, element and
varying-Rebar reads plus controlled 404/422 responses; it also exposed a missing varying-dimension
marker. `v1.13.3` mirrors the BOQ rule by mapping a dimension with `HasValue=false` to `Varies`.
The owner live-verified the corrected `Varies` payload and non-empty selection in `v1.13.3`;
the single-owner mutex and clean owner/Gateway shutdown are also live-verified. In `v1.14.1`, raw
STDIO and fresh-session registered Codex discovery pass, along with live status, document,
empty/non-empty selection, element and varying-Rebar calls. The previous pyRevit Routes prototype stays
disabled. P1 quantity,
P2 grouping and P3 formwork are complete; the owner confirmed `v1.8.10` Slab/Foundation routing in
Revit 2025 on 2026-09-03. Structure Wall `v1.9.3` is live-confirmed. Version `v1.12.4` keeps varying
Rebar sets separate and traceable in BBS (owner workbook live-confirmed); it retains the robust
system-Floor type detection and
verified LOBBY/ramp routing from `v1.12.3`, plus the compact
Element ID details from `v1.12.2` and the live-verified `v1.12.1` performance pass,
which builds on the
`v1.12.0` indexed export path by skipping Classic-only Grade work in Site exports, caching Level
lookups and avoiding unnecessary framing bounding boxes. It
retains the `v1.11.3` fix for angled
Beam shuttering by using actual family/type section width instead of bounding-box width, and retains
the `v1.11.2` behavior that keeps every
Available -> Selected parameter choice and its order across dialog close, pyRevit reload and Revit
restart. It retains the `v1.11.1` P5
shape-aware Rebar BBS and diameter summary on top of the P4 quantity/weight engine; the harness
passes. A `v1.19.0` read-only native Revit audit closed P4 quantity QA and verified P5 numeric/BBS
parity for fixed and variable samples plus all workbook totals. A changed non-empty selection/order
was restored after a fresh test-Revit restart. Its first Classic export exposed the IP27 ordering
defect fixed in `v1.19.1`; the corrected native export placed the three selections consecutively
and passed 118,101/118,101 canonical cells with zero mismatches. P5 is complete.

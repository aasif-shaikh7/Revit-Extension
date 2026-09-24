# Revit-Extension — Project Structure

**Document:** `PROJECT_STRUCTURE.md`
**Status:** Canonical — folder organization and dependency rules

## Purpose

This document is the canonical structure for the pyRevit RCC BOQ extension repository. It exists so
that:

- human contributors know where code and docs belong,
- AI coding agents have one structural source of truth,
- the pure-Python engine stays isolated from the Revit-only UI so it can be tested,
- documentation remains easy to discover,
- the host-specific and host-free parts are never accidentally mixed.

---

# 1. Top-Level Structure

```text
Revit-Extension/
│
├── Nudge.extension/            <- installable pyRevit extension root
├── docs/
│   └── reference/              <- older Kestrel docs kept for study
│
├── README.md
├── PRD.md
├── PROJECT_STRUCTURE.md
├── AI_DEVELOPMENT_GUIDE.md
├── CLAUDE.md
├── CHANGELOG.md
├── done-list.md
├── todo-list.md
├── scripts/
│   ├── install_rest_bridge.ps1  <- build/publish/install the Revit bridge
│   ├── rcc_boq_rest_client.py   <- dependency-free local Gateway client
│   └── revit_authoring.py       <- Revit-bound model builder, run via `pyrevit run`
├── RccBoq.RestBridge/
│   ├── RccBoq.RestBridge.addin.template
│   └── src/
│       ├── RccBoq.RestCore/       <- token, contracts and pipe protocol
│       ├── RccBoq.RestCore.Tests/ <- dependency-free Core test executable
│       ├── RccBoq.RestGateway/    <- localhost ASP.NET Core process
│       ├── RccBoq.RestMcp/        <- dependency-free STDIO MCP adapter
│       ├── RccBoq.RestMcp.Tests/  <- dependency-free MCP protocol tests
│       └── RccBoq.RestRevit/      <- Revit 2025 ExternalEvent/pipe add-in
├── test_rest_api.py             <- REST auth/serialization harness (pure Python)
├── test_xlsx_writer.py         <- standalone regression harness (pure Python)
└── __pycache__/                <- local bytecode cache (git-ignored, not tracked)
```

---

# 2. Root Documentation

The root is intentionally kept for files every contributor or coding agent should see first.

| File | Purpose |
| --- | --- |
| `README.md` | Project overview, status, usage, installation |
| `PRD.md` | Product requirements and scope |
| `PROJECT_STRUCTURE.md` | Canonical repository/folder organization |
| `AI_DEVELOPMENT_GUIDE.md` | Rules for AI-assisted implementation |
| `CLAUDE.md` | Condensed operating brief for AI coding agents |
| `CHANGELOG.md` | Records only what has actually been established |
| `done-list.md` | Finished work and what "finished" means |
| `todo-list.md` | The open queue |
| `test_xlsx_writer.py` | Standalone regression harness for the pure-Python XLSX engine |

---

# 3. `Nudge.extension/` — the pyRevit Extension

A pyRevit extension is a folder named `*.extension` containing `*.tab` folders, each with `*.panel`
folders, each with one or more `*.pushbutton` folders. This determines where the button appears in
Revit.

```text
Nudge.extension/
│
├── startup.disabled.py       <- disabled legacy pyRevit Routes prototype
├── Nudge.tab/
│   ├── Generate.panel/
│   │   └── BOQ.pushbutton/
│   │       ├── script.py    <- Revit-bound tool (dialog, discovery, wiring);
│   │       │                   pure engines import from ../../lib/
│   │       ├── ui.xaml      <- WPF dialog definition
│   │       └── icon.png     <- button icon
│   └── Brand.panel/
│       └── BrandShowcase.pushbutton/
│           ├── script.py    <- brand/theme live preview + Light/Dark QA
│           ├── ui.xaml      <- showcase dialog definition
│           ├── bundle.yaml  <- button title/tooltip
│           └── icon.png     <- button icon
│
└── lib/
    ├── theme_manager.py     <- Revit Light/Dark detection + resource merging
    ├── settings_engine.py   <- JSON settings persistence (pure Python)
    ├── quantity_engine.py   <- unit conversion + dimension helpers (pure Python)
    ├── formwork_engine.py   <- P3 shuttering rules + formula builder (pure Python)
    ├── rebar_engine.py      <- P4 rebar length + steel-weight calculations (pure Python)
    ├── rest_api.py          <- legacy prototype serializers retained for regression coverage
    ├── costing_engine.py    <- per-element rate x quantity costing sheet (pure Python)
    ├── export_engine.py     <- dependency-free Open XML XLSX writer (pure Python)
    ├── export_validation.py <- canonical XLSX cell validation + bounded report (pure Python)
    ├── validation_engine.py <- P9/P10 model-quality checks + unmapped element report (pure Python)
    ├── rule_engine.py       <- P8 host-free RCC classification/audit + grade rules (pure Python)
    ├── parameter_engine.py  <- P8 host-free parameter readers + ParameterItem (pure Python)
    ├── site_items_engine.py <- P7 non-model line items: rules, pricing, table (pure Python)
    ├── assembly_engine.py   <- P6 concrete/rebar/formwork assembly table (pure Python)
    ├── rate_database_engine.py <- P12 rates by code, place and date + BOQ pricing (pure Python)
    ├── stack_runner.py      <- runs the workbook writers on a 64 MB-stack thread (pure Python)
    ├── crash_trail.py       <- one flushed line per step, so a hard crash names its step
    ├── authoring_spec.py    <- declarative model specs + expected quantities (pure Python)
    ├── agent_export_job.py  <- fixed-path headless export job contract (pure Python)
    └── Resources/
        ├── Brand.Colors.Light.xaml
        ├── Brand.Colors.Dark.xaml
        ├── Brand.Typography.xaml
        └── Brand.Controls.xaml
```

- **`Nudge.tab`** → the extension's top-level Revit tab named **Nudge**.
- **`Generate.panel`** → a panel named **Generate** on that tab.
- **`BOQ.pushbutton`** → the **BOQ** button in that panel.
- **`Brand.panel`** → the **Brand Showcase** button — live preview of the brand
  resources; Light/Dark visual QA.
- **`lib/`** → shared, pushbutton-independent code and WPF resource
  dictionaries. It also hosts the **19 pure-Python modules** listed in the
  tree above (`settings_engine`, `quantity_engine`, `formwork_engine`,
  `rebar_engine`, `assembly_engine`, `costing_engine`, `rate_database_engine`,
  `export_engine`, `export_validation`, `validation_engine`, `rule_engine`,
  `parameter_engine`, `site_items_engine`, `stack_runner`, `crash_trail`,
  `authoring_spec`, `agent_export_job`, `rest_api`, and `theme_manager` on the
  UI side) that the BOQ
  pushbutton imports by plain module name — pyRevit puts the extension
  `lib/` folder on `sys.path` (the mechanism `theme_manager` already
  relied on). The engines must stay dependency-free: stdlib only, no
  Revit symbols, no WPF. The UI-side assets (`theme_manager.py` —
  host-independent except for the guarded `UIThemeManager` call site —
  and the XAML dictionaries) must never import the engine modules, and
  the engine modules must never import UI/Revit code.

Two pyRevit pushbuttons exist today; nesting stays intentionally flat. The installed native bridge
adds a separate Agent Bridge consent/status button under Revit Add-Ins.

The pyRevit Routes prototype is deliberately disabled because live host testing was unstable. The
supported integration lives in `RccBoq.RestBridge`: a localhost-only out-of-process Gateway talks to
a Revit 2025 add-in over a current-user-only Named Pipe. The add-in marshals a fixed operation
allow-list through `ExternalEvent`. Reads are always available; controlled writes require explicit,
short-lived consent and execute in named Revit transactions with rollback. It must never expose
evaluation, arbitrary method names, document save/close, document paths or token values.
`RccBoq.RestMcp` calls this Gateway rather than duplicating Revit work.

---

# 4. Inside `BOQ.pushbutton/`

## `script.py`

The single Python file pyRevit executes when BOQ is clicked. It contains, in order:

1. **Imports** and the `ParameterItem` display shim.
2. **Global state** — per-category selected parameters, export-scope flag, active selection ids,
   quantity flag.
3. **Selection helpers** — safe collection of the current Revit selection across multiple pyRevit
   API shapes.
4. **Settings persistence adapter** — uses `lib/settings_engine.py`; JSON lives under the user
   profile (`.rcc_boq_settings.json`).
5. **Safe value readers** — `safe_text`, `safe_storage_type`, `safe_is_built_in`,
   `safe_definition_info`, `read_parameter_value`, resolution-with-scope helpers.
6. **Quantity takeoff adapter** — Revit-bound reads and `build_element_data`; pure calculations
   live in `lib/quantity_engine.py` and `lib/formwork_engine.py`.
7. **Export adapter** — output path selection and dispatch to the dependency-free Open XML writer
   in `lib/export_engine.py`; costing formulas live in `lib/costing_engine.py`.
8. **Document + category definitions** — `CATEGORY_INFO` mapping the six category tabs to Revit
   `BuiltInCategory` values.
9. **Collection / classification** — Structure Wall filters `OST_Walls` by the Revit Structural
   flag; raw Floor/Foundation collections remain separate; `classify_rcc_element` reads one element
   and hands its identity text to `classify_identity_text` in `lib/rule_engine.py`, which owns the
   Slab/Foundation decision. `build_logical_rcc_collections` (also in `rule_engine.py`, with the
   reader injected) turns those results into exclusive collections, subtype filters, parameter pools
   and a pre-export audit.
10. **XAML wiring + main entry** — loads `ui.xaml`, wires search/filter/Add-Remove/export events,
    runs `window.ShowDialog()` inside a guarded `try/except`.

### Dependency rule

- The **XLSX engine must stay pure Python** — only standard-library dependencies. It must remain extractable by
  `test_xlsx_writer.py` and runnable in any Python 3.x with **no** Revit symbols.
- Everything that touches Revit/postscript is confined to the rest of the file.

## `ui.xaml`

The WPF window definition for the RCC BOQ Parameter Manager: header, per-category `TabControl`,
search boxes, Available/Selected `ListBox`es, Add/Remove buttons, subtype filter dropdowns, a status
bar, and OK / Export Excel / Close buttons with the export and quantity options.

## `icon.png`

The pushbutton icon; do not replace with a disconnected binary asset unless the change is intentional.

---

# 5. `docs/`

## `docs/reference/`

The previous **Kestrel** (Android) documentation was moved here intact so the current Revit docs
could take the root. Treat it as historical reference only — it documents the Kestrel project, not
this extension, and must not drive decisions here.

---

# 6. Test placement

`test_rest_api.py` and `test_xlsx_writer.py` live at the repository root and import nothing from
Revit. The REST harness validates the Python client contract and bounded serialization. The .NET
Core test executable validates Bearer-token handling and pipe framing. The XLSX harness runs
with a plain `python test_xlsx_writer.py`, which prints its own count (`RESULT: all N checks passed`); it resolves each function from `lib/` first and falls back to `script.py`, extracting the source of the XLSX engine
functions from the real `script.py` and validates the generated workbook by unzipping it.

---

# 7. Rules

- **Do not** put Revit-only logic inside the pure-Python engine.
- **Do not** add a new single huge script without splitting testable pure logic out.
- **Do not** import third-party packages (e.g. `openpyxl`) into the engine — dependency-free is a
  design constraint.
- **Empty tabs don't export** — skip wasted blank worksheets.
- **Keep documentation discoverable** — new docs belong at the root or under `docs/` only.
---

# 8. Versioning

The extension is versioned with **semantic versioning** (`MAJOR.MINOR.PATCH`), following the
GitHub-recommended practice from <https://semver.org/>.

## Single source of truth

The version lives in two places, **both inside `BOQ.pushbutton/script.py`** and both must be bumped
together:

- the `__version__` attribute in the module docstring (read by pyRevit for the button tooltip and
  extension manager), and
- the `SCRIPT_VERSION` constant used by the running code (shown in the Excel export dialog).

## Revit / pyRevit gating

The docstring declares `__min_revit_ver__ = '2025'` (Revit **2025 and above**).

**The engine in practice is IP27 (IronPython 2.7.12).** `script.py` carries no `#! python3` first
line, so pyRevit selects its default engine, and the default is IronPython — confirmed on
2026-09-22 and 2026-09-24 from the crash trail, whose first line prints the live engine. CP3123
(CPython 3.12.3) stays the stated target, and the `lib/` engines are already CPython-clean: all 19
import and write a workbook on CP3123 (measured 2026-09-24). Only `script.py`'s pyRevit/WPF layer
holds the tool on IP27, so moving the button is a deliberate, separately verified change.

Two IP27 consequences are load-bearing for the code as it stands:

- IronPython does not enforce `sys.recursionlimit`, so deep recursion is a hard process crash
  (`0xc00000fd`) rather than a `RecursionError`. The workbook writers therefore run on a
  large-stack thread (`lib/stack_runner.py`, `v1.32.1`).
- The engine is reused between button presses, so module state and `+=` subscriptions survive a
  run.

The engine guard remains, but known CP3123/IP27 runs are silent from `v1.9.3`; only an unexpected
engine raises a warning.

## Bump rules (semver)

Given `MAJOR.MINOR.PATCH`:

- **MAJOR** — an incompatible change: output format, supported Revit behavior, category API, or a
  behaviour a user depends on.
- **MINOR** — backward-compatible new functionality (new category, new export option, new sheet).
- **PATCH** — backward-compatible fix or refactor with no behaviour change.

Pre-`1.0.0` (`0.x.y`) means "not yet stable": MINOR is a breaking change, PATCH is new/backward
compatible. From `1.0.0` onward the normal rules apply.

## How versions are recorded

- Every release commit is tagged `vMAJOR.MINOR.PATCH`. **There is a gap:** tagging lapsed
  after `v1.7.7` and resumed at `v1.34.3`. The releases between them (`v1.7.8`-`v1.34.2`) are
  recorded in `CHANGELOG.md` but carry no tag, so use the changelog to find those commits.
- Development commits that predate the first semantic release are tagged `v0.x.y` so history is
  visible (`v0.1.0` … `v0.3.1`).

## Definition of done for a version bump

1. Bump `__version__` and `SCRIPT_VERSION` to the same number.
2. Add a `[CHANGELOG.md](CHANGELOG.md)` entry describing the change.
3. Update `done-list.md` / `todo-list.md` accordingly.
4. Run `python test_xlsx_writer.py` when the engine changed.
5. Tag the release commit (`git tag v1.0.0`).

---

# 9. Roadmap → Architecture (how phases land here)

The Development Roadmap in `PRD.md` §12 drives how code is added. Two structural rules apply to
every phase:

- **Extend, don't duplicate.** Every phase extends an existing engine (quantity, parameter,
  settings, XLSX) rather than adding a parallel one. See the roadmap's explicit "do not duplicate"
  notes.
- **Keep `script.py` modular, but don't split for its own sake.** `PRD.md` §14 shows the target
  layout (`quantity_engine.py`, `rebar_engine.py`, `formwork_engine.py`, `rule_engine.py`,
  `validation_engine.py`, `costing_engine.py`, `export_engine.py`, `settings_engine.py`). A module
  is created only when a phase genuinely needs it and it improves maintainability. The first five
  engines were extracted to `Nudge.extension/lib/` in `v1.8.6` (pure-Python code only; Revit-bound
  code stays in `script.py`); `rebar_engine.py` landed with P4 in `v1.10.0`. Future engines (`rule_engine.py`,
  `validation_engine.py`) follow the same pattern when their phase lands.

## Where each phase's code will go (planned)

| Phase | Planned landing point |
|---|---|
| P1 Quantity Engine | `lib/quantity_engine.py` (**exists since v1.8.6**; Revit-bound reads stay in `script.py`) |
| P2 Grouping | grouping/summary section of `script.py` (or a module when justified) |
| P3 Formwork Engine | `lib/formwork_engine.py` (**exists since v1.8.6**) |
| P4 Rebar Engine | `lib/rebar_engine.py` (**exists since v1.10.0**; Revit reads stay in `script.py`) |
| P5 Rebar Summary / BBS | `rebar_engine.py` |
| P6 Assembly | `lib/assembly_engine.py` + settings-driven configuration + export (**exists since v1.15.0**) |
| P7 Site items | `lib/site_items_engine.py` (**exists since v1.25.0**: rules, pricing and table; settings/dialog/export still to come) |
| P8 Rule Engine | `lib/rule_engine.py` + `lib/parameter_engine.py` (**since v1.24.0/v1.24.1/v1.25.7**: host-free classification rules, the routing core and its audit reporting, grade and parameter-reader rules; Revit-bound readers stay in `script.py`) |
| P9 Validation Engine | `lib/validation_engine.py` (**since v1.21.0** as the P10 foundation; **v1.25.8** adds issue severity and the compact pre-export report) |
| P10 Unmapped report | reuse validation engine (**first slice v1.21.0**: `build_unmapped_element_report`) |
| P11 Rate Analysis | `lib/costing_engine.py` (**exists since v1.8.6**) |
| P12 Rate Database | `lib/rate_database_engine.py` (**since v1.30.0**; entries live in settings) |
| P13 Professional Excel BOQ | `lib/export_engine.py` (**exists since v1.8.6**) |
| P14 Revision | `lib/export_engine.py` |
| P15 Model change detection | separate diagnostic module |
| P16 Dashboard | new feature/UI module |
| QA fixtures (not a roadmap phase) | `lib/authoring_spec.py` (pure declarations + expected quantities, **exists since v1.24.0**) with the Revit-bound builder in `scripts/revit_authoring.py`, run through `pyrevit run` |

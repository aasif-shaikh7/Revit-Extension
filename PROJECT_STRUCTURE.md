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
    ├── costing_engine.py    <- per-element rate x quantity costing sheet (pure Python)
    ├── export_engine.py     <- dependency-free Open XML XLSX writer (pure Python)
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
  dictionaries. Since the v1.8.6 module split it also hosts the five
  **pure-Python engine modules** (`settings_engine`, `quantity_engine`,
  `formwork_engine`, `costing_engine`, `export_engine`) that the BOQ
  pushbutton imports by plain module name — pyRevit puts the extension
  `lib/` folder on `sys.path` (the mechanism `theme_manager` already
  relied on). The engines must stay dependency-free: stdlib only, no
  Revit symbols, no WPF. The UI-side assets (`theme_manager.py` —
  host-independent except for the guarded `UIThemeManager` call site —
  and the XAML dictionaries) must never import the engine modules, and
  the engine modules must never import UI/Revit code.

Two pushbuttons exist today; nesting stays intentionally flat.

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
8. **Document + category definitions** — `CATEGORY_INFO` mapping the five tabs to Revit
   `BuiltInCategory` values.
9. **Collection / classification** — Structure Wall filters `OST_Walls` by the Revit Structural
   flag; raw Floor/Foundation collections remain separate;
   `classify_rcc_element` creates one structured logical result per element, from which exclusive
   Slab/Foundation collections, subtype filters, parameter pools and a pre-export audit derive.
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

`test_xlsx_writer.py` lives at the repository root so it runs with a plain `python
test_xlsx_writer.py`. It imports nothing from Revit; it extracts the source of the XLSX engine
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

The docstring declares `__min_revit_ver__ = '2025'` (Revit **2025 and above**). CP3123
(CPython 3.12.3) is the product target; IP27 is best-effort. On the currently inspected pyRevit
build the forms backend is available only through IP27. The guard remains, but known CP3123/IP27
runs are silent from `v1.9.3`; only an unexpected engine raises a warning.

## Bump rules (semver)

Given `MAJOR.MINOR.PATCH`:

- **MAJOR** — an incompatible change: output format, supported Revit behavior, category API, or a
  behaviour a user depends on.
- **MINOR** — backward-compatible new functionality (new category, new export option, new sheet).
- **PATCH** — backward-compatible fix or refactor with no behaviour change.

Pre-`1.0.0` (`0.x.y`) means "not yet stable": MINOR is a breaking change, PATCH is new/backward
compatible. From `1.0.0` onward the normal rules apply.

## How versions are recorded

- Every release commit is tagged `vMAJOR.MINOR.PATCH`.
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
  code stays in `script.py`); future engines (`rebar_engine.py`, `rule_engine.py`,
  `validation_engine.py`) follow the same pattern when their phase lands.

## Where each phase's code will go (planned)

| Phase | Planned landing point |
|---|---|
| P1 Quantity Engine | `lib/quantity_engine.py` (**exists since v1.8.6**; Revit-bound reads stay in `script.py`) |
| P2 Grouping | grouping/summary section of `script.py` (or a module when justified) |
| P3 Formwork Engine | `lib/formwork_engine.py` (**exists since v1.8.6**) |
| P4 Rebar Engine | `rebar_engine.py` |
| P5 Rebar Summary / BBS | `rebar_engine.py` |
| P6 Assembly | settings-driven configuration + export |
| P7 Site items | settings + element sheets |
| P8 Rule Engine | `rule_engine.py` |
| P9 Validation Engine | `validation_engine.py` |
| P10 Unmapped report | reuse validation engine |
| P11 Rate Analysis | `lib/costing_engine.py` (**exists since v1.8.6**) |
| P12 Rate Database | settings + data module |
| P13 Professional Excel BOQ | `lib/export_engine.py` (**exists since v1.8.6**) |
| P14 Revision | `lib/export_engine.py` |
| P15 Model change detection | separate diagnostic module |
| P16 Dashboard | new feature/UI module |

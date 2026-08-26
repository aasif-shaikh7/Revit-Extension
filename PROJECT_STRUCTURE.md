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
├── Aasif.extension/            <- installable pyRevit extension root
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
└── _remove_null.py             <- stray local helper (see note below)
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

# 3. `Aasif.extension/` — the pyRevit Extension

A pyRevit extension is a folder named `*.extension` containing `*.tab` folders, each with `*.panel`
folders, each with one or more `*.pushbutton` folders. This determines where the button appears in
Revit.

```text
Aasif.extension/
└── Aasif.tab/
    └── Generate.panel/
        └── BOQ.pushbutton/
            ├── script.py    <- the whole tool
            ├── ui.xaml      <- WPF dialog definition
            └── icon.png     <- button icon
```

- **`Aasif.tab`** → the extension's top-level Revit tab named **Aasif**.
- **`Generate.panel`** → a panel named **Generate** on that tab.
- **`BOQ.pushbutton`** → the **BOQ** button in that panel.

Only one pushbutton exists today; there is intentionally no further nesting.

---

# 4. Inside `BOQ.pushbutton/`

## `script.py`

The single Python file pyRevit executes when BOQ is clicked. It contains, in order:

1. **Imports** and the `ParameterItem` display shim.
2. **Global state** — per-category selected parameters, export-scope flag, active selection ids,
   quantity flag.
3. **Selection helpers** — safe collection of the current Revit selection across multiple pyRevit
   API shapes.
4. **Settings persistence** — JSON under the user profile (`.rcc_boq_settings.json`).
5. **Safe value readers** — `safe_text`, `safe_storage_type`, `safe_is_built_in`,
   `safe_definition_info`, `read_parameter_value`, resolution-with-scope helpers.
6. **Quantity takeoff engine** — metric conversion (`convert_quantity_value`) and
   `get_element_quantities`, plus `get_sample_values` / `build_element_data`.
7. **XLSX engine** — pure-Python, dependency-free Open XML writer: `xlsx_column_name`,
   `xlsx_inline_string`, `try_export_as_number`, `xlsx_cell`, `xlsx_formula_cell`,
   `build_xlsx_sheet_xml`, `build_xlsx_styles_xml`, `build_xlsx_workbook_xml`,
   `build_xlsx_workbook_rels_xml`, `build_xlsx_root_rels_xml`, `build_xlsx_content_types_xml`,
   `build_parameter_metadata_sheet`, `build_missing_values_summary`, `build_costing_sheet`,
   `write_basic_xlsx`, `choose_excel_output_path`.
8. **Document + category definitions** — `CATEGORY_INFO` mapping the four tabs to Revit
   `BuiltInCategory` values.
9. **Collection / classification** — `get_elements`, `get_parameters`, the slab/foundation
   classifier and filters, and the module-level element/parameter caches.
10. **XAML wiring + main entry** — loads `ui.xaml`, wires search/filter/Add-Remove/export events,
    runs `window.ShowDialog()` inside a guarded `try/except`.

### Dependency rule

- The **XLSX engine must stay pure Python** — only `os`, `re`, `json`, `zipfile`, `xml.sax.saxutils`
  and the `System` items needed for the save dialog. It must remain extractable by
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
# Revit-Extension — Done List

**Document:** `done-list.md`
**Status:** Active — the record of work that is finished, and what finished means for each item
**Companion to:** `todo-list.md`, which holds everything not yet finished

---

## How to read this

`todo-list.md` is the queue. This is the receipt.

An item moves here when it is **done** — meaning its code is in place and, for the engine, the
harness passes. A closed entry does **not** claim the live-Revit UI was exercised by an agent; the
project owner confirms in-Revit behavior on a real project and updates the entry when they do.

Each entry says:

1. **What was asked for**, in the words it was asked in where they exist.
2. **What was actually built** — enough that somebody reading it later knows where to look.
3. **How it is known to work** — Tested (harness), Reported, Reasoned or Unverified, the same
   vocabulary `todo-list.md` uses.
4. **What it cost**, where it cost something — a limit or a thing deliberately not done.

**Nothing is written here on the strength of a harness alone proving the whole extension.** The
harness proves the XLSX engine; a live Revit session is the only proof of the dialog.
"Tested (harness)" means exactly measured by `test_xlsx_writer.py`.

---

## Existing working foundation (confirmed in source code — do not rebuild)

The items below are confirmed present in the current `script.py` / `ui.xaml`. Future agents must
**extend, not duplicate** them (see `PRD.md` §18 source-of-truth rule).

- **Parameter engine** — discovery, names/values, storage type, shared/read-only/built-in/global
  parameter handling, definition metadata, and instance vs type **scope resolution**
  (`find_parameter_with_scope`, `safe_*` readers).
- **Parameter selection UI** — Available / Selected lists, multi-select, Add/Remove, and **Up /
  Down / Top / Bottom reordering** (`move_up / move_down / move_top / move_bottom`). Selected order
  is preserved into Excel.
- **Settings persistence** — `.rcc_boq_settings.json` under the user profile stores selected
  parameters, ordering, filters, `export_only`, `auto_open`, `quantities` and last folder, restored
  on the next run.
- **RCC classification / filtering** — Slab (Slab / Fold Slab / Grade Slab / Other) and Foundation
  (Footing / Combined Footing / PCC / Raft / Combined Raft / Other) with raw collections kept so
  filters can change without re-querying.
- **Quantity takeoff** — `Qty: Volume (m3)`, `Qty: Area (m2)`, `Qty: Length (m)`, controlled by
  *Include quantities*, with deterministic metric conversion.
- **Export options** — *Export selected only*, *Open file after export*, *Include quantities*.
- **Dependency-free XLSX/Open XML writer** — element sheets, BOQ Summary (live SUM + GRAND TOTAL),
  Costing (Qty × Rate = Amount + TOTAL), empty-category skipping, fully-empty column pruning,
  auto-filter, styled headers, `fullCalcOnLoad`.
- **Regression test** — `test_xlsx_writer.py` extracts the pure-Python engine and validates the
  workbook (sheet order, formulas, styles, totals, content types).

---

## Closed items

### BOQ-1 — RCC BOQ Parameter Manager dialog — **done** (`09dab85`)

**Asked for.** "Generate a BOQ parameter manager for Beam, Column, Slab, and Foundation with
Available/Selected parameter lists."

**Built.** A pyRevit pushbutton under `Aasif.tab ▶ Generate.panel ▶ BOQ.pushbutton` that opens a WPF
dialog (`ui.xaml`) with four category tabs, a search box per tab, Available→Selected
Add/Remove controls, a status bar, and OK/Export/Close. Parameter lists are discovered from the real
elements in the current document, never hard-coded.

**How it is known.** The XLSX engine path is **Tested (harness)**; the dialog UI itself is
**Unverified** in a live Revit session (requires the project owner).

**Cost.** The dialog is WPF via pyRevit `forms.WPFWindow`; only the pure-Python engine can be tested
off-line, so UI behavior waits for a manual check.

### BOQ-2 — BOQ pushbutton icon — **done** — `f14903b`
**What it was.** A visible button on the Generate panel. **Built.** `icon.png` added to
`BOQ.pushbutton`. **How it is known.** Reasoned (the asset is present and referenced by the layout).
**Cost.** None.

### BOQ-3 — Parameter metadata and Missing-values audit — **done** — `0ab717c`
**Built.** Per-parameter metadata capture plus `build_missing_values_summary` (Total/Missing/Filled/
Fill %) and the Costing sheet (Qty × Rate = Amount TOTAL). Fully-empty parameter columns are pruned
from element sheets but still reported. **How it is known.** **Tested (harness)** — metadata/
missing-values/costing functions are imported into the harness and the produced workbook is
validated. **Cost.** The finalized workbook deliberately omits previously-empty/duplicate tabs; the
harness asserts they are not emitted.

### BOQ-4 — Quantity takeoff and BOQ Summary — **done** — `98fb30b`

**Built.** `convert_quantity_value` (metric, three-tier fallback) and `get_element_quantities`,
appending `Qty: Volume/Area/Length` columns; a `BOQ Summary` sheet of live `SUM()` formulas plus a
`GRAND TOTAL`; `fullCalcOnLoad`. **How it is known.** **Tested (harness)** — asserts SUM formulas,
cross-sheet `Beam!` references, `GRAND TOTAL`, auto-filter range excluding totals, styles. **Cost.**
Quantity conversion constants are deterministic, but true numeric accuracy on real Revit materials is
still **Unverified** until tested on a model.

### BOQ-5 — Element-referencing parameters show name not ElementId — **done** — `v1.0.1`

**Reported (live, Revit 2025).** *"Type, Level, Top Level, Base Level, Reference Level, Cover Type
etc. ke naam aur value ke badle Element ID show ho raha hai."* Owner confirmed the dialog works with
no regression; only these reference-parameter values were wrong in the export.

**Built.** In `safe_parameter_value`, the `StorageType.ElementId` branch now resolves the referenced
element and returns its **name/value** — preferred Revit `AsValueString()`, then
`doc.GetElement(id).Name`, keeping the numeric id only as a final fallback.

**How it is known.** **Tested (harness)** for the engine; live element-name resolution is
**project-owner confirmed** in Revit 2025.

**Cost.** None — a bounded fix to one reader; the same reader also feeds classification so identity
text is now more useful.

---

## Standing conventions

- "Tested" always means **the harness** unless a live-Revit confirmation is explicitly noted.
- No entry is closed on a `script.py` that only *imports cleanly*.
- When the project owner verifies live-Revit behavior, update the "How it is known" line and add a
  dated note here.
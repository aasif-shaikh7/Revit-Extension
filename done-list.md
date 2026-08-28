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

### BOQ-6 — P1 category-aware quantity engine — **done** (`v1.1.0`)

**Asked for.** Roadmap Phase 1: per-category quantities with Count and dimensions, distinguishing
Parameter vs Calculated quantity.

**Built.** `get_element_quantities(element, element_name)` — Calculated Volume/Area/Length
preserved; Parameter `Qty: Height (m)` for Column and `Qty: Thickness (m)` for Slab/Foundation via
`read_metric_parameter` (name lookup across element/Symbol/type); `Qty: Count` = 1 per row with the
TOTAL summing to element count.

**How it is known.** **Tested (harness)** for export; **owner-confirmed live** in Revit 2025 — real
Height/Thickness/Count values correct. Tagged `v1.1.0`.

**Cost.** Height/Thickness rely on parameters literally named "Height"/"Thickness"; projects using
different names get empty (auto-pruned) columns until a mapping is added.

---

### BOQ-7 — P2 level-wise grouping + CP3123-only decision — **done** (`v1.2.0`)

**Asked for.** Level-wise BOQ grouping; single supported engine.

**Built.** Engine-added `Level` column on every element sheet (`get_element_level`: reference/
schedule level params → LevelId fallback); new `BOQ by Level` sheet with live SUMIF formulas per
Level x Category and static Elements counts. Engine standardized on **CP3123 (CPython 3.12.3)**;
IP27 documented best-effort/untested.

**How it is known.** **Tested (harness)** (grouped rows, 9 SUMIF cells, sheet order); **owner-
confirmed live** in Revit 2025 (points 1–4 passed, no regression). Tagged `v1.2.0`.

**Cost.** Grouping is by level only so far — material-wise and concrete-grade-wise grouping (rest of
Phase 2) is still open.

---

### BOQ-8 — v1.4.0 site-format export + P3 formwork (first slice) — **done** (engine side)

**Asked for.** Owner's screenshots of the hand-made site BOQ: title blocks, MM size columns,
VOLUME + SHUTTERING per member, front Summary grouped by level.

**Built.**
- Pure helpers: `meters_to_millimeters`, `build_section_description`
  ("`W X L`" mm strings), `_site_dim_value` (unrounded dims for MM), `resolve_element_dimensions`
  (param-first with bbox fallback; Column pair sorted W<=L), `compute_shuttering_area`
  (Column `2(L+W)H`, Beam `(W+2H)L`, Slab soffit, Foundation sides).
- Quantity engine emits `Qty: Dim L/W/H (m)` + `Qty: Shuttering (m2)` per element row.
- Site writers: `build_site_detail_sheet` (8-column layout A=SNO…H=LEVEL feed, banded header rows
  5–6 with MERGE_V markers, MM integer cells, TOTAL row with SUM(F/G)), `build_site_summary_sheet`
  (LEVEL × category VOL/SHUT pairs + TOTAL pair, live SUMIF against each sheet's H column),
  `build_xlsx_sheet_xml_site` (merged title blocks, mergeCells, frozen panes below band, gridlines
  off, site style indexes 5–13 incl. light-blue fills `FFBDD7EE`/`FFDDEBF7` and full borders),
  `write_site_xlsx` (Summary + populated categories).
- Export dispatch honours `site_format_flag = True` (site writer default); classic path intact via
  `write_basic_xlsx(site_format=False)`. Versions bumped to 1.4.0 everywhere.

**How it is known.** **Tested (harness)** — full suite green: shuttering rules per category, dim
fallbacks, natural level ordering, description format `ITEM B1 | 230 X 6096`, meta contract F/G/H,
SUMIF criteria per level, horizontal TOTAL sums, both workbooks' XML parts valid, mergeCell spans
match the manual layout. `script.py` compiles clean (CPython 3.12).

**Cost / limits.** Slab shuttering uses plan area only (no drop/bulkhead deduction yet); beam
shuttering excludes soffit-overlap overlaps at intersections; dims fall back to axis-aligned
bounding boxes, skewed geometry still needs param-backed dimensions. Live-Revit confirmation
pending; `v1.3.0`/`v1.4.0` tags withheld until then.

---

### BOQ-9 — Brand UI system: shared theme resources + Brand Showcase — code in place (`b1f3c38` + cleanup)

**Asked for.** Make `docs/reference/brand-guidelines.md` real: shared Light/Dark theme resources
for the toolkit's WPF dialogs, plus a live visual QA surface for them.

**Built.**
- `Aasif.extension/lib/Resources/` — `Brand.Colors.Light.xaml` /
  `Brand.Colors.Dark.xaml` (Ember 500/600/100/900 accent brushes + Light/Dark
  surface-alt/border/text neutrals + system success/warning/error/info),
  `Brand.Typography.xaml` (Sora with Segoe UI Variable → Segoe UI fallback;
  header 18 / subheader 14 / label 13 / body 12 / caption 11, SemiBold labels,
  default TextBlock style) and `Brand.Controls.xaml` (Ember primary button with
  hover trigger, outline secondary button, TextBox/CheckBox/ComboBox chrome,
  success/error chips, dialog + ribbon containers).
- `Aasif.extension/lib/theme_manager.py` — `get_current_theme` (guarded
  `UIThemeManager`, then the Windows `AppsUseLightTheme` registry value, then
  Light), `apply_theme` (merges color + typography + controls dictionaries onto
  any `Window` and stashes the theme on `window.Tag`), `toggle_theme`,
  `watch_theme_changes` (re-applies on Revit's own theme flip; silent no-op
  where the event is absent) and `stop_watching` (unsubscribes from the
  window's Closed event so open/close cycles don't leak handlers).
- `Aasif.tab ▶ Brand.panel ▶ BrandShowcase.pushbutton` (`script.py`, `ui.xaml`,
  `bundle.yaml`, icons) — previews typography, buttons, inputs and status chips
  with a theme label and a Toggle Light/Dark button; re-themes itself if
  Revit's theme changes while open. Handlers are wired explicitly in Python
  (XAML `Click=` does not bind on dynamically-loaded XAML in pyRevit).
- Cleanup: the "DEBUG BUILD 3" canary alert, the TEST isolation button and the
  per-toggle modal popup from the wiring investigation are removed; the toggle
  error path follows guidelines §5 (plain-language headline, traceback
  collapsed under the details toggle). The applied one-shot patch helper
  `_patch_summary2.py` is deleted from the root.
- Modeless-lifetime fix (owner feedback): the showcase now registers on an
  engine-persistent holder in `theme_manager` (`keep_alive` / `release`)
  because pyRevit tears the command scope down after the script returns —
  a `show(modal=False)` window outlives the scope and used to keep its
  visible chrome while its Python-side event wiring died (dead toggle).
  Strong references to all handlers are kept on the instance, and handlers
  read `theme_manager` via `self._tm` so none depends on the command scope.

**How it is known.** Code review only — **no harness coverage is possible**
(WPF resource loading and Revit theme detection cannot run outside Revit). The
XLSX engine is untouched: `python test_xlsx_writer.py` still ends with
`RESULT: all checks passed`, and every edited Python file passes
`python -m py_compile`. Live confirmation on Revit 2025 / CP3123 is **pending**
with the project owner: showcase opens fully styled, the toggle flips
Light/Dark instantly, the theme auto-follows Revit's setting.

**Cost / limits.** The BOQ Parameter Manager dialog does not consume these
dictionaries yet — it keeps its own WPF styling and applies the Ember palette
only to the exported workbook. Sora renders only where the font is installed;
the fallback chain covers the rest. Toolkit naming remains an open owner
decision (todo-list). Engine note: the installed pyRevit (master `6.5.3`)
stubs `pyrevit.forms` for CPython (`_cpy.py` → `PyRevitCPythonNotSupported`);
the only working backend on this machine is IronPython `_ipy.py`, so the
showcase (and the BOQ dialog) effectively run IP27 today — the CP3123-only
decision (T-03) is not yet reflected by the installed build.

---

## Standing conventions

- "Tested" always means **the harness** unless a live-Revit confirmation is explicitly noted.
- No entry is closed on a `script.py` that only *imports cleanly*.
- When the project owner verifies live-Revit behavior, update the "How it is known" line and add a
  dated note here.
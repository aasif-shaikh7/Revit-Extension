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
`python -m py_compile`. **Confirmed live (2026-08-31)** with the project
owner: showcase opens fully styled, the toggle flips
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

### BOQ-10 — BOQ Parameter Manager dialog consumes the brand theme — code in place (`v1.4.2`)

**Asked for.** The Brand UI system's written next step: "apply the same dictionaries to the BOQ
Parameter Manager dialog (`Generate.panel/BOQ.pushbutton/ui.xaml`), which today applies the Ember
palette only to the exported workbook."

**Built.**
- `ui.xaml` restyled entirely through `DynamicResource` brand keys (never `StaticResource` — the
  dictionaries are merged at runtime by `theme_manager.apply_theme`, which replaces the window's
  merged dictionaries): window + TabControl surfaces (`SurfaceBrush`), the brand type scale on
  header/project/status text, `BrandTextBox` search boxes, `BrandComboBox` filters,
  `BrandCheckBox` options, `BrandSecondaryButton` on Add/Remove/Up/Down/Top/Bottom and OK/Close,
  `BrandPrimaryButton` (Ember fill) on Export Excel, Surface/TextPrimary/Border brushes on the
  list boxes and the footer band. Control names (46 `x:Name`s), layout, tooltips and all Python
  wiring are untouched — the mechanical patch asserted every substitution count.
- `script.py` — guarded block right after window creation: `theme_manager.apply_theme(window)`
  plus `watch_theme_changes` re-apply, unsubscribed via `stop_watching` from the dialog's Closed
  event. The dialog is modal (`ShowDialog`), so plain locals outlive the session — no
  `keep_alive` (that fix is for modeless windows only). Failure of the whole block degrades to
  the stock look; it can never block the dialog.
- Version bumped to **1.4.2** (`__version__` + `SCRIPT_VERSION`).

**How it is known.** Code review + XML well-formedness check of the edited `ui.xaml` only — no
harness coverage is possible (WPF resource loading and Revit theme detection cannot run outside
Revit). Engine untouched: `python test_xlsx_writer.py` ends `RESULT: all checks passed` and
`script.py` compiles clean under CPython 3.12. **Confirmed live (2026-08-31)** by the owner:
dialog opens styled, both themes readable, the theme follows Revit's setting, and
tabs/selection/filters/reorder/export behave exactly as before.

**Cost / limits.** TabItem headers and GroupBox chrome stay on the system theme (the brand kit
ships no TabItem/GroupBox styles). Sora renders only where the font is installed (Segoe UI
fallback). Same engine reality as BOQ-9: the installed pyRevit (master `6.5.3`) stubs
`pyrevit.forms` for CPython, so the dialog runs the IronPython backend on this machine today.

---

## BOQ Parameter Manager — Level Sync-style header/footer composition (v1.4.3)

**What.** The BOQ dialog's header and footer are restyled to match the Level Sync Studio dialog's
cleaner composition: primary action (Export Excel) moved into the header, footer simplified to just
Close + options.

**Files.**
- `Aasif.extension/Aasif.tab/Generate.panel/BOQ.pushbutton/ui.xaml` — header rebuilt as a DockPanel
  (title + subtitle + project left, Export right); footer simplified (ApplyButton removed); TabControl
  gets `BorderThickness="0"`.
- `Aasif.extension/Aasif.tab/Generate.panel/BOQ.pushbutton/script.py` — version bumped to 1.4.3.
  ApplyButton handler stays behind the `if apply_button:` guard (resolves to None, degrades gracefully).

**How it is known.** XAML parses as well-formed XML; `script.py` compiles clean under CPython 3.12;
all control names (incl. ExportButton, CloseButton, 4× tab controls) intact; `python test_xlsx_writer.py`
ends with `RESULT: all checks passed`. **Confirmed (UI, 2026-08-31):** owner verified live in
Revit 2025.

---

## Theme selector + full-control brand theming — code in place (`v1.5.0`)

**Asked for.** A professional centralized Light/Dark theme with an in-dialog selector,
persistence through the existing settings file, and every control (tabs, group boxes, parameter
lists, combos, scrollbars, status states) on the active theme — built on top of the existing
architecture, not a redesign.

**Built.**
- Semantic interactive-state brushes added to `Brand.Colors.Light.xaml` /
  `Brand.Colors.Dark.xaml` with verified 42-key parity: Hover / Pressed / ItemHover / Selected /
  SelectedText / Focus (Ember) / Disabled / DisabledText / ControlBackground / Heading / Label,
  plus `Ember700` pressed accent. Light selection = Ember-100 tint with Ember-900 text; Dark
  selection = warm Ember tint with Ember-500 text.
- `Brand.Controls.xaml`: pressed states on both button styles; TextBox hover/focus/disabled
  triggers; full CheckBox template (Ember box + white tick); complete ComboBox template
  (toggle, arrow, bordered rounded dropdown) + ComboBoxItem rows; new **implicit** styles —
  TabItem (folder-tab: selected tab fills with the surface colour and connects to the content
  pane under an Ember underline; the hover fill now applies only to unselected tabs, removing
  the stray block the owner spotted on the selected tab in Dark) and an implicit TabControl
  that renders the tab row as a themed `SurfaceAltBrush` header band; GroupBox (bordered
  surface + brand header), ListBoxItem (Ember-tinted selection, neutral hover, disabled text),
  Separator, and a slim implicit ScrollBar with a horizontal variant. Implicit styles mean the
  consuming `ui.xaml` control declarations were not touched.
- `ui.xaml`: single addition — `Theme:` label + `ThemeSelector` combo (`Auto (Revit)` / `Light` /
  `Dark`) heading the footer options row. All 46 `x:Name`s (45 original + ThemeSelector), layout
  and tooltips intact.
- `script.py`: the guarded brand-theme block now restores the saved choice (existing
  `.rcc_boq_settings.json`, `"theme"` key, default `Auto`), the combo applies and **saves
  immediately** on change, and `capture_and_save_settings` carries the selector state forward
  so exports never wipe the preference. `Auto` preserves the v1.4.2 follow-Revit behavior and
  its `CurrentThemeChanged` watcher; manual Light/Dark pause the watcher until Auto returns.
  Watcher handle held in a dict (Python 2.7 has no `nonlocal`); every step degrades silently to
  the stock look. All ten footer status messages route through a new `set_status(message,
  kind)` helper — success green, error red, warning amber, info blue, normal primary text —
  applied via `SetResourceReference` so the tint follows Light/Dark swaps. Version 1.5.0.

**How it is known.** Off-Revit checks only (WPF resource loading cannot run outside Revit):
one-shot consistency script verified XML well-formedness of all five XAML files, resolved every
window `DynamicResource` reference, resolved all intra-dictionary `StaticResource` references,
confirmed Light/Dark key parity and the ThemeSelector wiring, then was deleted;
`python -m py_compile` clean; `python test_xlsx_writer.py` ends `RESULT: all checks passed`
(engine untouched). **Confirmed live (2026-08-31)** by the owner in Revit 2025: both themes
readable on every control, instant switching without reopen, choice persists across
close/reopen, Auto follows Revit's theme flip, and no regression in
tabs/selection/filters/reorder/export.

**Cost / limits.** Default theme is `Auto` rather than strict Light (deliberate — preserves the
existing follow-Revit behavior; one-line change if strict Light is wanted). Sora renders only
where installed (Segoe UI fallback). Same engine reality as v1.4.2 — the installed pyRevit
(master 6.5.3) runs the dialog on the IronPython backend; all new script code is 2.7-safe.

---

## P2-02 — Concrete-grade BOQ grouping — code complete (`v1.6.0`)

**Asked for.** P2's remaining half: "grade of concrete" grouping (owner folded material-wise
into grade-wise).

**Built.**
- `CONCRETE_GRADE_VALUES` (IS 456 series, M10–M80) + `CONCRETE_GRADE_PARAMETER_HINTS`
  (Concrete Grade / Grade of Concrete / Concrete Grade (fck) / Grade / Concrete Type /
  Concrete Mix / Mix / Mix Design).
- `normalize_concrete_grade` — pure tokenizer: canonical `M25` from `M25` / `m-30` / `M 40`
  spellings; rejects non-grades (`MIX`, `M150`, empty).
- `resolve_concrete_grade` — per-element resolution order: grade parameter (element → type,
  via the existing `find_parameter_with_scope` + `safe_parameter_value`) → Material parameter's
  target material name → grade token inside the element identity text → `(No Grade)`. Never
  raises.
- `build_element_data` emits the `Grade` column right after `Level` (deterministic column C).
- `write_basic_xlsx`: Level/Grade never pruned as fully-empty grouping columns;
  `summary_info` carries `grade_col`; new `BOQ by Grade` sheet (`build_grade_summary_table`)
  with one row per Grade x Category, static Elements counts and live SUMIF formulas against
  each category sheet's Grade column — placed between BOQ by Level and Costing (8-sheet
  workbook). Missing-values audit excludes Grade; site-format writer skips it like Level.
- Version bumped to **1.6.0** (`__version__` + `SCRIPT_VERSION`).

**How it is known.** **Tested (harness)** — `python test_xlsx_writer.py` ends
`RESULT: all checks passed` with new assertions: Grade column placement, BOQ by Grade headers,
grouped rows including `(No Grade)`, 9 live SUMIF cells, static counts, token normalization,
8-sheet order and Summary cover listing; `script.py` compiles clean under CPython 3.12. One
real defect was caught and fixed during development: fully-empty grouping columns were being
pruned from element sheets, which would have broken the SUMIF references — Level/Grade are now
prune-protected.

**Cost / limits.** Grade resolution trusts parameters literally named per the hints list;
projects using other names fall through to Material/identity matching, and only IS 456 M-grades
are recognized. Ungraded elements group under `(No Grade)`. **Confirmed live (2026-08-31)** by
the owner: grades resolve sensibly on a real model, the BOQ by Grade sheet works, and the
export stays otherwise unchanged.

---

## Site format toggle in the dialog — code complete (`v1.6.1`)

**Asked for.** Discovered during the v1.6.0 live pass: the export dispatch ran on the
hard-coded `site_format_flag = True`, so the site-style workbook shipped with no way to reach
the classic workbook (BOQ Summary / BOQ by Level / BOQ by Grade) from the UI.

**Built.** A fourth footer checkbox, **"Site format"** (`SiteFormatCheck`), wired exactly like
the existing three: export dispatch reads it (module flag stays the fallback default), the
choice persists as `"site_format"` in the existing `.rcc_boq_settings.json` via
`capture_and_save_settings`, and it is restored on startup. Checked (default) = site-style
workbook; unchecked = classic workbook with BOQ Summary, BOQ by Level and BOQ by Grade.
Version bumped to **1.6.1**.

**How it is known.** `python -m py_compile` clean; `python test_xlsx_writer.py` ends
`RESULT: all checks passed` (both writers untouched); `ui.xaml` parses as well-formed XML;
wiring asserted in source. **Confirmed (live, 2026-08-31)** — owner flipped the checkbox and
confirmed both workbooks export correctly; everything else in v1.6.0 is also live-confirmed
(2026-08-31).

**Cost / limits.** None — the checkbox only selects between the two already-verified writers.

---

## Grade fix (case-insensitive) + classic column cleanup — code complete (`v1.6.2`)

**Asked for.** Owner's live export showed the engine `Grade` column as `(No Grade)` even though
the project's shared parameter `GRADE OF CONCRETE` (all-caps) carried `M40` — and asked how to
customise/reorder classic-workbook columns.

**Built.**
- `find_grade_parameter` — case-insensitive grade lookup (element → Symbol → type), used by
  `resolve_concrete_grade` instead of the exact-name `find_parameter_with_scope`. The root cause
  was `find_parameter_on_element`'s case-sensitive `name == parameter_name` comparison: the
  hints list holds title-case names while the project's shared parameter is upper-case.
- Classic workbook cleanup: the `Qty: Dim L/W/H (m)` and `Qty: Shuttering (m2)` columns are now
  site-format-only and no longer emitted in the classic workbook (Volume / Area / Length /
  Height / Thickness / Count remain).
- Version bumped to **1.6.2** (`__version__` + `SCRIPT_VERSION`).

**How it is known.** `python -m py_compile` clean; `python test_xlsx_writer.py` ends
`RESULT: all checks passed` (the classic filter does not touch the harness expectations).
**Confirmed live (2026-08-31)** — owner re-exported: the Grade column shows `M40` from
`GRADE OF CONCRETE` and the Dim/Shuttering columns are gone from the classic workbook.

**Cost / limits.** Grade hints still match by name only (case-insensitive); a project using a
completely different parameter name still falls through to Material/identity matching.

---

## PCC beds moved into the Foundation tab — code complete (`v1.7.0`)

**Asked for.** "'Footing (F1, F2), combined footing (CF1, CF2) ke PCC' — yeh sab elements Foundation me chahiye mujhe."

**Built.**
- `is_pcc_element` — word-boundary `pcc` token check against the element identity
  (name / type / family / common labels), independent of how the element is modeled.
- PCC detection is now the **first** check in `classify_foundation_subtype`, so any PCC bed
  ("PCC F1", "PCC-CF2", "PCC Slab") classifies as the Foundation **PCC** subtype even when it
  is modeled as a floor or its name also carries slab wording / a footing mark.
- `category_elements` + `refresh_category_view`: floors whose identity carries a PCC token are
  **removed from the Slab tab** and **added to the Foundation tab** (so filter changes don't
  drift from the initial state). The Foundation **PCC** filter now shows them, and they flow
  into the Foundation element sheet / BOQ by Level / BOQ by Grade / Costing.
- Version bumped to **1.7.0** (`__version__` + `SCRIPT_VERSION`).

**How it is known.** `python -m py_compile` clean; `python test_xlsx_writer.py` ends
`RESULT: all checks passed` (engine untouched; classification is Revit-dependent so the harness
cannot execute it). **Unverified live** — owner to reload in Revit 2025 and confirm the PCC beds
appear under the Foundation tab and the Slab tab no longer lists them.

**Cost / limits.** PCC matching is by identity token; a floor named in another way ("bed",
"blinding" etc.) stays in Slab unless the name/type/family carries a PCC token.

---

## Double-click list moves + selected hidden from Available — code complete (`v1.7.1`)

**Asked for.**
1. Double-click karo to parameters Available ↔ Selected me add/remove ho jayein.
2. Jo parameters Selected me add hain, wo Available list se remove ho jayein (nahi dikhne chahiye).

**Built.**
- **Double-click:** `MouseDoubleClick` wired on every Available and Selected `ListBox`
  (Beam/Column/Slab/Foundation, wired inside the same per-category loop as the buttons):
  double-click on Available adds the item(s) to Selected, double-click on Selected removes
  them back to Available. Existing Add/Remove buttons keep working unchanged.
- **Available hides selected:** `filter_available_by_search` now collects the names currently
  in the category's Selected list and skips them when rebuilding Available — so a parameter can
  only appear in one list at a time. After Add, the moved parameter disappears from Available;
  after Remove it reappears. Saved settings restore re-runs the filter so restored selections
  are hidden too; searching and filter changes stay consistent.
- Version bumped to **1.7.1** (`__version__` + `SCRIPT_VERSION`).

**How it is known.** `python -m py_compile` clean; `python test_xlsx_writer.py` ends
`RESULT: all checks passed` (engine untouched; the list behaviour is WPF/Revit-live-only).
MouseDoubleClick wiring asserted present for both list kinds. **Unverified live** — owner to
reload in Revit 2025: double-click moves items both ways; selected items vanish from Available;
removing or restarting (restored settings) brings them back.

**Cost / limits.** None — additive UX change; ordering, filters, export untouched.

---

## Search-box text visibility fix — code complete (`v1.7.2`)

**Asked for.** "Search box me search krne pr text visible nh ho rh fix kro."

**Built.** `BrandTextBox` (used by all four search boxes) now pins the typed text to the theme's
primary colour explicitly:
- `CaretBrush` follows `TextPrimaryBrush` so the blinking caret is visible too.
- The `PART_ContentHost` ScrollViewer carries `TextElement.Foreground="{TemplateBinding Foreground}"`
  — the internal text view now explicitly inherits the control's foreground even after the brand
  dictionaries are swapped at runtime (pyRevit / IronPython dynamic-resource quirk where the text
  could otherwise lose its colour, leaving invisible input).
- `SelectionBrush` / `SelectionTextBrush` set (Ember selection, white selected text) so the
  selection is readable in both themes; disabled state also dims the caret.
- Version bumped to **1.7.2** (`__version__` + `SCRIPT_VERSION`).

**How it is known.** `Brand.Controls.xaml` parses as well-formed XML; `python -m py_compile`
clean; `python test_xlsx_writer.py` ends `RESULT: all checks passed` (engine untouched).
**Unverified live** — owner to reload in Revit 2025 and confirm typed search text is clearly
visible in both Light and Dark, with a visible caret.

**Cost / limits.** None — same template, same resources, explicit foreground inheritance.

---

## Search-box text visibility fix (round 2) — code complete (`v1.7.3`)

**Asked for.** "Image me dekho me search kr rh hu mgr text dikh nh rh hai search box pr." — the
round-1 template change alone was not enough on the live dialog.

**Root cause.** The list boxes show their text because they set `Foreground` **directly on the
element** in `ui.xaml` (`Foreground="{DynamicResource TextPrimaryBrush}"`). The search TextBoxes
relied on that property coming from `BrandTextBox`'s style setter, which does not reliably reach
the internal text view after the theme dictionaries are merged at runtime (pyRevit / IronPython).

**Built.** The four search boxes (`BeamSearch`, `ColumnSearch`, `SlabSearch`, `FoundationSearch`)
now also set `Foreground` and `CaretBrush` **directly on the element** in `ui.xaml`, same pattern
as the working list boxes — so the typed text and the caret always render in `TextPrimaryBrush`
regardless of the theme swap. Version bumped to **1.7.3**.

**How it is known.** `ui.xaml` parses as well-formed XML; `python -m py_compile` clean;
`python test_xlsx_writer.py` ends `RESULT: all checks passed` (engine untouched); direct
Foreground presence asserted on the search boxes. **Unverified live** — owner to reload and
confirm typed search text is visible in both themes.

**Cost / limits.** None — element-level properties mirror the list-box pattern that already
renders correctly.

---

## Search-box text visibility fix (round 3, programmatic) — code complete (`v1.7.4`)

**Asked for.** "Search box tikh kar do, show nahi ho raha hai text." — after template-level
(v1.7.2) and element-level XAML (v1.7.3) foreground fixes, the live IronPython dialog still
rendered the typed search text invisible.

**Root cause.** The XAML `{DynamicResource TextPrimaryBrush}` attribute — whether on the
`BrandTextBox` style/template or directly on the element — does not reliably reach the TextBox's
internal text view after the brand dictionaries are merged at runtime. The status bar, by
contrast, already used the exact `SetResourceReference` pattern and **is confirmed visible**, so
that pattern is authoritative in this environment.

**Built.** New `_apply_search_foregrounds()` in `script.py`: after theme apply (and on every
theme switch via `_apply_theme_choice`, plus a first-paint safety net) it calls
`SetResourceReference(TextBox.ForegroundProperty / CaretBrushProperty, "TextPrimaryBrush")` on
all four search boxes (`BeamSearch` / `ColumnSearch` / `SlabSearch` / `FoundationSearch`).
`SetResourceReference` sets a dynamic local reference that resolves after the dictionaries are
in place — so the text and caret always render in the theme's primary colour, and keep following
Light/Dark swaps. Version bumped to **1.7.4**.

**How it is known.** `python -m py_compile` clean; `python test_xlsx_writer.py` ends
`RESULT: all checks passed` (engine untouched); helper wired in three places (definition +
first-paint + theme-switch). **Unverified live** — owner to reload and confirm the typed search
text is now visible in both themes.

**Cost / limits.** None — additive, guarded, degrades silently if any lookup fails.

---

## Search-box text visibility fix (round 4, concrete brush + default template) — code complete (`v1.7.5`)

**Asked for.** "Nhi aa raha hai text likha hua" — rounds 1–3 (template `TextElement.Foreground`, XAML element attributes, `SetResourceReference`) did not make the typed search text visible on the live IronPython dialog.

**Root cause.** Dynamic-resource-driven `Foreground` — whether via the style, the template's `PART_ContentHost`, or XAML attributes — does not reliably reach the TextBox's internal text editor after the theme dictionaries are re-merged under IronPython. The text editor then falls back to the system window-text colour (white on a dark OS), which is white-on-white on the Light theme surface.

**Built.**
- `BrandTextBox` no longer uses a custom `ControlTemplate` — it uses the **default WPF TextBox chrome** (which renders text straight from the control's `Foreground`) plus brand colour setters and `Style.Triggers` for focus/hover/disabled border states.
- `_apply_search_foregrounds()` (definition + first-paint + every theme switch) now assigns **concrete `SolidColorBrush` values via `SetValue`** — `Foreground`/`CaretBrush` = theme primary (`#1F1F1F` Light / `#EDEDED` Dark, read from `window.Tag`), `SelectionBrush` = Ember, `SelectionTextBrush` = white. A local `SetValue` beats every lookup and cannot miss; re-applied on theme change.
- Version bumped to **1.7.5**.

**How it is known.** `Brand.Controls.xaml` well-formed; `python -m py_compile` clean; `python test_xlsx_writer.py` ends `RESULT: all checks passed` (engine untouched); helper wired at startup + on theme switch. **Unverified live** — owner to reload and confirm the typed search text (and caret) is visible in both themes.

**Cost / limits.** The TextBox loses its custom 4px rounded corner (default chrome corners are fine); disabled foreground trigger is overridden by the local brush (search boxes are never disabled in this dialog).

---

## Search-box full visual paint (background + border too) — code complete (`v1.7.6`)

**Asked for.** "Proper nhi dikh raha" — after round 4 made the typed text visible, the box
itself could still render off-theme (background/border still dynamic-resource driven; same
IronPython quirk could leave a white/internal default behind a Light or Dark surface).

**Built.** `_apply_search_foregrounds()` (now `_apply_search_textboxes()`) paints **every**
visual property of the four search boxes with concrete `SolidColorBrush` values via `SetValue`,
re-applied on every theme switch (theme from `window.Tag`): `Foreground`/`CaretBrush` = theme
primary (`#1F1F1F` Light / `#EDEDED` Dark), `Background` = theme surface (`#FFFFFF` /
`#2B2B2B`), `BorderBrush` = theme border (`#D6D6D6` / `#3F3F3F`), `SelectionBrush` = Ember,
`SelectionTextBrush` = white, plus `BorderThickness = 1`. Version bumped to **1.7.6**.

**How it is known.** `python -m py_compile` clean; `python test_xlsx_writer.py` ends
`RESULT: all checks passed` (engine untouched). **Unverified live** — owner to reload and
confirm the search boxes look proper in both themes (matching background/border/text/caret).

**Cost / limits.** None.

---

## Search-box text size fix (explicit font + larger size) — code complete (`v1.7.7`)

**Asked for.** Search-box text was visible but **very small / blurry** — the real problem was not color (5 previous color-only fixes) but **size and font resolution**: `FontSize="12"` was too small and `FontFamily="{DynamicResource BrandFontFamily}"` was not resolving under IronPython, falling back to a system default that rendered tiny/blurry.

**Built.** `BrandTextBox` style updated: `FontFamily` explicitly `"Segoe UI"` (no resource dependency — guaranteed to resolve on every Windows machine), `FontSize` 12→**14**, `Padding` 8,6→**10,7** for comfortable touch/click target. Single shared style — all four search boxes (Beam/Column/Slab/Foundation) benefit. Version bumped to **1.7.7**.

**How it is known.** `Brand.Controls.xaml` well-formed; `python -m py_compile` clean; `python test_xlsx_writer.py` ends `RESULT: all checks passed` (engine untouched). **Unverified live** — owner to reload and confirm the typed search text is now a clear, readable size in both themes.

**Cost / limits.** None — default WPF TextBox chrome was already in use since v1.7.5.

---

## Double-click add/remove with highlight — code complete (`v1.7.8`)

**Asked for.** "Double click krne pr available parameters or selected parameters remove or add hona chahiye, aur jo remove or add ho wo highlighted ho jana chahiye." — double-clicking items in Available should add them to Selected, double-clicking items in Selected should remove them, and the moved items must be **highlighted** in their new list.

**Built.** Modified `add_parameters()` and `remove_parameters()` in `script.py`:
- `add_parameters()`: tracks newly added items in a `newly_added` list; after the move, calls `selected.UnselectAll()` then adds each new item to `selected.SelectedItems` so they appear highlighted.
- `remove_parameters()`: tracks removed item names in a `removed_names` list; after `filter_available_by_search()` returns them to Available, calls `available.UnselectAll()` then selects every item whose name is in `removed_names`.
- Both blocks are wrapped in `try/except` so a highlight failure never aborts the move. Version bumped to **1.7.8**.

**How it is known.** `python -m py_compile` clean; `python test_xlsx_writer.py` ends `RESULT: all checks passed` (engine untouched). **Unverified live** — owner to reload in Revit 2025 and confirm: double-click on Available adds + highlights in Selected; double-click on Selected removes + highlights in Available.

**Cost / limits.** None — pure selection-state change, no new controls or resources.

---

## Search-box text clipping fix (row height + vertical centering) — code complete (`v1.7.9`)

**Asked for.** "Jo mene image me mark kiya hai woh text dikh nh rh search krne par" — the typed
search text was clipped vertically (only the bottom sliver of the glyphs visible at the top edge
of the box).

**Root cause.** Not a colour/size problem this time — a **clipping** problem. The search box row
was fixed at `Height="35"`; with `Margin="5"` the TextBox had only 25 px, while FontSize 14 +
Padding `10,7` (14 px vertical) + 2 px border need ≈33 px. The default WPF TextBox template
centred the text view in the remaining space, so the glyphs were cut top and bottom.

**Built.**
- `ui.xaml`: all six fixed search/input rows `Height="35"` → `Height="42"` (Beam/Column/Slab/Foundation
  search boxes + two matching rows) — full room for 14 pt text + padding + border.
- `Brand.Controls.xaml` `BrandTextBox`: added `VerticalContentAlignment="Center"` so the text stays
  centred regardless of box height.
- Side fix: a PowerShell rewrite during the edit double-encoded the header em-dash
  (`â€”`); restored to a proper `—` and re-saved clean UTF-8 (no BOM).
- Version bumped to **1.7.9** (script was still at 1.7.7 — the v1.7.8 double-click change had not
  been bumped; script jumps 1.7.7 → 1.7.9).

**How it is known.** Both XAML files parse as valid XML; `python -m py_compile` clean; em-dash and
six `Height="42"` rows verified by content check. **Unverified live** — owner to reload and confirm
the typed search text is fully visible (not clipped) in both themes.

**Cost / limits.** Search rows are 7 px taller; the Available list under each box loses that much
vertical space (negligible).

---

## P3 Formwork Engine slice 2 — configurable rules + Include formwork toggle — code complete (`v1.8.0`)

**Asked for.** Roadmap P3 "Formwork Engine (configurable rules)" — the v1.4.0 first slice had the
hard-coded shuttering formulas; this increment makes them configurable and switchable from the
dialog.

**Built.**
- **Engine** (`script.py`): `DEFAULT_FORMWORK_RULES` + runtime `formwork_rules` — `enabled` flag and
  per-category `deduction_pct` (0-100, e.g. a junction allowance where beams frame into columns).
  `compute_shuttering_area(..., factor=1.0, enabled=True)` now scales the raw contact area by a
  clamped factor (`_safe_factor`: negative/invalid → 1.0) and short-circuits to `""` when disabled —
  the SHUTTERING column goes blank instead of crashing. Slab passthrough honours the same factor and
  zero-filter as the other categories. Helpers: `normalize_formwork_rules` (settings merge with
  clamping and bad-value fallbacks), `get_formwork_factor` (pct → multiplier), `is_formwork_enabled`.
  `get_element_quantities` passes the rules so every site-format row obeys them.
- **UI** (`ui.xaml`): fifth footer checkbox **"Include formwork"** (`IncludeFormworkCheck`, default
  checked) with a tooltip documenting the formulas and where the percentages live.
- **Wiring**: export time reads the checkbox into `formwork_rules["enabled"]` (same pattern as
  `QuantitiesCheck`); apply-settings persists `settings["formwork"]` (enabled + percentages); dialog
  open restores the rules **and mirrors the saved enabled state back onto the checkbox**.
- Per-category percentages are advanced settings — edited in `.rcc_boq_settings.json` under
  `"formwork" → "deduction_pct"`; a UI editor is deliberately deferred.
- Version bumped to **1.8.0**.

**How it is known.** Harness extended: 41 functions extracted incl. the three new helpers + 11 new
checks (defaults fallback, 0-100 clamping, pct→factor conversion, enabled toggling, factor on
Column/Beam/Slab, disabled blank, zero-factor blank, negative-factor fallback);
`python test_xlsx_writer.py` ends `RESULT: all checks passed`; `python -m py_compile` clean; XAML
parses. **Unverified live** — owner to reload and confirm: "Include formwork" unchecked leaves the
SHUTTERING column blank in the site workbook, checked restores it; the choice survives restart.

**Cost / limits.** Junction deduction is a configurable percentage, not geometric intersection
analysis — beam/column overlap at frames is still counted unless the owner sets a deduction; a
per-category UI editor for the percentages is future work.

---

## Site-format SHUTTERING column restored — code complete (`v1.8.1`)

**Asked for.** "Export krne par SHUTTERING column nh dikh rh hai" — after the v1.8.0 formwork
rules landed, the exported site workbook still had no SHUTTERING column.

**Root cause.** Not a regression — the SF round-3 redesign had **deliberately removed** every
automatic column (`SIZE (MM) / VOLUME / SHUTTERING / LEVEL`) from the site detail sheets, leaving
only SNO + selected parameters. `build_site_detail_sheet` skipped all `Qty:` keys, so the engine's
`Qty: Shuttering (m2)` values were computed but never rendered.

**Built.**
- `build_site_detail_sheet(..., include_formwork=True)`: after the selected-parameter columns it
  renders one automatic **`SHUTTERING (SQM)`** band header (`MERGE_V`) plus per-row 2-decimal
  figures from `Qty: Shuttering (m2)`; `meta` gains `shuttering_col` (column letter via
  `xlsx_column_name`) and widths grow by 12 only when shown. `include_formwork=False` restores the
  previous column plan exactly.
- `write_site_xlsx(..., include_formwork=True)` passes the flag through to every detail sheet.
- Export handler calls `write_site_xlsx(..., include_formwork=is_formwork_enabled())` — the footer
  **"Include formwork"** checkbox now actually controls the workbook (the checkbox read happens
  before the writer call).
- Version bumped to **1.8.1**.

**How it is known.** Harness updated: the old "No auto columns" assertion replaced with
`include_formwork` on/off checks (SHUTTERING band header + `"8.72"` value with the fixture, column
removed and widths shrinking when off); `python test_xlsx_writer.py` ends `RESULT: all checks
passed`; `python -m py_compile` clean. **Unverified live** — owner to reload and confirm the
SHUTTERING (SQM) column appears on every populated detail sheet with real values, and disappears
when "Include formwork" is unchecked.

**Cost / limits.** SIZE (MM), VOLUME and LEVEL automatic columns stay removed (unchanged SF round-3
behavior); the Summary sheet remains the element-count cover — a SHUTTERING summary column is
future work once the owner confirms the detail figures.

---

## Formwork flag order fix + Summary honours Include formwork — code complete (`v1.8.2`)

**Asked for (owner live test of `v1.8.1`).** Two defects:
1. Site format + Include formwork **checked** → the SHUTTERING (SQM) column appeared on the detail
   sheets but every cell was **empty**.
2. Include formwork **unchecked** → the detail sheets correctly dropped the column, but the front
   **Summary still showed SHUTTERING (m2) with values**.

**Root causes.**
1. **Order-of-operations.** The export handler read the IncludeFormworkCheck checkbox *after*
   `build_element_data()` had already computed the rows. `get_element_quantities` ran against the
   stale (restored) `formwork_rules["enabled"]` — so the rows carried blank shuttering values while
   the flag updated in time for the writer, which then rendered the (empty) column.
2. **Summary ignored the flag.** `build_site_summary_sheet` had no `include_formwork` parameter; it
   always aggregated `Qty: Shuttering (m2)` straight from `data_result` (independent of what the
   detail sheets rendered), so its SHUTTERING column kept showing figures even when formwork was off.

**Built.**
- Export handler: the checkbox read moved **above `build_element_data()`** (beside the
  `QuantitiesCheck` read, with an explanatory comment); the stale copy after the site-format check
  was deleted. Rows now always see the current dialog state.
- `build_site_summary_sheet(..., include_formwork=True)`: formwork off drops the SHUTTERING (m2)
  band column, the per-category aggregate cell and the TOTAL-row SUM formula, renames the caption
  to "ITEM-WISE SUMMARY - CONCRETE", and reports `total_columns: 4` / no `Shuttering (m2)` in meta.
  `write_site_xlsx` passes the flag through and shrinks `summary_widths` to
  `[7, 24, 10, 14]` when off.
- Version bumped to **1.8.2**.

**How it is known.** Harness extended with formwork-off summary checks (caption, band without
SHUTTERING, 4-cell data rows, 4-column meta); `python test_xlsx_writer.py` ends `RESULT: all checks
passed`; `python -m py_compile` clean; checkbox-read-before-rows-build order verified by line
inspection. **Confirmed live (2026-09, owner)** — both checkbox states verified end to end in
Revit 2025; with v1.8.2 this closes roadmap **P3 — Formwork Engine**.

**Cost / limits.** None beyond v1.8.1's — junction deduction is still a configurable percentage.

---

## Search-box descender clipping fix + mojibake arrow buttons repaired — code complete (`v1.8.3`)

**Asked for (owner screenshots).**
1. Search-box me typed alphabets ke descenders (g/y/p ki neeche wali tail) **puri tarah nahi
   dikhte** — "building" ka g cut.
2. Add/Remove/Up/Down/Top/Bottom buttons pe text corrupt: `Add â†'`, `â†‘ Up`, `â‡§ Top`…

**Root causes.**
1. **Descenders:** search row 46 px se bhi chhoti math nahi ban rahi thi — box 32 px (42 - 10
   margin), border 2 px, Padding `10,7` = 14 px vertical → text ke liye sirf 16 px, jabki Segoe UI
   14 pt ki line height ≈ 19 px. Descender clip fix karna tha.
2. **Buttons:** file me arrows (`→ ← ↑ ↓ ⇧ ⇩`) ki UTF-8 bytes **Windows-1252 se dobara encode** ho
   chuki thi — mojibake literally stored tha (`â†'` = U+2192 ke bytes), WPF sahi render kar raha
   tha, file hi galat thi.

**Built.**
- `ui.xaml`: search/input rows `Height="42"` → **46** (6 places); button Content strings ke mojibake
  sequences ko **XML numeric character references** me convert kiya — `Add &#x2192;`,
  `&#x2190; Remove`, `&#x2191; Up`, `&#x2193; Down`, `&#x21E7; Top`, `&#x21E9; Bottom` (24
  replacements — 4 tabs × 6 buttons). Numeric references encoding-proof hain: ab koi bhi file
  reader/parser unhe hamesha sahi arrow me hi convert karega.
- `Brand.Controls.xaml` `BrandTextBox`: `Padding` `10,7` → **`10,5`** — content area ab
  30 - 10 = 20+ px text room deta hai (19 px line height fit), descender safe.
- Version bumped to **1.8.3**.

**How it is known.** Dono XAML valid XML; mojibake sequence count 0; 24 numeric refs present;
6× `Height="46"`; `Padding 10,5` present; `python -m py_compile` clean; harness `RESULT: all checks
passed`. **Unverified live** — owner to reload and confirm: search me g/y/p descenders poore dikhen
aur buttons par sahi arrows (→ ← ↑ ↓ ⇧ ⇩) dikhen.

**Cost / limits.** Rows 4 px taller (negligible); numeric refs source me thode less readable —
intentional trade for encoding-immunity.

---

## Descender clipping fix (corrected) — code complete (`v1.8.4`)

**Asked for (owner screenshots).** Small alphabets (g, p, q, y) ke descenders abhi bhi clip ho rahe hain — "g" pura nahi dikh raha.

**Root cause.** v1.8.3 ne Padding `10,7` se `10,5` kar diya (ghataya), jisse content area aur chhota ho gaya. FontSize 14 + line height ~19px ke liye bottom padding 5px kam tha — descenders neeche se clip ho rahe the.

**Built.**
- `Brand.Controls.xaml` `BrandTextBox`: `Padding` `10,5` → **`10,8`** — content area ab 32px (border 2px + padding 16px = 18px used, ~14px text room, descenders safe).
- Version bumped to **1.8.4**.

**How it is known.** XAML valid; `Padding 10,8` present; `python -m py_compile` clean. **Unverified live** — owner to reload and confirm: g/p/q/y ke descenders poore dikhen.

**Cost / limits.** Negligible — text box thoda zyada padding ke saath, par visually balanced.

---

## v1.8.5 — Shuttering column now writes Excel formulas (not plain values)

**Asked.** P3 me SHUTTERING (SQM) column direct value likhta tha — ab Excel formula chahiye taaki sheet dynamic rahe aur L/W/H change hone par shuttering auto-update ho jaaye.

**What was built.** `build_site_detail_sheet` me shuttering cell ab `=ROUND(..., 2)` formula likhta hai:
- Column: `=ROUND(2*(L+W)*H, 2)`
- Beam: `=ROUND((W+2*H)*L, 2)`
- Slab: `=ROUND(L*W, 2)` (soffit area)
- Foundation: `=ROUND(2*(L+W)*H, 2)`

Formula column letters dynamically assign hoti hain — selected parameters ke hisab se L/W/H ka letter calculate hota hai.

**How it is known.** Harness: all checks passed (41 functions). Naye checks verify ki har category ka formula sahi column letters ke saath likh raha hai. `py_compile` clean. **Confirmed live (owner)** — SHUTTERING (SQM) column me formula dikhta hai, L/W/H change hone par auto-update hota hai.

**Cost / limits.** None — Excel native formulas, no performance impact.

---

## v1.8.6 — Module split: five pure-Python engines moved to `Nudge.extension/lib/`

**Asked.** `script.py` (~7,289 lines) ko PROJECT_STRUCTURE.md §9 ke target layout me split karna —
refactor only, zero behaviour change; P4 (Rebar Engine) se pehle required.

**What was built.** Five engines moved verbatim (byte-identical, machine-verified against the
pre-split file) from `BOQ.pushbutton/script.py` (7,289 → 4,181 lines) into `Nudge.extension/lib/`:
`settings_engine.py` (79), `quantity_engine.py` (235), `formwork_engine.py` (247),
`costing_engine.py` (155), `export_engine.py` (2,566). `script.py` imports the moved names back by
plain module name — the same extension-`lib/` sys.path mechanism the existing `theme_manager`
import uses. Revit-bound code (classification, parameter discovery, WPF dialog, event wiring) stays
in `script.py`. Two documented mechanical shims were unavoidable: a guarded `Autodesk.Revit` import
in `convert_quantity_value` (keeps the module importable in plain Python for the harness), and a
call-time `from costing_engine import build_costing_sheet` inside `write_basic_xlsx` (avoids the
writer→costing import cycle). `test_xlsx_writer.py` is now module-aware (engine modules first,
`script.py` fallback; `lib/` on sys.path) and a pre-existing broken `\Z` anchor in its extraction
regex was fixed. `SCRIPT_VERSION` / docstring `__version__` aligned at `1.8.6` (PATCH bump per §8).

**How it is known.** Harness: `python test_xlsx_writer.py` → `RESULT: all checks passed` (42
functions resolved from the new modules: export ×31, formwork ×6, quantity ×3, costing ×1,
script ×1). A separate verbatim proof confirmed 45 moved defs byte-identical to the pre-split file
(modulo the two documented shims). `py_compile` clean on all six files. **Unverified in Revit** —
the `lib/` import at button click must be confirmed live by the project owner (Revit 2025; T-03
engine guard still applies: on this machine the button runs on IP27 until a CPython-capable
`pyrevit.forms` ships).

**Cost / limits.** In-Revit behaviour of the split is pending owner verification. Pre-existing
`__version__` drift (docstring 1.8.3 vs `SCRIPT_VERSION` 1.8.5) is now aligned at 1.8.6.

---

## v1.8.7 — Site detail sheets now sort by level (ascending building order)

**Asked.** Site-format detail sheets me rows collector order me aa rahi thi — LEVEL_V ascending
nahi tha (Beam tail me 7TH LEVEL ke baad 2ND/3RD wapas aa rahe the; Column sheet me 12 TERRACE
LEVEL, 06 3RD LEVEL se pehle dikh raha tha). Owner ne ascending order fix manga.

**What was built.** `export_engine.py` me naya stable `_sort_site_rows(rows)` — har category sheet
ko uske pehle LEVEL-like selected parameter (LEVEL_V, BASE LEVEL, ...) par ascending sort karta hai,
caller `write_site_xlsx` se wired. `_site_sort_key` ab documented building order follow karta hai:
FOUNDATION/BASE < PLINTH < numbered levels ("Level 2 before Level 10" preserved) < TERRACE <
OHW/LMR < baaki text alphabetically. Named storeys jinke naam me number nahi hai (PLINTH LEVEL,
TERRACE LEVEL, OHW/LMR LEVEL) keyword-rank se place hote hain, aur jinka number model-list index
hai ("01 FOUNDATION LEVEL", "03 PLINTH LEVEL") wo bhi keyword se hi sahi rank hota hai. No-level
selections (jaise Slab/Foundation me LEVEL_V select nahi hai) apne original collection order me
aate hain. Sort stable hai — ek hi storey ke andar element order aur SNO sequence deterministic
reheta hai. `SCRIPT_VERSION` / docstring `__version__` bumped to **1.8.7**.

**How it is known.** Harness: `python test_xlsx_writer.py` → `RESULT: all checks passed` (43
functions; naye checks — building-order ranking of the level key, ascending stable grouping via
`_sort_site_rows`, no-level rows passing through untouched). `py_compile` clean. **Unverified
live** — owner ko v1.8.7 reload karke re-export karna hoga; purani workbook pre-fix export hai.

**Cost / limits.** Beam sheet me 26 blank VOLUME rows the (25 x 7TH LEVEL + 1 x 2ND LEVEL, SNO
515-545 range) — unka L/W/H/CUT LENGTH bhara hai, sirf VOLUME parameter khali report hua, matlab
model-data side: tool selected parameter ko as-is dikhata hai, values invent nahi karta. LEVEL_V
Slab/Foundation sheets par tabhi dikhega jab owner dialog me un categories ke liye LEVEL_V select
kare — per-category selection by design hai.

---

## Standing conventions

- "Tested" always means **the harness** unless a live-Revit confirmation is explicitly noted.
- No entry is closed on a `script.py` that only *imports cleanly*.
- When the project owner verifies live-Revit behavior, update the "How it is known" line and add a
  dated note here.
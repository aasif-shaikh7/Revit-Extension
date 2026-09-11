# Revit-Extension — Todo List

**Document:** `todo-list.md`
**Status:** Active — the queue of work not yet finished
**Companion to:** `done-list.md`, which holds everything finished

---

## How to read this

Each open item is in one of these phases and moves down only when the previous phase is actually
true:

```text
todo      → decided but not started
pending   → design/requirement agreed
building  → code being written
testing   → code exists, being verified
done      → moved to done-list.md (for the engine: harness passes; for the UI: project-owner confirm)
```

Work follows the **Development Roadmap** in `PRD.md` (Phases 1–16). Phases are taken in order and
the next phase starts only after the previous one is stable in Revit — except when the actual
source code suggests a better order. In case of conflict, **the code wins over this document**.

An agent can move only the **engine-side** items toward `done` by running `test_xlsx_writer.py`.
Everything about the live Revit dialog stops at `testing` until the project owner runs it in Revit
2025+ on a real project.

**Verification states used:** `Unverified`, `Experimental`, `Tested (harness)`, `Tested (live)`,
`Supported`.

**Feature ratings** (Priority / Benefit / Complexity / Implementation Ease) are defined in `PRD.md`
§Feature Rating.

---

## Roadmap phase status

| Phase | Feature | Rating (P/B/C/E) | Status |
|---|---|---|---|
| P0 | Live-Revit confirmation of the current dialog | — | **done** (`v1.0.1`) |
| P1 | Structural Quantity Engine (extend, don't duplicate) | 5/5/3/4 | **done** (`v1.1.0`) |
| P2 | Structural BOQ Grouping (level + concrete grade done) | 4/4/2/5 | **done** (`v1.6.0`) |
| P3 | Formwork Engine (configurable rules) | 5/5/3/4 | **done** (`v1.8.2`) |
| P3.5 | Structure Wall category integration | 5/5/2/4 | **done** (`v1.9.3`) |
| P4 | Rebar Quantity Engine | 5/5/3/3 | **done** (`v1.19.0` QA) |
| P5 | Rebar Diameter Summary + BBS | 4/5/5/2 | **done** (`v1.19.1`) |
| P6 | Structural BOQ Assembly (concrete/rebar/formwork/wire/blocks/labour) | 4/5/4/3 | **done** (`v1.15.0`) |
| P7 | Site / Manual Structural Items | 4/4/2/4 | `todo` |
| P8 | Structural Rule Engine (keep `script.py` modular) | 5/5/5/2 | `todo` |
| P9 | Validation Engine (compact report) | 4/4/3/4 | `todo` |
| P10 | Unmapped Element Report | 4/4/2/4 | `todo` |
| P11 | Structural Rate Analysis (material/labour/machinery/wastage/overheads) | 4/5/5/2 | `todo` |
| P12 | Structural Rate Database (configurable, not hard-coded) | 4/5/4/2 | `todo` |
| P13 | Professional Excel BOQ (extend existing XLSX engine) | 5/5/3/4 | `todo` |
| P14 | BOQ Revision (Rev 00/01/02 comparison) | 4/5/4/2 | `todo` |
| P15 | Model Change Detection (added/modified/deleted) | 3/5/5/1 | `todo` |
| P16 | Structural Dashboard | 3/4/3/4 | `todo` |
| INT-03 | Controlled Agent Bridge (MCP read/write + BOQ validation) | — | `done` (`v1.19.0`) |

---

## Active roadmap phase

**Current product focus:** P7 Site / Manual Structural Items. P4 and P5 native Rebar/BBS QA are
complete through `v1.19.1`.

### INT-03 — Controlled Agent Bridge — **done** (`v1.19.0`, Bridge API `v2.3.0`)

**Built:** native Agent Bridge consent button, 15-minute write window, dry-run-first parameter edit,
optimistic current-value check, bounded REST/MCP schemas, Revit transaction rollback and audit log.
Arbitrary code/API dispatch, delete and automatic document save remain forbidden.

**Verified:** zero-warning Revit/Gateway/MCP builds and Core/MCP protocol tests. The `v2.0.0`
deployment also ran beside an untouched `v1.14.1` Revit session: authenticated status/document/
element/Rebar reads passed against Revit 2025, the `Comments` dry-run returned the expected preview,
an apply attempt with write consent disabled was rejected, and the parameter remained unchanged.
With explicit 15-minute consent enabled, `Comments` was changed from blank to `Agent QA`, verified
by a fresh read, restored to blank and verified again without saving the document. A stale
expected-value write was rejected without changing the model, and manual revocation restored
read-only mode. The installed MCP server completed a raw initialize/list/status exchange and is
registered in Codex as `rcc-boq-v2`.

**Built in v1.17.0:** Classic and Site exports now validate every persisted non-empty XLSX cell
against their canonical in-memory Revit-derived rows before publication. A bounded fixed-path
report carries basename/digest/counts only, and the new read-only REST/MCP/CLI operation returns
that report plus its active-document match state without accepting an arbitrary filesystem path.

**Verified (host-free):** both workbook formats pass the canonical validator; an intentionally
changed Beam cell is detected. All Python, .NET Core/MCP/REST and zero-warning bridge builds pass.

**Built in v1.18.0:** the consent-gated MCP/REST export operation queues the existing pyRevit BOQ
command in hidden one-shot mode. It writes a uniquely named Classic/Site workbook only below the
fixed current-user `AgentExports` folder, preserves saved dialog settings, prevents auto-open and
publishes a pollable bounded result with the canonical validation summary. No arbitrary output path,
overwrite or Revit document save is exposed.

**Verified (host-free):** job lifecycle, exact-document matching, external-path rejection,
dry-run-first REST/MCP schemas, nine-tool catalog, Python compilation and all automated suites pass.

**Fixed in v1.18.1:** Bridge `v2.2.1` uses the fully-qualified BOQ command identifier captured from
the live Revit journal; the earlier short identifier was not postable by Revit 2025.

**Fixed and live-verified in v1.18.2:** optional .NET-null assembly factors no longer abort export;
the validator releases its ZIP wrapper before publication and retries transient Windows locks. A
native headless Site workbook passed 70,085/70,085 cells across 10/10 sheets, and Classic passed
118,101/118,101 across 14/14 sheets. Both had zero mismatches and their report hashes matched the
published files. The consent-off guard and automatic return to consent-disabled state also passed.

**Built in v1.19.0:** Primary (`48885`) and Secondary (`48886`) bridge builds use separate mutexes
and Named Pipes, so a dedicated test Revit can be targeted without touching the user's working
Revit process. The consent-gated `force_rollback` probe deliberately fails after a valid parameter
set, rolls the transaction back and verifies the original value by native read-back.

**Verified in native Revit 2025:** Secondary `48886` connected only to the dedicated
`20260225-BBS_BEAM_RBM_SALES-P1` test process while Primary `48885` remained connected to the
working document. Rebar `3411763` `Comments` passed dry-run and consent-off checks; the consented
forced-failure probe returned `RolledBack`, fresh read-back matched the original blank value, the
audit log recorded `verified=True`, and the document was not saved.

### P6 — Structural BOQ Assembly — **done** (`v1.15.0`)

**Built:** a pure `assembly_engine.py` creates category/component take-offs for concrete,
reinforcement, formwork, binding wire, cover blocks and labour. The Global / Custom profile never
invents missing local factors: unsupported allowances remain blank with `Input required`. Profile
and source metadata are exported, saved settings are normalized, and Classic plus Site workbooks
include a `Structural Assembly` sheet.

**Verified:** compile checks and the complete XLSX harness pass, including hosted Rebar weight
routing, auditable headers, blank-allowance safety and both workbook layouts. Revit 2025 live QA
also verified the Assembly Profile UI, saved-profile restore, and both Site and Classic exports;
their generated workbooks contained the Structural Assembly sheet with the saved profile/source.

### INT-02 — Codex STDIO MCP adapter — `complete` (`v1.14.1`)

**Built:** a dependency-free .NET 8 STDIO MCP server exposes five read-only tools for bridge status,
active document, selection, generic element and Rebar. It reads the existing per-user token at call
time and forwards only to the fixed localhost REST allow-list. Tool annotations declare read-only,
non-destructive, idempotent, closed-world behavior; element IDs require positive integers.

**Verified:** zero-warning build, dependency-free MCP protocol regressions and live STDIO handshakes
all pass. After a fresh Revit 2025 launch, the installed MCP server listed all five tools and its
status call returned the connected `v1.14.1` bridge without exposing a path or token. With
`20260225-BBS_BEAM_RBM_SALES-P1` open, document, empty-selection, generic-element and varying-Rebar
calls passed. Rebar `3411763` returned Quantity `3`, blank Bar Length, Total Bar Length `33510 mm`,
dimension A as `Varies` and `has_variable_length_bars=true`.

**Installed:** `v1.14.1` is published side-by-side and global Codex server `rcc-boq` is enabled at
the installed executable. Its BOM-hardened installed STDIO handshake and live status/document calls
pass; the fresh Revit process now loads and reports the `v1.14.1` bridge.

**Final live QA:** a fresh ephemeral Codex session discovered and invoked the registered
`rcc-boq/rcc_boq_status` tool without using a shell, direct executable or HTTP fallback; it returned
the connected `v1.14.1` bridge. A visible Revit selection then returned one bounded Structural Rebar
snapshot for element `3411763` with `truncated=false`. INT-02 is complete.

### INT-01 — Secure direct Revit REST integration — `complete` (`v1.13.3`)

**Built:** a Revit 2025 .NET add-in owns a current-user-only Named Pipe and queues only approved reads
through `ExternalEvent`. An out-of-process ASP.NET Core Gateway exposes status, document, selection,
element and Rebar GET endpoints only on `127.0.0.1`; a random per-user Bearer token protects every
endpoint. Payloads are bounded, responses are non-cacheable, model paths are excluded, and there is
no transaction/arbitrary-execution endpoint. The dependency-free client lives at
`scripts/rcc_boq_rest_client.py`; `scripts/install_rest_bridge.ps1` builds and installs the add-in.
The unstable pyRevit Routes prototype remains disabled as `startup.disabled.py`.

**Tested (host-free):** Gateway and Revit projects compile with zero warnings/errors; .NET token and
pipe framing tests pass; Python client/serialization and complete XLSX regressions pass. A local
Gateway smoke test returns `401` without credentials and a fast `503` when Revit is unavailable.

**Live-verified:** Revit 2025 loaded `v1.13.1`; unauthenticated status returned `401`, authenticated
status reported a connected Revit bridge, document and empty-selection calls succeeded, and varying
Rebar ID `3411763` returned native Quantity `3`, blank Bar Length, Total Bar Length `33510 mm` and
`has_variable_length_bars=true`. Non-Rebar and missing-element calls returned `422` and `404`.
Revit and Gateway remained responsive with no new bridge-log error.

**Live-verified in `v1.13.2`:** a non-empty selection returned Rebar `3411763` with bounded identity
data. A repeated Rebar call confirmed Revit exposes A as blank/`HasValue=false`, so merely reading
display text is insufficient.

**Live-verified in `v1.13.3`:** authenticated status reported the connected bridge; the non-empty
selection returned Rebar `3411763`, and its Rebar payload returned A `Varies`, B `492 mm`, Quantity
`3`, blank individual Bar Length, Total Bar Length `33510 mm` and
`has_variable_length_bars=true`. Revit and Gateway remained responsive with no new bridge-log error.

**Final live QA:** with two Revit processes, exactly one Gateway remained active and the second
add-in logged that it was inactive while the API stayed connected. Closing the owner Revit normally
also stopped its Gateway and wrote a clean bridge-stopped log entry. Relaunching Revit restored one
Gateway with `revit_connected=true`. INT-01 is complete; the MCP layer is the next integration phase.

### P4-01 — Rebar Quantity Engine first slice — **done** (`v1.19.0` QA)

**Built:** a dedicated Rebar tab collects `OST_Rebar`, discovers raw Revit parameters and writes a
Rebar sheet in Classic and Site formats. Automatic fields are Bar Mark, Diameter, Shape, included
bar Quantity, individual Bar Length, Total Length, Host Element ID/category, Level, Unit Weight and
Total Weight. The pure `lib/rebar_engine.py` uses `d²/162 kg/m`; Revit's `TotalLength` is preferred,
with `Bar Length × Quantity` as a guarded fallback. Rebar-only models may export without selecting an
extra raw parameter. Every automatic field also appears in Rebar's Available Parameters list and can
be moved into Selected / Export. Costing uses Total Weight first when a rate field exists.

**Tested (harness):** pure unit/total weight, Classic Rebar columns and sheet order, Site Rebar
columns without formwork, costing integration, UI controls, `OST_Rebar` wiring and every prior
regression pass. Syntax compilation passes.

**Verified in native Revit 2025 (`v1.19.0` QA):** the isolated Secondary bridge compared a
Quantity-1 bar and fixed Rebar sets directly with the validated Classic/Site rows. Diameter,
Quantity, Bar Length, Total Length, Host ID/category, host Level and d²/162 weights matched native
Revit reads within displayed-unit rounding. All 965 Rebar detail rows reconcile with both BBS and
diameter summaries at 11,903 bars, 25,439.37 m and 30,130.966 kg. Site Rebar contains no standalone
L/W/H or SHUTTERING columns. P4-01 is complete.

### P5-01 — Shape-aware BBS + diameter summary — **done** (`v1.19.1`)

**Built:** automatic A-H dimensions, Bend Diameter, start/end hooks and Cutting Length are read for
each Rebar. Cutting Length intentionally uses Revit's shape-aware Bar Length instead of assuming one
bend-deduction formula for L/C/stirrup/U-ring shapes. Classic and Site workbooks add `Rebar BBS` and
`Rebar Summary`; compatible rows group by geometry/host/level and diameter totals report bars,
length, kilograms and tonnes.

The owner-exported `v1.11.0` workbook reconciled raw/detail, BBS and diameter totals exactly at
11,903 bars, 25,439.37 m and 30,130.966 kg. Audit found every BBS Level blank and 26 grouped
variable-length entries (280 bars) without an individual Bar Length. `v1.11.1` adds host-level
fallback plus an explicit Average Bar Length / Length Status without fabricating a cutting length.

`v1.11.2` additionally persists every Available -> Selected parameter choice and its visible order
after edits, Apply/Export and all dialog close paths.

`v1.11.3` fixes Beam shuttering for angled/rotated framing: actual built-in/type `BEAM WIDTH` and
depth drive the formula, while bounding-box section dimensions are rejected. The corrected owner
workbook target is 22,488.481276 m2 unrounded, or 22,488.94 m2 after the exporter's existing
two-decimal rounding on each of the 4,031 Beam rows.

`v1.12.0` indexes instance parameters once per element and type parameters once per shared Revit
type, then reuses those indexes for Selected fields, Grade and identity reads. This removes the
largest repeated API scan from the export path.

Live `v1.12.0` timing was 46.0 seconds for 9,632 rows: Revit data 40.1 seconds and workbook 5.9
seconds. `v1.12.1` targets that measured data bottleneck by skipping Site-only unnecessary Grade
resolution, caching Level names and avoiding unnecessary framing bounding boxes.

Live `v1.12.1` follow-up completed the same export in 19.1 seconds (58.5% faster). `v1.12.2` adds
a compact completion-popup list for routing findings. `v1.12.3` uses system-Floor built-in Type
fallbacks and routes the screenshot-verified `LOBBY` and `ramp` types to `Slab / Slab`.
`v1.12.4` keeps each varying Rebar set on its own BBS row, preserves `Varies` dimensions and adds
Rebar Element ID traceability while retaining fixed-bar grouping.

**Live-verified in `v1.12.4`:** the two `33510 mm / 3 bar` sets are separate BBS rows with distinct
Rebar Element IDs, `11.17 m` average, blank Cutting Length and `A=Varies`. The old combined row is
absent, and BBS/Rebar Summary totals reconcile exactly.

**Verified in native Revit 2025 (`v1.19.0` QA):** all 4,031 Site Beam L/W/H rows match native
element/type dimensions within the Classic/Site 1 mm formatting boundary. Fixed stirrup, straight,
L-shape, C-shape and both U-ring samples match native Diameter, A-H, bend, hooks, Cutting Length,
Quantity, Total Length, host and Level values. Variable Rebar `3411763` remains blank for Cutting
Length and reports `Variable set / average only`. Both workbook formats are valid Open XML and
their Rebar/BBS/Summary totals reconcile exactly.

**Found and fixed in `v1.19.1`:** the fresh restart restored the exact JSON selection order, but
the active IP27 engine's plain Python `dict` interleaved automatic columns in the Classic workbook.
Export rows now use `OrderedDict`, preserving grouping fields followed by the Selected-list order.
Compilation and the complete harness pass. A corrected native Classic export placed the saved
`Rebar: Element ID`, `Rebar: Diameter (mm)`, `Rebar: Total Weight (kg)` fields consecutively at
columns 3-5 after `Element ID, Level`; all 118,101 canonical cells and 14 sheets passed with zero
mismatches. P5-01 is complete.

---

## P0 — Confirm the current dialog in Revit 2025 (before any new phase)

### T-01 — Confirm live-Revit behavior of the dialog — **done** (`v1.0.1`)
**State:** **Confirmed live in Revit 2025** by the project owner with **no regression** (tabs,
parameter loading, filters, reorder, export). One issue was found and fixed in `v1.0.1`:
element-referencing parameters (Type, Level, Base/Top/Reference Level, Cover Type) now export the
referenced element's **name** instead of the raw ElementId. **Acceptance met** — owner confirmed the
fix in the same Revit session. Remaining for full P0 closure: dual-engine parity (CP3123 vs IP27) is
still pending (T-03).

### T-02 — Quantity accuracy on real materials — `testing`
**State:** Metric conversion logic is deterministic and harness-tested with sample data, but true
`Qty: Volume/Area/Length` values on actual Revit elements are

---

### T-07 — Double-click add/remove with highlight — **done** (`v1.7.8`)
**Asked for.** "Double click krne pr available parameters or selected parameters remove or add hona chahiye, aur jo remove or add ho wo highlighted ho jana chahiye."
**Built.** `add_parameters()` and `remove_parameters()` now select/highlight moved items in their new list.
**Confirmed live (2026-08-31):** owner verified double-click highlight works for both directions in Revit 2025.
**Acceptance:** compare at least one beam/column/slab/foundation quantity against a known-correct
value in Revit; record any engine adjustments.

### T-03 — Dual-engine parity — **closed by decision** (`1.2.0`)
**Decision (owner, 2026-08-26):** only ONE engine is supported — **CP3123 (CPython 3.12.3)**, the
modern runtime. **IP27 (IronPython 2.7)** is legacy EOL Python and is documented as best-effort /
untested, not a support target. The code stays 2.7-syntax-safe so IP27 may still work, but no
parity testing is promised or tracked here.
**Engine reality — confirmed by inspection (2026-09-01, evidence-based):** the installed pyRevit
build at `%APPDATA%\pyRevit-Master` reports version `6.5.3.26176+2017`; its
`pyrevitlib/pyrevit/forms/__init__.py` dispatches on `IRONPY` (`compat.py:15`,
`'.net' in sys.version.lower()`) → `forms/_ipy.py` (IronPython) or `forms/_cpy.py` (CPython); its
`forms/_cpy.py` is a **pure stub** — every symbol raises `PyRevitCPythonNotSupported` (checked against the installed file,and against upstream master `6.5.5`, which ships the identical stub).
Upstream pyRevit master currently exposes **no** CPython-capable `pyrevit.forms`, so **no** upstream
version/bump fixes this yet. **Consequence (stated, not guessed):** both form-based pushbuttons
(`BOQ.pushbutton`, `BrandShowcase.pushbutton`) execute on the **IP27** engine on this machine today
— the dialog can only open via `forms/_ipy.py`. The "CP3123-only" product decision remains the
support target, but it is **not** the actually-active runtime until a CPython `forms` backend
ships in pyRevit.

**Runtime verification hook (added in code `v1.8.6`):** `script.py` calls
`_warn_if_not_cp3123()` at startup. The live engine check is complete, so from `v1.9.3` known
CP3123/IP27 runs are silent and do not force-open pyRevit output; only an unexpected third engine
raises `forms.alert(...)`. A detection failure never blocks the dialog or export.
**Tested (live) 2026-09-02:** the owner clicked the BOQ button in Revit 2025 — the guard's
`forms.alert` appeared with the expected IP27 wording, and the dialog opened, which also live-proves
that the v1.8.6 module split (plain imports from `Nudge.extension/lib/`) loads on the IP27 engine.
That historical one-time evidence is retained here; the recurring alert/output was removed in
`v1.9.3` after it began interrupting otherwise healthy exports. Settings persistence remains a
separate live verification item.

---

## P2 — Structural BOQ Grouping (code complete)

### P2-01 — Level-wise BOQ grouping — **done** (`v1.2.0`)
**Built:** every element row carries an engine-added `Level` column (deterministic column B),
resolved from reference/schedule level parameters with a `LevelId` fallback. A new `BOQ by Level`
sheet groups quantities per Level x Category using live SUMIF formulas against the category
sheets; Elements is a static per-group count. Missing-values audit excludes the Level column.
**Tested (harness):** Level placement, grouped rows for every collected level (incl. `(No Level)`),
9 live SUMIF cells for the sample layout, static counts, final sheet order
Beam/Column/Foundation/BOQ Summary/BOQ by Level/Costing.
**Confirmed live (`v1.2.0`).** Owner verified Level resolution, grouped totals and the full export
in Revit 2025; tagged `v1.2.0`.

### P2-02 — Concrete-grade BOQ grouping — **code complete** (`v1.6.0`, live QA pending)
**Decision (owner):** grade of concrete — material-wise grouping collapses into grade grouping.
**Built:** every element row now also carries an engine-added `Grade` column (deterministic
column C, right after Level), resolved by `resolve_concrete_grade`: (1) recognized grade
parameters (Concrete Grade / Grade of Concrete / Grade / Concrete Type / Concrete Mix / Mix /
Mix Design) via the existing scope resolver, (2) the Material parameter's target material name,
(3) a grade token (`M25` / `m-30` / `M 40`) in the element identity text — normalized against the
IS 456 series (`CONCRETE_GRADE_VALUES`, M10–M80); falls back to `(No Grade)`. New `BOQ by Grade`
sheet groups quantities per Grade x Category with live SUMIF formulas against each category
sheet's Grade column, placed between BOQ by Level and Costing. Grouping columns (Level, Grade)
are never pruned as fully-empty so the formulas always resolve; the missing-values audit excludes
both; the site-format writer skips the Grade column like Level.
**Tested (harness):** Grade placement after Level, headers, grouped rows incl. `(No Grade)`,
9 live SUMIF cells, static counts, grade-token normalization (`M25`/`m-30`/`M 40` accepted;
`MIX`/`M150`/empty rejected), sheet order with 8 sheets, Summary cover listing.
**Confirmed live (`v1.6.0`, 2026-08-31).** Owner verified grade resolution, the `BOQ by Grade`
sheet and the export on a real model in Revit 2025.

---

## Professional output — Summary cover + site naming (started)

### OUT-01 — Site naming convention + front Summary cover — `testing` (code v1.3.0)
**Built:** Save dialog suggests `YYYYMMDD-<Project>-CONCRETE_FINISHING_BOQ.xlsx`
(`sanitize_file_name` + document title); a front `Summary` cover sheet carries project name,
generation stamp, tool version and the sheet listing.
**Tested (harness):** cover meta/listing checks, sanitization and default-name regex all pass.
**Remaining:** live Revit confirmation of the suggested filename and cover contents; then tag
`v1.3.0`.

### OUT-02 — 3D view snapshot — `decision pending`
A true/embedded Revit 3D view inside Excel is **not feasible** via the supported API. The realistic
option is an *Experimental* image sheet capturing the current 3D view (window screenshot) — only if
the owner opts in. Exact column styling from
Exact reference styling is deferred until a new workbook or screenshots are intentionally supplied;
the old local `.xlsm` reference has been purged from the repository.

---

## Site-format export — manual site BOQ look (started)

### SF-01 — Site workbook + P3 shuttering (first slice) — `engine done` (code v1.4.1)
**Built:** pure helpers — `meters_to_millimeters`, `build_section_description`
("`W X L`" mm strings), `_site_dim_value` (unrounded dims), `resolve_element_dimensions`
(param-first with bbox fallback; Column pair sorted W<=L) and `compute_shuttering_area`
(Column `2(L+W)H`, Beam `(W+2H)L`, Slab soffit, Foundation footing sides). Quantity rows
carry `Qty: Dim L/W/H (m)` + `Qty: Shuttering (m2)`; `write_site_xlsx` +
`build_xlsx_sheet_xml_site` render merged title blocks, two-tier light-blue header bands,
MM integer columns, VOLUME/SHUTTERING figures, bordered TOTAL rows and a front level-wise
Summary with live SUMIF formulas against each detail sheet's LEVEL feed column.
Dispatch sits behind `site_format_flag = True`; classic workbook stays as rollback
(`write_basic_xlsx(site_format=False)`).
**Fixed (owner feedback):** export no longer triggers Excel's repair dialog — the merge grid is
mechanically validated free of degenerate/duplicate/overlapping spans; DESCRIPTION now follows
exactly the parameters selected per category (UI selection order kept) with one column per selected parameter plus adaptive widths;
full thin-border box applied to band, data and TOTAL cells.
**Fixed (owner feedback round 3):** the site workbook now exports ONLY the
parameters the user selected in the UI — each detail sheet is `SNO` + one
column per selected parameter, with the automatic `SIZE (MM) L/B/D`,
`VOLUME`, `SHUTTERING` and `LEVEL` columns and the SUM totals row removed;
the front `Summary` is reduced to a simple per-category element-count cover
(`SNO | CATEGORY | ELEMENTS`) since no quantitative feed remains.
**Tested (harness):** full suite green — shuttering rules, dim fallbacks, level ordering,
param-driven description format, SUMIF criteria, merge-span integrity (zero bad spans),
bordered-grid styles and XML parts all pass; `script.py` compiles clean under CPython 3.12.
**Remaining:** live Revit confirmation on CP3123 (parameter-backed dims vs bbox fallback;
shuttering overlap handling at frame intersections), then tag `v1.4.0`.

### P3-02 — Configurable formwork rules + Include formwork toggle — **done** (`v1.8.2`)
**Built:** `formwork_rules` (enabled + per-category `deduction_pct` 0-100) persisted under
`settings["formwork"]`; `compute_shuttering_area(factor, enabled)` with `_safe_factor` clamping;
`normalize_formwork_rules` / `get_formwork_factor` / `is_formwork_enabled` helpers;
footer **"Include formwork"** checkbox wired at export/restore/save (restore mirrors the state
onto the checkbox). Harness: 11 new checks, `RESULT: all checks passed`.
**Fixed round 1 (owner feedback, `v1.8.1`):** the site detail sheets rendered no SHUTTERING column —
the SF round-3 redesign had removed all automatic columns. `build_site_detail_sheet` /
`write_site_xlsx` now take `include_formwork` and render an automatic **`SHUTTERING (SQM)`**
column (2-decimal figures from `Qty: Shuttering (m2)`, `shuttering_col` letter in meta) when the
checkbox is on; the export handler passes `is_formwork_enabled()`.
**Fixed round 2 (owner feedback, `v1.8.2`):** (a) checkbox read moved above `build_element_data()`
— rows were built against the stale flag, so the detail column rendered empty; (b) Summary sheet
now honours `include_formwork` too — off state drops the SHUTTERING (m2) column, its TOTAL SUM and
the caption tail, with 4-column meta and widths.
**Confirmed live (2026-09, owner):** both states verified end to end in Revit 2025 — checked →
SHUTTERING (SQM) values on detail sheets + summary; unchecked → column absent everywhere.
**Remaining (optional, non-blocking):** per-category percentage UI editor; geometric junction
analysis (current deduction is a configurable percentage, not intersection-aware). P3 is closed.

---

## Brand identity — `docs/reference/brand-guidelines.md` (applied 2026-08-27)

**Reference read & applied** to the code surface the guidelines actually reach:

- **Color — Ember accent replaces Revit blue.** The exported workbook's bold
  header fill is now `F2994A` (Ember 500), light band `FCE8D5` (Ember 100),
  sub-band `FFF0E3` — declared as `EMBER_500 / EMBER_100 / EMBER_200 /`
  `GRAY_TOTALS_FILL` constants beside the site-format style indexes. This
  follows the guideline literally: *"Don't use Revit's own blue as an accent."*
- **Typography — Segoe UI.** styles.xml fonts switched Calibri → **Segoe UI**
  (Windows-native, matches Revit exactly per §4.3).
- **Voice — outcome-led, friendly, plain.** Export success alert now leads
  with "Everything's exported — here's your workbook." (detail lines kept);
  the empty-workbook summary cell is one friendly line plus the next step,
  not an all-caps "NO DATA EXPORTED - ...".

**Tested (harness):** style assertions updated to the Ember fills and the full
suite is green (`RESULT: all checks passed`); `script.py` compiles clean.

**Toolkit naming:** **Nudge** is the active repository and Revit-tab name
(`Nudge.extension/Nudge.tab/...`). Older candidate-name wording in the brand brief is historical;
active project documentation follows the implemented Nudge layout.

### Brand UI system — shared theme resources + Brand Showcase — **confirmed live** (2026-08-28 code, 2026-08-31 owner QA)
**Built:** the guidelines became the actual UI surface — `lib/Resources/` carries
`Brand.Colors.Light/Dark.xaml` (Ember accent + Light/Dark surface neutrals + system colors),
`Brand.Typography.xaml` (Sora → Segoe UI fallback type scale) and `Brand.Controls.xaml` (buttons,
inputs, chips, containers); `lib/theme_manager.py` detects Revit's active Light/Dark theme
(guarded `UIThemeManager` → Windows app-theme registry → Light), merges the dictionaries into any
`forms.WPFWindow`, and supports force/toggle/auto-reapply with a `stop_watching` unsubscribe hook.
The new `Brand.panel ▶ BrandShowcase.pushbutton` previews every style and doubles as a Light/Dark
QA tool; handlers are wired explicitly in Python because XAML `Click=` does not bind on
dynamically-loaded XAML in pyRevit. Debug scaffolding (canary alert, TEST button, per-toggle
popup) removed.
**Confirmed live (2026-08-31).** Owner verified the toolkit UI on Revit 2025: windows open
styled, the toggle flips themes, the theme follows Revit.
**Fixed (owner feedback, 2026-08-28):** the toggle was dead in the opened window — pyRevit tears
the command scope down after the script returns, and a `show(modal=False)` window outlives it
(visible chrome, dead Python-side event wiring). `theme_manager` now provides an engine-persistent
holder (`keep_alive` / `release`); the showcase registers before showing, releases on close, keeps
strong references to all handlers, and reads `theme_manager` via `self._tm` so no handler depends
on the command scope.
**Engine reality check:** the window can only have opened via the IronPython `forms/_ipy.py`
backend — the installed pyRevit (master `6.5.3`) stubs `pyrevit.forms` for CPython
(`_cpy.py` → `PyRevitCPythonNotSupported`), so both UI buttons effectively run IP27 today. The
CP3123-only decision (T-03) needs a CPython-capable `pyrevit.forms` on the installed build before
it can become real.
**Next step — applied (2026-08-29, code v1.4.2, live QA pending):** the BOQ Parameter Manager
dialog (`Generate.panel/BOQ.pushbutton/ui.xaml`) now consumes the same dictionaries — `ui.xaml`
restyled via `DynamicResource` brand keys (surfaces, type scale, inputs, outline buttons + the
Ember primary Export, brand list/footer brushes) and `script.py` calls
`theme_manager.apply_theme(window)` right after building the window (guarded; the dialog is
modal, so no `keep_alive` is needed) with a `watch_theme_changes` + `Closed` → `stop_watching`
pair. **Confirmed live (2026-08-31):** dialog opens styled, both themes readable, export
unchanged.

---

## P1 — Structural Quantity Engine (completed)

### P1-01 — Extend quantity engine per category — **done** (`v1.1.0`)
**Goal:** Keep the existing dependency-free engine and extend it per category — Beam (Volume, Area,
Length, Count), Column (Volume, Area, Height/Length, Count), Slab (Volume, Area, Thickness, Count),
Foundation (Volume, Area, Thickness/Count).
**Notes:** distinguishes **Parameter Quantity** (Height/Thickness, read by name) vs **Calculated
Quantity** (Volume/Area/Length); never creates a duplicate engine.
**What landed (first increment, code v1.1.0):** `get_element_quantities(element, element_name)` is
category-aware; adds `Qty: Height (m)` for Column, `Qty: Thickness (m)` for Slab/Foundation (pruned
if absent), and `Qty: Count` (=1/row, TOTAL sums to count). Harness asserts Count + Height +
Thickness columns.
**Confirmed live (`v1.1.0`).** Owner verified real Height/Thickness/Count values in Revit 2025;
tagged `v1.1.0`.

### P1-02 — Element Count column — **done** (`v1.1.0`) — implemented in P1-01
**Built** as part of `get_element_quantities`: `Qty: Count` = 1 per element row; the sheet TOTAL row
sums to the element count, and the BOQ Summary already reports the per-category count in its
`Elements` column. **Tested (harness):** asserts a Count quantity column on each populated sheet.
**Remaining:** live Revit confirmation with P1-01.

---

## Open queue (cross-cutting, draft)

### T-04 — Configuration schema / engineering notes doc — `draft`
**State:** Settings live in `.rcc_boq_settings.json` and are documented only implicitly.
**Plan:** add a short config reference (keys, defaults, how to reset) near the docs.

### T-05 — Category registry — `draft`
**State:** The fifth Structure Wall category is integrated, but category definitions and XAML tabs
remain hard-coded in several coordinated locations.
**Plan:** before adding a sixth category, design one registry for collection, UI metadata, settings
and export ordering; do not refactor the now live-proven five-category path without dedicated tests.

### T-06 — Rate database (supersedes the simple rate parameter) — `draft`
**State:** Rates come from a single recognized parameter.
**Plan:** becomes Phase 12 (P12) work; keep current behaviour until then.

---

## Rule for the agent

Never mark an engine change `done` without running `python test_xlsx_writer.py`. Never mark any
live-Revit item `done` yourself — that is the project owner's confirmation. Work one roadmap phase
at a time; do not jump to P4+ (rebar / BBS / rate analysis) before P1–P3 are stable in Revit.

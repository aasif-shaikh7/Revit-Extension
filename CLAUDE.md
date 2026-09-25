# CLAUDE.md

**Document:** `CLAUDE.md`
**Status:** Active — condensed operating brief for AI coding agents

Guidance for Claude Code and other AI coding agents working in this repository.

---

## 1. What this repository currently is

**Revit-Extension** — a **pyRevit** extension that generates **RCC (Reinforced Cement Concrete) BOQ**
workbooks from Autodesk Revit.

**Target env:** Revit **2025+**, pyRevit **6.10.0+**.

**Runtime — read this before reasoning about engine behaviour.** The BOQ button actually runs on
**IronPython 2.7.12 (IP27)**, because `script.py` carries **no `#! python3` line**: without that
first line pyRevit picks its default engine, and the default is IronPython. Confirmed on
2026-09-22 and again on 2026-09-24 — the crash trail's first line prints the live engine
(`engine 2.7.12`). Consequences that have already cost real time:

- IronPython does not enforce `sys.recursionlimit`. Deep recursion is a **hard process crash**
  (`0xc00000fd`, no Python traceback) rather than a `RecursionError`, and it takes Revit with it.
  A BBS export died this way until the workbook writers were moved onto a 64 MB-stack thread
  (`lib/stack_runner.py`).
- The engine is reused between button presses, so module state in `sys.modules` and `+=` event
  subscriptions survive.
- `float(None)` raises **`SystemError`** ("Object reference not set to an instance of an
  object"), not `TypeError`, so `except (TypeError, ValueError)` does not catch it, and a
  **dict does not keep insertion order**. Both shipped in `v1.35.0` with a green harness and
  were found only by a live export (`v1.35.1`). Anything order-sensitive reads a list; a `try`
  around `float()` catches `Exception` - the harness enforces that since `v1.35.2`
  (`float([])` raises `AttributeError` there, too).
- If `script.py` does not compile, pyRevit shows an error window titled `BOQ` and every queued
  bridge export waits forever. The harness now compiles every file whole.

The **engines in `lib/` are CPython-clean**: 19 of the 22 import and write a workbook on
CP3123 (measured 2026-09-24); `revision_engine.py` (v1.35.0), `header_colour.py` (v1.36.0) and
`model_change_engine.py` (v1.40.0) have so far only been measured on Python 3.12.10 in the
harness (the last also on IronPython 2.7.12). Only `script.py`'s pyRevit/WPF layer holds the tool on IP27. Moving the
button to CP3123 is a deliberate, separately verified change, not a one-line edit.

**Current state: one working tool pushbutton plus brand infrastructure.**
`Nudge.extension/Nudge.tab/Generate.panel/BOQ.pushbutton`
contains `script.py` (the Revit/UI orchestration), `ui.xaml` (the WPF dialog) and `icon.png`. It opens the RCC
BOQ Parameter Manager for Beam/Column/Structure Wall/Slab/Foundation/Rebar, discovers real parameters, classifies slab/
foundation subtypes, collects concrete/formwork/rebar quantities, and writes a dependency-free XLSX workbook.
The dialog has **eleven tabs**: the six categories plus Assembly Profile, Site Items, Rate
Analysis, Rate Database and Revision. The workbook carries, as the data allows: one sheet per category, Rebar Summary,
Rebar BBS, Structural Assembly, Rate Analysis, Rate Database, BOQ Summary, BOQ by Level, BOQ by
Grade, Concrete Summary, Formwork Summary, Detailed BOQ, BOQ Revision, Model Changes, Site Items,
Unmapped Elements and Costing.
`Nudge.extension/lib/` contains the split pure-Python engines and
the shared brand/theme system
(`theme_manager.py` + `lib/Resources/*.xaml` resource dictionaries), previewed live by the
`Nudge.tab/Brand.panel/BrandShowcase.pushbutton` QA window.

What exists:

- One extension: the BOQ tool pushbutton, a Brand Showcase pushbutton (theme QA), and a shared
  `lib/` (22 engine modules, 5 dialog-tab modules + brand resource dictionaries + theme
  manager). No CI.
- `RccBoq.RestBridge/` — the .NET Agent Bridge add-in and gateway that lets an agent read the live
  document and run a headless export, and `scripts/rcc_boq_rest_client.py`, its client.
- Pure-Python dependency-free engines under `Nudge.extension/lib/`, deliberately free of Revit
  symbols so they can be tested outside Revit.
- A standalone regression harness, `test_xlsx_writer.py`, that extracts production functions from
  `lib/` and the Revit-bound classifier from `script.py`, then validates workbooks and routing.

What an agent can actually verify here:

```bash
python test_xlsx_writer.py     # pure Python, ~1 s; prints "RESULT: all N checks passed"
python test_rest_api.py        # the bridge's own Python-side checks
powershell -File scripts\ip27_compile.ps1   # every file compiled on IronPython 2.7.12
```

The harness prints its own count, so quote that number rather than a hand-maintained one. The
`.NET` bridge has `dotnet` tests as well (see `README.md`).

The harness runs in any Python 3.x, no Revit or SDK needed. Nothing else in this repository can be
executed without a live Revit session (which is not available to the agent). `test_xlsx_writer.py`
proves the XLSX engine; it says nothing about in-Revit behavior, so never claim a live Revit feature
as verified when only the harness ran.

The pure-Python engine intentionally matches a Kotlin-JVM philosophy: **the importable/unit-testable
part must not depend on the host** — XLSX functions stay extractable, Revit-bound code stays
elsewhere in `script.py`. Do not drag Revit or pyRevit symbols into the engine, and do not add
third-party packages (`openpyxl`, pandas, etc.) to it.

`docs/reference/` holds the older Kestrel (Android) documentation moved from the root. It is
reference only and does not describe this extension.

---

## 2. Documentation map — who is authoritative for what

| File | What it is |
| --- | --- |
| `README.md` | Overview, status, usage, install |
| `PRD.md` | What is being built and scope |
| `PROJECT_STRUCTURE.md` | Canonical folder/dependency rules |
| `AI_DEVELOPMENT_GUIDE.md` | Rules for AI-assisted implementation |
| `test_xlsx_writer.py` | The runnable regression harness |
| `CHANGELOG.md` | What has actually been established, by build/commit |
| `done-list.md` / `todo-list.md` | Finished work vs the open queue |
| `brand-guidelines.md` | The brand/theme reference for the dialog and the workbook |
| `RccBoq.RestBridge/` + `scripts/` | The Agent Bridge add-in, gateway and its Python client |
| `docs/reference/` | Older Kestrel docs, historical only |

---

## 3. Key files and what they do

`Nudge.extension/Nudge.tab/Generate.panel/BOQ.pushbutton/`:

- `script.py` — Revit imports/state, selection, safe parameter readers, category definitions,
  structural-wall filtering, the centralized Slab/Foundation classifier/audit, and XAML wiring/main entry.
- `ui.xaml` — WPF window: header, per-category tabs, search, Available/Selected box, Add/Remove,
  filters, status, OK/Export/Close.
- `icon.png` — button icon.

The main element sheets come from `CATEGORY_INFO` (Beam→`OST_StructuralFraming`,
Column→`OST_StructuralColumns`, Structure Wall→structural-only `OST_Walls`, Slab→`OST_Floors`,
Foundation→`OST_StructuralFoundation`), plus a
single logical classifier for slab/foundation subtypes. Both Floor and Structural Foundation raw
collections can route to either logical sheet; code `v1.8.10` audits counts and duplicate IDs before
export. Structure Wall uses Length/Height/Thickness and gross `2LH` shuttering. Rebar
(`OST_Rebar`) is the sixth category: detail rows plus `d²/162` steel weight through
`lib/rebar_engine.py`. The dependency-free engines live in `lib/`; the newest of them are
`rate_database_engine.py` (P12 rates by code, place and date), `revision_engine.py` (P14: the
snapshot behind each issue, and the comparison between two), `stack_runner.py` (runs the
workbook writers on a big-stack thread) and `crash_trail.py` (one flushed line per step, so a
hard crash names its step).

---

## 4. Verification rules that matter here

- **`python test_xlsx_writer.py`** validates the engine. If it fails, the engine is broken — fix it.
- **Never propagate a false "tested"** — state whether you verified the engine (harness) versus the
  live Revit UI (not verifiable by an agent).
- **`CHANGELOG.md`** is the record and must be updated in the same change it describes.
- **Source of truth is the code.** `script.py`, `ui.xaml` and `test_xlsx_writer.py` beat any prompt
  or roadmap. Read all three completely before writing code; never invent or remove functionality.
- **Roadmap phases in `PRD.md` §12, live status in `todo-list.md`.** P1-P13 have shipped; P12's
  engine, tab, sheet and BOQ pricing are in, waiting only on the owner's real rates. **P14** is done
  (`v1.35.0`-`v1.37.0`: engine, snapshots, both workbook sheets, the Revision tab); **P15**'s Model
  Changes sheet shipped in `v1.40.0`. The open phases are **P8** (keep splitting `script.py`) and
  **P16** (dashboard). Work one at a time, and
  check `todo-list.md` rather than any older "next phase" sentence.

---

## 5. Rules specific to AI agents

These come from `AI_DEVELOPMENT_GUIDE.md`.

- **Never fabricate an API.** No invented Revit, pyRevit, WPF, or Python members; guard real ones.
- **Never fake results.** "Should work" is not "tested." Use `Unverified` / `Experimental` /
  `Tested` / `Supported`.
- **Inspect before editing.** Read the existing script, XAML, and harness first.
- **Smallest reasonable change.** Keep the engine dependency-free; no unrelated reformatting.
- **Report engine-specific facts** for Revit claims (Revit version, IP27 - the live engine - vs
  CP3123, guarded/fallback).
- **Say when uncertain.**

### Task format worth requesting or restating

```
Goal / Context / Relevant files / Requirements / Constraints /
Do not change / Tests / Acceptance criteria
```

### End-of-task report

```
Implemented:
Files changed:
Tests added:
Tests run:
Known limitations:
```

State plainly when something could not be run. In this repository, "Tests run: engine harness only —
no live Revit session" is the correct and honest answer.

---

## 6. Principle

> **Use AI to increase development speed, not to reduce engineering discipline.**

The project owner remains responsible for product decisions, review, live-Revit testing, and release
readiness.

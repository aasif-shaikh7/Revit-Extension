# CLAUDE.md

**Document:** `CLAUDE.md`
**Status:** Active — condensed operating brief for AI coding agents

Guidance for Claude Code and other AI coding agents working in this repository.

---

## 1. What this repository currently is

**Revit-Extension** — a **pyRevit** extension that generates **RCC (Reinforced Cement Concrete) BOQ**
workbooks from Autodesk Revit.

**Target env:** Revit **2025+**; pyRevit **6.10.0+**, running on either the **CP3123** (CPython
3.12.3) or **IP27** (IronPython 2.7) engine.

**Current state: one working pushbutton.** `Aasif.extension/Aasif.tab/Generate.panel/BOQ.pushbutton`
contains `script.py` (the whole tool), `ui.xaml` (the WPF dialog) and `icon.png`. It opens the RCC
BOQ Parameter Manager for Beam/Column/Slab/Foundation, discovers real parameters, classifies slab/
foundation subtypes, collects metric quantities, and writes a dependency-free XLSX workbook with a
BOQ Summary and a Costing sheet.

What exists:

- One extension, one pushbutton. No CI, no other modules.
- A pure-Python, dependency-free XLSX engine inside `script.py`, deliberately free of Revit symbols
  so it can be tested outside Revit.
- A standalone regression harness, `test_xlsx_writer.py`, that extracts the engine's source from the
  real `script.py`, builds a workbook, unzips it, and XML-validates it.

What an agent can actually verify here:

```bash
python test_xlsx_writer.py     # pure Python; the only runnable check in this repo
```

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
| `docs/reference/` | Older Kestrel docs, historical only |

---

## 3. Key files and what they do

`Aasif.extension/Aasif.tab/Generate.panel/BOQ.pushbutton/`:

- `script.py` — imports, global state, selection, settings JSON, safe parameter readers, quantity
  takeoff, the pure-Python XLSX engine, category definitions, classification/filters, and the XAML
  wiring/main entry.
- `ui.xaml` — WPF window: header, per-category tabs, search, Available/Selected box, Add/Remove,
  filters, status, OK/Export/Close.
- `icon.png` — button icon.

The main element sheets come from `CATEGORY_INFO` (Beam→`OST_StructuralFraming`,
Column→`OST_StructuralColumns`, Slab→`OST_Floors`, Foundation→`OST_StructuralFoundation`), plus a
logical classifier for slab/foundation subtypes.

---

## 4. Verification rules that matter here

- **`python test_xlsx_writer.py`** validates the engine. If it fails, the engine is broken — fix it.
- **Never propagate a false "tested"** — state whether you verified the engine (harness) versus the
  live Revit UI (not verifiable by an agent).
- **`CHANGELOG.md`** is the record and must be updated in the same change it describes.
- **Source of truth is the code.** `script.py`, `ui.xaml` and `test_xlsx_writer.py` beat any prompt
  or roadmap. Read all three completely before writing code; never invent or remove functionality.
- **Roadmap phases in `PRD.md` §12.** Work one phase at a time (P1 quantity engine first). Do not
  jump to rebar / BBS / rate analysis before earlier phases are stable in a live Revit 2025 project.

---

## 5. Rules specific to AI agents

These come from `AI_DEVELOPMENT_GUIDE.md`.

- **Never fabricate an API.** No invented Revit, pyRevit, WPF, or Python members; guard real ones.
- **Never fake results.** "Should work" is not "tested." Use `Unverified` / `Experimental` /
  `Tested` / `Supported`.
- **Inspect before editing.** Read the existing script, XAML, and harness first.
- **Smallest reasonable change.** Keep the engine dependency-free; no unrelated reformatting.
- **Report engine-specific facts** for Revit claims (version, CP3123 vs IP27, guarded/fallback).
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
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
| P0 | Live-Revit confirmation of the current dialog | — | `testing` (owner) |
| P1 | Structural Quantity Engine (extend, don't duplicate) | 5/5/3/4 | `next` |
| P2 | Structural BOQ Grouping (level / material / concrete grade) | 4/4/2/5 | `todo` |
| P3 | Formwork Engine (configurable rules) | 5/5/3/4 | `todo` |
| P4 | Rebar Quantity Engine | 5/5/3/3 | `todo` |
| P5 | Rebar Diameter Summary + BBS | 4/5/5/2 | `todo` |
| P6 | Structural BOQ Assembly (concrete/rebar/formwork/wire/blocks/labour) | 4/5/4/3 | `todo` |
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

---

## P0 — Confirm the current dialog in Revit 2025 (before any new phase)

### T-01 — Confirm live-Revit behavior of the dialog — `testing`
**State:** The dialog, filters, selection, export scope, **parameter ordering (Up/Down/Top/Bottom)**,
and settings persistence are implemented but the **live Revit 2025+** behavior is `Unverified` by an
agent.
**Acceptance:** Project owner opens BOQ in a real RCC model (Beam/Column/Slab/Foundation), picks
parameters, reorders with Up/Down/Top/Bottom, sets filters, and exports; confirms parameters load,
classification is correct, **selected order is preserved in Excel**, and the workbook matches
expectations. Record the outcome (both CP3123 and IP27, and Revit version) in `done-list.md`.

### T-02 — Quantity accuracy on real materials — `testing`
**State:** Metric conversion logic is deterministic and harness-tested with sample data, but true
`Qty: Volume/Area/Length` values on actual Revit elements are **Unverified**.
**Acceptance:** compare at least one beam/column/slab/foundation quantity against a known-correct
value in Revit; record any engine adjustments.

### T-03 — Dual-engine parity (CP3123 and IP27) — `pending`
**State:** Target environments explicitly include both engines, but neither has been exercised here.
**Acceptance:** run the export end-to-end once per engine on the same model and record differences in
`CHANGELOG.md`.

---

## P1 — Structural Quantity Engine (next phase)

### P1-01 — Extend quantity engine per category — `todo`
**Goal:** Keep the existing dependency-free engine and extend it per category — Beam (Volume, Area,
Length, Count, dimensions where available), Column (Volume, Area, Height/Length, Count), Slab
(Volume, Area, Thickness, Count), Foundation (Volume, Area, Dimensions, Count).
**Notes:** distinguish **Parameter Quantity** vs **Calculated Quantity** where necessary; never
create a duplicate engine.
**Acceptance:** pure-Python engine functions extended + `test_xlsx_writer.py` updated; live-Revit
confirmation by the owner before P1 is closed.

### P1-02 — Element Count column — `todo`
**Goal:** add a per-category element **Count** usable by grouping (P2) and summaries.
**Acceptance:** harness asserts a Count quantity column on each populated sheet.

---

## Open queue (cross-cutting, draft)

### T-04 — Configuration schema / engineering notes doc — `draft`
**State:** Settings live in `.rcc_boq_settings.json` and are documented only implicitly.
**Plan:** add a short config reference (keys, defaults, how to reset) near the docs.

### T-05 — Category registry — `draft`
**State:** The four categories are hard-coded tabs.
**Plan:** decide only when a fifth category is actually requested.

### T-06 — Rate database (supersedes the simple rate parameter) — `draft`
**State:** Rates come from a single recognized parameter.
**Plan:** becomes Phase 12 (P12) work; keep current behaviour until then.

---

## Rule for the agent

Never mark an engine change `done` without running `python test_xlsx_writer.py`. Never mark any
live-Revit item `done` yourself — that is the project owner's confirmation. Work one roadmap phase
at a time; do not jump to P4+ (rebar / BBS / rate analysis) before P1–P3 are stable in Revit.
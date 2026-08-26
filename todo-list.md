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

An agent can move only the **engine-side** items toward `done` by running `test_xlsx_writer.py`.
Everything about the live Revit dialog stops at `testing` until the project owner runs it in Revit
2025+ on a real project.

**Verification states used:** `Unverified`, `Experimental`, `Tested (harness)`, `Tested (live)`,
`Supported`.

---

## Open queue

### T-01 — Confirm live-Revit behavior of the dialog — `testing`
**State:** The dialog, filters, selection, export scope, and settings persistence are implemented but
the **live Revit 2025+** behavior is `Unverified` by an agent.
**Acceptance:** Project owner opens BOQ in a real RCC model (Beam/Column/Slab/Foundation), picks
parameters, filters, and exports; confirms parameters load, classification/subtype filters are
correct, and the workbook matches the screen expectations. Record the outcome (both CP3123 and IP27,
and Revit version) in `done-list.md`.

### T-02 — Quantity accuracy on real materials — `testing`
**State:** Metric conversion logic is deterministic and harness-tested with sample data, but true
`Qty: Volume/Area/Length` values on actual Revit elements are **Unverified**.
**Acceptance:** compare at least one beam/column/slab/foundation quantity against a known-correct
value in Revit; record any engine adjustments.

### T-03 — Dual-engine parity (CP3123 and IP27) — `pending`
**State:** Target environments explicitly include both engines, but neither has been exercised here.
**Acceptance:** run the export end-to-end once per engine on the same model and record differences in
`CHANGELOG.md`.

### T-04 — Configuration schema / engineering notes doc — `draft`
**State:** There is no dedicated config/schema note yet; settings live in
`.rcc_boq_settings.json` and are documented only implicitly.
**Plan:** add a short config reference (keys, defaults, hot to reset) near the docs.

### T-05 — Category registry — `draft`
**State:** The four categories are hard-coded tabs. Widening the tool needs a data-driven category
registry.
**Plan:** decide only when a fifth category is actually requested.

### T-06 — Live BOM/costing rate tables — `draft`
**State:** Rates come from a single recognized parameter; there is no rate database.
**Plan:** keep it this way until a user asks for a maintained rate table; then add a design note.

---

## Rule for the agent

Never mark an engine change `done` without running `python test_xlsx_writer.py`. Never mark any
live-Revit item `done` yourself — that is the project owner's confirmation.
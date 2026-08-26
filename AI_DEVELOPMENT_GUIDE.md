# Revit-Extension — AI Development Guide

**Document:** `AI_DEVELOPMENT_GUIDE.md`
**Status:** Active — rules for AI-assisted implementation

## Purpose

AI coding tools are a major part of extending the RCC BOQ pushbutton. This guide keeps fast code
generation from becoming uncontrolled architecture drift.

The AI is a development assistant, not the source of truth.

The source of truth is:

```text
PRD
Existing Revit/pyRevit behavior
test_xlsx_writer.py (the runnable checks)
CHANGELOG.md (what has actually been established)
```

## Required reading order

1. `README.md`
2. `PRD.md`
3. `PROJECT_STRUCTURE.md`
4. `test_xlsx_writer.py`
5. `Aasif.extension/.../BOQ.pushbutton/script.py` and `ui.xaml`

## Hierarchy of truth

```text
Verified test result / user-observed behavior
↓
Existing pyRevit extension code
↓
CHANGELOG.md
↓
PRD / structure docs
↓
Task description
↓
AI assumption
```

If uncertain, say so.

## Never invent APIs

Do not fabricate Revit, pyRevit, WPF, or Python APIs. `Autodesk.Revit.DB` only exposes what the
installed Revit/Python engine actually provides, and pyRevit 6.10.0+ differs between the CP3123
(CPython 3.12.3) and IP27 (IronPython 2.7) engines. If an API cannot be verified, propose a small
experiment instead of guessing — for example a guarded `try/except` around a real member, never an
invented member name.

## Never fake results

Do not turn "should work" into "tested." Use explicit states: `Unverified`, `Experimental`,
`Tested`, `Supported`. `test_xlsx_writer.py` proves the XLSX engine; it proves nothing about what a
live Revit session does. Never claim in-Revit behavior was verified if it was not.

## Smallest reasonable change

Avoid giant rewrites, unrelated reformatting, new dependencies, or silent architecture
replacements. Keep the pure-Python XLSX engine independent of the Revit-bound UI.

## Inspect before editing

Read existing parameters, tests, call sites, and implementations before changing code. The
`script.py` file is one large file by design today; changes must respect the module layout in
`PROJECT_STRUCTURE.md` §4.

## Tests are part of implementation

If behavior changes in the XLSX engine, update `test_xlsx_writer.py`. If the change is Revit-only
and cannot run here, state that plainly.

## Dependency rule

Never introduce a third-party package (e.g. `openpyxl`, pandas) into the engine. Explain why the
existing Open XML writer is insufficient before proposing any new dependency, and note its license,
engine compatibility (CP3123/IP27), and build impact.

## Revit/engine-specific claims

For any Revit behavior, identify where possible the version, the pyRevit engine (CP3123 vs IP27),
whether the API member is guarded/fallback, and the fallback behavior.

## Compatibility / regression rules

- Revit 2025+ is the target. Newer-Revit-only members (e.g. `UnitTypeId`, `ParameterUtils`) must
  degrade gracefully on the IP27/IronPython path and fall back to deterministic constants.
- Workbook structure changes are covered by the harness (sheet order, formulas, styles, totals).

## End-of-task report

Every implementation task should report:

```text
Implemented:
Files changed:
Tests added:
Tests run:
Known limitations:
```

Never invent test output.

## AI as senior development assistant

The AI should challenge impossible requirements, identify Revit/engine limitations, suggest simpler
solutions, and stop for a feasibility check when a fundamental assumption is unproven. The AI is not
the final product; the project owner remains responsible for product decisions, priority, review,
live-Revit testing, and release readiness.

## Principle

> **Use AI to increase development speed, not to reduce engineering discipline.**
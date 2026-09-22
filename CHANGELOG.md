# Changelog

**Document:** `CHANGELOG.md`
**Status:** Active — records only what has actually been established

All notable changes to the Revit-Extension (RCC BOQ) will be documented in this file.

The extension uses **semantic versioning** (`MAJOR.MINOR.PATCH`, see `PROJECT_STRUCTURE.md`
§Versioning). This changelog records only what has actually been established — commits in git and,
where applicable, what the XLSX harness verifies.

The format is inspired by [Keep a Changelog](https://keepachangelog.com/). Development history that
predates the first semantic release is recorded under "Established so far" and retrospectively
tagged `v0.x`.

**Verification vocabulary** used in this file:
- **Tested** — verified by `python test_xlsx_writer.py` (engine) when labelled `(harness)`.
- **Unverified** — present in code but not run in a live Revit session by an agent; the project
  owner confirms in-Revit behavior on a real project.

Nothing below claims a live Revit feature was verified by an agent when only the harness ran.

---

## [v1.31.0] - 2026-09-22

### Added (P12 second slice: Rate Database tab and sheet)
- **Rate Database tab** in the BOQ dialog, after Rate Analysis. It has fields for Item Code, Unit,
  Rate, Description, Location, Currency, Effective Date, Vendor and Source, a list of rates, and
  Add / Update selected / Remove selected / Clear fields.
- **This project's location** field (for example `Navsari, Gujarat, India` or `Dubai, UAE`),
  saved **per project** so one rate database serves jobs in different cities and countries.
- **The tab refuses** a rate with no item code, a Rate that is not a number of zero or more, an
  Effective Date that is not `YYYY-MM-DD`, and a second rate for the same code, location and date,
  on both Add and Update. A blank Rate is allowed and shows as needing input.
- **Summary line:** counts ready rates, samples and rates needing input.
- **Rate Database sheet** in both workbook formats (after Rate Analysis, in the site bands for the
  site format), with a status on every row. It appears only when rates exist, so a project without
  rates keeps its familiar workbook.
- **Headless exports are guarded:** saving the rates and the location is guarded by
  `rate_db_ready`, as P11 is, so an export that never showed the tab cannot erase them.
- `get_project_location` / `set_project_location` in `lib/rate_database_engine.py`.

### Verified
- Harness: `python test_xlsx_writer.py` passes **350 checks**, up from 340. The new checks cover:
  - every control exists once and every handler is wired;
  - the four refusals on Add and Update;
  - the headless guard and the per-project location;
  - both writers actually run and write the sheet only when rates exist.
- `ui.xaml` loads with WPF's own `XamlReader` outside Revit, and every new control is found by name.
- **Not yet verified in Revit:** the tab has not been used in a live Revit session yet.

---

## [v1.30.0] - 2026-09-22

### Added (P12 first slice: the rate database engine)
- New pure-Python engine `lib/rate_database_engine.py`. A rate entry has the PRD fields: Item Code,
  Description, Unit, Rate, Currency, Location, Vendor and Effective Date, plus a Source.
- **Lookup (`find_rate`):** answers "what is the rate for this item, here, on this day?":
  - the latest rate in force on the day wins, and a rate dated later is not used yet;
  - **any city, state or country:** the job location is searched level by level, most
    specific first. For `Navsari, Gujarat, India`: a Navsari rate, else Gujarat, else India, else
    the general rate. A job in `Dubai, UAE` picks up a `UAE` rate in AED. A state or country rate
    reaches every city under it, and a sibling city's rate (Surat for a Navsari job) is never
    borrowed;
  - two rates with the same code, location and date are a conflict and price nothing.
- **Rules:**
  - A rate must be a non-negative number. Blank, text, boolean and NaN are refused, not read as
    zero.
  - Dates must be `YYYY-MM-DD`, since `01/09/2026` reads two ways. An unreadable date is kept as
    typed and flagged, and it blocks that rate.
- **Samples are labelled:** a Source containing "SAMPLE" shows as "Sample - not a real rate".
- **Store and sheet:**
  - `load_rate_database` / `save_rate_database` use the settings key `rate_database`. Only the
    declared fields are saved, and a corrupt store loads as empty.
  - `build_rate_database_sheet` builds the Rate Database table, with a status on every row.
  - `find_rate_entry_conflict` is for the dialog to refuse a duplicate.
- **No rate lives in the engine.** The sample figures are in the harness fixture only. The owner has
  no real rates yet, and they go in later without a code change.

### Verified (harness only - nothing is wired into Revit yet)
- `python test_xlsx_writer.py`: **340 checks pass**, up from 327, with 13 new P12 checks.
- A mutation run broke the engine eight ways, and the harness catches every one: ignoring the date
  cutoff, borrowing another location's rate, skipping the state/country levels, trying the general
  rate before the city, picking one of two clashing rates, accepting a negative rate,
  case-sensitive codes, and a sample shown as ready.

### Not yet
- The Rate Database sheet in the workbook, the dialog tab, and the Detailed BOQ Rate column filled
  from the database are the next slices. There is no live Revit check for this slice, because
  nothing in Revit calls the engine yet.

---

## [v1.29.1] - 2026-09-22

### Fixed
- The site workbook's **Structural Assembly** sheet showed the band "RCC - REINFORCEMENT BBS"
  because it fell back to the BBS default of `build_site_tabular_sheet`. It now passes its own
  band, **"RCC - STRUCTURAL ASSEMBLY"**. Rebar Summary and Rebar BBS keep the BBS band.

### Verified
- Harness: `python test_xlsx_writer.py` passes **327 checks**, up from 326. The new check pins the
  Structural Assembly band and confirms the BBS sheet still has its own.
- Live, in the owner's own Revit 2025 on UMA NIWAS (Primary bridge, consent given): the site export
  gave 10 sheets, 13,256 cells and 0 mismatches, and row 2 of Structural Assembly reads
  "RCC - STRUCTURAL ASSEMBLY". The P13 sheets are unchanged: 873.6960 m3 and 6,563.07 m2, no
  problems. Nothing was saved.

---

## [v1.29.0] - 2026-09-22

### Added (P13 site format: the three BOQ sheets in the site workbook)
- The **site-format** workbook now carries **Concrete Summary**, **Formwork Summary** and
  **Detailed BOQ** after Structural Assembly, in the site title bands (project, band, title,
  header). The Detailed BOQ description column is widened for the item text.
- The site title bands push every data row five rows down, so the builders take a `row_offset`:
  each Amount `IF(E{r}="","",D{r}*E{r})`, each row total and every TOTAL `SUM` points at the row it
  actually lands on inside the bands.
- The site element sheets carry no Volume or Grade column for a `SUMIF` to read, so in the site
  workbook the concrete cells are the rounded sums of the element rows (`_concrete_quantity`); the
  classic workbook keeps its live `SUMIF`s. Row and column totals and Amounts stay live in both.

### Verified (harness)
- `python test_xlsx_writer.py`: **326 checks pass**, up from 323. The site sheets are **evaluated**
  inside their bands against the same figures as the classic sheets, and every site Amount and
  TOTAL is checked against the row it lands on. With the offset deliberately set to 0 the three new
  checks fail, so they do catch a formula aimed at a band row.

### Verified (live, owner's model, isolated second Revit window)
- A copy of `R25-UMA NIWAS BUILDING-ST-31-08-2026 - DUPLICATES REMOVED` exported in the **site
  format** from a test Revit on the Secondary bridge: **10 sheets, 13,256 cells, zero mismatches**.
- Every formula in the three sheets was evaluated by its real cell address:
  - **Concrete Summary:** M10 22.8123, M30 454.7580, M40 396.1257, total **873.6960 m3**, and
    every category column matches the site Structural Assembly.
  - **Formwork Summary:** 12 levels, every level x category cell matches the classic export of the
    same model to the centimetre, total **6,563.07 m2**.
  - **Detailed BOQ:** items A.1-A.7 and B.1-B.5 on rows 8-20. Every Amount points at its own row,
    the TOTAL is `SUM(F8:F20)`, and the concrete and shuttering equal the two summaries.

### Verified (live, owner's own Revit, after the merge)
- The owner opened `R25-UMA NIWAS BUILDING-ST-31-08-2026 - DUPLICATES REMOVED` in their own Revit
  2025 and gave consent; the agent ran the site export on the Primary bridge: **10 sheets, 13,256
  cells, zero mismatches**, nothing saved. The same evaluation of every formula in the three
  sheets found no problems, and every figure equals the second-window run above (873.6960 m3,
  6,563.07 m2).

---

## [v1.28.0] - 2026-09-22

### Added (P13 second slice: Concrete Summary and Formwork Summary)
- **Concrete Summary** - one row per grade (M10, M30, M40 ... in number order, an unrecorded grade
  last), one column per category, a Total (m3) per grade and a TOTAL row: how much of each grade
  the project needs, which is what RMC is ordered by. Every cell is the same live `SUMIF` BOQ by
  Grade and the Detailed BOQ use, so the three always agree; row and column totals are live `SUM`s.
- **Formwork Summary** - one row per level in level order, one column per category, a Total (m2)
  per level and a TOTAL row: the floor-by-floor shuttering a site plans against. The classic
  element sheets carry no shuttering column, so the level figures are summed from the rows, as
  Structural Assembly and the Detailed BOQ do; the totals are live.
- Both sit with the other summaries, just before the Detailed BOQ, and appear only when there is
  concrete or shuttering to summarize.

### Verified (harness)
- `python test_xlsx_writer.py`: **323 checks pass**, up from 318. Both sheets are **evaluated**,
  not read - every `SUMIF` and every row and column `SUM` - and compared with sums taken straight
  from the fixture; the Concrete Summary TOTAL is also checked against the Detailed BOQ's concrete.
  The harness evaluator now handles row sums across columns as well as column sums.

### Verified (live, owner's model, isolated second Revit window)
- A copy of `R25-UMA NIWAS BUILDING-ST-31-08-2026 - DUPLICATES REMOVED` exported from a test Revit
  on the Secondary bridge: **14 sheets, 18,805 cells, zero mismatches**.
- **Concrete Summary:** M10 22.81, M30 454.76, M40 396.13 m3; every cell matched a direct recount
  from the element sheets, and the grand total **873.6960 m3** equals every element volume in the
  workbook. No beam appears under M40 - the three plinth `MB` beams the owner moved to M30 today.
- **Formwork Summary:** 12 levels in order, `01 FOUNDATION LEVEL` to `13 OHW/LMR LEVEL`; every
  category total matched the Structural Assembly sheet to the centimetre, grand total
  **6,563.07 m2**.

---

## [v1.27.0] - 2026-09-22

### Added (P13 first slice: the Detailed BOQ sheet)
- The classic workbook gains a **Detailed BOQ** - the itemized schedule a client or contractor
  prices: `Item No. | Description | Unit | Quantity | Rate | Amount`, in three sections and a
  TOTAL:
  - **A. Concrete** - one item per category and grade present (`Concrete M30 in Beams`), grades
    in number order. An element with no recorded grade is itemized, not dropped
    (`Concrete in Beams - grade not recorded`), and goes last where it will be noticed rather than
    priced.
  - **B. Centering and shuttering** - one item per category.
  - **C. Reinforcement** - one item per diameter (`Reinforcement steel, 12 mm dia`), in kg.
- **Concrete quantities are live `SUMIF` formulas** against the category sheets, built the way
  BOQ by Grade is, so an edit to an element sheet flows through.
- **Rate is left blank and Amount is a live formula** - blank until a rate is typed, then
  Quantity x Rate - so the sheet can be priced in Excel without touching a formula. No rate is
  invented; P11/P12 own rates.
- Reinforcement reuses `build_rebar_diameter_summary_table`, the source of the Rebar Summary
  sheet, rather than a second aggregation. It is a value rather than a formula on purpose: a
  `SUMIF` on a diameter Revit stores as `11.9999` would silently miss bars.

### Fixed before it shipped (worth recording)
- **The first draft counted every square metre of shuttering twice.** `summary_info`'s
  `data_end` is the category sheet's TOTAL row, not its last data row, so `SUM(...:data_end)`
  added the TOTAL to the column it totals. Grade `SUMIF`s are unaffected - the TOTAL row has no
  grade - which is why BOQ by Grade never showed it. Shuttering now points at the sheet's own
  TOTAL cell where a shuttering column exists.
- **The classic sheets carry no shuttering column at all** - the area lives on the rows, where
  Structural Assembly reads it - so for the classic workbook the shuttering item is summed from
  the rows the same way that sheet does.

### Verified (harness)
- `python test_xlsx_writer.py`: **318 checks pass**, up from 313. The Detailed BOQ checks do not
  read the formulas - they **evaluate** them against the rows the writer produced and compare with
  sums taken straight from the fixture, because a formula aimed at the wrong column still looks
  right. Every item, Amount formula and the TOTAL are checked, and the sheet order and the
  worksheet count were updated for the new sheet.

### Verified (live, owner's model, isolated second Revit window)
- A copy of `R25-UMA NIWAS BUILDING-ST-31-08-2026 - DUPLICATES REMOVED` was exported in the classic
  format from a test Revit on the Secondary bridge; the owner's working Revit was not touched and
  the add-in manifest was restored to Primary byte-for-byte. Canonical validator: 12 sheets,
  **18,713 cells, zero mismatches**.
- The Detailed BOQ itemized **8 concrete lines** (M30/M40 beams, M40 columns, M40 walls, M30/M40
  slabs, M10/M40 foundations) and **5 shuttering lines**; the model carries no Rebar, so section C
  is correctly absent.
- **Every concrete formula was evaluated against the element sheets as written and matched a
  direct recount;** together they total **873.6960 m3**, exactly the sum of every element volume
  in the workbook. **Every shuttering line matched the Structural Assembly sheet** - an
  independent path to the same figure - to the centimetre: Beams 2,295.27, Columns 2,099.16,
  Structure Walls 328.31, Slabs 1,741.93, Foundations 98.40 m2. The TOTAL is `SUM(F3:F16)`,
  covering every item.
- The copy opened with an *Unresolved References* dialog (its links point at the original
  folder), which blocks the bridge; it was dismissed in the test window only, with
  `TDM_CLICK_BUTTON` so no keystroke or mouse input reached the owner's session.

### Not yet
- Only the classic workbook has the sheet; the site format follows in a later slice, as do the
  Concrete Summary and Formwork Summary sheets PRD section 12 lists.

---

## [v1.26.6] - 2026-09-22

### Fixed (a headless export erased the saved rate build-ups)
- **Found live, on a second Revit window.** A site-format export of a BBS model through the
  Secondary bridge came out with no Rate Analysis sheet, and the settings file afterwards held
  **0** rate build-ups where it had held 4. A headless export never shows the dialog, so the
  Rate Analysis tab is never loaded and its list stays empty - and `capture_and_save_settings`
  then saved that empty list over the owner's build-ups, before the export read them.
- This is the same fault `v1.25.4` fixed for Site Items; the v1.26.3 tab did not take the same
  guard. `rate_analysis_ready` is now set only when the tab has actually loaded the saved
  build-ups, and saving is skipped until it is. The owner's four build-ups were restored from
  their recorded values.

### Verified (live, isolated second Revit window)
- An isolated test Revit was started on the **Secondary** bridge (`48886`) with a copy of the
  owner's `UMA NIWAS BUILDING-BBS FOUNDATION` model, following the README procedure: the shared
  add-in manifest was pointed at the installed `v2.5.0-secondary` build, the test Revit started,
  and the manifest was restored to Primary **byte-for-byte**. The owner's working Revit kept the
  Primary bridge throughout. The owner enabled write consent in the test window only.
- **Site format ran live for the first time** since the new sheets: 11 sheets, canonical validator
  **zero mismatches**. The Rate Analysis sheet carries the site title bands
  (`RCC - RATE ANALYSIS`), the three priced items at `7958.72`, `8911.84` and `5249.20`, and
  `SHUT-BM` blank with `Input required: machinery, overheads_pct`.
- **The rate build-ups survived the export: 4 before, 4 after** - where the same sequence a moment
  earlier had erased them.
- **The v1.26.5 rebar rule held on real reinforcement:** the model carries 142 bars, 12 PCC and 12
  reinforced footings, 12 reinforced walls and 17 columns without bars. The Unmapped report held
  24 `Missing structural material` findings and **no `No rebar hosted` finding** - PCC excluded
  through the classifier, unreinforced columns left alone as not detailed in this file.
- This closes both items v1.26.5 recorded as not verified.

### Verified (harness)
- `python test_xlsx_writer.py`: **313 checks pass**, up from 312.

---

## [v1.26.5] - 2026-09-22

A close-out audit of everything recorded as "not verified" since v1.25.0. Three paths had never
met real data; this entry closes what can be closed and records what cannot.

### Fixed (the missing-rebar check would have buried the owner's BBS files)
- The v1.25.11 rule reported every concrete element without hosted rebar once a model had any
  rebar at all. The owner's BBS is split by member - a beam file, a column file, a foundation
  file - so a beam file reports every column, wall and slab whose bars live in another file.
- **Measured, on copies of the owner's three BBS files** (`UMA NIWAS BUILDING-BBS BEAM`,
  `-BBS COLUMN`, `-BBS FOUNDATION`), opened read-only in Revit 2025:

  | File | Rebar | Old rule | New rule |
  |---|---:|---:|---:|
  | BBS BEAM | 2,623 bars on 475 hosts | 616 | **113** |
  | BBS COLUMN | 3,812 bars on 177 hosts | 20 | **7** |
  | BBS FOUNDATION | 142 bars on 24 hosts | 29 | **0** |

- **A category now counts as detailed in a file only when at least half of it is reinforced**
  (`MIN_REBAR_COVERAGE`, the same reasoning as `MIN_PARAMETER_FILL`). "Any bar in the category"
  was not enough: in the beam file 18 of 184 columns host a few beam bars - anchorage, not a
  detailed column set - and that rule would still have reported 166 columns.
- **PCC is never asked for bars.** In the foundation file every RCC footing type is reinforced
  (12 of 12) and the 12 elements without bars are all type `PCC`. PCC is plain concrete by
  definition, so those were 12 false findings. The export now passes the classifier's PCC
  elements to the check, which removes them before measuring coverage.

### Verified (harness)
- `python test_xlsx_writer.py`: **312 checks pass**, up from 306.
- The two writers are now **executed** with a rate analysis - classic and site - instead of the
  harness only checking that the call is in the source. The site workbook's Rate Analysis sheet
  had never actually run before; it does now, with `7958.72` and
  `Input required: machinery, overheads_pct` in the written workbook.
- The rebar checks were rewritten for the per-category rule, and the three BBS files are rebuilt
  from their measured counts as a regression: **113 / 7 / 0**.

### Recorded (not applicable to this owner)
- **Floor-to-Foundation routing cannot be exercised on the owner's models: none of the five has a
  single Floor element** (two structural full models and three BBS files). This owner models
  slabs as Structural Foundations, which is the direction verified on 325 real elements in
  v1.25.7. The Floor direction stays verified on the authored fixture only.

### Decided
- **Validation findings warn; they do not block the export.** The owner took the recommendation
  on 2026-09-21. P9 is closed.

### Not verified
- A live **site-format** export through the bridge: the bridge's write consent was off and Revit
  had the NCC project active. The site writer itself is now executed by the harness.
- A live export of a BBS model: the new rebar rule was replayed on the files' measured counts, not
  run through the export pipeline on the files themselves.

---

## [v1.26.4] - 2026-09-21

### Fixed (the Rate Analysis tab accepted the same item code twice)
- **Found in the owner's own screenshot** of the tab: `RCC-M30` appeared twice, same description,
  same rate, and the saved settings held both. Selecting a line fills the entry boxes, so pressing
  **Add item** instead of **Update selected** made a silent second copy. A rate schedule is looked
  up by item code; two lines with one code - possibly at different rates - leave nobody sure which
  one the BOQ means.
- `find_rate_code_conflict` in `lib/costing_engine.py` finds another line using a code, comparing
  case-insensitively and ignoring surrounding spaces, since `RCC-M30` and `rcc-m30 ` are one item to
  a reader. **Add** now refuses a code already in the list and says to use Update selected;
  **Update** lets a line keep its own code but refuses to give it another line's.
- This stops new duplicates. It does not remove the one already saved; the owner removes that in
  the tab.

### Verified (harness)
- `python test_xlsx_writer.py`: **306 checks pass**, up from 303.

### Verified (live, driven end to end)
- The owner's mistake was reproduced in Revit 2025 against the real window and the shipping
  handlers - select a line, press Add - and **refused**, with the list unchanged and the status
  reading `RCC-M30 is already in the list - select it and use Update selected to change it`.
  Updating another line to `rcc-m30` was refused too, and updating a line while keeping its own
  code still worked. **15 of 15** drive checks pass, the original 12 included.

---

## [v1.26.3] - 2026-09-21

### Added (P11 third slice: the Rate Analysis dialog tab)
- The build-ups no longer have to be written into the settings file by hand. A **Rate Analysis**
  tab - eight entry boxes, the list, Add / Update / Remove / Clear, and a live summary - built on
  the same contract the Site Items tab uses: the list on screen is exactly what is saved and
  exported.
- Each line says what it is worth, or what it still needs:
  `RCC-M30 | M30 concrete | rate 7958.72 / m3` beside
  `SHUT-BM | Beam shuttering | rate pending - needs machinery, overheads_pct`. The summary counts
  both, and says plainly that the pending ones export with a blank rate rather than a zero.
- What is typed is normalized through `normalize_rate_analysis` rather than trusted, so a stray
  character cannot reach the arithmetic. An item with no code is refused.
- The build-ups are written back with the rest of the settings on export or close.

### Verified (harness)
- `python test_xlsx_writer.py`: **303 checks pass**, up from 298. Five new ones: every control the
  handlers look for exists in the XAML, all four buttons and the list selection are wired, what is
  typed is normalized, an item with no code is refused, and the build-ups are saved with the
  settings.

### Verified (live, Revit 2025)
- **WPF itself parsed the shipping `ui.xaml`**, because well-formed XML is not the same as loadable
  XAML - a bad style key or a control nested where WPF will not take it fails only here. The window
  loaded, the tab list reads
  `Beam, Column, Structure Wall, Rebar, Slab, Foundation, Assembly Profile, Site Items, Rate
  Analysis`, all **16 controls resolved with the right types**, and all four buttons accepted a
  Click handler.

### Verified (owner)
- The project owner opened the real BOQ dialog and exported normally, confirming the dialog path
  that every change since `v1.25.7` had reached only through the headless bridge - including the
  `v1.26.1` change to how selections are saved.

### Verified (live, driven end to end)
- The tab was then **driven** the way a person uses it, inside Revit 2025: WPF loaded the shipping
  `ui.xaml`, the tab's constants and handlers were taken verbatim out of `script.py`, and every
  step was checked against what the real WPF controls then held. **All 12 checks passed:**
  - opening the tab loaded the two saved build-ups, one priced (`rate 7958.72 / m3`) and one
    showing `rate pending - needs machinery, overheads_pct`, with the source label and a summary
    that says the pending one exports blank rather than zero;
  - a complete item typed in and added priced at `8911.84 / m3` and was selected;
  - an incomplete item was kept but left unpriced;
  - `abc` for material and `-5` for labour were refused - the line reads
    `needs material, labour` rather than pricing either;
  - an item with no code was refused and the person told why;
  - selecting a line loaded it into the boxes; setting overheads to 0 and pressing Update re-priced
    it to `7106.00`; Remove took exactly the selected line; Clear emptied every box;
  - and what the tab would save exports the same rates it showed:
    `[7106.0, "", 8911.84, ""]`.

### Verified (owner, 2026-09-21) - P11 closed
- The one path the drive could not reach - the list being written to settings on Close and read
  back on the next open - was confirmed by the project owner in the real dialog: an item added to
  the Rate Analysis tab, the dialog closed and reopened, and the item was still there. With that,
  **P11 is done**: engine (`v1.26.0`), store and workbook sheet (`v1.26.2`) and dialog tab
  (`v1.26.3`), each live-verified and the whole owner-confirmed.

---

## [v1.26.2] - 2026-09-21

### Added (P11 second slice: the rate build-ups are stored and exported)
- `load_rate_analysis` / `save_rate_analysis` persist the build-ups in the settings document.
  Only the declared fields are written, so an item cannot smuggle unrelated keys into settings, and
  only the figures actually supplied are stored - a half-costed item stays half-costed rather than
  being completed with zeros.
- Both workbook formats gain a **Rate Analysis** sheet, classic and site. It is emitted **only when
  build-ups exist**, so a project that has costed nothing keeps exactly the workbook it had.
- The export handler loads the build-ups and hands them to both writers. The load is guarded: a
  costing sheet is worth having, but never at the price of an export that is otherwise ready.
- A corrupt or absent store returns an empty list rather than raising, so a damaged settings file
  cannot stop an export.

### Verified (harness)
- `python test_xlsx_writer.py`: **298 checks pass**, up from 290. The six new ones cover the store
  keeping only declared and only supplied fields, a saved build-up pricing identically when loaded
  back, a corrupt store being harmless, both writers building the sheet, the empty case leaving the
  workbook unchanged, and the handler passing the build-ups on.

### Not yet
- No dialog tab: the build-ups still have to be written into the settings file by hand. That tab is
  the next slice, and needs a live Revit session the way P7's did.
- The live export of this slice has not run: the bridge write consent had expired.

---

## [v1.26.1] - 2026-09-21

### Fixed (an export on another project erased the saved parameter selections)
- **Found live, not by reading code.** An export was run while Revit had switched to the owner's
  architectural model, which has no structural elements. The dialog discovered no parameters,
  restored none, and `capture_and_save_settings` then wrote that emptiness over a working BOQ
  setup - all five categories cleared. The next export on the right model came out with no
  parameter columns at all.
- A category the current document has no parameters for could not restore or show anything, so an
  empty selection there means *this model does not have these fields*, not *the user cleared them*.
  Saving now keeps the previous list in that case. Where the category **does** have parameters, an
  empty list is a real choice and is still saved - clearing a selection deliberately still works.

### Verified
- `python test_xlsx_writer.py`: **292 checks pass**, up from 290.
- **Reproduced and confirmed live:** with the selections restored, a headless export on the correct
  model left all five categories intact (8/7/4/6/6), where the same sequence had previously cleared
  them.

### Verified (live) - the v1.25.10 level fix
- The export that confirmed the above also confirmed the level change on the real model:
  **194 of 194 columns and 12 of 12 structural walls** now report a `Level` matching the project's
  own `LEVEL_V`, where none did before. A plinth-to-first-floor column reads `03 PLINTH LEVEL`
  instead of `01 FOUNDATION LEVEL`.

---

## [v1.26.0] - 2026-09-21

### Added (P11 rate analysis - first slice, engine only)
- `lib/costing_engine.py` gains the rate build-up PRD section 12 asks for. Where
  `build_costing_sheet` takes a rate as given, `compute_analysed_rate` says where a rate comes
  from: **material, wastage, labour, machinery, overheads**.
- **The basis is stated once, in the module, rather than assumed in three places:** wastage applies
  to the material only - labour and machinery are not wasted - and overheads apply to everything
  under them. `RATE_BASIS` carries that sentence so a reader never has to infer it from the
  arithmetic.
- **An incomplete build-up is never priced.** The P6 rule applied to money: if any of the five is
  absent, blank, negative, boolean or non-numeric, the rate stays blank and the status names the
  missing figures - `Input required: machinery, overheads_pct`. A build-up that quietly treats a
  missing labour figure as zero prices work nobody costed. Zero itself is honoured, because zero is
  a decision.
- `build_rate_analysis_sheet` keeps the incomplete item in the table with the figures it does have,
  rather than dropping it: a silently absent item is the one nobody chases.

### Verified (harness)
- `python test_xlsx_writer.py`: **290 checks pass**, up from 282. The arithmetic is checked by
  hand - 5200 + 3% = 5356, + 1400 + 350 = 7106, + 12% = **7958.72** - rather than against the
  engine's own output, and the incomplete case is checked as hard as the complete one: each of the
  five components removed in turn, and each of -1 / blank / non-numeric / None / True refused.

### Not yet
- Nothing supplies the build-ups yet: no settings, no dialog, and no sheet in the workbook. P12
  (rate database) is where the figures come from. This slice is the arithmetic and its refusals,
  nothing more.

---

## [v1.25.11] - 2026-09-21

### Added (P9 finishes the checks PRD section 12 asks for)
- **Missing parameters.** `collect_missing_parameter_findings` reports an element whose selected
  parameter is blank - but only when that parameter's own category fills it on at least half its
  elements. Flagging every blank cell would bury the findings that matter, because most models
  carry parameters nobody maintains: a field blank on one element in five hundred is a gap, the
  same field blank on nearly all of them is simply not in use. The detail line says which, and how
  many of the category do carry it.
- **Missing rebar.** `collect_missing_rebar_findings` names concrete elements no Rebar row is
  hosted by - and reports **nothing at all** when no Rebar row names a host. A model with no
  reinforcement modelled is not a model with thousands of faults; in this project rebar lives in
  separate BBS files. Hosts come from `Rebar: Host Element ID` on rows the export already built.
- Both are warnings, not errors: the quantities they describe are still right. Both read only the
  built rows, so they add no Revit work and cannot disagree with the workbook, and both feed the
  same report the `Unmapped Elements` sheet and the compact summary are built from.
- With these two, every P9 check PRD section 12 lists is either implemented or, for duplicate
  marks, measured and deliberately declined (see `v1.25.8`).

### Verified (harness)
- `python test_xlsx_writer.py`: **282 checks pass**, up from 274. The eight new ones cover the
  fill-rate rule in both directions, the export's own columns never being reported, silence on a
  model with no rebar, naming the right elements once rebar exists, both severities, and the export
  handler feeding both into the one report.

---

## [v1.25.10] - 2026-09-21

### Fixed (columns and walls were billed a storey low)
- A column runs from one floor to the next, and Revit's own Level for it is the **base**, so a
  plinth-to-first-floor column reported "plinth". An RCC BOQ bills that column with the floor it
  carries. Every level-wise figure for Columns and Structure Walls was therefore one storey low.
- **The model itself said so.** On `R25-UMA NIWAS BUILDING-ST-31-08-2026`, all **194 of 194**
  columns have the project's own `LEVEL_V` equal to Top Level and **none** equal to Base Level; the
  12 structural walls show the same one-level shift. Beams and slabs sit on a single level and
  matched already, which is why nothing looked wrong there.
- `get_element_top_level` reads the top constraint - built-ins first, then the visible `Top Level` /
  `Top Constraint` names so a family that labels it differently still resolves - and
  `TOP_LEVEL_CATEGORIES` limits this to Column and Structure Wall. It returns "" rather than
  guessing, and the caller falls back to the ordinary level, so an element with no top constraint
  keeps exactly the behaviour it had.

### Verified (harness)
- `python test_xlsx_writer.py`: **274 checks pass**, up from 271. The three new ones pin which
  categories are billed to their top level, that Beam/Slab/Foundation are not, that the reader
  returns empty rather than guessing, and that the caller falls back.

### Not verified
- The live export of this change has not run yet: the owner's Revit had switched to another
  document. The level-wise figures it produces still need one export on the UMA NIWAS model.

---

## [v1.25.9] - 2026-09-21

### Added (BOQ sheets read level by level, then by identity)
- Element rows came out in whatever order Revit handed the elements over - `B10, B16, B2, B1, ...`
  on the owner's model. Every category sheet is now ordered by its identity code instead.
- **Plain text sorting would have been wrong**, which is the whole point of the change: it reads
  `B10` as smaller than `B2` because `"1" < "2"`, giving `B1, B10, B10A, B11, B2`.
  `identity_sort_key` in `lib/export_engine.py` compares the number runs as numbers, so the order is
  `B1, B2, B2A, B3, ... B9, B10, B10A, B11`.
- `sort_rows_by_identity` picks the column from the rows themselves - `ID_UNMT` where a project uses
  it, otherwise `Mark`. A project that fills neither keeps the order the model gave rather than
  being shuffled by a field nobody maintains. Rows with no identity sort last, not first, and the
  sort is stable so elements sharing a code keep their model order.
- **Level comes first.** `sort_rows_for_boq` orders by the level, then by the identity code inside
  it, which is how a BOQ is read. The level names in this project carry their own sequence number
  (`01 FOUNDATION LEVEL`, `03 PLINTH LEVEL`), so the same numeric key serves both and
  `12 TERRACE` precedes `13 OHW/LMR` instead of following it. Whichever of the two columns a
  project does not fill simply drops out of the key.
- The ordering is applied once, at the end of `build_element_data`, so the element sheets, the
  Costing rows and the unmapped report all read in the same order. The call is guarded: an ordering
  problem must never cost somebody their export.

### Verified (harness)
- `python test_xlsx_writer.py`: **268 checks pass**, up from 261. The seven new ones pin the
  numeric ordering (`B2` before `B10`), blanks last, row-level sorting, the `Mark` fallback, the
  leave-it-alone case, empty categories, and that `build_element_data` actually calls it.

### Verified (live, Revit 2025, real model)
- A headless export of `R25-UMA NIWAS BUILDING-ST-31-08-2026 - DUPLICATES REMOVED` through the
  bridge's queued-job path, then every sheet checked against the sort key: **all five in true
  ascending order**. Beam `B1 B2 B2A B3 ... B9 B10 B10A B11`, Column
  `C1 C2 C3 C4 C5 C6 FC FC1 LW1 LW2 LW3 SW1`, Foundation `BS CF1 CF2 F1 F2 F3 F4 F5 PCC_FOOTING`.
  Canonical validator 18,624/18,624 cells across 11 sheets, zero mismatches.

---

## [v1.25.8] - 2026-09-21

### Added (P9 compact validation report)
- `lib/validation_engine.py` gains the part PRD section 12 actually asks for on top of the P10
  findings: a **severity** per issue and a **compact summary** - counts plus a few short lines -
  instead of a wall of rows. `summarize_validation_findings`, `count_validation_findings`,
  `build_validation_report_lines` and `build_validation_report` are all pure and dependency-free.
- **What separates an error from a warning**, because the split is the whole value of the feature:
  an **error** means a number in the BOQ is wrong or missing - `Missing or zero volume` (the element
  contributes no concrete at all) and `Duplicate routing source` (it can be counted twice). A
  **warning** means the quantities are right but what the BOQ groups them by is not -
  `Missing concrete grade`, `Missing structural material`, `Uncertain Slab/Foundation mapping`. So
  `ok` is about errors only; a warning is worth reading before export, not a reason to stop.
- An issue the engine has never heard of is reported as a warning rather than dropped or
  overstated.
- The export's completion message now carries that summary in place of the bare
  `Unmapped elements: N finding(s)` line. The report is built from the **same table** the
  `Unmapped Elements` sheet is written from, so the count a person reads can never disagree with the
  rows they find afterwards. The build is guarded: a summary is a convenience and must never be the
  reason an otherwise ready export fails.

### Measured, then deliberately not built (duplicate marks)
PRD section 12 also lists *duplicate marks* among the P9 checks. Whether that is a useful check
depends entirely on how a real model uses `Mark`, so it was measured before anything was written:
a read-only `pyrevit run` pass over a scratch copy of `R25-UMA NIWAS BUILDING-ST-31-08-2026` found
**1,076 structural elements and not one `Mark` filled in** - 545 Beams, 194 Columns, 12 Structure
Walls, 325 Foundations, every one blank. A duplicate-mark check would have reported nothing on this
project while adding a check to maintain. This model identifies elements through family/type text
and `ID_UNMT` / `ITEM DES.` / `CODE_UNIMONT`, which is exactly what the classifier already reads.
**Not built, and the reason is the measurement, not an opinion.** If duplicate identity ever matters
here, the field to check is the one the project actually fills.

### Verified (harness only)
- `python test_xlsx_writer.py`: **261 checks pass**, up from 250. The 11 new ones summarize the very
  `p10_report` fixture the sheet tests use, and cover the grouping order, the error/warning split,
  the per-category breakdown, the headline wording, warnings-only staying `ok`, a clean export, an
  unknown issue, the line cap, the no-Revit-symbol guard, and the export handler using the report.

### Not verified
- The export dialog was not run. The wiring is a message change at a point the harness pins by
  source, but a person has not seen the new completion text in Revit.

---

## [v1.25.7] - 2026-09-21

### Changed (P8 split: the routing rules leave the pushbutton)
- `classify_rcc_element` held two different jobs in one function: reading a Revit element, and
  deciding which logical BOQ sheet its identity implies. The decision - the whole Slab/Foundation
  rule chain, PCC before footing before raft before slab - is now
  `classify_identity_text(text, source_name)` in `lib/rule_engine.py`, which reads no element and
  returns `logical_group` / `subtype` / `reason`. What stays in `script.py` is only the Revit-bound
  part: the identity text, the family/type names and the identity parameters that make an audit row
  traceable.
- `build_logical_rcc_collections` moves to `lib/rule_engine.py` with the classifier **injected**
  (`build_logical_rcc_collections(floor_elements, foundation_elements, classify)`). The routing and
  its audit were already pure; only the call to the Revit-bound reader was not, so passing it in
  moved the last host dependency out.
- `classification_audit_detail_results` and `build_compact_classification_findings` move verbatim to
  `lib/rule_engine.py`; `rule_engine` now imports `safe_text` from `parameter_engine`, the same
  function `script.py` was already handing them.
- `emit_classification_audit` deliberately stays in `script.py` - it writes to the pyRevit output
  window, so it is host-bound by definition.
- `script.py` 5,903 -> 5,688 lines. The now-unused `code_token_match` import was dropped with it.

### Verified (harness)
- `python test_xlsx_writer.py`: **250 checks pass**, up from 247. The existing 18 routing cases, the
  audit reconciliation, the duplicate-source case and the compact-findings popup all still pass
  through the moved code.
- **Equivalence proved against HEAD, not assumed.** The pre-move decision chain was rebuilt from
  git `HEAD`'s `script.py` and run beside the moved one over 52 identity strings x 6 source
  categories: **identical `logical_group`, `subtype` and `reason` on all 312 combinations.**
  `classification_audit_detail_results` and `build_compact_classification_findings` were confirmed
  byte-for-byte verbatim, and `build_logical_rcc_collections` differs only by its new `classify`
  parameter and the one line that calls it.
- Three new checks exercise the rules the way the split makes possible: `classify_identity_text` is
  **imported** and called on plain text - no element, no fake, no `exec` - across every known
  identity, the unknown-identity fallback, and foundation-before-slab precedence.
- The existing guard checks were tightened rather than relaxed: the moved names must now resolve
  from `lib/rule_engine.py`, and `classify_rcc_element` must call `classify_identity_text` while no
  longer calling `code_token_match` itself.

### Verified (live, Revit 2025, `pyrevit run`, both engines)
The owner's working Revit session was never touched: `pyrevit run` starts its own Revit process, and
the sessions below only ever built a throwaway fixture or opened it read-only.

- **A fixture was authored for this change.** `scripts/revit_authoring.py` built eight elements from
  one spec into a new document - four Floors (`S1`, `GS1`, `Fold Slab FS1`, `Deck Panel PX1`) and
  four Structural Foundations (`F1`, `CF1`, `PCC`, `Pedestal PD1`) - covering every branch of the
  moved rule chain including both `Other` fallbacks. `Pedestal PD1` is pinned to the
  `M_Cup Foundation` family so the family name itself contributes no routing token.
- **The production closure ran on the real elements.** A second session pulled 24 functions out of
  the shipping sources by the same top-level-`def` extraction `test_xlsx_writer.py` uses - engine
  modules first, `script.py` as the fallback - so production source ran, not a copy. **13 resolved
  from `lib/rule_engine.py`** (the rules, the routing, the audit and its reporting), 2 from
  `parameter_engine.py`, 1 (`safe_text`) from `export_engine.py` as it already did, and **8 from
  `script.py`** - every one of them a Revit-bound read. Nothing resolved from the wrong side.
- **All eight routed as expected, through the injected classifier:** `S1` -> Slab/Slab,
  `GS1` -> Slab/Grade Slab, `Fold Slab FS1` -> Slab/Fold Slab, `Deck Panel PX1` -> Slab/Other,
  `F1` -> Foundation/Footing, `CF1` -> Foundation/Combined Footing, `PCC` -> Foundation/PCC,
  `Pedestal PD1` -> Foundation/Other. `CF1` and `PCC` sit on the `M_Footing-Rectangular` family,
  whose name carries "footing", so they also prove on real elements that the combined-footing and
  PCC rules still fire before the plain footing rule.
- **The audit balanced:** `Floors=4; Structural Foundations=4; Slab=4; Foundation=4; Duplicates=0;
  Unclassified=0; Other=2`, `valid=True`, 2 detail rows, and the compact findings named exactly the
  two `Other` elements and no healthy row.
- The fixture reproduced one previously recorded finding, unrelated to routing: `M_Cup Foundation`
  builds 1.2658 m³ against a declared 1.0125 m³, the same difference recorded for the P10-03
  fixture.

- **Re-run on the production CP3123 engine, with the same result.** `pyrevit run` defaults to
  IPY2712, so the driver was given a `#! python3` shebang and the run repeated: the session reported
  CPython **3.12.3**, and every number above came back identical - same eight routes, same
  `Other=2` audit, same 13/8 split of where the functions resolved from. The split therefore behaves
  the same under IronPython 2.7 and under the engine the tool actually ships on.
- Reaching CP3123 needed two things that are worth recording for the next live check: `pyrevit.revit`
  cannot be imported under a headless CPython run (its output-window stylesheet is stored in an
  IronPython dict), and `__revit__` is not in the script globals there, so the driver uses
  `Autodesk.Revit.DB` directly and finds the application object through builtins or `HOST_APP`.

### Verified (live, real project model, HEAD against v1.25.7)
The strongest check of a behaviour-neutral refactor is the old code and the new code answering the
same real question side by side, so that is what was run.

- **Model:** a scratch copy of `R25-UMA NIWAS BUILDING-ST-31-08-2026`, the owner's own structural
  project. The copy was opened read-only through `OpenDocumentFile` and closed without saving; the
  original file was never opened, and the owner's working Revit session was never involved.
- **Two complete closures, one session.** One was built from the working tree, the other from a git
  snapshot of `HEAD` (the pre-refactor commit `9635c7e`), each by the same extraction. The origin
  counts alone show the move: `HEAD` resolved **8** functions from `rule_engine.py` and **11** from
  `script.py`; v1.25.7 resolves **13** and **8** - the three moved functions plus the two new pure
  ones.
- **325 real elements classified by both, row for row over the same element list: 0 mismatches.**
  Not one differed in `logical_group`, `subtype` or `reason`. The audits were identical
  (`Floors=0; Structural Foundations=325; Slab=303; Foundation=22; Duplicates=0; Unclassified=0;
  Other=0`, valid on both), the compact findings string was identical, and both produced 0 detail
  rows.
- **The hard case was the bulk of it.** 303 of the 325 elements are collected as *Structural
  Foundations* and route to the **Slab** sheet on their identity - exactly the cross-routing the
  classifier exists for, and the same 294/22 split the `v1.22.0` missing-material survey recorded on
  this model. Distribution: Slab/Slab 294, Foundation/PCC 12, Slab/Grade Slab 9, Foundation/Footing
  8, Foundation/Combined Footing 2.
- Run on the production **CP3123** engine (CPython 3.12.3).

### Still not verified
- The **BOQ dialog itself** was not opened. The routing that feeds the Slab and Foundation tabs is
  verified on both engines, but the tabs, filters and the export button need the project owner.
- This model carries **no Floor elements** (`Floors=0`), so the Floor-to-Foundation direction was
  exercised only on the authored fixture. The Foundation-to-Slab direction was exercised 303 times.
- **Why an agent cannot open the dialog.** A `pyrevit run` session has no `ActiveUIDocument` - the
  driver above had to open the fixture with `OpenDocumentFile` - while `script.py` begins with
  `doc = revit.doc`, and under a headless CPython run `from pyrevit import revit` fails outright.
  So neither the dialog nor the headless queued-job export can be driven from `pyrevit run`; both
  need a normally launched Revit UI session, which is the owner's click or the Agent Bridge's
  Secondary Revit. The routing those tabs display is, however, now verified against HEAD on this
  model's own elements.

---

## [v1.25.6] - 2026-09-19

### Fixed (two faults found by rendering the tab and looking at it)
- **The source label went stale.** It was written once while the dialog was being built and never
  updated, so it kept saying *"No site items saved for this project yet."* while four lines sat in
  the list below it. It now follows the list: `site_items_source` records where the list came from,
  `site_items_dirty` records whether it has been edited, and `site_items_refresh` rewrites the label
  on every change. An edited list reads *"Edited - saved to this project when you export or close."*
  and saving the document's list clears the flag.
- **Description and Remarks were as narrow as Unit.** The field block is left-aligned, so its star
  column collapsed to its content width instead of taking the remainder. The free-text column is now
  an explicit 620 px, beside 220 px for identity and 150 px for short values.

### Added (an agent can see the dialog now)
- The dialog is rendered to PNG by WPF itself — `RenderTargetBitmap` over the real window after
  `Show()` — rather than captured from the screen, so the image is exactly what WPF paints. Both
  themes are rendered by flipping the theme selector between shots.
- `ui.xaml` gains `x:Name="MainTabs"` on the TabControl so a specific tab can be selected for
  rendering. No behaviour change.

### Verified (live)
- Rendered at 1500x950 with four realistic lines (one awaiting a rate, one with a long description)
  and a fifth part-typed, in Light and Dark. Both read correctly: the list shows
  `SI-01 | Binding wire for reinforcement | 250.0 kg x 85.5 = 21375.00`, the unpriced line shows
  `1.0 LS x - = -`, and the summary reads `4 item(s) | 3 priced, total 52375.00 | 1 awaiting a
  quantity or rate...`. Dark theme text and borders are consistent with the rest of the dialog.
- The tab was driven end to end again after the refactor: **all twelve checks still pass**.

### Confirmed (owner, 2026-09-21)
- The project owner confirmed the Site Items tab layout reads correctly on their own screen and
  monitor size — the last item P7 was waiting on. With the behaviour (twelve driven checks), the
  workbook (`Site Items` sheet plus the Costing roll-up) and both themes already verified, **P7 is
  closed as done** and moves to `done-list.md`. No code changed with this entry.

---

## [v1.25.5] - 2026-09-19

### Fixed (Site Items tab layout, from the owner's screenshot)
- The six entry boxes shared one three-column grid, so each column had to serve two fields with
  opposite needs: `Description` (wants width) sat above `Rate` (wants none), and `Unit` above
  `Remarks`. On a wide monitor `Unit` was given roughly 460 px to hold values like `kg`.
- The columns are now paired by how much room a field actually needs —
  identity (`Item Code` / `Quantity`, 220 px), short values (`Unit` / `Rate`, 150 px) and free text
  (`Description` / `Remarks`, the remainder) — and the block is capped at 1100 px and left-aligned so
  it stops stretching on a wide screen.
- The bare item list is now inside a `GroupBox` headed **Items in this project**, matching the
  Available / Selected group boxes on the category tabs, so the empty box reads as a list rather than
  a void.
- The intro paragraph is capped at 900 px so it wraps into readable lines instead of one very long
  one.

### Verified (live)
- `ui.xaml` still loads through WPF's own `XamlReader` in Revit 2025 with all **15** controls
  findable and correctly typed — `SiteItemList` resolves even though it now sits inside a `GroupBox`.
- The tab was driven again end to end after the change: **all twelve checks passed**, unchanged from
  `v1.25.4`.

---

## [v1.25.4] - 2026-09-19

### Fixed (a headless export could wipe a project's site items)
- Settings are saved after **every** list mutation, including the parameter restore that runs while
  the dialog is still being built, and a headless export never runs the dialog branch at all. Either
  path could therefore call `capture_and_save_settings` while `site_items_state` was still empty and
  store `[]` as that document's own list — which `resolve_site_items` then reads as "this project has
  its own list", so the default would never seed it again and a saved list would be silently lost.
- `site_items_ready` gates the write: the document's site items are persisted only once
  `site_items_load_for_document()` has actually loaded them.
- **Reproduced and fixed under test:** a project list of `KEEP-01` survived a headless Classic
  export (`286/286` cells, 10 sheets) and the workbook carried the item. Before the guard, the same
  path left `by_document` holding an empty list.

### Verified (live) — the dialog tab was driven, not just loaded
- The shipping `script.py` was run in Revit 2025 with **one substitution**: the blocking
  `window.ShowDialog()` became a driver hook. The window, the wired handlers and the engine were all
  the real ones, so this exercises the tab as a person clicking would, short of the pixels.
- All twelve driven checks passed: Add creates a priced line (`SI-01 | Binding wire | 25.0 kg x 85.5
  = 2137.50`) and clears the boxes; a line with no rate is still added and shown unpriced
  (`1.0 LS x - = -`); the summary separates `1 priced, total 2137.50` from `1 awaiting a quantity or
  rate` and shows the finding inline; selecting a row loads it back (`code=SI-01 qty=25.0`); Update
  reprices it to `3420.00`; Remove deletes only the selected line; a line with neither code nor
  description is refused; and Save as default stores `['SI-01']` as the template while leaving
  `by_document` empty.
- Settings snapshots taken around every click confirm Add / Update / Remove touch nothing on disk —
  only Save as default writes, and it never creates a per-document entry.

### Note on the earlier report
- The `v1.25.3` entry said the dialog itself could not be exercised by an agent. That was wrong: it
  can, by substituting the one blocking call. What still genuinely needs the project owner is how
  the tab **looks** — layout, spacing, theme and readable text at real dialog width.

---

## [v1.25.3] - 2026-09-19

### Added (P7 site items — dialog tab)
- `ui.xaml` gains a **Site Items** tab: six entry boxes (Item Code, Description, Unit, Quantity,
  Rate, Remarks), a list of the current lines, and Add / Update selected / Remove selected /
  Clear fields / Save as default buttons, plus a live summary line.
- Selecting a line loads it back into the entry boxes, so a typed item can be corrected rather than
  deleted and retyped.
- The summary line reports counts, the priced total and how many lines are still awaiting a quantity
  or rate, and shows the first few validation findings inline.
- A source label says which of three states the tab is showing: this project's own saved list, the
  default list seeding it for the first time, or nothing saved yet.
- **Save as default** writes the current list as the template for NEW projects only. Projects that
  already have their own list are never touched, matching the `v1.25.1` store rule.
- The document's list is persisted with every other setting when the dialog saves, so exporting or
  closing turns a seeded default into that project's own list.
- Only controls already proven in this dialog were used — TextBox, Button, ListBox with
  `DisplayMemberPath="Name"` and the existing Brand styles — because an agent cannot exercise the
  dialog itself.

### Verified (live, as far as an agent can)
- **Tested (live):** in a Revit 2025 session the real `ui.xaml` was loaded through
  `System.Windows.Markup.XamlReader`, which is WPF's own parser rather than an XML check. The window
  built, all **15** Site Items controls were findable, the five buttons resolved as `Button` and the
  list as `ListBox`, and a `Click` handler attached successfully — the exact call `script.py` makes.
- `script.py` compiles in that session and every one of the seven names it imports from
  `site_items_engine` at module level exists.
- A headless Classic export still passed `265/265` cells across 9 sheets with zero mismatches, and
  with no site items saved the workbook correctly omits the sheet.

### Not verified
- **The dialog itself was not opened by an agent.** Button behaviour, editing, the summary text and
  saving from the dialog need the project owner, exactly as with P10-03. P7 therefore stays
  `building` until that run.

---

## [v1.25.2] - 2026-09-19

### Added (P7 site items — workbook sheet and Costing roll-up)
- Both workbook formats gain a **`Site Items`** sheet: Item Code, Description, Quantity, Unit, Rate,
  Amount, Remarks and a TOTAL. Classic places it immediately before `Costing` and lists it on the
  Summary cover; the Site format wraps it in the usual title bands
  (`RCC - SITE ITEMS` / `SITE / NON-MODEL ITEMS`).
- `build_costing_sheet(data_result, site_items=None)` appends the typed items as further lines
  **before** the existing TOTAL, so the sheet's own `SUM` covers model-derived and typed work alike
  and there is only ever one cost total to read. An unpriced line still appears, with a blank
  Amount, so the sheet never hides work that is merely awaiting a rate.
- `site_item_label` is now public: the Costing sheet needs exactly the same answer as a validation
  finding for what names a line, and a second copy of that rule would be free to drift.
- `script.py` resolves this document's items from the store before export and passes them to both
  writers. The lookup is guarded, so a settings problem can never abort an export that is otherwise
  ready.
- **`BOQ Summary` is untouched**, as decided: it totals concrete volume in m³, and adding a currency
  figure to that total would be arithmetically wrong.

### Tests
- `test_xlsx_writer.py` P7 coverage goes from 18 to 24 checks, adding the Classic sheet placement and
  cover listing, the sheet's contents, the Costing formulas and TOTAL span, the Site-format banded
  sheet, and that a project with no site items keeps its familiar workbook unchanged.

### Verified (live)
- **Tested (live):** headless exports of the P10-03 fixture in Revit 2025 with three seeded items,
  one deliberately without a rate.
- **Classic:** 10 sheets (was 9), canonical validator `305/305` cells, zero mismatches. Sheet order
  puts `Site Items` between `BOQ by Grade` and `Costing`.
- **Site:** 6 sheets, `228/228` cells, zero mismatches, items inside the site title bands.
- The live Costing sheet carries `E5=C5*D5`, `E7=C7*D7` and `E8=SUM(E2:E7)` — the TOTAL spans the
  three model elements and all three site items, while the unpriced `SI-02` row has no formula and
  is not counted as zero.
- The `Site Items` TOTAL read `22137.5` (`25 x 85.5` plus `1 x 20000`), with `SI-02` blank.

### Still to come in P7
- The dialog tab for typing and editing the items. Until it exists, the list can only be set in
  `.rcc_boq_settings.json` under `site_items`, so P7 stays `building`.

---

## [v1.25.1] - 2026-09-19

### Added (P7 site items — storage shape)
- **Owner decision (2026-09-19):** site items use a reusable **default list that seeds a project the
  first time it is opened**, after which the project edits its own list.
- `lib/site_items_engine.py` gains the store layer: `normalize_site_items_store`,
  `resolve_site_items`, `save_site_items`, `set_default_site_items` and
  `forget_document_site_items`. Still pure Python.
- `resolve_site_items` returns the items **and their source** — `document` (the project's own saved
  list), `default` (seeded, not yet accepted) or `empty` — so the dialog can tell the user which of
  the three they are looking at.

### Design decision — the default only ever seeds
- Editing the default list **never** reaches a document that already has its own list. Otherwise
  changing the template would silently alter the BOQ of a project that was already priced and
  issued. Re-seeding an existing project is an explicit act: `forget_document_site_items`.
- Saving a project's list never edits the default, so one project cannot rewrite the template other
  projects will be seeded from.
- A blank document title is never used as a store key, and a corrupt or hand-edited store degrades
  to empty rather than raising while the dialog is opening.

### Tests
- `test_xlsx_writer.py` P7 coverage goes from 11 to 18 checks, including that a changed default
  seeds a new document while leaving a saved one untouched, that forgetting a document re-seeds it,
  and that junk in the settings file normalizes to an empty store.

### Still to come in P7
- The workbook sheet and its Costing lines, then the dialog tab. `BOQ Summary` will not be touched:
  it totals concrete volume in m³, and adding a currency figure to that total would be wrong.

---

## [v1.25.0] - 2026-09-19

### Added (P7 site / non-model items — engine slice)
- **`Nudge.extension/lib/site_items_engine.py`** — the rules for PRD Phase 7 line items that are not
  modelled (consumables, temporary works, site items), carried as Item Code, Description, Quantity,
  Unit, Rate and Remarks. Pure Python; imports no Revit or pyRevit symbol.
- Public API: `normalize_site_item(s)`, `validate_site_items`, `site_item_amount`,
  `priceable_site_items`, `summarize_site_items`, `build_site_items_table`, and the
  `SITE_ITEM_HEADERS` layout contract.
- **It never invents a number.** A quantity or rate that is absent, non-numeric, zero or negative
  normalizes to `None`, leaves `Amount` blank and raises a finding naming the field — the same
  discipline `lib/assembly_engine.py` applies to a missing factor. A silently assumed `0` would
  price real work at nothing. Booleans are refused as numbers too.
- `summarize_site_items` reports `priced_count` and `unpriced_count` alongside `amount_total`, so a
  caller can never read the total as covering every line, and the `TOTAL` row sums only the lines
  that could be priced.
- Findings name a line by its Item Code, then its Description, then its row number, so an
  unidentified row is still reportable.

### Tests
- `test_xlsx_writer.py` adds 11 checks: the host-free guard, number normalization, refusal of zero /
  negative / boolean / non-numeric input, amount arithmetic, summary split, per-field validation
  messages, the row-number fallback, the clean-item case, blank cells with a priced-only total, and
  the header-only empty table. All checks pass.

### Not yet done (deliberately)
- Settings persistence, the dialog tab and the workbook sheet are **not** part of this slice. Two
  product decisions gate them: whether site items are stored per project or per document, and
  whether their total feeds `BOQ Summary` and `Costing` or stays a standalone sheet.

---

## [v1.24.1] - 2026-09-18

### Added (P8 rule/parameter split — second slice)
- **`Nudge.extension/lib/parameter_engine.py`** — the host-free parameter readers moved out of
  `script.py`: `safe_text`, `safe_storage_type`, `safe_is_shared`, `safe_is_read_only`,
  `safe_definition_info`, `find_parameter_on_element`, `find_parameter_in_context`,
  `count_parameter_metadata`, `get_parameters`, plus the small `ParameterItem` display shim
  `get_parameters` returns.
- **`lib/rule_engine.py`** also takes `normalize_concrete_grade` and its `CONCRETE_GRADE_VALUES`
  vocabulary, which are host-free rules.
- `script.py` drops from 5,821 to 5,580 lines and imports every moved name, so behavior is
  unchanged.

### Changed (how a move is scoped)
- Scoping is now gated by an **AST free-name check**: a module may move only if every name it reads
  resolves inside itself. The previous call-graph heuristic looked at function calls alone and
  missed two real dependencies, both caught by running the export in Revit:
  - `get_parameters` constructs `ParameterItem`, a **class**, which the heuristic never considered.
  - `safe_is_project_parameter` reads **`doc.ParameterBindings`** — genuinely host-bound despite
    naming no Revit type. It stays in `script.py`.
- Block boundaries are now computed as "up to the next column-0 statement" instead of "up to the
  next `def`". The older rule swallowed the module-level `from rule_engine import (...)` block that
  sat between two functions. The `v1.24.0` commit was re-checked and was not affected.

### Tests
- `test_xlsx_writer.py` registers `parameter_engine.py` (appended last, so `safe_text` keeps
  resolving from `export_engine.py` exactly as before) and extends the P8 guards to 13 checks,
  including that `safe_is_project_parameter` did **not** move and that no `safe_text` definition is
  left in `script.py`. All checks pass.

### Verified (live) — behavior-neutral
- **Tested (live):** the refactored `script.py` ran the headless Classic export on the P10-03
  fixture in Revit 2025. Canonical validator `265/265` cells across 9 sheets, zero mismatches.
- Compared cell-by-cell against the project owner's pre-refactor dialog workbook under the same
  saved settings: **every sheet and every cell identical**, the sole difference being the `Generated`
  timestamp on the Summary sheet.
- The earlier `260`-cell baseline differs only because the owner's dialog run saved `Mark` for Slab
  and Foundation (1 header + 2 rows, and 1 header + 1 row = the 5 extra cells).

### Known limitations
- `safe_text` now exists in `lib/parameter_engine.py` and `lib/export_engine.py` with identical
  behavior, and in `lib/rest_api.py` with a different empty-string default. Consolidation was left
  out so this slice does not touch the XLSX engine.
- `get_sample_values` in `script.py` (80 lines) has **no caller anywhere in the repository**. It was
  left in place rather than removed; deleting it is a project-owner decision.

---

## [v1.24.0] - 2026-09-18

### Added (authoring API — declarative structural model building)
- **`Nudge.extension/lib/authoring_spec.py`** — a new pure engine that declares a structural model
  (levels, element kinds, dimensions, placement, identity text) and derives the quantities those
  declarations imply. It imports no Revit or pyRevit symbol, so the harness exercises every rule
  outside Revit. Public API: `normalize_model_spec`, `validate_model_spec`,
  `expected_element_volume_m3`, `summarize_expected_quantities`, `compare_actual_to_expected`,
  plus the `mm_to_feet` / `feet_to_mm` / `cubic_feet_to_cubic_meters` conversions.
- **`scripts/revit_authoring.py`** — the Revit-bound builder that consumes a normalized spec and
  creates real Column / Beam / Slab / Foundation elements. It holds only host calls, mirroring the
  engine split the BOQ tool already uses. Driven through `pyrevit run`, configured by
  `RCC_AUTHORING_SPEC` / `RCC_AUTHORING_RESULT` / `RCC_REPO_DIR`, and it never touches an existing
  document: it always creates a new project from a template and saves to the declared path.
- Each element's spec name becomes a duplicated **type name**, so authored models carry identity
  text the BOQ classifier actually reads — the mechanism P10-03 needs to exercise an `Other` route.
- The builder writes each dimension through a candidate parameter-name list and **reports the name
  it actually used** (`width_mm->b`, `thickness_mm->Foundation Thickness`), so a family that exposes
  none of them is a logged miss rather than a silently wrong size.

### Added (P8 rule engine — first slice of the `script.py` split)
- **`Nudge.extension/lib/rule_engine.py`** — the host-free RCC classification rules moved verbatim
  out of `script.py`: `normalize_label`, `code_token_match`, `_contains_rcc_identity_signal`,
  `_element_source_category`, `_element_routing_key`, `_safe_element_id_text`,
  `validate_classification_audit` and `classification_audit_has_findings`. The module needs no
  constants and imports no Revit or pyRevit symbol.
- The move was scoped by computing each candidate's **transitive call closure**: only functions whose
  whole closure is host-free were taken. The Revit-bound `classify_rcc_element`,
  `build_logical_rcc_collections` and `get_element_identity_text` deliberately stay in `script.py`,
  which drops from 5,931 to 5,822 lines and now imports the rules by their existing names, so the
  classifier's behavior is unchanged.

### Changed (declared-but-invalid dimensions)
- `normalize_element_spec` now distinguishes an **absent** dimension (takes the kind default) from
  one **declared with a non-positive value** (kept as `None` so validation reports it). The first
  implementation silently substituted the default, which would have built an element the caller
  never asked for.

### Tests
- `test_xlsx_writer.py` registers `rule_engine.py` as an engine module and adds 4 checks pinning the
  P8 split: the rule engine imports no host symbol, all eight rules resolve from `rule_engine.py`,
  and both Revit-bound classifier functions still resolve from `script.py`. The existing v1.8.10
  routing regression (F2A / CF1A / WF1 cases included) now runs the rules from their new home.
- `test_xlsx_writer.py` adds 12 checks covering level sorting, per-kind defaults, column/footprint
  volumes, full-spec acceptance, summary totals, every unbuildable-declaration finding, the
  no-top-level volume guard, clean and drifted actual-versus-declared comparison, unit round-trips,
  and an architectural guard that the engine imports no Revit or pyRevit symbol. All checks pass.

### Verified (live)
- **Tested (live):** a `pyrevit run` session against Revit 2025 (`25.0.2.419`) built all four kinds
  from one spec into a new document and saved it. Read-back volumes matched the declared spec
  exactly with `build_findings: []` — Column `C1` 0.4050 m³, Beam `B1` 0.4140 m³, Slab `S1` 1.8000 m³,
  Foundation `F1` 1.0125 m³, total 3.6315 m³. Families resolved were
  `M_Concrete-Rectangular-Column`, `M_Concrete-Rectangular Beam`, `M_Footing-Rectangular` and a
  duplicated floor type.
- The owner's working Revit session was not touched: `pyrevit run` starts its own Revit process and
  the builder only ever writes a newly created document.
- **Tested (live, IronPython engine):** a second `pyrevit run` session compiled the refactored
  `script.py` (5,822 lines) inside Revit, imported `rule_engine` and `authoring_spec` from the
  extension lib, and re-ran the F2A / F2AB / WF1 / label-normalization rules from their new module.
  `pyrevit run` uses the IPY2712 engine, so this proves the split imports and behaves under
  IronPython; the production CP3123 path and the BOQ dialog itself still need the project owner.

### Verified (live) — P10-03 `Other` route, previously unexercised
- The authoring API built a fixture whose identities deliberately carry neither a known code nor
  `slab`/`foundation` wording, including a foundation on the `M_Cup Foundation` family so the family
  name itself contributes no routing token.
- A `pyrevit run` session then extracted the **real 21-function classification closure** from
  `script.py` and `lib/` (the same extraction `test_xlsx_writer.py` uses, so production source ran,
  not a copy) and classified the real Revit elements:
  - Floor `423208` `Floor / Deck Panel PX1` → **Slab / Other** ("Unknown identity retained under
    source Floor as Other")
  - Structural Foundation `424050` `M_Cup Foundation / Pedestal PD1` → **Foundation / Other**
  - Control Floor `423217` `Typical Slab ST1` → **Slab / Slab**, confirming the fixture does not
    simply fail everything
- The audit balanced (`Floors=2; Structural Foundations=1; Slab=2; Foundation=1; Duplicates=0;
  Unclassified=0; Other=2`), `collect_routing_findings` produced 2 findings, and
  `build_unmapped_element_report` emitted 2 data rows, both
  `Uncertain Slab/Foundation mapping`.
- 8 of the 21 closure functions resolved from the new `lib/rule_engine.py`, so the P8 split was
  exercised on real elements in the same run.

### Verified (live) — full BOQ export on the `Other`-route fixture
- The shipping `script.py` was run **headlessly through its own queued-job path** (the same
  `agent_export_job` contract the Agent Bridge uses), against the authored fixture in a live
  Revit 2025 session. No reimplementation: the production script took the headless branch and both
  workbooks came out of the normal export pipeline with the owner's saved dialog settings.
- **Classic:** 9 sheets, canonical validator `260/260` cells, `0` mismatches, SHA-256
  `8363342f302b738e71e82ae494e7c9859cb8a587326a6d37e6386f1c0cc17dad`.
- **Site:** 5 sheets, canonical validator `194/194` cells, `0` mismatches, SHA-256
  `8ebd62e578df68f63e86e0bcb0b0931af7276911c7a1bad14bf257d9f33408c6`.
- Both workbooks carry an `Unmapped Elements` sheet listing exactly two
  `Uncertain Slab/Foundation mapping` rows, now with real levels resolved by the export:
  - `Slab | 423208 | Level 2 | Unknown identity retained under source Floor as Other | Family/Type: Floor / Deck Panel PX1`
  - `Foundation | 424050 | Level 1 | Unknown identity retained under source Foundation as Other | Family/Type: M_Cup Foundation / Pedestal PD1`
- The control element `423217` (`Typical Slab ST1`) appears only under grade/material issues and
  **not** under routing, confirming the routing rows are specific to the `Other` route.

### Verified (live, project owner) — P10-03 closed
- The project owner ran the **real BOQ dialog** on the fixture (Nudge → Generate → RCC BOQ, `Mark`
  selected on the Slab and Foundation tabs) and exported
  `20260918-AgentTest-OtherRoute-CONCRETE_FINISHING_BOQ.xlsx`.
- That dialog workbook and the agent's headless Classic workbook have **identical sheet lists (9)**
  and **byte-identical `Unmapped Elements` tables (8 rows)**, including both
  `Uncertain Slab/Foundation mapping` rows with levels resolved.
- Detail sheets carry the selected `Mark` column with the authored values (`PX1`, `ST1`, `PD1`) and
  the read-back quantities (Slab `1.8` / `0.75` m³, Foundation `1.2658` m³).
- P10-03 is therefore **done**: routing, missing-grade and missing-material reporting are all
  confirmed on a real `Other`-route model through the shipping dialog.

### Known limitations
- The BOQ pushbutton was **not** opened in a live Revit session by an agent. The P8 move is
  behavior-preserving by construction (verbatim functions, unchanged names, harness plus in-Revit
  compile and rule checks), but a full Classic/Site export on a real project remains owner work.
- The authoring builder has been exercised on the metric structural template only, and it writes
  identity through duplicated type names plus Mark/Comments - not through shared parameters.
- `expected_element_volume_m3` models a prism (footprint x thickness). On the `M_Cup Foundation`
  fixture element it therefore reported a real difference - built 1.2658 m3 against a declared
  1.0125 m3 - because that family is not a plain box. The comparator behaved correctly; the spec
  simply cannot describe shaped families, and volume comparison should be read as meaningful only
  for prismatic ones.
- **The dialog and the headless job path differ at the export guard.** `script.py` refuses an export
  with zero selected parameters and no Rebar in the model, but the condition ends with
  `and _headless_export_job is None`, so a queued job is exempt. An agent-run headless export can
  therefore succeed where the dialog would stop the user, and it cannot on its own prove the dialog
  path. This surfaced during P10-03: the agent's export ran with no parameters selected, while the
  owner's dialog run required one (`Mark`) before it would export.

---

## [v1.23.2] - 2026-09-17

### Fixed (footing code routing)
- **Owner decision (2026-09-17):** `F<number><letter>` codes such as `F2A` and wall-footing codes
  such as `WF1`/`WF2` are footings, with no separate Wall Footing subtype.
- `code_token_match` now accepts one optional variant letter after the number for `F`, `CF` and the
  new `WF` prefix (`F2A`, `CF1A`, `WF1`). `S<number>` stays strict. Bare `WF` and two-letter
  suffixes such as `F2AB` are still rejected.
- The Footing branch matches `F` and `WF` codes, so a `Foundation Slab: F2A` identity routes to
  Foundation / Footing before the generic `slab` wording is considered. `CF1A` routes to Combined
  Footing.

### Tests
- `test_xlsx_writer.py` adds routing cases for `F2A`, `CF1A`, `WF1`, `Foundation Slab: F2A`,
  `Foundation Slab: WF2`, plus strict-boundary rejection of `WF` and `F2AB`. The five new routing
  cases fail on the `v1.23.1` classifier and pass after the change; all checks pass.

### Verified (live)
- **Tested (live):** isolated Secondary Revit 2025 (`25.0.2.419`) opened the owner-saved Revit 2025
  scratch copy `R25-P10-03-TEST-KINDER-GARTEN-ST`; the owner's Primary Revit was untouched and the
  model was not saved by the bridge.
- Classic validated 5,116/5,116 cells across 12 sheets and Site 3,413/3,413 across 8 sheets, both
  with zero mismatches (Classic SHA-256
  `edf47f82c84a66bf064cb09d890cca3fdf595d8d4e4e608292aea4e18f711dc6`).
- Compared with the `v1.23.1` export, exactly four elements moved from Slab to Foundation, confirmed
  by native reads as `F2A` (`347475`, `347539`), `WF2` (`348393`) and `WF1` (`376917`), all
  `Structural Foundations` / `Foundation Slab`. Slab went from 73 to 69 and Foundation from 30 to 34;
  the combined ID set is unchanged with no overlap. `BOQ by Level` lost only its now-empty
  Foundation Level x Slab row (the 5-cell difference). GRAND TOTAL remains `=SUM(B2:B6)`.

---

## [v1.23.1] - 2026-09-17

### Fixed (Classic BOQ Summary GRAND TOTAL)
- The Classic `BOQ Summary` GRAND TOTAL formulas ended one row early (`SUM(B2:B5)` with five
  category rows), so the last exported category - Foundation whenever it was present - was left out
  of every grand total. The range now ends on the last category row (`SUM(B2:B6)`). The per-category
  rows, element sheets, Site Summary and `BOQ by Level`/`BOQ by Grade` SUMIF sheets were unaffected.
- The workbook validator compares cell text/formulas against canonical rows built by the same
  engine, so it could not detect this wrong-but-consistent formula; the harness now asserts the
  GRAND TOTAL range explicitly.

### Tests
- `test_xlsx_writer.py` adds a GRAND TOTAL range check. It fails against the `v1.23.0` engine and
  passes after the fix; all checks pass.
- `test_rest_api.py` was stale since `v1.23.0` (it still required exactly two POST routes and failed).
  It now requires the three bounded write routes, including the structural-material route, and
  passes. RestCore and RestMcp suites pass unchanged.

### Verified (live) / findings
- **Tested (live):** isolated Secondary Revit 2025 (`25.0.2.419`, Bridge `v2.5.0` channel
  `secondary`) opened a scratch copy of `STRUCTURE - KINDER GARTEN.rvt`
  (`P10-03-TEST-KINDER-GARTEN-ST`) while the owner's Primary Revit was untouched; the shared add-in
  manifest was restored to Primary right after port `48886` opened. The model was not saved.
- Before the fix, Classic (5,121/5,121 cells, 12 sheets) and Site (3,413/3,413 cells, 8 sheets)
  validated with zero mismatches and showed `GRAND TOTAL =SUM(B2:B5)` over 137 Beam, 60 Column,
  8 Structure Wall, 73 Slab and 30 Foundation rows. The final `v1.23.1` Classic export validated
  5,121/5,121 cells across 12 sheets with zero mismatches, labels the tool `v1.23.1` and reads
  `=SUM(B2:B6)` (SHA-256 `b1bf91146ceb64d3a843af186b490ea64f774eae854e2b9b2585adf2bb2a671f`).
- T-02 sample: 20 exported rows (four each from Beam, Column, Structure Wall, Slab, Foundation)
  match native Revit Volume/Area **at Revit's displayed precision** (0.01 m3, 1 m2). The bridge
  returns display strings, so full-precision agreement is not claimed.
- P10 reported 314 findings (308 missing concrete grade, 6 Column missing structural material) and
  **zero routing findings**: every Structural Foundation in this model uses the `Foundation Slab`
  family, so the generic `slab` wording routes any non-exact code to Slab and no element reaches
  `Other`. P10-03 `Other`-route findings therefore remain unexercised live.
- **Open classification question (not changed):** `F2A` (2), `WF1` and `WF2` footings at
  `-02-Foundation Level` (0.5-0.6 m) are routed to the Slab sheet, because `F2A`/`WF1` are not exact
  `F<number>` codes and the family name contains `Slab`. Whether these codes are footings is an
  owner decision before any classifier change.

---

## [v1.23.0] - 2026-09-15

### Added (controlled Structural Material assignment)
- Agent Bridge `v2.5.0` adds a read-only `GET /rcc-boq/materials` catalog, bounded to 1,000
  materials from the active document, plus matching CLI and `rcc_boq_materials` MCP access.
- Added a dedicated `POST /rcc-boq/element-types/<element_id>/structural-material` operation and
  `rcc_boq_set_structural_material` MCP tool. It accepts only an explicit active-document material
  ID and an ElementType in Structural Foundations, Floors, Structural Framing, Structural Columns
  or Walls.
- Structural Material writes default to dry-run, require the temporary Revit write session for
  apply, support an optimistic `expected_current_material_id` guard (`0` means blank), perform
  native read-back, and expose a forced-failure rollback probe for isolated QA.
- Writable family types use the built-in type parameter. System types whose Structural Material is
  derived/read-only use only an unambiguous compound-structure `Structure` layer; the operation sets
  that layer's material and designates its structural-material index without adding/deleting layers.

### Safety
- The general `set_parameter` operation still rejects every `ElementId` parameter. Structural
  Material is available only through the new narrow type/material endpoint; arbitrary ElementId
  writes remain unavailable.
- The bridge still exposes no save, delete, arbitrary path or arbitrary code operation. A successful
  assignment changes only the open Revit document and reports `document_saved=false`.

### Verified / remaining
- **Tested (host-free):** Primary and Secondary Revit add-in/Gateway builds pass with zero warnings
  and errors; Primary and Secondary Core and 11-tool MCP protocol suites pass; Python compilation
  and the complete 189-check XLSX regression harness pass.
- **Tested (live):** isolated Secondary Revit 2025 loaded `v2.5.0` on the saved `TEST COPY` of UMA
  NIWAS while the shared manifest was restored to Primary. Its bounded catalog returned all 631
  materials. All 13 affected Slab/Foundation types resolved one structural layer at index 0 with
  the correct existing layer material (`RCC_SLAB`, `RCC_FOOTING` or `PCC_FOOTING`).
- Consent-disabled apply was rejected without change. A consented F1 forced-failure probe returned
  `RolledBack`, and fresh read-back confirmed effective Structural Material returned to blank while
  the layer's existing `RCC_FOOTING` material remained unchanged.
- With owner-enabled consent, all 13 guarded type transactions committed and independent generic
  element reads returned the expected Structural Material. The 316 prior missing-material findings
  dropped to zero. The final Classic workbook contains zero `(No Grade)`, only the independent 20
  Beam missing/zero-volume findings, and validates 12,165/12,165 cells across 12 sheets with zero
  mismatches (SHA-256
  `0d0dbde94cf562825c34b3fb2e0be03c954420702de843e5d226a8b040864e27`).
- **Persistence verified:** after the owner manually saved `TEST COPY`, the Secondary Revit process
  was normally closed and the saved RVT reopened with write consent disabled. Fresh reads of all 13
  types matched their expected `RCC_SLAB`, `RCC_FOOTING` or `PCC_FOOTING` values.
- **Installed (Primary production):** with Revit 2025 closed, `scripts/install_rest_bridge.ps1`
  published Primary `v2.5.0` with zero warnings/errors and pointed the Revit manifest at
  `RestBridge\v2.5.0\RccBoq.RestRevit.dll` (previous `v2.4.0` manifest backed up). Installed
  binaries carry the Primary pipe/port constants, and the installed STDIO MCP server completed an
  initialize/tools-list handshake reporting `v2.5.0` with all 11 tools. Codex `rcc-boq-v2` now
  targets the `v2.5.0` MCP server (previous config backed up).
- **Tested (live, Primary):** a fresh Revit 2025 (`25.0.2`) launch opened port `48885` within ~35 s.
  Authenticated REST status and the installed MCP `rcc_boq_status` tool both returned API `2.5.0`,
  channel `primary`, `revit_connected=true` and write consent disabled; an unauthenticated request
  returned `401`. With no model open, document and material-catalog reads returned the bounded
  `No active Revit document` error.
- **Tested (live, Primary, open model):** Revit 2025 was relaunched on the saved UMA NIWAS
  `TEST COPY`. The document read returned `TEST COPY`; REST and installed-MCP material catalogs each
  returned all 631 materials untruncated, including `RCC_SLAB`, `RCC_FOOTING` and `PCC_FOOTING`.
  A generic read of type `3070326` (`F1 - 600MM`, Structural Foundations) returned Structural
  Material `RCC_FOOTING`, matching the Secondary-assigned persisted value. Revit closed without a
  save prompt, and the RVT size, timestamp and SHA-256 were unchanged. **Unverified on Primary:**
  the Structural Material dry-run/apply path (an agent-side permission policy blocked the dry-run
  call; it remains verified only on Secondary).

---

## [v1.22.2] - 2026-09-15

### Fixed (authoritative concrete-grade fields)
- Concrete grade now comes only from the owner-confirmed Text parameters `GRADE OF CONCRETE`
  and `Grade`, matched case-insensitively. `Grade of Concrete` has deterministic precedence over
  `Grade`; for each name, a blank or invalid instance value falls through to its type value.
- Removed grade inference from `Structural Material`, `Material` and element/type identity text.
  Those fallbacks could hide missing `GRADE OF CONCRETE` model data by inventing a grade from a
  secondary source. Structural Material remains independently available to the P10 missing-material
  rule; only grade resolution changed.
- Grade spellings `M40`, `M-40` and `M 40` still normalize to canonical `M40`. If neither
  authoritative field contains a recognized M10-M80 token, the export writes `(No Grade)` and P10
  reports the element as missing concrete grade.
- Corrected the P10 missing-grade detail so it names only `GRADE OF CONCRETE` and `Grade`; it no
  longer claims that material or identity-text fallback was attempted.

### Verified
- `python -m py_compile` passes for `script.py`, `validation_engine.py` and `export_engine.py`.
- `python test_xlsx_writer.py` passes (189 checks), including uppercase-name matching, field
  precedence, instance-to-type fallback, invalid-value fallback to the second authoritative field,
  explicit rejection of material and identity-text inference, and authoritative P10 detail text.
- **Tested (live):** an isolated Secondary Revit 2025 Classic export of
  `RVT-25-AMANI_KNOWLEDGE_PARK-ST` ran `v1.22.2` without saving the model. The published workbook
  validated 93,623 of 93,623 non-empty cells across 12 sheets with zero mismatches. Its element
  sheets read `M40` for 2,404 Beams, 729 Columns, 271 Structure Walls, 1,089 Slabs and 13
  Foundations, and `BOQ by Grade` grouped all five categories under `M40`. The final workbook hash
  after the P10 wording correction is
  `9513748d6dcbca7e6ab4d29476250f9496ff7355301cc2db214262aa52da0e9d`.
- The same live export reported 36 Structure Walls as `(No Grade)`. Read-only API inspection of
  sample instances and their types confirmed the authoritative grade field is blank/absent, so
  these are genuine model-data findings rather than resolver false positives.
- **Second-project live verification:** an isolated Secondary Classic export of
  `R25-UMA NIWAS BUILDING-ST-31-08-2026` validated 13,895/13,895 cells across 12 sheets with zero
  mismatches and did not save the model. The authoritative fields produced M30/M40/M10 groups,
  including M40 for 3 Beams, 185 Columns, 12 Structure Walls, 2 Slabs and 10 Foundations.
  The remaining `(No Grade)` set is 3 Beams plus 9 Columns. Read-only inspection of all 12
  instances and their three unique types (`B43(a)`, `B55(h)` and `FC1`) confirmed blank/absent
  `GRADE OF CONCRETE`/`Grade` data. Final workbook SHA-256:
  `2a59e0d5ef056ac41f8314c1892a41eca4d1e366ea8b3ed2c8085347388e71ba`.
- With the owner's explicit grade confirmation, the Secondary Agent Bridge set M30 on the three
  Beam instances and M40 on the nine FC1 Column instances. All 12 writes passed blank-current-value
  guards and fresh native read-back; the document remained unsaved. The post-fill Classic export
  contains zero `(No Grade)` elements and validates 13,745/13,745 cells across 12 sheets with zero
  mismatches (SHA-256
  `844f64a89aec50a7ba8d61cd5ebf9b43095b4993da08916415e86e109e42572f`).
- The post-fill workbook still correctly reports independent model-quality issues: 20 Beams with
  missing/zero computed Volume and 316 Slab/Foundation elements with missing Structural Material.
  Six zero-volume Beam IDs from the earlier workbook were already unresolvable through the active
  document API before the grade writes and are absent from the later snapshot; the bridge exposes
  no delete operation.

---

## [v1.22.1] - 2026-09-15

### Fixed (P10-03 concrete grade from structural material)
- `resolve_concrete_grade` step 2 now reads `Structural Material` (instance, then type) before
  `Material`. Before, it looked up only a parameter named `Material`, which the surveyed Revit 2025
  models do not have, so a grade carried in a structural material name (for example
  `Concrete - M25`) was never used and such elements fell through to identity text or `(No Grade)`.
- A new `structural_material_candidates` helper yields every non-empty material name in priority
  order. The grade resolver tries each one, so a mix-free `Structural Material` such as `RCC_BEAM`
  never hides a graded `Material`. `resolve_structural_material` (P10-02) now returns the first
  candidate, so the missing-material check is unchanged.
- Grade precedence is unchanged: grade parameter, then material, then identity text. Where a model
  carries different grades in its material name and its identity text, the material grade now wins,
  as the documented order always intended.

### Verified
- Before and after on the real function source: with an instance `Structural Material` of
  `Concrete - M25` or a type value of `M35 RCC`, the `v1.22.0` resolver returns `(No Grade)`;
  `v1.22.1` returns `M25` and `M35`.
- `python test_xlsx_writer.py` passes (188 checks), including a new P10-03 check covering
  grade-parameter precedence, instance and type Structural Material, a `Material` fallback behind a
  mix-free Structural Material, an invalid grade parameter falling through, identity text and
  `(No Grade)`. The P10-02 material checks still pass after the helper refactor.
- **Unverified (live):** the two surveyed models name materials without a grade token (`RCC_BEAM`,
  `RCC_COLUMN`, `RCC_WALL`, `Concrete, Cast-in-Place gray`), so a live export there cannot show a
  changed grade. No live export has been run for this release.

---

## [v1.22.0] - 2026-09-15

### Added (P10-02 missing structural material)
- The Unmapped Element Report also flags `Missing structural material` for exported concrete
  elements whose structural material resolves to blank or `<By Category>`.
- `resolve_structural_material` in `script.py` reads the per-element parameter index the export
  already builds: instance `Structural Material`, then type `Structural Material`, then `Material`.
  An instance value that is blank falls through to the type. No extra ParameterSet iteration is
  added.
- Materials reach the report through a separate Element ID map, so no workbook column is added.
  Material is judged only for elements whose parameters were indexed.
- Live survey that shaped the rule, on a scratch copy of `R25-UMA NIWAS BUILDING-ST-31-08-2026`:
  Beams (56) and Columns (16) carry an instance value (`RCC_BEAM`, `RCC_COLUMN`); Walls and
  Foundation Slabs expose it on the type, and 32 of 34 sampled Foundation Slab types were blank.
  No sampled element had a parameter literally named `Material`.

### Observed, not changed
- `resolve_concrete_grade` step 2 looks up a parameter named `Material`, which the surveyed models
  do not have; their material lives in `Structural Material`, so grade-from-material never fires
  there. It has no effect on these models because their material names carry no M-grade token.
  Left for a separate owner decision.

### Docs
- `README.md` Secondary-channel QA now restores the Primary manifest by copying a saved backup.
  Re-running the installer for Primary fails while the Primary Revit is running, because its
  add-in and Gateway files are locked, and would leave the shared manifest on Secondary.

### Verified
- `python test_xlsx_writer.py` passes (187 checks), including 3 new P10-02 checks: the report rule
  for blank, `<By Category>`, present and unresolved materials; the resolver scope order and
  fallbacks; and export-handler wiring that only records indexed elements.
- The survey ran in an isolated second Revit 2025 window on the Secondary bridge (port 48886) against
  a scratch copy of the model. The owner's working Revit and the Primary bridge were never called,
  and the shared add-in manifest was restored to Primary (hash verified) as soon as the test Revit
  had loaded.
- Live pyRevit Site export of the scratch copy in the isolated test Revit, with write consent
  granted by the owner in that window only; the model was not saved. 8,245 of 8,245 cells
  validated across 8 sheets with zero mismatches. `Unmapped Elements` lists 354 findings: 294 on
  the Slab sheet and 22 on the Foundation sheet for missing structural material, 3 Beam and
  9 Column for missing concrete grade, and 26 Beam for missing or zero volume.
- No Beam, Column or Structure Wall reported missing material, matching the survey (`RCC_BEAM`,
  `RCC_COLUMN`, `RCC_WALL`). Spot check through the Secondary bridge: Foundation Slab elements
  `3141335` and `3178190` (`BS_300MM`) and `3313456` and `3313469` (`RCC_SLAB_125MM`) have no
  instance Structural Material and a blank type Structural Material, so they are true findings.

---

## [v1.21.1] - 2026-09-15

### Fixed (export popup sheet listing order)
- The completion popup "Workbook sheets" line now lists sheets in the same order as the workbook.
  It joins the keys of the mapping returned by the workbook writers, and both writers returned a
  plain `dict`: IP27 keeps no key order (the owner saw a scrambled list in the `v1.21.0` popup), and
  even on CPython `Summary` was stored last although it is the first workbook sheet.
- `write_basic_xlsx` and `write_site_xlsx` now return an `OrderedDict` built from `sheet_names`,
  the same list that writes `workbook.xml`. The export popup code in `script.py` is unchanged; only
  the version moves to `1.21.1`. The workbook contents and sheet order were already correct and do
  not change.

### Verified
- Reproduced before the fix on CPython: both writers returned keys ending in `Summary` while the
  workbook began with it. After the fix both key orders match `workbook.xml` exactly.
- `python test_xlsx_writer.py` passes (184 checks), including 2 new checks that compare each
  writer's returned key order with the sheet order read back from `workbook.xml`.
- Owner-confirmed in the interactive dialog on `20260225-BBS_BEAM_RBM_SALES-P1` (2026-09-15): the
  `1.21.1` popup lists `Summary, Beam, Column, Structure Wall, Slab, Foundation, Rebar, Rebar
  Summary, Rebar BBS, BOQ Summary, Structural Assembly, BOQ by Level, BOQ by Grade, Costing,
  Unmapped Elements`, matching the workbook, with validation PASS on 166,835 cells and the same
  8,696 unmapped findings.

---

## [v1.21.0] - 2026-09-15

### Added (P10 Unmapped Element Report - first slice)
- New dependency-free `lib/validation_engine.py`, the planned P9 landing point
  (`PROJECT_STRUCTURE.md` section 9), now carrying the P10 first slice.
  `build_unmapped_element_report(data_result, routing_findings)` lists exported Beam, Column,
  Structure Wall, Slab and Foundation elements with a missing concrete grade (blank or
  `(No Grade)`), a missing, zero or non-numeric `Qty: Volume (m3)`, or an uncertain Slab/Foundation
  route. `collect_routing_findings` flattens the existing v1.8.10 classifier audit (`Other` routes
  and duplicate routing sources) into plain rows, so the engine never touches Revit objects.
- Only elements present in the export are reported, so Slab/Foundation subtype filters and
  "Export selected only" never list elements missing from the workbook. Grade and volume are judged
  only when the row carries those columns; Rebar is excluded.
- Both workbook writers accept `unmapped_report`. When it holds findings, an `Unmapped Elements`
  sheet (Category, Element ID, Level, Issue, Detail) is appended: after Costing in the Classic
  workbook, where the Summary cover lists it, and after Structural Assembly in the Site workbook,
  inside the site title bands under `RCC - MODEL VALIDATION`. A header-only report adds no tab, so a
  clean model keeps its familiar workbook.
- The completion popup adds one line with the finding count. The existing routing note is kept.

### Changed
- Site export now resolves concrete grade as well (`build_element_data(include_grade=True)`) so the
  P10 grade check runs in the default Site format. Site detail sheets still hide the Grade column,
  and costing, assembly and the site summary ignore the key. The harness contract that asserted
  "Site skips grade work" now asserts that Site keeps P10 grade resolution.
- `build_site_tabular_sheet` gains an optional `band_title` (default unchanged,
  `RCC - REINFORCEMENT BBS`) and column widths for the Issue and Detail headers.

### Roadmap order
- P10 was taken before P7, P8 and P9 by owner decision on 2026-09-15. A live agent read of
  `20260225-BBS_BEAM_RBM_SALES-P1` found `GRADE OF CONCRETE` present but empty on 400 of 400
  sampled structural elements, which today exports a BOQ by Grade collapsed into `(No Grade)` with no
  warning. `todo-list.md` allows code- and data-driven reordering.

### Verified
- `python test_xlsx_writer.py` passes (182 checks), including 10 new P10 checks: engine rules fed by
  the real classifier audit output, Classic and Site workbooks re-read by the canonical validator,
  no empty tab for a clean report, no Grade column on Site detail sheets, and export-handler wiring.
- Live pyRevit export of `20260225-BBS_BEAM_RBM_SALES-P1` on Revit 2025 build `25.0.2.419`, run
  through the Agent Bridge headless export with owner-granted write consent. The model was not saved.
  - Site: 118,821 of 118,821 cells validated across 11 sheets with zero mismatches. `Unmapped
    Elements` is the last sheet, under `RCC - MODEL VALIDATION`, with 8,696 findings: 8,667 missing
    concrete grade and 29 missing or zero volume (28 Beam, 1 Slab). The Beam site sheet carries no
    Grade column. Job time 124 s.
  - Classic: 166,835 of 166,835 cells validated across 15 sheets with zero mismatches. `Unmapped
    Elements` follows Costing, the Summary cover lists it, and it holds the same 8,696 findings.
    Job time 149 s.
  - Cross-check: missing-grade findings equal the `(No Grade)` rows on every element sheet (Beam
    4,031, Column 1,311, Structure Wall 849, Slab 2,318, Foundation 158), and BOQ by Grade holds only
    `(No Grade)`, the silent collapse this phase exists to surface.
  - Spot check: Beams `2970078`, `2970079` and `2970080` read back through the bridge with an empty
    Revit Volume despite lengths of 3141, 2697 and 775 mm, and Slab `3026042` reads `0.00 m3`. These
    are real model issues, not false positives. No uncertain routing occurred on this model.
- Owner-confirmed in the interactive dialog on the same model: a Classic export (validation PASS,
  166,835 cells) ended with `Unmapped elements: 8696 finding(s) - see the 'Unmapped Elements' sheet
  and use Manage > Select by ID to fix them in the model.` Processing time 57.2 s (Revit data
  36.4 s, workbook 20.8 s).
- **Unverified:** routing findings on a model with `Other` routes, and Site export time against a
  v1.20.0 baseline.
- **Observed, pre-existing:** the popup "Workbook sheets" listing prints in scrambled order under
  IP27 because it joins the keys of a plain `dict`. The workbook itself keeps the correct order.
  Not introduced by this release.

---

## [v1.20.0] - 2026-09-12

### Changed (Agent Bridge write-session window)
- The Agent Bridge consent window is now **1 hour** instead of 15 minutes. `AgentBridgeCommand`
  holds the single `WriteDuration` constant (`TimeSpan.FromHours(1)`); the TaskDialog strings are
  derived from it through `FormatWriteDuration`, so the dialog text can no longer drift from the
  duration actually granted. `WriteSessionConsent` was untouched and still applies no clamp of its
  own.
- The consent model is otherwise unchanged: write access stays opt-in from Revit's Agent Bridge
  button, "Disable write access now" still revokes immediately, and the longer window only widens
  the period during which an already-consented agent may write.
- Bridge installs as **v2.4.0** (`RccBoq.RestRevit`, Gateway and MCP). The `v2.3.0` install tree is
  left in place, so the `.addin` manifest can be pointed back at it to roll back.
- `BridgeConstants.Version` and `BridgeConstants.ApiVersion` were bumped to `2.4.0` alongside
  `Directory.Build.props`. The bridge version lives in those two places and they are not derived
  from each other: a live `status` probe after the first `v2.4.0` install still reported
  `api_version 2.3.0` because only the props file had been bumped. Both constants have moved
  together on every bump since `v2.0.0`, so both were moved here too.

### Verified (native Revit 2025)
- Live read path confirmed against the running bridge before the change: `status` returned
  `api_version 2.3.0`, `revit_connected true` and an active 15-minute write session; `document`
  returned `20260225-BBS_BEAM_RBM_SALES-P1` on Revit build `25.0.2.419`.
- `dotnet build RccBoq.RestRevit -c Release` and the full install script pass with 0 warnings and
  0 errors. Binary string inspection confirms the installed `v2.4.0` assembly carries `1 hour` and
  no longer carries `Enable write access for 15 minutes`, while the retained `v2.3.0` assembly
  still carries the old strings.
- Confirmed in a live Revit 2025 session. The project owner restarted Revit and reported the
  consent dialog reading "Enable write access for 1 hour"; an agent `status` probe against that
  session returned `RemainingSeconds: 3574`.
- After the version-constant correction was installed, an agent started Revit 2025 and polled the
  bridge: it came up in 19s reporting `api_version 2.4.0`, `extension_version 2.4.0` and
  `revit_connected true`, with `write_session.Enabled false` on a fresh start — the consent gate
  holding as designed. With no document open, `document` and `selection` returned a clean
  `No active Revit document` error and `last-validation` served its cached record while correctly
  flagging `matches_active_document false`.
- **Not agent-verifiable:** enabling write consent requires clicking the Agent Bridge TaskDialog in
  Revit, so the 1-hour grant itself rests on the project owner's confirmation above. The dialog
  code is byte-identical between that build and the reinstalled one; only the version constants
  changed.

---

## [v1.19.1] - 2026-09-11

### Fixed (IP27 selected-column order)
- Revit's active IP27 engine no longer builds export rows with an unordered Python 2 `dict`.
  `OrderedDict` now preserves `Element ID`, grouping fields, the exact Selected-list order, then
  remaining automatic quantity fields through Classic workbook generation.
- A regression asserts the IP27-specific ordered-row contract. The defect was found by a fresh
  native persistence/export test: the JSON settings restored the requested Rebar order correctly,
  but the `v1.19.0` Classic workbook interleaved automatic fields between those selections.

### Verified (native Revit 2025)
- Compilation and the full XLSX harness pass. After a fresh test-Revit restart, the saved Rebar
  selection restored as `Element ID → Diameter → Total Weight`; a `v1.19.0` control export exposed
  the unordered IP27 header, then the `v1.19.1` export placed those fields consecutively at columns
  3-5 after `Element ID, Level`.
- The corrected Classic workbook passed canonical validation across 118,101/118,101 cells and
  14/14 sheets with zero mismatches. It matched the active BBS test document and Revit did not save
  the model.

---

## [v1.19.0] - 2026-09-11

### Added (isolated multi-Revit rollback QA)
- Upgraded Agent Bridge to `v2.3.0`. Builds now support an explicit `Primary` channel on port
  `48885` and an isolated `Secondary` channel on port `48886`, each with its own mutex and Named
  Pipe. This lets native QA target a dedicated Revit process without taking bridge ownership from
  the user's working Revit session.
- Added consent-gated `force_rollback` to the existing bounded parameter-write operation. The probe
  sets one allow-listed parameter inside a normal Revit transaction, deliberately raises a
  controlled exception before commit, rolls back, and verifies the original value by fresh native
  read-back. The document is never saved automatically.
- `install_rest_bridge.ps1` accepts `-BridgeChannel Primary|Secondary`; Secondary installation uses
  a versioned `-secondary` folder and warns that the normal Primary manifest must be restored after
  the target test process starts.

### Verified
- Primary and Secondary Core/Revit/Gateway builds pass with zero warnings. Pipe serialization,
  MCP forwarding/schema, REST security checks and CLI compilation cover the rollback flag and both
  fixed loopback channels.
- Native Revit 2025 QA connected the dedicated BBS test document through Secondary `48886` while
  the working document remained connected through Primary `48885`. Rebar `3411763` `Comments` was
  temporarily set inside the controlled probe, the forced failure returned transaction status
  `RolledBack`, and fresh read-back restored the original blank value. The audit log recorded
  `verified=True`; the Revit document was not saved.
- A read-only P4/P5 audit compared the validated Classic and Site workbooks with the dedicated
  Revit process. All 4,031 Site Beam L/W/H rows matched native element/type dimensions within the
  formats' 1 mm rounding boundary. Classic/Site Rebar, BBS and diameter summaries independently
  reconciled at 11,903 bars, 25,439.37 m and 30,130.966 kg.
- Native reads matched one single bar plus fixed stirrup, straight, L-shape, C-shape and both U-ring
  samples. Variable Rebar `3411763` retained blank Cutting Length, its native average-only status
  and unchanged quantity/length. The full XLSX harness also passed. Live dialog selection-order
  persistence remains a separate UI-bound P5 check.

---

## [v1.18.2] - 2026-09-09

### Fixed (live headless export)
- Assembly-profile normalization now treats CPython/.NET null-coercion `SystemError` as a missing
  optional factor instead of aborting export.
- Canonical validation explicitly releases its ZIP wrapper before atomic publication, and workbook
  publication retries transient Windows file locks. Headless failures retain the innermost bounded
  traceback so native failures remain actionable without exposing an arbitrary file path.

### Verified (native Revit 2025)
- Agent Bridge `v2.2.1` queued the existing pyRevit BOQ command against
  `20260225-BBS_BEAM_RBM_SALES-P1` without opening the BOQ or Save dialogs.
- Site output passed `70,085 / 70,085` canonical cells across `10 / 10` sheets with zero mismatches.
  Classic output independently passed `118,101 / 118,101` cells across `14 / 14` sheets with zero
  mismatches. Each validation SHA-256 matched the published workbook on disk.
- The consent-off apply guard passed before testing; the 15-minute write session later expired back
  to disabled automatically. Neither export saved the Revit document.

---

## [v1.18.1] - 2026-09-09

### Fixed (live Revit command discovery)
- Upgraded Agent Bridge to `v2.2.1`. Live Revit dry-run showed that pyRevit registers the BOQ
  button with the fully-qualified identifier
  `CustomCtrl_%CustomCtrl_%Nudge%Generate%BOQ`; command discovery now tries that journal-confirmed
  identifier first while retaining the earlier compatibility candidates.

### Verified
- Revit 2025 loaded Agent Bridge `v2.2.0`, connected to the intended BBS test document, and safely
  rejected command discovery before any job or workbook was created. The exact BOQ identifier was
  then recovered from the same native Revit journal and added to the REST regression contract.

---

## [v1.18.0] - 2026-09-09

### Added (headless Agent export; host-free verified)
- Upgraded Agent Bridge to `v2.2.0` with a consent-gated, dry-run-first BOQ export job. The bridge
  posts the existing Nudge RCC BOQ pyRevit command, so classification, quantities and workbook
  generation are not duplicated in native code.
- Added a hidden one-shot mode to the existing BOQ command. It consumes only a schema-checked job
  for the exact active document, bypasses WPF and Save dialogs, preserves saved user preferences,
  forces quantities on, prevents Excel auto-open, and publishes the existing canonical validation.
- Exports use unique names only inside `%LOCALAPPDATA%\RCC_BOQ\AgentExports`; arbitrary output paths,
  overwrite requests and Revit document save remain unavailable.
- Added REST `POST /rcc-boq/boq/export`, `GET /rcc-boq/boq/export-status`, MCP tools
  `rcc_boq_start_export` / `rcc_boq_export_status`, and CLI commands `start-export` /
  `export-status`. Job status returns only bounded metadata and the output basename, never the
  internal filesystem path.

### Verified (host-free)
- Python compilation, the complete Classic/Site XLSX harness, Core/MCP/REST regressions and all
  Revit/Gateway/MCP builds pass with zero warnings. Tests cover queued/running/completed jobs,
  external-path rejection, dry-run defaults and the nine-tool closed MCP catalog.

### Verification boundary
- A fresh Revit restart must confirm pyRevit command discovery, native `PostCommand`, headless
  completion and retrieval of the generated validation report before this export operation is
  marked live-tested.

---

## [v1.17.0] - 2026-09-09

### Added (canonical BOQ validation; host-free verified)
- Added a dependency-free XLSX validator that reopens each temporary Classic or Site workbook and
  compares every persisted non-empty string, number and formula cell with the canonical in-memory
  rows derived from the active Revit document.
- Invalid workbooks are rejected before replacing the destination file. Successful validation
  publishes a bounded report at `%LOCALAPPDATA%\RCC_BOQ\last_boq_validation.json` containing only
  the workbook basename, SHA-256 digest, counts and capped mismatch diagnostics; no workbook path
  or Revit document path is exposed.
- Upgraded Agent Bridge to `v2.1.0` with read-only REST endpoint
  `GET /rcc-boq/boq/last-validation`, MCP tool `rcc_boq_last_export_validation`, and matching CLI
  command `last-validation`. The bridge reports whether the validation belongs to the active
  document.

### Verified (host-free)
- Python compilation and the complete XLSX harness pass for Classic and Site output. The harness
  confirms a clean cell-for-cell validation report and proves that a deliberately changed Beam
  element ID is detected as a mismatch.
- Revit add-in, Gateway and MCP builds pass with zero warnings; Core, MCP protocol and REST client
  regressions pass with seven closed-world MCP tools.

### Verification boundary
- Install/restart and one fresh live Revit export are required before claiming native report
  retrieval or active-document matching. This slice validates exporter input against persisted
  XLSX cells; unattended triggering of the pyRevit export dialog is not exposed.

---

## [v1.16.0] - 2026-09-09

### Added (Agent Bridge v2 foundation; host-free verified)
- Upgraded the local bridge protocol to `v2.0.0` and added a native Revit **Agent Bridge**
  pushbutton under Add-Ins.
- Assigned v2 its own current-user mutex, named pipe and localhost port `48885`, allowing migration
  testing beside a still-running v1 bridge without taking over the user's active Revit session.
- Added a user-controlled 15-minute write session; writes remain disabled by default and are
  disabled again during Revit shutdown.
- Added `rcc_boq_set_parameter` to MCP and REST with dry-run default, expected-current-value guard,
  explicit apply mode, Revit transaction rollback, bounded inputs and local audit logging.
- Kept the MCP surface closed-world: no arbitrary Revit method names, code evaluation, delete,
  document save or document-close operation is exposed.

### Verified (live Revit 2025 + automated tests)
- Revit add-in, Gateway and MCP builds pass with zero warnings; Core and MCP protocol regressions
  pass. The installed v2 bridge started beside the still-running v1 bridge without taking over the
  user's working Revit process.
- Authenticated status/document/element/Rebar reads passed against Revit `25.0.2.419`. A native
  `Comments` parameter dry-run produced the expected preview; apply with write consent disabled was
  rejected and a follow-up read confirmed that the model value remained unchanged.
- During an explicitly enabled write session, `Comments` was changed from blank to `Agent QA`,
  confirmed by read-back, restored to blank and confirmed again. The bridge reported
  `document_saved=false`; an expected-current-value mismatch was rejected without mutation, and
  manual consent revocation returned the bridge to read-only mode.
- The installed MCP executable passed a raw initialize/list/status exchange with all six tools and
  is registered in Codex as `rcc-boq-v2`.

### Verification boundary
- Automatic consent expiry and a forced-failure transaction rollback still require controlled
  native Revit QA.
- Background BOQ snapshot/export comparison is the next Agent Bridge slice and is not claimed here.

---

## [v1.15.1] - 2026-09-09

### Fixed (host-free verified; native Revit QA pending)
- Replaced the BOQ footer `DockPanel` with a responsive three-column grid so long status messages
  truncate with an ellipsis instead of squeezing the export-option controls off-screen.
- Preserved the complete status text in a tooltip and kept the options plus Close button at their
  natural widths.

---

## [v1.15.0] - 2026-09-08

### Added (P6; host-free and Revit 2025 verified)
- Added a pure Structural BOQ Assembly engine with measured Concrete, hosted Reinforcement and
  Formwork components plus configurable Binding Wire, Cover Blocks and Labour allowances.
- Added a safe Global / Custom profile: absent or invalid local factors stay blank and are labelled
  `Input required` instead of silently fabricating quantities.
- Added Profile and Source audit columns and persisted normalized assembly settings.
- Added `Structural Assembly` sheets to Classic and Site-format workbooks.
- Added regressions for hosted Rebar routing, safe blank allowances, sheet structure and ordering.

### Verification boundary
- Python compilation and the full XLSX regression harness pass.
- Revit 2025 live QA verified Assembly Profile entry and restore, plus generated Site and Classic
  workbooks containing `Structural Assembly` with the saved profile and source metadata.

## [v1.14.1] - 2026-09-08

### Fixed (installed STDIO smoke-test follow-up)
- Accept a leading UTF-8 BOM on an MCP input line, matching the behavior observed through a native
  Windows PowerShell pipeline.
- Do not accept `notifications/initialized` unless a valid `initialize` request was processed first.
- Added the BOM case to the dependency-free MCP protocol regression.

### Verification
- The corrected `v1.14.1` executable is installed and registered as the enabled global Codex STDIO
  server `rcc-boq`.
- Its installed handshake and live status/document calls pass, including the PowerShell BOM path.
  A fresh Revit 2025 launch now reports the connected `v1.14.1` assembly, and the installed MCP
  executable lists all five tools and calls live status successfully. With the test model open,
  document, empty-selection, generic-element and varying-Rebar calls also pass; Rebar `3411763`
  preserves Quantity `3`, blank Bar Length, Total Bar Length `33510 mm`, A as `Varies` and the
  variable-set flag. A fresh ephemeral Codex session discovered and invoked the registered
  `rcc-boq/rcc_boq_status` tool without a fallback, and a visible non-empty Revit selection returned
  the bounded snapshot for Structural Rebar `3411763`. INT-02 is complete.

## [v1.14.0] - 2026-09-08

### Added (host-free + raw STDIO live verification; Codex restart pending)
- Added a dependency-free .NET 8 STDIO MCP adapter over the proven token-protected localhost REST
  boundary. It exposes status, active document, selection, element and Rebar as five read-only tools.
- Added bounded JSON-RPC input, MCP initialization/instructions, fixed tool schemas, positive Revit
  element-ID validation, read-only/non-destructive annotations and safe tool-level Gateway errors.
- Extended the installer to publish the MCP executable side-by-side and print the exact Codex
  registration command.
- Added dependency-free MCP regressions covering initialization, notification handling, tool
  discovery, annotations, endpoint mapping and invalid arguments.

### Verification boundary
- MCP and Core projects build with zero warnings/errors; MCP protocol regressions pass.
- A raw STDIO MCP session successfully listed all five tools and called status, document and
  selection against the live Revit project. Registered-tool discovery still requires install plus a
  fresh Codex session.

## [v1.13.3] - 2026-09-08

### Fixed (live Revit 2025 + automated tests)
- Varying Rebar dimensions now use the same proven rule as the BOQ exporter: an existing dimension
  parameter with `HasValue=false` is exported as `Varies`. The REST serializer no longer depends on
  Revit returning a literal `<varies>` display string.
- Moved the normalization into shared `RebarValueRules` and added Core regressions for false
  `HasValue`, literal varying display text and fixed dimension preservation.

### Verification boundary
- Revit `25.0.2.419` loaded `v1.13.3`; authenticated status reported the connected bridge and a
  non-empty selection returned Rebar `3411763`.
- The Rebar payload now returns A `Varies`, B `492 mm`, Quantity `3`, blank individual Bar Length,
  Total Bar Length `33510 mm` and `has_variable_length_bars=true`. Revit and Gateway remained
  responsive and the bridge log contained no new error.
- With two Revit processes running, exactly one Gateway remained active; the second add-in logged
  that it was inactive while the authenticated API stayed connected.
- Closing the owner Revit normally stopped its Gateway and wrote a clean bridge-stopped log entry.
  A fresh Revit launch then restored exactly one Gateway with `revit_connected=true`. The REST
  integration gates are complete; the MCP layer is the next phase.

## [v1.13.2] - 2026-09-08

### Fixed (owner live payload + automated tests; restart verification pending)
- Revit varying-dimension display text is now read before the `Parameter.HasValue` early exit. This
  preserves native markers such as `<varies>` that Revit exposes while reporting no scalar value.
- Added a regression for a false `HasValue` combined with a valid varying display value.

### Verification boundary
- The defect was found through the live `v1.13.1` payload for Rebar `3411763`: native varying-set
  identity and totals were correct, but dimension A was blank. Projects build and host-free tests
  pass; `v1.13.2` requires one restart and the same Rebar endpoint check before closure.

## [v1.13.1] - 2026-09-08

### Fixed (automated tests; live verification completed in v1.13.3)
- Added a per-user/session mutex so only one Revit process owns the fixed localhost port, Named Pipe
  and Gateway. Additional Revit processes remain inactive instead of competing for the pipe.
- Added a one-second backoff after unexpected pipe-server failures, preventing the tight error loop
  observed when two Revit processes loaded the initial bridge simultaneously.
- Missing Revit now returns `503 Bridge unavailable` in about one second instead of waiting 15
  seconds and returning `504`. Status remains outside the Revit `ExternalEvent` queue.
- The installer now derives its semantic version from `Directory.Build.props`, enabling side-by-side
  patch deployment when a running Revit process has the previous add-in assembly locked.

### Verified (live Revit 2025 + automated tests)
- Revit `25.0.2.419` loaded `v1.13.1` and launched the installed Gateway without a new bridge-log
  error. Both processes remained responsive through the endpoint checks.
- An unauthenticated status request returned `401`; authenticated status returned API `1.0.0`,
  extension `1.13.1` and `revit_connected=true`. Document and empty-selection reads succeeded.
- Generic element and native Rebar reads succeeded for varying Rebar ID `3411763`: Quantity `3`,
  blank Bar Length, Total Bar Length `33510 mm`, Distribution Type `Varying length` and
  `has_variable_length_bars=true`. A non-Rebar request returned `422`; a missing ID returned `404`.
- Gateway and Revit projects build with zero warnings/errors; .NET token/pipe, Python REST and full
  XLSX tests pass.

### Live boundary completed in v1.13.3
- Non-empty selection, second-instance mutex behavior and clean owner/Gateway shutdown were all
  subsequently verified with the `v1.13.3` deployment.

## [v1.13.0] - 2026-09-07

### Added (code + automated tests; live Revit verification pending)
- Added an out-of-process ASP.NET Core Gateway bound only to `127.0.0.1`, plus a Revit 2025 add-in
  that performs approved reads through `ExternalEvent` and a current-user-only Named Pipe. The fixed
  allow-list contains status, active-document, selection, element and Rebar inspection; it exposes
  no transaction, arbitrary method or code-execution operation.
- Added a 256-bit per-user Bearer token under `%LOCALAPPDATA%\RCC_BOQ`, `no-store` responses, bounded
  request/response sizes, parent-process monitoring and a one-second unavailable-Revit response.
  Document paths and token values are never returned.
- Added `scripts/install_rest_bridge.ps1`, a Revit add-in manifest template, the dependency-free
  `scripts/rcc_boq_rest_client.py`, .NET Core contract tests and Python client/serialization tests.
- The earlier pyRevit Routes prototype remains renamed to `startup.disabled.py` after live host
  instability. It is not part of the installed bridge and must not be re-enabled for this phase.

### Security boundary
- Gateway and Revit add-in projects build with zero warnings/errors. Token/pipe tests, Python REST
  tests and the complete XLSX harness pass. A host-free smoke test returned `401` without a token
  and `503` in about one second with a valid token but no Revit pipe. Installation, Revit restart
  and live endpoint calls remain owner-verified gates before this phase is marked live-tested.

## [v1.12.4] - 2026-09-07

### Fixed (owner live evidence + harness)
- Variable-length Rebar sets no longer merge merely because Bar Length and the varying A-H
  dimension are blank. Each varying Revit set now keeps its own BBS row and computes its own
  `Total Length / Quantity` average; fixed-length bars retain the existing geometry/host grouping.
- `Rebar Element ID` is available/exported for traceability, including the BBS. When Revit reports
  an A-H value as `<varies>`, the workbook now shows `Varies` instead of an ambiguous blank.
- The owner's example (`33510 mm / 3 bars`) is therefore represented as a blank Cutting Length,
  `11.17 m` Average Bar Length and `Variable set / average only` rather than being folded into the
  earlier `12 bars / 10.41 m` aggregate.

### Verified (owner live workbook + harness)
- In the owner's fresh `v1.12.4` workbook, the two `33510 mm / 3 bar` sets appear as separate BBS
  rows with Rebar Element IDs `3411763` and `3411765`. Both show `A=Varies`, `B=492 mm`, blank
  Cutting Length, `11.17 m` Average Bar Length and `Variable set / average only`.
- The old combined `12 bars / 124.92 m / 10.41 m average` row is absent. BBS and Rebar Summary
  reconcile exactly at 11,903 bars, 25,439.37 m and 30,130.966 kg.
- Compilation and the complete harness pass, including fixed-group retention, variable-set
  separation, Element ID traceability and `Varies` preservation.

## [v1.12.3] - 2026-09-07

### Fixed (owner live evidence + harness)
- System-family Floors now feature-detect Revit's built-in `Type` / `Type Name` and `Family`
  parameters when the live wrapper does not return `ElementType.Name`. Routing diagnostics therefore
  report the Properties-palette type instead of `-`.
- The owner's Element IDs `3182833` (`LOBBY`) and `3201775` (`ramp`) now route to `Slab / Slab`
  instead of the controlled `Other` bucket. Foundation/PCC/footing rules still take priority.

### Verification boundary
- The supplied Revit Properties screenshots establish both element identities. The owner's fresh
  `v1.12.3` export completed with no routing findings, and direct workbook inspection found `LOBBY`
  and `ramp` once each in Slab and zero times in Foundation. Compilation and the complete harness
  pass.

## [v1.12.2] - 2026-09-07

### Added (harness)
- When routing has `Other`, unclassified or duplicate findings, the export completion popup now
  lists only the affected Revit Element IDs with source category, family/type, available identity
  fields and routing reason.
- The compact list is capped at 10 rows and directs the user to Revit's `Manage > Select by ID`;
  healthy classification rows are not printed, avoiding the earlier oversized diagnostics window.

### Verification boundary
- Compilation and the complete harness pass. Live confirmation is required on the owner's two
  current `Other` elements.

## [v1.12.1] - 2026-09-07

### Performance (live timing + harness)
- The owner's `v1.12.0` Site export established a 46.0-second baseline: metadata 0.0 seconds,
  Revit data 40.1 seconds and workbook writing 5.9 seconds for 9,632 rows / 45 selected fields.
- Site format no longer resolves the automatic Classic-only Grade grouping for every concrete
  element. Level element names are cached, and Beam/Column/Wall bounding boxes are read only when
  an authoritative dimension needed by formwork is missing.

### Verified (owner live timing + harness)
- The same 9,632-row / 45-field Site export completed in 19.1 seconds: Revit data 15.1 seconds and
  workbook writing 4.0 seconds. This is 58.5% faster than the 46.0-second baseline.
- Compilation and the complete harness pass, including guards for Grade-skip, Level caching and
  conditional bounding-box reads.

## [v1.12.0] - 2026-09-07

### Performance (harness)
- Replaced repeated full Revit `ParameterSet` scans for every selected field with one lowercase-name
  index per element. Selected parameter reads are now constant-time dictionary lookups.
- Added a shared type-parameter cache, so thousands of instances of the same Revit type reuse one
  `doc.GetElement(typeId)` result and one type-parameter index.
- Concrete-grade and identity fallbacks reuse the same indexes instead of rescanning instance/type
  parameters for every grade hint and common identity field.
- Quantity dimension reads reuse that context too; each category now requests only the dimensions
  it actually needs, eliminating repeated type fetches and irrelevant Width/Depth reads on slabs
  and foundations.
- Site-format export skips the unused Classic parameter-metadata scan. The completion dialog now
  reports separate metadata, Revit-data and workbook-writing durations for live verification.
- Derived-only Rebar exports skip the general raw-parameter index because their BBS/weight values
  already come from the dedicated Rebar quantity adapter.

### Verification boundary
- Compilation and the complete workbook harness pass. A fake-Revit regression proves two instances
  of one type scan each instance once, scan the shared type once, and resolve both instance/type
  values correctly. Real elapsed-time improvement remains to be measured in Revit on the owner's
  project because Python tests cannot benchmark Revit API calls.

## [v1.11.3] - 2026-09-07

### Fixed (owner workbook audit + harness)
- Beam shuttering now reads the actual family/type section width through Revit's
  `STRUCTURAL_SECTION_COMMON_WIDTH` built-in parameter when available, then controlled aliases such
  as `BEAM WIDTH`. The matching section-height built-in/aliases are used for beam depth.
- Rotated/angled beam bounding-box width and height are no longer accepted as cross-section
  dimensions. Missing section dimensions now leave shuttering blank instead of exporting an
  inflated result.
- The supplied corrected workbook exposed the defect: original Beam shuttering was 37,531.28 m2
  versus 22,488.481276 m2 using `BEAM WIDTH / 1000`, with 3,858 of 4,031 rows differing by more
  than 10 mm. With the exporter's existing two-decimal rounding on every row, the fresh-export
  comparison target is 22,488.94 m2.

### Verification boundary
- Compilation and the complete harness pass, including built-in feature detection, custom
  `BEAM WIDTH` fallback and rotated-bounding-box rejection. A fresh Revit export is still required
  to confirm the project total against the corrected workbook.

## [v1.11.2] - 2026-09-07

### Fixed (harness)
- Available -> Selected parameter choices and their visible order now save immediately after add,
  remove, move-up/down and move-top/bottom actions.
- The same state is saved before Apply, before Export, and whenever the dialog closes through its
  Close button, title-bar X, Alt+F4 or host-driven window closure.
- Saving parameter selections now merges into the existing settings document, preserving the last
  Excel export folder and future unrelated preferences.

### Verification boundary
- Python compilation and the XLSX regression harness verify the persistence wiring. Reload/restart
  behavior still requires one live Revit 2025 confirmation by the project owner.

## [v1.11.1] - 2026-09-04

### Fixed (harness + owner workbook audit)
- Rebar Level now falls back to the host element's level when the Rebar itself has no direct level.
- BBS rows with no Revit Bar Length are explicitly labelled `Variable set / average only`; they
  retain blank Cutting Length and show `Total Length / Quantity` separately as Average Bar Length.
  This prevents a varying set average from being misrepresented as a fabrication cutting length.
- The owner's `v1.11.0` workbook reconciled exactly across raw Rebar, BBS and diameter summary:
  11,903 bars, 25,439.37 m and 30,130.966 kg. It also exposed 26 grouped variable-length entries
  (280 bars), which drove this patch. Live verification of the new level/status fields is pending.

## [v1.11.0] - 2026-09-04

### Added (harness)
- Started P5 with automatic Rebar shape fields `A` through `H`, Bend Diameter, Hook at Start/End
  and a dedicated Cutting Length field. Revit's shape-aware Bar Length remains the authoritative
  cutting length; the exporter does not apply a guessed universal bend-deduction formula.
- Added `Rebar BBS` in Classic and Site workbooks. Rows group compatible Bar Mark/shape/diameter/
  dimensions/cutting-length/host/level records and aggregate Quantity, Total Length and Weight.
- Added `Rebar Summary` with diameter-wise Number of Bars, Total Length, Unit Weight, Total Weight
  in kilograms and tonnes.

### Verification boundary
- Python compilation and the complete XLSX regression harness pass. Real-project rows supplied by
  the owner established that L/C/stirrup/U-ring shapes use different dimension repetition, hook and
  bend rules. Live Revit 2025 export of the two new sheets remains pending.

## [v1.10.2] - 2026-09-04

### Fixed (harness)
- Prevented a controlled Slab/Foundation `Other` route from dumping every correctly classified
  project element into the pyRevit output window before the Save dialog.
- Routing diagnostics now contain only the rows responsible for findings, capped at 100 details.
- Non-blocking findings are summarized in the normal success message without opening pyRevit
  output, so they cannot prevent or hide the file-save flow. Invalid audits still stop export with
  focused diagnostics.

### Verification boundary
- Python compilation and the XLSX regression harness pass. Live Revit 2025 confirmation is pending.

## [v1.10.1] - 2026-09-03

### Fixed (harness)
- Exposed every automatic P4 Rebar export field in the Rebar **Available Parameters** list: Level,
  Bar Mark, Diameter, Shape, Quantity, Bar/Total Length, Unit/Total Weight and Host ID/category.
- Treat selected Rebar calculated fields as calculated metadata instead of unresolved raw Revit
  parameters, preventing false missing-value counts and blank selected columns.
- Added a regression contract proving the complete automatic-field list is wired into Rebar.

### Verification boundary
- Python compile and the complete XLSX regression harness pass. Revit 2025 live verification remains
  required before P4 is marked done.

## [v1.10.0] - 2026-09-03

### Added (harness)
- Started P4 with a dedicated **Rebar** tab and `OST_Rebar` collection. Raw Revit parameters remain
  selectable while the quantity engine automatically exports Bar Mark, Diameter, Shape, Quantity,
  individual/total length, Host Element ID/category, Level, Unit Weight and Total Weight.
- Added dependency-free `lib/rebar_engine.py`. Unit weight uses `d²/162 kg/m`; total weight is unit
  weight × total length, with Total Length falling back to Bar Length × included Quantity.
- Added Rebar sheets to Classic and Site workbooks. Site Rebar output intentionally omits concrete
  L/W/H and SHUTTERING columns. Costing treats Total Weight as Rebar's primary quantity.
- Added P4 regressions for calculations, sheet columns/order, Site layout, UI/category wiring and
  retained all prior Wall/Slab/Foundation checks. Compilation and the full harness pass.

### Verification boundary
- Revit-facing Bar Diameter, TotalLength, ScheduleMark and GetHostId reads are guarded and based on
  Autodesk's documented Rebar API/parameters. Their values remain unverified until compared with a
  native schedule in Revit 2025. Variable-length/free-form/fabric reinforcement is not yet claimed.

---

## [v1.9.3] - 2026-09-03

### Fixed (harness)
- Successful exports no longer force-open the pyRevit output window. The known IP27 forms fallback
  and healthy classification audits are silent.
- Detailed per-element routing diagnostics remain available automatically when the audit is invalid
  or contains source/destination duplicates, unclassified elements or controlled `Other` routes.
- Added regressions proving a balanced clean audit is silent, audit findings still trigger
  diagnostics, and known CP3123/IP27 engines do not call the output window.

The project owner confirmed in Revit 2025 on 2026-09-03 that a healthy export no longer opens the
unwanted output popup. T-10 and P3.5 are closed.

---

## [v1.9.2] - 2026-09-03

### Fixed (harness)
- Site-format detail sheets no longer discard selected calculated `Qty:` fields. The writer now
  accepts the authoritative per-category UI selection and preserves Structure Wall
  `Qty: Thickness (m)` and `Qty: Count`, while still excluding unselected automatic quantities.
- Added an XLSX regression proving both selected headers reach the Structure Wall site sheet along
  with its existing live `2LH` shuttering formula.

The project owner confirmed the corrected Structure Wall Excel columns live in Revit 2025 on
2026-09-03. P3.5 / T-09 is closed.

---

## [v1.9.1] - 2026-09-03

### Fixed (harness)
- Structure Wall's Available list now includes selectable calculated fields
  `Qty: Thickness (m)` and `Qty: Count`. They were already calculated for export in v1.9.0 but
  could not appear in parameter discovery because neither is an instance `element.Parameters`
  entry (`Count` is derived and wall thickness is resolved through the quantity/type path).
- Selected calculated fields use the quantity-engine values, keep calculated metadata and no longer
  inflate the missing-parameter count. Added a discovery regression for the Wall Available pool.

Live Revit 2025 recheck is pending.

---

## [v1.9.0] - 2026-09-03

### Added (harness)
- Added a fifth **Structure Wall** tab with independent search, parameter selection, reordering and
  persisted metadata. Collection is limited to `OST_Walls` elements whose Revit Structural flag is
  enabled, excluding architectural walls.
- Routed Structure Wall through classic and site-format element sheets, BOQ Summary, Level/Grade
  summaries and Costing. Sheet-name references are now quoted safely, so formulas targeting
  `'Structure Wall'!` remain valid.
- Added category-aware wall Length, Height and Thickness quantities plus gross two-face shuttering
  value/formula `2 × Length × Height`. Opening/intersection deductions are intentionally deferred.
- Expanded the regression harness with structural-flag, XAML wiring, wall dimension/formwork,
  workbook order, site export and quoted-formula checks. `python -m py_compile` and the complete
  harness pass; live Revit 2025 Wall verification remains pending.

### Confirmed live
- The project owner confirmed the `v1.8.10` Slab/Foundation classification is correct in Revit 2025
  on 2026-09-03; T-08 is closed.

---

## [v1.8.10] - 2026-09-03

### Fixed (harness)
- Replaced the partial Slab/Foundation routing fixes with one authoritative
  `classify_rcc_element()` result containing logical group, subtype, source category, normalized
  identity and classification reason.
- Both raw `OST_Floors` and `OST_StructuralFoundation` collections now feed exclusive logical
  Slab/Foundation collections. Initial parameter discovery, subtype filters and Excel export reuse
  those same results instead of rebuilding routing independently.
- Foundation priority is deterministic: PCC, Combined Footing / exact `CF<number>`, Footing /
  exact `F<number>`, Combined Raft, Raft, then slab identities. Bare `F`, `SF`, `FLOOR` and `FOLD`
  are not footing codes.
- Added `S<number>`, `GS`, Grade/Fold Slab and Chajja routing to Slab regardless of physical Revit
  category. Unknown elements remain visible under a controlled `Other` fallback.
- Added a pre-export audit with raw/logical counts, duplicate ElementIds, unclassified rows and
  per-element diagnostic reasons. Duplicate source IDs are reported and routed only once; a
  destination overlap or count discrepancy blocks export.
- Audit diagnostics now resolve Family/Type for both loadable-family and system-family elements;
  startup prints the compact summary while the full per-element trace is emitted before export.
- Expanded `test_xlsx_writer.py` with the complete Structural Foundation, Floor and mixed-project
  matrices plus strict-code, Chajja, reliable `ID_UNMT` / `ITEM DES.` parameter-source,
  reconciliation and duplicate-ID regressions.

### Repository maintenance
- Purged local root diagnostic/readback scripts, text dumps and generated `__pycache__` folders;
  `.gitignore` now excludes future root `_*.py` / `_*.txt` scratch artifacts.
- Updated active project documentation to the real `Nudge.extension/Nudge.tab` layout and current
  P1-P3 / `v1.8.10` status. `docs/reference/` remains frozen historical Kestrel material.

Verification (re-run 2026-09-03): `python -m py_compile` passed for the harness, pushbutton and
five engine modules; `python test_xlsx_writer.py` ends `RESULT: all checks passed`. The project
owner confirmed the corrected Slab/Foundation classification live in Revit 2025 on 2026-09-03.

---

## [v1.8.9] - 2026-09-02

### Fixed (harness)
- **PCC/footing floors now correctly classified** (`script.py`): two root causes made the v1.8.8
  routing patch ineffective for the Uma Niwas footings:
  1. `is_pcc_element` and `classify_foundation_subtype` used `\bpcc\b` to detect PCC tokens, but
     `\b` (word boundary) fails when 'PCC' is followed by '_' because underscore is a regex word
     character — so 'PCC_FOOTING' was never recognized as PCC. Replaced with lookaround
     `(?<![a-z0-9])pcc(?![a-z0-9])` which correctly matches 'PCC_FOOTING', 'PCC-CF2', etc.
  2. `classify_foundation_subtype` checked for slab-like subtypes BEFORE footing/raft tokens. Footing
     elements modeled as floors often carry slab-ish family names (e.g. 'RCC_SLAB | F1'), so they
     were classified as 'Slab-like' before the footing check could run. Reordered: footing/raft
     tokens now checked first, slab-like last.
- Net effect: F1-F5, CF1/CF2, and PCC_FOOTING floors now route to the Foundation sheet; Slab sheet
  keeps only genuine slabs.

Live re-export on a real project: **Unverified** (owner click-through).

---

## [v1.8.8] - 2026-09-02

### Fixed (harness)
- **Footing/raft floors now route to the Foundation sheet** (`script.py`): the Uma Niwas export
  showed "Footing & PCC" (F1-F5) and "Combine Footing & PCC" (CF1/CF2) floors on the Slab sheet
  because the Slab/Foundation routing redirected only PCC floors. New `is_foundation_like_floor()`
  (PCC first, then Footing / Combined Footing / Raft / Combined Raft via
  `classify_foundation_subtype`) is applied at all four routing sites — the initial
  `category_elements` Slab and Foundation lists (kept mutually exclusive) and both
  `refresh_category_view` branches.
- **PCC double-count removed**: the Foundation filter refresh re-added elements the initial
  routing had placed in Slab, so PCC beds appeared on both sheets and the Summary VOLUME totals
  were inflated. The refresh now applies exactly the initial routing rule.
- Export collectors (`build_element_data`, metadata collector) read `category_elements`, so the
  corrected routing reaches the workbook without further changes.
- `test_xlsx_writer.py`: new routing regression section (foundation-like vs slab-like cases,
  including `PCC Slab` wording; name-only fake elements).

Live re-export on a real project: **Unverified** (owner click-through).

---

## [v1.8.7] - 2026-09-02

### Fixed (harness)
- **Site-format detail rows now group ascending by level** (`export_engine.py`): the site workbook
  rendered rows in element-collection order, so the same storey appeared in several separated blocks
  and named storeys (PLINTH / TERRACE / OHW-LMR) mixed with numbered floors. `_site_sort_key` existed
  but had no caller. It now ranks named storeys in real building order (FOUNDATION/BASE < PLINTH <
  numbered levels, "Level 2 before Level 10" preserved < TERRACE < OHW/LMR), and a new stable
  `_sort_site_rows` orders each category sheet by its first LEVEL-like selected parameter (LEVEL_V,
  BASE LEVEL, ...). Sheets without a level parameter keep their collection order; within one storey
  the original element order and SNO sequence stay stable.
- **test_xlsx_writer.py**: new checks — building-order ranking of the level key, ascending stable
  grouping via `_sort_site_rows`, and no-level rows passing through untouched.

### Notes
- Blank VOLUME cells seen in a real export (26 Beam rows) are model data, not a writer defect: those
  beams have an empty user `VOLUME` parameter while L/W/H and the SHUTTERING formula are populated.
- LEVEL_V appearing on Beam/Column sheets but not Slab/Foundation reflects the per-category parameter
  selection, not a rendering bug.

---

## [v1.8.6] - 2026-09-02

### Changed (refactor — zero behaviour change)
- **Module split (PROJECT_STRUCTURE.md §9)**: the five pure-Python engines moved verbatim out of the
  7,289-line `BOQ.pushbutton/script.py` (now 4,181 lines — Revit-bound code only) into
  `Nudge.extension/lib/`, the folder pyRevit already puts on `sys.path` (the same proven mechanism the
  existing `theme_manager` import uses): `settings_engine.py` (79 lines), `quantity_engine.py` (235),
  `formwork_engine.py` (247), `costing_engine.py` (155), `export_engine.py` (2,566). `script.py`
  imports the moved names back by plain module name; classification, parameter discovery, the WPF
  dialog and all event wiring stay in `script.py`. The dependency rule is preserved: the engines are
  stdlib-only (`os / re / json / time / zipfile / xml.sax.saxutils`), no Revit symbols.
  Two minimal mechanical shims were required by the move and are documented in the modules:
  `convert_quantity_value` gained a guarded `Autodesk.Revit` import so the module stays importable in
  plain Python, and `write_basic_xlsx` imports `build_costing_sheet` from `costing_engine` at call
  time to avoid a writer→costing import cycle.
- **test_xlsx_writer.py**: extraction is now module-aware — engine modules first, `script.py` as
  fallback — and puts `Nudge.extension/lib` on `sys.path` for the call-time import. Also fixed a
  pre-existing broken `\Z` anchor in the extraction regex (the raw string contained `\\Z`, a literal
  backslash-Z, so end-of-string never terminated a block; it only ever worked because script.py
  always had trailing defs).
- **Version**: `SCRIPT_VERSION` and the docstring `__version__` aligned at `1.8.6` (they had drifted
  to 1.8.5 / 1.8.3). PATCH bump per §8: backward-compatible refactor with no behaviour change.

**Verification:** `python test_xlsx_writer.py` → `RESULT: all checks passed` (harness; 42 functions
resolved from the new modules: export ×31, formwork ×6, quantity ×3, costing ×1, script ×1). The
in-Revit runtime (lib/ import at button click, engine guard) is **Unverified** until the project
owner runs the BOQ button in Revit 2025.

---

## [v1.7.7] - 2026-08-31

### Fixed
- **Search box text size**: `BrandTextBox` FontSize 12→14, Padding 8,6→10,7, FontFamily explicitly "Segoe UI" (was `BrandFontFamily` dynamic resource which may not resolve under IronPython, causing small/blurry text)

---

## [Unreleased] — Search-box full visual paint (background + border) — code `v1.7.6`

**Fix (unreleased; code `v1.7.6`).** The four search boxes are now painted entirely with
concrete theme brushes via `SetValue` — text, caret, **background and border** included —
re-applied on every theme switch. No visual property is left dependent on runtime dynamic
resources after the Brand dictionaries merge (the IronPython quirk can otherwise leave a box
that looks "not proper"). Light: `#FFFFFF` surface / `#D6D6D6` border / `#1F1F1F` text; Dark:
`#2B2B2B` surface / `#3F3F3F` border / `#EDEDED` text.

**Tested (off-Revit).** `python -m py_compile` clean; `python test_xlsx_writer.py` ends
`RESULT: all checks passed` (engine untouched). **Unverified live** — owner to reload and
confirm the search boxes look proper in both themes.

---

## [Unreleased] — Search-box text visibility fix (round 4, concrete brush) — code `v1.7.5`

**Fix (unreleased; code `v1.7.5`).** Dynamic-resource `Foreground` does not reliably reach the
TextBox's internal text editor under IronPython after the theme dictionaries are re-merged —
the typed text fell back to the system window-text colour and became invisible on Light.
`BrandTextBox` now uses the **default WPF TextBox template** (text renders straight from
`Foreground`), and `_apply_search_foregrounds()` assigns **concrete `SolidColorBrush` values via
`SetValue`** on all four search boxes: `Foreground`/`CaretBrush` = theme primary (`#1F1F1F` /
`#EDEDED` from `window.Tag`), `SelectionBrush` = Ember, `SelectionTextBrush` = white. Local
`SetValue` needs no resource lookup, so the text and caret are always visible; re-applied on
every theme switch.

**Tested (off-Revit).** `Brand.Controls.xaml` well-formed; `python -m py_compile` clean;
`python test_xlsx_writer.py` ends `RESULT: all checks passed` (engine untouched).
**Unverified live** — owner to reload and confirm visible search text + caret in both themes.

---

## [Unreleased] — Search-box text visibility fix (round 3, programmatic) — code `v1.7.4`

**Fix (unreleased; code `v1.7.4`).** Template-only (v1.7.2) and element-XAML (v1.7.3)
`DynamicResource` foreground fixes did not make the typed search text visible on the live
IronPython dialog. `script.py` now applies the same **`SetResourceReference`** pattern the
confirmed-visible status bar uses: `_apply_search_foregrounds()` pins
`TextBox.ForegroundProperty` / `CaretBrushProperty` to `TextPrimaryBrush` on all four search
boxes after every theme apply/switch (plus a first-paint safety net). The reference resolves
after the brand dictionaries are merged, so text and caret render regardless of theme.

**Tested (off-Revit).** `python -m py_compile` clean; `python test_xlsx_writer.py` ends
`RESULT: all checks passed` (engine untouched). **Unverified live** — owner to reload and
confirm visible search text / caret in both themes.

---

## [Unreleased] — Search-box text visibility fix (round 2) — code `v1.7.3`

**Fix (unreleased; code `v1.7.3`).** Round 1's template-only change was not enough on the live
dialog. The four search `TextBox`es now set `Foreground` and `CaretBrush` **directly on the
element** in `ui.xaml` — the same pattern the visible list boxes use — so the typed text and
caret always render in `TextPrimaryBrush` after the runtime theme dictionary merge.

**Tested (off-Revit).** `ui.xaml` well-formed; `python -m py_compile` clean;
`python test_xlsx_writer.py` ends `RESULT: all checks passed` (engine untouched).
**Unverified live** — owner to reload and confirm visible text + caret in both themes.

---

## [Unreleased] — Search-box text visibility fix — code `v1.7.2`

**Fix (unreleased; code `v1.7.2`).** Typed text in the four search boxes could be invisible
after the runtime brand dictionaries are merged: the custom TextBox template's text view was
not explicitly inheriting the control's foreground. `BrandTextBox` now sets
`CaretBrush`/`SelectionBrush`/`SelectionTextBrush` and applies
`TextElement.Foreground="{TemplateBinding Foreground}"` on `PART_ContentHost`, so the input and
the caret always render in `TextPrimaryBrush`. Disabled text dims the caret too.

**Tested (off-Revit).** `Brand.Controls.xaml` well-formed; `python -m py_compile` clean;
`python test_xlsx_writer.py` ends `RESULT: all checks passed` (engine untouched).
**Unverified live** — owner to reload and confirm visible text + caret in both themes.

---

## [Unreleased] — Double-click move + no duplicates between lists — code `v1.7.1`

**New UI (unreleased; code `v1.7.1`).** The parameter picker now supports fast mouse-only
selection:
- **Double-click** on an Available parameter adds it to Selected; double-click on a Selected
  parameter removes it back. Wired for all four categories on top of the existing buttons.
- **Available hides anything already Selected** — `filter_available_by_search` excludes the
  category's selected names while rebuilding the list, so a parameter appears in only one list
  at a time. Add/Remove/search/filter/restore all stay consistent with the single-set rule.

**Tested (off-Revit).** `python -m py_compile` clean; `python test_xlsx_writer.py` ends
`RESULT: all checks passed` (engine untouched). **Unverified live** — owner to reload in
Revit 2025 and confirm the double-click moves and the single-set rule.

---

## [Unreleased] — PCC beds belong to the Foundation tab — code `v1.7.0`

**New classification (unreleased; code `v1.7.0`).** PCC (plain cement concrete) beds under
footings / combined footings, which are commonly modeled as **floors** in Revit, now appear in
the **Foundation** tab instead of the Slab tab.

- New `is_pcc_element` — word-boundary `pcc` token check on the element identity
  (name / type / family / common labels).
- `classify_foundation_subtype` checks PCC **first**, so "PCC F1", "PCC-CF2" or "PCC Slab"
  classify as the Foundation **PCC** subtype regardless of modeling storage or other tokens.
- `category_elements` / `refresh_category_view`: PCC floors move from Slab to Foundation in the
  initial state and after every filter change. The Foundation **PCC** filter lists them, and
  they flow into the element sheets, BOQ by Level, BOQ by Grade and Costing.
- Version bumped to **1.7.0** (`__version__` + `SCRIPT_VERSION`).

**Tested (off-Revit).** `python -m py_compile` clean; `python test_xlsx_writer.py` ends
`RESULT: all checks passed` (engine untouched). **Unverified live** — owner to reload in
Revit 2025 and confirm PCC beds show under Foundation (and no longer under Slab).

---

## [Unreleased] — Grade fix (case-insensitive) + classic column cleanup — code `v1.6.2`

**Fix.** The engine `Grade` column showed `(No Grade)` on projects whose shared parameter is
named in another casing (`GRADE OF CONCRETE`): the grade lookup was case-sensitive. Grade hints
now resolve case-insensitively (element → Symbol → type), so `Grade of Concrete` matches
`GRADE OF CONCRETE` and the column carries the real grade (`M40`).

**Cleanup.** The classic workbook no longer emits the `Qty: Dim L/W/H (m)` and
`Qty: Shuttering (m2)` columns — they exist to feed the site-format workbook. Volume / Area /
Length / Height / Thickness / Count remain in the classic export.

**Tested (off-Revit).** `python -m py_compile` clean; `python test_xlsx_writer.py` ends
`RESULT: all checks passed`. **Confirmed (live, 2026-08-31).** Owner re-exported and confirmed.

---

## [Unreleased] — Concrete-grade BOQ grouping (P2 complete) — confirmed live (2026-08-31)

**New engine (unreleased; code `v1.6.0`).** P2's remaining half: the classic workbook gains a
**BOQ by Grade** sheet — quantities grouped per concrete grade (M20/M25/M30/…) x category with
live SUMIF formulas, right after BOQ by Level.

- Every element row carries an engine-added `Grade` column (column C, right after Level),
  resolved by `resolve_concrete_grade`: recognized grade parameters (Concrete Grade / Grade of
  Concrete / Grade / Concrete Type / Concrete Mix / Mix / Mix Design) → the Material parameter's
  target material name → a grade token in the element identity text (`M25` / `m-30` / `M 40`
  spellings normalize against the IS 456 M10–M80 series) → `(No Grade)`.
- `BOQ by Grade` mirrors the level sheet's contract: one row per Grade x Category, static
  Elements counts, live SUMIF per available metric, placed between BOQ by Level and Costing.
  Level/Grade grouping columns are prune-protected so the formulas always resolve; the
  missing-values audit and the site-format writer exclude the column like Level.
- Version bumped to **1.6.0** (`__version__` + `SCRIPT_VERSION`).

**Tested (harness).** `python test_xlsx_writer.py` ends `RESULT: all checks passed` — new
assertions cover Grade placement, headers, grouped rows incl. `(No Grade)`, 9 live SUMIF cells,
static counts, token normalization and the 8-sheet order; `script.py` compiles clean under
CPython 3.12.

**Confirmed (live, 2026-08-31).** Owner verified on a real model in Revit 2025: grades resolve
sensibly, the BOQ by Grade sheet works, and the rest of the export is unchanged.

---

## [Unreleased] — Site format toggle in the dialog — code `v1.6.1`, quick re-test pending

**New UI (unreleased; code `v1.6.1`).** The site-vs-classic writer choice moves out of the
hard-coded `site_format_flag` into the dialog: a fourth footer checkbox, **"Site format"**
(`SiteFormatCheck`), selects the writer at export time — checked (default) produces the manual
site-style workbook, unchecked produces the classic workbook with BOQ Summary, BOQ by Level and
the new BOQ by Grade sheets. The choice persists through the existing settings file
(`"site_format"` key) and is restored on the next run; the module flag remains the fallback
default. Same guarded wiring pattern as the other three checkboxes.

**Tested (off-Revit).** `python -m py_compile` clean; `python test_xlsx_writer.py` ends
`RESULT: all checks passed` (both writers unchanged); `ui.xaml` parses as well-formed XML.

**Confirmed (live, 2026-08-31).** Owner flipped the checkbox and confirmed both workbooks
export correctly; everything else in v1.6.0 is also live-confirmed.

---

## [Unreleased] — Theme selector + every control on the brand palette — confirmed live (2026-08-31)

**New UI (unreleased; code `v1.5.0`).** The BOQ Parameter Manager dialog gains a manual
**Theme selector** (Auto / Light / Dark) with persistence, and the brand kit itself now themes
every control the dialog uses — closing the gaps the v1.4.2 pass left on system chrome
(TabItem headers, GroupBox frames, ListBox selection, ComboBox dropdown, ScrollBars).

- **`lib/Resources/Brand.Colors.Light.xaml` / `Brand.Colors.Dark.xaml`** — new semantic
  interactive-state keys, identical in both files (verified 42-key parity): `HoverBrush`,
  `PressedBrush`, `ItemHoverBrush`, `SelectedBrush` (Ember tint; Ember-deep text in Light,
  Ember-500 text in Dark), `SelectedTextBrush`, `FocusBrush` (Ember 500), `DisabledBrush`,
  `DisabledTextBrush`, `ControlBackgroundBrush` (inputs sit slightly lighter than the Dark
  surface), `HeadingBrush`, `LabelBrush`, plus `Ember700Color` / `EmberPressedBrush` for the
  primary button's pressed state.
- **`lib/Resources/Brand.Controls.xaml`** — primary/secondary buttons gain pressed states;
  `BrandTextBox` gains hover/focus (Ember border) and disabled states; `BrandCheckBox` gets a
  full template (16 px Ember check box, white tick, disabled dimming); `BrandComboBox` gets a
  complete template (brand toggle button, arrow, rounded bordered dropdown popup) and
  `ComboBoxItem` implicit rows; new **implicit** styles for `TabItem` (folder-tab fill that
  connects to the content pane + Ember underline on the selected tab; hover background only on
  unselected tabs), `TabControl` (themed header strip band on `SurfaceAltBrush` so the tab row
  reads as a deliberate header band instead of system chrome), `GroupBox` (bordered surface
  panel with brand header text), `ListBoxItem` (Ember-tinted selection + neutral hover +
  disabled state) and `Separator`; implicit slim `ScrollBar` (Track + thumb, horizontal trigger
  variant). Implicit styles apply wherever the dictionaries are merged — the consuming
  `ui.xaml` control declarations did not change.
- **`Generate.panel/BOQ.pushbutton/ui.xaml`** — one addition only: `Theme:` label +
  `ThemeSelector` combo (`Auto (Revit)` / `Light` / `Dark`) at the head of the footer options
  row. No layout, dimension, tab, control-name or wiring changes.
- **`Generate.panel/BOQ.pushbutton/script.py`** — the guarded brand-theme block now reads the
  saved choice from the existing `.rcc_boq_settings.json` (`"theme"` key; default **Auto**)
  and applies it; the footer combo re-applies on change, saves the choice **immediately**
  through the same settings system (never waits for an export), and `capture_and_save_settings`
  carries the combo state forward so exports cannot wipe the preference. Auto mode keeps the
  pre-1.5 behavior — the dialog follows Revit's own Light/Dark setting and re-applies on
  Revit's theme flip; choosing Light/Dark pauses that watcher until Auto is picked again.
  Watcher state lives in a dict holder because Python 2.7 has no `nonlocal`. Everything stays
  guarded: if `theme_manager` or the dictionaries are missing, the dialog opens on the stock
  look and the selector degrades to a no-op. All ten status messages now route through a
  `set_status(message, kind)` helper that tints the footer status line with the matching
  semantic brush (success export green, export/metadata errors red, no-selection/no-rows
  warnings amber, filter/cancelled info blue, loading/loaded primary text) via
  `SetResourceReference`, keeping the DynamicResource link so the colour follows theme swaps.
- Version bumped to **1.5.0** (`__version__` + `SCRIPT_VERSION`).

**Tested (off-Revit).** A one-shot consistency check verified XML well-formedness of all five
touched XAML files, resolved every `DynamicResource` reference in both windows against the
merged dictionaries, resolved all intra-dictionary `StaticResource` references, confirmed
identical Light/Dark key sets (42 keys), and confirmed the `ThemeSelector` XAML/Python wiring;
the file was deleted after the run. `python -m py_compile` on `script.py` is clean, and
`python test_xlsx_writer.py` still ends with `RESULT: all checks passed` (engine untouched).

**Confirmed (UI, 2026-08-31).** Owner verified in Revit 2025 — dialog opens styled in both
themes, every control (tab headers, group boxes, list selection, combo dropdowns, scrollbars,
focus/disabled states) reads correctly, switching Auto → Light → Dark applies instantly without
reopening, the choice survives close/reopen, and Auto still follows Revit's own theme flip.

**Cost / limits.** `Auto` is the default theme (slight deviation from the original "Light
default" ask — chosen to preserve the v1.4.2 follow-Revit behavior; strict Light default is a
one-line change if wanted). Sora still renders only where installed. The installed pyRevit
(master `6.5.3`) still runs the dialog on the IronPython backend; all new code is 2.7-safe
(no `nonlocal`, no f-strings).

---

## [Unreleased] — BOQ Parameter Manager dialog consumes the brand theme — confirmed live (2026-08-31)

**New UI (unreleased; code `v1.4.2`).** The written "next step" of the Brand UI system: the BOQ
Parameter Manager dialog (`Generate.panel/BOQ.pushbutton/ui.xaml`) now consumes the shared
Light/Dark resource dictionaries instead of default WPF chrome — until now the Ember palette
reached only the exported workbook.

- **`ui.xaml`** — restyled entirely through `DynamicResource` references to the brand keys (no
  `StaticResource`, because the dictionaries are merged at runtime by `theme_manager.apply_theme`,
  which replaces the window's merged dictionaries): window and TabControl surfaces
  (`SurfaceBrush`), the brand type scale on the header/project/status text (`BrandHeaderText` /
  `BrandBodyText` / `BrandLabelText`), `BrandTextBox` on the four search boxes, `BrandComboBox` on
  the two filters, `BrandCheckBox` on the three options, `BrandSecondaryButton` on all
  Add/Remove/Up/Down/Top/Bottom + OK/Close buttons and `BrandPrimaryButton` (Ember fill) on
  Export Excel; the list boxes carry Surface/TextPrimary/Border brushes; the footer band uses
  `SurfaceAltBrush` + `BorderBrush2`. Control names, layout, tooltips and all Python wiring are
  untouched (46 `x:Name`s preserved; mechanical patch applied with per-pattern count assertions).
- **`script.py`** — guarded block right after the window is built: `theme_manager.apply_theme(window)`
  merges the dictionaries (theme auto-detected via guarded `UIThemeManager` → Windows app-theme
  registry → Light), `watch_theme_changes` re-applies if Revit's theme flips while the dialog is
  open, and the watcher is unsubscribed via `stop_watching` on the dialog's Closed event. The whole
  block degrades to the stock look if `theme_manager` or the dictionaries are unavailable. The
  dialog is modal (`ShowDialog`), so plain locals outlive the session — no `keep_alive` registration
  (that fix is for modeless windows only).
- Version bumped to **1.4.2** (`__version__` + `SCRIPT_VERSION`).

**Confirmed (UI, 2026-08-31).** Owner verified live on Revit 2025: dialog opens styled, both
themes are readable, the theme follows Revit's setting, and tabs/selection/filters/reorder/export
behave exactly as before. The XLSX engine is untouched: `python test_xlsx_writer.py` still ends
with `RESULT: all checks passed`, and `script.py` compiles clean under CPython 3.12.

**Known limits.** TabItem headers and GroupBox chrome keep their system-theme look (the brand kit
ships no TabItem/GroupBox styles); Sora renders only where the font is installed (Segoe UI
fallback); same engine reality as the showcase — the installed pyRevit (master `6.5.3`) stubs
`pyrevit.forms` for CPython, so the dialog runs the IronPython backend on this machine today.

---

## [Unreleased] — BOQ Parameter Manager: Level Sync-style header/footer composition — live QA pending

**New UI (unreleased; code `v1.4.3`).** The BOQ dialog's header and footer are restyled to match the
Level Sync Studio dialog's cleaner composition: primary action in the header, simplified footer.

- **`ui.xaml` header** — rebuilt as a `DockPanel`: a `StackPanel` on the left carries the title
  (`BrandHeaderText`), a new subtitle ("Structural Bill of Quantities — pick the parameters to export
  for Beam, Column, Slab and Foundation."), and the project name (`BrandBodyText`); the **Export
  Excel** button (`BrandPrimaryButton`) is docked **right** in the header so the primary action is
  always visible without scrolling. The header sits above the tab strip exactly like the Level Sync
  dialog.
- **`ui.xaml` footer** — simplified: the redundant **OK / Apply** button is removed (its `Click`
  handler in `script.py` is guarded by `if apply_button:`, so the missing name resolves to `None` and
  degrades gracefully); **Close** stays docked right with the options panel. The footer now mirrors
  Level Sync's minimal band.
- **`ui.xaml` tabs** — `TabControl` gets `BorderThickness="0"` for a plain underline tab strip.
- Version bumped to **1.4.3** (`__version__` + `SCRIPT_VERSION`).

**Unverified (UI).** Live confirmation on Revit 2025 is pending with the project owner: dialog opens
with the new header/footer, Export is reachable in the header, tabs/selection/filters/reorder/export
behave exactly as before. The XLSX engine is untouched: `python test_xlsx_writer.py` ends with
`RESULT: all checks passed`, `script.py` compiles clean, and the XAML parses as well-formed XML.

**Cost / limits.** Same engine reality as v1.4.2 — the dialog runs the IronPython backend; ApplyButton
wiring stays in `script.py` as dead code behind the `if apply_button:` guard.

---

## [Unreleased] — Brand UI system: shared theme resources + Brand Showcase — live QA pending

**New infrastructure (unreleased; commit `b1f3c38` + cleanup).** Turns
`docs/reference/brand-guidelines.md` from a document into the toolkit's actual UI surface: one
shared Light/Dark theme system for every WPF dialog.

- **`Nudge.extension/lib/Resources/`** — four brand resource dictionaries:
  `Brand.Colors.Light.xaml` / `Brand.Colors.Dark.xaml` (the Ember accent ramp
  `F2994A` / `D97C2B` / `FCE8D5` / `7A3F14` plus Light/Dark surface, border and text neutrals and
  the shared system success/warning/error/info colors), `Brand.Typography.xaml` (Sora with a
  Segoe UI Variable → Segoe UI fallback; header 18 / subheader 14 / label 13 / body 12 /
  caption 11, SemiBold labels, default TextBlock style) and `Brand.Controls.xaml` (Ember primary
  button with hover/pressed trigger, outline secondary button, TextBox, CheckBox, ComboBox
  chrome, status chips, dialog/ribbon containers).
- **`Nudge.extension/lib/theme_manager.py`** — `get_current_theme()` (guarded `UIThemeManager`
  lookup, falling back to the Windows `AppsUseLightTheme` registry value and then Light),
  `apply_theme()` (merges the color + typography + controls dictionaries into any `Window` and
  stashes the active theme on `window.Tag`), `toggle_theme()`, `watch_theme_changes()` (re-applies
  when Revit's own theme flips; silent no-op where the event is absent) and `stop_watching()`
  (unsubscribes the watcher from the window's Closed event so repeated open/close cycles don't
  accumulate dead handlers). Host-independent apart from the guarded Revit call site —
  pythonnet/.NET only, no pyRevit API dependency.
- **`Nudge.tab ▶ Brand.panel ▶ BrandShowcase.pushbutton`** — a live preview of every brand style
  that doubles as a Light/Dark visual QA tool (theme label + toggle; the window re-themes itself
  if Revit's theme changes while it is open, and unsubscribes its listener on close). Click
  handlers are wired explicitly in Python (`self.ToggleThemeBtn.Click += ...`) because XAML
  `Click=` attributes do not bind on dynamically-loaded XAML in pyRevit.
- **Debug scaffolding removed (cleanup).** The wiring investigation left a "DEBUG BUILD 3" canary
  alert that popped on every open, a temporary TEST isolation button and a per-toggle modal
  confirmation; all are gone. The toggle error path now follows guidelines §5 — a plain-language
  headline with the traceback collapsed under the details toggle.
- **Modeless-lifetime fix (owner feedback, 2026-08-28).** The Light/Dark toggle (and every other
  handler) was dead in the open window. Root cause: pyRevit tears a command's scope down once the
  script returns, and a `show(modal=False)` window outlives that scope — it stays visible but its
  Python-side event wiring does not. `theme_manager` now carries an engine-persistent holder
  (`keep_alive` / `release` — the module persists in the engine's `sys.modules` for the session);
  the showcase registers itself before showing, releases its slot on close, keeps strong references
  to all handlers on the instance, and reads `theme_manager` through the instance (`self._tm`) so
  no handler depends on the command scope.
- **Stray helper removed.** `_patch_summary2.py` — the one-shot patch that rewrote
  `build_site_summary_sheet` for the per-category VOLUME + SHUTTERING aggregation (already
  applied and committed in `b940f96`) — is deleted; the repo root keeps no throwaway helpers.
- **Engine reality check (diagnosis byproduct — owner attention needed).** The showcase window can
  only have opened via the **IronPython (`forms/_ipy.py`) backend**: the installed pyRevit build
  (master clone, `6.5.3`) ships `pyrevit/forms/_cpy.py` as a **stub** that raises
  `PyRevitCPythonNotSupported` for `WPFWindow` and `alert` on any CPython engine, and the machine
  carries no other `pyrevit.forms` backend. Both UI buttons (Brand Showcase and the BOQ dialog,
  which owner-confirmed working) therefore effectively run **IP27** today — the CP3123-only
  decision (T-03) does not describe the runtime yet. Before any CP3123 switch, the installed build
  needs a CPython-capable `pyrevit.forms` (or the dialogs move to raw WPF wiring without
  `pyrevit.forms`).

**Unverified (live).** This is WPF/pyRevit UI — the XLSX harness cannot execute it and the engine
is untouched. Pending owner confirmation on Revit 2025 / CP3123: the showcase opens fully styled,
the toggle flips Light/Dark instantly, and the theme follows Revit's own setting. The natural next
step after that is applying the same dictionaries to the **BOQ Parameter Manager** dialog
(`Generate.panel/BOQ.pushbutton/ui.xaml`), which currently applies the Ember palette only to the
exported workbook.

---

## [Unreleased] — v1.4.0 site-format export: manual site look + formwork (SHUTTERING) — P3 increment

**New feature (unreleased; code `v1.4.1`, tag pending).** Reproduces the hand-made site BOQ that the
owner supplied as screenshots (title blocks, light-blue two-tier headers, MM sizes,
VOLUME + SHUTTERING columns, level-wise front Summary).

- **Formwork engine (P3, first slice)** — `compute_shuttering_area`: Column `2(L+W)H`,
  Beam `(W+2H)L`, Slab soffit = plan area, Foundation footing sides `2(L+W)H`. Dimensions resolve in
  `resolve_element_dimensions` (parameters Width/Depth/Height/Thickness with bounding-box fallback);
  element rows carry `Qty: Dim L/W/H (m)` and `Qty: Shuttering (m2)`.
- **Site-format workbook writer** (`write_site_xlsx` + `build_xlsx_sheet_xml_site`): merged title
  blocks per sheet, two-tier banded headers (SIZE MM / QTY groups, `mergeCells`), whole-millimetre
  integer columns, VOLUME/SHUTTERING figures, bordered TOTAL rows with live SUMs, gridlines off,
  panes frozen below the header band. Front `Summary` = LEVEL × category grid with live SUMIF
  formulas against each detail sheet's hidden LEVEL column, closing with TOTAL m3/sqm pairs.
- **Owner feedback round (2026-08-27):** merged-cell XML no longer emits degenerate /
  overlapping spans (root cause of Excel's "We found a problem with some content…" repair
  prompt); band, data and TOTAL cells now carry a full thin-border box grid; DESCRIPTION is
  built strictly from the parameters selected for that category in the UI (selection order
  preserved), closing with the `W X L` millimetre cross-section.
- **Owner feedback round 2 (2026-08-27):** every selected parameter now
  lands in its OWN sheet column between SNO and SIZE (MM) - the combined
  DESCRIPTION cell is gone; column widths adapt to the parameter count;
  dimension feeds switched to unrounded `_site_dim_value` so MM sizes can
  never drift (6.096 m must print 6096, not 6100).
- **Owner feedback round 3 (2026-08-27):** the site workbook now exports
  ONLY the parameters the user ticked in the UI. Every detail sheet is
  `SNO` + one column per selected parameter (UI order preserved); the
  automatic `SIZE (MM) L/B/D`, `VOLUME`, `SHUTTERING` and `LEVEL` columns
  and the SUM totals row are removed. Because no quantitative feed remains,
  the front `Summary` becomes a simple per-category element-count cover
  (`SNO | CATEGORY | ELEMENTS`) instead of the level-vs-concrete SUMIF grid.
- **Brand pass `docs/reference/brand-guidelines.md` (2026-08-27):** the
  exported workbook drops Revit's own blue and applies the **Ember** accent
  ramp (header fill `F2994A`, band tint `FCE8D5`, sub-band `FFF0E3`) declared
  as `EMBER_*` constants at the top of the site-format section; UI fonts
  switch from Calibri to Windows-native **Segoe UI**. Voice pass: the export
  success alert now leads with outcome copy ("Everything's exported — here's
  your workbook.") and the empty workbook states with one friendly line plus
  the next step, instead of terse all-caps messages.
- **Switch:** `site_format_flag = True` selects the site writer at export time; the classic
  (v1.3.0-style) workbook remains available as rollback via `write_basic_xlsx(site_format=False)` —
  which itself now honours the flag when called directly.
- Version bumped to **1.4.1** (`__version__` + `SCRIPT_VERSION`).

**Tested (harness).** `python test_xlsx_writer.py` passes every check end-to-end: shuttering rules
per category, dimension fallbacks, natural level sort, detail/summary builders (`MERGE_V` markers,
MM integers, selection-driven parameter columns (one per selected parameter)), mergeCells part, live SUMIF/SUM
wiring, site + classic workbook XML validity, styles, plus a merge-grid integrity pass asserting
zero degenerate / duplicate / overlapping spans on every site sheet (Excel-repair regression
guard) and a bordered-grid check over the first data row. `script.py` also compiles clean under
CPython 3.12.

**Not yet released.** Live Revit confirmation on CP3123 still required before tagging; `v1.3.0`
remains tag-pending as well.

---

## [Unreleased] — Professional output: Summary cover + site naming convention (code v1.3.0, tag pending)

**New feature (P13-direction, first increment).**

- **Site naming convention** for exports, mirroring workbooks like
  `20260312-CHHANYADO_HOSPITAL_SURAT-CONCRETE_FINISHING_BOQ.xlsm`: the Save dialog now suggests
  **`YYYYMMDD-<Project>-CONCRETE_FINISHING_BOQ.xlsx`**, built from today's date plus the Revit
  document title (`sanitize_file_name` strips Windows-forbidden characters). The name stays
  editable before saving.
- **Front `Summary` cover sheet** (first tab): project name, generation stamp, tool version, and a
  listing of every sheet in the workbook.
- **3D view:** a true/embedded Revit 3D view inside Excel is **not feasible** through the supported
  API. The realistic option is an *Experimental* snapshot of the current 3D view embedded as an
  image sheet via window capture — implemented only if the project owner opts in.

**Tested (harness).** Cover title/meta/listing checks, file-name sanitization, and the default-name
convention regex all pass alongside every existing check.

**Not yet released.** `v1.3.0` tag is withheld until live Revit confirmation on CP3123.

---

## [1.2.0] — 2026-08-26

**Released.** P2 level-wise grouping (Level column + BOQ by Level SUMIF sheet) and the CP3123-only
engine decision — confirmed live in Revit 2025 by the project owner (points 1–4 passed, no
regression). Tag `v1.2.0`.

---

## [1.1.0] — 2026-08-26

**Released.** P1 quantity engine increment (category-aware quantities, Count, Column Height,
Slab/Foundation Thickness) — confirmed live by the project owner. Tag `v1.1.0`.

---

**New feature (P2, first increment).**

- Every element row now carries an engine-added **`Level`** column, written directly after
  `Element ID` (deterministic column B). The level name is resolved from the reference/schedule
  level built-in parameters with an `element.LevelId` fallback; unresolvable levels stay empty.
- New **`BOQ by Level`** sheet (between BOQ Summary and Costing): one row per
  **Level x Category**, with a static per-group `Elements` count and **live SUMIF formulas**
  against each category sheet's Level column — so grouped totals stay in sync with the element
  data.
- The missing-values audit excludes the engine-added Level column (it is grouping metadata, not a
  selected parameter).

**Engine decision (T-03 closed).** Only one engine is supported going forward: **CP3123 (CPython
3.12.3)** — the modern runtime. **IP27 (IronPython 2.7)** is legacy/EOL Python and is documented as
best-effort/untested rather than a support target. Code remains 2.7-syntax-safe so IP27 may still
work, but no parity testing is promised.

**Tested (harness).** `python test_xlsx_writer.py` asserts: Level column placement on element
sheets; the BOQ by Level header set; grouped rows for every collected level (including
`(No Level)`); exactly 9 live SUMIF metric cells for the sample layout (Beam has no Area column,
Foundation has no Length column); static Elements counts; and the sheet order
Beam / Column / Foundation / BOQ Summary / BOQ by Level / Costing. All checks pass.

**Released as `v1.2.0`.** Both increments confirmed live in Revit 2025 on CP3123 by the project
owner (parameter columns, level grouping, export — all correct, no regression).

---

## [Unreleased] — P1 Structural Quantity Engine (code v1.1.0, release tag pending)

**New feature (P1, first increment).** The quantity engine is now category-aware and adds
per-element **Count**, plus per-category parameter dimensions:

- **Calculated quantity (geometry/computed):** `Qty: Volume (m3)`, `Qty: Area (m2)`,
  `Qty: Length (m)` — unchanged and preserved.
- **Parameter quantity (from model, by name):** `Qty: Height (m)` for **Column**; `Qty: Thickness
  (m)` for **Slab** and **Foundation**. Read via `LookupParameter` on the element, its Symbol and
  its type; absent dimensions return `""` and are pruned automatically (existing behaviour).
- **Count:** `Qty: Count` = 1 per element row; the sheet TOTAL row sums to the element count.
  The BOQ Summary's `Elements` column is already the per-category count.
- `get_element_quantities(element)` is now `get_element_quantities(element, element_name)`; the
  value reader distinguishes **Calculated vs Parameter** quantity explicitly in the docstring.

**Tested (harness).** `python test_xlsx_writer.py` now asserts the P1 `Count` column on populated
sheets, `Height (m)` on Column and `Thickness (m)` on Foundation. All checks pass.

**Released as `v1.1.0`.** Live Revit gathering of real `Height`/`Thickness`/`Count` values confirmed
by the project owner.

---

## [1.0.1] — 2026-08-26

**Bug fix.** Element-referencing parameters exported as raw numeric ElementId.

- **Reported (live, Revit 2025):** Beam/Column/Slab/Foundation tabs work with no regression, but
  for parameters such as **Type, Level, Top Level, Base Level, Reference Level, Cover Type** the
  Excel cells showed the raw **ElementId number** instead of the element's name/value.
- **Fixed:** `safe_parameter_value` now resolves `StorageType.ElementId` parameters to the
  referenced element's **name** — preferred Revit `AsValueString()`, then `doc.GetElement(id).Name`
  (e.g. a Level shows "Level 1", a Type shows its type-family name), with the numeric id kept only
  as a last fallback. This is a single, bounded change to the value reader, so it also improves the
  classification/identity text that uses the same reader.
- Version bumped `1.0.0` → `1.0.1` (PATCH, backward-compatible bug fix).

**Tested (harness).** `python test_xlsx_writer.py` passes; `script.py` syntax valid. Live element-name
resolution requires a Revit session (project-owner confirmation; recorded in `done-list.md`).

---

## [Unreleased] — Roadmap planned (planning only, no code change)

Adopted the **Structural BOQ Development Roadmap** (see `PRD.md` §12–§18). This is documentation
only; the version stays `1.0.0` because no code changed.

- `PRD.md` — added the 16-phase Structural BOQ roadmap, feature rating system + priority ranking,
  architecture principle (keep `script.py` modular), error handling, testing workflow, regression
  protection, and the source-of-truth rule.
- `todo-list.md` — restructured around the phased roadmap (P0–P16), with P1 (quantity engine) next.
- `README.md` — added a Development Roadmap section and updated the project status.
- `CLAUDE.md` / `AI_DEVELOPMENT_GUIDE.md` — added source-of-truth, roadmap-discipline and testing
  workflow rules.
- `PROJECT_STRUCTURE.md` — added a Roadmap→Architecture section mapping each phase to its intended
  landing point.

No engine change → next semantic release is still a feature release when a real phase (e.g. P1)
is implemented.

---

## [1.0.0] — 2026-08-26

**First semantic release.** Adds version control to the extension and its pushbutton.

- `script.py` declares module metadata in its docstring — `__title__`, `__author__`,
  `__version__ = '1.0.0'`, `__min_revit_ver__ = '2025'` — and exposes a runtime `SCRIPT_VERSION`
  constant.
- The Excel export alert now reports the running version.
- Git tags `v0.1.0` … `v0.3.1` were added to the earlier commits to make development history
  visible.

**Tested (harness).** `python test_xlsx_writer.py` passes; `script.py` syntax is valid.

---

## Established so far

### `98fb30b` — Quantity takeoff and BOQ Summary sheet

**Quantity takeoff engine added.** `convert_quantity_value` converts Revit internal units to metric,
preferring `UnitUtils.ConvertFromInternalUnits` with `UnitTypeId`, falling back to
`DisplayUnitType`, then to deterministic foot-based constants. `get_element_quantities` appends
`Qty: Volume (m3)`, `Qty: Area (m2)`, `Qty: Length (m)` columns after the selected parameters so they
never disturb the parameter completeness audit.

**BOQ Summary sheet added.** The export inserts a `BOQ Summary` sheet — one row per populated
category plus a `GRAND TOTAL` — whose values are live cross-sheet `SUM()` formulas referencing the
element sheets. Empty categories do not produce a sheet. The workbook sets `fullCalcOnLoad`.

**Tested (harness).** `test_xlsx_writer.py` asserts sheet order, presence of `SUM(` formulas on the
Beam sheet, a BOQ Summary that references `Beam!` by formula, a `GRAND TOTAL` row, the auto-filter
range excluding the totals row, and the dark-blue header fill style.

### 0ab717c — Parameter metadata and Missing Values summary

**Parameter metadata capture added.** Per-parameter facts (storage type, built-in status, definition
info, data type, group, GUID) are collected into a metadata structure for the element sheets.

**Missing-values audit added.** `build_missing_values_summary` reports, per selected parameter that
has at least one empty value, the category, total elements, missing count, filled count, and fill
percentage. Completely-empty columns are pruned from the element sheets but still reported.

**Costing sheet introduced.** `build_costing_sheet` — per element row, Category, Element ID,
Quantity, Rate, and an Amount formula `Qty*Rate`, with a `SUM` `TOTAL` row. Rates are not hard-coded;
they come from whichever selected parameter name is recognized as a rate/price column.

**Note.** The metadata and missing-values functions exist and are exercised by the harness, while the
finalized workbook drops formerly-empty/tab duplicates; the harness explicitly checks that
`Parameter Metadata` and `Missing Values Summary` are **not** emitted as blank tabs.

### f14903b — BOQ pushbutton icon

**Icon added.** `icon.png` added to `BOQ.pushbutton` so the Generate panel button has a real icon.

### `09dab85` — RCC BOQ Parameter Manager UI

**Initial tool added.** `Nudge.extension/Nudge.tab/Generate.panel/BOQ.pushbutton` with `script.py`
and `ui.xaml`. Introduced the four-category dialog (Beam, Column, Slab, Foundation), per-category
parameter discovery from real elements, search + Add/Remove selection, WPF `ui.xaml` layout, status
bar, and the first dependency-free Open XML XLSX writer with element sheets and a `SaveFileDialog`.

**Tested (harness).** The XLSX engine functions are extracted from the real `script.py` and a sample
workbook is validated end-to-end.

---

## Open / unverified items

- In-Revit behavior of the dialog (parameter discovery, filters, selection, export scope, settings
  persistence, output path) — **Unverified by agent**; requires a live Revit 2025+ project on
  CP3123 and/or IP27 to certify, and is the project owner's confirmation step.
- `convert_quantity_value` numeric accuracy on actual Revit material units — the harness uses fixed
  sample data; real-model confirmation is pending.
- Dual-engine parity (CPython 3.12.3 vs IronPython 2.7) has not been executed by an agent.

Any of the above moving to "Tested" must be recorded here in the same change that establishes it.

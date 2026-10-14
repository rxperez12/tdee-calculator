---
title: Separate route and domain logic - Plan
type: refactor
date: 2026-10-10
execution: code
---

# Separate route and domain logic - Plan

## Goal Capsule

- **Objective:** Route files handle HTTP only. Rules, queries, and formatters live in
  the module that owns that kind of work, where they can be tested directly.
- **Means:** Move a few functions, remove duplicated rules, and add direct unit tests.
  No behavior, schema, template output, or URL changes.
- **Authority:** This plan sets the scope. `AGENTS.md` and `docs/testing.md` govern
  how the work is implemented and checked.
- **Execution profile:** Six small units. Units 1–5 are independent refactors;
  Unit 6 is optional.
- **Handoff:** This plan does not authorize implementation, commits, or publication.
  Each needs its own instruction.
- **Stop conditions:** Stop and report if any unit changes rendered HTML, a status
  code, a redirect, or stored data. That means it is no longer a refactor.

## The rule being applied

A route file reads the request, calls other code, and picks a response.
Anything that doesn't need FastAPI goes in the module that owns that kind of work:

| Kind of code | Home |
| --- | --- |
| Request parsing, template context, `TemplateResponse` / `RedirectResponse` | `routes/*.py` (page-specific) or `web.py` (shared) |
| Rules and view models (what a page means) | Pure module: `calc.py`, `dashboard.py`, new `body_fat.py` |
| Form validation | `*_form.py` |
| Database reads and writes | `entries.py`, `measurements.py`, `settings.py` |
| Unit conversion and display formatting | `units.py` |

Helpers that build template context, such as `render_home`, `render_settings`,
`render_measurements` and `measurement_values`, are route-layer work. They stay
in the route files.

## Current state

The codebase mostly follows this rule already. Only `app.py` and `web.py` import
FastAPI. `calc.py` and `dashboard.py` are pure, and the JS has no logic of its own.
The exceptions:

1. `routes/measurements.py` holds `MeasurementRow` and `build_row`, plus the
   latest/newer selection inside `render_measurements`. These rules decide which
   sites the Navy equation needs, whether settings are missing, and whether an
   estimate is believable. `dashboard.py` already does this job for the Today page.
2. `routes/history.py` runs `select(func.count()).select_from(Entry)` itself.
   It is the only route that writes its own query.
3. `routes/today.py:save_entry` and `routes/measurements.py:save` repeat the same
   edit-conflict rules: parse `loaded_date`, refuse a save to another date that
   already has data, refuse a stale version. `entry_version` and
   `measurement_version` are also the same function. `home()` and
   `measurements.page()` repeat the same `?date=` handling: parse it, default to
   today, and never allow a future date.
4. `save_entry` declares eight `Form()` parameters and rebuilds them into a dict.
   The other POST routes use `FormDependency`.
5. `format_height` is a display formatter, but it lives in `settings_form.py`.
   `routes/settings.py` imports it from there.
6. `MIN_WEIGHT_KG` / `MAX_WEIGHT_KG` live in `entry_form.py`, but `settings_form.py`
   and `routes/settings.py` also import them for the goal-weight range.

## Out of scope

- Splitting the `Settings` dataclass from its load/save functions. `dashboard.py`
  imports it but never touches the database, so a split would change nothing in
  behavior or tests.
- Moving `SITE_LABELS`, `ACTIVITY_LABELS`, or `chart_payload`. Each is already in
  the right place (see the table above).
- Moving `EntryInput` / `MeasurementInput` out of the form modules. The data
  modules import these plain dataclasses, which is a small backwards dependency,
  and moving them isn't worth the churn.
- The hard-coded Sex options in `settings.html`.

## Units

Each unit ends with `./check.sh` passing. Existing route tests are the safety net:
their status codes, rendered text, and stored state must not change. Do not edit
them, except to delete an assertion that has moved word for word into a new
direct test.

### Unit 1: `body_fat.py` view model (branch `feat/p2-measurements`)

This fixes code the current branch added, so it ships with P2.1 A.

- Create `src/tdee_calculator/body_fat.py`. It must be pure like `dashboard.py`:
  no database, clock, or web imports. It holds:
  - `MeasurementRow` (moved unchanged).
  - `build_row(row: MeasurementSession, settings: Settings) -> MeasurementRow`
    (moved unchanged, including the 2–60% range check and reason messages).
  - `MeasurementSummary` (or similar): `rows`, `latest`, `newer`, plus a
    `build_summary(sessions, settings)` that contains the latest/newer selection
    now inside `render_measurements`.
  - A module docstring in the style of `dashboard.py`'s, saying it is pure.
- `routes/measurements.py` calls `build_summary` and keeps `page`, `save`, `remove`,
  `render_measurements`, `measurement_values`, and `measurement_version` (see
  Unit 3 for that one).
- Add `tests/test_body_fat.py`. Build `MeasurementSession` / `MeasurementReading`
  objects in memory, without a database. The test needs:
  - one case for each reason: missing sex, missing height, missing both, each
    missing site for male and female, and an out-of-range estimate
  - a valid male and a valid female estimate, with expected values worked out
    independently (reuse the worked answers in `test_calc.py`, not the formula)
  - means per site from several readings
  - latest/newer selection: the newest session that can produce an estimate
    becomes `latest`, newer partial sessions go in `newer`, and when no session
    can produce one, `latest` is `None`
- Done when: `routes/measurements.py` no longer imports `navy_body_fat`, `Sex`,
  or `mean_reading`, and `test_measurement_routes.py` passes unchanged.

### Unit 2: entry count query (cleanup branch)

- Add `count_entries(session) -> int` to `entries.py`. `routes/history.py` calls
  it and no longer imports `sqlalchemy` or `Entry`.
- Add a test to `tests/test_entries.py` against real SQLite in `tmp_path`, with
  zero entries and with several. `test_recent_list_orders_limits_and_formats`
  already covers the "32 entries" page text.

### Unit 3: shared edit-conflict and date-parameter rules (cleanup branch)

- Add a pure function in a new `edits.py`. It is a rule, not HTTP, so it doesn't
  go in `web.py`:

  ```python
  EditConflict = Literal["conflict", "stale"]

  def edit_conflict(
      saved_date: Date,
      loaded_date_text: str,
      loaded_version: str,
      current_version: str,
      exists: bool,
  ) -> EditConflict | None: ...

  def row_version(updated_at: DateTime | None) -> str: ...
  ```

  `row_version` replaces `entry_version` and `measurement_version`.
- Add `requested_day(text: str | None, today: Date) -> Date` with the shared
  `?date=` handling. It is used by `home()` and `measurements.page()`. It is pure,
  so it goes in `edits.py` too, or in `web.py` if it reads better beside the other
  request helpers. Choose one place for it.
- `save_entry` and `measurements.save` keep their own `render_*` calls and status
  codes, and map the result: `"conflict"` → 409 with `conflict_date`, `"stale"` → 409
  with `stale_date`.
- Add `tests/test_edits.py` with a table covering:
  - the same date, version unchanged → `None`
  - the same date, version changed → `stale`
  - the same date, row deleted since the form loaded → `stale`
  - another date that has a row → `conflict`
  - another date with no row → `None`
  - a missing or malformed `loaded_date` when a row exists → `conflict`
  - `requested_day` with no date, a malformed date, a future date, and a past date
- The existing guard tests in `test_app.py` (`test_stale_form_*`,
  `test_overwrite_*`) and `test_measurement_routes.py` must pass unchanged.

### Unit 4 (optional, do with Unit 3): `save_entry` uses `FormDependency`

- Replace the eight `Form()` parameters with `values: FormDependency`, and read
  fields with `values.get(...)`, as `measurements.save` does. Pass `range` through
  `parse_range(values.get("range"))`.
- Check that a missing field still behaves like an empty string. Today's `Form()`
  defaults are `""`, and `"3m"` for `range`.

### Unit 5: `format_height` → `units.py` (cleanup branch)

- Move `format_height` into `units.py` beside `cm_to_feet_inches`. Update the
  imports in `settings_form.py` and `routes/settings.py`.
- Add direct tests to `tests/test_units.py`. There are none today; it is only
  covered through error messages. Cover kg ("180 cm"), lb ("5 ft 11 in"), a
  half-inch value ("5 ft 10.5 in"), and the bounds 100 cm / 250 cm in both units.

### Unit 6 (optional): weight limits out of `entry_form.py`

- Move `MIN_WEIGHT_KG` / `MAX_WEIGHT_KG` to `units.py`, or to a small `limits.py`
  if more shared limits are expected. `entry_form.py`, `settings_form.py`,
  `routes/settings.py`, and `routes/today.py` all import from there.
- Skip this unit unless another unit is already editing those files.

## Sequencing

| Unit | Branch | Depends on |
| --- | --- | --- |
| 1 | `feat/p2-measurements` | none |
| 2, 3, 5 | one cleanup branch after P2.1 A merges, one commit each | Unit 1 merged; Unit 3 edits `routes/measurements.py` |
| 4 | same commit as 3 | 3 |
| 6 | same cleanup branch, last | none |

## Verification

- `./check.sh` passes after each unit, and branch coverage stays at or above the
  98% threshold.
- Existing route tests pass without changes, which confirms the pages behave the
  same.
- Manual spot check with `TDEE_DATA_DIR` set to a scratch directory:
  - save, edit, and conflict paths on `/` and `/measurements`
  - the history count on `/history`
  - the height range text on `/settings` in both unit systems

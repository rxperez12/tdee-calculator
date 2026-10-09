---
title: Daily logging and complete log table - Plan
type: fix
date: 2026-10-09
artifact_contract: ce-unified-plan/v1
product_contract_source: ce-plan-bootstrap
execution: code
---

# Daily logging and complete log table - Plan

## Goal Capsule

- **Objective:** Complete a day's weight and calorie log at different times without the “Edit it” detour, and review both values together on the dashboard.
- **Means:** Selecting a date loads that day into the existing form through the existing GET route; the dashboard table is built from daily logs.
- **Authority:** This plan governs the behavior; `AGENTS.md` and `docs/testing.md` govern implementation and validation.
- **Execution profile:** Two small units, each starting with a failing regression test.
- **Handoff:** This request authorizes a plan only. Implementation requires a subsequent instruction; commits and publication require explicit authorization.
- **Stop conditions:** Report a blocker if the fix needs a schema change, a calculation change, or JavaScript beyond the one-line auto-submit.

## Problem

1. Changing the date picker changes the submitted date but leaves the previous day's weight and calories in the fields. Saving then hits the overwrite guard, which refuses with an “Edit it” link.
2. The dashboard table is built from chart points, so it shows weigh-ins only: no calories, no calorie-only days, and no table when the range has no weigh-ins.

## Requirements

- R1. Selecting a date loads that day's saved weight and calories into the form; an unlogged date loads empty fields.
- R2. Selecting a different date discards anything typed but not saved. No warning: choosing another day is the intent.
- R3. The form always saves to the day it loaded, shown in a visible label; values from one day can never be submitted against another.
- R4. Completing a missing field keeps the other field's exact stored value (e.g. 80.25 kg stays 80.25, not the displayed 80.2).
- R5. Existing validation, the stale-version check, the stale-units check, and cross-origin protection keep working.
- R6. The dashboard table shows Date, Weight, Calories, Trend, and Edit, newest first, in display units, for every logged date in the selected range, including calorie-only dates. Missing values show “—”; zero calories show 0.
- R7. The table appears whenever the range has logs, even when the chart is empty.
- R8. The selected range survives loading a day and saving.

## Decisions

- **No overwrite review.** Once the form shows the day's stored values, changing or clearing one is a deliberate, visible edit. Changes made in another tab are already caught by the stale-version check.
- **No dirty-draft warning.** Switching days discards the draft (R2).
- **No new JavaScript file or browser automation.** The picker auto-submits with an inline `onchange="this.form.requestSubmit()"`. `docs/testing.md` keeps JS logic-free and reserves Playwright for JS with logic of its own; this has none.
- **“All” range** keeps the chart's existing start. The table uses the same start date as the chart for every range.

## Implementation Units

### U1. Load the selected day into the form

**Files:** `src/tdee_calculator/routes/today.py`, `src/tdee_calculator/templates/_log_form.html`, `src/tdee_calculator/templates/_chart.html` (range links), `src/tdee_calculator/static/style.css`, `tests/test_app.py`.

**Approach:**

- Move the date picker into its own GET form (`action="/"`), not nested in the entry form, with `name="date"`, a hidden `range`, a “Load day” button, and the inline auto-submit. `requestSubmit()` keeps the `required`/`max` checks that `form.submit()` would skip.
- The POST form carries `entry_date` as a hidden field set to the loaded date, plus a hidden `range`. Show a label such as “Logging Wed 7 Oct” beside the fields, using `short_date`.
- In `home()`, take `date` as an optional string and fall back to today when it is empty, invalid, or in the future. Today `/?date=` and `/?date=garbage` return raw JSON 422s, and a future date loads a form that can't be saved.
- `save_entry()` accepts `range` and redirects to `/?date=<saved>&range=<range>&saved=<saved>`. Pass `range` back on 409/422 re-renders.
- Keep the mismatched-date guard as a fallback for stale or hand-built submissions. Reword its message to say the day needs to be loaded first, not “Edit it”.
- Use “Save” for the button in every case; drop `is_update`.

**Tests** (route tests through the real database, using `TestClient`):

1. Regression first: yesterday has 80.25 kg and no calories; `GET /?date=yesterday`, submit 2100 kcal; returns 303, one row, weight exactly 80.25, calories 2100.
2. Fill missing weight on a calorie-only day; calories stay the same.
3. `GET /?date=` with an unlogged date shows empty fields and a hidden `entry_date` for that date.
4. `GET /?date=`, `?date=garbage`, and a future date each render today's form with status 200.
5. Saving redirects to the saved day with the range kept; re-renders after 409/422 keep the range.
6. The page has two separate forms: GET selector and POST entry. Update the `FormInputs` helper so it reads the entry form, and fix any callers in `test_settings_routes.py` and `test_dashboard_routes.py`.
7. Existing tests for stale version, stale units, invalid input, empty form, cross-origin, and no duplicates still pass. Update tests that assert the old redirect or “Edit it” text.

### U2. Build the table from daily logs

**Files:** `src/tdee_calculator/dashboard.py`, `src/tdee_calculator/routes/today.py`, `src/tdee_calculator/templates/_chart.html`, `tests/test_dashboard.py`, `tests/test_dashboard_routes.py`.

**Approach:**

- Add a frozen `TableRow(date, weight_kg, calories, trend_kg)` and `build_table(logs, dashboard, chart) -> tuple[TableRow, ...]`. It takes logs dated from `chart.start` to `dashboard.today`, newest first, and looks up `trend_kg` by date from `dashboard.trend`. Never interpolate a missing trend, and never include projection dates.
- `render_home()` already calls `all_day_logs()` once; keep that list in a variable and pass it to both `build_dashboard()` and `build_table()`.
- In `_chart.html`, move the `<details>` table outside the `chart.empty` branch. Render it when there are rows; when the range has no logs, show “No logs in the last {range}.” Rename the summary to “Show daily log as a table”. Each row's Edit link goes to `/?date=<date>&range=<range>`. Update the chart fallback text to point at the daily table.

**Tests:**

1. Unit test: a mix of weight-only, calorie-only, and complete days gives one row per log, newest first, with `None` where data is missing. A calorie-only day has `trend_kg` `None`.
2. Unit test: rows respect the 4-week and 3-month start dates (inclusive) and include nothing after today.
3. Route test: zero calories render as 0; missing values render as “—”; lb/kJ units render correctly.
4. Route test: a range with only calorie totals shows the table with no canvas or chart scripts.
5. Route test: Edit links carry the date and range.
6. Update the existing test that equates table rows with weigh-ins (`test_dashboard_routes.py`).

## Verification

`./check.sh` passes: formatting, lint, strict mypy, and pytest with coverage at or above 98%.

Manual check with synthetic data in a separate `TDEE_DATA_DIR`, on desktop and at a 375px width:

- Log a morning weight, load the day again later, and add calories; then do it in the reverse order on another day.
- Change the date with the mouse picker and with the keyboard. If typing a date by keyboard jumps to another day partway through, remove the `onchange` and rely on “Load day”.
- Open the daily table with calorie-only data, and check that it scrolls sideways on mobile.

## Out of Scope

Overwrite confirmation, unsaved-draft warnings, browser test automation, calorie charts, inline table editing, pagination, schema or calculation changes.
`docs/plans/03-entry.md` and `docs/plans/05-dashboard.md` stay as historical records; this plan supersedes their date-loading and table decisions.

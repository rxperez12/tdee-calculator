---
title: "feat: Add home measurement logging and weekly cadence"
type: feat
status: active
date: 2026-10-10
---

# Home measurement logging and weekly cadence

## Overview

Add a compact Measurements section to home with the latest circumferences, the
latest usable Navy estimate, and an expandable form for logging or editing a
measurement session. Show a suggested weekly cadence while continuing to allow
corrections, backdated entries, and additional sessions.

This is a follow-up to P2.1 A, before external body-fat results (P2.1 B). It can
ship as one increment after A; planning this increment does not authorize its
implementation or publication.

## Problem and requirements

P2.1 A deliberately introduced a separate `/measurements` page and left home
unchanged. That provides storage and history but leaves measurements outside the
normal home logging workflow. The user requested home display and editing and
raised the spreadsheet's once-per-week entry pattern. This plan follows the
agreed direction: a weekly suggestion, with actual dated sessions retained.

- **R1:** Home shows the newest measurement session's recorded site means, units,
  and actual date, including when no daily weight/calorie entries exist.
- **R2:** Home shows the latest usable Navy estimate with its own measurement date
  and method. A newer partial session cannot make an older estimate look current.
- **R3:** Users can log measurements and edit the latest session directly on home,
  using the existing sites and one-to-three-reading form. Full history and
  instructions remain available on `/measurements`.
- **R4:** The suggested next session is seven calendar days after the newest saved
  session's date. It never blocks a save or makes daily logging incomplete.
- **R5:** Both pages use the same measurement validation and conditional save.
  Validation, overwrite, stale-tab, concurrent-save, and stale-unit outcomes remain
  visible on the page where the form was submitted.
- **R6:** Daily-entry and measurement forms keep independent dates, values,
  messages, and submissions. A measurement save writes no daily-entry data and
  does not change TDEE or calorie-target calculations.

## Scope

Keep one measurement session per date, canonical cm storage, current sex/height
for derived estimates, existing bounds, and existing display precision. No schema
change, dependency, configurable schedule, or new JavaScript is needed.

External results remain in P2.1 B. Charts, measurement deltas, BMI, waist-to-height
ratio, calendar markers, notifications, and weekly summary statistics remain in
their existing later milestones. This increment adds an in-page cadence prompt,
not a scheduling system or a new weekly record type.

## Context and patterns

- `src/tdee_calculator/body_fat.py`: pure `build_row` and `build_summary` already
  distinguish the latest usable estimate from newer sessions without estimates.
- `src/tdee_calculator/routes/today.py`: `render_home` builds the dashboard and
  daily form context; `date` and `range` currently belong to the daily workflow.
- `src/tdee_calculator/routes/measurements.py`: `measurement_values` loads raw
  readings, and `save` owns validation, edit guards, conditional persistence,
  failure rendering, and the success redirect.
- `src/tdee_calculator/measurement_form.py`, `edits.py`, and `measurements.py`:
  established parsing, unchanged-value preservation, version checks, and storage.
- `src/tdee_calculator/templates/measurements.html`: current form, errors, history,
  and instructions. Reuse its fields rather than maintaining another form.
- `src/tdee_calculator/templates/_log_form.html` and
  `static/date-selector.js`: the daily date loader and save form must continue
  targeting only daily entry elements.
- `tests/test_measurement_routes.py`, `tests/test_concurrent_saves.py`, and
  `tests/test_app.py`: real-database coverage for the existing mutation contracts.
- `AGENTS.md` and `docs/testing.md`: deterministic isolated tests, strict types,
  independently established expected answers, and the full quality gate.

There are no `docs/brainstorms/` or `docs/solutions/` documents in this checkout.
The conversation and `docs/plans/p2-1-measurements.md` are the scope sources.
Local patterns are sufficient; this changes presentation and reuses existing
equations and persistence rather than introducing an external-service contract.

## Behavior decisions

| Area | Decision and rationale |
| --- | --- |
| Home placement | Put Measurements below the daily logging area and before the existing statistics/chart, outside the `dashboard.has_entries` condition. Keep the normal daily inputs easy to reach. |
| Latest circumferences | Show all four site labels for the newest session, with a dash for unrecorded sites. Do not fill gaps with older readings. |
| Latest estimate | Reuse the current selection of the newest usable estimate. Label it Navy and give its own date. If the newest session has no estimate, show its reason; if an older estimate exists, show both dates. |
| Edit action | **Edit latest** loads the newest actual session, including a partial session. Older sessions are reached through full history. |
| Log action | **Log measurements** loads today, prefilled if today already has a session. New dates start blank; never copy older readings into a new date. |
| Weekly cadence | Use newest saved session date + seven days, including partial sessions. Corrections do not reset the cadence through `updated_at`; backfills only change the prompt if they become the newest session. |
| Form expansion | Home normally shows a collapsed native `details` form loaded with today, the same as **Log measurements**. Explicit log/edit navigation, measurement errors, and measurement save confirmation open it. A present `circumference_date` always opens the form, even when invalid or in the future; it then loads the date `requested_day` falls back or clamps to. The workflow works without JavaScript. |
| Return destination | The existing measurement POST accepts a bounded page source: home or measurements. Missing/unrecognized sources use the existing measurements-page behavior. Never accept an arbitrary return URL. Home success redirects to `/?date=<home_date>&range=<range>&circumference_date=<saved>&circumference_saved=<saved>`: the form reopens on the saved session and the confirmation appears inside the measurement section. A measurement save never sets the daily `saved` parameter. |
| Parameter names | New home query parameters and IDs say what was measured: `circumference_date`, `circumference_saved`, `circumference-log-heading`. A bare `measurement` prefix would be ambiguous once P2.1 B adds body-fat results from other sources, and next to weight and height. |
| POST field names | `date` keeps its current meaning in the measurement POST: the session date. The home form adds `source=home`, `home_date` (the selected daily date), and `range` (the chart range). The standalone form sends none of them. Never reuse `date` for the daily date. |
| Date display | Dates use the existing `short_date` filter (“Sat 3 Oct”, with the year when it differs), like the rest of the app. |
| Daily context | Home measurement navigation and save responses retain the selected daily date and chart range. Each form submits its own values; unsaved input in the other form is not a cross-form draft persistence feature. Daily navigation (the date selector and chart range links) does not carry `circumference_date` and returns the measurement section to its collapsed default; carrying the date without its unsaved readings would preserve only half the draft. |

Cadence copy uses explicit dates, without an overdue/missed-log count:

| Saved sessions relative to today | Home prompt |
| --- | --- |
| None | “No measurements yet. Log your first session.” No next date is invented. |
| Last session Sat 3 Oct; today Fri 9 Oct | “Last measured Sat 3 Oct · next suggested Sat 10 Oct.” |
| Last session Sat 3 Oct; today Sat 10 Oct | “Last measured Sat 3 Oct · suggested measurement today.” |
| Last session Sat 3 Oct; today Mon 12 Oct | “Last measured Sat 3 Oct · next suggested Sat 10 Oct. Log when ready.” |

## Implementation units

- [ ] **Unit 1: Build the home summary and cadence view model**

**Requirements:** R1, R2, R4. **Dependencies:** P2.1 A's existing summary.

**Files:** Create `src/tdee_calculator/measurement_dashboard.py` and
`tests/test_measurement_dashboard.py`. Reuse `src/tdee_calculator/body_fat.py`.

**Approach:** Add a small pure home view model that composes the existing summary
with an explicitly passed today. Expose the newest measurement row separately
from the latest usable estimate, the newest row's missing-estimate reason, and the
next suggested date/state. Reuse site means and estimate calculation; do not
reimplement them. Read the clock only in the route layer through `clock.py`.

**Patterns:** `body_fat.py` and `dashboard.py` use typed view models with no web,
database access, or clock reads. Existing display units and precision apply.

**Test scenarios:**

1. Empty sessions produce no latest row, estimate, or suggested date.
2. Complete Oct 3 session plus waist-only Oct 8 session produce Oct 8
   circumferences, Oct 3 estimate, the Oct 8 missing-sites reason, and Oct 15 as
   the next suggested date. No old neck reading appears in the Oct 8 row.
3. With an Oct 3 newest session, fixed today values Oct 9, 10, and 12 yield the
   future, today, and past prompt states respectively, always anchored to Oct 10.
4. Sep 27 yields Oct 4; Dec 28 yields Jan 4 of the following year. Calendar-week
   boundaries do not force a new measurement slot.
5. Missing sex/height or an out-of-range estimate still retains raw readings and
   the date, with the existing reason and Settings link flag where applicable.
6. Known readings display in cm for kg settings and inches for lb settings; use
   existing independently verified estimate fixtures rather than copied equations.

**Verification:** Deterministic tests establish selection and cadence without
changing the existing calculation or measurement-summary contracts.

- [ ] **Unit 2: Share the form and preserve the save contract across pages**

**Requirements:** R3, R5, R6. **Dependencies:** Unit 1; existing conditional storage.

**Files:** Create `src/tdee_calculator/routes/measurement_context.py` and
`src/tdee_calculator/templates/_measurement_form.html`. Modify
`routes/measurements.py`, `routes/today.py`, `templates/measurements.html`, and
`templates/index.html` under `src/tdee_calculator/`. Add
`tests/test_home_measurement_routes.py`; extend `tests/test_measurement_routes.py`
and `tests/test_concurrent_saves.py` where needed.

**Approach:** Extract only the shared form values and display metadata from the
measurement route into a route-layer helper. Extract its form and feedback into
a template partial with explicit form context and destination-aware edit/reload
links. Keep the parser, edit checks, and database mutation in the existing POST.

Home uses a distinct `circumference_date` query parameter to load and open the form;
the existing `date` remains the selected daily-entry date. Invalid/future requested
measurement dates follow `requested_day`'s existing fallback/clamp behavior.
Namespace measurement context so it cannot replace daily `form_values`, `errors`,
`saved`, or conflict notices. Give the two forms distinct control/error IDs: both
`_log_form.html` and the current measurement section use `id="log-heading"`, so the
partial renames its heading to `circumference-log-heading` and keeps
`measurement-date` and a measurement-specific date error ID. Every `render_home`
call, including daily-entry 422/409 failures, builds the measurement section.

The measurement POST dispatches only its rendering/redirect destination from the
page source. Home failures render home with the measurement form open; success
uses a 303 redirect to home with the saved measurement date and a separate
measurement confirmation. Carry the daily date and chart range through the
`home_date` and `range` fields, normalized with `requested_day` and `parse_range`. Standalone submissions retain their existing
redirect and message behavior. Conflict/reload links load the relevant session
on the originating page. Stale-unit failures reload saved readings in current
units rather than echoing old-unit input under new labels.

Avoid route import cycles: home reads the shared context helper, not the
measurement route. The measurement save route can call home rendering. Do not
move unrelated daily or measurement domain logic as part of this extraction.

**Execution note:** Start with failing real-database tests for home submission and
failure rendering; keep the standalone contract tests passing through extraction.

**Test scenarios:**

1. A home form saves readings through the real POST, persists cm values, returns
   a 303 to home, and confirms measurements without displaying “Saved” for a
   daily entry. Repeat in both units; no daily entry is created or modified.
2. Log loads today; Edit latest loads the newest actual session even when its
   estimate is missing. Today already saved means prefilled edit, not duplication.
3. With daily date Oct 2 and measurement date Oct 8, the fields remain independent
   across measurement save, redirect, errors, and reload links; chart range stays
   selected. The success redirect sets `circumference_saved`, not `saved`. Changing
   the chart range from that page keeps daily date Oct 2 and returns the measurement
   form to collapsed today. Daily submission still reads only the daily form and
   save path.
4. Empty, invalid, or future-date POSTs return 422 on home, keep typed measurement
   values and errors in the open measurement form, and leave all rows unchanged.
5. Changing the form date to an existing unloaded session returns 409 on home,
   offers the correct home Edit link, and preserves both sessions.
6. Stale edits, deleted sessions, competing creation, and a save landing between
   checking and writing return 409 with the proper home reload/edit action and
   no overwritten or recreated data. Use existing race-test patterns.
7. A weight-unit change returns 409 with fresh current-unit values; an energy-unit
   change alone does not reject a measurement save. Unchanged readings survive
   reload/save without conversion drift.
8. Missing or unrecognized page sources use the standalone behavior; submitted
   source/context values cannot redirect outside the two supported pages.
9. Cross-origin home-source mutation remains rejected by the existing middleware.
   Existing standalone create/edit/delete behavior remains covered.
10. Daily-entry 422 and 409 responses still render the collapsed measurement
    section with the saved summary, and contain no duplicate IDs.

**Verification:** Both forms exercise one mutation path with the same guards,
isolated form state, and destination-correct success/failure responses.

- [ ] **Unit 3: Finish the home presentation and handoff**

**Requirements:** R1–R6. **Dependencies:** Units 1 and 2.

**Files:** Create `src/tdee_calculator/templates/_measurement_summary.html` and
`templates/_measurement_macros.html`. Modify `templates/index.html`,
`templates/measurements.html`, `templates/_measurement_form.html`,
`templates/_log_form.html`, and `static/style.css`
under `src/tdee_calculator/`. Extend `tests/test_home_measurement_routes.py` and
`tests/test_dashboard_routes.py`. Update `docs/roadmap.md` and
`docs/plans/p2-1-measurements.md` at implementation completion.

**Approach:** Render the compact section unconditionally, with clear site labels,
dates, Navy method label, existing estimate uncertainty/target note, cadence copy,
and Log/Edit/full-history actions. Reuse the current responsive fields, labels,
error associations, native disclosure, and date formatting. Move the `estimate`
macro out of `measurements.html` into `_measurement_macros.html` and import it in
both pages. Give the instructions `details` element `id="how-to-measure"` and link
to `/measurements#how-to-measure`; keep the full history and delete controls on
`/measurements`.

Keep daily date-selector IDs and script assumptions intact. Retain the daily
weight autofocus on the normal home view; omit it when the measurement form is
explicitly open so it does not pull users away from measurement feedback. Keep
associated alerts and save status within the open measurement section. Add only
the CSS needed for the section and its narrow layout.

**Test scenarios:**

1. Home with no daily entries renders the measurement empty state, or recorded
   measurements when those exist, without requiring dashboard/chart data.
2. Latest partial session and older usable estimate show separate dates and the
   missing-input reason; no estimate uses the newest session's date by accident.
3. Missing settings expose raw readings and a Settings link; all-unusable histories
   show the latest reason. Future/today/past cadence copy matches Unit 1 outcomes.
4. The default form is collapsed; log/edit query, validation/conflict responses,
   and save confirmation open it. Forms have no nested form elements or duplicate
   IDs; measurement messages are associated with their own controls.
5. Real saves on adjacent dates in the same week both succeed. Backfilling an
   older date and correcting an existing session do not move the cadence anchor;
   deleting the newest session on `/measurements` makes home use the next newest.
6. Adding/changing measurements leaves dashboard TDEE and target results unchanged
   for fixed daily logs/settings. Existing daily date/range behavior remains intact.

**Verification:** Route assertions prove values/actions; manual browser checks
prove layout, keyboard operation, and daily date-selector behavior. Documentation
records actual completion only after these checks pass.

## Verification and risks

Implementation must pass the repository's full `./check.sh` gate, including Ruff,
strict mypy, pyright, and tests with branch coverage. Use fixed dates and real
temporary databases for mutations. Automated validation and the browser checks
below are separate implementation acceptance gates.

For manual checks, start with a separate temporary `TDEE_DATA_DIR`; never read or
write real `data/`. Check desktop and 375px widths, keyboard navigation, and
JavaScript disabled: empty state, complete/partial histories, inline create/edit,
422/409 recovery, both units, weekly prompt boundaries, and daily logging/date
selection. Confirm mobile fields and actions fit without horizontal overflow.

The main risks are mixed daily/measurement context, destination-specific failure
links, and misleading dates when an estimate is older than the newest session.
Namespaced context, a shared save/form path, and explicit two-date test fixtures
address these. No migration or record transformation is required.

## Delivery and documentation

Sequence Unit 1 → Unit 2 → Unit 3 in one follow-up increment. The current checkout
already contains the pure body-fat summary and shared edit helpers; no unrelated
cleanup units from the route/domain refactor plan are prerequisites.

Implement on its own branch, not `feat/p2-measurements`, so A's PR stays reviewable
on its own. Preferred: merge A, then branch from `main`. If work starts before A
merges, branch from `feat/p2-measurements` and rebase onto `main` once A lands.

Planning changes add the follow-up link and sequencing to the roadmap and P2.1
plan without changing completed A checkboxes. On implementation completion,
record its verification status and then return to P2.1 B. Exact helper/type names
and final responsive spacing may be settled during implementation; there are no
unresolved product blockers for this scope.

## Sources

- User conversation: home display/editing, then agreement to weekly guidance
  while retaining dated sessions.
- [P2.1 measurements](p2-1-measurements.md): existing form, estimate selection,
  storage/precision decisions, and standalone save contract.
- [Roadmap](../roadmap.md): measurement sequencing and daily-completeness rules.
- [Route/domain separation plan](2026-10-10-1117-separate-route-and-domain-logic-plan.md):
  route-layer form work and pure calculation/view-model boundaries.
- [Testing standards](../testing.md).

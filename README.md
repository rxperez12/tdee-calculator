# TDEE Calculator

A local, single-user tracker for daily weight, calorie intake, tape measurements,
and estimated energy expenditure.

Install [uv](https://docs.astral.sh/uv/), then start the app:

```sh
./run.sh
```

The default address is `http://127.0.0.1:8765`. The app stores its SQLite database
and startup backups in `data/`. Set `TDEE_DATA_DIR` to use another directory.

## Home dashboard

Current targets, TDEE, weight trends, and the latest dated measurement summary
appear above the daily calendar. These summaries stay current when you review an
older day. The weight chart sits below the logging workspace.

Today is selected on arrival. Choose a calendar day or use **Load day** to review
and correct its records. The editor sits beside the month on desktop and below
it on mobile. Weight/calories and the expandable measurement form save
independently; saving one never submits the other. Navigation loads saved records
and discards unsaved edits.

Use **Choose stats** to show recorded weight, calories, tape-session means, or a
Navy body-fat estimate. You can also clear all choices. Missing values stay
distinct from zero, and measurements are shown only on their actual session
date. Tape markers remain visible regardless of the selected stats. Tape fields
and Navy estimates use the current profile settings.

The calendar lists incomplete past days starting with your first saved weight or
calorie value. Today, future dates, and dates before tracking began are excluded.
Optional measurements never count as missing daily logs.

Weight and calorie streaks are independent. Each counts consecutive dates back
from today if recorded, otherwise yesterday. Zero calories counts as recorded;
an unfinished today preserves yesterday's run. Streaks use all history and update
after corrections or deletions.

Month browsing keeps the selected day, even when it is outside that month.
Selecting a day or choosing **Today** changes the displayed month to match.
Stat choices, chart range, month, and measurement disclosure survive saves and
error recovery through URL/form state. A fresh visit to `/` restores defaults.
Calendar navigation and both logging forms work without JavaScript.

History, the standalone Measurements page, Settings, and CSV export remain
available from navigation. External body-fat results and optional measurement
polish remain pending in [the roadmap](docs/roadmap.md).

## Development

Run the required formatting, lint, type, and coverage checks:

```sh
./check.sh
```

Use an isolated directory for manual testing rather than your personal records:

```sh
TDEE_DATA_DIR=/tmp/tdee-demo ./run.sh
```

Application data is stored in kg, kcal, and cm; Settings controls input and display
units. Architecture and test conventions are in [AGENTS.md](AGENTS.md) and
[docs/testing.md](docs/testing.md). Implementation plans live in `docs/plans/`.

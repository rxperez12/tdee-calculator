# Milestone 5: Dashboard and chart

**Goal:** The home page answers "what should I eat today, and how am I doing?" in one
glance, right next to the form you log with. It shows today's target, TDEE with how it
was estimated, trend weight and rate, progress toward the goal, and a weight chart with
a range selector. Every number comes from `calc.py`. This milestone only wires the math
to the page and formats the results.

**Done when:**

- `/` shows, top to bottom: today's target (the one big number), the log form, the
  stat row (TDEE, trend, goal), and the chart with its range selector and table view.
- The TDEE tile names its method ("From your logs", "Logs + formula", "Formula
  estimate") and shows logged days, estimated days, and the dates the estimate covers.
  It never shows the blend share as a percentage or as "confidence".
- The last weigh-in date is always visible. If it's 3 or more days old, the page says so.
- The goal tile appears whenever there are entries. With no goal set, it links to
  Settings. With a goal, it shows the distance left and, when the rate points toward
  the goal, the weeks and date "if you keep this rate". When the rate points away,
  when the date is more than 10 years out, or when the rate needs an intake below the
  floor, it says why there's no date and links to Settings.
- **The page never suggests an intake below the minimum** (1,200 kcal a day, or 1,500
  for men or when sex isn't set), and never shows a displayed target under the
  displayed floor. When a deficit pushes the target below it, the page suggests the
  fastest rate that stays at the floor. Gaining and maintaining are affected only when
  the TDEE estimate itself is below the floor, and then the message is about the
  estimate, not the goal.
- A TDEE estimate of zero or less is never shown as a number. The page says the
  estimate doesn't look right and points to recent entries and body stats.
- The formula estimate (Mifflin-St Jeor × activity) is shown for reference, or says
  which body stats are missing.
- Every state in the "States" table has a useful screen, including calorie-only logs
  and accepted-but-extreme settings (tiny rates, aggressive deficits). No settings value
  the form accepts can crash the page.
- The chart shows weigh-ins as dots, the trend as a line, the goal as a horizontal line,
  and a dashed projection from today at the target rate. **4 weeks / 3 months / All**
  switches the range. The range defaults to 3 months and is kept in the URL.
- The chart has a text summary and a "Show data as a table" view. Both work without
  JavaScript, and the page is still usable if Chart.js fails to load.
- The chart follows light/dark mode, including a live switch.
- The recent-entries table moves to a new **History** page. Nav: Today | History | Settings.
- `app.py` is split into routers (deferred from milestone 4).
- `./check.sh` passes. No migration.

## Decisions

| Question | Decision | Why |
| --- | --- | --- |
| Page layout | **`/` = today's target + log form + stats + chart. Recent entries move to `/history`.** | Decided in planning. The daily routine (weigh in, log, check the target) fits on one screen. The table is for occasional review and edits, so it can live on its own page. |
| The one big number | **Today's target**, or **TDEE** when there's no target | A dashboard gets one hero figure. The target is the number you act on. Without a rate, there's no target, so TDEE moves up. |
| Energy display rounding | **Steps of 10 kcal or 50 kJ, with thousands separators** ("1,950 kcal"). TDEE rounds to the nearest step. **Targets and the floor round up**, so 1,200 kcal shows as "5,050 kJ", not "5,000". | Settles the requirements' open question. The estimate's real error is in the hundreds of kcal, so a number like 1,947 is false precision. Nearest rounding could show a target under the displayed floor: 1,200 kcal = 5,020.8 kJ → "5,000" ≈ 1,195 kcal. Rounding up overstates by at most one step, which is the safe direction. Separators are only for display. Form inputs keep `format_energy`, which has none. |
| Other rounding | Trend weight 0.1 (`format_weight`), rate 0.01 per week (`format_rate`), weeks to goal **whole weeks** ("about 9 weeks"; "under a week") | Uses milestone 4's formats. A fractional week is false precision on a constant-rate projection. |
| Derived calc parameters | `min_span_days = ceil(window × 3/4)`, `blend_start_days = min_span_days`, `blend_full_days = window` | As decided in milestone 4. One function in `dashboard.py` derives them. |
| Rate of change | **`calc.weight_slope` × 7 over the TDEE window**, shown only with ≥ 10 weigh-ins spanning ≥ `min_span_days` | Uses the same evidence bar as the TDEE estimate, but doesn't need calories. A two-point slope is noise. |
| Formula weight input | **Current trend weight** | As decided in milestone 2: the trend smooths out water swings for the formula. |
| Which rate the ETA and projection use | **The target rate from Settings** | It matches the target number and the projection line. Your actual rate is already in the trend tile, and a second ETA would be clutter. |
| Rate pointing away from the goal | **No ETA and no projection.** The goal tile says "Your rate moves away from your goal" and links to Settings. | `goal_eta` returns `None`. Milestone 4 left this check to the dashboard. |
| Very slow rates | **More than 520 weeks (10 years) to the goal → no date and no projection.** The tile says "At this rate the goal is more than 10 years away". Check `remaining / rate` **before** calling `goal_eta`. | The form accepts −0.00001 kg/week, and `goal_eta` then raises `OverflowError` (a date past year 9999). Even −0.001 gives 6 Aug 2122. A cap is the honest answer to both. |
| Minimum intake | **An application guardrail of 1,200 kcal a day, or 1,500 for men or when sex isn't set.** These are `MIN_INTAKE_KCAL` constants in `dashboard.py`. A target below the floor is **never shown**. The math isn't clamped: `calc.daily_target` still returns the real value, and the dashboard decides not to display it. The page says "This is a guardrail, not medical advice." | Decided in review: don't suggest an obviously unhealthy number. The values come from general adult weight-management guidance ([AHA/ACC/TOS 2013](https://pmc.ncbi.nlm.nih.gov/articles/PMC5819889/)), where they're starting points for individualized plans. **The guardrail does not establish that a target or rate above it is safe for anyone in particular.** Without a known sex, use the more cautious value. `calc.py` stays a pure calculator, and the policy lives where the display decisions live. |
| Which floor rule applies | **Decided by TDEE, not by the rate's direction**, first match wins: TDEE ≤ 0 → **estimate invalid**: no TDEE number, no target, no projection, "Your TDEE estimate doesn't look right. Check your recent entries and body stats." · 0 < TDEE < floor → **estimate low**: show TDEE, no target, no projection, "This estimate is unusually low. Check your logs and body stats." · target < floor (only possible with a deficit) → **below floor**: show TDEE and suggest the fastest loss that stays at the floor. | One rule for losing, gaining, and maintaining. A low or negative TDEE (e.g. −200 kcal from 80 → 88 kg in 28 days on 2,000 kcal, probably a typo) is a data problem, so the message is about the data, whatever the goal. Only a TDEE ≤ 0 counts as invalid. A positive low value can be real for small, older, sedentary people, so it's shown, just never turned into a target. The raw estimate stays in the model for tests. |
| Below floor, the note | "Losing 0.75 kg a week would mean eating under 1,200 kcal a day. The fastest loss that stays at or above that is 0.72 kg a week." (TDEE 2,000) Plus a Settings link. **No ETA or projection** at the unsafe rate. | It turns a refusal into a next step. The suggested rate is `(floor − TDEE) × 7 ÷ density`, **truncated toward zero** at 0.01 so rounding can't land it under the floor. If it truncates to 0.00 (TDEE within a few kcal of the floor), use the "estimate low" wording instead of suggesting a 0 rate. |
| Gaining and maintaining | **Unaffected unless TDEE itself is below the floor.** A positive or zero rate gives a target at or above TDEE. | Bulking is a first-class use. Settings already allow up to +1.0 kg/week, and the goal checks work in both directions. |
| Range selector | **Links: `?range=4w`, `3m` (default), or `all`.** The server slices the data. An unknown value falls back to 3m. | Works without JavaScript, can be bookmarked, and the back button works. A local reload is instant. Links end in `#chart`, so the page doesn't jump to the top. |
| Range scope | **The range applies to the chart and its table only.** Stat tiles are always "now". | The selector sits directly above what it filters, so it's clear what it changes. |
| Trend in a range | **Compute the trend over all logs, then slice** | Starting the trend at the range's first day would restart the smoothing, and the line would change depending on the selected range. |
| Range lengths | **4w = 28 days, 3m = 91 days, All = today − first weigh-in, but at least 28 days.** Each range shows weigh-ins dated `today − range_days` through today. | "All" needs a concrete length for the projection cap. The 28-day minimum keeps a 3-day-old history from getting a 0-day cap. |
| Projection length | From (today, current trend) to the goal date, but **no further ahead than `range_days // 4` whole days** (7 for 4w, 22 for 3m) | Otherwise a goal a year away would squash the history into a corner. The exact date is in the goal tile anyway. Floor division keeps the end on a whole day. |
| Range with no weigh-ins | **No canvas, no table, no caption.** One sentence instead: "No weigh-ins in the last 4 weeks", with a link to All when older weigh-ins exist, or "No weigh-ins yet". | Old logs can still drive the stat tiles while the default 3-month range is empty. An empty chart with axes looks broken. |
| Y axis | Fits the visible weigh-ins, trend, and projection, **plus the goal line**. Not zero-based. | Weight isn't a magnitude chart, so starting at zero would flatten the trend. Including the goal shows how far away it is. Check this with seeded data (see "Deferred"). |
| Chart.js delivery | **Vendored into `static/vendor/`**: `chart.umd.min.js` and `chartjs-adapter-date-fns.bundle.min.js`, with their licenses and pinned versions | Local-first app: no third-party requests and it works offline. The date adapter gives week and month ticks on a real time axis, so we don't write tick logic. Both are MIT. |
| Passing data to JS | **`<script type="application/json" id="chart-data">{{ chart \| tojson }}</script>`**, read with `JSON.parse` | No inline JS, and `tojson` escapes `<`, `>`, `&`. Values are already converted to display units on the server, so the JS has no unit logic. |
| JS scope | **One file, `static/dashboard.js`, that only draws.** No math, no unit conversion, no fetching. | Everything worth testing is in Python, where pytest reaches it. |
| JS testing | **Python tests cover the chart payload. Drawing is checked by a manual browser checklist.** Playwright stays deferred. | `docs/testing.md` asks for focused browser checks once a feature depends on JS. With logic-free JS, a checklist covers it. Record this in `testing.md`. Revisit if the JS grows beyond drawing. |
| Chart colours | Trend and projection **`#2a78d6` light / `#3987e5` dark** (dataviz reference slot 1, validated against `#fff` and `#121212`: all checks pass). Weigh-ins in muted gray `#898781`. Goal line in secondary ink `#52514e` / `#c3c2b7`. | The emphasis pattern: one accent for the trend (the signal) and gray for the raw dots (the noise). Only one hue, so there's nothing to confuse under colour blindness. |
| Colour tokens | **CSS custom properties with a `prefers-color-scheme: dark` override, not `light-dark()`** | The canvas reads colours with `getComputedStyle`, which returns a `light-dark()` value unresolved. Plain values per mode are readable. The page gets an explicit background (`--surface`), so the dots' 2px surface ring matches it. |
| Dashes | **Only the projection is dashed.** Grid and goal lines are solid hairlines. | Dashing means "projected", so it's reserved for the one series that is projected. |
| Animation | **Off** | A data readout has nothing to animate, and this also covers `prefers-reduced-motion`. |
| Dev data | **`scripts/seed_dev_data.py`** writes ~120 days of deterministic synthetic entries to a dev data directory | As suggested in the roadmap: the dashboard isn't built against an empty DB. It refuses to write to the real `data/`. |

## The page

### Layout

```text
Nav: Today | History | Settings                        (main widens to ~60rem on Today)

┌ hero ───────────────────────┐ ┌ log form ─────────────────────┐   two columns ≥ 48rem,
│ Eat about                   │ │ Log Thu 8 Oct                 │   stacked below
│ 1,950 kcal today            │ │ Date [....] Weight [..] kcal [..]
│ to lose 0.50 kg a week      │ │ [Save]                        │
└─────────────────────────────┘ └───────────────────────────────┘
┌ TDEE ──────┐ ┌ Trend ──────┐ ┌ Goal ───────┐       grid: repeat(auto-fit, minmax(12rem, 1fr))
│ 2,540 kcal │ │ 79.4 kg     │ │ 4.4 kg to go│
│ From logs  │ │ −0.42 kg/wk │ │ ~9 weeks    │
│ 26 logged, │ │ Last weigh- │ │ Thu 10 Dec  │
│ 2 estimated│ │ in today    │ │ if you keep │
│ 6 Sep–6 Oct│ │             │ │ this rate   │
└────────────┘ └─────────────┘ └─────────────┘
Formula estimate: 2,480 kcal (Mifflin-St Jeor × moderate activity)   ← small reference line

Weight  [4 weeks] [3 months] [All]                               ← range above the chart
┌ figure ──────────────────────────────────────────────────────┐
│ chart                                                         │
│ figcaption: Trend 82.1 → 79.4 kg over the last 3 months. Goal 75.0 kg.
│ ▸ Show data as a table                                        │
└───────────────────────────────────────────────────────────────┘
```

DOM order matches visual order: hero, form, stats, chart. The weight input keeps
`autofocus`, so you can type right away.

### States

`dashboard.py` decides the state. Templates only pick the wording. Each column below is
decided on its own, and the first matching row wins.

#### Hero

| # | Situation | Hero |
| --- | --- | --- |
| 1 | No entries | "Log your first weigh-in to get started". Nothing else on the page except the form. |
| 2 | Entries but no weigh-ins (calorie-only logs) | "Log a weigh-in to start your estimate". The formula and the trend both need a weight. |
| 3 | Estimate invalid (TDEE ≤ 0) | "Your TDEE estimate doesn't look right" + links to History and Settings. No number. |
| 4 | Estimate low (0 < TDEE < floor) | **TDEE** + "This estimate is unusually low. Check your logs and body stats." No target, whatever the rate. |
| 5 | Target exists and is at or above the floor | **Target**: "Eat about 1,950 kcal today" + "to lose 0.50 kg a week" / "to gain…" / "to maintain your weight" (rate 0) |
| 6 | Target below the floor (a deficit) | **TDEE** + the floor note with the fastest rate that stays at the floor, + "This is a guardrail, not medical advice." |
| 7 | TDEE, no rate set | **TDEE**: "You burn about 2,540 kcal a day" + "Set a goal rate in Settings to get a daily target" |
| 8 | Weigh-ins, no TDEE | "Your TDEE estimate is on its way" (the TDEE tile shows progress) |

#### Tiles

All hidden in hero row 1. In hero row 3, the TDEE tile keeps its method and coverage but shows "—" instead of a number.

| Tile | States |
| --- | --- |
| TDEE | Estimate: value, method, "26 logged, 2 estimated · 6 Sep–6 Oct". No estimate: progress against **all three** requirements: "8 of 10 weigh-ins · 15 of 21 days · calories on 12 of 15 days (90% needed)", with a Settings link for a formula estimate in the meantime. When only calories are missing, the line says so: "Weigh-ins are enough. Log calories on 2 more days." |
| Trend | Trend weight and "Last weigh-in Thu 8 Oct". Rate once the gate is met. **≥ 3 days old:** "Last weigh-in Sat 3 Oct (5 days ago)", and the TDEE tile says "through Sat 3 Oct". **No weigh-ins:** "No weigh-ins yet". |
| Goal | In this order: no goal → "Set a goal weight" link · goal but no weigh-ins → goal value + "Log a weigh-in to see how far you have to go" · within 0.05 kg → "Goal reached" · rate unset or 0 → distance + "Set a rate to see when you'd get there" · rate points away → distance + "Your rate moves away from your goal" · estimate invalid, estimate low, or target below floor → distance + "See the note above" · more than 520 weeks → distance + "More than 10 years away at this rate" · otherwise → distance, weeks, date, "if you keep this rate". |

**Chart:** the goal line whenever a goal is set. The projection only in the last goal
state (on track). The range-empty sentence when the range has no weigh-ins.

### Words, not just numbers

- Signed values get a verb: "losing 0.42 kg a week", "to gain 0.25 kg a week",
  "4.4 kg to go". Don't print a bare `-0.42` in prose. Inputs keep the signed number.
- Labels are sentence case, with no trailing colons. Units go next to the value ("2,540
  kcal").
- No green or red on stats. Direction is carried by the verb, so meaning never depends
  on colour.
- Dates: "Thu 8 Oct", plus the year when it isn't the current year. One Jinja filter
  (`short_date`) replaces the inline `strftime` calls in the templates.
- The hero and stat values use proportional figures. Only the tables use
  `tabular-nums`, which `table` already has.

## The chart

| Series | Mark | Colour | Notes |
| --- | --- | --- | --- |
| Trend | 2px line, no points (4px on hover) | `--chart-accent` | Drawn on top |
| Weigh-ins | dots r = 4 with a 2px `--surface` ring, `hitRadius` ≈ 12 (24px target) | `--chart-muted` | The ring keeps dots readable where they cross the line |
| Projection | 2px **dashed** line, two points | `--chart-accent` | Only in the on-track goal state |
| Goal | 1px solid horizontal line across the plot | `--chart-goal` | The legend label carries the value: "Goal 75.0 kg" |

- **Legend:** always shown (there are four series), with line keys for lines and a
  dot for weigh-ins. Text uses text colours, never the series colour.
- **Tooltip:** at the nearest date, show the weigh-in and the trend there, value first:
  "79.8 kg weigh-in · 80.1 kg trend". The projection's end point shows its date and
  weight. The goal isn't in the tooltip, since the legend has it.
- **Axes:** a time x-axis (ticks from the adapter), and a y-axis labelled "Weight (kg)"
  or "(lb)". Gridlines are 1px solid `--chart-grid`, axis text `--chart-text`.
- **Size:** the container has `position: relative` and
  `height: clamp(16rem, 40vh, 24rem)`, with `maintainAspectRatio: false`. Chart.js draws
  the axes inside the canvas, so labels can't overflow.
- **Accessibility:** the `<canvas>` has `role="img"` and an `aria-label` with the same
  text as the visible `<figcaption>`: "Trend 82.1 → 79.4 kg over the last 3 months.
  Goal 75.0 kg. Projected 78.1 kg by Thu 29 Oct at your target rate." The projection
  sentence appears only when the projection does. The table in `<details>` lists date,
  weigh-in, and trend for the range, newest first. The caption and table together
  hold everything the tooltip shows, so it never holds information found nowhere else.
- **No JS / load failure:** the server renders `<p class="chart-fallback">Chart
  unavailable. The table below has the same data.</p>` inside the container.
  `dashboard.js` removes it only after the chart is drawn.
- **Theme:** read the tokens with `getComputedStyle(document.documentElement)` at draw
  time, and redraw on `matchMedia('(prefers-color-scheme: dark)')` `change`.

Payload, all in display units:

```json
{
  "unit": "kg",
  "start": "2026-07-08",
  "end": "2026-10-29",
  "weighIns": [{"x": "2026-07-08", "y": 82.3}],
  "trend":    [{"x": "2026-07-08", "y": 82.1}],
  "goal": 75.0,
  "projection": [{"x": "2026-10-08", "y": 79.4}, {"x": "2026-10-29", "y": 78.1}]
}
```

`goal` is `null` and `projection` is `[]` when they don't apply. `end` is today plus
the projection length, or today when there's no projection.

## Files

```text
src/tdee_calculator/
  web.py                         # new: templates + filters, get_session, Settings/Form
                                 #      dependencies, units_match, STALE_UNITS_NOTICE
  routes/__init__.py             # new
  routes/today.py                # new: GET /, POST /entries, POST /entries/{d}/delete
  routes/history.py              # new: GET /history
  routes/settings.py             # new: moved settings routes, unchanged
  app.py                         # edit: create_app, lifespan, middleware, include routers
  calc.py                        # edit: window_progress, shared with logged_tdee
  dashboard.py                   # new: Dashboard view model, build_dashboard, chart payload (pure)
  entries.py                     # edit: all_day_logs(session) -> list[DayLog]
  units.py                       # edit: format_energy_display
  templates/
    base.html                    # edit: nav Today | History | Settings; main width block
    index.html                   # edit: hero + form + stats + chart (includes)
    _log_form.html               # new: the existing form, moved out unchanged
    _stats.html                  # new: hero + stat tiles + formula line
    _chart.html                  # new: range links, figure, canvas, fallback, table
    history.html                 # new: the recent-entries table, moved from index.html
  static/
    style.css                    # edit: tokens, surface, grid, tiles, range control, chart box
    dashboard.js                 # new
    vendor/chart.umd.min.js      # new, pinned; LICENSE alongside
    vendor/chartjs-adapter-date-fns.bundle.min.js   # new, pinned; LICENSE alongside
scripts/
  seed_dev_data.py               # new
tests/
  test_calc.py                   # edit: window_progress
  test_dashboard.py              # new (pure)
  test_dashboard_routes.py       # new (real DB through TestClient)
  test_units.py                  # edit
  test_entries.py                # edit
  test_app.py                    # edit: recent list now on /history; delete redirects there
  test_seed.py                   # new
docs/
  testing.md                     # edit: JS testing decision
  roadmap.md                     # edit: link this plan
```

## Tasks

Do them in order. Each one leaves `./check.sh` passing.

### 1. Split `app.py` into routers (pure refactor)

Move code without changing behaviour. The test suite is the safety net: it must pass
with no test edits.

- `web.py` holds what every router shares: `templates` (with the filters), `get_session`,
  `SessionDependency`, `current_settings`, `SettingsDependency`, `get_form_values`,
  `FormDependency`, `units_match`, `STALE_UNITS_NOTICE`.
- Each `routes/*.py` defines `router = APIRouter()`. `render_home` and `render_settings`
  become module-level functions in their routers. They don't need anything from
  `create_app`'s closure, since the session comes from `request.app.state`.
- `app.py` keeps `create_app`, the lifespan, the middleware, the static mount, and
  `include_router` calls. `app = create_app()` stays, because `run.sh` and the tests use it.
- In TypeScript terms, `APIRouter` is like an Express `Router()` mounted with `app.use`.

### 2. History page

- `GET /history` renders `history.html`: the existing table and the "N entries" count,
  moved unchanged. Edit links still go to `/?date=…`, because the form lives on Today.
- `POST /entries/{date}/delete` now redirects to `/history`, since that's where the
  Delete button is.
- Nav: "Today" (`/`), "History", "Settings", with `aria-current` as now.
- Tests: move the list assertions in `test_app.py` (`"0 entries"`, `"No entries yet"`,
  `"1 entries"`) to `/history`. Delete → 303 to `/history`. Fix "1 entries" →
  "1 entry" while you're there.

### 3. Display formatting (`units.py`)

```python
def format_energy_display(kcal: float, unit: EnergyUnit) -> str: ...  # "1,950" / "8,150"
```

Converts, rounds to a step of 10 kcal or 50 kJ, and adds thousands separators.
It's for display only. A keyword argument `round_up: bool = False` switches from
nearest to ceiling, for targets and the floor (see "Energy display rounding").
Register two Jinja filters: `energy_display` (nearest, for TDEE and the formula) and
`intake_display` (round up, for targets and the floor). Also add a
`short_date(d, today)` filter in `web.py`.

- Before taking the ceiling, round the converted value to 6 decimal places. Float
  noise like `2000.0000000000002` would otherwise display as "2,010".

Tests: 1,947 kcal → "1,950"; 2,000 kcal in kJ (8,368) → "8,350"; 950 → "950" (no
separator); a negative value keeps its sign. Rounding up: 1,200 kcal → "1,200";
1,201 → "1,210"; 1,200 kcal in kJ (5,020.8) → "5,050", not the nearest-step "5,000";
`2000.0000000000002` → "2,000". Avoid exact ties in the nearest-step tests: rounding
ties don't matter for display.

### 4. Loading logs (`entries.py`)

`all_day_logs(session) -> list[DayLog]`, oldest first. This is the one place `Entry`
rows become `DayLog`s, as planned in milestone 2. Test it with real SQLite: weight-only,
calories-only, and both; order; empty DB → `[]`.

All rows is fine. Even years of data is a few thousand rows.

### 5. Window progress (`calc.py`)

The TDEE tile needs to say what's still missing: weigh-ins, span, **or calories**.
Those rules live in `logged_tdee`: the window bounds, and calories counted over
[first, last) weigh-in. Rebuilding them in `dashboard.py` is how the two would drift
apart, so extract them into a function `logged_tdee` uses itself.

```python
@dataclass(frozen=True)
class WindowProgress:
    weigh_ins: int
    span_days: int            # first to last weigh-in in the window; 0 with fewer than 2
    calorie_days: int         # recorded totals in [first, last)
    calorie_days_needed: int  # smallest n with n / span_days >= min_calorie_coverage

def window_progress(
    logs: Iterable[DayLog], as_of: date, *, window_days: int = 28,
    min_calorie_coverage: float = 0.9,
) -> WindowProgress: ...
```

- `calorie_days_needed` uses **the same comparison as `logged_tdee`**, the smallest
  `n` where `n / span >= coverage`. Don't use `ceil(coverage × span)`, since a float
  product like `0.9 × 30` can land a hair off and disagree by one day.
- `logged_tdee` calls it for its gates, then does the fit as before.

**Execution note:** refactor first, with `test_calc.py` unchanged and passing, then add
the new tests.

Tests (`test_calc.py`):

- [ ] 29 weigh-ins over 28 days with no calories → 29 weigh-ins, span 28, 0 calorie
      days, 26 needed. This is the case where both weigh-in counters are full but
      there's still no TDEE.
- [ ] Same with 25 calorie days → 25 of 26. `logged_tdee` is `None`. With 26 → it
      returns an estimate.
- [ ] Calories on the last weigh-in's date don't count (the interval is [first, last)).
- [ ] One weigh-in → span 0, 0 needed. No weigh-ins → all zeros.
- [ ] Logs outside the window are ignored, matching `logged_tdee`'s bounds.

### 6. Dashboard model (`dashboard.py`)

Pure, like `calc.py`: no DB, no clock, no web. `today` is passed in. It calls `calc`
and decides states. It does no formatting except converting the chart payload's
numbers to display units.

```python
Range = Literal["4w", "3m", "all"]

MIN_INTAKE_KCAL = {Sex.FEMALE: 1200, Sex.MALE: 1500}
MIN_INTAKE_UNKNOWN_SEX = 1500
MAX_ETA_WEEKS = 520

@dataclass(frozen=True)
class Dashboard:
    today: Date
    has_entries: bool
    last_weigh_in: Date | None
    days_since_weigh_in: int | None
    trend_kg: float | None
    rate_kg_per_week: float | None       # None until the rate gate is met
    estimate: TdeeEstimate | None        # from calc.estimate_tdee
    progress: WindowProgress | None      # set when estimate.logged is None
    formula_tdee: float | None
    missing_body_stats: tuple[str, ...]  # e.g. ("height", "birth date")
    target: TargetStatus
    goal: GoalStatus

TargetStatus = (                                   # small frozen dataclasses
    NoTarget | EstimateInvalid | EstimateLow | Target | TargetBelowFloor
)
GoalStatus = (
    NoGoal | GoalNoWeight | GoalReached | GoalNoRate
    | GoalAway | GoalNoSafeTarget | GoalTooSlow | GoalOnTrack
)

def calc_params(window_days: int) -> tuple[int, int, int]: ...   # min_span, blend_start, blend_full
def build_dashboard(logs: list[DayLog], settings: Settings, today: Date) -> Dashboard: ...
def parse_range(text: str | None) -> Range: ...                 # unknown → "3m"
def chart_payload(
    logs: list[DayLog], dashboard: Dashboard, settings: Settings, rng: Range
) -> dict[str, object]: ...
```

- **States as unions of small dataclasses**, not one class full of optional fields. A
  `match` on the type (Python's version of a TypeScript discriminated union) makes the
  template-facing code exhaustive, and mypy checks it. `Target` holds the kcal value.
  `TargetBelowFloor` holds the floor, the unsafe target (kept for tests, never
  rendered), and the fastest rate that stays at the floor. `EstimateInvalid` and
  `EstimateLow` hold the raw TDEE (and the floor) for tests. `GoalOnTrack` holds the `GoalEta`. `GoalNoRate` covers both
  an unset rate and a rate of 0.
- **Order of work** in `build_dashboard`: trend over all logs → current trend = last
  point → `window_progress` and `logged_tdee` with the derived parameters, window, and
  density from settings → formula (only if sex, height, birth date, activity, and a
  trend weight all exist; age is `calc.age_on`) → `estimate_tdee` → target → goal.
- **Target**, first match wins: no estimate → `NoTarget` · TDEE ≤ 0 →
  `EstimateInvalid` · TDEE < floor → `EstimateLow` · no rate → `NoTarget` ·
  `calc.daily_target(tdee, rate, density)` < floor → `TargetBelowFloor`, unless the
  suggested rate truncates to 0.00, which gives `EstimateLow` · otherwise `Target`.
  The estimate checks come before the rate check, so a low estimate is flagged even
  when no rate is set. The fastest rate at the floor is `(floor − tdee) × 7 ÷ density`,
  truncated toward zero at 0.01 in the user's weight unit, so the suggestion can't
  land under the floor.
- **Goal**, first match wins, as in the "States" table: no goal → no trend weight →
  reached (`goal_eta` with 0 weeks) → rate unset or 0 → points away → target is
  `EstimateInvalid`, `EstimateLow`, or `TargetBelowFloor` (`GoalNoSafeTarget`) →
  `remaining / rate > MAX_ETA_WEEKS` → on track. The 520-week check comes **before**
  `goal_eta` computes a date, which is what prevents the `OverflowError`.
- **Rate gate:** `window_progress` must show ≥ `MIN_WEIGH_INS` weigh-ins spanning ≥
  `min_span_days`. Set `MIN_WEIGH_INS = 10` here and have a test compare it with
  `calc.logged_tdee`'s default, the same way milestone 4 tied the `Settings` defaults
  to `calc`.
- **Chart payload:** the range starts at `today − range_days` (see "Range lengths").
  Slice the full trend list, never recompute it. Convert weights with
  `weight_from_kg` and round to 0.1 on the server, so the tooltip shows what the tables
  show. Only in `GoalOnTrack`, the projection runs from `(today, trend_kg)` to the
  earlier of the ETA date and `today + range_days // 4` days:
  - **The ETA ends it:** the end point is `(eta.date, goal)`, exactly on the goal line.
    Don't compute a weight for that day. `goal_eta` rounds to whole days, so a full
    day at the rate can overshoot: 80 → 79.88 kg at −1.5 kg/week gives an ETA of
    tomorrow, and `80 − 1.5 / 7` = 79.79 is past the goal.
  - **The ETA is today** (under half a day to go): no projection. A zero-length line
    is noise, and the goal tile already gives the date.
  - **The cap ends it:** the end weight is `trend + rate × days / 7`. The cap date
    falls before the actual crossing, so this can't pass the goal. Still clamp it to
    the goal as a guard.
  A range with no
  weigh-ins returns a payload with `"empty": true`, and the template shows the
  range-empty sentence instead of the figure.

Tests (`test_dashboard.py`). Build the logs synthetically, with answers worked out by
hand, as in `test_calc.py`:

- [ ] No logs → `has_entries` is false, everything else is `None`, `NoTarget`, `NoGoal`.
- [ ] Calorie-only logs → `has_entries`, no trend, no estimate even with full body
      stats (the formula needs a weight), progress shows 0 weigh-ins,
      `GoalNoWeight` when a goal is set.
- [ ] 5 weigh-ins over 6 days, no body stats → no estimate, progress 5 weigh-ins and
      span 5, rate `None`, missing stats listed.
- [ ] Same data plus full body stats → method "formula". Formula TDEE equals the
      Mifflin-St Jeor value worked out by hand at the trend weight.
- [ ] 28 days at 2,000 kcal with weights falling exactly 0.5 kg/week (the roadmap
      scenario) → TDEE 2,550 (`abs=1e-6`), method "logs", rate −0.5 kg/week.
- [ ] Window 14 → derived parameters (11, 11, 14). Window 28 → (21, 21, 28).
      Window 56 → (42, 42, 56). With window 28, a 21-day span is still "formula" (the
      ramp starts at 0), and a 24-day span with full coverage is "blend" at 3/7.
- [ ] Target: TDEE 2,550, rate −0.5, density 7,700 → `Target(2000)`. Rate unset →
      `NoTarget`. Rate 0 → equals TDEE. Rate +0.25 → 2,825 (gaining is unaffected).
- [ ] **Floor:** female, TDEE 2,000, rate −0.75 → target 1,175 → `TargetBelowFloor`
      with the fastest rate −0.72 kg/week. Rounding to the nearest would give −0.73,
      which means 1,197 kcal, under the floor, so this also pins down the truncation.
      Male or unset sex at TDEE 2,000, rate −0.5 (target 1,450) → below the 1,500
      floor. Female at exactly 1,200 → `Target` (the floor itself is allowed).
- [ ] **Estimate checks, independent of the rate:** female, formula TDEE 857 kcal →
      `EstimateLow` with rates of −1.5, 0, +0.1 (target 967, still under the floor),
      and with no rate set. Weights 80 → 88 kg over 28 days at 2,000 kcal → TDEE
      −200 → `EstimateInvalid`, again for any rate. The raw TDEE is kept on the
      state, and the goal state is `GoalNoSafeTarget` (no projection).
- [ ] TDEE less than 11 kcal above the floor with a loss rate → the suggested rate
      truncates to 0.00 → `EstimateLow`, not "lose 0.00 kg a week".
- [ ] **Too slow:** 80 → 75 kg at −0.00001 kg/week → `GoalTooSlow`, no exception
      (regression for the `OverflowError`). −0.01 (500 weeks) → on track.
      −0.009 (≈ 556 weeks) → too slow.
- [ ] Goal states in precedence order: unset; set with no weigh-ins; reached (within
      0.05 kg); rate unset; rate 0; pointing away (a gain goal with a negative rate,
      and a loss goal with a positive one); target below floor → `GoalNoSafeTarget` with
      no projection; on track (ETA date checked by hand), for both a loss and a gain.
- [ ] Last weigh-in 5 days before `today` → `days_since_weigh_in == 5`.
- [ ] Range slicing: the trend value on the first visible day is the same for "4w" and
      "all". This is the "compute over all, then slice" rule, so the test fails if the
      trend restarts at the range start.
- [ ] Range lengths: "all" with a first weigh-in 200 days ago → 200, cap 50 days.
      First weigh-in 3 days ago → 28, cap 7. "3m" cap → 22 days (91 // 4).
- [ ] Projection: capped as above. It reaches the ETA when that's sooner. Present only
      in `GoalOnTrack`.
- [ ] **Projection overshoot (regression):** trend 80, goal 79.88, rate −1.5 → the ETA
      is tomorrow, and the projection ends at exactly (tomorrow, 79.88), not 79.79.
      The same for a gain goal approached from below.
- [ ] Remaining 0.06 kg at −1.5 kg/week (0.28 days, so the ETA is today) → on track,
      with no projection.
- [ ] Weigh-ins only older than 91 days → the "3m" payload is empty, while the stats
      still come from those logs.
- [ ] Payload in lb: weights converted (80 kg → 176.4) and `unit == "lb"`.
- [ ] `parse_range`: "4w", "3m", "all" accepted; `None`, "", and "1y" → "3m".
- [ ] `MIN_WEIGH_INS` matches `calc.logged_tdee`'s default.

### 7. Today page: stats and hero (`_stats.html`, `routes/today.py`)

- `render_home` builds `all_day_logs` → `build_dashboard(…, clock.today())` and passes
  `dashboard` into the context. POST re-renders (422 and 409) get it too, so an error
  page still shows the dashboard.
- Markup: each tile is a `<section aria-labelledby>` with an `<h2>` label and a `<p>`
  value, plus a small `<p>` for notes. The hero value is the page's largest text
  (≥ 3rem, system sans, proportional figures). The `<h1>` is "Today".
- The formula line is a plain `<p class="help">` under the tiles. When stats are
  missing: "Add height and birth date in Settings to see a formula estimate."
- Every "Set … in Settings" message is a real link to `/settings`.

Tests (`test_dashboard_routes.py`, real DB, `client` fixture with today fixed at
2026-10-08). Arrange rows with the existing helpers, then assert visible text:

- [ ] Empty DB → the "Log your first weigh-in" message; no stat tiles.
- [ ] The roadmap scenario seeded → "2,550 kcal" in the TDEE tile and "From your logs".
      With a rate of −0.5 → hero "2,000 kcal".
- [ ] Same data in lb/kJ → trend in lb and energy in kJ ("10,650"). The rows are
      unchanged.
- [ ] Rate pointing away → the away message with a Settings link; no ETA date on
      the page.
- [ ] Last weigh-in 5 days ago → "5 days ago".
- [ ] Floor: female, the roadmap data (TDEE 2,550) with a rate of −1.5 (target 900) →
      no "900" anywhere on the page. The hero shows TDEE, the note names 1,200 kcal and
      a suggested rate, and there's no ETA date and no projection in `#chart-data`.
- [ ] Floor boundary in kJ: a female target of exactly 1,200 kcal → the hero shows
      "5,050 kJ" and the floor note (if any) never shows a smaller number than the
      target. In kcal → "1,200 kcal".
- [ ] Weights 80 → 88 kg over 28 days at 2,000 kcal → 200, "doesn't look right", and
      no "-200" or "−200" anywhere on the page.
- [ ] Saved rate −0.00001 with a goal 5 kg away → 200 with "more than 10 years".
      Regression: this crashed before.
- [ ] Calorie-only entries → 200, "Log a weigh-in" hero, and the range-empty sentence
      instead of a chart.
- [ ] A 422 from `POST /entries` still renders the stat tiles.

### 8. Chart (`_chart.html`, `dashboard.js`, vendored Chart.js)

- Download the pinned Chart.js 4.x UMD build and the date-fns adapter bundle into
  `static/vendor/`, each with its LICENSE. Note the versions in a comment at the top of
  `_chart.html`. Load them with `defer`, before `dashboard.js`.
- `_chart.html`:
  - an `<h2 id="chart">Weight</h2>`
  - the range control: a `<div role="group" aria-label="Chart range">` of links with
    `aria-current="true"` on the active one, styled as a segmented control, each at
    least 24px tall. Links keep `date` when it's in the URL.
  - the `<figure>`, the chart box with its fallback `<p>` and `<canvas>`
  - the `<figcaption>`, the `<details>` table, and the JSON `<script>`
- `dashboard.js` (about 100 lines): read the payload and tokens, build four datasets
  as in "The chart", draw, remove the fallback, and redraw on a theme change. Use
  `textContent` for any DOM text, never `innerHTML`.
- Optional: a crosshair hairline plugin (about 15 lines in `afterDraw`). Skip it if the
  tooltip feels clear enough without one.

Tests (route level; the drawing itself is checked by hand, see "Verify by hand"):

- [ ] `/?range=4w` → the JSON in `#chart-data` parses, and its `start` is 28 days before
      today. `/?range=bogus` → 3m and still 200.
- [ ] The active range link has `aria-current`, and the links end in `#chart`.
- [ ] The table view lists exactly the weigh-ins in range, newest first, in display units.
- [ ] The figcaption sentence includes the trend start and end and the goal.
- [ ] A payload containing `</script>` can't happen with numbers, but `tojson` escaping
      is still covered by asserting `<` never appears raw inside the JSON block.
- [ ] The vendored files are served from `/static/vendor/…` with 200.

### 9. Styles (`style.css`)

- Tokens on `:root`: `--surface`, `--text`, `--text-muted`, `--border`,
  `--chart-accent`, `--chart-muted`, `--chart-goal`, `--chart-grid`, `--chart-text`.
  Dark values go under `@media (prefers-color-scheme: dark)` (see the "Colour tokens"
  decision). `body { background: var(--surface); color: var(--text) }`. Existing
  `light-dark()` uses for errors and borders can stay.
- `main` widens to `min(60rem, 100% - 2rem)` on Today through a `{% block main_class %}`.
  Settings keeps its forms at 40rem.
- Hero and form: a two-column grid at ≥ 48rem, stacked below. Tiles:
  `repeat(auto-fit, minmax(12rem, 1fr))` with a 1px `--border` and generous padding,
  no shadows.
- A visible `:focus-visible` outline on links, buttons, and the range control.

### 10. Dev data (`scripts/seed_dev_data.py`)

- `uv run scripts/seed_dev_data.py --data-dir /tmp/tdee-dev [--days 120] [--with-settings]`
- Refuses to run when `--data-dir` resolves to the project's `data/`, and exits
  non-zero with a message.
- Runs the migrations, then writes deterministic entries (`random.Random(42)`): a
  0.4 kg/week loss, ±0.6 kg daily noise, intake around the matching TDEE, about 1 in 10
  days with no weigh-in, about 1 in 15 without calories, and one 5-day gap. That's
  enough to exercise every state.
- `--with-settings` also fills body stats, a goal 6 kg below, and a −0.5 rate.
- Tests (`test_seed.py`, `tmp_path`): refuses the real dir; writes the expected number
  of rows; two runs give identical rows.

### 11. Docs

- `docs/testing.md`: replace the JavaScript row's "deferred" note with this
  milestone's decision (payload in pytest, manual browser checklist, revisit at
  Playwright if the JS grows logic).
- `docs/roadmap.md`: link this plan in the table and tick the status when done.

## Verify by hand

```zsh
./check.sh
uv run scripts/seed_dev_data.py --data-dir /tmp/tdee-dev --with-settings
TDEE_DATA_DIR=/tmp/tdee-dev ./run.sh
```

- [ ] Hero, form, tiles, and chart are readable at 1280px and at 375px with no
      horizontal scroll.
- [ ] 4 weeks / 3 months / All: the chart and table change, the tiles don't, the page
      lands on the chart, and Back returns to the previous range.
- [ ] The tooltip at a weigh-in shows the weigh-in and trend values. The projection is
      dashed and stops at the goal or the ¼ cap.
- [ ] Switch the OS theme with the page open: the chart redraws in dark colours, and
      the dots' rings match the background.
- [ ] Switch to lb and kJ in Settings: every number on Today changes, including the
      chart axis title.
- [ ] Block `/static/vendor/chart.umd.min.js` in devtools: the fallback text shows,
      and the table still works.
- [ ] Keyboard only: Tab reaches the form, the range links, and the table summary,
      with visible focus.
- [ ] Empty data dir: the Today page shows the onboarding message and no broken chart.
- [ ] Long history: seed with `--days 1826`, open `?range=all` at 375px, and sweep the
      pointer across the chart. Every tooltip shows a single date. With years of data
      several days share a pixel, so the hover mode must group by date, not position.
- [ ] Set the rate to −1.5 kg/week: the target disappears, and the floor note suggests
      a rate and says it's a guardrail, not medical advice. Set it to the suggested
      rate: the target appears at or just above the floor, in kcal and in kJ.
- [ ] Edit one weigh-in to an obvious typo (e.g. 8 kg too high): the TDEE tile and hero
      show the "doesn't look right" or "unusually low" message rather than a strange
      number. Fix the typo, and it recovers.
- [ ] Set a goal above your weight with +0.25 kg/week: target above TDEE, "to gain",
      and the projection rises toward the goal.
- [ ] Log today's weight: the page reloads with "Saved", and the trend and last
      weigh-in update.

## Deferred to implementation

- **Including the goal in the y-range** when the goal is far from current weights.
  Check with seeded data. If the trend gets squashed, show the goal only in the legend
  ("Goal 70.0 kg, below chart") and leave it out of the scale.
- **Exact Chart.js interaction options** for "nearest date, all series" (`mode: 'x'`
  vs `'index'` with a `filter`). It's quicker to settle in a browser than on paper.
- **Exact wording** of each state. The table above sets the meaning, and the words can
  be tuned on the page.
- **Stale-weigh-in threshold** of 3 days. Easy to tune once it's used daily.

## Implementation notes

Where the code settled or changed something this plan left open:

- **Chart API:** `build_chart(dashboard, settings, range) -> Chart` slices the trend
  already on `Dashboard` (so it can't be recomputed per range), and
  `chart_payload(chart, unit)` makes the JSON. `target_status` and `goal_status` are
  public, so the floor and goal edge cases are tested with exact inputs.
- **Tooltip interaction:** neither `'x'` nor `'index'` fit. `dashboard.js` registers a
  small `nearestDate` interaction mode: the nearest point to the pointer, then every
  tooltip series **with that same date string** (an earlier version grouped by pixel,
  which mixed 7 dates in a five-year history at 375px). The goal line is left out of
  the tooltip.
- **Chart chrome:** no vertical gridlines (one per day was noise), unrotated x ticks,
  and the legend in reading order (`labels.sort`), not draw order.
- **Goal in the y-range:** kept. With the seeded data (a goal 6.7 kg below), the trend
  still reads clearly.
- **Vendored files:** Chart.js 4.5.1 and chartjs-adapter-date-fns 3.0.0, checked
  against their npm integrity hashes. See `static/vendor/README.md`.
- **Template states:** Jinja can't `match`, so a `state` test checks the dataclass
  name: `{% if goal is state("GoalOnTrack") %}`.

- **Added after review:** "Early estimate" tags on TDEE and the hero while the estimate
  leans on the formula (with "Fully from your logs after N more days"), an "Early
  trend" tag under 10 weigh-ins, a goal-direction line (↓ / ↑ / → with words, steady
  under 0.1 kg/week), and a chart axis that starts at the first weigh-in in range, with
  a week minimum, a little room at both ends, and y-axis headroom.

## Not in this milestone

- A projection range that narrows with more data:
  [issue #1](https://github.com/rxperez12/tdee-calculator/issues/1).

- CSV export (milestone 6).
- Changing the range without a page reload, or zoom and pan.
- A second ETA at your actual rate, and calorie or TDEE-history charts.
- Elapsed-time trend smoothing, confidence intervals, and weight-loss forecasting
  beyond a straight line (deferred in milestone 2).
- Playwright or other browser automation.
- Pagination on History.

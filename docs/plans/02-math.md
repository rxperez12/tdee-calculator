# Milestone 2: Math

**Goal:** All TDEE math lives in one module, `calc.py`, as pure functions over plain
data, with thorough unit tests. No database, web, or clock access. Later milestones
(the dashboard especially) call these functions and only format the results.

**Done when:**

- `calc.py` implements trend weight, weight slope, TDEE estimated from logs,
  Mifflin-St Jeor, the heuristic formula/logs blend, the daily target, and the goal ETA.
- `calc.py` imports only the standard library: nothing from `tdee_calculator` (no `db`,
  `models`, `app`, or even `clock`). A test enforces this.
- Every function has known-answer tests, including missing days, too little data,
  and the sign conventions for losing vs. gaining.
- `uv run pytest` passes.

## Ground rules

- **Canonical units only:** kilograms and kcal. Converting to lb/kJ is milestone 4's
  `units.py`, and happens at the edges (forms and display), never in `calc.py`.
- **Dates are passed in.** Functions take an `as_of: date` (or `today`) argument instead
  of calling `clock.today()`. That keeps them pure and makes tests trivial: no mocking.
- **Plain inputs, plain outputs.** Inputs are a small frozen dataclass (below), not ORM
  `Entry` objects. Outputs are numbers or small frozen dataclasses. The dashboard
  converts `Entry` rows to `DayLog`s in one place.
- **No rounding.** Functions return full-precision floats. Rounding for display (nearest
  5? 25?) is a dashboard decision in milestone 5.
- **Not enough data returns `None`,** not an exception. "Not enough history to estimate
  TDEE from logs" is a normal startup state, and the dashboard shows it as such.
  Invalid arguments (a smoothing factor of 0, a negative window) raise `ValueError`.

## Decisions

These answer the open questions from the requirements that this milestone touches.
Numerical defaults are engineering choices, not validated accuracy thresholds.
Milestone 4 can expose selected parameters as advanced settings later.

| Question | Decision | Why |
| --- | --- | --- |
| Energy density | **7700 kcal/kg**, stored per kg | A fixed approximation for tissue change; water, glycogen, and changing body composition can invalidate it. |
| Trend smoothing factor | **α = 0.1 per weigh-in** | Keep the existing chart behavior intentionally; its half-life is about 6.6 observations, not calendar days. |
| TDEE window | **28 elapsed days**, with both boundary mornings eligible | Up to 29 dated weigh-ins bracket 28 complete intake days. |
| Minimum history | **10 weigh-ins spanning at least 21 elapsed days** | Counts alone do not establish a sustained trend. |
| Calorie coverage | **At least 90% of the bracketed intake days recorded** | Permit a few missing days, filled with the recorded-day mean only for this calculation. For 28 days, require at least 26 recorded days. |
| Blend | **Heuristic ramp over 21–28 elapsed days, scaled by calorie coverage** | A gradual transition after eligibility; not inverse-variance weighting or a confidence probability. |
| Target formula sign | **target = TDEE + rate × density ÷ 7** | See "Correction" below. |
| Which rate the ETA uses | **Whatever rate is passed in** | The function doesn't decide. The dashboard can show an ETA at your target rate, your actual rate, or both. |

### Correction to the requirements' target formula

The requirements say `target = TDEE − (rate per week × energy density ÷ 7)`, with the rate
negative for loss. That gives the wrong sign: losing 0.5 kg/week at TDEE 2,500 gives
`2,500 − (−0.5 × 7,700 ÷ 7) = 3,050`, a surplus. With the sign convention kept
(− for loss, + for gain), the formula must be `TDEE + rate × density ÷ 7`, which gives
`2,500 − 550 = 1,950`. A test pins this down.

## Files

```text
src/tdee_calculator/
  calc.py                       # new: all the math
tests/
  test_calc.py                  # new: known-answer tests
```

One module is enough. Keep it small; explicit interval handling and tests matter more
than meeting a line-count target.

## Tasks

Do them in order. Each function builds on the ones before it.

### 1. Input type

```python
@dataclass(frozen=True)
class DayLog:
    date: date
    weight_kg: float | None
    calories: int | None
```

Functions accept any iterable of `DayLog`s in any order, and sort by date themselves.
Dates are unique (the DB's primary key guarantees it), so `calc.py` doesn't check.
Materialize an iterable once before making multiple passes, so generators work too.

For TDEE inference, `weight_kg` means a morning weigh-in and `calories` means the
completed total for that calendar day. `None` means unknown, not zero; an explicitly
recorded zero is a known value. A day with no row is also unknown. The entry workflow
must communicate that earlier partial totals are not complete records: this input
type cannot detect them. Today's intake is excluded by the morning boundary below.

### 2. Trend weight

```python
@dataclass(frozen=True)
class TrendPoint:
    date: date
    weight_kg: float    # the weigh-in
    trend_kg: float     # the smoothed value after this weigh-in

def trend(logs: Iterable[DayLog], alpha: float = 0.1) -> list[TrendPoint]: ...
```

An exponentially weighted moving average over weigh-in days only:

- The first weigh-in seeds the trend (`trend = weight`).
- Each later weigh-in: `trend = trend + alpha × (weight − trend)`.
- Days without a weight are skipped entirely. They don't update the trend and aren't
  filled in. This is the fix for the old spreadsheet copying values into missing days.
- `alpha` must be in `(0, 1]`, or raise `ValueError`.

Returns one point per weigh-in, which is exactly what the chart needs (dots for
`weight_kg`, a line for `trend_kg`). The current trend weight is `points[-1].trend_kg`.
Return an empty list when there are no weigh-ins. Smoothing is for the chart and the
formula's weight input; the TDEE regression uses raw morning weights, not this lagged
trend. Elapsed-time smoothing is deferred; do not silently change alpha across gaps.

### 3. Weight slope

```python
def weight_slope(logs: Iterable[DayLog]) -> float | None: ...   # kg per day
```

Ordinary least-squares slope of weight against date, using only days with a weight.
Convert dates to numbers as days since the first weigh-in, then use
`statistics.linear_regression(x, y).slope` from the standard library (Python 3.10+).
No numpy needed.

Returns `None` with fewer than two weigh-ins. Multiply by 7 for the "rate per week"
the dashboard shows.

### 4. TDEE estimated from logs

```python
@dataclass(frozen=True)
class LoggedTdee:
    tdee: float
    slope_kg_per_day: float  # raw weight slope, for display only
    avg_intake: float       # recorded-day mean, also used to fill missing days
    start_date: date        # first included morning weigh-in
    end_date: date          # last included morning weigh-in
    span_days: int          # (end_date - start_date).days
    weigh_ins: int
    calorie_days: int       # recorded totals in [start_date, end_date)
    imputed_days: int       # span_days - calorie_days
    calorie_coverage: float # calorie_days / span_days

def logged_tdee(
    logs: Iterable[DayLog],
    as_of: date,
    *,
    window_days: int = 28,
    energy_density: float = 7700,
    min_weigh_ins: int = 10,
    min_span_days: int = 21,
    min_calorie_coverage: float = 0.9,
) -> LoggedTdee | None: ...
```

**Align the interval before calculating anything:**

1. Select raw weigh-ins with `as_of − window_days ≤ date ≤ as_of`. Both boundaries
   are included. Ignore future logs.
2. Let `start_date` and `end_date` be the first and last selected weigh-in dates.
   Return `None` if there are fewer than `min_weigh_ins` weights or their actual span
   is less than `min_span_days`. Ten clustered weigh-ins are not 28 days of history.
3. Use calorie totals for every calendar day in `[start_date, end_date)`. The morning
   weight on day t reflects intake through t−1. Never use calories on `end_date`, or
   after it, even if the total is present. If today's weight is missing, the interval
   ends at the last actual weigh-in, not at `as_of`.
4. Count recorded calorie days over this actual interval. Require
   `calorie_days >= math.ceil(min_calorie_coverage * span_days)`; otherwise return
   `None`. Absent rows and rows with `calories=None` both count as missing.
5. Compute the mean of recorded totals in that interval. Fill missing intake days
   with this mean in memory only. Do not modify inputs or persist inferred entries.

**Fit the cumulative energy balance:**

For each selected weigh-in on date t, let `x` be elapsed days since `start_date` and
`C(t)` the cumulative intake from `start_date` through t−1, including any fills.
`C(start_date) = 0`. Regress these adjusted weights against x:

```text
adjusted_weight(t) = raw_weight(t) − C(t) / energy_density
tdee = −energy_density × linear_regression(x, adjusted_weight).slope
```

Under locally constant TDEE and energy density, the model is
`weight(t) = intercept + C(t) / density − TDEE × x / density + error(t)`.
This accounts for variable intake and irregular weigh-in dates. Do not replace it
with `mean_intake − density × raw_weight_slope`: those two summaries weight time
differently and can disagree even with perfect data. Calculate the raw weight slope
separately for the result's display field; it does not drive the TDEE estimate.

Validate parameters: positive finite energy density, positive integer window and
minimum span, `min_span_days <= window_days`, integer `min_weigh_ins >= 2`, and finite
coverage in `(0, 1]`; invalid arguments raise `ValueError`.

**What the result means:**

- Use the label **"TDEE estimated from logs"**, not "measured TDEE". It describes the
  fitted interval, not a direct measurement of today's expenditure. Expose its dates
  so the dashboard can say "data through [end date]" when the last weight is older.
- Show coverage honestly, for example "26 recorded days, 2 estimated." Mean-filling
  assumes missing days resemble recorded days. A 90% threshold limits missingness,
  not error; omitted high-intake days can still bias the estimate.
- Water shifts, inaccurate intake, changing expenditure, and the fixed density remain
  sources of error. Initial diet transitions are especially susceptible to water
  changes. A straight fitted line does not establish accurate TDEE.
- Do not output a TDEE confidence interval or use ordinary slope standard error to
  weight the blend in v1. It omits model and logging error; cumulative intake errors
  and water fluctuations can also produce correlated residuals. A gradual water
  shift can give a wrong estimate with essentially zero regression standard error.
- Stable additive underlogging can cancel when an inferred target is followed using
  the same logging convention. That cancellation is incomplete when blended with a
  formula estimating actual expenditure, and does not hold for changing logging bias.

### 5. Formula estimate

```python
class Sex(StrEnum):
    MALE = "male"
    FEMALE = "female"

class ActivityLevel(Enum):
    SEDENTARY = 1.2
    LIGHT = 1.375
    MODERATE = 1.55
    VERY = 1.725
    EXTRA = 1.9

def age_on(birth_date: date, on: date) -> int: ...

def mifflin_st_jeor_ree(sex: Sex, weight_kg: float, height_cm: float, age: int) -> float: ...
    # male:   10·kg + 6.25·cm − 5·age + 5
    # female: 10·kg + 6.25·cm − 5·age − 161

def formula_tdee(ree: float, activity: ActivityLevel) -> float: ...
```

- `age_on` counts whole years, so the day before a birthday is still the younger age.
- Mifflin-St Jeor predicts resting energy expenditure (REE). Multiplication by an
  activity factor is a separate approximation for TDEE. Keep this familiar starting
  estimate for v1; switching to the 2023 DRI equations is deferred.
- The weight to pass in is the current trend weight, not the latest raw weigh-in, so a
  single heavy morning doesn't move the estimate.
- `StrEnum` (3.11+) values compare equal to plain strings, which is convenient when
  milestone 4 stores `sex` in the settings table as text.

### 6. Blended estimate

```python
@dataclass(frozen=True)
class TdeeEstimate:
    tdee: float
    method: Literal["formula", "blend", "logs"]
    logs_weight: float          # 0.0 to 1.0; mixing share, not confidence
    logged: LoggedTdee | None
    formula: float | None

def estimate_tdee(
    logged: LoggedTdee | None,
    formula: float | None,
    *,
    blend_start_days: int = 21,
    blend_full_days: int = 28,
) -> TdeeEstimate | None: ...
```

- With both estimates, use this **explicitly heuristic** transition:
  `ramp = max(0, min(1, (logged.span_days - blend_start_days) / (blend_full_days - blend_start_days)))`;
  `w = ramp × logged.calorie_coverage`.
- `tdee = w × logged.tdee + (1 − w) × formula`.
- `method` is `"logs"` when `w == 1`, `"blend"` when `0 < w < 1`, and `"formula"`
  when `w == 0`. Retain the eligible logged estimate in the result even at zero share.
- No eligible logged estimate: use the formula with `logs_weight=0`. No formula:
  use an eligible logged estimate alone with `logs_weight=1` and `method="logs"`.
  Neither available: return `None`. Absence of a formula never bypasses eligibility.
- Require integer parameters with `0 <= blend_start_days < blend_full_days`;
  otherwise raise `ValueError`. These control the transition, independently of the
  eligibility window; changing advanced settings must preserve a reachable transition
  if the user intends logs to take over fully.

With the defaults and full coverage, logs contribute 0% at 21 elapsed days, 3/7 at
24 days, and 100% at 28 days. With 26 of 28 intake days recorded, their final share is
26/28. Missing weigh-ins do not directly reduce this share once the count and span
requirements pass. Losing eligibility can still cause a jump back to the formula;
the transition is not a promise of day-to-day continuity.

The share is a product rule for gradual adoption, not a probability, a confidence
score, or a claim that logs are accurate at 100%. Do not infer a statistical interval
from it. Inverse-variance blending and an assumed formula sigma of 250 kcal/day are
deferred until total uncertainty can be justified and tested.

Taking the two estimates as arguments (instead of the raw inputs) keeps this function
tiny and lets the dashboard show each piece separately.

### 7. Daily target

```python
def daily_target(tdee: float, rate_kg_per_week: float, energy_density: float = 7700) -> float: ...
    # tdee + rate_kg_per_week × energy_density / 7
```

Negative rate for loss, positive for gain, zero for maintenance.
This is a starting target under the fixed-density approximation, recalculated as the
TDEE estimate changes. It does not guarantee a sustained rate at an unchanged intake.

### 8. Goal ETA

```python
@dataclass(frozen=True)
class GoalEta:
    remaining_kg: float     # goal − current; negative means weight to lose
    weeks: float
    date: date

def goal_eta(
    current_kg: float,
    goal_kg: float,
    rate_kg_per_week: float,
    today: date,
) -> GoalEta | None: ...
```

- Already at the goal (within a small tolerance, say 0.05 kg): `weeks = 0`, `date = today`.
- Rate of zero, or a rate heading away from the goal: `None`. There's no date to show.
- Otherwise `weeks = remaining / rate` and `date = today + timedelta(weeks=weeks)`,
  rounded to whole days.

This is a constant-rate projection. Milestone 5 owns the label "if this rate
continues"; this milestone does not add a physiological weight-loss simulator.

### 9. Tests (`test_calc.py`)

Use synthetic data where the answer is known exactly. A small helper builds logs
from a start date, a daily weight function, and a daily calorie value, with an option
to drop specific days. Compare floats with `pytest.approx`, and use
`@pytest.mark.parametrize` for the formula and sign cases.
For variable-intake fixtures, generate morning weights independently from a known
TDEE: `weight[t+1] = weight[t] + (intake[t] - true_tdee) / density`. Keep 29 boundary
mornings for a 28-day intake interval. Remove weights and calorie totals independently.

Purity:

- [ ] `calc.py` has no imports from `tdee_calculator` (read the file's source with
      `inspect.getsource` or `ast` and check). This keeps the "pure module" rule
      from eroding.

Trend:

- [ ] Constant weights give a constant trend.
- [ ] A step from 80 to 81 kg with α = 0.1 gives 80.1, 80.19, 80.271, ...
- [ ] Logs with missing days produce the same trend as the same weigh-ins without them.
- [ ] `alpha` of 0 or above 1 raises `ValueError`.

Slope:

- [ ] Weight falling exactly 0.1 kg/day gives `−0.1`.
- [ ] Dropping random days from a perfect line doesn't change the slope.
- [ ] Fewer than two weigh-ins gives `None`.

TDEE estimated from logs:

- [ ] **Known answer:** 28 elapsed days at 2,000 kcal, with boundary morning weights
      falling exactly 0.5 kg/week, gives
      `2000 + (0.5 / 7) × 7700 = 2,550`.
- [ ] Gaining at the same rate gives `1,450`. Flat weight with constant intake gives
      that intake. Do not expect arithmetic mean intake for arbitrary variable-intake,
      flat-weight fixtures, which do not follow the constant-TDEE model.
- [ ] **Variable intake:** true TDEE 2,500, first 10 days at 2,000, next 7 at 4,000,
      last 11 at 2,000; cumulative fit returns 2,500. The old mean-minus-slope method
      returns about 2,290 even with aligned boundaries. Repeat with irregularly
      spaced weights (at least 10, preserving boundary dates) and retain the answer.
- [ ] The morning exactly `window_days` before `as_of` is included; earlier weights
      and calories do not contribute. Future logs do not contribute either.
- [ ] Changing calories on the final weigh-in date from missing to partial to a large
      completed total does not change the estimate, intake average, or coverage.
- [ ] No weight today: end at the last actual weigh-in, ignore intake on and after
      that date, and report the actual dates and span. Ignore calories preceding the
      first selected weight too, even when they fall inside the nominal window.
- [ ] With other requirements satisfied, 9 weigh-ins returns `None`; 10 spread over
      21 elapsed days qualifies. Ten clustered within 9 days and a 20-day span fail.
- [ ] Over 28 elapsed days, 25 recorded calorie days fails and 26 qualifies. Over
      21 elapsed days, 18 fails and 19 qualifies. Use actual span as the denominator.
- [ ] Missing rows and `calories=None` are filled identically. Constant-intake gaps
      preserve the known answer; counts, coverage, and imputed days are correct.
      Explicit zero totals count as recorded, and source inputs remain unchanged.
- [ ] **Missing high-intake days:** remove two high-intake totals from an otherwise
      complete 28-day fixture. It still qualifies, but mean-filling underestimates
      TDEE; restoring the true totals recovers the known TDEE. Compare plausible low
      and high fills as a sensitivity check, without adding a product feature or
      claiming coverage bounds the error.
- [ ] **Water drift:** add a linear 0.5 kg water loss across 28 days to perfect data
      with true TDEE 2,500. Expect 2,637.5 despite a perfectly straight adjusted fit.
      The result must not claim zero uncertainty. Also exercise a temporary weight
      spike at different positions in the interval; do not assume OLS removes it.
- [ ] **Logging bias:** subtract a constant 300 kcal/day from complete intake logs
      without changing weights; the inferred TDEE shifts down by 300.
- [ ] Empty data, all missing weights, and all missing calories return `None`.
      Invalid parameters raise `ValueError`. Unsorted lists and one-shot generators
      give the same results as sorted inputs.

Formula:

- [ ] Male, 80 kg, 180 cm, 30 years: REE `1,780`. Female, 60 kg, 165 cm, 25 years: `1,345.25`.
- [ ] `formula_tdee` with each activity level multiplies correctly.
- [ ] `age_on` the day before, on, and after a birthday; and a Feb 29 birth date.

Blend:

- [ ] Logged estimate `None` gives `method="formula"` and share 0. With both inputs
      and full coverage, spans of 21, 24, and 28 days give shares 0, 3/7, and 1, with
      methods `"formula"`, `"blend"`, and `"logs"`. Check the weighted TDEE too.
- [ ] At 28 days, 26 recorded intake days gives share 26/28 and method `"blend"`.
      Changing the number of eligible weigh-ins alone does not change the share.
- [ ] Retain logged metadata even at share 0. Without a formula, use eligible logs
      alone with share 1; neither input gives `None`.
- [ ] Clamp the ramp outside its bounds; reject invalid transition parameters.
      Losing log eligibility falls back to the formula, with no stale logged value.
- [ ] A noiseless but water-biased estimate gets the same share as a noisy estimate
      with identical span and coverage; no residual-based certainty is inferred.

Target and ETA:

- [ ] Losing 0.5 kg/week at TDEE 2,500 gives `1,950` (the sign-convention test).
      Gaining 0.25 kg/week gives `2,775`. Zero gives the TDEE.
- [ ] 85 → 80 kg at −0.5 kg/week: 10 weeks, `today + 70 days`.
- [ ] Moving away from the goal, or a zero rate, gives `None`.
- [ ] Within the tolerance of the goal gives 0 weeks.

## Verify by hand

```zsh
uv run pytest tests/test_calc.py -v
uv run python -c "from tdee_calculator import calc; print(calc.mifflin_st_jeor_ree(calc.Sex.MALE, 80, 180, 30))"
```

## Not in this milestone

- Unit conversion (`units.py`) and reading settings: milestone 4.
- Converting `Entry` rows to `DayLog`s, rounding, and the chart's projection line:
  milestone 5. Its notes show coverage, estimated intake days, the last weigh-in date,
  and the conditional ETA; they do not present mixing shares as confidence.
- Katch-McArdle and body fat: a reach goal.
- 2023 DRI starting equations, elapsed-time chart smoothing, statistical TDEE confidence
  intervals, inverse-variance blending, and dynamic physiological weight forecasting.
- Property-based tests (`hypothesis`). A nice stretch, not required.

## Evidence and limits

- [Mifflin et al. (1990)](https://pubmed.ncbi.nlm.nih.gov/2305711/): source for the
  resting-expenditure equation; the activity multipliers are a separate approximation.
- [Hall and Chow (2011)](https://pmc.ncbi.nlm.nih.gov/articles/PMC3127505/): illustrates
  the duration and noise issues in inferring energy-intake changes from weight. It
  does not validate this app's cumulative estimator or its eligibility thresholds.
- [Hall et al. (2011)](https://www.nccor.org/annualreport2013/downloads/Obesity-3.pdf):
  body composition, fluid changes, and changing expenditure limit fixed-density and
  constant-rate predictions.
- [NIST regression guidance](https://www.itl.nist.gov/div898/handbook/pmd/section4/pmd444.htm):
  dependent errors undermine ordinary regression uncertainty estimates.

The cumulative fit follows from the stated energy-balance model. The coverage rule,
mean imputation, minimum history, and blend ramp are explicit v1 heuristics. Synthetic
tests verify arithmetic and expose limitations; they do not establish real-world
physiological accuracy.

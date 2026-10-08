# Milestone 4: Settings

**Goal:** A settings page stores units, body stats, the goal, and the advanced
calculation values. Everything is still stored in kg and kcal. `units.py` converts at
the edges, so after switching to lb or kJ the entry form, the recent list, and the
settings page all read and write in your units, and the database doesn't change.

**Done when:**

- `/settings` shows and saves units, body stats (sex, height, birth date, activity
  level), the goal (goal weight, rate per week), and advanced values (TDEE window,
  energy density). Saved values survive a restart.
- Switching weight to lb shows weights, the goal, and the rate in lb everywhere, and
  height in feet and inches. Switching energy to kJ shows calories and energy density
  in kJ. Stored rows are unchanged by the switch.
- Entering a weight in lb stores the equivalent kg. Re-saving a form without touching a
  converted value leaves the stored value exactly as it was (see "Round-trip drift").
- Invalid settings re-render the form with errors and a 422, and nothing is saved.
- Body stats and the goal can be left blank or cleared. Blank advanced values
  fall back to their defaults.
- `./check.sh` passes. No migration: the `settings` key/value table from milestone 1
  is enough.

## Decisions

| Question | Decision | Why |
| --- | --- | --- |
| Settings storage | **Keep the key/value table**, with a typed `Settings` dataclass in front of it | No migration, and "not set yet" is simply a missing row. Typing lives in one module (`settings.py`), so the rest of the app never sees strings. Milestone 1 left this open; switching to typed columns later is a single migration. |
| Units offered | Weight **kg / lb**, energy **kcal / kJ** | As in the requirements. |
| Height unit | **Follows the weight unit:** cm with kg, feet + inches with lb | Anyone using lb thinks of height in feet and inches. A separate height setting isn't worth it. |
| Conversion constants | **1 lb = 0.45359237 kg** (exact by definition), **1 kcal = 4.184 kJ**, **1 in = 2.54 cm** | 4.184 is the thermochemical calorie, which food labels use. |
| Display precision | Weight and goal **0.1**; rate **0.01 per week**; energy and energy density **whole numbers**; height **whole cm**, or feet + **0.5 in** | Enough resolution for each value without noise. |
| Validation | **Ranges are defined in kg/kcal** and checked after conversion. Error messages show them in your units. | One set of limits, so lb users can't get around them. |
| Changing units vs. values | **Units get their own small form** at the top of the settings page | With one combined form, "goal weight 80" submitted along with a switch from kg to lb is ambiguous: 80 kg or 80 lb? A separate form makes each submission mean one thing. |
| Rate sign | **Signed number, − for loss**, with help text and a placeholder of `-0.5` | Matches `calc.py` and the requirements. Whether the rate points toward the goal is something the dashboard (milestone 5) can check, since it knows your current weight. |
| Advanced: window | **Integer, 14–56 days**, default 28 | `calc.logged_tdee` requires `min_span_days ≤ window_days`. Milestone 5 derives `min_span_days = ceil(window × 3/4)` (21 for 28) and passes `blend_start = min_span_days`, `blend_full = window`. That keeps any allowed window valid. |
| Advanced: energy density | **4,000–9,500 kcal/kg**, default 7,700 | Covers the common 3,500 kcal/lb (≈ 7,716 kcal/kg) and lower body-composition-aware values. Shown in your units, e.g. kcal/lb. |
| Smoothing factor, eligibility thresholds | **Not exposed** | The requirements list only the window and energy density. The others stay as `calc.py` defaults. |
| Settings form concurrency | **No version check** | One person, rarely in two tabs, and a lost settings edit is easy to see and redo. The entry form needs the check because daily logs are easy to miss. |

### Round-trip drift

Converting a stored value for display rounds it, and a later save converts the rounded
text back. For example, 81.7 kg is shown as 180.1 lb, and saving 180.1 lb gives
81.692 kg. The value drifts without anyone changing it. The same happens with 80.25 kg
shown as 80.2, and with 7,700 kcal/kg shown as 3,493 kcal/lb, which saves back as
7,700.75.

**Rule:** if a submitted field's text equals what the server would render for the
stored value, keep the stored value. Both forms follow this rule:

- Entry form: compare the submitted weight and calories with the formatted values of
  the row being saved over.
- Settings form: compare each field with the formatted current settings.

Only an edited field is converted and saved. This needs the prefilled value and the
comparison to use the same formatting function, so `units.py` owns formatting too.

## Files

```text
src/tdee_calculator/
  units.py                      # new: unit enums, conversions, display formatting (pure)
  settings.py                   # new: Settings dataclass, load_settings / save_settings
  settings_form.py              # new: settings form strings <-> Settings (pure)
  entry_form.py                 # edit: parse in the user's units, keep unchanged values
  app.py                        # edit: settings routes, unit-aware entry routes, filters
  templates/
    base.html                   # edit: nav (Log | Settings)
    index.html                  # edit: unit labels, converted values and limits
    settings.html               # new
  static/
    style.css                   # edit: nav, fieldsets
tests/
  test_units.py                 # new
  test_settings.py              # new
  test_settings_form.py         # new
  test_entry_form.py            # edit
  test_app.py                   # edit: entry routes in lb / kJ
  test_settings_routes.py       # new
```

## Tasks

Do them in order. Each one leaves `./check.sh` passing.

### 1. Units (`units.py`)

Pure, like `calc.py`: standard library only, no app imports. Constants are named, and
nothing else in the app writes `0.4536` or `4.184`.

```python
class WeightUnit(StrEnum):
    KG = "kg"
    LB = "lb"

class EnergyUnit(StrEnum):
    KCAL = "kcal"
    KJ = "kJ"

KG_PER_LB = 0.45359237
KJ_PER_KCAL = 4.184
CM_PER_INCH = 2.54

def weight_to_kg(value: float, unit: WeightUnit) -> float: ...
def weight_from_kg(kg: float, unit: WeightUnit) -> float: ...
def energy_to_kcal(value: float, unit: EnergyUnit) -> float: ...
def energy_from_kcal(kcal: float, unit: EnergyUnit) -> float: ...
def density_to_kcal_per_kg(value: float, weight: WeightUnit, energy: EnergyUnit) -> float: ...
def density_from_kcal_per_kg(kcal_per_kg: float, weight: WeightUnit, energy: EnergyUnit) -> float: ...
def feet_inches_to_cm(feet: int, inches: float) -> float: ...
def cm_to_feet_inches(cm: float) -> tuple[int, float]: ...   # inches rounded to 0.5

def format_weight(kg: float, unit: WeightUnit) -> str: ...   # "180.1"
def format_rate(kg_per_week: float, unit: WeightUnit) -> str: ...   # "-1.10"
def format_energy(kcal: float, unit: EnergyUnit) -> str: ...  # "8368"
def format_density(kcal_per_kg: float, weight: WeightUnit, energy: EnergyUnit) -> str: ...
```

- Energy density is energy per weight, so converting it uses **both** units. Per lb is
  *smaller* than per kg (multiply kcal/kg by `KG_PER_LB`). Get the direction from the
  test, not by intuition.
- `cm_to_feet_inches` can round up to 12 inches: 182.8 cm is 5 ft 11.97 in, which
  rounds to 5 ft 12.0 in. Carry it into the feet (6 ft 0 in).
- The format functions don't include the unit label. Templates print the label next
  to the number, and form fields need the bare number anyway.
- Format with `f"{value:.1f}"`, and so on, without thousands separators: the strings
  go into `<input type="number">`, which rejects `8,368`.

### 2. Settings model (`settings.py`)

```python
@dataclass(frozen=True)
class Settings:
    weight_unit: WeightUnit = WeightUnit.KG
    energy_unit: EnergyUnit = EnergyUnit.KCAL
    sex: Sex | None = None
    height_cm: float | None = None
    birth_date: Date | None = None
    activity: ActivityLevel | None = None
    goal_weight_kg: float | None = None
    rate_kg_per_week: float | None = None
    tdee_window_days: int = 28
    energy_density: float = 7700          # kcal/kg

def load_settings(session: Session) -> Settings: ...
def save_settings(session: Session, settings: Settings) -> None: ...
```

- **Keys are the field names.** Storage format: enums by `.value` (`"lb"`, `"female"`),
  except `ActivityLevel`, by `.name` (`"MODERATE"`), because its values are floats.
  Store numbers with `repr()`, so a float round-trips exactly. Dates use `isoformat()`.
- **`load_settings`:** one `select(Setting)` and a dict of the rows, then one small
  typed helper per field:

  ```python
  def _read[T](rows: dict[str, str], key: str, parse: Callable[[str], T], default: T) -> T: ...
  ```

  `_read(rows, "sex", Sex, None)` and `_read(rows, "tdee_window_days", int, 28)` keep
  mypy happy without `Any`. (`def f[T](...)` is 3.12's generic syntax, like
  `function f<T>(...)` in TypeScript.)
- **A stored value that doesn't parse** (only possible by editing the DB by hand) falls
  back to the default instead of crashing every page. A test pins this down.
- **`save_settings`:** for every field, `None` deletes the row and anything else
  upserts it (`session.get(Setting, key)`, then set or add, as in `entries.py`). One
  `commit()` at the end, so a save is all or nothing.
- `Settings()` with no arguments is "nothing set yet". The defaults live in the
  dataclass, so `calc.py`'s defaults and these must match. A test compares them with
  `inspect.signature(calc.logged_tdee).parameters`, so changing one without the other fails.

### 3. Settings form (`settings_form.py`)

Pure, like `entry_form.py`. It converts in both directions, so the page and the parser
share one formatting path:

```python
SettingsValues = dict[str, str]     # form field name -> text

def settings_to_form(settings: Settings) -> SettingsValues: ...
def parse_settings_form(
    form: SettingsValues, current: Settings, today: Date
) -> Settings | SettingsFormErrors: ...
def parse_units_form(form: SettingsValues, current: Settings) -> Settings | SettingsFormErrors: ...
```

Form fields (in the user's current units): `sex`, `height_cm` **or** `height_ft` +
`height_in`, `birth_date`, `activity`, `goal_weight`, `rate_per_week`,
`tdee_window_days`, `energy_density`.

- **Round-trip rule first:** compute `settings_to_form(current)`. If a submitted field
  equals the rendered value, keep `current`'s value for it. Otherwise parse and convert.
  Height is one value split across two inputs, so compare both inputs together.
- **Blank:** body stats and the goal become `None`. Advanced fields become the default.
  `dataclasses.replace(current, **changes)` builds the result.
- **Checks, all in kg/kcal after conversion; collect every error, as in `entry_form`:**

  | Field | Rule |
  | --- | --- |
  | `sex`, `activity` | One of the enum options |
  | Height | 100–250 cm. In ft + in: feet 3–8 and inches 0 to <12, then the cm range. |
  | `birth_date` | Valid ISO date; age on `today` between 15 and 100 (use `calc.age_on`) |
  | `goal_weight` | 20–400 kg (reuse `entry_form`'s constants) |
  | `rate_per_week` | −1.5 to +1.0 kg/week |
  | `tdee_window_days` | Whole number, 14–56 |
  | `energy_density` | 4,000–9,500 kcal/kg |

- `parse_units_form` accepts only the two unit fields. It changes no other value,
  because those are stored in kg/kcal and simply render differently next time.

### 4. Entry form in the user's units (`entry_form.py`)

```python
def parse_entry_form(
    date_text: str, weight_text: str, calories_text: str, today: Date,
    weight_unit: WeightUnit, energy_unit: EnergyUnit,
    current: Entry | None,    # the row being saved over, for the round-trip rule
) -> EntryInput | EntryFormErrors: ...
```

- Parse the number, convert to kg/kcal, then range-check against the existing
  `MIN_WEIGHT_KG`-style constants. Messages convert those limits: "between 44.1 and
  881.8 lb".
- Calories in kJ: require a whole number of kJ, convert, and round to whole kcal. kcal
  stays an `int` in the DB. Rounding can't break the round trip: kJ is the finer unit,
  so every kcal value has its own kJ display.
- **Round-trip rule:** if `current` has a weight and `weight_text ==
  format_weight(current.weight_kg, unit)`, keep `current.weight_kg`. Same for calories.
  Taking `current` keeps the module pure. The route already loads the row for its
  guards and passes it in.
- Keep the route's order of checks: parse errors (422), then the overwrite and version
  guards (409), then save. Load `current` before parsing; that's the same
  `get_entry` call the guards use.

### 5. Routes and templates (`app.py`)

- **Load settings per request** from a dependency:
  `SettingsDependency = Annotated[Settings, Depends(current_settings)]`, where
  `current_settings(session: SessionDependency) -> Settings` calls `load_settings`.
  FastAPI creates one session per request even when two dependencies ask for it.
  The table has ten rows at most, so no caching.
- **Jinja filters** so templates convert without logic: register
  `templates.env.filters["weight"] = format_weight` and so on. Then
  `{{ entry.weight_kg | weight(settings.weight_unit) }}`. Pass `settings` in every
  template context.
- **Entry page:** labels show the unit ("Weight (lb)"). The form prefill uses
  `format_weight` / `format_energy`, not `str(entry.weight_kg)`, so the round-trip
  comparison sees the same text. The HTML `min` / `max` attributes use the converted
  limits.
- **`GET /settings`:** two forms (units, then everything else) and a `?saved=1` notice.
- **`POST /settings/units`** and **`POST /settings`:** parse; on errors re-render
  `settings.html` with a 422 and the submitted text; otherwise `save_settings` and a 303
  to `/settings?saved=1`. The cross-origin middleware from milestone 3 already covers
  both, and a test proves it.
- `settings.html`:
  - Fieldsets for "Body", "Goal", and "Advanced".
  - `<select>` for sex and activity, with a blank "Not set" option. Activity labels such
    as "Moderate (exercise 3–5 days a week)" live in a dict in `settings_form.py`.
  - Height shows one cm input or two ft/in inputs, depending on the weight unit.
  - Advanced inputs show the default as `placeholder`, with a note that blank means default.
  - A help line under the rate field: "Negative to lose, positive to gain. 0 to maintain."
- `base.html`: a small nav with "Log" (`/`) and "Settings" (`/settings`).

`app.py` reaches about 300 lines with these routes. Splitting it into routers is worth
doing once the dashboard arrives. Leave it for milestone 5 so this diff stays about
settings.

### 6. Tests

`test_units.py` (pure; expected answers worked out by hand or from the definitions):

- [ ] 1 lb → 0.45359237 kg; 100 kg → 220.462 lb (`abs=1e-3`, as published).
- [ ] 2,000 kcal → 8,368 kJ exactly; 8,368 kJ → 2,000 kcal.
- [ ] 3,500 kcal/lb → 7,716.17 kcal/kg (`abs=0.01`); 7,700 kcal/kg → 3,492.66 kcal/lb.
      kJ/lb and kJ/kg combinations each give one known answer.
- [ ] 5 ft 10 in → 177.8 cm; 177.8 cm → (5, 10.0); 182.8 cm → (6, 0.0), not (5, 12.0).
- [ ] Every `to` / `from` pair round-trips within `1e-9`.
- [ ] Formatting: `format_weight(81.7, LB) == "180.1"`; no thousands separators;
      negative rate keeps its sign.

`test_settings.py` (real SQLite in `tmp_path`):

- [ ] Empty table → `Settings()`.
- [ ] Every field set → save → load in a fresh session gives an equal `Settings`.
      Include floats such as `81.64662660` that need `repr` to round-trip.
- [ ] Setting a field back to `None` deletes its row (count the rows).
- [ ] A hand-corrupted value (insert `tdee_window_days = "abc"` with SQL) loads as the default.
- [ ] The dataclass defaults match `calc.logged_tdee`'s defaults.

`test_settings_form.py` (pure):

- [ ] Valid metric and imperial submissions produce the expected kg/cm/kcal values.
- [ ] Re-submitting `settings_to_form(s)` unchanged gives exactly `s`, for a metric
      and an imperial `s` whose values don't fall on display boundaries (e.g. 81.7 kg).
- [ ] Changing only the goal weight changes only `goal_weight_kg`.
- [ ] Blank body stats → `None`; blank advanced → defaults.
- [ ] Each range edge from the table: accepted on the bound, rejected just past it, in
      both unit systems where the field converts. Messages show limits in the user's units.
- [ ] Feet/inches: 12 inches, negative feet, and only one of the two inputs filled are rejected.
- [ ] Birth date: age 15 accepted, 14 rejected, and a future date rejected.
- [ ] `parse_units_form` changes the units and nothing else; an unknown unit is an error.

`test_entry_form.py` additions:

- [ ] 180.1 lb parses to `weight_to_kg(180.1, LB)`; 8,368 kJ parses to 2,000 kcal.
- [ ] Range messages in lb; 44 lb rejected, as it is under 20 kg.
- [ ] Unchanged weight text with a `current` row keeps the stored kg exactly; changed text converts.

`test_app.py` / `test_settings_routes.py` (real database, `client` fixture):

- [ ] `GET /settings` with nothing saved shows blank stats and the advanced placeholders.
- [ ] `POST /settings` → 303, and the stored rows hold kg/kcal values: a 180 lb goal is
      stored as 81.64662... kg.
- [ ] Invalid `POST /settings` → 422, the errors and the typed text are on the page,
      and the settings rows are unchanged.
- [ ] Switching units → the entry list, entry form labels, and settings page show lb/kJ,
      and the `entries` rows are byte-for-byte the same as before the switch.
- [ ] In lb: logging 180.1 stores kg; re-saving that row with only calories changed
      leaves `weight_kg` exactly as stored.
- [ ] A cross-site `POST /settings` and `POST /settings/units` → 403, nothing saved.

## Verify by hand

```zsh
./check.sh
TDEE_DATA_DIR=$(mktemp -d) ./run.sh
# log 80.0 kg; Settings: switch to lb -> the list shows 176.4; switch back -> 80.0
# set goal 165 lb, rate -1; save; reload: same values; sqlite3 shows kg values
# Settings in lb shows height as ft/in; enter 5 ft 10 -> cm row 177.8
# blank the window, save -> 28 again; enter 13 -> error, nothing saved
```

## Not in this milestone

- Using these settings in calculations, the target, or the ETA (milestone 5).
- Checking that the rate points toward the goal (milestone 5, which knows the current weight).
- Exposing the smoothing factor or eligibility thresholds.
- A version check on the settings form.
- Splitting `app.py` into routers.

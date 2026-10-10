# P2.1: Body measurements and body-fat estimates

**Goal:** Log tape measurements on their own dated sessions, see a documented
body-fat estimate from them, and keep external results (DEXA, scales, scans) as a
separate history. Raw measurements are the record; estimates are derived from them
and always shown with the date of the measurements they come from.

## Delivery

This milestone ships as three PRs under this one plan. Each PR is usable on its own
and has its own "done when". The decisions below apply to all three.

| PR | Contents | Status |
| --- | --- | --- |
| **A. Tape measurements + Navy estimate** | Measurement sessions with repeated readings, instructions, the Navy estimate, history | Implemented; locally verified |
| **B. External body-fat results** | Separate table, form, and history for results recorded elsewhere, with their source | Outline only; detail before starting |
| **C. Context and polish** | Waist-to-height ratio, BMI (if kept), an estimate chart, seed data | Outline only; optional |

B does not depend on A and may ship in either order. C is optional: if A and B cover
what's needed, C moves to the later wishlist and P2.1 is done.

## Decisions

| Question | Decision | Why |
| --- | --- | --- |
| Equation | **Traditional Navy (Hodgdon–Beckett), inch form**: male `86.010·log10(abdomen − neck) − 70.041·log10(height) + 36.76`; female `163.205·log10(waist + hip − neck) − 97.684·log10(height) − 78.387` | This is exactly what the original spreadsheet (`TDEE variant with bf Dec 22.xlsx`, column R) computes. A "metric" Navy form (`495 / (1.0324 − …) − 450`) exists but gives slightly different numbers, so it is not used. `calc.py` converts cm to inches internally. |
| Measurement sites | **Neck, abdomen at the navel, waist at the narrowest point, hips at the widest point**, each stored under its own key | The male equation uses the abdomen at the navel; the female equation uses the narrowest waist. They are different places on the body, so they get different keys rather than one ambiguous "waist". |
| Which sites are required | **None individually; a session needs at least one reading** | Logging a waist alone is useful for tracking. The estimate appears only when the sites its equation needs are present. |
| Repeated readings | **Up to 3 readings per site**; the session value is their mean | This is the app's own approach, not the Navy's procedure. The 2021 Navy guide takes two readings, a third only when they disagree, uses the two closest, and rounds to 0.5 in. Keeping every raw reading and averaging them is simpler to explain and loses nothing, and the equation itself is unchanged. Three fixed input slots need no JavaScript. |
| Sessions per date | **One**, upserted like daily entries, with the same overwrite guard and version check | Matches the entry form, so there's one mental model. A second session the same day adds nothing. |
| Length unit | **Follows the weight unit**: cm with kg, inches with lb | Same rule as height in milestone 4. No new setting. The stale-units guard compares only `weight_unit`: the existing `web.units_match` also requires `energy_unit`, which this form doesn't send, so it can't be reused unchanged. |
| Storage | **cm floats**, readings stored as typed (after conversion) | Store canonical units, convert at the boundary. The protocol's 0.5 in rounding is not applied to stored values. |
| Display precision | Circumferences **0.1 cm / 0.1 in**; body fat **whole percent** | Whole percent matches the spreadsheet and the Navy's own reporting, and the method's error (several percentage points) makes decimals false precision. |
| Stored estimate vs. computed | **Computed on read** from the readings plus current sex and height; nothing derived is stored | The raw readings are the record. Correcting your height corrects every past estimate. The cost: changing sex or height in Settings changes historical estimates. That's accepted for a single adult user, and noted on the page. |
| Missing sex or height | **Readings are saved and shown; the estimate cell says what's missing** and links to Settings | Measurements are worth keeping even before Settings is complete. |
| Out-of-range results | **Show "outside the equation's range"** when the log argument is ≤ 0 or the result is below 2% or above 60% | Prevents a log-domain error and absurd numbers from typos that pass the per-site range check. |
| Valid ranges per reading | Neck **20–80 cm**; abdomen and waist **40–250 cm**; hips **50–250 cm** | Catches typos (e.g. 340 for 34.0) and the wrong unit, without rejecting real values. Displayed limits follow the milestone 4 "limits and rounding" rule. |
| Where it lives | **New `/measurements` page** and nav item | Separate from the daily log, as the roadmap asks. The dashboard isn't changed in A. |
| CSV export | **Not in P2.1** | The database backup already covers the data. Measurement export belongs with P2.10's richer exports. |

## A. Tape measurements + Navy estimate

**Done when:**

- `/measurements` shows the session form (date defaulting to today), the latest
  estimate with its measurement date, and a history table, newest first.
- The form has neck, abdomen (navel), waist (narrowest), and hips, each with up to
  three reading inputs in your length unit. Saving stores every reading in cm.
- Reopening a session (`/measurements?date=…`) pre-fills its readings. Saving
  without changing a value keeps the stored value exactly (no round-trip drift).
- Saving a date that already has a session updates it; changing the date picker to
  another date with a session is refused with 409 and an Edit link, as for entries.
  A session edited in another tab since the form loaded is refused with 409.
- Changing units since the page loaded is refused with 409 and nothing is saved.
- Each history row shows the date, the mean value per site, and the estimate or
  the reason there isn't one.
- The latest estimate comes from the **newest session that has the sites its
  equation needs**, shown with that session's date. Newer sessions that can't
  produce an estimate don't hide it; the page notes them (for example "Newer
  measurements on 8 Oct don't include neck"). If no session can produce an
  estimate, the page shows the reason for the newest one.
- An instructions section explains where and how to measure each site, and which
  sites the estimate uses for your sex.
- Deleting a session removes it and its readings.
- An invalid submission returns 422 with errors and the typed values, and changes
  nothing.
- `./check.sh` passes, with the tests listed under task 7.

### Files

| File | Change |
| --- | --- |
| `models.py` | `MeasurementSession`, `MeasurementReading` |
| `migrations/versions/…_create_measurements.py` | New tables |
| `calc.py` | `Site`, `navy_body_fat`, `mean_reading` |
| `units.py` | `LengthUnit`, conversions, `format_length` |
| `measurement_form.py` | New: parse and validate the session form |
| `measurements.py` | New: storage (get, upsert, delete, list) |
| `routes/measurements.py` | New: page, save, delete |
| `templates/measurements.html` | New page; nav item in `base.html` |
| `app.py` | Include the router |
| `static/style.css` | Reading grid, instructions |

### 1. Schema (`models.py`, migration)

```python
class MeasurementSession(Base):
    __tablename__ = "measurement_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[Date] = mapped_column(unique=True)
    created_at / updated_at  # same as Entry
    readings: Mapped[list["MeasurementReading"]] = relationship(
        cascade="all, delete-orphan", order_by=...
    )

class MeasurementReading(Base):
    __tablename__ = "measurement_readings"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("measurement_sessions.id"))
    site: Mapped[str]          # a calc.Site value
    reading: Mapped[int]       # 1-3
    value_cm: Mapped[float]
    # UniqueConstraint(session_id, site, reading)
```

- A surrogate `id` lets later milestones (P2.2 calendar, P2.7 experiments) refer to a
  session, while `unique` on `date` keeps one session per date.
- SQLite doesn't enforce foreign keys without a pragma, so deletes rely on the ORM
  cascade. Don't add raw `ON DELETE` handling outside `db.py`.
- The unique constraint on `(session_id, site, reading)` rules out replacing the
  `readings` collection wholesale: SQLAlchemy's flush runs inserts before deletes,
  so the new rows collide with the old ones. See task 5 for the upsert.
- `updated_at` on the session must change when only its readings change, because the
  version check uses it. Touch it explicitly in the upsert when any reading changed.
- Generate the migration with Alembic autogenerate, then review it by hand.

### 2. Math (`calc.py`)

- `Site` StrEnum: `NECK`, `ABDOMEN`, `WAIST`, `HIP` (stored values `neck`, `abdomen`,
  `waist`, `hip`).
- `mean_reading(values: Sequence[float]) -> float`: `ValueError` on an empty sequence.
- `navy_body_fat(sex, height_cm, sites: Mapping[Site, float]) -> float | None`:
  returns percent (not a fraction, unrounded), or `None` when a required site is
  missing. Raises `ValueError` when the log argument is ≤ 0. Male needs neck +
  abdomen; female needs neck + waist + hip.
- The 2–60% "outside the range" check is presentation and lives in the page's view
  code, not in `calc.py`.

### 3. Units (`units.py`)

- `LengthUnit` (`cm`, `in`), `length_unit_for(weight: WeightUnit)`,
  `length_to_cm`, `length_from_cm`, `format_length` (one decimal).
- Reuse `CM_PER_INCH` and `matching_bound` for the displayed limits.

### 4. Form (`measurement_form.py`)

- Field names `<site>_<n>`, e.g. `neck_1`, `abdomen_3`; plus `date`, `loaded_date`,
  `loaded_version`, `weight_unit`.
- Same shape as `entry_form.py`: return `MeasurementInput(date, readings)` or
  `MeasurementFormErrors`. Blank slots are skipped; at least one reading overall.
- Round-trip rule per slot: text equal to the formatted stored reading for that site
  and slot keeps the stored value.
- Readings are renumbered 1..n per site in the order typed, so a gap (slot 1 blank,
  slot 2 filled) doesn't leave a hole.
- Date rules match the entry form: valid, not in the future.

### 5. Storage (`measurements.py`)

`get_session(date)`, `upsert_session(input)`, `delete_session(date)`,
`all_sessions()` newest first, with readings loaded in one query (`selectinload`).

`upsert_session` inserts or updates the session and **updates reading slots in
place**, all in one transaction:

- Key the existing readings by `(site, reading)` and the submitted ones the same way.
- Slot in both: set `value_cm` only if it differs.
- Slot only submitted: append a new `MeasurementReading`.
- Slot only existing: remove it from the collection (delete-orphan deletes it).
- Touch `updated_at` only if any of the above changed something.

Because a slot that exists before and after is updated rather than deleted and
re-inserted, the flush never holds two rows for the same slot. Unchanged readings are
not written at all, which also keeps the round-trip rule exact.

### 6. Routes and template

- Stale-units guard: a weight-only check (`web.weight_unit_matches(values,
  settings)`, or a parameter on `units_match`) comparing the form's `weight_unit`
  with Settings. Changing only the energy unit must not block a save.
- `GET /measurements[?date=…&saved=…]`, `POST /measurements`,
  `POST /measurements/{date}/delete`, each following the patterns in
  `routes/today.py`: stale units → 409 fresh render, validation → 422,
  overwrite guard and version check → 409, success → 303.
- View code builds, per session: the mean per site (formatted) and an estimate state:
  a value, "set sex and height in Settings", "needs neck and abdomen" (or the female
  sites), or "outside the equation's range".
- Page sections, top to bottom: latest estimate ("18% · Navy method · measured Thu 8
  Oct"), the form, the instructions (`<details>`, open when there are no sessions
  yet), the history table.
- Instructions content: site positions and technique taken from the 2021 Navy guide
  ([mirrored PDF](https://www.calculator.net/pdf/navy-physical-readiness-program.pdf)),
  checked against its text when writing the template rather than paraphrased from
  memory. In particular, copy its neck placement and tape angle exactly. Expected
  content: bare skin, tape snug without compressing; neck just below the larynx;
  abdomen at the navel, at the end of a normal exhale; waist at the narrowest point;
  hips at the widest point of the buttocks, feet together. Then the app's own
  guidance: take up to three readings per site and the page averages them; measure at
  the same time of day, for example in the morning before eating.
- A note under the history: "Estimates use your current sex and height from
  Settings."

### 7. Tests

`test_calc.py`:

- [x] Navy male and female estimates against **independently established answers**:
      several cases from the Navy guide's lookup charts (whole percent, so
      `abs=0.5`), plus at least one case recomputed from the spreadsheet in
      LibreOffice headless. Record where each case came from in the test.
- [x] Missing a required site → `None`. Abdomen ≤ neck → `ValueError` naming the sites.
- [x] `mean_reading` of one and of three values; empty → `ValueError`.

`test_units.py`: cm/in round trip; `format_length` precision.

`test_measurement_form.py`: blank slots skipped; gap renumbering; no readings → form
error; range boundaries in cm and in inches (displayed limit stores the bound);
non-numeric, `nan`, `inf`; future date; round-trip keeps the stored value.

`test_measurements.py` (real SQLite): insert; re-save with the **same slots and new
values** (the case that breaks a delete-then-insert replace); re-save adding a slot,
removing a slot, and both at once; `updated_at` moves when only a reading changes and
stays put when nothing changes; delete removes the readings; unique date enforced.

`test_db.py`: migration upgrades from empty; upgrading a database with existing
entries keeps them; models and migrations agree.

`test_measurement_routes.py` (TestClient, real DB, fixed `clock.today`):

- [x] Save → 303, rows in the DB in cm. In lb mode, inches are converted.
- [x] Edit with unchanged text → stored values identical.
- [x] Overwrite guard 409 and version-check 409 leave stored rows unchanged.
- [x] Stale `weight_unit` → 409, nothing saved, submitted text not echoed.
- [x] Energy unit changed in Settings since the page loaded (weight unit unchanged)
      → save succeeds.
- [x] Invalid → 422, nothing saved.
- [x] Delete → 303, session and readings gone.
- [x] The page shows the estimate for a known case, "Settings" when height is
      missing, and "outside the equation's range" for an abdomen ≤ neck.
- [x] Older complete session, newer waist-only session → the latest estimate is the
      older session's value with the older date, plus the note about the newer one.
- [x] Cross-origin POST → 403.

### Verify by hand

```zsh
./check.sh
TDEE_DATA_DIR=$(mktemp -d) ./run.sh
# Settings: male, 71 in. Measurements: neck 15.5, abdomen 34 / 34.5 / 34 → estimate shown
# reload the session, save without changes: sqlite3 shows identical value_cm
# switch to kg: values show in cm; switch back: identical inches
# clear height in Settings: the estimate cell links to Settings, readings still shown
# delete the session: readings gone (sqlite3)
```

### Verification record — October 9, 2026

- `./check.sh`: formatting, lint, strict types, and all 612 tests pass;
  branch coverage is 99.94%.
- Equation fixtures include independently read male/female Navy lookup values
  and the original spreadsheet recalculated in LibreOffice: male, 71 in height,
  15.5 in neck, 34.5 in abdomen → 17% in cell R12.
- Browser checks used a separate temporary data directory: save repeated readings,
  unchanged edit (identical raw values, IDs, and timestamps), cm/in switching,
  missing-height Settings link, and deletion of both session and readings.
- Desktop (1280px) and mobile (375px), light and dark layouts checked. The desktop
  table shows its actions; mobile scrolls the table without page overflow.
- A is complete locally. B and C remain outlines; no commit or PR is included.

### Not in A

- External results (B); WHtR, BMI, chart, seed data (C).
- Arms, chest, thighs; RFM; skinfolds (later wishlist / P2.9).
- Dashboard or calendar markers (P2.2).
- A warning when repeated readings disagree by more than about 1 in. Worth adding
  once the form is in use.

## B. External body-fat results (outline)

`body_fat_results` table: date, percent, method (`dexa`, `bia_scale`, `bod_pod`,
`hydrostatic`, `other`), optional source label (for example a device or clinic
name), optional notes. Several results per date are allowed, since a scale and a
scan can both report on the same day. Form, edit/delete, and its own history list on
`/measurements`, visually separate from tape estimates. Never averaged with them.
Detail this section before starting B.

## C. Context and polish (outline)

Waist-to-height ratio per session (needs no weight). BMI only if a weigh-in exists on
the session date; otherwise omitted. Both are labelled as context, not body fat.
Optional Chart.js line of the estimate over time. `seed_dev_data.py` gains sessions.
Detail this section before starting C, or drop it.

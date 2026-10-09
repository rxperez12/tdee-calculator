# Milestone 6: CSV export

**Goal:** One link on the History page downloads every entry as a CSV file. It serves as
a portable backup, a way to look at the data in a spreadsheet, and the starting point
for the richer exports in Phase 2 (P2.10). It adds no schema changes and no new
dependencies.

**Done when:**

- The History page has a **Download CSV** link. Clicking it downloads
  `tdee-entries-YYYY-MM-DD.csv` (today's date) without leaving the page.
- The file has one header row and one row per entry, **oldest first**, with the columns
  `date,weight_kg,calories_kcal,source,created_at,updated_at`.
- Values are the stored kg/kcal values, whatever display units are set in Settings.
  A weight saved in lb reads back as the exact stored float.
- A missing weight or calorie total is an empty field, never `0`.
- With no entries, the download still works and contains only the header row.
- The response is `text/csv; charset=utf-8` with `Content-Disposition: attachment`,
  `X-Content-Type-Options: nosniff`, and `Cache-Control: no-store`.
- Opening the file in LibreOffice/Excel shows one column per field and dates that
  sort correctly.
- `./check.sh` passes. No migration.

## Decisions

| Question | Decision | Why |
| --- | --- | --- |
| Route | **`GET /entries.csv`** | A download only reads data, so GET is correct and a plain `<a href>` works without JavaScript or a form. The `.csv` suffix makes the URL say what it returns. |
| Where the link lives | **History page**, next to the entry count | History is the "all my data" page. The Today page stays focused on the daily routine. |
| Units | **Stored kg/kcal, with the unit in the column name** (`weight_kg`, `calories_kcal`) | Lossless and unambiguous: the file means the same thing whichever units were set when it was exported, and a future import doesn't need to guess. Matches the "store in kg/kcal" rule. A display-units option belongs to P2.10's richer exports. |
| Number precision | **Full stored precision.** Weight is written as Python's shortest round-trip float text (`81.6466266`), calories as an integer | Rounding would make the export lossy, and a backup that loses data defeats the point. Spreadsheets can format the column. |
| Missing values | **Empty field** | Unknown is not zero, as the Phase 2 notes require. A `0` for calories would read as a fasting day. |
| Row order | **Date ascending** | The natural order for a time series, and what spreadsheets and charting tools expect. History shows newest first, but that's a display choice. |
| Columns | **All of `entries`:** `date, weight_kg, calories_kcal, source, created_at, updated_at` | It's a full export. `source` already distinguishes manual entries from future imports, and the timestamps cost nothing to include. |
| Date and time format | **ISO 8601:** `2026-10-08` and `2026-10-08T08:00:00.123456` (preserve stored microseconds when present, no time zone) | Use `.isoformat()` without truncating timestamp precision so the export is lossless. Timestamps are naive local time, as everywhere in the app (see roadmap "Local time everywhere"). |
| Filename | **`tdee-entries-YYYY-MM-DD.csv`**, dated with `clock.today()` | Repeated exports don't overwrite each other in Downloads, and the name says when the snapshot was taken. |
| CSV dialect | **Python's `csv` module defaults:** comma separator, `\r\n` line endings, quoting only when needed, UTF-8 without a BOM | That is RFC 4180. Every value is ASCII, so a BOM (which Excel sometimes needs for non-ASCII text) adds nothing. |
| Building the file | **In memory (`io.StringIO`), returned as one `Response`** | One row a day is ~3,650 rows (~200 KB) after ten years. Streaming would add complexity for no benefit. |
| Spreadsheet formula injection | **Not applicable yet**: every value is a date, number, timestamp, or a fixed `source` value | No free text comes from the user. When notes arrive (P2.4), cells starting with `= + - @` need escaping. Record this in the module docstring so it isn't forgotten. |
| Cross-origin reads | **No extra check.** Add `X-Content-Type-Options: nosniff`. | The existing middleware only guards unsafe methods. Another site can link to the download, but it can't read the response: `fetch` without CORS headers is opaque, `TrustedHostMiddleware` blocks DNS rebinding, and `nosniff` with `text/csv` stops the file from being loaded as a script. A cross-site link just saves your own data to your own machine. |
| Caching | **`Cache-Control: no-store`** | An export should always reflect the database as it is now. |

## Tasks

### 1. Query all entries

In `entries.py`, add:

```python
def all_entries(session: Session) -> list[Entry]:
    """Every entry, oldest first."""
```

Rewrite `all_day_logs` to build its `DayLog`s from `all_entries`, so there is one
"every entry, oldest first" query.

### 2. `export.py`

A new module with a single function that has no web or database imports beyond the
`Entry` model:

```python
CSV_COLUMNS = ("date", "weight_kg", "calories_kcal", "source", "created_at", "updated_at")

def entries_csv(entries: Iterable[Entry]) -> str:
    """Entries as RFC 4180 CSV text with a header row, in the order given."""
```

- Use `csv.writer` over an `io.StringIO`. The writer emits `\r\n` itself, so nothing
  else needs to handle line endings. (The `newline=""` advice in the `csv` docs is
  for real files opened with `open`. A `StringIO` doesn't translate newlines.)
- `None` → `""`. Dates and timestamps use `.isoformat()` with the default precision;
  preserve nonzero microseconds in both `created_at` and `updated_at`.
  The writer turns floats into text with `repr`, which is the shortest form that
  round-trips. Don't format them by hand.
- Module docstring: the formula-injection note from the decisions table.

### 3. Route

In `routes/history.py`:

```python
@router.get("/entries.csv")
def export_csv(session: SessionDependency) -> Response:
```

Return `Response(content=..., media_type="text/csv; charset=utf-8", headers={...})`
with the `Content-Disposition`, `nosniff`, and `no-store` headers. The filename date
comes from `clock.today()`. This route doesn't need `SettingsDependency`, because
units don't affect the export.

### 4. Template

In `history.html`, after the entry count:

```html
<p><a href="/entries.csv" download>Download CSV</a></p>
```

Show it even with zero entries, since a header-only file is valid. The `download`
attribute is a hint. `Content-Disposition` is what makes it a download.

### 5. Tests

`test_export.py` (pure, building `Entry` objects without a database):

- [ ] No entries → exactly the header line, `"date,weight_kg,calories_kcal,source,created_at,updated_at\r\n"`.
- [ ] One full entry → the header plus the row
      `2026-10-08,80.5,2100,manual,2026-10-08T08:00:00,2026-10-08T09:30:00`.
- [ ] Nonzero microseconds → `created_at = 2026-10-08T08:00:00.123456` and
      `updated_at = 2026-10-08T09:30:00.654321` export exactly as shown. Parsing
      each field with `datetime.fromisoformat()` reproduces its original value exactly.
- [ ] Weight only and calories only → the missing field is empty (`2026-10-07,80.5,,manual,...`),
      not `0` or `None`.
- [ ] `weight_kg = 180 * 0.45359237` (180 lb) → parsing the field back with `float()`
      equals the stored value exactly. Assert `==`, not `approx`, because exact round-trip
      is the behavior under test.
- [ ] Rows come out in the order given (the query, not this function, decides the order).

`test_entries.py`:

- [ ] `all_entries` returns entries oldest first.

`test_history_routes.py`, or add to the existing History tests (the `client` fixture,
real DB). Parse the body with `csv.reader(io.StringIO(response.text))` instead of
comparing long strings:

- [ ] Empty DB → 200, `text/csv; charset=utf-8`, and only the header row.
- [ ] `Content-Disposition` is `attachment; filename="tdee-entries-2026-10-08.csv"`
      (the fixture's fixed today).
- [ ] `nosniff` and `no-store` headers are present.
- [ ] Three entries saved out of order through `POST /entries` → rows oldest first,
      with the values saved.
- [ ] 35 entries saved through `POST /entries` → all 35 data rows are exported,
      oldest first, with the expected oldest and newest dates. This must exceed
      History's 30-entry display limit to catch reuse of `recent_entries`.
- [ ] Settings set to lb/kJ, then a weight saved in lb → the export still has the
      kg value and kcal calories.
- [ ] `GET /entries.csv` with `Host: evil.example` → 400.
- [ ] `GET /history` contains a link to `/entries.csv`.

## Verify by hand

```zsh
./check.sh
uv run scripts/seed_dev_data.py --data-dir /tmp/tdee-dev --with-settings
TDEE_DATA_DIR=/tmp/tdee-dev ./run.sh
# History → Download CSV: the file lands in Downloads as tdee-entries-<today>.csv
# open it in LibreOffice/Excel: one column per field, dates oldest first, blanks where values are missing
# switch Settings to lb, download again: weight_kg values are unchanged
```

The seed data skips some weights and calorie totals, so blank fields appear without
extra setup. Use a temp `TDEE_DATA_DIR` so manual testing never
touches the real `data/`.

## Afterwards

- Roadmap: tick milestone 6 in Status. v1 is then complete.

## Not in this milestone

- Import of any kind, including re-importing this CSV (see "Other deferred ideas").
- Display-unit, date-range, or JSON/Markdown exports (P2.10).
- Exporting settings. They're a handful of values on one page, and the startup backup
  has them.
- Streaming responses or pagination.

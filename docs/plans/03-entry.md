# Milestone 3: Entry

**Goal:** Logging a day takes a few seconds. The home page has a form for date,
weight, and calories, and a list of recent entries with edit and delete. Saving a
date that already has an entry updates it instead of adding a second row.

**Done when:**

- Opening the app shows the form with today's date filled in and the cursor in the
  weight field. Typing a number and pressing Enter saves it.
- If today already has an entry, the form opens pre-filled with it. Adding the
  evening's calories keeps the morning's weight.
- Saving a date that already exists updates that row. There is still one row per date,
  `created_at` stays the same, and `updated_at` changes whenever a stored value changes.
- Changing the form's date to another date that already has an entry and saving is
  refused with an Edit link. The existing entry is untouched.
- A POST from another site is refused with 403 and changes nothing. A request whose
  `Host` header isn't localhost is refused with 400.
- The recent entries list shows the newest first, with an edit link and a delete button
  for each row.
- An invalid submission re-renders the form with an error message and the values you
  typed, returns 422, and leaves the database unchanged.
- `./check.sh` passes, including the route tests listed in `docs/testing.md`
  under "Milestone 3".

## Decisions

| Question | Decision | Why |
| --- | --- | --- |
| Units | **kg and kcal only** for now, labelled in the form | `units.py` is milestone 4. The form converts at the boundary, so milestone 4 adds a conversion step in one place and touches nothing else. |
| Where the form lives | **On `/`**, above the recent list | Logging is the most frequent action. Milestone 5 adds the dashboard to the same page or moves the form, whichever reads better. |
| Upsert semantics | **Replace:** a save sets both fields to what the form sent, so a blank field clears that value | It is the only rule that lets you clear a mistyped value. Pre-filling the form with the selected date's saved values (below) prevents the obvious data loss. |
| Edit | **`GET /?date=YYYY-MM-DD`** pre-fills the same form | One form, one POST route. No separate edit page. |
| Delete | **`POST /entries/{date}/delete`** | HTML forms can only send GET and POST. A GET that deletes could be triggered by a link prefetch or a crawler. |
| After a successful save or delete | **303 redirect to `/`** (Post/Redirect/GET) | Refreshing the page won't resubmit the form. 303 tells the browser to follow up with a GET. |
| Confirmation | **`/?saved=YYYY-MM-DD`** shows "Saved Thu 8 Oct" | Confirms what happened, with no session or flash-message machinery. |
| Empty entry | **Rejected:** at least one of weight or calories is required | A row with neither has no use and would count as a "logged day". |
| Valid ranges | Weight **20–400 kg**; calories **whole number, 0–20,000** | These catch typos (e.g. 8000 for 80.0) without rejecting real values. 0 kcal (a fasting day) is allowed. |
| Future dates | **Rejected** (later than `clock.today()`) | You can't weigh in tomorrow. This also catches date-picker slips. |
| Recent list length | **The 30 newest entries** | About a month, which matches the TDEE window. "Show all" can wait for CSV export or the chart. |
| Overwriting another date | **Refused with 409** unless the form was loaded for that date | See "Overwrite guard" below. |
| What `updated_at` means | **The last time a stored value changed** | SQLAlchemy only emits an UPDATE, and so only fires `onupdate`, when an attribute actually changed. A save that changes nothing touches nothing. |
| CSRF protection | **Fetch Metadata check with an `Origin` fallback, on every unsafe method** | Binding to localhost doesn't stop any website you visit from submitting a form to `127.0.0.1:8000`. See "Cross-origin protection" below. |
| DNS rebinding | **Reject requests whose `Host` isn't a local name** | Without this, a rebinding attack makes an attacker's page same-origin with the app, which defeats any CSRF check. |

### Overwrite guard

With replace semantics, the form overwrites whatever is saved for the date it submits.
Pre-filling covers the normal flows: today on page load, and any row via its Edit link.
The gap is changing the date picker by hand, for example to backfill yesterday, to a
date that already has data. Saving would replace that row with the form's values.
Startup backups don't help here, because they don't contain entries made since the app
started.

The form carries a hidden `loaded_date`: the date it was rendered for. On save:

- `entry_date == loaded_date`: a normal save or edit. Upsert.
- `entry_date != loaded_date`, and `entry_date` has **no** entry: a backfill. Insert.
- `entry_date != loaded_date`, and `entry_date` **has** an entry: refuse with 409.
  Re-render the form with the typed values and the message "8 Oct already has an entry:
  Edit it", linking to `/?date=...`.

A missing or malformed `loaded_date` matches no date, so a hand-built POST can create
entries but never overwrite one. Tests that update an entry must send `loaded_date`.

**Added after review:** the date check misses a stale form for the *same* date, e.g. a
second tab still showing a blank form after the first tab saved a weight. The form
also carries a hidden `loaded_version`: the row's `updated_at`, or `""` when the date
had no row. Saving the loaded date is refused with 409 ("changed since this page
loaded") unless the row's current version still matches. That also covers a row
deleted in another tab.

### Cross-origin protection

Today this protects `POST /entries` and the delete route. Milestones 4 and 6 add more
mutating routes, so the check runs as middleware on every unsafe method rather than as
a dependency each route must remember. The rules follow OWASP's Fetch Metadata guidance
and the same approach as Go 1.25's `http.CrossOriginProtection`:

1. `GET`, `HEAD`, and `OPTIONS` pass. They don't change anything (keep it that way).
2. If the request has `Sec-Fetch-Site`, allow only `same-origin` or `none`. `none`
   means the user started the request directly, e.g. a bookmark. Every current browser
   sends this header.
3. Otherwise, if it has `Origin`, allow it only if the origin's host and port equal the
   `Host` header. This is the fallback OWASP requires for browsers without Fetch Metadata.
4. Otherwise, allow. A request with neither header isn't from a modern browser, so it
   can't be a forged cross-site browser request. curl and `TestClient` land here.

A refused request gets a plain 403 and never reaches the route.

**Why not a token?** A synchronizer token or a signed double-submit cookie is the other
OWASP-recommended defense. Here it would need a persisted secret key, a cookie, and a
hidden field threaded through every form and template context. The header check needs
none of that and fails closed in every modern browser. If the app is ever hosted for
other people (a reach goal), revisit this alongside authentication.

**Host check.** `Origin == Host` proves only that the page and the request share an
origin. In a DNS-rebinding attack, `evil.example` resolves to `127.0.0.1` after the
page loads, so the attacker's page *is* same-origin, with `Host: evil.example:8000`.
Starlette's `TrustedHostMiddleware` with an allow-list of `localhost`, `127.0.0.1`,
`[::1]`, and `config.host` closes that gap. A non-local `TDEE_HOST` will need an
explicit allow-list setting; that's for the hosting goal.

## Files

```text
src/tdee_calculator/
  entry_form.py                 # new: parse and validate raw form strings (pure)
  entries.py                    # new: get / upsert / delete / recent, given a Session
  security.py                   # new: cross-origin check (pure) + local host list
  models.py                     # edit: timestamp defaults go through clock at call time
  app.py                        # edit: middleware, routes for the form, save, and delete
  templates/
    index.html                  # edit: form, errors, saved message, recent list
  static/
    style.css                   # edit: form and table layout
tests/
  conftest.py                   # edit: `client` fixture with a local base URL
  test_entry_form.py            # new
  test_entries.py               # new
  test_security.py              # new
  test_app.py                   # edit
```

No migration: the `entries` table from milestone 1 already has everything this needs.
`test_models_match_migrations` confirms that `models.py` hasn't drifted.

## Tasks

Do them in order. Each one leaves `./check.sh` passing.

### 1. Make timestamps testable (`models.py`)

`mapped_column(default=clock.now)` stores a reference to the function object when the
module is imported. Monkeypatching `tdee_calculator.clock.now` later doesn't affect it,
so a test can't control `created_at` or `updated_at`. Route the defaults through a small
module-level function that looks up `clock.now` each time it's called:

```python
def _now() -> DateTime: ...   # return clock.now()
```

Use it for `default=` and `onupdate=`. Columns and types don't change, so no migration.

Same rule for the routes: call `clock.today()` through the module (`from tdee_calculator
import clock`), never `from tdee_calculator.clock import today`. Monkeypatching replaces
the attribute on the module, and a name you imported directly still points at the
original function.

### 2. Form parsing (`entry_form.py`)

HTML forms send strings, and an empty input arrives as `""`. If the route declared
`weight: float | None`, FastAPI would answer `""` with a 422 JSON error page instead of
the form, so the route takes raw strings and this module does the parsing. It is pure:
no FastAPI or database, and `today` is passed in.

```python
@dataclass(frozen=True)
class EntryInput:
    date: Date
    weight_kg: float | None
    calories: int | None

@dataclass(frozen=True)
class EntryFormErrors:
    errors: dict[str, str]        # field name -> message; "form" for whole-form errors

def parse_entry_form(
    date_text: str, weight_text: str, calories_text: str, today: Date
) -> EntryInput | EntryFormErrors: ...
```

- Strip whitespace. A blank weight or calories value becomes `None`.
- Date: `Date.fromisoformat`. Report a missing, malformed, or future date on `"date"`.
- Weight: `float()`. Reject non-numbers, `nan`/`inf` (`float()` accepts them;
  `math.isfinite` catches them), and values outside 20–400.
- Calories: `int()`. Reject `"2000.5"`, non-numbers, and values outside 0–20,000.
- Neither weight nor calories → an error on `"form"`.
- Collect every error instead of stopping at the first, so one submission shows all
  problems. Keep the range limits as module constants and use them in the messages.

Returning one of two types (a union) instead of raising keeps the route simple. It
checks `isinstance(result, EntryFormErrors)`, and mypy narrows the type in each branch.

### 3. Entry storage (`entries.py`)

Plain functions that take a `Session`, so routes and tests share the same code. Each
mutating function commits its own transaction; the session comes from `get_session`.

```python
RECENT_LIMIT = 30

def get_entry(session: Session, entry_date: Date) -> Entry | None: ...
def upsert_entry(session: Session, data: EntryInput) -> Entry: ...
def delete_entry(session: Session, entry_date: Date) -> bool: ...   # False if missing
def recent_entries(session: Session, limit: int = RECENT_LIMIT) -> list[Entry]: ...
```

- **Upsert through the ORM:** `session.get(Entry, date)`, then either set the fields on
  the existing row or `session.add(Entry(...))`, then `commit()`. That's portable (no
  SQLite `INSERT ... ON CONFLICT`, per the "SQLite-specific SQL stays in `db.py`" rule)
  and lets `onupdate` set `updated_at`. With a single user there's no race between the
  `get` and the `add`.
- Assigning a value equal to the current one doesn't mark the row dirty, so an
  identical resave emits no UPDATE and `updated_at` stays put. That's the intended
  meaning ("last changed"), so don't set `updated_at` by hand.
- `upsert_entry` doesn't know about the overwrite guard. That's a request-level rule
  (it depends on what the form was showing), so it lives in the route.
- Set `source = "manual"` on every save, so a manual edit claims a row that a future
  import created.
- `recent_entries`: `select(Entry).order_by(Entry.date.desc()).limit(limit)`.
- `delete_entry` on a missing date returns `False` and does nothing. The route treats
  that as success too: the end state the user asked for is true either way.

### 4. Cross-origin protection (`security.py`, `app.py`)

Do this before the routes, so no mutating route ever exists unprotected. The decision
is a pure function, so a table of header combinations covers it without a server:

```python
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
LOCAL_HOSTS = ("localhost", "127.0.0.1", "[::1]")

def is_cross_origin(
    method: str, host: str | None, origin: str | None, sec_fetch_site: str | None
) -> bool: ...

def allowed_hosts(config: Config) -> list[str]: ...   # LOCAL_HOSTS + config.host
```

- Follow the four rules in "Cross-origin protection" above.
- For the `Origin` comparison, parse with `urllib.parse.urlsplit` and compare its
  `netloc` to `host`. A malformed or `"null"` origin (sandboxed iframes send that) is
  cross-origin.

In `create_app`:

- `application.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts(config))`.
  `TrustedHostMiddleware` matches the hostname without the port, so `127.0.0.1:8000` passes.
- An `@application.middleware("http")` function that returns
  `PlainTextResponse("Cross-origin request refused", status_code=403)` when
  `is_cross_origin(...)` is true, and otherwise `await call_next(request)`. Read the
  headers with `request.headers.get("origin")` etc.; Starlette headers are case-insensitive.

FastAPI is built on Starlette and re-exports most of its classes, but not this
middleware. Import it directly:
`from starlette.middleware.trustedhost import TrustedHostMiddleware`. Starlette is
already installed as a FastAPI dependency, so there's nothing to `uv add`.
`PlainTextResponse` is available from `fastapi.responses`.

Starlette runs middleware added last first. The order doesn't matter for correctness
here, since both checks only reject.

**Test client.** `TestClient` sends `Host: testserver`, which the allow-list rejects.
Add a `client` fixture in `conftest.py` that yields
`TestClient(create_app(config), base_url="http://127.0.0.1:8000")` as a context manager,
and switch the two existing tests in `test_app.py` to it.

### 5. Routes (`app.py`)

Add three routes inside `create_app`, next to `home`. Keep them thin: parse, call
`entries.py`, render or redirect.

```python
@application.get("/")
def home(
    request: Request,
    session: SessionDependency,
    date: Date | None = None,       # ?date=... edit mode
    saved: Date | None = None,      # ?saved=... confirmation
) -> HTMLResponse: ...

@application.post("/entries", response_model=None)
def save_entry(
    request: Request,
    session: SessionDependency,
    entry_date: Annotated[str, Form()] = "",
    loaded_date: Annotated[str, Form()] = "",
    weight_kg: Annotated[str, Form()] = "",
    calories: Annotated[str, Form()] = "",
) -> HTMLResponse | RedirectResponse: ...

@application.post("/entries/{entry_date}/delete")
def remove_entry(entry_date: Date, session: SessionDependency) -> RedirectResponse: ...
```

- **`home`:** the form date is `date` or `clock.today()`. If that date has an entry,
  pre-fill weight and calories from it. Pass the recent list, the entry count, and
  `saved`.
- **`save_entry`:**
  - On errors, render `index.html` with `status_code=422`, the errors, the submitted
    strings (so the user's typing isn't lost), and the recent list.
  - Apply the overwrite guard: if `entry_date` isn't the same date as `loaded_date`
    and `get_entry` finds a row, render with `status_code=409`, the typed values, and
    the "already has an entry" message with its Edit link. Compare dates, not strings:
    parse `loaded_date` with `Date.fromisoformat` and treat a failure as "no match".
  - Otherwise upsert and return `RedirectResponse(f"/?saved={date}", status_code=303)`.
  - `response_model=None` stops FastAPI from trying to build a response schema from
    the union return type.
- **`remove_entry`:** delete, then a 303 redirect to `/`. A malformed date in the path
  gets FastAPI's default 422. That URL only comes from the list's own buttons, so a
  plain error page is fine there.
- Building the template context: a small helper inside `create_app` (e.g.
  `render_home(request, session, form_values, errors, status_code)`) keeps `home` and
  the error branch of `save_entry` from duplicating it.

Form fields need `python-multipart`, which is already a dependency.

### 6. Template and styles

`index.html`:

- A form posting to `/entries`, fields named `entry_date`, `weight_kg`, and `calories`
  to match the route parameters, plus `<input type="hidden" name="loaded_date">` set to
  the date the form was rendered for. When re-rendering after an error, keep the
  submitted `loaded_date`, not the newly typed date. Otherwise a second save would
  get past the guard.
  - `<input type="date" max="{{ today }}">`.
  - `<input type="number" step="any" inputmode="decimal" autofocus>` for weight.
    `step="any"` stops the browser from rejecting `80.25`.
  - `<input type="number" step="1" inputmode="numeric">` for calories.
  - Unit labels "kg" and "kcal", hard-coded for now.
  - The submit button reads "Save" or "Update" depending on whether the date has an
    entry, so you can see when you're overwriting.
- An error next to each field, plus the `"form"` error above the form.
- "Saved Thu 8 Oct" when `saved` is set.
- The recent list as a `<table>`: date (with weekday), weight (1 decimal), calories,
  blank cells for missing values, an "Edit" link to `/?date=...`, and a "Delete" button
  inside a small `<form method="post">` per row.
- An empty state when there are no entries yet.

Browser validation (`min`, `max`, `step`) is a convenience. The server is the source of
truth, and the tests post directly, bypassing it.

No JavaScript in this milestone. An `onsubmit="return confirm(...)"` on delete is tempting,
but `docs/testing.md` asks for browser checks once a feature depends on JS. Backups cover
a mis-click for now.

`style.css`: lay out the form fields in a row, right-align the number columns, and make
the per-row delete form inline.

### 7. Tests

`test_entry_form.py` (pure, no fixtures). Parametrize where a table of cases reads better:

- [ ] Weight and calories both given → `EntryInput` with a float and an int.
- [ ] Weight only, calories only → the other is `None`.
- [ ] Surrounding whitespace is ignored. Blank and whitespace-only become `None`.
- [ ] Both blank → a `"form"` error.
- [ ] Boundaries: 20 and 400 kg accepted, 19.9 and 400.1 rejected. 0 and 20,000 kcal
      accepted, -1 and 20,001 rejected.
- [ ] `"abc"`, `"nan"`, and `"inf"` weights are rejected. `"2000.5"` calories rejected.
- [ ] Date equal to `today` accepted. `today + 1 day` rejected. `""` and `"2026-13-01"` rejected.
- [ ] Several bad fields at once → one error per field.

`test_entries.py` (real SQLite: run migrations on `config`, then build a session from
`make_engine`; a fixture keeps this short):

- [ ] Upsert on a new date inserts one row with `source == "manual"`.
- [ ] Upsert on an existing date leaves one row with the new values. `created_at` is
      unchanged and `updated_at` moved. Monkeypatch `clock.now` to two fixed datetimes,
      which works because of task 1.
- [ ] Upsert with identical values leaves `updated_at` unchanged, even with `clock.now`
      returning a later time.
- [ ] Upsert with `weight_kg=None` clears a previously saved weight (replace semantics).
- [ ] `delete_entry` removes the row and returns `True`; on a missing date it returns `False`.
- [ ] `recent_entries` returns newest first and respects `limit`.

`test_security.py` (pure, parametrized over `is_cross_origin`):

- [ ] `GET` with `Sec-Fetch-Site: cross-site` → allowed (safe method).
- [ ] `POST` with `Sec-Fetch-Site` `same-origin` / `none` → allowed;
      `same-site` / `cross-site` → refused.
- [ ] `Sec-Fetch-Site` wins over `Origin`: `same-origin` plus a foreign `Origin` → allowed.
- [ ] No `Sec-Fetch-Site`: `Origin` matching `Host` (including port) → allowed;
      different host, different port, `"null"`, or garbage → refused.
- [ ] Neither header → allowed.
- [ ] `allowed_hosts` includes the local names and `config.host`.

`test_app.py` (the `client` fixture, through the real database; verify persisted state
by querying the temp DB, not just the HTML). Monkeypatch `clock.today` to a fixed date:

- [ ] `GET /` pre-fills the date field with the fixed today.
- [ ] `GET /` pre-fills today's saved weight when today has an entry.
- [ ] `POST /entries` with valid data → 303 to `/?saved=...`, and the row is in the DB.
      (Pass `follow_redirects=False` to see the 303.)
- [ ] Posting the same date twice → one row, holding the second post's values.
- [ ] Invalid post for a new date → 422, the error and the typed values are in the
      page, and the table is still empty.
- [ ] Invalid post for an existing date → 422, and the stored row is unchanged.
- [ ] `POST /entries/{date}/delete` → 303, and the row is gone.
- [ ] Overwrite guard: with an entry on day A, post day A with `loaded_date` = day B →
      409, the page links to `/?date=A`, and A's stored values are unchanged.
- [ ] Backfill: post day A with `loaded_date` = day B when A has no entry → 303, row created.
- [ ] Updating without `loaded_date` → 409 (a hand-built POST can't overwrite).
- [ ] `POST /entries` with `Sec-Fetch-Site: cross-site` → 403, and no row is created.
- [ ] Delete with `Sec-Fetch-Site: cross-site` → 403, and the row is still there.
- [ ] `POST /entries` with `Sec-Fetch-Site: same-origin` → 303 (the check isn't overzealous).
- [ ] `GET /` with `Host: evil.example` → 400.
- [ ] `GET /?date=...` pre-fills that entry's values.
- [ ] The recent list shows entries newest first.

## Verify by hand

```zsh
./check.sh
TDEE_DATA_DIR=$(mktemp -d) ./run.sh
# type a weight, press Enter: "Saved ..." appears, and the row is in the list
# reload: the form shows today's weight; add calories, save: one row with both
# Edit an older row, change calories, save; Delete a row
# submit 8000 as weight: the error shows, the value stays in the field, the list is unchanged
# with today loaded, change the date picker to a date in the list and save: refused, Edit link shown
```

Check the cross-origin refusal from a real browser once: save a file containing a
form that auto-submits to `http://127.0.0.1:8000/entries`, open it from another local
server (`python -m http.server 9000`, then visit `localhost:9000/that.html`), and
confirm you get the 403 page and no new entry.

Use a temp `TDEE_DATA_DIR` so manual testing never writes to the real `data/`.

## Not in this milestone

- Unit conversion (milestone 4). The form is kg/kcal only.
- Anything computed: trend, TDEE, the chart (milestone 5).
- Pagination or "show all" for the list.
- JavaScript, including a delete confirmation.
- Auth, CSRF tokens, or a configurable host allow-list (the hosting reach goal).

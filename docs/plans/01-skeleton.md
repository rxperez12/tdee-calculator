# Milestone 1: Skeleton

**Goal:** One command starts the app. `./run.sh` installs dependencies, backs up the
database and brings its schema up to date, starts the server on `127.0.0.1`, and opens
a page in the browser. No features yet. This milestone sets up the structure the later
milestones build on.

**Done when:**

- `./run.sh` on a fresh clone opens a page in the browser that shows how many entries are in the DB (0).
- `data/tdee.db` exists with the `entries` and `settings` tables, created by Alembic.
- It works when `data/` doesn't exist yet: every folder is created before anything connects.
- A second start writes a backup to `data/backups/`, and old backups are pruned to the configured count.
  Auto-reloads in the dev loop do not write backups.
- The browser opens only once the server responds.
- Host, port, and data directory can be changed with environment variables.
- `uv run pytest` passes, including a check that the models and migrations agree.

## Stack additions

- **SQLite** as the database: one file at `data/tdee.db`, no server. See the roadmap's
  Decisions section for why not Postgres.
- **SQLAlchemy 2.0 ORM**, sync (not async). FastAPI runs sync dependencies and routes in
  a thread pool, and SQLite gains nothing from async, so this keeps sessions simple.
  SQLAlchemy uses Python's built-in `sqlite3` driver, so no extra package is needed.
- **Alembic** for migrations, with autogenerate. Migrations run automatically at startup.

**Keep the database swappable.** Everything outside `db.py` goes through the ORM, and
`Config.db_url` is the only place the SQLite URL is built. The two SQLite-specific
pieces, the file backup and `render_as_batch`, stay in `db.py` and `migrations/env.py`.

## Files

```text
run.sh                          # new: one-command start
alembic.ini                     # new: CLI config (for `alembic revision`, etc.)
.gitignore                      # edit: ignore data/
pyproject.toml                  # edit: sqlalchemy, alembic, httpx (dev)
src/tdee_calculator/
  __init__.py                   # edit: main() backs up, starts uvicorn, opens the browser
  config.py                     # new: settings from environment variables
  models.py                     # new: Base, Entry, Setting
  db.py                         # new: folders, engine, migrations, backup, prepare()
  app.py                        # new: FastAPI app factory, lifespan, "/" route
  migrations/                   # new: Alembic env.py + versions/
  templates/
    base.html                   # new: page shell
    index.html                  # new: placeholder home page
  static/
    style.css                   # new: minimal styles
tests/
  conftest.py                   # new: tmp data dir fixture
  test_config.py                # new
  test_db.py                    # new
  test_app.py                   # new
```

`migrations/` lives inside the package (not at the repo root) so the app can find it via
`Path(__file__)` when it runs migrations at startup.

## Tasks

Do them in order. Each one leaves the project in a working state.

### 1. Housekeeping

- [ ] Add `data/` to `.gitignore`.
- [ ] `uv add sqlalchemy alembic`
- [ ] `uv add --dev httpx` (FastAPI's `TestClient` needs it).
- [ ] Create `tests/` with an empty `conftest.py`.

### 2. Config (`config.py`)

A small frozen dataclass read from environment variables. Don't add `pydantic-settings`
yet; the standard library is enough for four values.

| Field | Env var | Default |
| --- | --- | --- |
| `host` | `TDEE_HOST` | `127.0.0.1` |
| `port` | `TDEE_PORT` | `8000` |
| `data_dir` | `TDEE_DATA_DIR` | `data` (relative to the working directory) |
| `backup_keep` | `TDEE_BACKUP_KEEP` | `10` |

```python
@dataclass(frozen=True)
class Config:
    host: str
    port: int
    data_dir: Path
    backup_keep: int

    @property
    def db_path(self) -> Path: ...      # data_dir / "tdee.db"

    @property
    def db_url(self) -> str: ...        # f"sqlite:///{db_path}"

    @property
    def backup_dir(self) -> Path: ...   # data_dir / "backups"

def load_config() -> Config: ...        # reads os.environ, applies defaults
```

Passing a `Config` around (instead of reading `os.environ` everywhere) is what makes
tests easy: tests build a `Config` that points at a temp directory.

### 3. Models (`models.py`)

SQLAlchemy 2.0 style: `DeclarativeBase`, `Mapped[...]`, `mapped_column(...)`. The
tables match the data model in the requirements doc.

```python
class Base(DeclarativeBase): ...

class Entry(Base):
    __tablename__ = "entries"
    date: Mapped[datetime.date] = mapped_column(primary_key=True)
    weight_kg: Mapped[float | None]
    calories: Mapped[int | None]
    source: Mapped[str] = mapped_column(default="manual", server_default="manual")
    created_at: Mapped[datetime.datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(default=utcnow, onupdate=utcnow)

class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str]
```

- `Mapped[float | None]` makes a column nullable; `Mapped[float]` makes it `NOT NULL`.
- SQLAlchemy's `Date` and `DateTime` types store ISO strings in SQLite, so the file stays
  readable with the `sqlite3` CLI and you get real `date` objects in Python.
- `utcnow` is a small helper returning `datetime.now(UTC)`. Keep timestamps in UTC; the
  entry `date` is your local calendar day, which is what you want.
- Settings stay a key/value table for now, as in the requirements. Milestone 4 decides
  whether to keep that or switch to typed columns, which is a cheap migration either way.

### 4. Alembic setup

- [ ] `uv run alembic init src/tdee_calculator/migrations`. This creates `alembic.ini` at
      the repo root and the `migrations/` folder.
- [ ] In `alembic.ini`, delete the `sqlalchemy.url` line. The URL comes from `Config`.
- [ ] Edit `migrations/env.py`:
  - `target_metadata = Base.metadata` (import `Base` from `tdee_calculator.models`).
  - Get the URL from `config.get_main_option("sqlalchemy.url")`, falling back to
    `load_config().db_url` when it's not set. The app sets it explicitly; the CLI uses
    the fallback. In the fallback branch, call `ensure_dirs(load_config())` first:
    SQLite can't create a file inside a missing folder, and on a fresh clone `data/`
    doesn't exist yet when you run the autogenerate step below.
  - Pass `render_as_batch=True` to `context.configure(...)` in both the offline and
    online functions. SQLite can't `ALTER` most things in place, and batch mode makes
    Alembic rebuild the table instead. Without it, the first "change a column" migration fails.
- [ ] Generate the first migration:
      `uv run alembic revision --autogenerate -m "create entries and settings"`.
      Read the generated file before committing it. Autogenerate is a draft, not gospel.

From now on, the workflow for a schema change is: edit `models.py`, run
`alembic revision --autogenerate -m "..."`, review the file, commit both.

### 5. Database (`db.py`)

```python
def ensure_dirs(config: Config) -> None: ...
    # data_dir and backup_dir, mkdir(parents=True, exist_ok=True)

def make_engine(config: Config) -> Engine: ...
    # ensure_dirs(config); create_engine(config.db_url)

def run_migrations(config: Config) -> None: ...
    # ensure_dirs(config); builds an alembic Config in code (script_location from
    # Path(__file__), sqlalchemy.url from config.db_url), then command.upgrade(cfg, "head")

def backup(db_path: Path, backup_dir: Path, keep: int) -> Path | None: ...
    # no-op (returns None) if db_path doesn't exist yet; creates backup_dir itself

def prepare(config: Config) -> Path | None: ...
    # what main() runs before the server starts: ensure_dirs(), then backup()
```

**Folders first.** SQLite can't create a database file inside a folder that doesn't
exist. Every function that connects or writes a file calls `ensure_dirs()` (or, for
`backup()`, creates its own folder). `mkdir(exist_ok=True)` is cheap, so calling it more
than once is fine, and no function depends on another one having run first.

**Backup.** Use `sqlite3.Connection.backup()` from the standard library rather than
copying the file. It gives a consistent copy even if a write is in progress. Name files
`tdee-YYYYMMDD-HHMMSS-ffffff.db` (`%f` is microseconds) so two starts in the same second
don't overwrite each other and sorting by name is still sorting by age. Then delete
everything past the newest `keep`. This works on the file directly and doesn't need SQLAlchemy.

**Where the backup runs.** In `main()`, not in the app's lifespan. The lifespan runs
again on every auto-reload in the dev loop (`uvicorn --reload`), so a backup there would
write one per saved file and push your real backups out of the `keep` window. Running it
in `main()` means backups happen only when you launch the app with `./run.sh`. Because
`main()` runs before the server starts, the backup still happens before migrations.

### 6. App (`app.py`)

```python
def create_app(config: Config | None = None) -> FastAPI: ...

app = create_app()   # module-level, so `uvicorn tdee_calculator.app:app --reload` works
```

- **Lifespan** (runs at every server start, including reloads): `run_migrations()`, then
  `make_engine()` and a `sessionmaker`, stored on `app.state`. Dispose the engine on
  shutdown. Migrations stay here so the dev loop and `TestClient` always get an
  up-to-date schema; they skip work that's already done, so repeated runs are fast.
  The backup is *not* here (see task 5).
- **Session dependency**: `get_session()` yields a `Session` from `app.state`'s
  sessionmaker and closes it after the request. Routes take
  `session: Annotated[Session, Depends(get_session)]`. Milestone 3 reuses it.
- **Templates and static files**: resolve paths from `Path(__file__).parent` so they work
  no matter which directory the server is started from. Mount `static/` at `/static`.
- **`GET /`**: render `index.html` with the entry count
  (`session.scalar(select(func.count()).select_from(Entry))`). The page is a placeholder,
  but the count shows the whole path works: request, session, DB, template.

Templates: `base.html` has the `<html>` shell, a `<link>` to `/static/style.css`, and a
`{% block content %}`. `index.html` extends it with a heading and the count.

### 7. Entry point (`__init__.py` → `main()`)

`main()` is already wired up as the `tdee-calculator` script in `pyproject.toml`.

1. `config = load_config()`
2. `prepare(config)`: create folders, back up the existing DB.
3. Unless `TDEE_NO_BROWSER=1`, start a daemon thread that waits for the server and then
   opens the browser (below).
4. `uvicorn.run(create_app(config), host=config.host, port=config.port)`. Passing the
   app object (not an import string) guarantees the server uses the same `config`.

**Opening the browser when the server is ready.** A fixed delay is a guess: if
migrations or startup take longer, you land on a "can't connect" page. Instead, the
thread polls the URL with `urllib.request.urlopen(url, timeout=1)` every ~100 ms. On the
first successful response it calls `webbrowser.open(url)`. If nothing answers within
10 seconds, it prints the URL and gives up, so you can open it yourself.

Python's `webbrowser` module works on Linux, macOS, and Windows, so `run.sh` doesn't
need `xdg-open`.

### 8. `run.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"          # so data/ always lands in the repo, wherever it's run from

command -v uv >/dev/null || { echo "uv not found: https://docs.astral.sh/uv/"; exit 1; }
uv sync --quiet               # installs on first run, no-op after
exec uv run tdee-calculator
```

Then `chmod +x run.sh`. The backup happens in `main()` and migrations in the app's
lifespan, so the script stays this short.

### 9. Tests

`conftest.py` provides a `config` fixture with `data_dir = tmp_path / "data"`, so tests
never touch your real `data/`. Use the nested path, not `tmp_path` itself: pytest has
already created `tmp_path`, which would hide a "folder doesn't exist" bug.

`test_config.py`:

- [ ] With no `TDEE_*` variables set (`monkeypatch.delenv(..., raising=False)`),
      `load_config()` returns the defaults.
- [ ] With all four set (`monkeypatch.setenv`), it returns the overrides, with `port`
      and `backup_keep` as `int`s.

`test_db.py`:

- [ ] `run_migrations()` with a `data_dir` that doesn't exist yet creates the folder
      and the DB, with `entries` and `settings`
      (check with `sqlalchemy.inspect(engine).get_table_names()`).
- [ ] Running `run_migrations()` twice does nothing the second time.
- [ ] **Models match migrations:** after `run_migrations()`, Alembic's `command.check(cfg)`
      passes. This fails if you change `models.py` and forget to generate a migration.
- [ ] `backup()` returns `None` when the DB file doesn't exist.
- [ ] `backup()` creates `backup_dir` if it's missing and writes a readable copy that
      contains the original's rows.
- [ ] With `keep=3`, five real `backup()` calls in a row leave three files with
      distinct names. This checks both pruning and that fast calls don't collide.
- [ ] **Two starts:** `prepare()`, then `run_migrations()`, then `prepare()` again leaves
      exactly one backup. The first `prepare()` has no DB to back up yet.

`test_app.py`:

- [ ] Using `TestClient(create_app(config))` as a context manager (so the lifespan runs),
      `GET /` returns 200 and shows the count 0.
- [ ] After the client starts, the DB file exists in the temp data dir.

## Verify by hand

```zsh
uv run pytest
./run.sh                                   # browser opens, page shows 0 entries
ls data/ data/backups/                     # tdee.db; no backup yet on the first run
sqlite3 data/tdee.db .schema               # entries, settings, alembic_version
# Ctrl-C, then ./run.sh again
ls data/backups/                           # one backup now
TDEE_PORT=8123 TDEE_NO_BROWSER=1 ./run.sh  # serves on :8123, no browser
TDEE_DATA_DIR=$(mktemp -d)/fresh ./run.sh  # a data dir that doesn't exist yet still works
```

Dev loop with auto-reload:

```zsh
TDEE_NO_BROWSER=1 uv run uvicorn tdee_calculator.app:app --reload
# save a .py file a few times: the server reloads, and data/backups/ doesn't change
```

## Not in this milestone

- Entry, settings, or dashboard routes (milestones 3–5).
- Writing rows. Milestone 3 is the first to insert entries and exercise the timestamp defaults.
- Logging setup, error pages, or CSS beyond the basics.
- Auth or non-localhost hosting. The configurable host keeps that option open.

import sqlite3
from contextlib import closing
from datetime import date as Date
from datetime import datetime as DateTime
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import Engine, create_engine, update
from sqlalchemy.orm import Session

from tdee_calculator import clock
from tdee_calculator.config import Config
from tdee_calculator.models import Entry, MeasurementSession

MIGRATIONS_DIR = Path(__file__).with_name("migrations")


def ensure_dirs(config: Config) -> None:
    config.data_dir.mkdir(parents=True, exist_ok=True)
    config.backup_dir.mkdir(parents=True, exist_ok=True)


def make_engine(config: Config) -> Engine:
    ensure_dirs(config)
    return create_engine(config.db_url)


def make_alembic_config(config: Config) -> AlembicConfig:
    alembic_config = AlembicConfig()
    alembic_config.set_main_option("script_location", str(MIGRATIONS_DIR))
    alembic_config.set_main_option("sqlalchemy.url", config.db_url)
    return alembic_config


def run_migrations(config: Config) -> None:
    ensure_dirs(config)
    command.upgrade(make_alembic_config(config), "head")


def backup(db_path: Path, backup_dir: Path, keep: int) -> Path | None:
    if not db_path.exists():
        return None

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = clock.now().strftime("%Y%m%d-%H%M%S-%f")
    backup_path = backup_dir / f"tdee-{timestamp}.db"
    # Write under a name the pruning glob doesn't match, so a failed backup can never
    # count as one of the `keep` newest and push out a good backup.
    temp_path = backup_path.with_suffix(".db.tmp")

    try:
        with (
            closing(sqlite3.connect(db_path)) as source,
            closing(sqlite3.connect(temp_path)) as destination,
        ):
            source.backup(destination)
        temp_path.replace(backup_path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise

    backups = sorted(backup_dir.glob("tdee-*.db"), reverse=True)
    for old_backup in backups[keep:]:
        old_backup.unlink()

    return backup_path


def prepare(config: Config) -> Path | None:
    ensure_dirs(config)
    return backup(config.db_path, config.backup_dir, config.backup_keep)


def claim_version(
    session: Session,
    model: type[Entry] | type[MeasurementSession],
    day: Date,
    expected_version: str,
) -> bool:
    """Lock `day`'s row for this transaction if it is still `expected_version`.

    The no-op UPDATE matches only an unchanged row, and the write it starts holds
    SQLite's lock until commit, so no other save can land between check and write.
    """
    try:
        expected = DateTime.fromisoformat(expected_version)
    except ValueError:
        return False
    result = session.connection().execute(
        update(model)
        .where(model.date == day, model.updated_at == expected)
        .values(updated_at=model.updated_at)
    )
    return result.rowcount == 1

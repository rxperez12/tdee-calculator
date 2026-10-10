import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from tdee_calculator.db import (
    backup,
    make_alembic_config,
    make_engine,
    prepare,
    run_migrations,
)
from tdee_calculator.models import Entry, Setting

ALEMBIC_INI = Path(__file__).parents[1] / "alembic.ini"


def table_names(config) -> set[str]:
    engine = make_engine(config)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_run_migrations_creates_missing_data_directory_and_tables(config) -> None:
    assert not config.data_dir.exists()

    run_migrations(config)

    engine = make_engine(config)
    try:
        assert set(inspect(engine).get_table_names()) == {
            "alembic_version",
            "entries",
            "settings",
            "measurement_sessions",
            "measurement_readings",
        }
    finally:
        engine.dispose()


def test_run_migrations_is_idempotent(config) -> None:
    run_migrations(config)
    run_migrations(config)

    assert config.db_path.exists()


def test_models_match_migrations(config) -> None:
    run_migrations(config)

    command.check(make_alembic_config(config))


def test_migrations_downgrade_to_base_and_upgrade_again(config) -> None:
    run_migrations(config)
    alembic_config = make_alembic_config(config)

    command.downgrade(alembic_config, "base")
    assert table_names(config) == {"alembic_version"}

    command.upgrade(alembic_config, "head")
    assert table_names(config) == {
        "alembic_version",
        "entries",
        "settings",
        "measurement_sessions",
        "measurement_readings",
    }


def test_alembic_cli_config_migrates_database_from_environment(
    monkeypatch, config
) -> None:
    # alembic.ini's logging setup would replace pytest's handlers for later tests.
    logging_configs = []
    monkeypatch.setattr("logging.config.fileConfig", logging_configs.append)
    monkeypatch.setenv("TDEE_DATA_DIR", str(config.data_dir))

    command.upgrade(AlembicConfig(str(ALEMBIC_INI)), "head")

    assert logging_configs == [str(ALEMBIC_INI)]
    assert table_names(config) == {
        "alembic_version",
        "entries",
        "settings",
        "measurement_sessions",
        "measurement_readings",
    }


def test_measurements_migration_preserves_existing_entries_and_settings(config):
    engine = make_engine(config)
    try:
        command.upgrade(make_alembic_config(config), "61e68c996d17")
        with Session(engine) as session:
            session.add(Entry(date=date(2026, 10, 8), weight_kg=80.25, calories=2100))
            session.add(Setting(key="height_cm", value="180.5"))
            session.commit()
        run_migrations(config)
        with Session(engine) as session:
            row = session.get(Entry, date(2026, 10, 8))
            assert row.weight_kg == pytest.approx(80.25, abs=1e-9)
            assert row.calories == 2100
            assert session.get(Setting, "height_cm").value == "180.5"
        assert "measurement_readings" in table_names(config)
    finally:
        engine.dispose()


def test_offline_migrations_are_rejected(config) -> None:
    with pytest.raises(RuntimeError, match="Offline"):
        command.upgrade(make_alembic_config(config), "head", sql=True)


def test_backup_returns_none_when_database_is_missing(config) -> None:
    assert backup(config.db_path, config.backup_dir, config.backup_keep) is None


def test_backup_creates_directory_and_readable_copy(config) -> None:
    config.data_dir.mkdir(parents=True)
    with closing(sqlite3.connect(config.db_path)) as connection, connection:
        connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample VALUES ('original')")

    backup_path = backup(config.db_path, config.backup_dir, config.backup_keep)

    assert backup_path is not None
    assert backup_path.parent == config.backup_dir
    with closing(sqlite3.connect(backup_path)) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone() == (
            "original",
        )


def test_failed_backup_leaves_no_files(config) -> None:
    config.data_dir.mkdir(parents=True)
    config.db_path.write_bytes(b"not a sqlite database" * 100)

    with pytest.raises(sqlite3.DatabaseError):
        backup(config.db_path, config.backup_dir, config.backup_keep)

    assert list(config.backup_dir.iterdir()) == []


def test_backup_prunes_old_files_without_name_collisions(config) -> None:
    config.data_dir.mkdir(parents=True)
    with closing(sqlite3.connect(config.db_path)) as connection, connection:
        connection.execute("CREATE TABLE sample (value INTEGER NOT NULL)")

    created = [
        backup(config.db_path, config.backup_dir, config.backup_keep) for _ in range(5)
    ]
    backup_paths = sorted(config.backup_dir.glob("tdee-*.db"))

    assert all(path is not None for path in created)
    assert len(set(created)) == 5
    assert len(backup_paths) == config.backup_keep
    assert backup_paths == sorted(created)[-config.backup_keep :]


def test_prepare_backs_up_on_second_start(config) -> None:
    assert prepare(config) is None
    run_migrations(config)

    backup_path = prepare(config)

    assert backup_path is not None
    assert list(config.backup_dir.glob("tdee-*.db")) == [backup_path]

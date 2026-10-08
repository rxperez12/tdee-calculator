import sqlite3
from contextlib import closing

import pytest
from alembic import command
from sqlalchemy import inspect

from tdee_calculator.db import (
    backup,
    make_alembic_config,
    make_engine,
    prepare,
    run_migrations,
)


def test_run_migrations_creates_missing_data_directory_and_tables(config) -> None:
    assert not config.data_dir.exists()

    run_migrations(config)

    engine = make_engine(config)
    try:
        assert set(inspect(engine).get_table_names()) == {
            "alembic_version",
            "entries",
            "settings",
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

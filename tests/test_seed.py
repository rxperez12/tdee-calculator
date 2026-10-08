import importlib.util
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from tdee_calculator import clock
from tdee_calculator.config import Config
from tdee_calculator.db import make_engine
from tdee_calculator.models import Entry
from tdee_calculator.settings import load_settings

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "seed_dev_data.py"


@pytest.fixture
def seed(monkeypatch):
    spec = importlib.util.spec_from_file_location("seed_dev_data", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(clock, "today", lambda: date(2026, 10, 8))
    return module


def read(data_dir):
    config = Config(host="127.0.0.1", port=8000, data_dir=data_dir, backup_keep=3)
    engine = make_engine(config)
    try:
        with Session(engine) as session:
            rows = [
                (row.date, row.weight_kg, row.calories)
                for row in session.scalars(select(Entry).order_by(Entry.date))
            ]
            return rows, load_settings(session)
    finally:
        engine.dispose()


def test_refuses_the_real_data_directory(seed, tmp_path, monkeypatch):
    # Stand in a temp dir for the real one, so the test can't touch real data.
    protected = tmp_path / "data"
    monkeypatch.setattr(seed, "REAL_DATA_DIR", protected)
    assert seed.main(["--data-dir", str(protected)]) == 1
    assert not protected.exists()


def test_writes_deterministic_entries_and_settings(seed, tmp_path):
    first, second = tmp_path / "one", tmp_path / "two"
    assert seed.main(["--data-dir", str(first), "--with-settings"]) == 0
    assert seed.main(["--data-dir", str(second), "--with-settings"]) == 0
    rows, settings = read(first)
    assert (rows, settings) == read(second)
    assert rows[0][0] == date(2026, 6, 10)  # 120 days before today
    assert rows[-1][0] == date(2026, 10, 8)
    assert rows[-1][2] is None  # today's calories aren't in yet
    # 121 days minus the 5-day gap, minus days with neither value.
    assert 100 < len(rows) <= 116
    assert any(weight is None for _, weight, _ in rows)
    assert any(calories is None for _, _, calories in rows[:-1])
    assert settings.rate_kg_per_week == -0.5
    assert settings.goal_weight_kg is not None


def test_without_settings_leaves_defaults(seed, tmp_path):
    assert seed.main(["--data-dir", str(tmp_path), "--days", "30"]) == 0
    rows, settings = read(tmp_path)
    assert len(rows) <= 31
    assert settings.goal_weight_kg is None

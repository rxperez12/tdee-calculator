from dataclasses import replace
from datetime import date
from inspect import signature

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from tdee_calculator import calc
from tdee_calculator.db import make_engine, run_migrations
from tdee_calculator.models import Setting
from tdee_calculator.settings import Settings, load_settings, save_settings
from tdee_calculator.units import EnergyUnit, WeightUnit


@pytest.fixture
def engine(config):
    run_migrations(config)
    engine = make_engine(config)
    yield engine
    engine.dispose()


def test_empty_settings_and_calc_defaults(engine):
    with Session(engine) as session:
        assert load_settings(session) == Settings()
    defaults = signature(calc.logged_tdee).parameters
    assert Settings().tdee_window_days == defaults["window_days"].default
    assert Settings().energy_density == defaults["energy_density"].default


def test_persistence_and_optional_deletion(engine):
    settings = Settings(
        weight_unit=WeightUnit.LB,
        energy_unit=EnergyUnit.KJ,
        sex=calc.Sex.FEMALE,
        height_cm=177.8,
        birth_date=date(1990, 2, 3),
        activity=calc.ActivityLevel.MODERATE,
        goal_weight_kg=81.64662660,
        rate_kg_per_week=-0.5,
        tdee_window_days=35,
        energy_density=7716.17,
    )
    with Session(engine) as session:
        save_settings(session, settings)
    with Session(engine) as session:
        assert load_settings(session) == settings
        rows = {row.key: row.value for row in session.scalars(select(Setting))}
        assert rows["activity"] == "MODERATE"
        assert rows["goal_weight_kg"] == "81.6466266"
        save_settings(
            session,
            replace(
                settings,
                sex=None,
                height_cm=None,
                birth_date=None,
                activity=None,
                goal_weight_kg=None,
                rate_kg_per_week=None,
            ),
        )
    with Session(engine) as session:
        assert set(session.scalars(select(Setting.key))) == {
            "weight_unit",
            "energy_unit",
            "tdee_window_days",
            "energy_density",
        }
        loaded = load_settings(session)
        assert loaded.sex is None
        assert loaded.height_cm is None
        assert loaded.birth_date is None
        assert loaded.activity is None
        assert loaded.goal_weight_kg is None
        assert loaded.rate_kg_per_week is None


@pytest.mark.parametrize(
    "key",
    [
        "tdee_window_days",
        "weight_unit",
        "energy_unit",
        "sex",
        "activity",
        "birth_date",
        "height_cm",
        "goal_weight_kg",
        "rate_kg_per_week",
        "energy_density",
    ],
)
def test_corrupt_value_defaults(engine, key):
    with Session(engine) as session:
        session.add(Setting(key=key, value="abc"))
        session.commit()
        assert load_settings(session) == Settings()

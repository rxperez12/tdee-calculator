"""Typed settings over the existing key/value table."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date as Date

from sqlalchemy import select
from sqlalchemy.orm import Session

from tdee_calculator.calc import ActivityLevel, Sex
from tdee_calculator.models import Setting
from tdee_calculator.units import EnergyUnit, WeightUnit


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
    energy_density: float = 7700


def _read[T](
    rows: dict[str, str], key: str, parse: Callable[[str], T], default: T
) -> T:
    if key not in rows:
        return default
    try:
        return parse(rows[key])
    except (ValueError, KeyError):
        return default


def load_settings(session: Session) -> Settings:
    rows = {row.key: row.value for row in session.scalars(select(Setting))}
    defaults = Settings()
    return Settings(
        weight_unit=_read(rows, "weight_unit", WeightUnit, defaults.weight_unit),
        energy_unit=_read(rows, "energy_unit", EnergyUnit, defaults.energy_unit),
        sex=_read(rows, "sex", Sex, None),
        height_cm=_read(rows, "height_cm", float, None),
        birth_date=_read(rows, "birth_date", Date.fromisoformat, None),
        activity=_read(rows, "activity", lambda value: ActivityLevel[value], None),
        goal_weight_kg=_read(rows, "goal_weight_kg", float, None),
        rate_kg_per_week=_read(rows, "rate_kg_per_week", float, None),
        tdee_window_days=_read(
            rows, "tdee_window_days", int, defaults.tdee_window_days
        ),
        energy_density=_read(rows, "energy_density", float, defaults.energy_density),
    )


def save_settings(session: Session, settings: Settings) -> None:
    values = {
        "weight_unit": settings.weight_unit.value,
        "energy_unit": settings.energy_unit.value,
        "sex": settings.sex.value if settings.sex is not None else None,
        "height_cm": repr(settings.height_cm)
        if settings.height_cm is not None
        else None,
        "birth_date": settings.birth_date.isoformat()
        if settings.birth_date is not None
        else None,
        "activity": settings.activity.name if settings.activity is not None else None,
        "goal_weight_kg": repr(settings.goal_weight_kg)
        if settings.goal_weight_kg is not None
        else None,
        "rate_kg_per_week": repr(settings.rate_kg_per_week)
        if settings.rate_kg_per_week is not None
        else None,
        "tdee_window_days": repr(settings.tdee_window_days),
        "energy_density": repr(settings.energy_density),
    }
    for key, value in values.items():
        row = session.get(Setting, key)
        if value is None:
            if row is not None:
                session.delete(row)
        elif row is None:
            session.add(Setting(key=key, value=value))
        else:
            row.value = value
    session.commit()

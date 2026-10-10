"""Shared web pieces: templates, filters, and request dependencies."""

from collections.abc import Iterator
from datetime import date as Date
from functools import partial
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, sessionmaker

from tdee_calculator.settings import Settings, load_settings
from tdee_calculator.settings_form import SettingsValues
from tdee_calculator.units import (
    WeightUnit,
    format_density,
    format_energy,
    format_energy_display,
    format_rate,
    format_weight,
)

PACKAGE_DIR = Path(__file__).parent


def short_date(day: Date, today: Date) -> str:
    """'Thu 8 Oct', with the year added when it isn't the current one."""
    text = f"{day:%a} {day.day} {day:%b}"
    return text if day.year == today.year else f"{text} {day.year}"


def change_phrase(kg_per_week: float, unit: WeightUnit, ongoing: bool = False) -> str:
    """A signed rate in words: 'lose 0.50 kg a week', or 'losing ...' when ongoing."""
    amount = format_rate(abs(kg_per_week), unit)
    if amount == format_rate(0, unit):
        return "holding steady" if ongoing else "maintain your weight"
    if kg_per_week < 0:
        verb = "losing" if ongoing else "lose"
    else:
        verb = "gaining" if ongoing else "gain"
    return f"{verb} {amount} {unit.value} a week"


def requested_day(text: str | None, today: Date) -> Date:
    """The `?date=` a page should load: today when missing or invalid, never later."""
    try:
        day = Date.fromisoformat(text or "")
    except ValueError:
        return today
    return min(day, today)


def is_state(value: object, name: str) -> bool:
    """Jinja test for the dashboard's state dataclasses: `x is state("Target")`."""
    return type(value).__name__ == name


templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")
templates.env.filters.update(
    weight=format_weight,
    energy=format_energy,
    rate=format_rate,
    density=format_density,
    energy_display=format_energy_display,
    intake_display=partial(format_energy_display, round_up=True),
    short_date=short_date,
    change=change_phrase,
)
templates.env.tests["state"] = is_state

STALE_UNITS_NOTICE = (
    "Your units changed since this page loaded. Nothing was saved. "
    "Check the values and submit again."
)


def get_session(request: Request) -> Iterator[Session]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:
        yield session


SessionDependency = Annotated[Session, Depends(get_session)]


def current_settings(session: SessionDependency) -> Settings:
    return load_settings(session)


SettingsDependency = Annotated[Settings, Depends(current_settings)]


async def get_form_values(request: Request) -> SettingsValues:
    return {
        key: value
        for key, value in (await request.form()).items()
        if isinstance(value, str)
    }


FormDependency = Annotated[SettingsValues, Depends(get_form_values)]


def units_match(values: dict[str, str], settings: Settings) -> bool:
    return (
        weight_unit_matches(values, settings)
        and values.get("energy_unit") == settings.energy_unit.value
    )


def weight_unit_matches(values: dict[str, str], settings: Settings) -> bool:
    return values.get("weight_unit") == settings.weight_unit.value

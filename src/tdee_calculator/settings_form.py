"""Settings form formatting and validation in the selected display units."""

import math
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date as Date

from tdee_calculator.calc import ActivityLevel, Sex, age_on
from tdee_calculator.entry_form import MAX_WEIGHT_KG, MIN_WEIGHT_KG
from tdee_calculator.settings import Settings
from tdee_calculator.units import (
    EnergyUnit,
    WeightUnit,
    cm_to_feet_inches,
    density_to_kcal_per_kg,
    feet_inches_to_cm,
    format_density,
    format_rate,
    format_weight,
    matching_bound,
    weight_to_kg,
)

SettingsValues = dict[str, str]
MIN_HEIGHT_CM = 100
MAX_HEIGHT_CM = 250
MIN_RATE = -1.5
MAX_RATE = 1.0
MIN_WINDOW = 14
MAX_WINDOW = 56
MIN_DENSITY = 4000
MAX_DENSITY = 9500

ACTIVITY_LABELS = {
    ActivityLevel.SEDENTARY: "Sedentary (little or no exercise)",
    ActivityLevel.LIGHT: "Light (exercise 1-3 days a week)",
    ActivityLevel.MODERATE: "Moderate (exercise 3-5 days a week)",
    ActivityLevel.VERY: "Very active (exercise 6-7 days a week)",
    ActivityLevel.EXTRA: "Extra active (physical job or intense daily exercise)",
}


@dataclass(frozen=True)
class SettingsFormErrors:
    errors: dict[str, str]


def settings_to_form(settings: Settings) -> SettingsValues:
    weight, energy = settings.weight_unit, settings.energy_unit
    feet, inches = cm_to_feet_inches(settings.height_cm or 0)
    defaults = Settings()
    return {
        "weight_unit": weight.value,
        "energy_unit": energy.value,
        "sex": settings.sex.value if settings.sex is not None else "",
        "activity": settings.activity.name if settings.activity is not None else "",
        "height_cm": f"{settings.height_cm:.0f}"
        if settings.height_cm is not None
        else "",
        "height_ft": str(feet) if settings.height_cm is not None else "",
        "height_in": f"{inches:.1f}" if settings.height_cm is not None else "",
        "birth_date": settings.birth_date.isoformat()
        if settings.birth_date is not None
        else "",
        "goal_weight": format_weight(settings.goal_weight_kg, weight)
        if settings.goal_weight_kg is not None
        else "",
        "rate_per_week": format_rate(settings.rate_kg_per_week, weight)
        if settings.rate_kg_per_week is not None
        else "",
        "tdee_window_days": str(settings.tdee_window_days)
        if settings.tdee_window_days != defaults.tdee_window_days
        else "",
        "energy_density": format_density(settings.energy_density, weight, energy)
        if settings.energy_density != defaults.energy_density
        else "",
    }


def _number(
    text: str,
    key: str,
    label: str,
    lower: float,
    upper: float,
    convert: Callable[[float], float],
    formatter: Callable[[float], str],
    errors: dict[str, str],
) -> float | None:
    try:
        value = float(text)
    except ValueError:
        errors[key] = f"Enter a number for {label}."
        return None
    bound = matching_bound(value, lower, upper, formatter)
    canonical = bound if bound is not None else convert(value)
    if not math.isfinite(canonical) or not lower <= canonical <= upper:
        errors[key] = (
            f"{label.capitalize()} must be between "
            f"{formatter(lower)} and {formatter(upper)}."
        )
        return None
    return canonical


def _optional_number(
    text: str,
    current: float | None,
    rendered: str,
    key: str,
    label: str,
    lower: float,
    upper: float,
    convert: Callable[[float], float],
    formatter: Callable[[float], str],
    errors: dict[str, str],
) -> float | None:
    if text == rendered:
        return current
    if not text:
        return None
    return _number(text, key, label, lower, upper, convert, formatter, errors)


def format_height(cm: float, weight: WeightUnit) -> str:
    if weight is WeightUnit.KG:
        return f"{cm:.0f} cm"
    feet, inches = cm_to_feet_inches(cm)
    return f"{feet} ft {inches:g} in"


def _height(
    form: SettingsValues,
    current: Settings,
    rendered: SettingsValues,
    errors: dict[str, str],
) -> float | None:
    if current.weight_unit is WeightUnit.KG:
        return _optional_number(
            form.get("height_cm", ""),
            current.height_cm,
            rendered["height_cm"],
            "height_cm",
            "height (cm)",
            MIN_HEIGHT_CM,
            MAX_HEIGHT_CM,
            lambda value: value,
            lambda cm: f"{cm:.0f}",
            errors,
        )
    feet_text, inches_text = form.get("height_ft", ""), form.get("height_in", "")
    if (feet_text, inches_text) == (rendered["height_ft"], rendered["height_in"]):
        return current.height_cm
    if not feet_text and not inches_text:
        return None
    try:
        feet, inches = int(feet_text), float(inches_text)
    except ValueError:
        errors["height"] = "Enter both feet and inches for height."
        return None
    if not 3 <= feet <= 8 or not 0 <= inches < 12:
        errors["height"] = (
            "Feet must be between 3 and 8; inches must be at least 0 and less than 12."
        )
        return None
    # Match the displayed height bounds using total inches, then store cm.
    bound = matching_bound(
        feet * 12 + inches,
        MIN_HEIGHT_CM,
        MAX_HEIGHT_CM,
        lambda cm: str(_height_inches(cm)),
    )
    cm = bound if bound is not None else feet_inches_to_cm(feet, inches)
    if not MIN_HEIGHT_CM <= cm <= MAX_HEIGHT_CM:
        errors["height"] = (
            "Height must be between "
            f"{format_height(MIN_HEIGHT_CM, current.weight_unit)} and "
            f"{format_height(MAX_HEIGHT_CM, current.weight_unit)}."
        )
        return None
    return cm


def _height_inches(cm: float) -> float:
    feet, inches = cm_to_feet_inches(cm)
    return feet * 12 + inches


def parse_settings_form(
    form: SettingsValues, current: Settings, today: Date
) -> Settings | SettingsFormErrors:
    form = {key: value.strip() for key, value in form.items()}
    rendered = settings_to_form(current)
    errors: dict[str, str] = {}
    sex: Sex | None = None
    activity: ActivityLevel | None = None
    birth_date: Date | None = None
    if form.get("sex"):
        try:
            sex = Sex(form["sex"])
        except ValueError:
            errors["sex"] = "Choose one of the sex options."
    if form.get("activity"):
        try:
            activity = ActivityLevel[form["activity"]]
        except KeyError:
            errors["activity"] = "Choose one of the activity options."
    birth_text = form.get("birth_date", "")
    if birth_text == rendered["birth_date"]:
        birth_date = current.birth_date
    elif birth_text:
        try:
            birth_date = Date.fromisoformat(birth_text)
            age = age_on(birth_date, today)
        except ValueError:
            errors["birth_date"] = "Enter a valid birth date that is not in the future."
        else:
            if not 15 <= age <= 100:
                errors["birth_date"] = "Age must be between 15 and 100."
    height = _height(form, current, rendered, errors)
    weight, energy = current.weight_unit, current.energy_unit
    goal = _optional_number(
        form.get("goal_weight", ""),
        current.goal_weight_kg,
        rendered["goal_weight"],
        "goal_weight",
        f"goal weight ({weight.value})",
        MIN_WEIGHT_KG,
        MAX_WEIGHT_KG,
        lambda value: weight_to_kg(value, weight),
        lambda kg: format_weight(kg, weight),
        errors,
    )
    rate = _optional_number(
        form.get("rate_per_week", ""),
        current.rate_kg_per_week,
        rendered["rate_per_week"],
        "rate_per_week",
        f"rate ({weight.value}/week)",
        MIN_RATE,
        MAX_RATE,
        lambda value: weight_to_kg(value, weight),
        lambda kg: format_rate(kg, weight),
        errors,
    )
    defaults = Settings()
    window = defaults.tdee_window_days
    if form.get("tdee_window_days"):
        try:
            window = int(form["tdee_window_days"])
        except ValueError:
            errors["tdee_window_days"] = "Enter a whole number of days."
        else:
            if not MIN_WINDOW <= window <= MAX_WINDOW:
                errors["tdee_window_days"] = (
                    f"Window must be between {MIN_WINDOW} and {MAX_WINDOW} days."
                )
    density_text = form.get("energy_density", "")
    density: float | None = defaults.energy_density
    if density_text == rendered["energy_density"]:
        density = current.energy_density
    elif density_text:
        density = _number(
            density_text,
            "energy_density",
            f"energy density ({energy.value}/{weight.value})",
            MIN_DENSITY,
            MAX_DENSITY,
            lambda value: density_to_kcal_per_kg(value, weight, energy),
            lambda value: format_density(value, weight, energy),
            errors,
        )
    if errors:
        return SettingsFormErrors(errors)
    assert density is not None
    return replace(
        current,
        sex=sex,
        activity=activity,
        birth_date=birth_date,
        height_cm=height,
        goal_weight_kg=goal,
        rate_kg_per_week=rate,
        tdee_window_days=window,
        energy_density=density,
    )


def parse_units_form(
    form: SettingsValues, current: Settings
) -> Settings | SettingsFormErrors:
    errors: dict[str, str] = {}
    weight, energy = current.weight_unit, current.energy_unit
    try:
        weight = WeightUnit(form.get("weight_unit", ""))
    except ValueError:
        errors["weight_unit"] = "Choose kg or lb."
    try:
        energy = EnergyUnit(form.get("energy_unit", ""))
    except ValueError:
        errors["energy_unit"] = "Choose kcal or kJ."
    if errors:
        return SettingsFormErrors(errors)
    return replace(current, weight_unit=weight, energy_unit=energy)

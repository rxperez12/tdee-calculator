from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date as Date
from typing import TYPE_CHECKING

from tdee_calculator.units import (
    MAX_WEIGHT_KG,
    MIN_WEIGHT_KG,
    EnergyUnit,
    WeightUnit,
    energy_from_kcal,
    energy_to_kcal,
    format_energy,
    format_weight,
    matching_bound,
    weight_to_kg,
)

if TYPE_CHECKING:
    from tdee_calculator.models import Entry

MIN_CALORIES = 0
MAX_CALORIES = 20_000


@dataclass(frozen=True)
class EntryInput:
    date: Date
    weight_kg: float | None
    calories: int | None


@dataclass(frozen=True)
class EntryFormErrors:
    errors: dict[str, str]


def parse_entry_form(
    date_text: str,
    weight_text: str,
    calories_text: str,
    today: Date,
    weight_unit: WeightUnit = WeightUnit.KG,
    energy_unit: EnergyUnit = EnergyUnit.KCAL,
    current: Entry | None = None,
) -> EntryInput | EntryFormErrors:
    date_text, weight_text, calories_text = (
        date_text.strip(),
        weight_text.strip(),
        calories_text.strip(),
    )
    errors: dict[str, str] = {}
    entry_date: Date | None = None
    weight: float | None = None
    calories: int | None = None
    try:
        entry_date = Date.fromisoformat(date_text)
    except ValueError:
        errors["date"] = "Enter a valid date."
    else:
        if entry_date > today:
            errors["date"] = "Date cannot be in the future."

    if (
        current is not None
        and current.weight_kg is not None
        and weight_text == format_weight(current.weight_kg, weight_unit)
    ):
        weight = current.weight_kg
    elif weight_text:
        try:
            parsed_weight = float(weight_text)
        except ValueError:
            errors["weight"] = "Enter a number for weight."
        else:
            bound = matching_bound(
                parsed_weight,
                MIN_WEIGHT_KG,
                MAX_WEIGHT_KG,
                lambda kg: format_weight(kg, weight_unit),
            )
            weight = (
                bound if bound is not None else weight_to_kg(parsed_weight, weight_unit)
            )
            if (
                not math.isfinite(weight)
                or not MIN_WEIGHT_KG <= weight <= MAX_WEIGHT_KG
            ):
                errors["weight"] = (
                    "Weight must be between "
                    f"{format_weight(MIN_WEIGHT_KG, weight_unit)} and "
                    f"{format_weight(MAX_WEIGHT_KG, weight_unit)} {weight_unit.value}."
                )
    if (
        current is not None
        and current.calories is not None
        and calories_text == format_energy(current.calories, energy_unit)
    ):
        calories = current.calories
    elif calories_text:
        try:
            parsed_energy = int(calories_text)
        except ValueError:
            errors["calories"] = "Enter a whole number for calories."
        else:
            if (
                not energy_from_kcal(MIN_CALORIES, energy_unit)
                <= parsed_energy
                <= energy_from_kcal(MAX_CALORIES, energy_unit)
            ):
                errors["calories"] = (
                    "Calories must be between "
                    f"{format_energy(MIN_CALORIES, energy_unit)} and "
                    f"{format_energy(MAX_CALORIES, energy_unit)} {energy_unit.value}."
                )
            else:
                calories = round(energy_to_kcal(parsed_energy, energy_unit))
    if not weight_text and not calories_text:
        errors["form"] = "Enter weight or calories, or both."
    if errors:
        return EntryFormErrors(errors)
    assert entry_date is not None
    return EntryInput(entry_date, weight, calories)

import math
from dataclasses import dataclass
from datetime import date as Date

MIN_WEIGHT_KG = 20
MAX_WEIGHT_KG = 400
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
    date_text: str, weight_text: str, calories_text: str, today: Date
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

    if weight_text:
        try:
            weight = float(weight_text)
        except ValueError:
            errors["weight_kg"] = "Enter a number for weight."
        else:
            if (
                not math.isfinite(weight)
                or not MIN_WEIGHT_KG <= weight <= MAX_WEIGHT_KG
            ):
                errors["weight_kg"] = (
                    f"Weight must be between {MIN_WEIGHT_KG} and {MAX_WEIGHT_KG} kg."
                )
    if calories_text:
        try:
            calories = int(calories_text)
        except ValueError:
            errors["calories"] = "Enter a whole number for calories."
        else:
            if not MIN_CALORIES <= calories <= MAX_CALORIES:
                errors["calories"] = (
                    f"Calories must be between {MIN_CALORIES:,} "
                    f"and {MAX_CALORIES:,} kcal."
                )
    if not weight_text and not calories_text:
        errors["form"] = "Enter weight or calories, or both."
    if errors:
        return EntryFormErrors(errors)
    assert entry_date is not None
    return EntryInput(entry_date, weight, calories)

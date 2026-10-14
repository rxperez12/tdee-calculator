"""Measurement form validation and preservation of unchanged raw readings."""

import math
from dataclasses import dataclass
from datetime import date as Date

from tdee_calculator.calc import Site
from tdee_calculator.models import MeasurementSession
from tdee_calculator.units import (
    WeightUnit,
    format_length,
    length_to_cm,
    length_unit_for,
    matching_bound,
)

SITE_LABELS = {
    Site.NECK: "Neck",
    Site.ABDOMEN: "Abdomen (navel)",
    Site.WAIST: "Waist (narrowest point)",
    Site.HIP: "Hips",
}
READING_LIMITS = {
    Site.NECK: (20, 80),
    Site.ABDOMEN: (40, 250),
    Site.WAIST: (40, 250),
    Site.HIP: (50, 250),
}


@dataclass(frozen=True)
class MeasurementInput:
    date: Date
    readings: dict[Site, tuple[float, ...]]


@dataclass(frozen=True)
class MeasurementFormErrors:
    errors: dict[str, str]


def parse_measurement_form(
    form: dict[str, str],
    today: Date,
    weight_unit: WeightUnit,
    current: MeasurementSession | None = None,
) -> MeasurementInput | MeasurementFormErrors:
    errors: dict[str, str] = {}
    measurement_date: Date | None = None
    try:
        measurement_date = Date.fromisoformat(form.get("date", "").strip())
    except ValueError:
        errors["date"] = "Enter a valid date."
    else:
        if measurement_date > today:
            errors["date"] = "Date cannot be in the future."
    unit = length_unit_for(weight_unit)
    existing = (
        {(row.site, row.reading): row.value_cm for row in current.readings}
        if current is not None
        else {}
    )
    readings: dict[Site, tuple[float, ...]] = {}
    for site in Site:
        values: list[float] = []
        lower, upper = READING_LIMITS[site]
        for slot in range(1, 4):
            field = f"{site.value}_{slot}"
            text = form.get(field, "").strip()
            if not text:
                continue
            stored = existing.get((site.value, slot))
            if stored is not None and text == format_length(stored, unit):
                values.append(stored)
                continue
            try:
                number = float(text)
            except ValueError:
                errors[field] = "Enter a number."
                continue
            bound = matching_bound(
                number, lower, upper, lambda cm: format_length(cm, unit)
            )
            value = bound if bound is not None else length_to_cm(number, unit)
            if not math.isfinite(value) or not lower <= value <= upper:
                errors[field] = (
                    f"{SITE_LABELS[site]} must be between "
                    f"{format_length(lower, unit)} and "
                    f"{format_length(upper, unit)} {unit.value}."
                )
            else:
                values.append(value)
        if values:
            readings[site] = tuple(values)
    if not readings and not errors:
        errors["form"] = "Enter at least one reading."
    if errors:
        return MeasurementFormErrors(errors)
    assert measurement_date is not None
    return MeasurementInput(measurement_date, readings)

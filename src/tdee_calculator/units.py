"""Pure conversions between stored kg/kcal and display units."""

from collections.abc import Callable
from enum import StrEnum
from math import ceil

KG_PER_LB = 0.45359237
KJ_PER_KCAL = 4.184
CM_PER_INCH = 2.54
DISPLAY_STEP = {"kcal": 10, "kJ": 50}


class WeightUnit(StrEnum):
    KG = "kg"
    LB = "lb"


class LengthUnit(StrEnum):
    CM = "cm"
    IN = "in"


def length_unit_for(weight: WeightUnit) -> LengthUnit:
    return LengthUnit.IN if weight is WeightUnit.LB else LengthUnit.CM


def length_to_cm(value: float, unit: LengthUnit) -> float:
    return value * CM_PER_INCH if unit is LengthUnit.IN else value


def length_from_cm(cm: float, unit: LengthUnit) -> float:
    return cm / CM_PER_INCH if unit is LengthUnit.IN else cm


def format_length(cm: float, unit: LengthUnit) -> str:
    return f"{length_from_cm(cm, unit):.1f}"


class EnergyUnit(StrEnum):
    KCAL = "kcal"
    KJ = "kJ"


def weight_to_kg(value: float, unit: WeightUnit) -> float:
    return value * KG_PER_LB if unit is WeightUnit.LB else value


def weight_from_kg(kg: float, unit: WeightUnit) -> float:
    return kg / KG_PER_LB if unit is WeightUnit.LB else kg


def energy_to_kcal(value: float, unit: EnergyUnit) -> float:
    return value / KJ_PER_KCAL if unit is EnergyUnit.KJ else value


def energy_from_kcal(kcal: float, unit: EnergyUnit) -> float:
    return kcal * KJ_PER_KCAL if unit is EnergyUnit.KJ else kcal


def density_to_kcal_per_kg(
    value: float, weight: WeightUnit, energy: EnergyUnit
) -> float:
    return energy_to_kcal(value, energy) / weight_to_kg(1, weight)


def density_from_kcal_per_kg(
    kcal_per_kg: float, weight: WeightUnit, energy: EnergyUnit
) -> float:
    return energy_from_kcal(kcal_per_kg, energy) * weight_to_kg(1, weight)


def feet_inches_to_cm(feet: int, inches: float) -> float:
    return (feet * 12 + inches) * CM_PER_INCH


def cm_to_feet_inches(cm: float) -> tuple[int, float]:
    half_inches = round(cm / CM_PER_INCH * 2)
    feet, remaining = divmod(half_inches, 24)
    return feet, remaining / 2


def format_weight(kg: float, unit: WeightUnit) -> str:
    return f"{weight_from_kg(kg, unit):.1f}"


def format_rate(kg_per_week: float, unit: WeightUnit) -> str:
    return f"{weight_from_kg(kg_per_week, unit):.2f}"


def format_energy(kcal: float, unit: EnergyUnit) -> str:
    return f"{energy_from_kcal(kcal, unit):.0f}"


def format_density(kcal_per_kg: float, weight: WeightUnit, energy: EnergyUnit) -> str:
    return f"{density_from_kcal_per_kg(kcal_per_kg, weight, energy):.0f}"


def format_energy_display(
    kcal: float, unit: EnergyUnit, *, round_up: bool = False
) -> str:
    """Display-only energy in steps of 10 kcal or 50 kJ, with thousands separators.

    Rounding up keeps a displayed target from dropping below a displayed floor.
    """
    step = DISPLAY_STEP[unit.value]
    value = energy_from_kcal(kcal, unit)
    # Six places absorbs float noise, e.g. 2000.0000000000002 must not show as 2,010.
    steps = ceil(round(value, 6) / step) if round_up else round(value / step)
    return f"{steps * step:,}"


def matching_bound(
    value: float, lower: float, upper: float, formatter: Callable[[float], str]
) -> float | None:
    """Recognize a displayed bound numerically, without a tolerance band."""
    for bound in (lower, upper):
        if value == float(formatter(bound)):
            return bound
    return None

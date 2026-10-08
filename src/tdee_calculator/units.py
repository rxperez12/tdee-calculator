"""Pure conversions between stored kg/kcal and display units."""

from collections.abc import Callable
from enum import StrEnum

KG_PER_LB = 0.45359237
KJ_PER_KCAL = 4.184
CM_PER_INCH = 2.54


class WeightUnit(StrEnum):
    KG = "kg"
    LB = "lb"


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


def matching_bound(
    value: float, lower: float, upper: float, formatter: Callable[[float], str]
) -> float | None:
    """Recognize a displayed bound numerically, without a tolerance band."""
    for bound in (lower, upper):
        if value == float(formatter(bound)):
            return bound
    return None

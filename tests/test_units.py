import pytest

from tdee_calculator.units import (
    EnergyUnit,
    WeightUnit,
    cm_to_feet_inches,
    density_from_kcal_per_kg,
    density_to_kcal_per_kg,
    energy_from_kcal,
    energy_to_kcal,
    feet_inches_to_cm,
    format_density,
    format_energy,
    format_energy_display,
    format_rate,
    format_weight,
    matching_bound,
    weight_from_kg,
    weight_to_kg,
)


def test_known_conversions():
    assert weight_to_kg(1, WeightUnit.LB) == 0.45359237
    assert weight_from_kg(100, WeightUnit.LB) == pytest.approx(220.462, abs=0.001)
    assert energy_from_kcal(2000, EnergyUnit.KJ) == 8368
    assert energy_to_kcal(8368, EnergyUnit.KJ) == 2000
    assert density_to_kcal_per_kg(
        3500, WeightUnit.LB, EnergyUnit.KCAL
    ) == pytest.approx(7716.17, abs=0.01)
    assert density_from_kcal_per_kg(
        7700, WeightUnit.LB, EnergyUnit.KCAL
    ) == pytest.approx(3492.66, abs=0.01)
    assert density_from_kcal_per_kg(
        7700, WeightUnit.KG, EnergyUnit.KJ
    ) == pytest.approx(32216.8, abs=1e-9)
    assert density_from_kcal_per_kg(
        7700, WeightUnit.LB, EnergyUnit.KJ
    ) == pytest.approx(14613.294665816, abs=1e-9)


@pytest.mark.parametrize("weight", list(WeightUnit))
@pytest.mark.parametrize("energy", list(EnergyUnit))
def test_conversion_round_trips(weight, energy):
    assert weight_to_kg(weight_from_kg(81.7, weight), weight) == pytest.approx(
        81.7, abs=1e-9
    )
    assert energy_to_kcal(energy_from_kcal(2137, energy), energy) == pytest.approx(
        2137, abs=1e-9
    )
    assert density_to_kcal_per_kg(
        density_from_kcal_per_kg(7700, weight, energy), weight, energy
    ) == pytest.approx(7700, abs=1e-9)


def test_height_and_carry():
    assert feet_inches_to_cm(5, 10) == pytest.approx(177.8, abs=1e-9)
    assert cm_to_feet_inches(177.8) == (5, 10)
    assert cm_to_feet_inches(182.8) == (6, 0)
    assert feet_inches_to_cm(*cm_to_feet_inches(182.8)) == pytest.approx(
        182.88, abs=1e-9
    )


@pytest.mark.parametrize("cm", [100, 101.5, 160, 177.8, 182.8, 250])
def test_rounded_height_precision(cm):
    assert feet_inches_to_cm(*cm_to_feet_inches(cm)) == pytest.approx(cm, abs=0.635)


def test_formatting():
    assert format_weight(81.7, WeightUnit.LB) == "180.1"
    assert format_rate(-0.5, WeightUnit.LB) == "-1.10"
    assert format_energy(2000, EnergyUnit.KJ) == "8368"
    assert format_density(7700, WeightUnit.LB, EnergyUnit.KCAL) == "3493"


@pytest.mark.parametrize("value", [-3.31, 2.20])
def test_numeric_bound_matches(value):
    assert matching_bound(
        value, -1.5, 1, lambda kg: format_rate(kg, WeightUnit.LB)
    ) == (-1.5 if value < 0 else 1)


def test_bound_matching_has_no_tolerance():
    assert (
        matching_bound(-3.308, -1.5, 1, lambda kg: format_rate(kg, WeightUnit.LB))
        is None
    )
    assert (
        matching_bound(44.05, 20, 400, lambda kg: format_weight(kg, WeightUnit.LB))
        is None
    )
    assert (
        matching_bound(
            1814,
            4000,
            9500,
            lambda density: format_density(density, WeightUnit.LB, EnergyUnit.KCAL),
        )
        == 4000
    )


def test_energy_display_rounds_to_steps_with_separators():
    assert format_energy_display(1947, EnergyUnit.KCAL) == "1,950"
    assert format_energy_display(950, EnergyUnit.KCAL) == "950"
    # 2,000 kcal is 8,368 kJ, nearest 50 kJ step.
    assert format_energy_display(2000, EnergyUnit.KJ) == "8,350"
    assert format_energy_display(-203, EnergyUnit.KCAL) == "-200"


def test_energy_display_rounding_up_never_shows_less():
    assert format_energy_display(1200, EnergyUnit.KCAL, round_up=True) == "1,200"
    assert format_energy_display(1201, EnergyUnit.KCAL, round_up=True) == "1,210"
    # 1,200 kcal is 5,020.8 kJ: the nearest step would show 5,000 (about 1,195 kcal).
    assert format_energy_display(1200, EnergyUnit.KJ) == "5,000"
    assert format_energy_display(1200, EnergyUnit.KJ, round_up=True) == "5,050"
    assert (
        format_energy_display(2000.0000000000002, EnergyUnit.KCAL, round_up=True)
        == "2,000"
    )

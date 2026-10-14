"""Home measurement summary and suggested cadence, with dates passed in."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date as Date
from datetime import timedelta
from typing import Literal

from tdee_calculator.body_fat import MeasurementRow, build_summary
from tdee_calculator.models import MeasurementSession
from tdee_calculator.settings import Settings


@dataclass(frozen=True)
class MeasurementDashboard:
    newest: MeasurementRow | None
    latest: MeasurementRow | None
    next_suggested: Date | None
    cadence: Literal["future", "today", "past"] | None


def build_measurement_dashboard(
    sessions: Sequence[MeasurementSession], settings: Settings, today: Date
) -> MeasurementDashboard:
    """Compose the existing summary; sessions arrive newest first."""
    summary = build_summary(sessions, settings)
    if not summary.rows:
        return MeasurementDashboard(None, None, None, None)
    newest = summary.rows[0]
    next_suggested = newest.date + timedelta(days=7)
    cadence: Literal["future", "today", "past"] = "future"
    if next_suggested == today:
        cadence = "today"
    elif next_suggested < today:
        cadence = "past"
    return MeasurementDashboard(newest, summary.latest, next_suggested, cadence)

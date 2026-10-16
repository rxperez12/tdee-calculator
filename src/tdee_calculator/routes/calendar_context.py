"""One homepage workspace context shared by navigation and both save routes."""

from dataclasses import dataclass, replace
from datetime import date as Date
from typing import Annotated
from urllib.parse import urlencode

from fastapi import Depends, Request

from tdee_calculator import clock
from tdee_calculator.dashboard import Range, parse_range
from tdee_calculator.logging_calendar import stat_options
from tdee_calculator.web import SettingsDependency, requested_day


@dataclass(frozen=True)
class Workspace:
    day: Date
    month: Date
    stats: tuple[str, ...]
    measurements_open: bool
    chart_range: Range
    today: Date

    def url(
        self,
        *,
        day: Date | None = None,
        month: Date | None = None,
        measurements_open: bool | None = None,
        chart_range: Range | None = None,
        saved: bool = False,
        measurement_saved: bool = False,
        fragment: str = "selected-day",
    ) -> str:
        selected = day if day is not None else self.day
        visible = (
            month if month is not None else selected if day is not None else self.month
        )
        opened = (
            self.measurements_open if measurements_open is None else measurements_open
        )
        params = [
            ("date", selected.isoformat()),
            ("month", visible.isoformat()[:7]),
            ("range", chart_range or self.chart_range),
            ("selection", "1"),
            *(("stat", stat) for stat in self.stats),
        ]
        if opened:
            params.append(("measurements", "open"))
        if saved:
            params.append(("saved", selected.isoformat()))
        if measurement_saved:
            params.append(("circumference_saved", selected.isoformat()))
        return "/?" + urlencode(params) + ("#" + fragment if fragment else "")

    def for_day(self, day: Date) -> "Workspace":
        return replace(self, day=day)


async def workspace_context(
    request: Request, settings: SettingsDependency
) -> Workspace:
    source = await request.form() if request.method == "POST" else request.query_params
    values = {key: value for key, value in source.items() if isinstance(value, str)}
    today = clock.today()
    day_text = (
        values.get("entry_date")
        if request.url.path == "/entries"
        else values.get("date")
    )
    legacy = request.method == "GET" and "circumference_date" in values
    if legacy:
        day_text = values["circumference_date"]
    day = requested_day(day_text, today)
    if request.method == "POST":
        try:
            submitted = Date.fromisoformat(day_text or "")
        except ValueError:
            submitted = None
        if submitted is None or submitted > today:
            day = requested_day(values.get("loaded_date"), today)
    month_text = values.get("month", "")
    try:
        month = Date.fromisoformat(month_text + "-01")
        if month.isoformat()[:7] != month_text:
            raise ValueError("Month must be YYYY-MM")
    except ValueError:
        month = day.replace(day=1)
    explicit = "selection" in values or "stat" in source
    requested = source.getlist("stat") if explicit else ["weight", "calories"]
    stats = tuple(
        option.key for option in stat_options(settings) if option.key in requested
    )
    return Workspace(
        day,
        month,
        stats,
        values.get("measurements") == "open"
        or legacy
        or "circumference_saved" in values,
        parse_range(values.get("range")),
        today,
    )


WorkspaceDependency = Annotated[Workspace, Depends(workspace_context)]

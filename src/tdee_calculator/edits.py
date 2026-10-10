"""Rules for saving a dated form safely when other tabs may have saved since.

A form records the date it loaded and that row's version. Saving is refused when it
would overwrite a different date's row, or a row that changed after the form loaded.
"""

from datetime import date as Date
from datetime import datetime as DateTime
from typing import Literal, Protocol

EditConflict = Literal["conflict", "stale"]


class Versioned(Protocol):
    @property
    def updated_at(self) -> DateTime: ...


def row_version(row: Versioned | None) -> str:
    return "" if row is None else row.updated_at.isoformat()


def edit_conflict(
    saved_date: Date,
    loaded_date_text: str,
    loaded_version: str,
    current: Versioned | None,
) -> EditConflict | None:
    """Why saving to `saved_date` must be refused, or None when it's safe.

    `current` is the row stored for `saved_date` now. "conflict": the form loaded
    another date (or none) and would overwrite this one. "stale": the form loaded
    this date, but the row was saved, created, or deleted since.
    """
    try:
        loaded = Date.fromisoformat(loaded_date_text)
    except ValueError:
        loaded = None
    if saved_date != loaded:
        return "conflict" if current is not None else None
    return "stale" if loaded_version != row_version(current) else None

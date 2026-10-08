"""The app's only source of the current date and time.

The app runs locally, so the computer's clock and time zone are treated as correct.
Every timestamp is a naive local datetime, matching what SQLite stores and returns.
"""

from datetime import date, datetime


def now() -> datetime:
    return datetime.now()


def today() -> date:
    return date.today()

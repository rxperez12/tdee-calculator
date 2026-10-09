"""Lossless entry exports in stored kg/kcal units.

Current application inputs are dates, numbers, timestamps, and fixed source values.
If user-provided text (including notes or sources) is added, revisit spreadsheet
formula injection for cells starting with =, +, -, or @ before exporting it.
"""

import csv
import io
from collections.abc import Iterable

from tdee_calculator.models import Entry

CSV_COLUMNS = (
    "date",
    "weight_kg",
    "calories_kcal",
    "source",
    "created_at",
    "updated_at",
)


def entries_csv(entries: Iterable[Entry]) -> str:
    """Entries as RFC 4180 CSV text with a header row, in the order given."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(CSV_COLUMNS)
    for entry in entries:
        writer.writerow(
            (
                entry.date.isoformat(),
                entry.weight_kg,
                entry.calories,
                entry.source,
                entry.created_at.isoformat(),
                entry.updated_at.isoformat(),
            )
        )
    return output.getvalue()

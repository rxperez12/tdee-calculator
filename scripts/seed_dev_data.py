"""Write deterministic fake entries to a dev data directory, never the real one.

uv run scripts/seed_dev_data.py --data-dir /tmp/tdee-dev [--days 120] [--with-settings]
TDEE_DATA_DIR=/tmp/tdee-dev ./run.sh
"""

import argparse
import random
import sys
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from tdee_calculator import clock
from tdee_calculator.calc import ActivityLevel, Sex
from tdee_calculator.config import Config
from tdee_calculator.db import make_engine, run_migrations
from tdee_calculator.entries import upsert_entry
from tdee_calculator.entry_form import EntryInput
from tdee_calculator.settings import Settings, save_settings

REAL_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TDEE = 2550
DENSITY = 7700
# Long runs alternate cutting and regaining, so weights stay realistic for any --days.
CUT_UNTIL_KG = 75.0
REGAIN_UNTIL_KG = 86.0
GAP_DAYS_AGO = range(40, 45)  # one 5-day gap with no entries at all


def fake_entries(days: int, today: date) -> list[EntryInput]:
    """About 0.4 kg/week of loss with daily noise and the usual missing days.

    Below 75 kg it regains about 0.27 kg/week until 86 kg, then cuts again.
    """
    rng = random.Random(42)
    weight = REGAIN_UNTIL_KG
    cutting = True
    entries = []
    for offset in range(days, -1, -1):
        day = today - timedelta(days=offset)
        if cutting and weight < CUT_UNTIL_KG:
            cutting = False
        elif not cutting and weight > REGAIN_UNTIL_KG:
            cutting = True
        intake = round(rng.gauss(2110 if cutting else 2850, 150))
        measured = round(weight + rng.uniform(-0.6, 0.6), 1)
        skip_weight = rng.random() < 0.1
        skip_calories = rng.random() < 1 / 15
        weight += (intake - TDEE) / DENSITY
        if offset in GAP_DAYS_AGO or (skip_weight and skip_calories):
            continue
        entries.append(
            EntryInput(
                day,
                None if skip_weight else measured,
                None if skip_calories or offset == 0 else intake,
            )
        )
    return entries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--with-settings", action="store_true")
    args = parser.parse_args(argv)

    data_dir: Path = args.data_dir.resolve()
    # Resolve both sides at run time: data/ may be a symlink to the real store.
    if data_dir.is_relative_to(REAL_DATA_DIR.resolve()):
        print(f"Refusing to seed the real data directory: {data_dir}", file=sys.stderr)
        return 1

    config = Config(host="127.0.0.1", port=8000, data_dir=data_dir, backup_keep=3)
    run_migrations(config)
    engine = make_engine(config)
    entries = fake_entries(args.days, clock.today())
    try:
        with Session(engine) as session:
            for entry in entries:
                upsert_entry(session, entry)
            if args.with_settings:
                latest = next(e.weight_kg for e in reversed(entries) if e.weight_kg)
                save_settings(
                    session,
                    Settings(
                        sex=Sex.FEMALE,
                        height_cm=168.0,
                        birth_date=date(1990, 5, 14),
                        activity=ActivityLevel.MODERATE,
                        goal_weight_kg=round(latest - 6),
                        rate_kg_per_week=-0.5,
                    ),
                )
    finally:
        engine.dispose()
    print(f"Wrote {len(entries)} entries to {config.db_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

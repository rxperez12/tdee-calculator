# Project standards

- `./run.sh` starts the app; `./check.sh` runs formatting, lint, strict types,
  and tests with branch coverage. It must pass before work is called done.
- Use `uv add` for dependencies and include the resulting `uv.lock` changes.
  Do not use `pip install`. Checks use locked dependencies locally and in CI.
- Milestones live in `docs/roadmap.md`; implementation plans live in `docs/plans/`.

## Architecture and data

- `calc.py` is pure and imports only the standard library. Pass dates in.
- Store and calculate in kg/kcal; convert units only at input/display boundaries.
- Read the current date/time only through `clock.py`.
- Keep SQLite-specific SQL in `db.py` in application code. Schema changes require
  an Alembic migration; tests may use SQL to arrange and verify temporary databases.
- Never read or write the real `data/` directory during agent work or tests.
  Use `tmp_path` in tests and a separate `TDEE_DATA_DIR` for manual checks.

## Code and tests

- Ruff owns Python formatting and lint rules in `pyproject.toml`.
- Annotate all functions in `src/`; strict mypy checks application and migration code.
- Suppressions must name a code and give a short reason, e.g.
  `# type: ignore[arg-type]  # reason`. Fix errors instead of hiding them with `Any`.
- Follow [the testing standards](docs/testing.md). Test observable behavior with
  independently established expected answers, not copied implementation formulas.
- Integration tests use real app/database layers. Mock outside boundaries only,
  except focused orchestration tests that record the order of internal steps.
- Keep tests deterministic and isolated; bug fixes include a failing regression test.

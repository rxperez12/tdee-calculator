# Testing standards

Run `./check.sh` before calling work done. It checks formatting, lint, strict source
types, and the full pytest suite with branch coverage using `uv.lock`.

For a focused iteration, use `uv run --locked pytest tests/test_calc.py`, or
`uv run --locked pytest tests/test_db.py -k backup`. Run the full gate before handoff.

## Required coverage

| Change | Required coverage |
| --- | --- |
| Calculations and unit conversions | Independently established answers, boundaries, missing data, invalid inputs, and `pytest.approx` with an explicit tolerance justified by the expected precision |
| Database behavior | Real SQLite in `tmp_path`; verify saved values, constraints, updates, and rollback where relevant |
| Routes and forms | `TestClient` through the real database layer; verify the response and persisted state for mutations |
| Migrations | Upgrade from empty, agreement between models and migrations, and preservation of existing data when the schema changes |
| JavaScript behavior | Focused browser checks when a feature depends on JavaScript; browser automation is deferred until then |

## Rules for every test

- Test observable behavior. Mock outside boundaries, such as browser opening or the
  clock when it cannot be passed in. Integration tests use real app/database layers.
- When the order of steps is the behavior under test, a focused unit test may
  replace internal steps with recorders. `test_main.py` verifies that `prepare`
  backs up before the server starts; migrations run in the application's lifespan.
- Use fixed dates and isolated fixtures. Never read or write the real `data/`
  directory. Tests must work independently of execution order and wall-clock timing.
- Bug fixes include a regression test that fails without the fix.
- Establish expected values separately from the implementation. Use worked answers
  or synthetic scenarios with known outcomes, as in `test_calc.py`. Do not simply
  repeat the implementation's formula in an assertion.
- New or modified floating-point assertions state their tolerance explicitly;
  existing numerical expectations are preserved during standards-only refactors.
- Rejection tests verify the intended failure, including the relevant argument in
  the error message where needed to avoid catching an unrelated exception.
- No snapshot tests. Assert the specific values and behavior that matter.

## Coverage

`uv run --locked pytest --cov` reports missing statements and branches.
The threshold is recorded in `pyproject.toml` and set from the measured baseline.
At adoption, the 130-test baseline was 98.60%; after adding browser fallback/startup
coverage, 132 tests reached 99.72%. The minimum is 98%.
Investigate gaps for meaningful behavior and failure paths; an aggregate percentage
does not replace the scenarios above. Do not lower the threshold or exclude behavior
just to make a check pass. Any exclusion needs a specific reason and review.

## Milestone 3

The entry workflow must include real-database route tests for creating an entry,
updating an existing date without duplication, deleting an entry, and rejecting
invalid submissions without changing stored data.

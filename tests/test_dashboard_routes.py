import json
import re
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session
from test_app import save
from test_dashboard import linear_logs

from tdee_calculator.calc import DayLog, Sex
from tdee_calculator.db import make_engine
from tdee_calculator.models import Entry
from tdee_calculator.settings import Settings, save_settings
from tdee_calculator.units import EnergyUnit, WeightUnit

TODAY = date(2026, 10, 8)


def seed(config, logs, settings=None):
    engine = make_engine(config)
    try:
        with Session(engine) as session:
            session.add_all(
                Entry(date=log.date, weight_kg=log.weight_kg, calories=log.calories)
                for log in logs
            )
            session.commit()
            if settings is not None:
                save_settings(session, settings)
    finally:
        engine.dispose()


def section(html, heading_id):
    """Text of the <section> labelled by heading_id, tags stripped."""
    start = html.index(f'id="{heading_id}"')
    body = html[start : html.index("</section>", start)]
    return " ".join(re.sub(r"<[^>]+>", " ", body.split(">", 1)[1]).split())


def chart_data(html):
    match = re.search(
        r'<script type="application/json" id="chart-data">(.*?)</script>', html
    )
    assert match is not None
    return json.loads(match.group(1))


def test_empty_database_shows_onboarding_only(client):
    page = client.get("/").text
    assert "Log your first weigh-in to get started" in page
    assert 'id="tdee-heading"' not in page
    assert 'id="chart"' not in page
    assert "chart.umd.min.js" not in page


def test_logged_tdee_and_target(client, config):
    seed(config, linear_logs(), Settings(rate_kg_per_week=-0.5))
    page = client.get("/").text
    tdee = section(page, "tdee-heading")
    assert "2,550 kcal" in tdee
    assert "From your logs" in tdee
    assert "28 logged, 0 estimated" in tdee
    hero = section(page, "hero-heading")
    assert "2,000 kcal today" in hero
    assert "to lose 0.50 kg a week" in hero
    assert "Losing 0.50 kg a week" in section(page, "trend-heading")


def test_units_convert_and_targets_round_up(client, config):
    settings = Settings(
        weight_unit=WeightUnit.LB, energy_unit=EnergyUnit.KJ, rate_kg_per_week=-0.5
    )
    seed(config, linear_logs(), settings)
    before = client.get("/history").text
    page = client.get("/").text
    # TDEE 2,550 kcal = 10,669 kJ, nearest 50: 10,650. The 2,000 kcal target is
    # 8,368 kJ, rounded up: 8,400.
    assert "10,650 kJ" in section(page, "tdee-heading")
    assert "8,400 kJ today" in section(page, "hero-heading")
    assert " lb" in section(page, "trend-heading")
    assert chart_data(page)["unit"] == "lb"
    assert client.get("/history").text == before


def test_rate_away_from_goal(client, config):
    seed(config, linear_logs(), Settings(goal_weight_kg=90, rate_kg_per_week=-0.5))
    goal = section(client.get("/").text, "goal-heading")
    assert "Your rate moves away from your goal" in goal
    assert 'href="/settings"' in client.get("/").text
    assert "if you keep this rate" not in goal


def test_goal_on_track(client, config):
    seed(config, linear_logs(), Settings(goal_weight_kg=70, rate_kg_per_week=-0.5))
    page = client.get("/").text
    assert "if you keep this rate" in section(page, "goal-heading")
    assert len(chart_data(page)["projection"]) == 2
    assert "Projected" in page


def test_stale_weigh_in(client, config):
    seed(config, [DayLog(TODAY - timedelta(days=5), 80.0, 2000)])
    trend = section(client.get("/").text, "trend-heading")
    assert "Last weigh-in Sat 3 Oct (5 days ago)" in trend


def test_floor_hides_unsafe_target_in_kilojoules(client, config):
    settings = Settings(
        sex=Sex.FEMALE,
        energy_unit=EnergyUnit.KJ,
        goal_weight_kg=70,
        rate_kg_per_week=-1.5,
    )
    seed(config, linear_logs(), settings)
    page = client.get("/").text
    hero = section(page, "hero-heading")
    # 2,550 - 1.5 * 1,100 = 900 kcal (3,766 kJ): never shown.
    assert "3,750" not in page
    assert "3,800" not in page
    # 1,200 kcal = 5,020.8 kJ, rounded up so it never reads below the floor.
    assert "under 5,050 kJ a day" in hero
    # (1,200 - 2,550) * 7 / 7,700 = -1.227..., truncated to 1.22.
    assert "fastest loss that stays at or above that is 1.22 kg a week" in hero
    assert "guardrail, not medical advice" in hero
    assert "See the note above" in section(page, "goal-heading")
    assert chart_data(page)["projection"] == []


def test_negative_estimate_is_never_shown(client, config):
    seed(config, linear_logs(kg_per_week=2.0), Settings(rate_kg_per_week=-0.5))
    page = client.get("/").text
    assert "doesn't look right" in section(page, "hero-heading")
    assert "-200" not in page
    assert "\N{MINUS SIGN}200" not in page
    assert "Eat about" not in page


def test_tiny_rate_does_not_crash(client, config):
    seed(
        config,
        [DayLog(TODAY, 80.0, None)],
        Settings(goal_weight_kg=75, rate_kg_per_week=-0.00001),
    )
    response = client.get("/")
    assert response.status_code == 200
    assert "More than 10 years away" in section(response.text, "goal-heading")


def test_calorie_only_entries(client, config):
    seed(config, [DayLog(TODAY - timedelta(days=d), None, 2000) for d in range(5)])
    page = client.get("/").text
    assert "Log a weigh-in to start your estimate" in page
    assert "No weigh-ins yet" in page
    assert 'id="weight-chart"' not in page


def test_formula_line_and_missing_stats(client, config):
    seed(config, [DayLog(TODAY, 70.0, None)])
    assert (
        "Add sex, height, birth date, activity level in Settings"
        in client.get("/").text
    )


def test_invalid_post_still_renders_dashboard(client, config):
    seed(config, linear_logs(end=TODAY - timedelta(days=1)))
    response = save(client, {"weight_unit": "kg", "energy_unit": "kcal"})
    assert response.status_code == 422
    assert 'id="tdee-heading"' in response.text


@pytest.mark.parametrize(
    "query,start",
    [("?range=4w", "2026-09-10"), ("?range=bogus", "2026-07-09"), ("", "2026-07-09")],
)
def test_range_selects_chart_window(client, config, query, start):
    seed(config, linear_logs(120))
    page = client.get(f"/{query}").text
    data = chart_data(page)
    assert data["start"] == start
    rows = page[page.index("<tbody>", page.index("chart-table")) :]
    rows = rows[: rows.index("</tbody>")]
    assert rows.count("<tr>") == len(data["weighIns"])
    assert rows.index("Thu 8 Oct") < rows.index("Wed 7 Oct")  # newest first


def test_range_links(client, config):
    seed(config, linear_logs())
    page = client.get("/?range=4w").text
    assert re.search(r'href="/\?range=4w#chart"\s+aria-current="true"', page)
    assert 'href="/?range=all#chart"' in page
    edit = client.get("/?date=2026-10-01").text
    assert 'href="/?range=all&amp;date=2026-10-01#chart"' in edit


def test_caption_and_json_escaping(client, config):
    seed(config, linear_logs(), Settings(goal_weight_kg=70, rate_kg_per_week=-0.5))
    page = client.get("/?range=4w").text
    caption = page[page.index("<figcaption>") : page.index("</figcaption>")]
    assert "Trend " in caption
    assert "over the last 4 weeks" in caption
    assert "Goal 70.0 kg." in caption
    raw = page[
        page.index('id="chart-data">') : page.index(
            "</script>", page.index('id="chart-data">')
        )
    ]
    assert "<" not in raw.split(">", 1)[1]


def test_range_without_weigh_ins(client, config):
    seed(config, [DayLog(TODAY - timedelta(days=120), 80.0, None)])
    page = client.get("/").text
    assert "No weigh-ins in the last 3 months." in page
    assert 'href="/?range=all#chart">Show all' in page
    assert "80.0 kg" in section(page, "trend-heading")
    assert 'id="weight-chart"' in client.get("/?range=all").text


@pytest.mark.parametrize(
    "path",
    [
        "/static/vendor/chart.umd.min.js",
        "/static/vendor/chartjs-adapter-date-fns.bundle.min.js",
        "/static/dashboard.js",
    ],
)
def test_chart_scripts_are_served(client, path):
    assert client.get(path).status_code == 200

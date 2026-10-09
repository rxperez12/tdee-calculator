import json
import re
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session
from test_app import save
from test_dashboard import linear_logs

from tdee_calculator.calc import ActivityLevel, DayLog, Sex
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
    assert "Log your first weigh-in." in page
    assert 'id="tdee-heading"' not in page
    assert 'id="chart"' not in page
    assert "chart.umd.min.js" not in page


def test_daily_table_includes_calorie_only_days(client, config):
    seed(
        config,
        [
            DayLog(TODAY - timedelta(days=2), 80.0, None),
            DayLog(TODAY - timedelta(days=1), None, 0),
            DayLog(TODAY, 80.0, 2100),
        ],
    )
    page = client.get("/?range=4w").text
    table = page[page.index('<details class="chart-table">') :]
    assert table.count("<tr>") == 4  # header plus all three logged dates
    assert "Show daily log as a table" in table
    assert "Calories (kcal)" in table
    assert (
        table.index("Thu 8 Oct") < table.index("Wed 7 Oct") < table.index("Tue 6 Oct")
    )
    assert 'href="/?date=2026-10-07&amp;range=4w"' in table
    assert table.count('class="number">—</td>') == 3
    assert 'class="number">0</td>' in table


def test_calorie_only_range_has_table_without_chart(client, config):
    seed(config, [DayLog(TODAY, None, 2100)])
    page = client.get("/?range=4w").text
    assert "No weigh-ins yet" in page
    assert "Show daily log as a table" in page
    assert 'class="number">2100</td>' in page
    assert 'id="weight-chart"' not in page
    assert "chart.umd.min.js" not in page


def test_daily_table_uses_display_units_and_edit_loads_row(client, config):
    seed(
        config,
        [DayLog(TODAY, 80.0, 2000)],
        Settings(weight_unit=WeightUnit.LB, energy_unit=EnergyUnit.KJ),
    )
    page = client.get("/?range=4w").text
    table = page[page.index('<details class="chart-table">') :]
    assert "Weight (lb)" in table
    assert "Calories (kJ)" in table
    assert 'class="number">176.4</td>' in table
    assert 'class="number">8368</td>' in table
    link = re.search(r'href="([^\"]+)" aria-label="Edit', table)
    assert link is not None
    edit = client.get(link.group(1).replace("&amp;", "&")).text
    assert "Logging Thu 8 Oct" in edit
    assert 'name="range" value="4w"' in edit


def test_daily_table_empty_range_and_old_weigh_in_with_recent_calories(client, config):
    seed(config, [DayLog(TODAY - timedelta(days=120), 80.0, None)])
    page = client.get("/?range=4w").text
    assert "No logs in the last 4 weeks" in page
    assert '<details class="chart-table">' not in page
    seed(config, [DayLog(TODAY, None, 2100)])
    page = client.get("/?range=4w&date=2026-10-01").text
    assert "No weigh-ins in the last 4 weeks" in page
    assert 'href="/?range=all&amp;date=2026-10-01#chart"' in page
    assert "Show daily log as a table" in page
    assert 'class="number">2100</td>' in page


def test_logged_tdee_and_target(client, config):
    seed(config, linear_logs(), Settings(rate_kg_per_week=-0.5))
    page = client.get("/").text
    tdee = section(page, "tdee-heading")
    assert "2,550 kcal" in tdee
    assert "From logs · 28/28 days logged" in tdee
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
    assert "your target rate points away" in goal
    assert "Away from goal" in goal
    assert 'href="/settings"' in client.get("/").text
    assert "if you keep this rate" not in goal


def test_goal_on_track(client, config):
    seed(config, linear_logs(), Settings(goal_weight_kg=70, rate_kg_per_week=-0.5))
    page = client.get("/").text
    assert "at target rate" in section(page, "goal-heading")
    assert len(chart_data(page)["projection"]) == 2
    assert "Projected" in page


def test_stale_weigh_in(client, config):
    seed(config, [DayLog(TODAY - timedelta(days=5), 80.0, 2000)])
    trend = section(client.get("/").text, "trend-heading")
    assert "Last weighed 5 days ago" in trend


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
    assert "eating under 5,050 kJ" in hero
    # (1,200 - 2,550) * 7 / 7,700 = -1.227..., truncated to 1.22.
    assert "Try 1.22 kg/week or slower" in hero
    assert "A guardrail, not medical advice." in hero
    assert "see the note above" in section(page, "goal-heading")
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
    assert "10+ years at this rate" in section(response.text, "goal-heading")


def test_calorie_only_entries(client, config):
    seed(config, [DayLog(TODAY - timedelta(days=d), None, 2000) for d in range(5)])
    page = client.get("/").text
    assert "Log a weigh-in to start your estimate" in page
    assert "No weigh-ins yet" in page
    assert 'id="weight-chart"' not in page


def test_missing_body_stats_link(client, config):
    seed(config, [DayLog(TODAY, 70.0, None)])
    tdee = section(client.get("/").text, "tdee-heading")
    assert "Add body stats for an estimate now" in tdee


def test_formula_shown_beside_a_logged_estimate(client, config):
    body = Settings(
        sex=Sex.FEMALE,
        height_cm=165.0,
        birth_date=date(1990, 10, 8),
        activity=ActivityLevel.MODERATE,
    )
    seed(config, linear_logs(), body)
    assert "Formula:" in section(client.get("/").text, "tdee-heading")


def test_invalid_post_still_renders_dashboard(client, config):
    seed(config, linear_logs(end=TODAY - timedelta(days=1)))
    response = save(client, {"weight_unit": "kg", "energy_unit": "kcal"})
    assert response.status_code == 422
    assert 'id="tdee-heading"' in response.text


@pytest.mark.parametrize(
    "query,start",
    [("?range=4w", "2026-09-09"), ("?range=bogus", "2026-07-08"), ("", "2026-07-08")],
)
def test_range_selects_chart_window(client, config, query, start):
    # The axis starts a day of room before the first weigh-in in range.
    seed(config, linear_logs(120))
    page = client.get(f"/{query}").text
    data = chart_data(page)
    assert data["start"] == start
    rows = page[page.index("<tbody>", page.index("chart-table")) :]
    rows = rows[: rows.index("</tbody>")]
    assert rows.count("<tr>") == (29 if query == "?range=4w" else 92)
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
    caption = page[page.index("<figcaption") : page.index("</figcaption>")]
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


def test_one_day_of_data_is_marked_early(client, config):
    body = Settings(
        sex=Sex.FEMALE,
        height_cm=165.0,
        birth_date=date(1990, 10, 8),
        activity=ActivityLevel.MODERATE,
        rate_kg_per_week=-0.5,
    )
    seed(config, [DayLog(TODAY, 70.0, None)], body)
    page = client.get("/").text
    assert "Early" in section(page, "tdee-heading")
    assert "Early" in section(page, "hero-heading")
    trend = section(page, "trend-heading")
    assert "Early" in trend
    assert "1/10 weigh-ins" in section(page, "tdee-heading")
    # The chart axis starts a week (plus a day of room) back, not 3 months back.
    assert chart_data(page)["start"] == "2026-09-30"
    assert "One weigh-in so far: 70.0 kg on Thu 8 Oct." in page


def test_settled_estimate_and_trend_are_not_marked_early(client, config):
    seed(config, linear_logs(), Settings(rate_kg_per_week=-0.5))
    page = client.get("/").text
    assert "Early" not in page


def test_goal_shows_direction(client, config):
    seed(config, linear_logs(), Settings(goal_weight_kg=70, rate_kg_per_week=-0.5))
    goal = section(client.get("/").text, "goal-heading")
    assert "Toward goal" in goal
    assert 'class="badge good"' in goal_html(client)


def test_goal_direction_waits_for_enough_data(client, config):
    seed(config, [DayLog(TODAY, 80.0, None)], Settings(goal_weight_kg=70))
    goal = section(client.get("/").text, "goal-heading")
    # One weigh-in: no rate yet, so no direction badge at all.
    assert "10.0 kg to go" in goal
    assert "badge" not in goal_html(client)


def test_caption_says_since_when_data_is_shorter_than_range(client, config):
    seed(config, linear_logs(14))
    page = client.get("/").text
    caption = page[page.index("<figcaption") : page.index("</figcaption>")]
    assert "since Thu 24 Sep" in caption


def goal_html(client):
    page = client.get("/").text
    start = page.index('id="goal-heading"')
    return page[start : page.index("</section>", start)]

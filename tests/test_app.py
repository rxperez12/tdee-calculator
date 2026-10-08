from fastapi.testclient import TestClient

from tdee_calculator.app import create_app


def test_home_page_shows_zero_entries(config) -> None:
    with TestClient(create_app(config)) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "0 entries" in response.text


def test_app_startup_creates_database(config) -> None:
    assert not config.data_dir.exists()

    with TestClient(create_app(config)):
        pass

    assert config.db_path.exists()

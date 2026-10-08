from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tdee_calculator import clock
from tdee_calculator.app import create_app
from tdee_calculator.config import Config


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(
        host="127.0.0.1",
        port=8000,
        data_dir=tmp_path / "data",
        backup_keep=3,
    )


@pytest.fixture
def client(config: Config, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(clock, "today", lambda: date(2026, 10, 8))
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 10, 8, 8))
    with TestClient(create_app(config), base_url="http://127.0.0.1:8000") as client:
        yield client

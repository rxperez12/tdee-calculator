from pathlib import Path

import pytest

from tdee_calculator.config import Config


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(
        host="127.0.0.1",
        port=8000,
        data_dir=tmp_path / "data",
        backup_keep=3,
    )

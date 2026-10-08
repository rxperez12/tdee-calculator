from pathlib import Path

from tdee_calculator.config import load_config


ENV_VARS = (
    "TDEE_HOST",
    "TDEE_PORT",
    "TDEE_DATA_DIR",
    "TDEE_BACKUP_KEEP",
)


def test_load_config_uses_defaults(monkeypatch) -> None:
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    config = load_config()

    assert config.host == "127.0.0.1"
    assert config.port == 8000
    assert config.data_dir == Path("data")
    assert config.backup_keep == 10


def test_load_config_reads_environment_overrides(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "custom-data"
    monkeypatch.setenv("TDEE_HOST", "0.0.0.0")
    monkeypatch.setenv("TDEE_PORT", "8123")
    monkeypatch.setenv("TDEE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("TDEE_BACKUP_KEEP", "4")

    config = load_config()

    assert config.host == "0.0.0.0"
    assert config.port == 8123
    assert config.data_dir == data_dir
    assert config.backup_keep == 4
    assert config.db_path == data_dir / "tdee.db"
    assert config.backup_dir == data_dir / "backups"
    assert config.db_url == f"sqlite:///{data_dir / 'tdee.db'}"

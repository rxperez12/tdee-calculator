import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    data_dir: Path
    backup_keep: int

    @property
    def db_path(self) -> Path:
        return self.data_dir / "tdee.db"

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backups"


def load_config() -> Config:
    return Config(
        host=os.environ.get("TDEE_HOST", "127.0.0.1"),
        port=int(os.environ.get("TDEE_PORT", "8000")),
        data_dir=Path(os.environ.get("TDEE_DATA_DIR", "data")),
        backup_keep=int(os.environ.get("TDEE_BACKUP_KEEP", "10")),
    )

"""Environment-based configuration for the LEYRA cloud core."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    control_token: str
    database_path: str
    database_url: str
    redis_url: str
    environment: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            control_token=os.getenv("LEYRA_CONTROL_TOKEN", "").strip(),
            database_path=os.getenv("LEYRA_DATABASE_PATH", "/data/leyra.sqlite3").strip(),
            database_url=os.getenv("LEYRA_DATABASE_URL", "").strip(),
            redis_url=os.getenv("LEYRA_REDIS_URL", "").strip(),
            environment=os.getenv("LEYRA_ENV", "production").strip().lower(),
        )


def ensure_data_directory(settings: Settings) -> None:
    if not settings.database_url.startswith(("postgres://", "postgresql://")):
        Path(settings.database_path).expanduser().parent.mkdir(parents=True, exist_ok=True)

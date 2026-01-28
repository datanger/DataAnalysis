from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    db_path: Path
    provider_order: tuple[str, ...]
    tushare_token: str | None

    # Task runner
    max_workers: int


def load_config() -> AppConfig:
    root = Path(os.getenv("WORKBENCH_ROOT", Path.cwd()))
    data_dir = Path(os.getenv("WORKBENCH_DATA_DIR", root / "data"))

    # Default: keep it local and simple.
    db_path = Path(os.getenv("WORKBENCH_DB_PATH", data_dir / "workbench.db"))

    provider_order = tuple(
        p.strip()
        for p in os.getenv("WORKBENCH_PROVIDER_ORDER", "tushare,akshare").split(",")
        if p.strip()
    )

    tushare_token = os.getenv("TUSHARE_TOKEN")

    max_workers = int(os.getenv("WORKBENCH_MAX_WORKERS", "4"))

    return AppConfig(
        db_path=db_path,
        provider_order=provider_order,
        tushare_token=tushare_token,
        max_workers=max_workers,
    )

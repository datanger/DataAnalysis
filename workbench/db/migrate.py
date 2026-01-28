from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        );
        """
    )


def _applied_versions(conn: sqlite3.Connection) -> set[int]:
    _ensure_migrations_table(conn)
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {int(r[0]) for r in rows}


def load_migrations(migrations_dir: Path) -> list[Migration]:
    migrations: list[Migration] = []
    for path in sorted(migrations_dir.glob("*.sql")):
        prefix = path.name.split("_", 1)[0]
        version = int(prefix)
        migrations.append(
            Migration(version=version, name=path.name, sql=path.read_text(encoding="utf-8"))
        )
    return migrations


def apply_migrations(conn: sqlite3.Connection, migrations_dir: Path) -> None:
    migrations = load_migrations(migrations_dir)
    applied = _applied_versions(conn)

    for m in migrations:
        if m.version in applied:
            continue
        with conn:
            conn.executescript(m.sql)
            conn.execute(
                "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, datetime('now'))",
                (m.version, m.name),
            )

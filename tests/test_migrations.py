from __future__ import annotations

from pathlib import Path

from workbench.db.conn import connect
from workbench.db.migrate import apply_migrations


def test_migrations_apply(tmp_path: Path):
    db_path = tmp_path / "test.db"
    conn = connect(db_path)
    try:
        migrations_dir = Path(__file__).resolve().parents[1] / "workbench" / "migrations"
        apply_migrations(conn, migrations_dir=migrations_dir)
        for tbl in ("instruments", "watchlist_items", "portfolio_accounts"):
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (tbl,),
            ).fetchone()
            assert row is not None
    finally:
        conn.close()

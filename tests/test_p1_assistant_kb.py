from __future__ import annotations

import importlib
import os
from pathlib import Path

from fastapi.testclient import TestClient

from workbench.db.conn import connect


def _make_client(tmp_path: Path):
    os.environ["WORKBENCH_DB_PATH"] = str(tmp_path / "wb.db")
    import workbench.api.app as appmod

    importlib.reload(appmod)
    return TestClient(appmod.app), Path(os.environ["WORKBENCH_DB_PATH"])


def _seed_bars(db_path: Path, symbol: str = "600519", exchange: str = "SSE", n: int = 60):
    conn = connect(db_path)
    try:
        with conn:
            for i in range(n):
                # YYYY-01-01.. YYYY-03-01 (enough for indicator calcs)
                d = 1 + i
                trade_date = f"2025-01-{d:02d}" if d <= 31 else f"2025-02-{(d - 31):02d}"
                close = 1000.0 + i
                conn.execute(
                    """
                    INSERT OR REPLACE INTO bars_daily(
                        symbol, exchange, trade_date, adj,
                        open, high, low, close, volume, amount, pre_close,
                        source, quality, ingested_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    """,
                    (symbol, exchange, trade_date, "RAW", close, close, close, close, 1000.0, 1e8, None, "test", "OK"),
                )
    finally:
        conn.close()


def test_kb_create_and_search(tmp_path: Path):
    client, _db_path = _make_client(tmp_path)

    resp = client.post(
        "/api/v1/kb/documents",
        json={"doc_type": "note", "title": "demo", "content": "alpha beta gamma", "tags": ["alpha"]},
    )
    assert resp.status_code == 200
    doc_id = resp.json()["data"]["doc_id"]
    assert doc_id

    resp = client.get("/api/v1/kb/search", params={"q": "alpha"})
    assert resp.status_code == 200
    hits = resp.json()["data"]
    assert any(h["doc_id"] == doc_id for h in hits)


def test_assistant_chat_offline(tmp_path: Path):
    client, db_path = _make_client(tmp_path)

    _seed_bars(db_path)
    # Seed mock news so citations exist.
    resp = client.post("/api/v1/news/ingest_mock", json={"symbol": "600519", "exchange": "SSE", "count": 3})
    assert resp.status_code == 200

    resp = client.post(
        "/api/v1/assistant/chat",
        json={"mode": "research", "prompt": "给出结论与风险", "target": "600519", "cite": "news", "save_note": True},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["report"]["conclusion"]
    assert isinstance(data["sources"], list)
    # When save_note is true and target parses, note_id should be present.
    assert data["note_id"]


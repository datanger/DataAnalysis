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


def test_health_endpoint(tmp_path: Path):
    client, _db_path = _make_client(tmp_path)
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert "providers" in payload["data"]


def test_workspace_not_ready(tmp_path: Path):
    client, _db_path = _make_client(tmp_path)
    resp = client.get("/api/v1/stocks/SSE/600519/workspace")
    assert resp.status_code == 409
    payload = resp.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "DATA_NOT_READY"


def test_scoring_calc(tmp_path: Path):
    client, db_path = _make_client(tmp_path)

    # Seed 80 bars.
    conn = connect(db_path)
    try:
        with conn:
            for i in range(80):
                d = 1 + i
                trade_date = f"2025-01-{d:02d}" if d <= 31 else f"2025-02-{(d-31):02d}"
                close = 1000.0 + i
                conn.execute(
                    """
                    INSERT OR REPLACE INTO bars_daily(
                        symbol, exchange, trade_date, adj,
                        open, high, low, close, volume, amount, pre_close,
                        source, quality, ingested_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    """,
                    ("600519", "SSE", trade_date, "RAW", close, close, close, close, 1000.0, 1e8, None, "test", "OK"),
                )
    finally:
        conn.close()

    resp = client.post("/api/v1/scores/calc", json={"symbol": "600519", "exchange": "SSE"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["score_id"]
    assert 0.0 <= data["score_total"] <= 100.0
    assert "trend" in data["breakdown"]
    assert "metrics" in data


def test_sim_trade_flow(tmp_path: Path):
    client, db_path = _make_client(tmp_path)

    resp = client.post("/api/v1/portfolios", json={"name": "demo", "initial_cash": 500000})
    assert resp.status_code == 200
    portfolio_id = resp.json()["data"]["portfolio_id"]

    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO bars_daily(symbol, exchange, trade_date, adj, close, source, quality, ingested_at) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))",
                ("600519", "SSE", "2025-01-02", "RAW", 1000.0, "test", "OK"),
            )
    finally:
        conn.close()

    resp = client.post(
        "/api/v1/order_drafts",
        json={
            "portfolio_id": portfolio_id,
            "symbol": "600519",
            "exchange": "SSE",
            "side": "BUY",
            "order_type": "LIMIT",
            "price": 1000.0,
            "qty": 100,
            "origin": "manual",
        },
    )
    assert resp.status_code == 200
    draft_id = resp.json()["data"]["draft_id"]

    resp = client.post("/api/v1/risk/check", json={"draft_ids": [draft_id]})
    assert resp.status_code == 200
    riskcheck_id = resp.json()["data"]["riskcheck_id"]
    assert resp.json()["data"]["status"] in ("PASS", "WARN")

    resp = client.post("/api/v1/sim/confirm", json={"draft_ids": [draft_id], "riskcheck_id": riskcheck_id})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "FILLED"
    assert data["order_id"]

    resp = client.get(f"/api/v1/portfolios/{portfolio_id}")
    assert resp.status_code == 200
    p = resp.json()["data"]
    assert p["cash"] < 500000
    assert any(pos["symbol"] == "600519" and pos["qty"] == 100 for pos in p["positions"])

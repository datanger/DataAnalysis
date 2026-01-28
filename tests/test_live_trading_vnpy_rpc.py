from __future__ import annotations

import importlib
import os
from pathlib import Path

from fastapi.testclient import TestClient


def _make_client(tmp_path: Path):
    # Use an isolated DB per test and force vnpy_rpc provider.
    os.environ["WORKBENCH_DB_PATH"] = str(tmp_path / "wb.db")
    os.environ["LIVE_TRADING_PROVIDER"] = "vnpy_rpc"
    os.environ["VNPY_RPC_REQ"] = "tcp://127.0.0.1:2014"
    os.environ["VNPY_RPC_SUB"] = "tcp://127.0.0.1:2015"

    import workbench.api.app as appmod

    importlib.reload(appmod)
    return TestClient(appmod.app)


def test_vnpy_rpc_missing_deps_returns_409(tmp_path: Path):
    """
    In CI/dev environments where pyzmq isn't installed, vnpy_rpc should not crash the API.
    """
    client = _make_client(tmp_path)
    resp = client.post("/api/v1/live/ping", json={})
    assert resp.status_code == 409
    payload = resp.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "LIVE_NOT_AVAILABLE"


#!/usr/bin/env python3
"""
Minimal vn.py RPC server for Workbench's vnpy_rpc adapter.

This is NOT a brokerage gateway. It only provides a small RPC surface so that
Workbench can demonstrate connecting to an external vn.py-like process.

Requires:
  - pyzmq installed
  - vn.py importable (vendored under ./vnpy in this repo)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from time import sleep, time
from typing import Any


def _ensure_vnpy_importable() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    vnpy_root = repo_root / "vnpy"
    if vnpy_root.exists():
        sys.path.insert(0, str(vnpy_root))


_ensure_vnpy_importable()

from vnpy.rpc import RpcServer  # noqa: E402


class WorkbenchDemoServer(RpcServer):
    def __init__(self) -> None:
        super().__init__()

        # Methods expected by workbench/services/live_trading.py::VnpyRpcAdapter
        self.register(self.ping)
        self.register(self.list_accounts)
        self.register(self.list_positions)
        self.register(self.list_orders)
        self.register(self.list_trades)
        self.register(self.send_order)
        self.register(self.cancel_order)

        self._orders: list[dict[str, Any]] = []
        self._trades: list[dict[str, Any]] = []

    def ping(self) -> dict[str, Any]:
        return {"ok": True, "server_time": time()}

    def list_accounts(self) -> list[dict[str, Any]]:
        return [{"account_id": "DEMO", "name": "Demo RPC Account", "currency": "CNY"}]

    def list_positions(self) -> list[dict[str, Any]]:
        return []

    def list_orders(self, active_only: bool = False, limit: int = 200) -> list[dict[str, Any]]:
        del active_only
        return self._orders[-limit:]

    def list_trades(self, limit: int = 500) -> list[dict[str, Any]]:
        return self._trades[-limit:]

    def send_order(self, body: dict[str, Any]) -> dict[str, Any]:
        order_id = f"DEMO.{len(self._orders) + 1}"
        row = {"order_id": order_id, **body, "status": "ACCEPTED"}
        self._orders.append(row)
        return row

    def cancel_order(self, body: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "body": body}


def main() -> None:
    rep_address = os.getenv("VNPY_RPC_REQ", "tcp://127.0.0.1:2014")
    pub_address = os.getenv("VNPY_RPC_SUB", "tcp://127.0.0.1:2015")

    server = WorkbenchDemoServer()
    server.start(rep_address, pub_address)

    print(f"[vnpy_rpc demo] rep={rep_address} pub={pub_address}")
    print("[vnpy_rpc demo] running; Ctrl+C to stop")

    try:
        while True:
            sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
        server.join()


if __name__ == "__main__":
    main()


from __future__ import annotations

"""
Live trading integration (P1).

This repo is "offline-first" and can run without any brokerage connectivity.
For P1 we provide a pluggable adapter interface:

- provider=sim: uses the existing local simulation flow (draft -> risk -> confirm).
- provider=vnpy_rpc: optional connector to a separate vn.py process via vnpy.rpc (requires pyzmq).

The vn.py repo is vendored under ./vnpy but gateway implementations are usually installed
as separate packages; therefore the RPC mode is designed to connect to an external process.
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class LiveTradingNotAvailable(RuntimeError):
    pass


@dataclass(frozen=True)
class LiveTradingConfig:
    provider: str
    vnpy_req_address: str | None = None
    vnpy_sub_address: str | None = None


def load_live_trading_config() -> LiveTradingConfig:
    provider = os.getenv("LIVE_TRADING_PROVIDER", "sim").strip().lower()
    if provider == "vnpy_rpc":
        return LiveTradingConfig(
            provider=provider,
            vnpy_req_address=os.getenv("VNPY_RPC_REQ", "tcp://127.0.0.1:2014"),
            vnpy_sub_address=os.getenv("VNPY_RPC_SUB", "tcp://127.0.0.1:2015"),
        )
    return LiveTradingConfig(provider="sim")


class LiveTradingAdapter:
    """Adapter interface for live trading backends."""

    def info(self) -> dict[str, Any]:
        raise NotImplementedError

    def ping(self) -> dict[str, Any]:
        raise NotImplementedError

    def list_accounts(self) -> list[dict]:
        raise NotImplementedError

    def list_positions(self) -> list[dict]:
        raise NotImplementedError

    def list_orders(self, *, active_only: bool = False, limit: int = 200) -> list[dict]:
        raise NotImplementedError

    def list_trades(self, *, limit: int = 500) -> list[dict]:
        raise NotImplementedError

    def send_order(self, body: dict) -> dict:
        raise NotImplementedError

    def cancel_order(self, body: dict) -> dict:
        raise NotImplementedError


class SimAdapter(LiveTradingAdapter):
    """Delegates to the existing local simulation primitives.

    This keeps P1 runnable on any machine while still providing a "live trading" facade.
    """

    def __init__(self, conn):
        self._conn = conn

    def info(self) -> dict[str, Any]:
        return {"provider": "sim", "capabilities": ["orders", "trades", "positions", "accounts"]}

    def ping(self) -> dict[str, Any]:
        return {"ok": True, "provider": "sim"}

    def list_accounts(self) -> list[dict]:
        # Map portfolios to "accounts".
        from workbench.services.portfolios import PortfolioRepo

        repo = PortfolioRepo(self._conn)
        return repo.list()

    def list_positions(self) -> list[dict]:
        # Flatten positions across portfolios.
        from workbench.services.portfolios import PortfolioRepo

        repo = PortfolioRepo(self._conn)
        rows: list[dict] = []
        for p in repo.list():
            detail = repo.get(p["portfolio_id"])
            for pos in (detail or {}).get("positions", []):
                rows.append({**pos, "portfolio_id": p["portfolio_id"], "portfolio_name": p["name"]})
        return rows

    def list_orders(self, *, active_only: bool = False, limit: int = 200) -> list[dict]:
        from workbench.services.sim import LedgerRepo

        repo = LedgerRepo(self._conn)
        # No global "active" concept in sim_orders; return recent orders.
        out: list[dict] = []
        for p in self.list_accounts():
            out.extend(repo.list_orders(portfolio_id=p["portfolio_id"], limit=limit))
        return out[:limit]

    def list_trades(self, *, limit: int = 500) -> list[dict]:
        from workbench.services.sim import LedgerRepo

        repo = LedgerRepo(self._conn)
        out: list[dict] = []
        for p in self.list_accounts():
            out.extend(repo.list_trades(portfolio_id=p["portfolio_id"], limit=limit))
        return out[:limit]

    def send_order(self, body: dict) -> dict:
        """Create draft + (optional) confirm; mirrors the P0 flow but through a P1 facade."""
        from workbench.services.order_drafts import OrderDraftRepo
        from workbench.services.risk import RiskService
        from workbench.services.sim import SimService

        portfolio_id = str(body.get("portfolio_id") or "")
        symbol = str(body.get("symbol") or "")
        exchange = str(body.get("exchange") or "")
        side = str(body.get("side") or "").upper()
        qty = body.get("qty")
        price = body.get("price")
        auto_confirm = bool(body.get("auto_confirm") or False)

        if not portfolio_id or not symbol or not exchange or not side or qty is None:
            raise ValueError("portfolio_id/symbol/exchange/side/qty are required")

        drafts = OrderDraftRepo(self._conn)
        draft_id = drafts.create(
            portfolio_id=portfolio_id,
            symbol=symbol,
            exchange=exchange,
            side=side,
            order_type=str(body.get("order_type") or "LIMIT"),
            price=float(price) if price is not None else None,
            qty=int(qty),
            origin=str(body.get("origin") or "live.sim"),
        )

        # Run risk check.
        draft_rows = drafts.list(portfolio_id=portfolio_id)
        row = next((d for d in draft_rows if d["draft_id"] == draft_id), None)
        if not row:
            raise RuntimeError("draft not found after creation")

        riskcheck_id, risk_payload = RiskService(self._conn).check(draft_rows=[row])

        result: dict[str, Any] = {
            "draft_id": draft_id,
            "riskcheck_id": riskcheck_id,
            "risk": risk_payload,
        }

        if auto_confirm and risk_payload.get("status") != "FAIL":
            confirm = SimService(self._conn).confirm(portfolio_id=portfolio_id, draft_rows=[row], riskcheck_id=riskcheck_id)
            result["confirm"] = confirm

        return result

    def cancel_order(self, body: dict) -> dict:
        # Local sim doesn't support cancel once filled; treat as best-effort.
        return {"ok": True, "provider": "sim", "note": "sim mode has no cancel semantics for FILLED orders"}


class VnpyRpcAdapter(LiveTradingAdapter):
    """Connect to an external vn.py process via vnpy.rpc.

    Requires:
    - pyzmq installed in the environment running workbench
    - a vn.py RPC server exposing the methods used here
    """

    def __init__(self, cfg: LiveTradingConfig):
        self._cfg = cfg
        self._client = self._make_client(cfg)
        self._started = False

    @staticmethod
    def _make_client(cfg: LiveTradingConfig):
        repo_root = Path(__file__).resolve().parents[2]
        vnpy_root = repo_root / "vnpy"
        if vnpy_root.exists():
            sys.path.insert(0, str(vnpy_root))
        try:
            from vnpy.rpc.client import RpcClient  # type: ignore
        except Exception as e:  # pragma: no cover
            raise LiveTradingNotAvailable(
                "vnpy_rpc requires vn.py (vendored or installed) and pyzmq; "
                "install pyzmq and ensure vnpy is importable."
            ) from e

        class _Client(RpcClient):
            def callback(self, topic: str, data: Any) -> None:
                # For now we don't stream events into workbench.
                return

        return _Client()

    def _ensure_started(self) -> None:
        if self._started:
            return
        if not self._cfg.vnpy_req_address or not self._cfg.vnpy_sub_address:
            raise LiveTradingNotAvailable("vnpy_rpc addresses missing")
        self._client.start(self._cfg.vnpy_req_address, self._cfg.vnpy_sub_address)
        # Subscribe to vn.py heartbeat to avoid the client printing "disconnected" messages.
        # We currently don't stream events into workbench, but heartbeat keeps the channel alive.
        try:
            self._client.subscribe_topic("heartbeat")
        except Exception:
            # Best-effort: missing zmq/etc will be handled by the caller as LiveTradingNotAvailable.
            pass
        self._started = True

    def info(self) -> dict[str, Any]:
        return {
            "provider": "vnpy_rpc",
            "req": self._cfg.vnpy_req_address,
            "sub": self._cfg.vnpy_sub_address,
            "capabilities": ["accounts", "positions", "orders", "trades"],
        }

    def ping(self) -> dict[str, Any]:
        self._ensure_started()
        # Expect the server to expose a ping() method.
        return {"ok": True, "provider": "vnpy_rpc", "pong": self._client.ping(timeout=1500)}

    def list_accounts(self) -> list[dict]:
        self._ensure_started()
        return list(self._client.list_accounts(timeout=5000))

    def list_positions(self) -> list[dict]:
        self._ensure_started()
        return list(self._client.list_positions(timeout=5000))

    def list_orders(self, *, active_only: bool = False, limit: int = 200) -> list[dict]:
        self._ensure_started()
        return list(self._client.list_orders(active_only=active_only, limit=limit, timeout=5000))

    def list_trades(self, *, limit: int = 500) -> list[dict]:
        self._ensure_started()
        return list(self._client.list_trades(limit=limit, timeout=5000))

    def send_order(self, body: dict) -> dict:
        self._ensure_started()
        return dict(self._client.send_order(body=body, timeout=8000))

    def cancel_order(self, body: dict) -> dict:
        self._ensure_started()
        return dict(self._client.cancel_order(body=body, timeout=8000))


def get_adapter(*, conn) -> LiveTradingAdapter:
    cfg = load_live_trading_config()
    if cfg.provider == "vnpy_rpc":
        return VnpyRpcAdapter(cfg)
    return SimAdapter(conn)

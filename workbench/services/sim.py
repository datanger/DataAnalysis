from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from uuid import uuid4

from workbench.jsonutil import dumps
from workbench.services.portfolios import PortfolioRepo


class SimService:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self.fee_rate = float(os.getenv("SIM_FEE_RATE", "0.0003"))
        self.slippage_rate = float(os.getenv("SIM_SLIPPAGE_RATE", "0.0005"))

    def confirm(self, *, portfolio_id: str, draft_rows: list[dict], riskcheck_id: str) -> dict:
        if not draft_rows:
            raise ValueError("draft_rows empty")

        # Verify riskcheck status.
        row = self._conn.execute(
            "SELECT status FROM risk_check_results WHERE riskcheck_id=?",
            (riskcheck_id,),
        ).fetchone()
        if not row:
            raise ValueError("riskcheck_id not found")
        if str(row[0]) == "FAIL":
            raise ValueError("risk check failed")

        cash = PortfolioRepo(self._conn).get_cash(portfolio_id)

        order_id = str(uuid4())
        now = datetime.now().isoformat(timespec="seconds")

        total_fee = 0.0
        total_slip = 0.0
        filled_qty_total = 0
        fill_value_total = 0.0

        trades: list[dict] = []

        with self._conn:
            for d in draft_rows:
                sym = d["symbol"]
                exch = d["exchange"]
                side = d["side"]
                qty = int(d["qty"])
                limit_price = d["price"]

                latest = self._latest_close(sym, exch)
                if latest is None:
                    raise ValueError(f"no latest price for {sym}.{exch}")

                base_price = float(latest)
                fill_price = float(limit_price) if limit_price is not None else base_price

                slippage = base_price * self.slippage_rate * qty
                fee = fill_price * qty * self.fee_rate

                if side == "BUY":
                    cash -= (fill_price * qty) + fee + slippage
                else:
                    cash += (fill_price * qty) - fee - slippage

                total_fee += fee
                total_slip += slippage
                filled_qty_total += qty
                fill_value_total += fill_price * qty

                trade_id = str(uuid4())
                self._conn.execute(
                    """
                    INSERT INTO sim_trades(
                        trade_id, order_id, portfolio_id, filled_at,
                        symbol, exchange, side, fill_price, fill_qty, fee, slippage
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trade_id,
                        order_id,
                        portfolio_id,
                        now,
                        sym,
                        exch,
                        side,
                        float(fill_price),
                        int(qty),
                        float(fee),
                        float(slippage),
                    ),
                )

                self._apply_position(portfolio_id=portfolio_id, symbol=sym, exchange=exch, side=side, qty=qty, fill_price=fill_price, fee=fee, slippage=slippage)

                trades.append(
                    {
                        "trade_id": trade_id,
                        "symbol": sym,
                        "exchange": exch,
                        "side": side,
                        "fill_price": fill_price,
                        "fill_qty": qty,
                        "fee": fee,
                        "slippage": slippage,
                    }
                )

            avg_fill_price = (fill_value_total / filled_qty_total) if filled_qty_total else None

            self._conn.execute(
                """
                INSERT INTO sim_orders(order_id, portfolio_id, created_at, status, draft_ids_json, filled_qty, avg_fill_price, fee_total, slippage_total)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    portfolio_id,
                    now,
                    "FILLED",
                    dumps([d["draft_id"] for d in draft_rows]),
                    filled_qty_total,
                    avg_fill_price,
                    total_fee,
                    total_slip,
                ),
            )

            PortfolioRepo(self._conn).set_cash(portfolio_id, cash)

        return {
            "order_id": order_id,
            "status": "FILLED",
            "filled_qty": filled_qty_total,
            "avg_fill_price": (fill_value_total / filled_qty_total) if filled_qty_total else None,
            "fee_total": total_fee,
            "slippage_total": total_slip,
            "trades": trades,
            "cash": cash,
        }

    def _latest_close(self, symbol: str, exchange: str) -> float | None:
        row = self._conn.execute(
            """
            SELECT close
            FROM bars_daily
            WHERE symbol=? AND exchange=? AND adj='RAW'
            ORDER BY trade_date DESC
            LIMIT 1
            """,
            (symbol, exchange),
        ).fetchone()
        return float(row[0]) if row and row[0] is not None else None

    def _apply_position(
        self,
        *,
        portfolio_id: str,
        symbol: str,
        exchange: str,
        side: str,
        qty: int,
        fill_price: float,
        fee: float,
        slippage: float,
    ) -> None:
        repo = PortfolioRepo(self._conn)
        pos = repo.get_position(portfolio_id, symbol, exchange)
        old_qty = pos[0] if pos else 0
        old_avg = pos[1] if pos else 0.0

        if side == "BUY":
            new_qty = old_qty + qty
            new_cost_total = (old_avg * old_qty) + (fill_price * qty) + fee + slippage
            new_avg = new_cost_total / new_qty if new_qty else 0.0
            repo.upsert_position(portfolio_id=portfolio_id, symbol=symbol, exchange=exchange, qty=new_qty, avg_cost=new_avg)
        else:
            new_qty = old_qty - qty
            if new_qty < 0:
                raise ValueError("position would go negative")
            if new_qty == 0:
                repo.delete_position(portfolio_id=portfolio_id, symbol=symbol, exchange=exchange)
            else:
                # Keep avg_cost unchanged on sells.
                repo.upsert_position(portfolio_id=portfolio_id, symbol=symbol, exchange=exchange, qty=new_qty, avg_cost=old_avg)


class LedgerRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def list_orders(self, portfolio_id: str, limit: int = 200) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT order_id, created_at, status, draft_ids_json, filled_qty, avg_fill_price, fee_total, slippage_total
            FROM sim_orders
            WHERE portfolio_id=?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (portfolio_id, limit),
        ).fetchall()

        import json

        return [
            {
                "order_id": r[0],
                "created_at": r[1],
                "status": r[2],
                "draft_ids": json.loads(r[3]) if r[3] else [],
                "filled_qty": r[4],
                "avg_fill_price": r[5],
                "fee_total": r[6],
                "slippage_total": r[7],
            }
            for r in rows
        ]

    def list_trades(self, portfolio_id: str, limit: int = 500) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT trade_id, order_id, filled_at, symbol, exchange, side, fill_price, fill_qty, fee, slippage
            FROM sim_trades
            WHERE portfolio_id=?
            ORDER BY filled_at DESC
            LIMIT ?
            """,
            (portfolio_id, limit),
        ).fetchall()

        return [
            {
                "trade_id": r[0],
                "order_id": r[1],
                "filled_at": r[2],
                "symbol": r[3],
                "exchange": r[4],
                "side": r[5],
                "fill_price": r[6],
                "fill_qty": r[7],
                "fee": r[8],
                "slippage": r[9],
            }
            for r in rows
        ]

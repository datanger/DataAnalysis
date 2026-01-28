from __future__ import annotations

import sqlite3
from datetime import datetime
from uuid import uuid4


class PortfolioRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create(self, *, name: str, initial_cash: float) -> str:
        portfolio_id = str(uuid4())
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn:
            self._conn.execute(
                "INSERT INTO portfolios(portfolio_id, name, base_currency, created_at) VALUES (?, ?, 'CNY', ?)",
                (portfolio_id, name, now),
            )
            self._conn.execute(
                "INSERT INTO portfolio_accounts(portfolio_id, cash, updated_at) VALUES (?, ?, ?)",
                (portfolio_id, float(initial_cash), now),
            )
        return portfolio_id

    def list(self) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT p.portfolio_id, p.name, p.base_currency, p.created_at,
                   a.cash, a.updated_at
            FROM portfolios p
            JOIN portfolio_accounts a ON a.portfolio_id=p.portfolio_id
            ORDER BY p.created_at DESC
            """
        ).fetchall()

        return [
            {
                "portfolio_id": r[0],
                "name": r[1],
                "base_currency": r[2],
                "created_at": r[3],
                "cash": float(r[4]),
                "cash_updated_at": r[5],
            }
            for r in rows
        ]

    def get(self, portfolio_id: str) -> dict | None:
        row = self._conn.execute(
            """
            SELECT p.portfolio_id, p.name, p.base_currency, p.created_at,
                   a.cash, a.updated_at
            FROM portfolios p
            JOIN portfolio_accounts a ON a.portfolio_id=p.portfolio_id
            WHERE p.portfolio_id=?
            """,
            (portfolio_id,),
        ).fetchone()
        if not row:
            return None

        cash = float(row[4])

        positions = self._conn.execute(
            """
            SELECT symbol, exchange, qty, avg_cost, updated_at
            FROM positions
            WHERE portfolio_id=?
            ORDER BY symbol
            """,
            (portfolio_id,),
        ).fetchall()

        pos_rows: list[dict] = []
        mv_total = 0.0
        missing_prices: list[str] = []
        for p in positions:
            symbol = str(p[0])
            exchange = str(p[1])
            qty = int(p[2])
            avg_cost = float(p[3])

            last_price = self._latest_close(symbol, exchange)
            market_value = (qty * last_price) if last_price is not None else None
            unrealized_pnl = (market_value - (qty * avg_cost)) if market_value is not None else None
            unrealized_pnl_pct = (
                (unrealized_pnl / (qty * avg_cost))
                if unrealized_pnl is not None and (qty * avg_cost) != 0
                else None
            )

            if market_value is None:
                missing_prices.append(f"{symbol}.{exchange}")
            else:
                mv_total += market_value

            pos_rows.append(
                {
                    "symbol": symbol,
                    "exchange": exchange,
                    "qty": qty,
                    "avg_cost": avg_cost,
                    "updated_at": p[4],
                    "last_price": last_price,
                    "market_value": market_value,
                    "unrealized_pnl": unrealized_pnl,
                    "unrealized_pnl_pct": unrealized_pnl_pct,
                }
            )

        total_equity = cash + mv_total
        for r in pos_rows:
            mv = r.get("market_value")
            r["weight"] = (mv / total_equity) if mv is not None and total_equity > 0 else None

        return {
            "portfolio_id": row[0],
            "name": row[1],
            "base_currency": row[2],
            "created_at": row[3],
            "cash": cash,
            "cash_updated_at": row[5],
            "positions": pos_rows,
            "positions_market_value": mv_total,
            "total_equity": total_equity,
            "cash_ratio": (cash / total_equity) if total_equity > 0 else None,
            "missing_prices": missing_prices,
        }

    def get_cash(self, portfolio_id: str) -> float:
        row = self._conn.execute(
            "SELECT cash FROM portfolio_accounts WHERE portfolio_id=?",
            (portfolio_id,),
        ).fetchone()
        if not row:
            raise KeyError("portfolio not found")
        return float(row[0])

    def set_cash(self, portfolio_id: str, cash: float) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn:
            self._conn.execute(
                "UPDATE portfolio_accounts SET cash=?, updated_at=? WHERE portfolio_id=?",
                (float(cash), now, portfolio_id),
            )

    def get_position(self, portfolio_id: str, symbol: str, exchange: str) -> tuple[int, float] | None:
        row = self._conn.execute(
            "SELECT qty, avg_cost FROM positions WHERE portfolio_id=? AND symbol=? AND exchange=?",
            (portfolio_id, symbol, exchange),
        ).fetchone()
        if not row:
            return None
        return int(row[0]), float(row[1])

    def upsert_position(self, *, portfolio_id: str, symbol: str, exchange: str, qty: int, avg_cost: float) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO positions(portfolio_id, symbol, exchange, qty, avg_cost, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(portfolio_id, symbol, exchange) DO UPDATE SET
                    qty=excluded.qty,
                    avg_cost=excluded.avg_cost,
                    updated_at=excluded.updated_at
                """,
                (portfolio_id, symbol, exchange, int(qty), float(avg_cost), now),
            )

    def delete_position(self, *, portfolio_id: str, symbol: str, exchange: str) -> None:
        with self._conn:
            self._conn.execute(
                "DELETE FROM positions WHERE portfolio_id=? AND symbol=? AND exchange=?",
                (portfolio_id, symbol, exchange),
            )

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


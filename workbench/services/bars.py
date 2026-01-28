from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Iterable, Sequence

from workbench.providers.base import BarDailyRow


class BarsRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def upsert_many(self, rows: Iterable[BarDailyRow]) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        n = 0
        with self._conn:
            for r in rows:
                self._conn.execute(
                    """
                    INSERT INTO bars_daily(
                        symbol, exchange, trade_date, adj,
                        open, high, low, close, volume, amount, pre_close,
                        source, quality, ingested_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol, exchange, trade_date, adj) DO UPDATE SET
                        open=excluded.open,
                        high=excluded.high,
                        low=excluded.low,
                        close=excluded.close,
                        volume=excluded.volume,
                        amount=excluded.amount,
                        pre_close=excluded.pre_close,
                        source=excluded.source,
                        quality=excluded.quality,
                        ingested_at=excluded.ingested_at
                    """,
                    (
                        r.symbol,
                        r.exchange,
                        r.trade_date,
                        r.adj,
                        r.open,
                        r.high,
                        r.low,
                        r.close,
                        r.volume,
                        r.amount,
                        r.pre_close,
                        r.source,
                        r.quality,
                        now,
                    ),
                )
                n += 1
        return n

    def list_bars(self, *, symbol: str, exchange: str, adj: str = "RAW", limit: int = 200) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT trade_date, open, high, low, close, volume, amount, pre_close
            FROM bars_daily
            WHERE symbol=? AND exchange=? AND adj=?
            ORDER BY trade_date DESC
            LIMIT ?
            """,
            (symbol, exchange, adj, limit),
        ).fetchall()

        # Return oldest-first for charting.
        rows = list(reversed(rows))

        return [
            {
                "trade_date": r[0],
                "open": r[1],
                "high": r[2],
                "low": r[3],
                "close": r[4],
                "volume": r[5],
                "amount": r[6],
                "pre_close": r[7],
            }
            for r in rows
        ]

    def latest_ingested_at(self, *, symbol: str, exchange: str, adj: str = "RAW") -> str | None:
        row = self._conn.execute(
            """
            SELECT ingested_at
            FROM bars_daily
            WHERE symbol=? AND exchange=? AND adj=?
            ORDER BY ingested_at DESC
            LIMIT 1
            """,
            (symbol, exchange, adj),
        ).fetchone()
        return row[0] if row else None

    def list_bars_range(
        self,
        *,
        symbol: str,
        exchange: str,
        start_date: str,
        end_date: str,
        adj: str = "RAW",
    ) -> list[dict]:
        """List bars within a date range."""
        rows = self._conn.execute(
            """
            SELECT trade_date, open, high, low, close, volume, amount, pre_close
            FROM bars_daily
            WHERE symbol=? AND exchange=? AND adj=? AND trade_date BETWEEN ? AND ?
            ORDER BY trade_date ASC
            """,
            (symbol, exchange, adj, start_date, end_date),
        ).fetchall()

        return [
            {
                "trade_date": r[0],
                "open": r[1],
                "high": r[2],
                "low": r[3],
                "close": r[4],
                "volume": r[5],
                "amount": r[6],
                "pre_close": r[7],
            }
            for r in rows
        ]

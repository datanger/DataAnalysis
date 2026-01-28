from __future__ import annotations

import sqlite3
from datetime import datetime


class FundamentalsRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def upsert_daily(
        self,
        *,
        symbol: str,
        exchange: str,
        trade_date: str,  # YYYY-MM-DD
        pe_ttm: float | None,
        pb: float | None,
        ps_ttm: float | None,
        mv: float | None,
        source: str,
        quality: str = "OK",
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO fundamental_snapshot(
                    symbol, exchange, report_period, report_type,
                    pe_ttm, pb, ps_ttm, mv,
                    source, quality, ingested_at
                ) VALUES (?, ?, ?, 'D', ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, exchange, report_period, report_type) DO UPDATE SET
                    pe_ttm=excluded.pe_ttm,
                    pb=excluded.pb,
                    ps_ttm=excluded.ps_ttm,
                    mv=excluded.mv,
                    source=excluded.source,
                    quality=excluded.quality,
                    ingested_at=excluded.ingested_at
                """,
                (
                    symbol,
                    exchange,
                    trade_date,
                    pe_ttm,
                    pb,
                    ps_ttm,
                    mv,
                    source,
                    quality,
                    now,
                ),
            )

    def latest_daily(self, *, symbol: str, exchange: str) -> dict | None:
        row = self._conn.execute(
            """
            SELECT report_period, pe_ttm, pb, ps_ttm, mv, source, quality, ingested_at
            FROM fundamental_snapshot
            WHERE symbol=? AND exchange=? AND report_type='D'
            ORDER BY report_period DESC
            LIMIT 1
            """,
            (symbol, exchange),
        ).fetchone()
        if not row:
            return None
        return {
            "trade_date": row[0],
            "pe_ttm": row[1],
            "pb": row[2],
            "ps_ttm": row[3],
            "mv": row[4],
            "source": row[5],
            "quality": row[6],
            "ingested_at": row[7],
        }

    def list_daily_range(
        self,
        *,
        symbol: str,
        exchange: str,
        start_date: str,
        end_date: str,
    ) -> list[dict]:
        """List fundamental data within a date range."""
        rows = self._conn.execute(
            """
            SELECT report_period, pe_ttm, pb, ps_ttm, mv, source, quality, ingested_at
            FROM fundamental_snapshot
            WHERE symbol=? AND exchange=? AND report_type='D'
            AND report_period BETWEEN ? AND ?
            ORDER BY report_period ASC
            """,
            (symbol, exchange, start_date, end_date),
        ).fetchall()

        return [
            {
                "trade_date": r[0],
                "pe_ttm": r[1],
                "pb": r[2],
                "ps_ttm": r[3],
                "mv": r[4],
                "source": r[5],
                "quality": r[6],
                "ingested_at": r[7],
            }
            for r in rows
        ]


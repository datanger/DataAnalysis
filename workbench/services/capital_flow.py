from __future__ import annotations

import sqlite3
from datetime import datetime


class CapitalFlowRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def upsert_daily(
        self,
        *,
        symbol: str,
        exchange: str,
        trade_date: str,  # YYYY-MM-DD
        net_inflow: float | None,
        main_inflow: float | None,
        northbound_net: float | None,
        source: str,
        quality: str = "OK",
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO capital_flow_daily(
                    symbol, exchange, trade_date,
                    net_inflow, main_inflow, northbound_net,
                    source, quality, ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, exchange, trade_date) DO UPDATE SET
                    net_inflow=excluded.net_inflow,
                    main_inflow=excluded.main_inflow,
                    northbound_net=excluded.northbound_net,
                    source=excluded.source,
                    quality=excluded.quality,
                    ingested_at=excluded.ingested_at
                """,
                (
                    symbol,
                    exchange,
                    trade_date,
                    net_inflow,
                    main_inflow,
                    northbound_net,
                    source,
                    quality,
                    now,
                ),
            )

    def latest(self, *, symbol: str, exchange: str) -> dict | None:
        row = self._conn.execute(
            """
            SELECT trade_date, net_inflow, main_inflow, northbound_net, source, quality, ingested_at
            FROM capital_flow_daily
            WHERE symbol=? AND exchange=?
            ORDER BY trade_date DESC
            LIMIT 1
            """,
            (symbol, exchange),
        ).fetchone()
        if not row:
            return None
        return {
            "trade_date": row[0],
            "net_inflow": row[1],
            "main_inflow": row[2],
            "northbound_net": row[3],
            "source": row[4],
            "quality": row[5],
            "ingested_at": row[6],
        }


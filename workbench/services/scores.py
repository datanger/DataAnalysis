from __future__ import annotations

import sqlite3
from datetime import date, datetime
from uuid import uuid4

from workbench.jsonutil import dumps


class ScoresRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def insert(
        self,
        *,
        symbol: str,
        exchange: str,
        trade_date: str,
        score_total: float,
        breakdown: dict,
        reasons: list[str],
        ruleset_version: str,
        data_version: dict,
    ) -> str:
        score_id = str(uuid4())
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO score_snapshots(
                    score_id, symbol, exchange, trade_date, score_total,
                    breakdown_json, reasons_json, ruleset_version, data_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    score_id,
                    symbol,
                    exchange,
                    trade_date,
                    float(score_total),
                    dumps(breakdown),
                    dumps(reasons),
                    ruleset_version,
                    dumps(data_version),
                    now,
                ),
            )
        return score_id

    def latest(self, *, symbol: str, exchange: str) -> dict | None:
        row = self._conn.execute(
            """
            SELECT score_id, trade_date, score_total, breakdown_json, reasons_json, ruleset_version, data_version, created_at
            FROM score_snapshots
            WHERE symbol=? AND exchange=?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (symbol, exchange),
        ).fetchone()
        if not row:
            return None

        import json

        return {
            "score_id": row[0],
            "trade_date": row[1],
            "score_total": row[2],
            "breakdown": json.loads(row[3]) if row[3] else {},
            "reasons": json.loads(row[4]) if row[4] else [],
            "ruleset_version": row[5],
            "data_version": json.loads(row[6]) if row[6] else {},
            "created_at": row[7],
        }

    def list(self, *, symbol: str, exchange: str, limit: int = 200) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT score_id, trade_date, score_total, breakdown_json, reasons_json, ruleset_version, data_version, created_at
            FROM score_snapshots
            WHERE symbol=? AND exchange=?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (symbol, exchange, limit),
        ).fetchall()

        import json

        out: list[dict] = []
        for row in rows:
            out.append(
                {
                    "score_id": row[0],
                    "trade_date": row[1],
                    "score_total": row[2],
                    "breakdown": json.loads(row[3]) if row[3] else {},
                    "reasons": json.loads(row[4]) if row[4] else [],
                    "ruleset_version": row[5],
                    "data_version": json.loads(row[6]) if row[6] else {},
                    "created_at": row[7],
                }
            )
        return out

    def list_range(
        self,
        *,
        symbol: str,
        exchange: str,
        start_date: str,
        end_date: str,
    ) -> list[dict]:
        """List scores within a date range."""
        rows = self._conn.execute(
            """
            SELECT score_id, trade_date, score_total, breakdown_json, reasons_json, ruleset_version, data_version, created_at
            FROM score_snapshots
            WHERE symbol=? AND exchange=? AND trade_date BETWEEN ? AND ?
            ORDER BY trade_date ASC
            """,
            (symbol, exchange, start_date, end_date),
        ).fetchall()

        import json

        out: list[dict] = []
        for row in rows:
            out.append(
                {
                    "score_id": row[0],
                    "trade_date": row[1],
                    "score_total": row[2],
                    "breakdown": json.loads(row[3]) if row[3] else {},
                    "reasons": json.loads(row[4]) if row[4] else [],
                    "ruleset_version": row[5],
                    "data_version": json.loads(row[6]) if row[6] else {},
                    "created_at": row[7],
                }
            )
        return out

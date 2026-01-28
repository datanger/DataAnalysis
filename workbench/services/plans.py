from __future__ import annotations

import sqlite3
from datetime import datetime
from uuid import uuid4

from workbench.jsonutil import dumps


class PlansRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def _next_version(self, *, symbol: str, exchange: str) -> int:
        row = self._conn.execute(
            "SELECT MAX(plan_version) FROM trade_plans WHERE symbol=? AND exchange=?",
            (symbol, exchange),
        ).fetchone()
        cur = int(row[0]) if row and row[0] is not None else 0
        return cur + 1

    def create(self, *, symbol: str, exchange: str, plan_json: dict, based_on: dict) -> str:
        plan_id = str(uuid4())
        now = datetime.now().isoformat(timespec="seconds")
        version = self._next_version(symbol=symbol, exchange=exchange)
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO trade_plans(plan_id, symbol, exchange, created_at, plan_version, plan_json, based_on_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (plan_id, symbol, exchange, now, version, dumps(plan_json), dumps(based_on)),
            )
        return plan_id

    def latest(self, *, symbol: str, exchange: str) -> dict | None:
        row = self._conn.execute(
            """
            SELECT plan_id, created_at, plan_version, plan_json, based_on_json
            FROM trade_plans
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
            "plan_id": row[0],
            "created_at": row[1],
            "plan_version": row[2],
            "plan": json.loads(row[3]) if row[3] else {},
            "based_on": json.loads(row[4]) if row[4] else {},
        }

    def list(self, *, symbol: str, exchange: str, limit: int = 200) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT plan_id, created_at, plan_version, plan_json, based_on_json
            FROM trade_plans
            WHERE symbol=? AND exchange=?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (symbol, exchange, limit),
        ).fetchall()

        import json

        return [
            {
                "plan_id": r[0],
                "created_at": r[1],
                "plan_version": r[2],
                "plan": json.loads(r[3]) if r[3] else {},
                "based_on": json.loads(r[4]) if r[4] else {},
            }
            for r in rows
        ]

    def get(self, plan_id: str) -> dict | None:
        row = self._conn.execute(
            """
            SELECT plan_id, symbol, exchange, created_at, plan_version, plan_json, based_on_json
            FROM trade_plans
            WHERE plan_id=?
            """,
            (plan_id,),
        ).fetchone()
        if not row:
            return None

        import json

        return {
            "plan_id": row[0],
            "symbol": row[1],
            "exchange": row[2],
            "created_at": row[3],
            "plan_version": row[4],
            "plan": json.loads(row[5]) if row[5] else {},
            "based_on": json.loads(row[6]) if row[6] else {},
        }

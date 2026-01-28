from __future__ import annotations

import sqlite3
from datetime import datetime
from uuid import uuid4


class OrderDraftRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create(
        self,
        *,
        portfolio_id: str,
        symbol: str,
        exchange: str,
        side: str,
        order_type: str,
        price: float | None,
        qty: int,
        notes: str | None,
        origin: str,
    ) -> str:
        draft_id = str(uuid4())
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO order_drafts(
                    draft_id, portfolio_id, symbol, exchange,
                    side, order_type, price, qty, notes, origin,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    draft_id,
                    portfolio_id,
                    symbol,
                    exchange,
                    side,
                    order_type,
                    price,
                    int(qty),
                    notes,
                    origin,
                    now,
                    now,
                ),
            )
        return draft_id

    def list(self, portfolio_id: str) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT draft_id, portfolio_id, symbol, exchange, side, order_type, price, qty, notes, origin, created_at, updated_at
            FROM order_drafts
            WHERE portfolio_id=?
            ORDER BY created_at DESC
            """,
            (portfolio_id,),
        ).fetchall()

        return [
            {
                "draft_id": r[0],
                "portfolio_id": r[1],
                "symbol": r[2],
                "exchange": r[3],
                "side": r[4],
                "order_type": r[5],
                "price": r[6],
                "qty": r[7],
                "notes": r[8],
                "origin": r[9],
                "created_at": r[10],
                "updated_at": r[11],
            }
            for r in rows
        ]

    def get_many(self, draft_ids: list[str]) -> list[dict]:
        if not draft_ids:
            return []
        placeholders = ",".join("?" for _ in draft_ids)
        rows = self._conn.execute(
            f"""
            SELECT draft_id, portfolio_id, symbol, exchange, side, order_type, price, qty, notes, origin, created_at, updated_at
            FROM order_drafts
            WHERE draft_id IN ({placeholders})
            """,
            tuple(draft_ids),
        ).fetchall()
        return [
            {
                "draft_id": r[0],
                "portfolio_id": r[1],
                "symbol": r[2],
                "exchange": r[3],
                "side": r[4],
                "order_type": r[5],
                "price": r[6],
                "qty": r[7],
                "notes": r[8],
                "origin": r[9],
                "created_at": r[10],
                "updated_at": r[11],
            }
            for r in rows
        ]

    def update(self, draft_id: str, patch: dict) -> None:
        allowed = {"price", "qty", "notes"}
        fields = {k: v for k, v in patch.items() if k in allowed}
        if not fields:
            return

        sets = []
        params = []
        for k, v in fields.items():
            sets.append(f"{k}=?")
            params.append(v)
        sets.append("updated_at=?")
        params.append(datetime.now().isoformat(timespec="seconds"))
        params.append(draft_id)

        sql = f"UPDATE order_drafts SET {', '.join(sets)} WHERE draft_id=?"
        with self._conn:
            self._conn.execute(sql, tuple(params))

    def delete(self, draft_id: str) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM order_drafts WHERE draft_id=?", (draft_id,))

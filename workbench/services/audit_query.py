from __future__ import annotations

import sqlite3


class AuditQueryRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def list(self, *, entity_type: str, entity_id: str, limit: int = 200) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT ts, actor, action, entity_type, entity_id, input_snapshot_json, output_snapshot_json,
                   ruleset_version, data_version, model_version
            FROM audit_log
            WHERE entity_type=? AND entity_id=?
            ORDER BY ts DESC
            LIMIT ?
            """,
            (entity_type, entity_id, limit),
        ).fetchall()

        import json

        return [
            {
                "ts": r[0],
                "actor": r[1],
                "action": r[2],
                "entity_type": r[3],
                "entity_id": r[4],
                "input": json.loads(r[5]) if r[5] else {},
                "output": json.loads(r[6]) if r[6] else {},
                "ruleset_version": r[7],
                "data_version": r[8],
                "model_version": r[9],
            }
            for r in rows
        ]

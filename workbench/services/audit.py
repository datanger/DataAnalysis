from __future__ import annotations

from datetime import datetime
import sqlite3
from uuid import uuid4

from workbench.jsonutil import dumps


class AuditLogger:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def log(
        self,
        *,
        actor: str,
        action: str,
        entity_type: str,
        entity_id: str,
        input_snapshot: dict,
        output_snapshot: dict,
        ruleset_version: str | None = None,
        data_version: object | None = None,
        model_version: object | None = None,
    ) -> str:
        audit_id = str(uuid4())
        ts = datetime.now().isoformat(timespec="seconds")

        # Store versions as TEXT; accept dict/list and serialize.
        dv = None
        if data_version is not None:
            dv = data_version if isinstance(data_version, str) else dumps(data_version)
        mv = None
        if model_version is not None:
            mv = model_version if isinstance(model_version, str) else dumps(model_version)

        with self._conn:
            self._conn.execute(
                """
                INSERT INTO audit_log(
                    audit_id, ts, actor, action, entity_type, entity_id,
                    input_snapshot_json, output_snapshot_json,
                    ruleset_version, data_version, model_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    audit_id,
                    ts,
                    actor,
                    action,
                    entity_type,
                    entity_id,
                    dumps(input_snapshot),
                    dumps(output_snapshot),
                    ruleset_version,
                    dv,
                    mv,
                ),
            )
        return audit_id

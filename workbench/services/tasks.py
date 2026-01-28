from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import traceback
from typing import Callable
from uuid import uuid4

from workbench.db.conn import connect
from workbench.domain.types import TaskStatus
from workbench.errors import ErrorCodes
from workbench.jsonutil import dumps


TaskFn = Callable[[object, dict], dict]


class TaskManager:
    """In-process async task runner backed by the SQLite tasks table.

    Important: SQLite connections are thread-affine unless configured otherwise.
    We use short-lived connections (one per method call / task execution).
    """

    def __init__(self, db_path: Path, max_workers: int):
        self._db_path = db_path
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = threading.Lock()

    def create_task(self, type_: str, payload: dict) -> str:
        task_id = str(uuid4())
        now = datetime.now().isoformat(timespec="seconds")
        conn = connect(self._db_path)
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO tasks(task_id, type, status, payload_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (task_id, type_, TaskStatus.PENDING.value, dumps(payload), now),
                )
        finally:
            conn.close()
        return task_id

    def submit(self, task_id: str, fn: Callable[[object, dict], dict]) -> None:
        def _run() -> None:
            conn = connect(self._db_path)
            try:
                with self._lock:
                    self._mark_running(conn, task_id)
                payload = self._get_payload(conn, task_id)
                try:
                    result = fn(conn, payload)
                    self._mark_succeeded(conn, task_id, result)
                except Exception as e:  # noqa: BLE001
                    tb = traceback.format_exc(limit=20)
                    self._mark_failed(conn, task_id, ErrorCodes.INTERNAL_ERROR, f"{e}\n{tb}")
            finally:
                conn.close()

        self._executor.submit(_run)

    def _mark_running(self, conn, task_id: str) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with conn:
            conn.execute(
                "UPDATE tasks SET status=?, started_at=? WHERE task_id=?",
                (TaskStatus.RUNNING.value, now, task_id),
            )

    def _mark_succeeded(self, conn, task_id: str, result: dict) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with conn:
            conn.execute(
                "UPDATE tasks SET status=?, finished_at=?, result_json=? WHERE task_id=?",
                (TaskStatus.SUCCEEDED.value, now, dumps(result), task_id),
            )

    def _mark_failed(self, conn, task_id: str, error_code: str, error_message: str) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with conn:
            conn.execute(
                """
                UPDATE tasks
                SET status=?, finished_at=?, error_code=?, error_message=?
                WHERE task_id=?
                """,
                (TaskStatus.FAILED.value, now, error_code, error_message, task_id),
            )

    def _get_payload(self, conn, task_id: str) -> dict:
        row = conn.execute(
            "SELECT payload_json FROM tasks WHERE task_id=?",
            (task_id,),
        ).fetchone()
        if not row:
            return {}
        import json

        return json.loads(row[0])

    def get_task(self, task_id: str) -> dict | None:
        conn = connect(self._db_path)
        try:
            row = conn.execute(
                """
                SELECT task_id, type, status, payload_json, result_json,
                       error_code, error_message, created_at, started_at, finished_at
                FROM tasks WHERE task_id=?
                """,
                (task_id,),
            ).fetchone()
            if not row:
                return None

            import json

            return {
                "task_id": row[0],
                "type": row[1],
                "status": row[2],
                "payload": json.loads(row[3]) if row[3] else {},
                "result": json.loads(row[4]) if row[4] else None,
                "error_code": row[5],
                "error_message": row[6],
                "created_at": row[7],
                "started_at": row[8],
                "finished_at": row[9],
            }
        finally:
            conn.close()

    def list_tasks(self, limit: int = 50) -> list[dict]:
        conn = connect(self._db_path)
        try:
            rows = conn.execute(
                """
                SELECT task_id, type, status, payload_json, result_json,
                       error_code, error_message, created_at, started_at, finished_at
                FROM tasks ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()

            import json

            out: list[dict] = []
            for row in rows:
                out.append(
                    {
                        "task_id": row[0],
                        "type": row[1],
                        "status": row[2],
                        "payload": json.loads(row[3]) if row[3] else {},
                        "result": json.loads(row[4]) if row[4] else None,
                        "error_code": row[5],
                        "error_message": row[6],
                        "created_at": row[7],
                        "started_at": row[8],
                        "finished_at": row[9],
                    }
                )
            return out
        finally:
            conn.close()

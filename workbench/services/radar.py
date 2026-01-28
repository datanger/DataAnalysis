from __future__ import annotations

import sqlite3
from datetime import datetime
from uuid import uuid4

from workbench.jsonutil import dumps
from workbench.services.scoring import ScoringService


def _match_rule(row: dict, rule: dict) -> tuple[bool, str]:
    """Return (matched, reason)."""

    field = rule.get("field")
    op = rule.get("op")
    value = rule.get("value")

    v = row.get(field)

    if op == "eq":
        ok = v == value
        return ok, f"{field}=={value}" if ok else ""
    if op == "in":
        ok = v in (value or [])
        return ok, f"{field} in {value}" if ok else ""
    if op == "prefix":
        ok = isinstance(v, str) and isinstance(value, str) and v.startswith(value)
        return ok, f"{field} startswith {value}" if ok else ""

    return False, ""


class RadarRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create_template(self, name: str, universe: dict, rules: list[dict]) -> str:
        template_id = str(uuid4())
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO radar_templates(template_id, name, universe_json, rules_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (template_id, name, dumps(universe), dumps(rules), now, now),
            )
        return template_id

    def list_templates(self) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT template_id, name, universe_json, rules_json, created_at, updated_at
            FROM radar_templates
            ORDER BY updated_at DESC
            """
        ).fetchall()

        import json

        return [
            {
                "template_id": r[0],
                "name": r[1],
                "universe": json.loads(r[2]) if r[2] else {},
                "rules": json.loads(r[3]) if r[3] else [],
                "created_at": r[4],
                "updated_at": r[5],
            }
            for r in rows
        ]

    def write_results(self, task_id: str, items: list[dict]) -> int:
        with self._conn:
            for it in items:
                self._conn.execute(
                    """
                    INSERT INTO radar_results(task_id, symbol, exchange, score_total, breakdown_json, reasons_json, key_metrics_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task_id,
                        it["symbol"],
                        it["exchange"],
                        it["score_total"],
                        dumps(it.get("breakdown", {})),
                        dumps(it.get("reasons", [])),
                        dumps(it.get("key_metrics", {})),
                    ),
                )
        return len(items)

    def list_results(self, task_id: str, limit: int = 200) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT symbol, exchange, score_total, breakdown_json, reasons_json, key_metrics_json
            FROM radar_results
            WHERE task_id=?
            ORDER BY score_total DESC
            LIMIT ?
            """,
            (task_id, limit),
        ).fetchall()

        import json

        return [
            {
                "symbol": r[0],
                "exchange": r[1],
                "score_total": r[2],
                "breakdown": json.loads(r[3]) if r[3] else {},
                "reasons": json.loads(r[4]) if r[4] else [],
                "key_metrics": json.loads(r[5]) if r[5] else {},
            }
            for r in rows
        ]


class RadarService:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def run(self, *, task_id: str, universe: dict, rules: list[dict]) -> dict:
        """Execute a radar scan and persist results.

        Current behavior (P0): only ranks instruments that already have enough local bars
        to compute a score.
        """

        instruments = self._select_universe(universe)

        out: list[dict] = []
        skipped_no_data = 0

        scoring = ScoringService(self._conn)

        for ins in instruments:
            ins_row = {
                "symbol": ins[0],
                "exchange": ins[1],
                "market": ins[2],
                "name": ins[3],
                "industry": ins[4],
            }

            rule_reasons: list[str] = []
            ok = True
            for rule in rules:
                matched, reason = _match_rule(ins_row, rule)
                if not matched:
                    ok = False
                    break
                if reason:
                    rule_reasons.append(reason)

            if not ok:
                continue

            try:
                s = scoring.calc(symbol=ins_row["symbol"], exchange=ins_row["exchange"], adj="RAW")
            except Exception:  # noqa: BLE001
                skipped_no_data += 1
                continue

            out.append(
                {
                    "symbol": ins_row["symbol"],
                    "exchange": ins_row["exchange"],
                    "score_total": s.score_total,
                    "breakdown": s.breakdown,
                    "reasons": rule_reasons + s.reasons,
                    "key_metrics": {
                        "name": ins_row.get("name"),
                        "industry": ins_row.get("industry"),
                        **s.metrics,
                    },
                }
            )

        repo = RadarRepo(self._conn)
        written = repo.write_results(task_id, out)

        return {"task_id": task_id, "count": written, "skipped_no_data": skipped_no_data}

    def _select_universe(self, universe: dict) -> list[tuple]:
        utype = (universe or {}).get("type", "ALL")

        if utype == "ALL":
            return self._conn.execute(
                "SELECT symbol, exchange, market, name, industry FROM instruments WHERE is_active=1"
            ).fetchall()

        if utype == "CUSTOM":
            # Custom symbol list: symbols can be ["600519", ...] or [{"symbol":"600519","exchange":"SSE"}, ...]
            symbols_in = (universe or {}).get("symbols") or []
            pairs: list[tuple[str, str]] = []
            for it in symbols_in:
                if isinstance(it, dict):
                    s = str(it.get("symbol") or "").strip().zfill(6)
                    ex = str(it.get("exchange") or "").strip().upper()
                    if s and ex:
                        pairs.append((s, ex))
                    continue
                s = str(it).strip()
                if not s:
                    continue
                s = s.zfill(6)
                # Heuristic for CN A-share exchange when not provided.
                ex = "SSE" if s.startswith(("6", "9")) else "SZSE"
                pairs.append((s, ex))

            if not pairs:
                return []

            # Build OR list: (symbol=? AND exchange=?) ...
            where = " OR ".join(["(symbol=? AND exchange=?)"] * len(pairs))
            params: list[str] = []
            for s, ex in pairs:
                params.extend([s, ex])

            return self._conn.execute(
                f"SELECT symbol, exchange, market, name, industry FROM instruments WHERE {where}",
                params,
            ).fetchall()

        if utype == "WATCHLIST":
            list_type = (universe or {}).get("list_type", "WATCH")
            return self._conn.execute(
                """
                SELECT i.symbol, i.exchange, i.market, i.name, i.industry
                FROM instruments i
                JOIN watchlist_items w
                  ON w.symbol=i.symbol AND w.exchange=i.exchange
                WHERE w.list_type=?
                """,
                (list_type,),
            ).fetchall()

        return []

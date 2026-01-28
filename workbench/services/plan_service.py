from __future__ import annotations

import sqlite3

from workbench.services.bars import BarsRepo
from workbench.services.plans import PlansRepo
from workbench.services.scoring import ScoringService
from workbench.services.scores import ScoresRepo


class PlanService:
    """Generate a minimal, editable trade plan (V1)."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def generate_and_save(self, *, symbol: str, exchange: str) -> dict:
        # Ensure we have a latest score (use existing if present; else compute and persist).
        latest_score = ScoresRepo(self._conn).latest(symbol=symbol, exchange=exchange)
        if not latest_score:
            latest_score = ScoringService(self._conn).calc_and_persist(symbol=symbol, exchange=exchange)

        bars = BarsRepo(self._conn).list_bars(symbol=symbol, exchange=exchange, adj="RAW", limit=60)
        if not bars:
            raise ValueError("no bars")

        last = float(bars[-1]["close"])

        # Basic plan heuristics.
        entry_low = round(last * 0.98, 2)
        entry_high = round(last * 1.02, 2)
        stop_loss = round(last * 0.95, 2)
        take_profit = round(last * 1.10, 2)

        score_total = float(latest_score["score_total"])
        position_sizing = max(0.05, min(0.25, round(score_total / 100.0 * 0.25, 4)))

        plan = {
            "direction": "LONG",
            "entry": {"type": "range", "low": entry_low, "high": entry_high, "note": "based on last close"},
            "exit_stop_loss": {"type": "price", "price": stop_loss},
            "exit_take_profit": {"type": "price", "price": take_profit},
            "position_sizing": position_sizing,
            "risk_notes": [
                "plan is a heuristic; edit before execution",
                "ensure liquidity and news risks are checked",
            ],
            "assumptions": ["local bars reflect tradable prices"],
        }

        based_on = {
            "score_id": latest_score["score_id"],
            "score_ruleset": latest_score.get("ruleset_version"),
            "trade_date": latest_score.get("trade_date"),
        }

        plan_id = PlansRepo(self._conn).create(symbol=symbol, exchange=exchange, plan_json=plan, based_on=based_on)

        return {
            "plan_id": plan_id,
            "symbol": symbol,
            "exchange": exchange,
            "plan": plan,
            "based_on": based_on,
        }

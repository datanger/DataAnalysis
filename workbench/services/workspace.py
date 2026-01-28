from __future__ import annotations

import sqlite3

from workbench.services.bars import BarsRepo
from workbench.services.capital_flow import CapitalFlowRepo
from workbench.services.fundamentals import FundamentalsRepo
from workbench.services.indicators import compute_indicators
from workbench.services.notes import NotesRepo
from workbench.services.plans import PlansRepo
from workbench.services.scores import ScoresRepo
from workbench.services.news import NewsRepo


class WorkspaceService:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def get_workspace(self, *, symbol: str, exchange: str, adj: str = "RAW") -> dict:
        bars_repo = BarsRepo(self._conn)
        bars = bars_repo.list_bars(symbol=symbol, exchange=exchange, adj=adj, limit=400)
        last_ingested = bars_repo.latest_ingested_at(symbol=symbol, exchange=exchange, adj=adj)

        indicators = compute_indicators(bars) if bars else []

        fundamentals_summary = FundamentalsRepo(self._conn).latest_daily(symbol=symbol, exchange=exchange)
        capital_flow = CapitalFlowRepo(self._conn).latest(symbol=symbol, exchange=exchange)
        latest_score = ScoresRepo(self._conn).latest(symbol=symbol, exchange=exchange)
        latest_plan = PlansRepo(self._conn).latest(symbol=symbol, exchange=exchange)
        notes = NotesRepo(self._conn).list(symbol=symbol, exchange=exchange, limit=20)
        news = NewsRepo(self._conn).list(symbol=symbol, exchange=exchange, limit=50)

        return {
            "price_bars": bars,
            "indicators": indicators,
            "fundamentals_summary": fundamentals_summary,
            "capital_flow": capital_flow,
            "news": news,
            "latest_score": latest_score,
            "latest_plan": latest_plan,
            "notes": notes,
            "data_version": {"bars_ingested_at": last_ingested},
        }

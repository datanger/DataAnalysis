from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass

import numpy as np

from workbench.services.bars import BarsRepo
from workbench.services.scores import ScoresRepo


RULESET_VERSION = "score/tech_v1"


@dataclass(frozen=True)
class ScoreResult:
    score_total: float
    breakdown: dict
    reasons: list[str]
    data_version: dict
    trade_date: str
    metrics: dict


class ScoringService:
    """Simple, explainable technical scoring (V1)."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def calc_and_persist(self, *, symbol: str, exchange: str, adj: str = "RAW") -> dict:
        res = self.calc(symbol=symbol, exchange=exchange, adj=adj)
        score_id = ScoresRepo(self._conn).insert(
            symbol=symbol,
            exchange=exchange,
            trade_date=res.trade_date,
            score_total=res.score_total,
            breakdown=res.breakdown,
            reasons=res.reasons,
            ruleset_version=RULESET_VERSION,
            data_version=res.data_version,
        )
        return {
            "score_id": score_id,
            "trade_date": res.trade_date,
            "score_total": res.score_total,
            "breakdown": res.breakdown,
            "reasons": res.reasons,
            "ruleset_version": RULESET_VERSION,
            "data_version": res.data_version,
            "metrics": res.metrics,
        }

    def calc(self, *, symbol: str, exchange: str, adj: str = "RAW") -> ScoreResult:
        bars = BarsRepo(self._conn).list_bars(symbol=symbol, exchange=exchange, adj=adj, limit=120)
        if len(bars) < 60:
            raise ValueError("not enough bars; ingest more history")

        closes = np.array([b["close"] for b in bars], dtype=float)
        amounts = np.array([b.get("amount") or 0.0 for b in bars], dtype=float)

        trade_date = bars[-1]["trade_date"]

        ma20 = float(np.mean(closes[-20:]))
        ma60 = float(np.mean(closes[-60:]))
        last = float(closes[-1])

        ret20 = float((closes[-1] / closes[-21]) - 1.0)
        vol20 = float(np.std(np.diff(np.log(closes[-21:]))))
        liq20 = float(np.mean(amounts[-20:]))

        score = 0.0
        breakdown: dict[str, float] = {}
        reasons: list[str] = []

        trend = 0.0
        if last > ma20:
            trend += 10.0
            reasons.append("price_above_ma20")
        if ma20 > ma60:
            trend += 10.0
            reasons.append("ma20_above_ma60")
        if last > ma60:
            trend += 10.0
            reasons.append("price_above_ma60")
        breakdown["trend"] = trend
        score += trend

        mom = 0.0
        if ret20 > 0:
            mom += 10.0
            reasons.append("ret20_positive")
        if ret20 > 0.10:
            mom += 10.0
            reasons.append("ret20_gt_10pct")
        breakdown["momentum"] = mom
        score += mom

        vol = 0.0
        if vol20 < 0.03:
            vol += 10.0
            reasons.append("vol20_low")
        elif vol20 < 0.06:
            vol += 5.0
            reasons.append("vol20_mid")
        breakdown["volatility"] = vol
        score += vol

        liq = 0.0
        if liq20 > 1e8:
            liq += 10.0
            reasons.append("liq20_gt_1e8")
        elif liq20 > 2e7:
            liq += 5.0
            reasons.append("liq20_gt_2e7")
        breakdown["liquidity"] = liq
        score += liq

        score_total = float(max(0.0, min(100.0, score * 2)))

        data_version = {
            "bars_trade_date": trade_date,
            "bars_count": int(len(bars)),
        }

        metrics = {
            "last_close": last,
            "ma20": ma20,
            "ma60": ma60,
            "ret20": ret20,
            "vol20": vol20,
            "liq20": liq20,
        }

        return ScoreResult(
            score_total=score_total,
            breakdown=breakdown,
            reasons=reasons,
            data_version=data_version,
            trade_date=trade_date,
            metrics=metrics,
        )

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


def _rolling_mean(x: np.ndarray, window: int) -> np.ndarray:
    if len(x) < window:
        return np.array([np.nan] * len(x), dtype=float)
    out = np.full(len(x), np.nan, dtype=float)
    cumsum = np.cumsum(np.insert(x, 0, 0.0))
    out[window - 1 :] = (cumsum[window:] - cumsum[:-window]) / window
    return out


def _rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    if len(close) < period + 1:
        return np.array([np.nan] * len(close), dtype=float)

    delta = np.diff(close)
    up = np.where(delta > 0, delta, 0.0)
    down = np.where(delta < 0, -delta, 0.0)

    rsi = np.full(len(close), np.nan, dtype=float)

    # Wilder's smoothing
    avg_gain = np.mean(up[:period])
    avg_loss = np.mean(down[:period])

    def _calc(g: float, l: float) -> float:
        if l == 0:
            return 100.0
        rs = g / l
        return 100.0 - (100.0 / (1.0 + rs))

    rsi[period] = _calc(avg_gain, avg_loss)

    for i in range(period + 1, len(close)):
        gain = up[i - 1]
        loss = down[i - 1]
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        rsi[i] = _calc(avg_gain, avg_loss)

    return rsi


def _ema(x: np.ndarray, span: int) -> np.ndarray:
    out = np.full(len(x), np.nan, dtype=float)
    if len(x) == 0:
        return out
    alpha = 2.0 / (span + 1.0)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = alpha * x[i] + (1 - alpha) * out[i - 1]
    return out


def compute_indicators(bars: list[dict]) -> list[dict]:
    """Compute a small set of common indicators.

    Returns an array of indicator objects with `series` aligned to `bars`.
    """

    if not bars:
        return []

    closes = np.array([float(b["close"]) for b in bars], dtype=float)
    dates = [b["trade_date"] for b in bars]

    ma20 = _rolling_mean(closes, 20)
    ma60 = _rolling_mean(closes, 60)
    rsi14 = _rsi(closes, 14)

    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    dif = ema12 - ema26
    dea = _ema(dif, 9)
    hist = (dif - dea) * 2.0

    def _pack(name: str, params: dict, values: np.ndarray) -> dict:
        series = []
        for d, v in zip(dates, values):
            if v == v:  # not nan
                series.append({"trade_date": d, "value": float(v)})
        last = series[-1]["value"] if series else None
        return {"name": name, "params": params, "last": last, "series": series}

    return [
        _pack("MA", {"period": 20}, ma20),
        _pack("MA", {"period": 60}, ma60),
        _pack("RSI", {"period": 14}, rsi14),
        {
            "name": "MACD",
            "params": {"fast": 12, "slow": 26, "signal": 9},
            "last": {
                "dif": float(dif[-1]) if dif[-1] == dif[-1] else None,
                "dea": float(dea[-1]) if dea[-1] == dea[-1] else None,
                "hist": float(hist[-1]) if hist[-1] == hist[-1] else None,
            },
            "series": [
                {
                    "trade_date": d,
                    "dif": float(a) if a == a else None,
                    "dea": float(b) if b == b else None,
                    "hist": float(c) if c == c else None,
                }
                for d, a, b, c in zip(dates, dif, dea, hist)
            ],
        },
    ]

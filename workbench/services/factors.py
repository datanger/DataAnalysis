from __future__ import annotations

import sqlite3
import numpy as np
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4
from workbench.jsonutil import dumps


class FactorService:
    """Service for factor engineering and factor library management."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def calculate_factors(
        self,
        *,
        symbol: str,
        exchange: str,
        start_date: str,
        end_date: str,
        factor_names: List[str],
    ) -> Dict[str, Any]:
        """Calculate factors for a symbol over a date range.

        Args:
            symbol: Stock symbol
            exchange: Exchange code
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            factor_names: List of factor names to calculate

        Returns:
            Dictionary with factor data
        """
        from workbench.services.bars import BarsRepo
        from workbench.services.fundamentals import FundamentalsRepo

        bars_repo = BarsRepo(self._conn)
        fundamentals_repo = FundamentalsRepo(self._conn)

        # Get price data
        bars = bars_repo.list_bars_range(
            symbol=symbol,
            exchange=exchange,
            start_date=start_date,
            end_date=end_date,
            adj="RAW"
        )

        if not bars:
            raise ValueError("No price data available")

        # Get fundamental data
        fundamentals = fundamentals_repo.list_daily_range(
            symbol=symbol,
            exchange=exchange,
            start_date=start_date,
            end_date=end_date
        )

        # Calculate factors
        factor_data = self._calculate_all_factors(bars, fundamentals)

        # Filter by requested factors
        result = {name: data for name, data in factor_data.items() if name in factor_names}

        return result

    def _calculate_all_factors(
        self,
        bars: List[Dict],
        fundamentals: List[Dict],
    ) -> Dict[str, Dict]:
        """Calculate all available factors."""
        result = {}

        # Technical factors
        result.update(self._calculate_technical_factors(bars))

        # Fundamental factors
        result.update(self._calculate_fundamental_factors(fundamentals))

        # Price-based factors
        result.update(self._calculate_price_factors(bars))

        return result

    def _calculate_technical_factors(self, bars: List[Dict]) -> Dict[str, Dict]:
        """Calculate technical factors."""
        factors = {}

        if len(bars) < 20:
            return factors

        closes = np.array([b["close"] for b in bars])
        highs = np.array([b["high"] for b in bars])
        lows = np.array([b["low"] for b in bars])
        volumes = np.array([b["volume"] for b in bars])

        # Moving Averages
        factors["MA5"] = {
            "values": self._moving_average(closes, 5).tolist(),
            "dates": [b["trade_date"] for b in bars],
            "description": "5-day moving average",
        }

        factors["MA10"] = {
            "values": self._moving_average(closes, 10).tolist(),
            "dates": [b["trade_date"] for b in bars],
            "description": "10-day moving average",
        }

        factors["MA20"] = {
            "values": self._moving_average(closes, 20).tolist(),
            "dates": [b["trade_date"] for b in bars],
            "description": "20-day moving average",
        }

        # RSI
        factors["RSI"] = {
            "values": self._calculate_rsi(closes, 14).tolist(),
            "dates": [b["trade_date"] for b in bars],
            "description": "14-day RSI",
        }

        # MACD
        ema12 = self._ema(closes, 12)
        ema26 = self._ema(closes, 26)
        macd_line = ema12 - ema26
        signal_line = self._ema(macd_line, 9)
        histogram = macd_line - signal_line

        factors["MACD"] = {
            "values": macd_line.tolist(),
            "signal_line": signal_line.tolist(),
            "histogram": histogram.tolist(),
            "dates": [b["trade_date"] for b in bars],
            "description": "MACD indicator",
        }

        # Bollinger Bands
        ma20 = self._moving_average(closes, 20)
        std20 = np.array([np.std(closes[max(0, i-19):i+1]) for i in range(len(closes))])
        upper_band = ma20 + 2 * std20
        lower_band = ma20 - 2 * std20

        factors["BB"] = {
            "upper": upper_band.tolist(),
            "middle": ma20.tolist(),
            "lower": lower_band.tolist(),
            "dates": [b["trade_date"] for b in bars],
            "description": "Bollinger Bands",
        }

        # Volume factors
        factors["VOL_MA"] = {
            "values": self._moving_average(volumes, 20).tolist(),
            "dates": [b["trade_date"] for b in bars],
            "description": "20-day average volume",
        }

        return factors

    def _calculate_fundamental_factors(self, fundamentals: List[Dict]) -> Dict[str, Dict]:
        """Calculate fundamental factors."""
        factors = {}

        if not fundamentals:
            return factors

        # Get latest fundamental data
        latest = fundamentals[-1] if fundamentals else {}

        # Valuation factors
        factors["PE"] = {
            "value": latest.get("pe_ttm"),
            "description": "Price-to-Earnings ratio",
        }

        factors["PB"] = {
            "value": latest.get("pb"),
            "description": "Price-to-Book ratio",
        }

        factors["PS"] = {
            "value": latest.get("ps_ttm"),
            "description": "Price-to-Sales ratio",
        }

        factors["PCF"] = {
            "value": latest.get("pcf"),
            "description": "Price-to-Cash-Flow ratio",
        }

        # Profitability factors
        factors["ROE"] = {
            "value": latest.get("roe"),
            "description": "Return on Equity",
        }

        factors["ROA"] = {
            "value": latest.get("roa"),
            "description": "Return on Assets",
        }

        factors["ROIC"] = {
            "value": latest.get("roic"),
            "description": "Return on Invested Capital",
        }

        # Growth factors
        factors["REVENUE_GROWTH"] = {
            "value": latest.get("revenue_growth"),
            "description": "Revenue growth rate",
        }

        factors["PROFIT_GROWTH"] = {
            "value": latest.get("profit_growth"),
            "description": "Net profit growth rate",
        }

        # Financial health
        factors["DEBT_RATIO"] = {
            "value": latest.get("debt_ratio"),
            "description": "Debt-to-Assets ratio",
        }

        factors["CURRENT_RATIO"] = {
            "value": latest.get("current_ratio"),
            "description": "Current ratio",
        }

        return factors

    def _calculate_price_factors(self, bars: List[Dict]) -> Dict[str, Dict]:
        """Calculate price-based factors."""
        factors = {}

        if len(bars) < 20:
            return factors

        closes = np.array([b["close"] for b in bars])
        highs = np.array([b["high"] for b in bars])
        lows = np.array([b["low"] for b in bars])
        volumes = np.array([b["volume"] for b in bars])

        # Price momentum
        factors["MOM_5"] = {
            "values": (closes / np.concatenate([[closes[0]], closes[:-1]]) - 1)[:-5].tolist(),
            "dates": [b["trade_date"] for b in bars[5:]],
            "description": "5-day price momentum",
        }

        factors["MOM_20"] = {
            "values": (closes / np.concatenate([[closes[0]], closes[:-1]]) - 1)[:-20].tolist(),
            "dates": [b["trade_date"] for b in bars[20:]],
            "description": "20-day price momentum",
        }

        # Mean reversion
        returns = np.diff(closes) / closes[:-1]
        factors["MEAN_REVERSION"] = {
            "values": (1 - np.abs(returns)).tolist(),
            "dates": [b["trade_date"] for b in bars[1:]],
            "description": "Mean reversion factor",
        }

        # Volatility
        returns_20d = np.array([
            np.std(closes[max(0, i-19):i+1]) / np.mean(closes[max(0, i-19):i+1])
            for i in range(len(closes))
        ])
        factors["VOLATILITY"] = {
            "values": returns_20d.tolist(),
            "dates": [b["trade_date"] for b in bars],
            "description": "20-day volatility",
        }

        # Volume-Price Trend
        vpt = np.cumsum((closes[1:] - closes[:-1]) / closes[:-1] * volumes[1:])
        vpt = np.concatenate([[0], vpt])
        factors["VPT"] = {
            "values": vpt.tolist(),
            "dates": [b["trade_date"] for b in bars],
            "description": "Volume Price Trend",
        }

        return factors

    def _moving_average(self, data: np.ndarray, window: int) -> np.ndarray:
        """Calculate moving average."""
        return np.convolve(data, np.ones(window) / window, mode="valid")

    def _ema(self, data: np.ndarray, span: int) -> np.ndarray:
        """Calculate exponential moving average."""
        alpha = 2 / (span + 1)
        ema = np.zeros_like(data)
        ema[0] = data[0]
        for i in range(1, len(data)):
            ema[i] = alpha * data[i] + (1 - alpha) * ema[i - 1]
        return ema

    def _calculate_rsi(self, prices: np.ndarray, window: int) -> np.ndarray:
        """Calculate RSI."""
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gains = np.convolve(gains, np.ones(window) / window, mode="valid")
        avg_losses = np.convolve(losses, np.ones(window) / window, mode="valid")

        rs = avg_gains / (avg_losses + 1e-10)
        rsi = 100 - (100 / (1 + rs))

        # Pad with NaN to match input length
        return np.concatenate([np.full(window - 1, np.nan), rsi])

    def standardize_factors(
        self,
        factor_values: List[float],
        method: str = "zscore",
    ) -> List[float]:
        """Standardize factor values.

        Args:
            factor_values: List of factor values
            method: Standardization method ("zscore", "rank", "winsorize")

        Returns:
            Standardized factor values
        """
        values = np.array(factor_values)
        values = values[~np.isnan(values)]  # Remove NaN values

        if len(values) == 0:
            return factor_values

        if method == "zscore":
            mean_val = np.mean(values)
            std_val = np.std(values)
            if std_val == 0:
                return [0.0] * len(factor_values)
            return ((np.array(factor_values) - mean_val) / std_val).tolist()

        elif method == "rank":
            ranks = np.argsort(np.argsort(factor_values))
            return (ranks / len(factor_values)).tolist()

        elif method == "winsorize":
            q5 = np.percentile(values, 5)
            q95 = np.percentile(values, 95)
            winsorized = np.clip(factor_values, q5, q95)
            return winsorized.tolist()

        return factor_values

    def neutralize_factors(
        self,
        factor_values: List[float],
        market_values: List[float],
    ) -> List[float]:
        """Neutralize factor values against market values (e.g., beta neutralization).

        Args:
            factor_values: Factor values
            market_values: Market benchmark values

        Returns:
            Neutralized factor values
        """
        factor = np.array(factor_values)
        market = np.array(market_values)

        # Remove NaN values
        valid_mask = ~(np.isnan(factor) | np.isnan(market))
        factor_valid = factor[valid_mask]
        market_valid = market[valid_mask]

        if len(factor_valid) < 10:
            return factor_values

        # Calculate beta
        cov_matrix = np.cov(factor_valid, market_valid)
        beta = cov_matrix[0, 1] / np.var(market_valid)

        # Remove beta component
        factor_mean = np.mean(factor_valid)
        market_mean = np.mean(market_valid)
        neutralized = factor - beta * (market - market_mean) - factor_mean

        # Fill back into original array
        result = factor.copy()
        result[valid_mask] = neutralized

        return result.tolist()

    def analyze_factor(
        self,
        factor_name: str,
        factor_values: List[float],
        returns: List[float],
    ) -> Dict[str, Any]:
        """Analyze factor effectiveness.

        Args:
            factor_name: Name of the factor
            factor_values: Factor values
            returns: Corresponding returns

        Returns:
            Dictionary with analysis results
        """
        # Remove NaN values
        combined = list(zip(factor_values, returns))
        combined = [(f, r) for f, r in combined if not (np.isnan(f) or np.isnan(r))]

        if len(combined) < 10:
            return {
                "factor_name": factor_name,
                "ic": np.nan,
                "ic_ir": np.nan,
                "hit_rate": np.nan,
                "mean_forward_return": np.nan,
                "std_forward_return": np.nan,
            }

        factor_vals = np.array([c[0] for c in combined])
        return_vals = np.array([c[1] for c in combined])

        # Information Coefficient (IC) - correlation between factor and returns
        ic = np.corrcoef(factor_vals, return_vals)[0, 1]

        # IC IR (Information Ratio) - mean IC / std IC
        ic_mean = np.mean(ic) if isinstance(ic, np.ndarray) else ic
        ic_std = np.std(ic) if isinstance(ic, np.ndarray) else 0
        ic_ir = ic_mean / ic_std if ic_std > 0 else np.nan

        # Hit rate - percentage of times factor correctly predicts direction
        sign_factor = np.sign(factor_vals)
        sign_returns = np.sign(return_vals)
        hit_rate = np.mean(sign_factor == sign_returns)

        # Forward return statistics
        mean_forward_return = np.mean(return_vals)
        std_forward_return = np.std(return_vals)

        return {
            "factor_name": factor_name,
            "ic": float(ic) if not np.isnan(ic) else np.nan,
            "ic_ir": float(ic_ir) if not np.isnan(ic_ir) else np.nan,
            "hit_rate": float(hit_rate),
            "mean_forward_return": float(mean_forward_return),
            "std_forward_return": float(std_forward_return),
            "count": len(combined),
        }

    def save_factor_values(
        self,
        symbol: str,
        exchange: str,
        factor_name: str,
        values: Dict[str, List[float]],
    ) -> str:
        """Save factor values to database."""
        factor_id = str(uuid4())
        now = datetime.now().isoformat(timespec="seconds")

        with self._conn:
            self._conn.execute(
                """
                INSERT INTO factor_values(
                    factor_id, symbol, exchange, factor_name,
                    values_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    factor_id,
                    symbol,
                    exchange,
                    factor_name,
                    dumps(values),
                    now,
                ),
            )

        return factor_id

    def get_factor_values(
        self,
        symbol: str,
        exchange: str,
        factor_name: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Optional[Dict]:
        """Get factor values from database."""
        query = """
            SELECT values_json, created_at
            FROM factor_values
            WHERE symbol=? AND exchange=? AND factor_name=?
        """
        params = [symbol, exchange, factor_name]

        if start_date:
            query += " AND trade_date>=?"
            params.append(start_date)

        if end_date:
            query += " AND trade_date<=?"
            params.append(end_date)

        query += " ORDER BY created_at DESC LIMIT 1"

        row = self._conn.execute(query, params).fetchone()

        if not row:
            return None

        import json

        return {
            "factor_name": factor_name,
            "values": json.loads(row[0]),
            "created_at": row[1],
        }

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, Tuple, List
from workbench.jsonutil import dumps


class BacktestService:
    """Service for backtesting strategies on historical data."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def run_backtest(
        self,
        *,
        symbol: str,
        exchange: str,
        start_date: str,  # YYYY-MM-DD
        end_date: str,    # YYYY-MM-DD
        initial_cash: float = 1000000,
        signal_type: str = "score_threshold",  # "score_threshold", "price_ma", "manual"
        signal_params: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Run a backtest on historical data.

        Args:
            symbol: Stock symbol to backtest
            exchange: Exchange code
            start_date: Start date for backtest (YYYY-MM-DD)
            end_date: End date for backtest (YYYY-MM-DD)
            initial_cash: Initial cash amount
            signal_type: Type of trading signal
            signal_params: Parameters for the signal

        Returns:
            Dictionary containing backtest results and metrics
        """
        from workbench.services.bars import BarsRepo
        from workbench.services.scores import ScoresRepo

        bars_repo = BarsRepo(self._conn)
        scores_repo = ScoresRepo(self._conn)

        # Get historical bars
        bars = bars_repo.list_bars_range(
            symbol=symbol,
            exchange=exchange,
            start_date=start_date,
            end_date=end_date,
            adj="RAW"
        )

        if not bars or len(bars) < 2:
            raise ValueError("Not enough historical data for backtest")

        # Get historical scores
        scores = scores_repo.list_range(
            symbol=symbol,
            exchange=exchange,
            start_date=start_date,
            end_date=end_date
        )

        # Run backtest simulation
        trades, equity_curve, metrics = self._simulate_trading(
            bars=bars,
            scores=scores,
            initial_cash=initial_cash,
            signal_type=signal_type,
            signal_params=signal_params or {}
        )

        # Generate report
        report = {
            "backtest_id": f"bt_{symbol}_{start_date}_{end_date}",
            "symbol": symbol,
            "exchange": exchange,
            "period": {
                "start_date": start_date,
                "end_date": end_date,
                "trading_days": len(bars),
            },
            "parameters": {
                "initial_cash": initial_cash,
                "signal_type": signal_type,
                "signal_params": signal_params or {},
            },
            "metrics": metrics,
            "trades": trades,
            "equity_curve": equity_curve,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        }

        return report

    def _simulate_trading(
        self,
        *,
        bars: list[Dict],
        scores: list[Dict],
        initial_cash: float,
        signal_type: str,
        signal_params: Dict[str, Any],
    ) -> Tuple[List[Dict], List[Dict], Dict[str, Any]]:
        """Simulate trading based on signals.

        Returns:
            (trades, equity_curve, metrics)
        """
        trades = []
        equity_curve = []

        cash = initial_cash
        position = 0
        position_value = 0
        total_value = initial_cash

        # Create score lookup
        score_lookup = {s["trade_date"]: s for s in scores}

        # Trading parameters
        threshold = signal_params.get("threshold", 70)  # Buy if score >= 70
        position_size = signal_params.get("position_size", 0.5)  # 50% of portfolio per trade
        stop_loss = signal_params.get("stop_loss", 0.1)  # 10% stop loss
        take_profit = signal_params.get("take_profit", 0.2)  # 20% take profit

        entry_price = 0
        for i, bar in enumerate(bars):
            date = bar["trade_date"]
            close_price = float(bar["close"])
            high_price = float(bar["high"])
            low_price = float(bar["low"])

            # Calculate position value
            position_value = position * close_price
            total_value = cash + position_value

            # Check for exit signals
            if position > 0:
                # Stop loss check
                if entry_price and (close_price <= entry_price * (1 - stop_loss)):
                    # Sell at stop loss
                    sell_price = close_price
                    pnl = (sell_price - entry_price) * position
                    cash += position * sell_price

                    trades.append({
                        "trade_id": f"exit_{len(trades)}",
                        "entry_date": bars[i - 1]["trade_date"],
                        "exit_date": date,
                        "side": "SELL",
                        "entry_price": entry_price,
                        "exit_price": sell_price,
                        "qty": position,
                        "pnl": pnl,
                        "pnl_pct": pnl / (entry_price * position),
                        "reason": "STOP_LOSS"
                    })

                    position = 0
                    entry_price = 0

                # Take profit check
                elif entry_price and (close_price >= entry_price * (1 + take_profit)):
                    # Sell at take profit
                    sell_price = close_price
                    pnl = (sell_price - entry_price) * position
                    cash += position * sell_price

                    trades.append({
                        "trade_id": f"exit_{len(trades)}",
                        "entry_date": bars[i - 1]["trade_date"],
                        "exit_date": date,
                        "side": "SELL",
                        "entry_price": entry_price,
                        "exit_price": sell_price,
                        "qty": position,
                        "pnl": pnl,
                        "pnl_pct": pnl / (entry_price * position),
                        "reason": "TAKE_PROFIT"
                    })

                    position = 0
                    entry_price = 0

            # Check entry signals
            if position == 0:
                score = score_lookup.get(date, {}).get("score_total", 0)

                if signal_type == "score_threshold" and score >= threshold:
                    # Buy signal
                    target_value = total_value * position_size
                    qty = int(target_value / close_price / 100) * 100  # Round to lots

                    if qty > 0 and cash >= qty * close_price:
                        cash -= qty * close_price
                        position = qty
                        entry_price = close_price

                        trades.append({
                            "trade_id": f"entry_{len(trades)}",
                            "entry_date": date,
                            "side": "BUY",
                            "entry_price": entry_price,
                            "qty": qty,
                            "reason": "SCORE_THRESHOLD"
                        })

            # Record equity curve
            equity_curve.append({
                "date": date,
                "close": close_price,
                "cash": cash,
                "position": position,
                "position_value": position_value,
                "total_value": cash + position_value,
                "position_pct": (position * close_price / (cash + position * close_price)) if cash + position * close_price > 0 else 0,
            })

        # Close remaining position
        if position > 0 and bars:
            last_bar = bars[-1]
            sell_price = float(last_bar["close"])
            pnl = (sell_price - entry_price) * position
            cash += position * sell_price

            trades.append({
                "trade_id": f"exit_{len(trades)}",
                "entry_date": bars[-2]["trade_date"],
                "exit_date": last_bar["trade_date"],
                "side": "SELL",
                "entry_price": entry_price,
                "exit_price": sell_price,
                "qty": position,
                "pnl": pnl,
                "pnl_pct": pnl / (entry_price * position),
                "reason": "END_OF_PERIOD"
            })

        # Calculate metrics
        metrics = self._calculate_metrics(equity_curve, initial_cash)

        return trades, equity_curve, metrics

    def _calculate_metrics(self, equity_curve: List[Dict], initial_cash: float) -> Dict[str, Any]:
        """Calculate backtest performance metrics."""
        if not equity_curve:
            return {}

        first_value = equity_curve[0]["total_value"]
        last_value = equity_curve[-1]["total_value"]

        # Total return
        total_return = (last_value - initial_cash) / initial_cash

        # Calculate daily returns
        daily_returns = []
        for i in range(1, len(equity_curve)):
            prev_value = equity_curve[i - 1]["total_value"]
            curr_value = equity_curve[i]["total_value"]
            if prev_value > 0:
                daily_return = (curr_value - prev_value) / prev_value
                daily_returns.append(daily_return)

        # Annualized return (assuming 252 trading days)
        trading_days = len(equity_curve)
        years = trading_days / 252
        annualized_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0

        # Volatility
        if daily_returns:
            mean_return = sum(daily_returns) / len(daily_returns)
            variance = sum([(r - mean_return) ** 2 for r in daily_returns]) / len(daily_returns)
            daily_volatility = variance ** 0.5
            annualized_volatility = daily_volatility * (252 ** 0.5)
        else:
            annualized_volatility = 0

        # Sharpe ratio (assuming 0% risk-free rate)
        sharpe_ratio = annualized_return / annualized_volatility if annualized_volatility > 0 else 0

        # Maximum drawdown
        peak = equity_curve[0]["total_value"]
        max_drawdown = 0
        drawdown_periods = []

        for point in equity_curve:
            if point["total_value"] > peak:
                peak = point["total_value"]

            drawdown = (peak - point["total_value"]) / peak
            if drawdown > max_drawdown:
                max_drawdown = drawdown

            drawdown_periods.append({
                "date": point["date"],
                "drawdown": drawdown,
                "value": point["total_value"]
            })

        # Find worst drawdown period
        worst_drawdown = max(drawdown_periods, key=lambda x: x["drawdown"]) if drawdown_periods else None

        # Win rate
        winning_trades = sum([1 for r in daily_returns if r > 0])
        win_rate = winning_trades / len(daily_returns) * 100 if daily_returns else 0

        # CAGR
        cagr = ((last_value / initial_cash) ** (252 / trading_days) - 1) if trading_days > 0 else 0

        return {
            "total_return": total_return,
            "total_return_pct": total_return * 100,
            "annualized_return": annualized_return,
            "annualized_return_pct": annualized_return * 100,
            "annualized_volatility": annualized_volatility,
            "annualized_volatility_pct": annualized_volatility * 100,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": max_drawdown,
            "max_drawdown_pct": max_drawdown * 100,
            "worst_drawdown_date": worst_drawdown["date"] if worst_drawdown else None,
            "win_rate": win_rate,
            "cagr": cagr,
            "cagr_pct": cagr * 100,
            "final_value": last_value,
            "trading_days": trading_days,
            "avg_daily_return": sum(daily_returns) / len(daily_returns) if daily_returns else 0,
        }

    def compare_strategies(
        self,
        *,
        symbol: str,
        exchange: str,
        start_date: str,
        end_date: str,
        strategies: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Compare multiple strategies side by side."""
        results = []

        for strategy in strategies:
            result = self.run_backtest(
                symbol=symbol,
                exchange=exchange,
                start_date=start_date,
                end_date=end_date,
                initial_cash=strategy.get("initial_cash", 1000000),
                signal_type=strategy.get("signal_type", "score_threshold"),
                signal_params=strategy.get("signal_params", {}),
            )
            results.append({
                "strategy_name": strategy.get("name", "Unnamed"),
                "metrics": result["metrics"],
                "trade_count": len(result["trades"]),
            })

        # Find best strategy
        best_by_return = max(results, key=lambda x: x["metrics"]["total_return_pct"])
        best_by_sharpe = max(results, key=lambda x: x["metrics"]["sharpe_ratio"])

        comparison = {
            "symbol": symbol,
            "exchange": exchange,
            "period": {
                "start_date": start_date,
                "end_date": end_date,
            },
            "strategies": results,
            "best_by_return": {
                "name": best_by_return["strategy_name"],
                "total_return_pct": best_by_return["metrics"]["total_return_pct"],
            },
            "best_by_sharpe": {
                "name": best_by_sharpe["strategy_name"],
                "sharpe_ratio": best_by_sharpe["metrics"]["sharpe_ratio"],
            },
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        }

        return comparison

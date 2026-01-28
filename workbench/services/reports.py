from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any
from workbench.jsonutil import dumps


class ReportsService:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def generate_stock_report(self, symbol: str, exchange: str, report_type: str = "comprehensive") -> dict[str, Any]:
        """Generate a comprehensive stock research report."""
        from workbench.services.workspace import WorkspaceService
        from workbench.services.scores import ScoresRepo
        from workbench.services.plans import PlansRepo
        from workbench.services.notes import NotesRepo
        from workbench.services.bars import BarsRepo

        workspace = WorkspaceService(self._conn)
        scores_repo = ScoresRepo(self._conn)
        plans_repo = PlansRepo(self._conn)
        notes_repo = NotesRepo(self._conn)
        bars_repo = BarsRepo(self._conn)

        # Get workspace data
        ws_data = workspace.get_workspace(symbol=symbol, exchange=exchange)

        # Get historical scores
        scores = scores_repo.list(symbol=symbol, exchange=exchange, limit=10)

        # Get latest plan
        plan = plans_repo.latest(symbol=symbol, exchange=exchange)

        # Get notes
        notes = notes_repo.list(symbol=symbol, exchange=exchange, limit=5)

        # Calculate price performance
        bars = bars_repo.list_bars(symbol=symbol, exchange=exchange, adj="RAW", limit=250)
        performance = {}
        if len(bars) >= 2:
            latest_price = bars[-1]["close"]
            week_ago_price = bars[-6]["close"] if len(bars) >= 6 else bars[0]["close"]
            month_ago_price = bars[-22]["close"] if len(bars) >= 22 else bars[0]["close"]

            performance = {
                "1_week": ((latest_price - week_ago_price) / week_ago_price * 100) if week_ago_price else None,
                "1_month": ((latest_price - month_ago_price) / month_ago_price * 100) if month_ago_price else None,
                "ytd": ((latest_price - bars[0]["close"]) / bars[0]["close"] * 100) if bars[0]["close"] else None,
            }

        # Generate report sections
        report = {
            "report_id": f"stock_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "symbol": symbol,
            "exchange": exchange,
            "report_type": report_type,
            "sections": {
                "executive_summary": self._generate_executive_summary(ws_data, scores),
                "technical_analysis": self._generate_technical_analysis(ws_data, bars),
                "fundamental_analysis": self._generate_fundamental_analysis(ws_data),
                "capital_flow": self._generate_capital_flow_analysis(ws_data),
                "score_analysis": self._generate_score_analysis(scores),
                "plan_summary": self._generate_plan_summary(plan),
                "notes_summary": self._generate_notes_summary(notes),
                "performance": performance,
                "risk_factors": self._generate_risk_factors(ws_data, scores),
                "recommendations": self._generate_recommendations(ws_data, scores, plan),
            }
        }

        return report

    def generate_portfolio_report(self, portfolio_id: str, report_type: str = "monthly") -> dict[str, Any]:
        """Generate a portfolio performance report."""
        from workbench.services.portfolios import PortfolioRepo
        from workbench.services.sim import LedgerRepo

        portfolio_repo = PortfolioRepo(self._conn)
        ledger_repo = LedgerRepo(self._conn)

        # Get portfolio details
        portfolio = portfolio_repo.get(portfolio_id)
        positions = portfolio_repo.get_positions(portfolio_id)

        # Get recent trades
        trades = ledger_repo.list_trades(portfolio_id=portfolio_id, limit=100)
        orders = ledger_repo.list_orders(portfolio_id=portfolio_id, limit=100)

        # Calculate metrics
        metrics = self._calculate_portfolio_metrics(portfolio, positions, trades)

        # Get date range for report
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30 if report_type == "monthly" else 90)

        report = {
            "report_id": f"portfolio_{portfolio_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "portfolio_id": portfolio_id,
            "report_type": report_type,
            "period": {
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d"),
            },
            "portfolio_summary": {
                "name": portfolio["name"],
                "base_currency": portfolio["base_currency"],
                "initial_cash": portfolio["initial_cash"],
                "current_cash": portfolio["cash"],
                "total_positions_value": metrics.get("total_positions_value", 0),
                "total_equity": metrics.get("total_equity", 0),
            },
            "performance": {
                "total_return": metrics.get("total_return", 0),
                "total_return_pct": metrics.get("total_return_pct", 0),
                "win_rate": metrics.get("win_rate", 0),
                "profit_factor": metrics.get("profit_factor", 0),
            },
            "positions": positions,
            "recent_trades": trades[-20:],  # Last 20 trades
            "orders_summary": {
                "total_orders": len(orders),
                "filled_orders": len([o for o in orders if o["status"] == "FILLED"]),
                "cancelled_orders": len([o for o in orders if o["status"] == "CANCELLED"]),
            },
            "risk_metrics": {
                "position_concentration": metrics.get("position_concentration", {}),
                "sector_exposure": metrics.get("sector_exposure", {}),
            }
        }

        return report

    def generate_trade_report(self, portfolio_id: str, start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
        """Generate a trading activity report."""
        from workbench.services.sim import LedgerRepo

        ledger_repo = LedgerRepo(self._conn)

        # Use default date range if not provided
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

        # Get trades in date range
        trades = ledger_repo.list_trades(portfolio_id=portfolio_id, limit=500)

        # Filter by date
        filtered_trades = []
        for trade in trades:
            trade_date = trade["filled_at"][:10]  # Extract date part
            if start_date <= trade_date <= end_date:
                filtered_trades.append(trade)

        # Calculate metrics
        total_trades = len(filtered_trades)
        profitable_trades = len([t for t in filtered_trades if t.get("unrealized_pnl", 0) > 0])
        win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0

        total_fees = sum([t.get("fee", 0) for t in filtered_trades])
        total_pnl = sum([t.get("realized_pnl", 0) + t.get("unrealized_pnl", 0) for t in filtered_trades])

        # Group by symbol
        symbol_summary = {}
        for trade in filtered_trades:
            sym = trade["symbol"]
            if sym not in symbol_summary:
                symbol_summary[sym] = {
                    "trade_count": 0,
                    "total_pnl": 0,
                    "total_fees": 0,
                    "avg_fill_price": 0,
                }

            s = symbol_summary[sym]
            s["trade_count"] += 1
            s["total_pnl"] += trade.get("realized_pnl", 0) + trade.get("unrealized_pnl", 0)
            s["total_fees"] += trade.get("fee", 0)

        # Calculate average prices
        for sym in symbol_summary:
            sym_trades = [t for t in filtered_trades if t["symbol"] == sym]
            if sym_trades:
                total_qty = sum([t["fill_qty"] for t in sym_trades])
                total_value = sum([t["fill_price"] * t["fill_qty"] for t in sym_trades])
                symbol_summary[sym]["avg_fill_price"] = total_value / total_qty if total_qty > 0 else 0

        report = {
            "report_id": f"trade_{portfolio_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "portfolio_id": portfolio_id,
            "period": {
                "start_date": start_date,
                "end_date": end_date,
            },
            "summary": {
                "total_trades": total_trades,
                "profitable_trades": profitable_trades,
                "win_rate": win_rate,
                "total_pnl": total_pnl,
                "total_fees": total_fees,
                "avg_trade_size": total_pnl / total_trades if total_trades > 0 else 0,
            },
            "trades": filtered_trades,
            "by_symbol": symbol_summary,
        }

        return report

    def _generate_executive_summary(self, ws_data: dict, scores: list) -> dict:
        """Generate executive summary section."""
        latest_score = scores[0] if scores else None
        score_total = latest_score.get("score_total", 0) if latest_score else 0

        summary = {
            "overall_score": score_total,
            "score_level": "Strong" if score_total >= 80 else "Good" if score_total >= 60 else "Weak",
            "key_highlights": [],
            "key_concerns": [],
        }

        if score_total >= 80:
            summary["key_highlights"].append("Strong technical momentum")
        elif score_total < 60:
            summary["key_concerns"].append("Weak technical signals")

        return summary

    def _generate_technical_analysis(self, ws_data: dict, bars: list) -> dict:
        """Generate technical analysis section."""
        indicators = ws_data.get("indicators", [])

        tech_signals = []
        for ind in indicators:
            if ind.get("indicator_name") == "RSI":
                rsi = ind.get("value_json", {}).get("rsi", 0)
                if rsi > 70:
                    tech_signals.append({"signal": "RSI Overbought", "value": rsi, "level": "Risk"})
                elif rsi < 30:
                    tech_signals.append({"signal": "RSI Oversold", "value": rsi, "level": "Opportunity"})

        return {
            "signals": tech_signals,
            "trend": "Bullish" if bars and bars[-1]["close"] > bars[-20]["close"] else "Bearish" if bars else "Unknown",
            "support_level": self._calculate_support(bars) if bars else None,
            "resistance_level": self._calculate_resistance(bars) if bars else None,
        }

    def _generate_fundamental_analysis(self, ws_data: dict) -> dict:
        """Generate fundamental analysis section."""
        fundamentals = ws_data.get("fundamentals_summary") or {}

        return {
            "valuation": {
                "pe": fundamentals.get("pe_ttm"),
                "pb": fundamentals.get("pb"),
                "ps": fundamentals.get("ps_ttm"),
            },
            "profitability": {
                "roe": fundamentals.get("roe"),
                "gross_margin": fundamentals.get("gross_margin"),
                "net_profit_margin": fundamentals.get("net_profit_margin"),
            },
            "financial_health": {
                "debt_ratio": fundamentals.get("debt_ratio"),
            }
        }

    def _generate_capital_flow_analysis(self, ws_data: dict) -> dict:
        """Generate capital flow analysis section."""
        capital_flow = ws_data.get("capital_flow") or {}

        return {
            "net_inflow": capital_flow.get("net_inflow"),
            "main_inflow": capital_flow.get("main_inflow"),
            "northbound_net": capital_flow.get("northbound_net"),
            "flow_trend": "Positive" if capital_flow.get("net_inflow", 0) > 0 else "Negative",
        }

    def _generate_score_analysis(self, scores: list) -> dict:
        """Generate score analysis section."""
        if not scores:
            return {"message": "No score history available"}

        latest = scores[0]
        return {
            "current_score": latest.get("score_total", 0),
            "breakdown": latest.get("breakdown_json", {}),
            "reasons": latest.get("reasons_json", []),
            "score_trend": "Improving" if len(scores) > 1 and scores[0].get("score_total", 0) > scores[1].get("score_total", 0) else "Stable",
        }

    def _generate_plan_summary(self, plan: dict | None) -> dict:
        """Generate plan summary section."""
        if not plan:
            return {"message": "No active plan"}

        return {
            "plan_id": plan.get("plan_id"),
            "direction": plan.get("plan_json", {}).get("direction"),
            "position_sizing": plan.get("plan_json", {}).get("position_sizing"),
            "risk_notes": plan.get("plan_json", {}).get("risk_notes", []),
        }

    def _generate_notes_summary(self, notes: list) -> dict:
        """Generate notes summary section."""
        return {
            "note_count": len(notes),
            "latest_note": notes[0] if notes else None,
        }

    def _generate_risk_factors(self, ws_data: dict, scores: list) -> list:
        """Generate risk factors section."""
        risks = []

        if scores and scores[0].get("score_total", 0) < 60:
            risks.append("Low technical score indicates potential weakness")

        capital_flow = ws_data.get("capital_flow", {})
        if capital_flow.get("net_inflow", 0) < 0:
            risks.append("Negative capital flow suggests selling pressure")

        return risks

    def _generate_recommendations(self, ws_data: dict, scores: list, plan: dict | None) -> list:
        """Generate recommendations section."""
        recommendations = []

        if scores and scores[0].get("score_total", 0) >= 70:
            recommendations.append("Consider increasing position size")
        elif scores and scores[0].get("score_total", 0) < 50:
            recommendations.append("Consider reducing position or exiting")

        if plan:
            recommendations.append(f"Follow planned entry/exit criteria")

        return recommendations

    def _calculate_support(self, bars: list) -> float | None:
        """Calculate support level (simplified)."""
        if not bars or len(bars) < 20:
            return None

        recent_lows = [b["low"] for b in bars[-20:]]
        return min(recent_lows)

    def _calculate_resistance(self, bars: list) -> float | None:
        """Calculate resistance level (simplified)."""
        if not bars or len(bars) < 20:
            return None

        recent_highs = [b["high"] for b in bars[-20:]]
        return max(recent_highs)

    def _calculate_portfolio_metrics(self, portfolio: dict, positions: list, trades: list) -> dict:
        """Calculate portfolio performance metrics."""
        total_positions_value = sum([p.get("market_value", 0) for p in positions])
        total_equity = portfolio.get("cash", 0) + total_positions_value
        initial_value = portfolio.get("initial_cash", 0)

        total_return = total_equity - initial_value
        total_return_pct = (total_return / initial_value * 100) if initial_value > 0 else 0

        # Calculate win rate
        winning_trades = len([t for t in trades if t.get("realized_pnl", 0) > 0])
        total_trades = len(trades)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

        return {
            "total_positions_value": total_positions_value,
            "total_equity": total_equity,
            "total_return": total_return,
            "total_return_pct": total_return_pct,
            "win_rate": win_rate,
            "profit_factor": 0,  # Simplified
            "position_concentration": {},
            "sector_exposure": {},
        }

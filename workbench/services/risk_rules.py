from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta
from typing import Any


class RiskRulesRepo:
    """Repository for managing risk rules configuration."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def get_all_rules(self) -> dict[str, Any]:
        """Get all risk rules with their values."""
        rules: dict[str, Any] = {
            # Position rules
            "max_position_per_symbol": float(os.getenv("RISK_MAX_POSITION_PER_SYMBOL", "0.25")),
            "max_position_per_sector": float(os.getenv("RISK_MAX_POSITION_PER_SECTOR", "0.40")),
            "max_position_single_stock": float(os.getenv("RISK_MAX_POSITION_SINGLE_STOCK", "0.20")),

            # Cash rules
            "min_cash_ratio": float(os.getenv("RISK_MIN_CASH_RATIO", "0.05")),
            "min_cash_reserve": float(os.getenv("RISK_MIN_CASH_RESERVE", "50000")),

            # Order rules
            "max_order_value": float(os.getenv("RISK_MAX_ORDER_VALUE", "200000")),
            "min_order_value": float(os.getenv("RISK_MIN_ORDER_VALUE", "1000")),
            "max_orders_per_day": int(os.getenv("RISK_MAX_ORDERS_PER_DAY", "50")),
            "max_order_frequency_seconds": int(os.getenv("RISK_MAX_ORDER_FREQUENCY_SECONDS", "60")),

            # Price rules
            "price_deviation_limit": float(os.getenv("RISK_PRICE_DEVIATION_LIMIT", "0.03")),
            "max_price_change_pct": float(os.getenv("RISK_MAX_PRICE_CHANGE_PCT", "0.10")),
            "ban_trading_on_limit_up": os.getenv("RISK_BAN_TRADING_ON_LIMIT_UP", "false").lower() == "true",
            "ban_trading_on_limit_down": os.getenv("RISK_BAN_TRADING_ON_LIMIT_DOWN", "false").lower() == "true",

            # Volume rules
            "lot_size": int(os.getenv("RISK_LOT_SIZE", "100")),
            "max_daily_trading_value": float(os.getenv("RISK_MAX_DAILY_TRADING_VALUE", "1000000")),

            # Other rules
            "stop_loss_check": os.getenv("RISK_STOP_LOSS_CHECK", "false").lower() == "true",
            "profit_target_check": os.getenv("RISK_PROFIT_TARGET_CHECK", "false").lower() == "true",
        }

        # Overlay DB overrides (written by update_rule). Keep parsing robust and type-aware.
        try:
            rows = self._conn.execute("SELECT rule_name, value FROM risk_rules").fetchall()
        except sqlite3.Error:
            rows = []

        for name, raw in rows:
            key = str(name)
            val = str(raw)
            if key not in rules:
                # Allow forward-compatible rules without breaking older clients.
                rules[key] = val
                continue

            default = rules[key]
            try:
                if isinstance(default, bool):
                    rules[key] = val.lower() in ("1", "true", "yes", "y", "on")
                elif isinstance(default, int) and not isinstance(default, bool):
                    rules[key] = int(float(val))
                elif isinstance(default, float):
                    rules[key] = float(val)
                else:
                    rules[key] = val
            except Exception:
                # Keep default on parse errors.
                pass

        return rules

    def update_rule(self, rule_name: str, value: Any) -> None:
        """Update a single risk rule value."""
        # For demo purposes, we'll store in environment-like table
        # In production, this would be in a proper config store
        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO risk_rules (rule_name, value, updated_at)
                VALUES (?, ?, ?)
                """,
                (rule_name, str(value), datetime.now().isoformat(timespec="seconds"))
            )

    def get_recent_trades_count(self, portfolio_id: str, hours: int = 24) -> int:
        """Get count of trades in recent hours."""
        since = (datetime.now() - timedelta(hours=hours)).isoformat()
        row = self._conn.execute(
            """
            SELECT COUNT(1) FROM sim_trades
            WHERE portfolio_id=? AND filled_at>=?
            """,
            (portfolio_id, since)
        ).fetchone()
        return int(row[0]) if row else 0

    def get_recent_orders_count(self, portfolio_id: str, minutes: int = 60) -> int:
        """Get count of orders in recent minutes."""
        since = (datetime.now() - timedelta(minutes=minutes)).isoformat()
        row = self._conn.execute(
            """
            SELECT COUNT(1) FROM sim_orders
            WHERE portfolio_id=? AND created_at>=?
            """,
            (portfolio_id, since)
        ).fetchone()
        return int(row[0]) if row else 0

    def get_last_order_time(self, portfolio_id: str, symbol: str, exchange: str) -> datetime | None:
        """Get last order time for symbol."""
        row = self._conn.execute(
            """
            SELECT filled_at FROM sim_trades
            WHERE portfolio_id=? AND symbol=? AND exchange=?
            ORDER BY filled_at DESC
            LIMIT 1
            """,
            (portfolio_id, symbol, exchange)
        ).fetchone()
        if row and row[0]:
            return datetime.fromisoformat(row[0])
        return None

    def check_price_limit(self, symbol: str, exchange: str, side: str, latest_price: float | None) -> dict | None:
        """Check if trading is allowed based on price limits (limit up/down)."""
        if not latest_price:
            return None

        # Get price change from yesterday's close
        row = self._conn.execute(
            """
            SELECT close, pre_close
            FROM bars_daily
            WHERE symbol=? AND exchange=? AND adj='RAW'
            ORDER BY trade_date DESC
            LIMIT 1
            """,
            (symbol, exchange)
        ).fetchone()

        if not row or row[0] is None or row[1] is None:
            return None

        current_price = float(row[0])
        pre_close = float(row[1])

        # Calculate price change percentage
        change_pct = (current_price - pre_close) / pre_close

        # Check limit up
        if change_pct >= 0.099:  # Close to 10% limit
            return {
                "code": "RISK_LIMIT_UP",
                "level": "WARN" if side == "SELL" else "FAIL",
                "message": f"Stock is at limit up price ({change_pct:.2%})",
                "suggestion": "Avoid buying at limit up, consider selling if holding"
            }

        # Check limit down
        if change_pct <= -0.099:  # Close to -10% limit
            return {
                "code": "RISK_LIMIT_DOWN",
                "level": "WARN" if side == "BUY" else "FAIL",
                "message": f"Stock is at limit down price ({change_pct:.2%})",
                "suggestion": "Avoid buying, consider selling to cut losses"
            }

        return None

    def check_sector_exposure(self, portfolio_id: str, symbol: str, exchange: str, new_qty: int) -> dict | None:
        """Check sector exposure limits (simplified - would need industry data)."""
        # This is a placeholder - in production, you'd query industry data
        # For now, just return None (no check)
        return None

    def check_daily_trading_value(self, portfolio_id: str, order_value: float) -> dict | None:
        """Check daily trading value limit."""
        rules = self.get_all_rules()
        max_daily = rules.get("max_daily_trading_value", 1000000)

        # Get today's trading value
        today = datetime.now().strftime("%Y-%m-%d")
        row = self._conn.execute(
            """
            SELECT COALESCE(SUM(fill_price * fill_qty), 0) as total
            FROM sim_trades
            WHERE portfolio_id=? AND DATE(filled_at)=?
            """,
            (portfolio_id, today)
        ).fetchone()

        today_value = float(row[0]) if row else 0.0
        projected_value = today_value + order_value

        if projected_value > max_daily:
            return {
                "code": "RISK_DAILY_VALUE_LIMIT",
                "level": "WARN",
                "message": f"Daily trading value {projected_value:.2f} exceeds limit {max_daily:.2f}",
                "suggestion": "Reduce order size or wait for next trading day"
            }

        return None

    def check_order_frequency(self, portfolio_id: str, symbol: str, exchange: str) -> dict | None:
        """Check order frequency to prevent over-trading."""
        rules = self.get_all_rules()
        min_interval = rules.get("max_order_frequency_seconds", 60)

        last_order = self.get_last_order_time(portfolio_id, symbol, exchange)
        if last_order:
            elapsed = (datetime.now() - last_order).total_seconds()
            if elapsed < min_interval:
                return {
                    "code": "RISK_ORDER_FREQUENCY",
                    "level": "WARN",
                    "message": f"Last order for {symbol} was {elapsed:.0f}s ago, minimum interval is {min_interval}s",
                    "suggestion": f"Wait {min_interval - elapsed:.0f} more seconds before placing another order"
                }

        return None

    def check_max_orders_per_day(self, portfolio_id: str) -> dict | None:
        """Check maximum orders per day."""
        rules = self.get_all_rules()
        max_orders = rules.get("max_orders_per_day", 50)

        today = datetime.now().strftime("%Y-%m-%d")
        row = self._conn.execute(
            """
            SELECT COUNT(1) FROM sim_orders
            WHERE portfolio_id=? AND DATE(created_at)=?
            """,
            (portfolio_id, today)
        ).fetchone()

        orders_today = int(row[0]) if row else 0

        if orders_today >= max_orders:
            return {
                "code": "RISK_MAX_ORDERS_PER_DAY",
                "level": "WARN",
                "message": f"Already placed {orders_today} orders today, limit is {max_orders}",
                "suggestion": "No more orders allowed today, try again tomorrow"
            }

        return None

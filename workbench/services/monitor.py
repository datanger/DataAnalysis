from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from uuid import uuid4
from typing import Any, Callable, Optional
from workbench.jsonutil import dumps


class AlertRule:
    """Represents a monitoring alert rule."""

    def __init__(
        self,
        rule_id: str,
        portfolio_id: Optional[str],
        symbol: Optional[str],
        exchange: Optional[str],
        rule_type: str,
        threshold: float,
        condition: str,  # 'above', 'below', 'crosses_above', 'crosses_below'
        enabled: bool,
        created_at: str,
        trigger_count: int = 0,
        last_triggered: Optional[str] = None,
    ):
        self.rule_id = rule_id
        self.portfolio_id = portfolio_id
        self.symbol = symbol
        self.exchange = exchange
        self.rule_type = rule_type
        self.threshold = threshold
        self.condition = condition
        self.enabled = enabled
        self.created_at = created_at
        self.trigger_count = trigger_count
        self.last_triggered = last_triggered


class Alert:
    """Represents a triggered alert."""

    def __init__(
        self,
        alert_id: str,
        rule_id: str,
        triggered_at: str,
        message: str,
        severity: str,  # 'INFO', 'WARN', 'CRITICAL'
        data: dict,
    ):
        self.alert_id = alert_id
        self.rule_id = rule_id
        self.triggered_at = triggered_at
        self.message = message
        self.severity = severity
        self.data = data


class MonitorService:
    """Service for monitoring and alerting on market conditions."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create_rule(
        self,
        *,
        portfolio_id: Optional[str],
        symbol: Optional[str],
        exchange: Optional[str],
        rule_type: str,
        threshold: float,
        condition: str,
        enabled: bool = True,
    ) -> str:
        """Create a new monitoring rule."""
        rule_id = str(uuid4())
        now = datetime.now().isoformat(timespec="seconds")

        with self._conn:
            self._conn.execute(
                """
                INSERT INTO alert_rules(
                    rule_id, portfolio_id, symbol, exchange, rule_type,
                    threshold, condition, enabled, created_at, trigger_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    rule_id,
                    portfolio_id,
                    symbol,
                    exchange,
                    rule_type,
                    threshold,
                    condition,
                    1 if enabled else 0,
                    now,
                ),
            )

        return rule_id

    def list_rules(
        self,
        portfolio_id: Optional[str] = None,
        symbol: Optional[str] = None,
        enabled_only: bool = False,
    ) -> list[AlertRule]:
        """List alert rules."""
        query = "SELECT * FROM alert_rules WHERE 1=1"
        params = []

        if portfolio_id:
            query += " AND portfolio_id=?"
            params.append(portfolio_id)

        if symbol:
            query += " AND symbol=?"
            params.append(symbol)

        if enabled_only:
            query += " AND enabled=1"

        query += " ORDER BY created_at DESC"

        rows = self._conn.execute(query, params).fetchall()

        rules = []
        for row in rows:
            rules.append(
                AlertRule(
                    rule_id=row[0],
                    portfolio_id=row[1],
                    symbol=row[2],
                    exchange=row[3],
                    rule_type=row[4],
                    threshold=float(row[5]),
                    condition=row[6],
                    enabled=bool(row[7]),
                    created_at=row[8],
                    trigger_count=row[9],
                    last_triggered=row[10],
                )
            )

        return rules

    def update_rule(
        self,
        rule_id: str,
        *,
        threshold: Optional[float] = None,
        condition: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> None:
        """Update an existing rule."""
        updates = []
        params = []

        if threshold is not None:
            updates.append("threshold=?")
            params.append(threshold)

        if condition is not None:
            updates.append("condition=?")
            params.append(condition)

        if enabled is not None:
            updates.append("enabled=?")
            params.append(1 if enabled else 0)

        if not updates:
            return

        params.append(rule_id)

        with self._conn:
            self._conn.execute(
                f"UPDATE alert_rules SET {', '.join(updates)} WHERE rule_id=?",
                params,
            )

    def delete_rule(self, rule_id: str) -> None:
        """Delete a rule."""
        with self._conn:
            self._conn.execute("DELETE FROM alert_rules WHERE rule_id=?", (rule_id,))

    def check_rules(self) -> list[Alert]:
        """Check all enabled rules and return triggered alerts."""
        rules = self.list_rules(enabled_only=True)
        alerts = []

        for rule in rules:
            alert = self._check_rule(rule)
            if alert:
                alerts.append(alert)

        return alerts

    def _check_rule(self, rule: AlertRule) -> Optional[Alert]:
        """Check a single rule."""
        if rule.rule_type == "price_change_pct":
            return self._check_price_change(rule)
        elif rule.rule_type == "volume_spike":
            return self._check_volume_spike(rule)
        elif rule.rule_type == "score_change":
            return self._check_score_change(rule)
        elif rule.rule_type == "position_limit":
            return self._check_position_limit(rule)
        elif rule.rule_type == "cash_ratio":
            return self._check_cash_ratio(rule)

        return None

    def _check_price_change(self, rule: AlertRule) -> Optional[Alert]:
        """Check price change percentage."""
        if not rule.symbol or not rule.exchange:
            return None

        # Get latest price
        row = self._conn.execute(
            """
            SELECT close, pre_close
            FROM bars_daily
            WHERE symbol=? AND exchange=? AND adj='RAW'
            ORDER BY trade_date DESC
            LIMIT 1
            """,
            (rule.symbol, rule.exchange),
        ).fetchone()

        if not row or row[0] is None or row[1] is None:
            return None

        current_price = float(row[0])
        pre_close = float(row[1])
        change_pct = ((current_price - pre_close) / pre_close) * 100

        triggered = False
        if rule.condition == "above" and change_pct > rule.threshold:
            triggered = True
        elif rule.condition == "below" and change_pct < rule.threshold:
            triggered = True
        elif rule.condition == "crosses_above":
            # Simplified - just check if above
            if change_pct > rule.threshold:
                triggered = True

        if triggered:
            # Check if already triggered recently (debounce)
            if rule.last_triggered:
                last = datetime.fromisoformat(rule.last_triggered)
                if datetime.now() - last < timedelta(hours=1):
                    return None

            # Update trigger count
            with self._conn:
                self._conn.execute(
                    """
                    UPDATE alert_rules
                    SET trigger_count=trigger_count+1, last_triggered=?
                    WHERE rule_id=?
                    """,
                    (datetime.now().isoformat(timespec="seconds"), rule.rule_id),
                )

            return Alert(
                alert_id=str(uuid4()),
                rule_id=rule.rule_id,
                triggered_at=datetime.now().isoformat(timespec="seconds"),
                message=f"{rule.symbol} 价格变动 {change_pct:.2f}% 触发阈值 {rule.threshold:.2f}%",
                severity="WARN" if abs(change_pct) < 10 else "CRITICAL",
                data={
                    "symbol": rule.symbol,
                    "exchange": rule.exchange,
                    "current_price": current_price,
                    "pre_close": pre_close,
                    "change_pct": change_pct,
                    "threshold": rule.threshold,
                    "condition": rule.condition,
                },
            )

        return None

    def _check_volume_spike(self, rule: AlertRule) -> Optional[Alert]:
        """Check for volume spikes."""
        if not rule.symbol or not rule.exchange:
            return None

        # Get recent volumes
        rows = self._conn.execute(
            """
            SELECT trade_date, volume
            FROM bars_daily
            WHERE symbol=? AND exchange=? AND adj='RAW'
            ORDER BY trade_date DESC
            LIMIT 21
            """,
            (rule.symbol, rule.exchange),
        ).fetchall()

        if len(rows) < 20:
            return None

        # Calculate average volume (excluding today)
        recent_volumes = [float(r[1]) for r in rows[1:20] if r[1] is not None]
        if not recent_volumes:
            return None

        avg_volume = sum(recent_volumes) / len(recent_volumes)
        today_volume = float(rows[0][1]) if rows[0][1] is not None else 0

        volume_ratio = today_volume / avg_volume if avg_volume > 0 else 0

        if volume_ratio > rule.threshold:
            # Debounce
            if rule.last_triggered:
                last = datetime.fromisoformat(rule.last_triggered)
                if datetime.now() - last < timedelta(hours=2):
                    return None

            # Update trigger count
            with self._conn:
                self._conn.execute(
                    """
                    UPDATE alert_rules
                    SET trigger_count=trigger_count+1, last_triggered=?
                    WHERE rule_id=?
                    """,
                    (datetime.now().isoformat(timespec="seconds"), rule.rule_id),
                )

            return Alert(
                alert_id=str(uuid4()),
                rule_id=rule.rule_id,
                triggered_at=datetime.now().isoformat(timespec="seconds"),
                message=f"{rule.symbol} 成交量放大 {volume_ratio:.1f}倍",
                severity="INFO",
                data={
                    "symbol": rule.symbol,
                    "exchange": rule.exchange,
                    "today_volume": today_volume,
                    "avg_volume": avg_volume,
                    "volume_ratio": volume_ratio,
                    "threshold": rule.threshold,
                },
            )

        return None

    def _check_score_change(self, rule: AlertRule) -> Optional[Alert]:
        """Check for score changes."""
        if not rule.symbol or not rule.exchange:
            return None

        # Get latest scores
        rows = self._conn.execute(
            """
            SELECT score_total, created_at
            FROM score_snapshots
            WHERE symbol=? AND exchange=?
            ORDER BY created_at DESC
            LIMIT 2
            """,
            (rule.symbol, rule.exchange),
        ).fetchall()

        if len(rows) < 2:
            return None

        latest_score = float(rows[0][0])
        prev_score = float(rows[1][0])
        score_change = latest_score - prev_score

        if abs(score_change) > rule.threshold:
            # Update trigger count
            with self._conn:
                self._conn.execute(
                    """
                    UPDATE alert_rules
                    SET trigger_count=trigger_count+1, last_triggered=?
                    WHERE rule_id=?
                    """,
                    (datetime.now().isoformat(timespec="seconds"), rule.rule_id),
                )

            return Alert(
                alert_id=str(uuid4()),
                rule_id=rule.rule_id,
                triggered_at=datetime.now().isoformat(timespec="seconds"),
                message=f"{rule.symbol} 评分变动 {score_change:+.1f}",
                severity="INFO",
                data={
                    "symbol": rule.symbol,
                    "exchange": rule.exchange,
                    "latest_score": latest_score,
                    "prev_score": prev_score,
                    "score_change": score_change,
                    "threshold": rule.threshold,
                },
            )

        return None

    def _check_position_limit(self, rule: AlertRule) -> Optional[Alert]:
        """Check if position exceeds limit."""
        if not rule.portfolio_id:
            return None

        # Use portfolio total_equity + position weights (realistic).
        from workbench.services.portfolios import PortfolioRepo

        repo = PortfolioRepo(self._conn)
        p = repo.get(rule.portfolio_id)
        if not p:
            return None

        total_equity = float(p.get("total_equity") or 0.0)
        if total_equity <= 0:
            return None

        positions = p.get("positions") or []
        if not positions:
            return None

        top = max(positions, key=lambda r: float(r.get("market_value") or 0.0))
        top_pct = float(top.get("weight") or 0.0) * 100.0
        position_value = float(top.get("market_value") or 0.0)

        if top_pct > rule.threshold:
            return Alert(
                alert_id=str(uuid4()),
                rule_id=rule.rule_id,
                triggered_at=datetime.now().isoformat(timespec="seconds"),
                message=f"组合 {rule.portfolio_id} 单票仓位 {top_pct:.1f}% 超过限制 {rule.threshold:.1f}%",
                severity="WARN",
                data={
                    "portfolio_id": rule.portfolio_id,
                    "symbol": top.get("symbol"),
                    "exchange": top.get("exchange"),
                    "position_value": position_value,
                    "position_pct": top_pct,
                    "total_equity": total_equity,
                    "threshold": rule.threshold,
                },
            )

        return None

    def _check_cash_ratio(self, rule: AlertRule) -> Optional[Alert]:
        """Check if cash ratio is below threshold."""
        if not rule.portfolio_id:
            return None

        from workbench.services.portfolios import PortfolioRepo

        repo = PortfolioRepo(self._conn)
        p = repo.get(rule.portfolio_id)
        if not p:
            return None

        cash = float(p.get("cash") or 0.0)
        total_equity = float(p.get("total_equity") or 0.0)
        if total_equity <= 0:
            return None

        cash_ratio = float(p.get("cash_ratio") or 0.0) * 100.0

        if cash_ratio < rule.threshold:
            return Alert(
                alert_id=str(uuid4()),
                rule_id=rule.rule_id,
                triggered_at=datetime.now().isoformat(timespec="seconds"),
                message=f"组合 {rule.portfolio_id} 现金比例 {cash_ratio:.1f}% 低于阈值 {rule.threshold:.1f}%",
                severity="WARN",
                data={
                    "portfolio_id": rule.portfolio_id,
                    "cash": cash,
                    "cash_ratio": cash_ratio,
                    "total_equity": total_equity,
                    "threshold": rule.threshold,
                },
            )

        return None

    def list_alerts(self, limit: int = 100, since: Optional[str] = None) -> list[Alert]:
        """List recent alerts."""
        query = "SELECT * FROM alerts WHERE 1=1"
        params = []

        if since:
            query += " AND triggered_at>=?"
            params.append(since)

        query += " ORDER BY triggered_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()

        alerts = []
        for row in rows:
            import json

            alerts.append(
                Alert(
                    alert_id=row[0],
                    rule_id=row[1],
                    triggered_at=row[2],
                    message=row[3],
                    severity=row[4],
                    data=json.loads(row[5]) if row[5] else {},
                )
            )

        return alerts

    def save_alert(self, alert: Alert) -> None:
        """Save an alert to database."""
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO alerts(alert_id, rule_id, triggered_at, message, severity, data_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    alert.alert_id,
                    alert.rule_id,
                    alert.triggered_at,
                    alert.message,
                    alert.severity,
                    dumps(alert.data),
                ),
            )

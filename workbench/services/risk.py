from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from uuid import uuid4

from workbench.jsonutil import dumps
from workbench.services.risk_rules import RiskRulesRepo


DEFAULT_RULESET_VERSION = "risk/v1"


class RiskService:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self.rules_repo = RiskRulesRepo(conn)

        # Get rules from repo
        self.rules = self.rules_repo.get_all_rules()

        # Legacy support - use rules dict
        self.max_position_per_symbol = self.rules.get("max_position_per_symbol", 0.25)
        self.min_cash_ratio = self.rules.get("min_cash_ratio", 0.05)
        self.max_order_value = self.rules.get("max_order_value", 200000)
        self.price_deviation_limit = self.rules.get("price_deviation_limit", 0.03)
        self.lot_size = self.rules.get("lot_size", 100)

    def check(self, *, draft_rows: list[dict]) -> tuple[str, dict]:
        """Return (riskcheck_id, payload).

        Notes:
        - This check is conservative and sequential: it simulates the cash/positions
          after applying drafts in the given order.
        - Equity is marked-to-market using latest closes where available.
        """

        if not draft_rows:
            raise ValueError("draft_ids empty")

        portfolio_id = draft_rows[0]["portfolio_id"]
        if any(d["portfolio_id"] != portfolio_id for d in draft_rows):
            raise ValueError("drafts must belong to the same portfolio")

        cash = self._get_cash(portfolio_id)
        pos_qty_map = self._positions_qty_map(portfolio_id)

        items: list[dict] = []
        status = "PASS"

        # Pre-checks using enhanced rules
        daily_orders_check = self.rules_repo.check_max_orders_per_day(portfolio_id)
        if daily_orders_check:
            items.append(daily_orders_check)
            if status != "FAIL":
                status = "WARN"

        positions_mv, price_missing = self._positions_market_value(pos_qty_map)
        total_equity = cash + positions_mv
        if total_equity <= 0:
            total_equity = cash

        cash_now = cash

        # Cache latest prices.
        price_cache: dict[tuple[str, str], float] = {}

        def _latest(sym: str, exch: str) -> float | None:
            key = (sym, exch)
            if key in price_cache:
                return price_cache[key]
            px = self._latest_close(sym, exch)
            if px is not None:
                price_cache[key] = px
            return px

        for d in draft_rows:
            sym = d["symbol"]
            exch = d["exchange"]
            side = str(d["side"]).upper()
            qty = int(d["qty"])
            limit_price = d["price"]

            if qty <= 0 or qty % self.lot_size != 0:
                items.append(
                    {
                        "code": "RISK_INVALID_QTY",
                        "level": "FAIL",
                        "message": f"qty must be positive and multiple of {self.lot_size}",
                        "suggestion": f"set qty to {self.lot_size} * n",
                        "draft_id": d["draft_id"],
                    }
                )
                status = "FAIL"
                continue

            latest = _latest(sym, exch)
            if latest is None:
                items.append(
                    {
                        "code": "DATA_NOT_READY",
                        "level": "FAIL",
                        "message": f"no latest price for {sym}.{exch}",
                        "suggestion": "run ingest_bars_daily for this symbol",
                        "draft_id": d["draft_id"],
                    }
                )
                status = "FAIL"
                continue

            order_price = float(limit_price) if limit_price is not None else float(latest)
            order_value = order_price * qty

            # Enhanced price deviation check
            if limit_price is not None:
                deviation = abs(order_price - float(latest)) / float(latest)
                if deviation > self.price_deviation_limit:
                    items.append(
                        {
                            "code": "RISK_PRICE_DEVIATION",
                            "level": "WARN",
                            "message": f"limit price deviates from latest close by {deviation:.2%}",
                            "suggestion": "confirm price or adjust closer to market",
                            "draft_id": d["draft_id"],
                        }
                    )
                    if status != "FAIL":
                        status = "WARN"

            # Order frequency check (only for BUY orders)
            if side == "BUY":
                freq_check = self.rules_repo.check_order_frequency(portfolio_id, sym, exch)
                if freq_check:
                    items.append(freq_check)
                    status = freq_check["level"] if status != "FAIL" else status

            # Price limit check (limit up/down)
            limit_check = self.rules_repo.check_price_limit(sym, exch, side, latest)
            if limit_check:
                items.append(limit_check)
                if limit_check["level"] == "FAIL":
                    status = "FAIL"
                elif status != "FAIL":
                    status = "WARN"

            # Daily trading value check (only for BUY orders)
            if side == "BUY":
                daily_value_check = self.rules_repo.check_daily_trading_value(portfolio_id, order_value)
                if daily_value_check:
                    items.append(daily_value_check)
                    if status != "FAIL":
                        status = "WARN"

            # Min order value check
            min_order_value = self.rules.get("min_order_value", 1000)
            if order_value < min_order_value:
                items.append(
                    {
                        "code": "RISK_MIN_ORDER_VALUE",
                        "level": "WARN",
                        "message": f"order value {order_value:.2f} below minimum {min_order_value:.2f}",
                        "suggestion": "increase order size or combine orders",
                        "draft_id": d["draft_id"],
                    }
                )
                if status != "FAIL":
                    status = "WARN"

            if order_value > self.max_order_value:
                items.append(
                    {
                        "code": "RISK_MAX_ORDER_VALUE",
                        "level": "WARN",
                        "message": f"order value {order_value:.2f} exceeds limit {self.max_order_value:.2f}",
                        "suggestion": "reduce order size",
                        "draft_id": d["draft_id"],
                    }
                )
                if status != "FAIL":
                    status = "WARN"

            cur_qty = int(pos_qty_map.get((sym, exch), 0))

            if side == "SELL":
                if qty > cur_qty:
                    items.append(
                        {
                            "code": "RISK_SELL_QTY_EXCEEDS_POSITION",
                            "level": "FAIL",
                            "message": "sell qty exceeds current position",
                            "suggestion": "reduce sell qty",
                            "draft_id": d["draft_id"],
                        }
                    )
                    status = "FAIL"
                    continue

                # Simulate sell: increase cash.
                cash_now += order_value
                pos_qty_map[(sym, exch)] = cur_qty - qty
                continue

            if side != "BUY":
                items.append(
                    {
                        "code": "RISK_UNSUPPORTED_SIDE",
                        "level": "FAIL",
                        "message": f"unsupported side: {side}",
                        "suggestion": "use BUY or SELL",
                        "draft_id": d["draft_id"],
                    }
                )
                status = "FAIL"
                continue

            # BUY checks
            if order_value > cash_now:
                items.append(
                    {
                        "code": "RISK_INSUFFICIENT_CASH",
                        "level": "FAIL",
                        "message": "insufficient cash",
                        "suggestion": "reduce buy qty or add cash",
                        "draft_id": d["draft_id"],
                    }
                )
                status = "FAIL"
                continue

            # Simulate buy: decrease cash, increase position.
            cash_now -= order_value
            pos_qty_map[(sym, exch)] = cur_qty + qty

            if total_equity > 0 and (cash_now / total_equity) < self.min_cash_ratio:
                items.append(
                    {
                        "code": "RISK_MIN_CASH_RATIO",
                        "level": "FAIL",
                        "message": "cash ratio after trades below minimum",
                        "suggestion": "reduce buy size",
                        "draft_id": d["draft_id"],
                    }
                )
                status = "FAIL"
                continue

            # Position limit (approx by latest close)
            pos_value = pos_qty_map[(sym, exch)] * float(latest)
            if total_equity > 0 and (pos_value / total_equity) > self.max_position_per_symbol:
                items.append(
                    {
                        "code": "RISK_POSITION_LIMIT",
                        "level": "FAIL",
                        "message": "position size exceeds limit",
                        "suggestion": "reduce buy size",
                        "draft_id": d["draft_id"],
                    }
                )
                status = "FAIL"
                continue

        if price_missing and status == "PASS":
            items.append(
                {
                    "code": "RISK_PRICE_MISSING_FOR_SOME_POSITIONS",
                    "level": "WARN",
                    "message": "some positions missing latest price; risk checks are approximate",
                    "suggestion": "ingest bars for all held symbols",
                }
            )
            status = "WARN"

        riskcheck_id = str(uuid4())
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO risk_check_results(riskcheck_id, created_at, status, items_json, ruleset_version, input_draft_ids_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    riskcheck_id,
                    now,
                    status,
                    dumps(items),
                    DEFAULT_RULESET_VERSION,
                    dumps([d["draft_id"] for d in draft_rows]),
                ),
            )

        payload = {
            "status": status,
            "items": items,
            "ruleset_version": DEFAULT_RULESET_VERSION,
            "summary": {
                "cash_before": cash,
                "cash_after_est": cash_now,
                "total_equity_est": total_equity,
            },
        }

        return riskcheck_id, payload

    def _get_cash(self, portfolio_id: str) -> float:
        row = self._conn.execute(
            "SELECT cash FROM portfolio_accounts WHERE portfolio_id=?",
            (portfolio_id,),
        ).fetchone()
        if not row:
            raise KeyError("portfolio not found")
        return float(row[0])

    def _positions_qty_map(self, portfolio_id: str) -> dict[tuple[str, str], int]:
        rows = self._conn.execute(
            "SELECT symbol, exchange, qty FROM positions WHERE portfolio_id=?",
            (portfolio_id,),
        ).fetchall()
        return {(str(r[0]), str(r[1])): int(r[2]) for r in rows}

    def _latest_close(self, symbol: str, exchange: str) -> float | None:
        row = self._conn.execute(
            """
            SELECT close
            FROM bars_daily
            WHERE symbol=? AND exchange=? AND adj='RAW'
            ORDER BY trade_date DESC
            LIMIT 1
            """,
            (symbol, exchange),
        ).fetchone()
        return float(row[0]) if row and row[0] is not None else None

    def _positions_market_value(self, pos_qty_map: dict[tuple[str, str], int]) -> tuple[float, bool]:
        mv = 0.0
        missing = False
        for (sym, exch), qty in pos_qty_map.items():
            px = self._latest_close(sym, exch)
            if px is None:
                missing = True
                continue
            mv += qty * px
        return mv, missing

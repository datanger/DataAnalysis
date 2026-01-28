from __future__ import annotations

import os
import sqlite3

from workbench.services.portfolios import PortfolioRepo


class RebalanceService:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self.lot_size = int(os.getenv("RISK_LOT_SIZE", "100"))

    def suggest(
        self,
        *,
        portfolio_id: str,
        targets: list[dict],
        cash_reserve_ratio: float = 0.05,
    ) -> dict:
        """Return suggested orders to move toward target weights.

        Targets: [{symbol, exchange, weight}] with weights summing to 1.
        """

        repo = PortfolioRepo(self._conn)
        cash = repo.get_cash(portfolio_id)

        positions = self._conn.execute(
            "SELECT symbol, exchange, qty FROM positions WHERE portfolio_id=?",
            (portfolio_id,),
        ).fetchall()

        px_map: dict[tuple[str, str], float] = {}
        missing: list[str] = []

        def _px(sym: str, exch: str) -> float | None:
            row = self._conn.execute(
                """
                SELECT close FROM bars_daily
                WHERE symbol=? AND exchange=? AND adj='RAW'
                ORDER BY trade_date DESC LIMIT 1
                """,
                (sym, exch),
            ).fetchone()
            return float(row[0]) if row and row[0] is not None else None

        mv_positions = 0.0
        for sym, exch, qty in positions:
            p = _px(sym, exch)
            if p is None:
                missing.append(f"{sym}.{exch}")
                continue
            px_map[(sym, exch)] = p
            mv_positions += int(qty) * p

        total_equity = cash + mv_positions
        investable = total_equity * (1.0 - float(cash_reserve_ratio))

        # Normalize targets.
        cleaned: list[dict] = []
        wsum = 0.0
        for t in targets:
            sym = str(t.get("symbol") or "").zfill(6)
            exch = str(t.get("exchange") or "")
            w = float(t.get("weight") or 0.0)
            if not sym or not exch or w <= 0:
                continue
            cleaned.append({"symbol": sym, "exchange": exch, "weight": w})
            wsum += w

        if wsum <= 0:
            raise ValueError("targets empty or weights invalid")
        for t in cleaned:
            t["weight"] = t["weight"] / wsum

        pos_qty_map = {(str(s), str(e)): int(q) for s, e, q in positions}

        orders: list[dict] = []
        cash_after = cash
        for t in cleaned:
            sym = t["symbol"]
            exch = t["exchange"]
            weight = float(t["weight"])

            px = px_map.get((sym, exch))
            if px is None:
                px2 = _px(sym, exch)
                if px2 is None:
                    missing.append(f"{sym}.{exch}")
                    continue
                px = px2
                px_map[(sym, exch)] = px

            target_value = investable * weight
            cur_qty = pos_qty_map.get((sym, exch), 0)
            cur_value = cur_qty * px
            delta = target_value - cur_value

            if abs(delta) < px * self.lot_size:
                continue

            if delta > 0:
                buy_qty = int(delta / px)
                buy_qty = (buy_qty // self.lot_size) * self.lot_size
                if buy_qty <= 0:
                    continue
                orders.append(
                    {
                        "symbol": sym,
                        "exchange": exch,
                        "side": "BUY",
                        "qty": buy_qty,
                        "price": px,
                        "estimated_value": buy_qty * px,
                    }
                )
                cash_after -= buy_qty * px
            else:
                sell_qty = int((-delta) / px)
                sell_qty = (sell_qty // self.lot_size) * self.lot_size
                sell_qty = min(sell_qty, cur_qty)
                if sell_qty <= 0:
                    continue
                orders.append(
                    {
                        "symbol": sym,
                        "exchange": exch,
                        "side": "SELL",
                        "qty": sell_qty,
                        "price": px,
                        "estimated_value": sell_qty * px,
                    }
                )
                cash_after += sell_qty * px

        return {
            "portfolio_id": portfolio_id,
            "total_equity": total_equity,
            "cash_before": cash,
            "cash_after_est": cash_after,
            "cash_reserve_ratio": cash_reserve_ratio,
            "orders": orders,
            "missing_prices": sorted(set(missing)),
        }

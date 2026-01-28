from __future__ import annotations

from datetime import datetime
import sqlite3

from workbench.services.capital_flow import CapitalFlowRepo


class CapitalFlowIngestService:
    def __init__(self, conn: sqlite3.Connection, *, tushare_token: str | None):
        self._conn = conn
        self._tushare_token = tushare_token

    def ingest_moneyflow(self, *, symbols: list[dict]) -> dict:
        if not self._tushare_token:
            raise RuntimeError("TUSHARE_TOKEN not configured")

        import tushare as ts

        pro = ts.pro_api(self._tushare_token)
        repo = CapitalFlowRepo(self._conn)

        ingested = 0
        for item in symbols:
            symbol = str(item.get("symbol") or "").zfill(6)
            exchange = str(item.get("exchange") or "")
            if not symbol or exchange not in ("SSE", "SZSE"):
                continue

            ts_code = f"{symbol}.SH" if exchange == "SSE" else f"{symbol}.SZ"
            df = pro.moneyflow(
                ts_code=ts_code,
                fields="ts_code,trade_date,net_mf_amount",
            )
            if df is None or df.empty:
                continue

            row = df.iloc[0]
            td = str(row["trade_date"])
            trade_date = f"{td[0:4]}-{td[4:6]}-{td[6:8]}"

            # net_mf_amount is in 1e4 CNY (万)
            net_inflow = float(row["net_mf_amount"]) * 1e4 if row["net_mf_amount"] == row["net_mf_amount"] else None

            repo.upsert_daily(
                symbol=symbol,
                exchange=exchange,
                trade_date=trade_date,
                net_inflow=net_inflow,
                main_inflow=None,
                northbound_net=None,
                source="tushare",
            )
            ingested += 1

        return {"ingested": ingested, "source": "tushare", "asof": datetime.now().isoformat(timespec="seconds")}


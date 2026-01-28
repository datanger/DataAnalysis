from __future__ import annotations

from datetime import datetime
import sqlite3

from workbench.services.fundamentals import FundamentalsRepo


class FundamentalsIngestService:
    def __init__(self, conn: sqlite3.Connection, *, tushare_token: str | None):
        self._conn = conn
        self._tushare_token = tushare_token

    def ingest_daily_basic(self, *, symbols: list[dict]) -> dict:
        if not self._tushare_token:
            raise RuntimeError("TUSHARE_TOKEN not configured")

        import tushare as ts

        pro = ts.pro_api(self._tushare_token)
        repo = FundamentalsRepo(self._conn)

        ingested = 0
        for item in symbols:
            symbol = str(item.get("symbol") or "").zfill(6)
            exchange = str(item.get("exchange") or "")
            if not symbol or exchange not in ("SSE", "SZSE"):
                continue

            ts_code = f"{symbol}.SH" if exchange == "SSE" else f"{symbol}.SZ"
            df = pro.daily_basic(
                ts_code=ts_code,
                fields="ts_code,trade_date,pe_ttm,pb,ps_ttm,total_mv",
            )
            if df is None or df.empty:
                continue

            # Latest record (trade_date is YYYYMMDD)
            row = df.iloc[0]
            td = str(row["trade_date"])
            trade_date = f"{td[0:4]}-{td[4:6]}-{td[6:8]}"

            pe_ttm = float(row["pe_ttm"]) if row["pe_ttm"] == row["pe_ttm"] else None
            pb = float(row["pb"]) if row["pb"] == row["pb"] else None
            ps_ttm = float(row["ps_ttm"]) if row["ps_ttm"] == row["ps_ttm"] else None

            # total_mv is in 1e4 CNY (万). Store mv in CNY.
            mv = float(row["total_mv"]) * 1e4 if row["total_mv"] == row["total_mv"] else None

            repo.upsert_daily(
                symbol=symbol,
                exchange=exchange,
                trade_date=trade_date,
                pe_ttm=pe_ttm,
                pb=pb,
                ps_ttm=ps_ttm,
                mv=mv,
                source="tushare",
            )
            ingested += 1

        return {"ingested": ingested, "source": "tushare", "asof": datetime.now().isoformat(timespec="seconds")}


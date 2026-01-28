from __future__ import annotations

from datetime import datetime
from typing import Iterable, Sequence

from workbench.providers.base import BarDailyRow, DataProvider, InstrumentRow, ProviderStatus


class TushareProvider(DataProvider):
    def __init__(self, token: str | None):
        self._token = token

    @property
    def name(self) -> str:
        return "tushare"

    def status(self) -> ProviderStatus:
        if not self._token:
            return ProviderStatus(
                name=self.name,
                ok=False,
                details={"error": "TUSHARE_TOKEN not configured"},
            )
        try:
            import tushare  # noqa: F401

            return ProviderStatus(name=self.name, ok=True, details={"import": "ok"})
        except Exception as e:  # noqa: BLE001
            return ProviderStatus(name=self.name, ok=False, details={"error": str(e)})

    def iter_instruments(self) -> Iterable[InstrumentRow]:
        """Yield A-share instruments via TuShare Pro."""

        if not self._token:
            raise RuntimeError("TUSHARE_TOKEN not configured")

        import tushare as ts

        pro = ts.pro_api(self._token)
        df = pro.stock_basic(
            exchange="",
            list_status="L",
            fields="ts_code,symbol,name,exchange,industry",
        )

        for row in df.itertuples(index=False):
            exchange = getattr(row, "exchange", None) or ""
            symbol = str(getattr(row, "symbol", "") or "").zfill(6)
            name = getattr(row, "name", None)
            industry = getattr(row, "industry", None)

            if exchange not in ("SSE", "SZSE"):
                ts_code = getattr(row, "ts_code", "") or ""
                if ts_code.endswith(".SH"):
                    exchange = "SSE"
                elif ts_code.endswith(".SZ"):
                    exchange = "SZSE"
                else:
                    exchange = "SSE" if symbol.startswith("6") else "SZSE"

            yield InstrumentRow(
                symbol=symbol,
                exchange=exchange,
                market="CN_A",
                name=name,
                industry=industry,
            )

    def fetch_bars_daily(
        self,
        *,
        symbol: str,
        exchange: str,
        start_date: str | None = None,
        end_date: str | None = None,
        adj: str = "RAW",
    ) -> Sequence[BarDailyRow]:
        if not self._token:
            raise RuntimeError("TUSHARE_TOKEN not configured")
        if adj != "RAW":
            raise NotImplementedError("TuShare adjusted bars are not implemented yet")

        import tushare as ts

        pro = ts.pro_api(self._token)
        ts_code = f"{symbol}.SH" if exchange == "SSE" else f"{symbol}.SZ"
        df = pro.daily(
            ts_code=ts_code,
            start_date=start_date or "19900101",
            end_date=end_date or datetime.now().strftime("%Y%m%d"),
        )

        # TuShare returns trade_date as YYYYMMDD.
        df = df.sort_values("trade_date")

        out: list[BarDailyRow] = []
        for r in df.itertuples(index=False):
            trade_date = getattr(r, "trade_date")
            trade_date = f"{trade_date[0:4]}-{trade_date[4:6]}-{trade_date[6:8]}"

            out.append(
                BarDailyRow(
                    symbol=symbol,
                    exchange=exchange,
                    trade_date=trade_date,
                    adj=adj,
                    open=float(getattr(r, "open")),
                    high=float(getattr(r, "high")),
                    low=float(getattr(r, "low")),
                    close=float(getattr(r, "close")),
                    volume=float(getattr(r, "vol")),
                    amount=float(getattr(r, "amount")),
                    pre_close=float(getattr(r, "pre_close")),
                    source=self.name,
                    quality="OK",
                )
            )

        return out

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Sequence

from workbench.providers.base import BarDailyRow, DataProvider, InstrumentRow, ProviderStatus


class AkshareProvider(DataProvider):
    @property
    def name(self) -> str:
        return "akshare"

    def status(self) -> ProviderStatus:
        try:
            import akshare  # noqa: F401

            return ProviderStatus(name=self.name, ok=True, details={"import": "ok"})
        except Exception as e:  # noqa: BLE001
            return ProviderStatus(name=self.name, ok=False, details={"error": str(e)})

    def iter_instruments(self) -> Iterable[InstrumentRow]:
        """Yield A-share instruments.

        Uses AKShare's public instrument list. Exchange is inferred from symbol.
        """

        import akshare as ak

        df = ak.stock_info_a_code_name()

        # AKShare column names vary by version. Normalize to code/name.
        cols = {c.lower(): c for c in df.columns}
        code_col = cols.get("code") or cols.get("证券代码") or list(df.columns)[0]
        name_col = cols.get("name") or cols.get("证券简称") or list(df.columns)[1]

        for _, row in df.iterrows():
            symbol = str(row[code_col]).zfill(6)
            name = str(row[name_col]) if name_col in row else None

            if symbol.startswith("6"):
                exchange = "SSE"
            else:
                exchange = "SZSE"

            yield InstrumentRow(
                symbol=symbol,
                exchange=exchange,
                market="CN_A",
                name=name,
                industry=None,
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
        import akshare as ak

        adjust = ""
        if adj == "QFQ":
            adjust = "qfq"
        elif adj == "HFQ":
            adjust = "hfq"

        df = ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start_date or "19900101",
            end_date=end_date or datetime.now().strftime("%Y%m%d"),
            adjust=adjust,
        )

        # Normalize columns.
        # Typical: 日期 开盘 收盘 最高 最低 成交量 成交额 ...
        colmap = {
            "日期": "trade_date",
            "开盘": "open",
            "最高": "high",
            "最低": "low",
            "收盘": "close",
            "成交量": "volume",
            "成交额": "amount",
        }

        for k, v in colmap.items():
            if k in df.columns:
                df = df.rename(columns={k: v})

        df = df.sort_values("trade_date")

        pre_close = None
        out: list[BarDailyRow] = []
        for _, r in df.iterrows():
            trade_date = str(r["trade_date"])
            # AKShare dates are YYYY-MM-DD already.
            close = float(r["close"]) if "close" in r and r["close"] == r["close"] else None
            row = BarDailyRow(
                symbol=symbol,
                exchange=exchange,
                trade_date=trade_date,
                adj=adj,
                open=float(r["open"]) if "open" in r and r["open"] == r["open"] else None,
                high=float(r["high"]) if "high" in r and r["high"] == r["high"] else None,
                low=float(r["low"]) if "low" in r and r["low"] == r["low"] else None,
                close=close,
                volume=float(r["volume"]) if "volume" in r and r["volume"] == r["volume"] else None,
                amount=float(r["amount"]) if "amount" in r and r["amount"] == r["amount"] else None,
                pre_close=pre_close,
                source=self.name,
                quality="OK",
            )
            out.append(row)
            pre_close = close

        return out

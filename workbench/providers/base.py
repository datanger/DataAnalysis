from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class ProviderStatus:
    name: str
    ok: bool
    details: dict


@dataclass(frozen=True)
class InstrumentRow:
    symbol: str
    exchange: str
    market: str
    name: str | None = None
    industry: str | None = None


@dataclass(frozen=True)
class BarDailyRow:
    symbol: str
    exchange: str
    trade_date: str  # YYYY-MM-DD
    adj: str  # RAW/QFQ/HFQ
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None
    amount: float | None
    pre_close: float | None
    source: str
    quality: str


class DataProvider(ABC):
    """Pluggable data provider interface."""

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def status(self) -> ProviderStatus:
        raise NotImplementedError

    @abstractmethod
    def iter_instruments(self) -> Iterable[InstrumentRow]:
        raise NotImplementedError

    @abstractmethod
    def fetch_bars_daily(
        self,
        *,
        symbol: str,
        exchange: str,
        start_date: str | None = None,  # YYYYMMDD
        end_date: str | None = None,  # YYYYMMDD
        adj: str = "RAW",
    ) -> Sequence[BarDailyRow]:
        """Fetch daily bars.

        start_date/end_date use YYYYMMDD because most data sources prefer it.
        """

        raise NotImplementedError

from __future__ import annotations

from dataclasses import dataclass

from workbench.providers.base import DataProvider
from workbench.providers.akshare_provider import AkshareProvider
from workbench.providers.tushare_provider import TushareProvider


@dataclass(frozen=True)
class ProviderRegistry:
    providers: dict[str, DataProvider]

    def get(self, name: str) -> DataProvider | None:
        return self.providers.get(name)

    def ordered(self, names: tuple[str, ...]) -> list[DataProvider]:
        out: list[DataProvider] = []
        for n in names:
            p = self.get(n)
            if p is not None:
                out.append(p)
        for n, p in self.providers.items():
            if n not in names:
                out.append(p)
        return out


def build_registry(tushare_token: str | None) -> ProviderRegistry:
    providers: dict[str, DataProvider] = {
        "akshare": AkshareProvider(),
        "tushare": TushareProvider(token=tushare_token),
    }
    return ProviderRegistry(providers=providers)

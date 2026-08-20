from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime

from ..core.models import Candle


class ProviderError(RuntimeError):
    pass


class MarketDataProvider(ABC):
    name = "Provider"

    @abstractmethod
    def fetch_candles(
        self, symbol: str, timeframe: str, limit: int = 500,
        start: datetime | None = None, end: datetime | None = None,
    ) -> list[Candle]:
        raise NotImplementedError

    @abstractmethod
    def list_symbols(self) -> list[str]:
        raise NotImplementedError

    def test_connection(self) -> tuple[bool, float | None, str]:
        raise NotImplementedError

    async def stream_candles(
        self, symbol: str, timeframe: str, callback: Callable[[Candle], None], stop_event,
    ) -> None:
        raise NotImplementedError


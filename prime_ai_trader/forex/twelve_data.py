from __future__ import annotations

import time
from datetime import datetime, timezone

import pandas as pd

from ..core.models import Candle, FOREX_DEFAULTS
from ..market.base import MarketDataProvider, ProviderError
from ..market.http import get_json


TWELVE_INTERVALS = {"1m": "1min", "3m": "1min", "5m": "5min", "15m": "15min", "30m": "30min", "1h": "1h", "4h": "4h"}


class TwelveDataProvider(MarketDataProvider):
    name = "Twelve Data"
    base_url = "https://api.twelvedata.com"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key.strip()

    def _require_key(self) -> None:
        if not self.api_key:
            raise ProviderError("Configure a chave da Twelve Data em Configurações > APIs.")

    def fetch_candles(self, symbol: str, timeframe: str, limit: int = 500,
                      start: datetime | None = None, end: datetime | None = None) -> list[Candle]:
        self._require_key()
        params: dict[str, str | int] = {
            "symbol": symbol, "interval": TWELVE_INTERVALS[timeframe],
            "outputsize": min(max(limit, 1), 5000), "apikey": self.api_key, "timezone": "UTC",
        }
        if start:
            params["start_date"] = start.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        if end:
            params["end_date"] = end.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        data = get_json(f"{self.base_url}/time_series", params)
        if data.get("status") == "error" or "values" not in data:
            raise ProviderError(data.get("message", "Twelve Data não retornou candles."))
        candles = []
        for row in reversed(data["values"]):
            when = datetime.strptime(row["datetime"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            candles.append(Candle(when, float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]), float(row.get("volume") or 0)))
        if timeframe == "3m" and candles:
            source = pd.DataFrame({
                "time": [c.open_time for c in candles], "open": [c.open for c in candles],
                "high": [c.high for c in candles], "low": [c.low for c in candles],
                "close": [c.close for c in candles], "volume": [c.volume for c in candles],
            }).set_index("time")
            grouped = source.resample("3min").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
            candles = [Candle(index.to_pydatetime(), row.open, row.high, row.low, row.close, row.volume) for index, row in grouped.iterrows()]
        return candles

    def list_symbols(self) -> list[str]:
        return FOREX_DEFAULTS.copy()

    def test_connection(self) -> tuple[bool, float | None, str]:
        if not self.api_key:
            return False, None, "CHAVE NÃO CONFIGURADA"
        started = time.perf_counter()
        try:
            self.fetch_candles("EUR/USD", "1m", 1)
            return True, (time.perf_counter() - started) * 1000, "ONLINE"
        except ProviderError as exc:
            return False, None, str(exc)

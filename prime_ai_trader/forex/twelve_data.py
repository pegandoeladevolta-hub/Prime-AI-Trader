from __future__ import annotations

import time
from collections import deque
from datetime import datetime, timezone
from threading import Lock

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
        self._cache: dict[tuple, tuple[float, list[Candle]]] = {}
        self._request_times: deque[float] = deque()
        self._lock = Lock()
        self._last_success_at = 0.0
        self._last_latency_ms: float | None = None

    def _require_key(self) -> None:
        if not self.api_key:
            raise ProviderError("Configure a chave da Twelve Data em Configurações > APIs.")

    def fetch_candles(self, symbol: str, timeframe: str, limit: int = 500,
                      start: datetime | None = None, end: datetime | None = None) -> list[Candle]:
        self._require_key()
        if timeframe not in TWELVE_INTERVALS:
            raise ProviderError(f"Timeframe {timeframe} não é compatível com Forex.")
        cache_key = (
            symbol.upper(), timeframe, int(limit),
            start.isoformat() if start else "", end.isoformat() if end else "",
        )
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(cache_key)
            if cached and now - cached[0] < 105:
                return cached[1].copy()
            while self._request_times and now - self._request_times[0] >= 60:
                self._request_times.popleft()
            if len(self._request_times) >= 7:
                raise ProviderError("Limite preventivo da Twelve Data: aguarde cerca de 1 minuto para tentar novamente.")
            self._request_times.append(now)
        requested = min(max(limit * (3 if timeframe == "3m" else 1), 1), 5000)
        params: dict[str, str | int] = {
            "symbol": symbol, "interval": TWELVE_INTERVALS[timeframe],
            "outputsize": requested, "apikey": self.api_key, "timezone": "UTC",
        }
        if start:
            params["start_date"] = start.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        if end:
            params["end_date"] = end.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        started = time.perf_counter()
        try:
            data = get_json(f"{self.base_url}/time_series", params, timeout=8)
        except ProviderError as exc:
            message = str(exc)
            lowered = message.lower()
            if "429" in lowered or "credit" in lowered or "rate limit" in lowered:
                raise ProviderError("Limite de créditos da Twelve Data atingido. Aguarde a renovação do plano gratuito antes de tentar novamente.") from exc
            if "401" in lowered or "403" in lowered or "api key" in lowered or "apikey" in lowered:
                raise ProviderError("A chave da Twelve Data é inválida ou não está ativa. Confira em APIs.") from exc
            raise
        if not isinstance(data, dict):
            raise ProviderError("A Twelve Data retornou uma resposta inesperada.")
        if data.get("status") == "error" or "values" not in data:
            message = str(data.get("message", "Twelve Data não retornou candles."))
            lowered = message.lower()
            try:
                code = int(data.get("code") or 0)
            except (TypeError, ValueError):
                code = 0
            if code == 429 or "credit" in lowered or "rate limit" in lowered:
                message = "Limite de créditos da Twelve Data atingido. Aguarde a renovação do plano gratuito."
            elif code in {401, 403} or "api key" in lowered or "apikey" in lowered:
                message = "A chave da Twelve Data é inválida ou não está ativa. Confira em APIs."
            elif "symbol" in lowered:
                message = f"O par {symbol} não está disponível na sua conta Twelve Data."
            raise ProviderError(message)
        candles = []
        for row in reversed(data["values"]):
            when = datetime.fromisoformat(str(row["datetime"]).replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            else:
                when = when.astimezone(timezone.utc)
            candles.append(Candle(when, float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]), float(row.get("volume") or 0)))
        if timeframe == "3m" and candles:
            source = pd.DataFrame({
                "time": [c.open_time for c in candles], "open": [c.open for c in candles],
                "high": [c.high for c in candles], "low": [c.low for c in candles],
                "close": [c.close for c in candles], "volume": [c.volume for c in candles],
            }).set_index("time")
            grouped = source.resample("3min").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
            candles = [Candle(index.to_pydatetime(), row.open, row.high, row.low, row.close, row.volume) for index, row in grouped.iterrows()]
        candles = candles[-limit:]
        if not candles:
            raise ProviderError(f"A Twelve Data não retornou candles para {symbol}.")
        latency = (time.perf_counter() - started) * 1000
        with self._lock:
            self._cache[cache_key] = (time.monotonic(), candles.copy())
            self._last_success_at = time.monotonic()
            self._last_latency_ms = latency
        return candles

    def list_symbols(self) -> list[str]:
        return FOREX_DEFAULTS.copy()

    def test_connection(self) -> tuple[bool, float | None, str]:
        if not self.api_key:
            return False, None, "CHAVE NÃO CONFIGURADA"
        with self._lock:
            if self._last_success_at and time.monotonic() - self._last_success_at < 900:
                return True, self._last_latency_ms, "ONLINE • CRÉDITOS POUPADOS"
        started = time.perf_counter()
        try:
            self.fetch_candles("EUR/USD", "1m", 1)
            return True, (time.perf_counter() - started) * 1000, "ONLINE"
        except ProviderError as exc:
            return False, None, str(exc)

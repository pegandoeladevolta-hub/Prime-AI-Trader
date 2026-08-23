from __future__ import annotations

import time
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock

from ..core.models import Candle, FOREX_DEFAULTS, TIMEFRAME_MINUTES
from ..crypto.public import _aggregate_candles
from ..market.base import MarketDataProvider, ProviderError
from ..market.http import get_json
from .twelve_data import TwelveDataProvider


@dataclass(frozen=True, slots=True)
class ForexLiveQuote:
    symbol: str
    price: float
    observed_at: datetime
    source: str
    bid: float | None = None
    ask: float | None = None
    spread: float | None = None


def merge_forex_quote(candle: Candle, quote: ForexLiveQuote, timeframe: str) -> Candle | None:
    """Atualiza uma vela com cotação real, sem inventar ticks, volume ou períodos."""
    minutes = TIMEFRAME_MINUTES.get(timeframe)
    if minutes is None or not math.isfinite(quote.price) or quote.price <= 0:
        return None
    observed = quote.observed_at.astimezone(timezone.utc)
    seconds = minutes * 60
    opened = datetime.fromtimestamp(int(observed.timestamp()) // seconds * seconds, tz=timezone.utc)
    previous_opened = candle.open_time.astimezone(timezone.utc)
    if opened < previous_opened:
        return None
    if opened == previous_opened:
        return Candle(
            candle.open_time, candle.open, max(candle.high, quote.price),
            min(candle.low, quote.price), quote.price, candle.volume,
            close_time=candle.close_time, quote_volume=candle.quote_volume,
            trades=candle.trades, taker_buy_volume=candle.taker_buy_volume,
            closed=False,
        )
    return Candle(opened, quote.price, quote.price, quote.price, quote.price, 0.0, closed=False)


class YahooForexProvider(MarketDataProvider):
    """Feed público sem chave. A disponibilidade pode variar e não é garantida."""

    name = "Yahoo Finance Forex público"
    base_urls = (
        "https://query1.finance.yahoo.com/v8/finance/chart",
        "https://query2.finance.yahoo.com/v8/finance/chart",
    )
    _intervals = {"1m": "1m", "3m": "1m", "5m": "5m", "15m": "15m",
                  "30m": "30m", "1h": "60m", "4h": "60m"}

    def __init__(self, cache_seconds: int = 45, quote_cache_seconds: int = 6) -> None:
        self.cache_seconds = cache_seconds
        self.quote_cache_seconds = quote_cache_seconds
        self._cache: dict[tuple, tuple[float, list[Candle]]] = {}
        self._quote_cache: dict[str, tuple[float, ForexLiveQuote]] = {}
        self._lock = Lock()

    def fetch_live_quote(self, symbol: str) -> ForexLiveQuote:
        key = symbol.upper()
        with self._lock:
            cached = self._quote_cache.get(key)
            if cached and time.monotonic() - cached[0] < self.quote_cache_seconds:
                return cached[1]
        ticker = key.replace("/", "") + "=X"
        payload = None
        last_error = ""
        for endpoint in self.base_urls:
            try:
                payload = get_json(
                    f"{endpoint}/{ticker}",
                    {"interval": "1m", "range": "1d", "includePrePost": "false"},
                    timeout=4,
                )
                break
            except ProviderError as exc:
                last_error = str(exc)
                if "429" in last_error:
                    break
        if not isinstance(payload, dict):
            raise ProviderError(f"Cotação Forex pública indisponível: {last_error or 'resposta inválida'}")
        chart = payload.get("chart") or {}
        if chart.get("error") or not chart.get("result"):
            raise ProviderError(f"Cotação Forex pública indisponível para {symbol}.")
        result = chart["result"][0]
        metadata = result.get("meta") or {}
        timestamps = result.get("timestamp") or []
        values = ((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
        latest = next(
            ((int(timestamps[index]), float(values[index]))
             for index in range(min(len(timestamps), len(values)) - 1, -1, -1)
             if values[index] is not None),
            None,
        )
        try:
            raw_price = float(metadata.get("regularMarketPrice"))
            raw_time = int(metadata.get("regularMarketTime") or (latest[0] if latest else 0))
        except (TypeError, ValueError):
            if latest is None:
                raise ProviderError(f"Cotação Forex pública inválida para {symbol}.") from None
            raw_time, raw_price = latest
        if latest is not None and latest[0] > raw_time:
            raw_time, raw_price = latest
        if raw_time <= 0 or not math.isfinite(raw_price) or raw_price <= 0:
            raise ProviderError(f"Cotação Forex pública inválida para {symbol}.")
        try:
            bid = float(metadata.get("bid"))
            ask = float(metadata.get("ask"))
            if not (math.isfinite(bid) and math.isfinite(ask) and 0 < bid <= ask):
                raise ValueError
            spread = ask - bid
        except (TypeError, ValueError):
            bid = ask = spread = None
        quote = ForexLiveQuote(
            key, raw_price, datetime.fromtimestamp(raw_time, tz=timezone.utc), self.name,
            bid, ask, spread,
        )
        with self._lock:
            self._quote_cache[key] = (time.monotonic(), quote)
        return quote

    def fetch_candles(self, symbol: str, timeframe: str, limit: int = 500,
                      start: datetime | None = None,
                      end: datetime | None = None) -> list[Candle]:
        interval = self._intervals.get(timeframe)
        if interval is None:
            raise ProviderError(f"Timeframe {timeframe} não está disponível no Forex público.")
        cache_key = (symbol.upper(), timeframe, limit,
                     start.isoformat() if start else "", end.isoformat() if end else "")
        with self._lock:
            cached = self._cache.get(cache_key)
            if cached and time.monotonic() - cached[0] < self.cache_seconds:
                return cached[1].copy()
        ticker = symbol.replace("/", "").upper() + "=X"
        params: dict[str, str | int] = {"interval": interval, "includePrePost": "false"}
        if start or end:
            final = end or datetime.now(timezone.utc)
            initial = start or final - timedelta(days=7 if interval == "1m" else 60)
            params.update({"period1": int(initial.timestamp()), "period2": int(final.timestamp())})
        else:
            params["range"] = "7d" if interval == "1m" else "60d" if interval in {"5m", "15m", "30m"} else "730d"
        payload: dict | list | None = None
        last_error = ""
        for endpoint in self.base_urls:
            try:
                payload = get_json(f"{endpoint}/{ticker}", params, timeout=5)
                break
            except ProviderError as exc:
                last_error = str(exc)
                if "429" in last_error:
                    break
        if payload is None:
            raise ProviderError(f"Forex público temporariamente indisponível: {last_error}")
        if not isinstance(payload, dict):
            raise ProviderError("O Forex público retornou uma resposta inesperada.")
        chart = payload.get("chart", {})
        if chart.get("error"):
            error = chart["error"]
            detail = error.get("description", "par indisponível") if isinstance(error, dict) else str(error)
            raise ProviderError(f"O par {symbol} não está disponível no Forex público: {detail}")
        results = chart.get("result") or []
        if not results:
            raise ProviderError(f"O Forex público não retornou histórico para {symbol}.")
        result = results[0]
        timestamps = result.get("timestamp") or []
        quote = (result.get("indicators", {}).get("quote") or [{}])[0]
        now = datetime.now(timezone.utc)
        base_minutes = 60 if interval == "60m" else int(interval[:-1])
        candles: list[Candle] = []
        for index, timestamp in enumerate(timestamps):
            try:
                values = [quote[key][index] for key in ("open", "high", "low", "close")]
            except (IndexError, KeyError, TypeError):
                continue
            if any(value is None for value in values):
                continue
            opened = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
            volumes = quote.get("volume") or []
            volume = volumes[index] if index < len(volumes) and volumes[index] is not None else 0
            candles.append(Candle(
                opened, *(float(value) for value in values), float(volume),
                closed=opened + timedelta(minutes=base_minutes) <= now,
            ))
        if timeframe in {"3m", "4h"}:
            candles = _aggregate_candles(candles, TIMEFRAME_MINUTES[timeframe], limit)
        else:
            candles = candles[-limit:]
        if not candles:
            raise ProviderError(f"O Forex público não retornou candles válidos para {symbol}.")
        with self._lock:
            self._cache[cache_key] = (time.monotonic(), candles.copy())
        return candles

    def list_symbols(self) -> list[str]:
        return FOREX_DEFAULTS.copy()

    def test_connection(self) -> tuple[bool, float | None, str]:
        started = time.perf_counter()
        try:
            self.fetch_candles("EUR/USD", "1m", 1)
            return True, (time.perf_counter() - started) * 1000, "PÚBLICO • SEM CHAVE"
        except ProviderError as exc:
            return False, None, str(exc)


class AlphaVantageForexProvider(MarketDataProvider):
    name = "Alpha Vantage Forex"
    endpoint = "https://www.alphavantage.co/query"
    _intervals = {"1m": "1min", "3m": "1min", "5m": "5min", "15m": "15min",
                  "30m": "30min", "1h": "60min", "4h": "60min"}

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key.strip()
        self._cache: dict[tuple[str, str], tuple[float, list[Candle]]] = {}

    def fetch_candles(self, symbol: str, timeframe: str, limit: int = 500,
                      start: datetime | None = None,
                      end: datetime | None = None) -> list[Candle]:
        if not self.api_key:
            raise ProviderError("Chave Alpha Vantage não configurada.")
        interval = self._intervals.get(timeframe)
        if interval is None:
            raise ProviderError(f"Timeframe {timeframe} não está disponível na Alpha Vantage.")
        key = (symbol.upper(), timeframe)
        cached = self._cache.get(key)
        if cached and time.monotonic() - cached[0] < 180:
            return cached[1][-limit:].copy()
        base, quote = symbol.upper().split("/", 1)
        payload = get_json(self.endpoint, {
            "function": "FX_INTRADAY", "from_symbol": base, "to_symbol": quote,
            "interval": interval, "outputsize": "full", "apikey": self.api_key,
        }, timeout=7)
        if not isinstance(payload, dict):
            raise ProviderError("A Alpha Vantage retornou uma resposta inesperada.")
        if payload.get("Information") or payload.get("Note") or payload.get("Error Message"):
            detail = payload.get("Information") or payload.get("Note") or payload.get("Error Message")
            raise ProviderError(f"Alpha Vantage indisponível ou com limite atingido: {detail}")
        rows = next((value for name, value in payload.items() if "Time Series FX" in name), {})
        candles = []
        base_minutes = 60 if interval == "60min" else int(interval.replace("min", ""))
        now = datetime.now(timezone.utc)
        for raw_time, row in sorted(rows.items()):
            opened = datetime.fromisoformat(raw_time).replace(tzinfo=timezone.utc)
            if (start and opened < start) or (end and opened > end):
                continue
            candles.append(Candle(
                opened, float(row["1. open"]), float(row["2. high"]),
                float(row["3. low"]), float(row["4. close"]), 0.0,
                closed=opened + timedelta(minutes=base_minutes) <= now,
            ))
        if timeframe in {"3m", "4h"}:
            candles = _aggregate_candles(candles, TIMEFRAME_MINUTES[timeframe], max(limit, 100))
        if not candles:
            raise ProviderError(f"A Alpha Vantage não retornou candles para {symbol}.")
        self._cache[key] = (time.monotonic(), candles.copy())
        return candles[-limit:]

    def list_symbols(self) -> list[str]:
        return FOREX_DEFAULTS.copy()

    def test_connection(self) -> tuple[bool, float | None, str]:
        if not self.api_key:
            return False, None, "CHAVE OPCIONAL NÃO CONFIGURADA"
        try:
            self.fetch_candles("EUR/USD", "5m", 1)
            return True, None, "ALPHA VANTAGE ONLINE"
        except ProviderError as exc:
            return False, None, str(exc)


class FrankfurterReferenceProvider:
    """Referência diária oficial; nunca é apresentada como candle intraday."""

    endpoint = "https://api.frankfurter.dev/v1/latest"

    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, float]] = {}

    def fetch_reference_rate(self, symbol: str) -> float:
        key = symbol.upper()
        cached = self._cache.get(key)
        if cached and time.monotonic() - cached[0] < 1800:
            return cached[1]
        base, quote = key.split("/", 1)
        payload = get_json(self.endpoint, {"base": base, "symbols": quote}, timeout=4)
        try:
            rate = float(payload["rates"][quote])
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError(f"Referência diária não disponível para {symbol}.") from exc
        self._cache[key] = (time.monotonic(), rate)
        return rate


class ResilientForexProvider(MarketDataProvider):
    name = "Forex gratuito com fallback"

    def __init__(self, twelve_data_key: str = "", alpha_vantage_key: str = "") -> None:
        self.twelve_data = TwelveDataProvider(twelve_data_key)
        self.yahoo = YahooForexProvider()
        self.alpha_vantage = AlphaVantageForexProvider(alpha_vantage_key)
        self.reference = FrankfurterReferenceProvider()
        self.last_provider_name = "Forex público"
        self.last_warning = ""

    @property
    def recommended_poll_ms(self) -> int:
        return 120_000 if self.last_provider_name == self.twelve_data.name else 60_000

    @property
    def recommended_quote_ms(self) -> int:
        return 10_000

    def fetch_live_quote(self, symbol: str) -> ForexLiveQuote:
        """Cotação rápida sem consumir créditos do Twelve Data ou da Alpha Vantage."""
        return self.yahoo.fetch_live_quote(symbol)

    def _providers(self) -> list[MarketDataProvider]:
        providers: list[MarketDataProvider] = []
        if self.twelve_data.api_key:
            providers.append(self.twelve_data)
        providers.append(self.yahoo)
        if self.alpha_vantage.api_key:
            providers.append(self.alpha_vantage)
        return providers

    def fetch_candles(self, symbol: str, timeframe: str, limit: int = 500,
                      start: datetime | None = None,
                      end: datetime | None = None) -> list[Candle]:
        errors = []
        providers = self._providers()
        for provider in providers:
            try:
                candles = provider.fetch_candles(symbol, timeframe, limit, start, end)
                if len(candles) < min(30, limit):
                    raise ProviderError("histórico insuficiente nesta fonte")
                self.last_provider_name = provider.name
                self.last_warning = "" if provider is providers[0] else (
                    f"Fonte principal indisponível; Forex carregado por {provider.name}."
                )
                return candles
            except ProviderError as exc:
                errors.append(f"{provider.name}: {exc}")
        raise ProviderError("Nenhuma fonte gratuita de Forex respondeu. " + " | ".join(errors))

    def list_symbols(self) -> list[str]:
        return FOREX_DEFAULTS.copy()

    def test_connection(self) -> tuple[bool, float | None, str]:
        errors = []
        for provider in self._providers():
            online, latency, detail = provider.test_connection()
            if online:
                self.last_provider_name = provider.name
                return True, latency, detail
            errors.append(detail)
        return False, None, errors[-1] if errors else "SEM FONTE PÚBLICA"

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from ..core.models import CRYPTO_DEFAULTS, Candle, TIMEFRAME_MINUTES
from ..market.base import MarketDataProvider, ProviderError
from ..market.http import get_json


def _aggregate_candles(candles: list[Candle], target_minutes: int,
                       limit: int) -> list[Candle]:
    if not candles:
        return []
    frame = pd.DataFrame({
        "time": [item.open_time for item in candles],
        "open": [item.open for item in candles],
        "high": [item.high for item in candles],
        "low": [item.low for item in candles],
        "close": [item.close for item in candles],
        "volume": [item.volume for item in candles],
    }).set_index("time").sort_index()
    grouped = frame.resample(f"{target_minutes}min").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna()
    now = datetime.now(timezone.utc)
    return [
        Candle(
            index.to_pydatetime(), float(row.open), float(row.high),
            float(row.low), float(row.close), float(row.volume),
            closed=index.to_pydatetime() + timedelta(minutes=target_minutes) <= now,
        )
        for index, row in grouped.iloc[-limit:].iterrows()
    ]


class CoinbaseSpotProvider(MarketDataProvider):
    """Backup público oficial; utiliza o mercado USD quando USDT não existir."""

    name = "Coinbase Exchange pública"
    base_url = "https://api.exchange.coinbase.com"
    _granularities = {"1m": 60, "3m": 60, "5m": 300, "15m": 900,
                      "30m": 900, "1h": 3600, "4h": 3600}

    def fetch_candles(self, symbol: str, timeframe: str, limit: int = 500,
                      start: datetime | None = None,
                      end: datetime | None = None) -> list[Candle]:
        granularity = self._granularities.get(timeframe)
        if granularity is None:
            raise ProviderError(f"Timeframe {timeframe} não está disponível na Coinbase.")
        target_minutes = TIMEFRAME_MINUTES[timeframe]
        multiplier = max(1, target_minutes * 60 // granularity)
        requested = min(max(limit * multiplier, 1), 1800)
        base = symbol.split("/")[0].upper()
        product = f"{base}-USD"
        rows: list[list] = []
        cursor = end.astimezone(timezone.utc) if end else datetime.now(timezone.utc)
        while len(rows) < requested:
            count = min(300, requested - len(rows))
            batch_start = max(start, cursor - timedelta(seconds=granularity * count)) if start else cursor - timedelta(seconds=granularity * count)
            payload = get_json(
                f"{self.base_url}/products/{product}/candles",
                {"granularity": granularity,
                 "start": batch_start.astimezone(timezone.utc).isoformat(),
                 "end": cursor.isoformat()},
                timeout=5,
            )
            if not isinstance(payload, list):
                raise ProviderError(f"A Coinbase não disponibilizou o mercado {product}.")
            if not payload:
                break
            rows.extend(payload)
            earliest = min(int(row[0]) for row in payload)
            cursor = datetime.fromtimestamp(earliest, tz=timezone.utc) - timedelta(seconds=1)
            if len(payload) < count or (start and cursor <= start):
                break
        now = datetime.now(timezone.utc)
        unique = {int(row[0]): row for row in rows if len(row) >= 5}
        candles = []
        for timestamp in sorted(unique):
            row = unique[timestamp]
            opened = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            candles.append(Candle(
                opened, float(row[3]), float(row[2]), float(row[1]),
                float(row[4]), float(row[5]) if len(row) > 5 else 0.0,
                closed=opened + timedelta(seconds=granularity) <= now,
            ))
        if not candles:
            raise ProviderError(f"A Coinbase não retornou candles para {product}.")
        if multiplier > 1:
            return _aggregate_candles(candles, target_minutes, limit)
        return candles[-limit:]

    def list_symbols(self) -> list[str]:
        return CRYPTO_DEFAULTS.copy()

    def test_connection(self) -> tuple[bool, float | None, str]:
        try:
            self.fetch_candles("BTC/USDT", "1m", 1)
            return True, None, "COINBASE PÚBLICA"
        except ProviderError as exc:
            return False, None, str(exc)


class KrakenSpotProvider(MarketDataProvider):
    """OHLC público da Kraken, limitado oficialmente aos 720 candles recentes."""

    name = "Kraken pública"
    endpoint = "https://api.kraken.com/0/public/OHLC"
    _intervals = {"1m": 1, "3m": 1, "5m": 5, "15m": 15,
                  "30m": 30, "1h": 60, "4h": 240}

    def fetch_candles(self, symbol: str, timeframe: str, limit: int = 500,
                      start: datetime | None = None,
                      end: datetime | None = None) -> list[Candle]:
        interval = self._intervals.get(timeframe)
        if interval is None:
            raise ProviderError(f"Timeframe {timeframe} não está disponível na Kraken.")
        base = symbol.split("/")[0].upper()
        if base == "BTC":
            base = "XBT"
        params: dict[str, int | str] = {"pair": f"{base}USD", "interval": interval}
        if start:
            params["since"] = int(start.timestamp())
        payload = get_json(self.endpoint, params, timeout=5)
        if not isinstance(payload, dict) or payload.get("error"):
            detail = payload.get("error") if isinstance(payload, dict) else "resposta inválida"
            raise ProviderError(f"A Kraken não disponibilizou {base}/USD: {detail}")
        result = payload.get("result", {})
        rows = next((value for key, value in result.items() if key != "last"), [])
        now = datetime.now(timezone.utc)
        candles = []
        for row in rows:
            opened = datetime.fromtimestamp(int(row[0]), tz=timezone.utc)
            if end and opened > end:
                continue
            candles.append(Candle(
                opened, float(row[1]), float(row[2]), float(row[3]),
                float(row[4]), float(row[6]),
                trades=int(row[7]) if len(row) > 7 else 0,
                closed=opened + timedelta(minutes=interval) <= now,
            ))
        if not candles:
            raise ProviderError(f"A Kraken não retornou candles para {base}/USD.")
        if timeframe == "3m":
            return _aggregate_candles(candles, 3, limit)
        return candles[-limit:]

    def list_symbols(self) -> list[str]:
        return CRYPTO_DEFAULTS.copy()

    def test_connection(self) -> tuple[bool, float | None, str]:
        try:
            self.fetch_candles("BTC/USDT", "1m", 1)
            return True, None, "KRAKEN PÚBLICA"
        except ProviderError as exc:
            return False, None, str(exc)


class ResilientCryptoProvider(MarketDataProvider):
    name = "Mercado cripto público"

    def __init__(self, primary: MarketDataProvider,
                 backups: list[MarketDataProvider] | None = None) -> None:
        self.primary = primary
        self.backups = backups if backups is not None else [CoinbaseSpotProvider(), KrakenSpotProvider()]
        self.last_provider_name = primary.name
        self.last_warning = ""

    def fetch_candles(self, symbol: str, timeframe: str, limit: int = 500,
                      start: datetime | None = None,
                      end: datetime | None = None) -> list[Candle]:
        errors = []
        for provider in [self.primary, *self.backups]:
            try:
                candles = provider.fetch_candles(symbol, timeframe, limit, start, end)
                if len(candles) < min(30, limit):
                    raise ProviderError("histórico insuficiente nesta fonte")
                self.last_provider_name = provider.name
                self.last_warning = "" if provider is self.primary else (
                    f"Binance indisponível; fonte pública alternativa: {provider.name}. "
                    "Compare o preço com o da plataforma."
                )
                return candles
            except ProviderError as exc:
                errors.append(f"{provider.name}: {exc}")
        raise ProviderError("Nenhuma fonte pública de criptomoedas respondeu. " + " | ".join(errors))

    def list_symbols(self) -> list[str]:
        try:
            return self.primary.list_symbols()
        except ProviderError:
            return CRYPTO_DEFAULTS.copy()

    def test_connection(self) -> tuple[bool, float | None, str]:
        return self.primary.test_connection()

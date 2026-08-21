from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from datetime import datetime, timezone

from ..core.models import CRYPTO_DEFAULTS, Candle
from ..market.base import MarketDataProvider, ProviderError
from ..market.http import get_json


class BinanceSpotProvider(MarketDataProvider):
    name = "Binance Spot"
    rest_url = "https://api.binance.com"
    public_urls = (
        "https://api.binance.com",
        "https://data-api.binance.vision",
        "https://api-gcp.binance.com",
    )
    ws_url = "wss://stream.binance.com:9443/ws"

    def __init__(self) -> None:
        self._symbols_cache: tuple[float, list[str]] | None = None

    @staticmethod
    def api_symbol(symbol: str) -> str:
        return symbol.replace("/", "").upper()

    def _public_json(self, path: str, params: dict | None = None,
                     timeout: float = 5.0) -> dict | list:
        errors: list[str] = []
        for base_url in self.public_urls:
            try:
                return get_json(f"{base_url}{path}", params, timeout=timeout)
            except ProviderError as exc:
                message = str(exc)
                # Limites por IP e símbolos inválidos não podem ser resolvidos
                # trocando o host; insistir apenas piora a disponibilidade.
                lowered = message.lower()
                if "429" in lowered or "418" in lowered or "invalid symbol" in lowered or "-1121" in lowered:
                    raise
                errors.append(message)
        raise ProviderError(f"Binance pública indisponível: {errors[-1] if errors else 'sem resposta'}")

    def fetch_candles(self, symbol: str, timeframe: str, limit: int = 500,
                      start: datetime | None = None, end: datetime | None = None) -> list[Candle]:
        requested = min(max(limit, 1), 5000)
        rows: list = []
        next_end = int(end.timestamp() * 1000) if end else None
        while len(rows) < requested:
            batch_limit = min(1000, requested - len(rows))
            params: dict[str, int | str] = {
                "symbol": self.api_symbol(symbol), "interval": timeframe, "limit": batch_limit,
            }
            if start:
                params["startTime"] = int(start.timestamp() * 1000)
            if next_end is not None:
                params["endTime"] = next_end
            batch = self._public_json("/api/v3/klines", params)
            if not isinstance(batch, list):
                raise ProviderError("A Binance retornou candles em formato inesperado.")
            if not batch:
                break
            rows = batch + rows
            if start or len(batch) < batch_limit:
                break
            next_end = int(batch[0][0]) - 1
        now = datetime.now(timezone.utc)
        unique = {int(row[0]): row for row in rows}
        ordered = [unique[key] for key in sorted(unique)][-requested:]
        return [Candle.from_binance(row, closed=datetime.fromtimestamp(int(row[6]) / 1000, tz=timezone.utc) <= now) for row in ordered]

    def list_symbols(self) -> list[str]:
        if self._symbols_cache and time.monotonic() - self._symbols_cache[0] < 600:
            return self._symbols_cache[1].copy()
        payload = self._public_json("/api/v3/exchangeInfo")
        candidates: dict[str, str] = {}
        stable_bases = {"USDT", "USDC", "FDUSD", "TUSD", "USDP", "DAI", "EUR", "BRL"}
        leveraged_suffixes = ("UP", "DOWN", "BULL", "BEAR")
        for item in payload.get("symbols", []):
            if item.get("status") == "TRADING" and item.get("quoteAsset") == "USDT" and item.get("isSpotTradingAllowed", True):
                base = str(item.get("baseAsset", "")).upper()
                if not base or base in stable_bases or base.endswith(leveraged_suffixes):
                    continue
                candidates[str(item["symbol"])] = f"{base}/USDT"
        ranked: list[str] = []
        try:
            tickers = self._public_json("/api/v3/ticker/24hr")
            if isinstance(tickers, list):
                liquid = sorted(
                    (
                        (float(item.get("quoteVolume") or 0), candidates[item["symbol"]])
                        for item in tickers if item.get("symbol") in candidates
                    ),
                    reverse=True,
                )
                ranked = [symbol for volume, symbol in liquid if volume >= 1_000_000][:100]
        except ProviderError:
            ranked = []
        if not ranked:
            ranked = [symbol for symbol in CRYPTO_DEFAULTS if self.api_symbol(symbol) in candidates]
            ranked.extend(sorted(symbol for symbol in candidates.values() if symbol not in ranked)[:70])
        self._symbols_cache = (time.monotonic(), ranked)
        return ranked.copy()

    def book_ticker(self, symbol: str) -> dict[str, float]:
        data = self._public_json("/api/v3/ticker/bookTicker", {"symbol": self.api_symbol(symbol)})
        bid, ask = float(data["bidPrice"]), float(data["askPrice"])
        return {"bid": bid, "ask": ask, "spread": ask - bid, "spread_pct": ((ask - bid) / bid * 100) if bid else 0.0}

    def test_connection(self) -> tuple[bool, float | None, str]:
        started = time.perf_counter()
        try:
            self._public_json("/api/v3/ping", timeout=5)
            return True, (time.perf_counter() - started) * 1000, "ONLINE"
        except ProviderError as exc:
            return False, None, str(exc)

    async def stream_candles(self, symbol: str, timeframe: str, callback: Callable[[Candle], None], stop_event) -> None:
        try:
            import websockets
        except ImportError as exc:
            raise ProviderError("Dependência websockets não instalada.") from exc
        stream = f"{self.api_symbol(symbol).lower()}@kline_{timeframe}"
        backoff = 1
        while not stop_event.is_set():
            try:
                async with websockets.connect(f"{self.ws_url}/{stream}", ping_interval=20, ping_timeout=20) as ws:
                    backoff = 1
                    while not stop_event.is_set():
                        raw = await asyncio.wait_for(ws.recv(), timeout=35)
                        k = json.loads(raw)["k"]
                        row = [k["t"], k["o"], k["h"], k["l"], k["c"], k["v"], k["T"], k["q"], k["n"], k["V"]]
                        callback(Candle.from_binance(row, closed=bool(k["x"])))
            except (OSError, asyncio.TimeoutError, KeyError, json.JSONDecodeError, websockets.WebSocketException):
                if stop_event.is_set():
                    break
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

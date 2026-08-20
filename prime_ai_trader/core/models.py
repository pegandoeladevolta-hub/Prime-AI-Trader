from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class Market(str, Enum):
    CRYPTO = "Criptomoedas"
    FOREX = "Forex"


class Direction(str, Enum):
    BUY = "COMPRA"
    SELL = "VENDA"
    WAIT = "AGUARDAR"


class SignalState(str, Enum):
    FORMING = "SINAL EM FORMAÇÃO"
    CONFIRMED = "SINAL CONFIRMADO"
    BLOCKED = "OPERAÇÕES BLOQUEADAS"
    WAITING = "SEM SINAL"


@dataclass(slots=True)
class Candle:
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: datetime | None = None
    quote_volume: float = 0.0
    trades: int = 0
    taker_buy_volume: float = 0.0
    closed: bool = True

    def as_dict(self) -> dict[str, Any]:
        item = asdict(self)
        item["open_time"] = self.open_time.isoformat()
        item["close_time"] = self.close_time.isoformat() if self.close_time else None
        return item

    @classmethod
    def from_binance(cls, row: list[Any], closed: bool = True) -> "Candle":
        return cls(
            open_time=datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc),
            open=float(row[1]), high=float(row[2]), low=float(row[3]),
            close=float(row[4]), volume=float(row[5]),
            close_time=datetime.fromtimestamp(int(row[6]) / 1000, tz=timezone.utc),
            quote_volume=float(row[7]), trades=int(row[8]),
            taker_buy_volume=float(row[9]), closed=closed,
        )


@dataclass(slots=True)
class Zone:
    kind: str
    low: float
    high: float
    strength: int
    last_touch: int

    @property
    def midpoint(self) -> float:
        return (self.low + self.high) / 2


@dataclass(slots=True)
class Signal:
    direction: Direction
    state: SignalState
    score: int
    probabilities: dict[str, float]
    entry: float | None
    horizon_minutes: int
    confluences: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    model_version: str = "rules-v1"
    calibrated_rate: float | None = None
    calibrated_samples: int = 0


@dataclass(slots=True)
class HealthStatus:
    name: str
    online: bool
    detail: str = ""
    latency_ms: float | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


CRYPTO_DEFAULTS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
FOREX_DEFAULTS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "AUD/USD",
    "USD/CAD", "NZD/USD", "EUR/JPY", "GBP/JPY", "EUR/GBP",
]
TIMEFRAMES = ["1m", "3m", "5m", "15m", "30m", "1h", "4h"]
TIMEFRAME_MINUTES = {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240}


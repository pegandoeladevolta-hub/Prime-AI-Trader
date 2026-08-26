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
    warnings: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    model_version: str = "rules-v1"
    calibrated_rate: float | None = None
    calibrated_samples: int = 0
    setup_name: str = "ANÁLISE EM FORMAÇÃO"
    waiting_reasons: list[str] = field(default_factory=list)
    validation_note: str = ""
    technical_score: int = 0
    model_score: int | None = None
    payout_percent: int = 80
    break_even_rate: float = 1 / 1.8
    expected_value: float | None = None
    market_regime: str = "ANALISANDO ESTRUTURA"
    structure_event: str = ""
    pullback_state: str = ""
    timeframe_context: str = ""
    strategy_name: str = ""
    source_lag_seconds: float | None = None
    confirmed_candle: bool = False
    next_candle_entry: bool = False
    candlestick_patterns: list[str] = field(default_factory=list)
    candlestick_context: str = ""
    reversal_risk: str = ""
    technical_stop: float | None = None
    technical_target: float | None = None
    technical_room_ratio: float | None = None
    technical_levels_note: str = ""
    buy_rule_points: int = 0
    sell_rule_points: int = 0
    buy_score: int = 0
    sell_score: int = 0
    buy_reasons: list[str] = field(default_factory=list)
    sell_reasons: list[str] = field(default_factory=list)
    independent_confirmations: list[str] = field(default_factory=list)
    momentum_votes: int = 0
    higher_timeframe_bias: str = "INDEFINIDA"
    higher_timeframe_label: str = ""
    higher_timeframe_regime: str = ""
    higher_timeframe_candles: int = 0
    higher_timeframe_source: str = ""
    pullback_primary_direction: str = ""
    pullback_correction_direction: str = ""
    pullback_phase: str = ""
    pullback_depth_atr: float | None = None
    reversal_votes: int = 0
    reversal_reasons: list[str] = field(default_factory=list)
    all_waiting_reasons: list[str] = field(default_factory=list)
    news_context_label: str = "SEM DADOS"
    news_context_summary: str = ""
    news_relevant_count: int = 0
    news_latest_age_minutes: float | None = None


@dataclass(slots=True)
class HealthStatus:
    name: str
    online: bool
    detail: str = ""
    latency_ms: float | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


PLATFORM_CRYPTO_DEFAULTS = [
    "BTC/USDT", "LTC/USDT", "ADA/USDT", "BNB/USDT", "XRP/USDT",
    "ETH/USDT", "SOL/USDT", "DOGE/USDT", "SUI/USDT", "XLM/USDT",
]

CRYPTO_NAMES = {
    "BTC": "Bitcoin", "LTC": "Litecoin", "ADA": "Cardano", "BNB": "BNB",
    "XRP": "XRP", "ETH": "Ethereum", "SOL": "Solana", "DOGE": "Dogecoin",
    "SUI": "Sui", "XLM": "Stellar", "TRX": "Tron", "AVAX": "Avalanche",
    "LINK": "Chainlink", "DOT": "Polkadot", "BCH": "Bitcoin Cash",
}

CRYPTO_DEFAULTS = [
    *PLATFORM_CRYPTO_DEFAULTS,
    "TRX/USDT", "AVAX/USDT", "LINK/USDT", "DOT/USDT", "BCH/USDT",
    "SHIB/USDT", "PEPE/USDT", "NEAR/USDT", "AAVE/USDT", "UNI/USDT", "ICP/USDT",
    "ETC/USDT", "ATOM/USDT", "FIL/USDT", "ARB/USDT", "OP/USDT",
    "INJ/USDT", "SEI/USDT", "FET/USDT", "RENDER/USDT", "WIF/USDT",
]
FOREX_DEFAULTS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "AUD/USD",
    "USD/CAD", "NZD/USD", "EUR/JPY", "GBP/JPY", "EUR/GBP",
    "EUR/CHF", "EUR/AUD", "EUR/CAD", "EUR/NZD", "GBP/CHF",
    "GBP/AUD", "GBP/CAD", "GBP/NZD", "AUD/JPY", "AUD/CAD",
    "AUD/NZD", "AUD/CHF", "NZD/JPY", "NZD/CAD", "NZD/CHF",
    "CAD/JPY", "CAD/CHF", "CHF/JPY",
]
TIMEFRAMES = ["1m", "3m", "5m", "15m", "30m", "1h", "4h"]
TIMEFRAME_MINUTES = {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240}

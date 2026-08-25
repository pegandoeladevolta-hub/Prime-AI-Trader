from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from ..core.models import Market


@dataclass(frozen=True, slots=True)
class ForexSession:
    name: str
    timezone_name: str
    opening_hour: int
    closing_hour: int

    def active(self, observed_at: datetime) -> bool:
        aware = observed_at if observed_at.tzinfo else observed_at.replace(tzinfo=timezone.utc)
        local = aware.astimezone(ZoneInfo(self.timezone_name))
        return local.weekday() < 5 and self.opening_hour <= local.hour < self.closing_hour


FOREX_SESSIONS = (
    ForexSession("TÓQUIO", "Asia/Tokyo", 9, 18),
    ForexSession("LONDRES", "Europe/London", 8, 17),
    ForexSession("NOVA YORK", "America/New_York", 8, 17),
)


def forex_sessions(observed_at: datetime) -> tuple[str, ...]:
    """Sessões por fuso IANA, incluindo as mudanças de horário de verão."""
    return tuple(session.name for session in FOREX_SESSIONS if session.active(observed_at))


def strategy_key(market: str) -> str:
    if market == Market.CRYPTO.value:
        return "crypto-structure-volume-candles-v6"
    if market == Market.FOREX.value:
        return "forex-session-priceaction-candles-v6"
    return "market-generic-candles-v6"

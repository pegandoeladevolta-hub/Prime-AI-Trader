from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone

from ..market.base import ProviderError
from ..market.http import get_json


@dataclass(slots=True)
class EconomicEvent:
    currency: str
    event: str
    scheduled_at: datetime
    impact: str
    previous: str = ""
    estimate: str = ""
    actual: str = ""


class FinnhubEconomicCalendar:
    endpoint = "https://finnhub.io/api/v1/calendar/economic"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key.strip()

    @staticmethod
    def _currency(row: dict) -> str:
        direct = str(row.get("currency") or "").upper().strip()
        if direct:
            return direct
        country = str(row.get("country") or "").upper().strip()
        return {
            "US": "USD", "UNITED STATES": "USD", "EU": "EUR", "EURO ZONE": "EUR",
            "GB": "GBP", "UNITED KINGDOM": "GBP", "JP": "JPY", "JAPAN": "JPY",
            "CH": "CHF", "SWITZERLAND": "CHF", "CA": "CAD", "CANADA": "CAD",
            "AU": "AUD", "AUSTRALIA": "AUD", "NZ": "NZD", "NEW ZEALAND": "NZD",
        }.get(country, country)

    def fetch(self, start: date, end: date) -> list[EconomicEvent]:
        if not self.api_key:
            raise ProviderError("Configure a chave Finnhub em Configurações > APIs.")
        data = get_json(self.endpoint, {"from": start.isoformat(), "to": end.isoformat(), "token": self.api_key})
        events = []
        for row in data.get("economicCalendar", []):
            raw_time = row.get("time") or row.get("date")
            try:
                when = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                when = datetime.combine(start, time.min, timezone.utc)
            impact = str(row.get("impact", row.get("importance", "medium"))).upper()
            events.append(EconomicEvent(
                self._currency(row), str(row.get("event", "Evento econômico")),
                when, impact, str(row.get("prev", "")), str(row.get("estimate", "")), str(row.get("actual", "")),
            ))
        return sorted(events, key=lambda item: item.scheduled_at)

    @staticmethod
    def blocking_event(events: list[EconomicEvent], now: datetime, minutes: int, currencies: tuple[str, ...] = ()) -> EconomicEvent | None:
        for event in events:
            distance = (event.scheduled_at - now).total_seconds() / 60
            high = event.impact in {"HIGH", "3", "3.0"}
            affected = not currencies or event.currency.upper() in currencies
            if high and affected and 0 <= distance <= minutes:
                return event
        return None


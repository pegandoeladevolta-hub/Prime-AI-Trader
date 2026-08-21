from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from threading import Lock
import time as clock

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


class PublicEconomicCalendar:
    """Calendário público semanal com cache de uma hora para respeitar o feed."""

    endpoint = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

    def __init__(self, cache_seconds: int = 3600) -> None:
        self.cache_seconds = cache_seconds
        self._cached_at = 0.0
        self._cached_events: list[EconomicEvent] = []
        self._lock = Lock()

    def fetch(self, start: date, end: date) -> list[EconomicEvent]:
        with self._lock:
            if self._cached_at and clock.monotonic() - self._cached_at < self.cache_seconds:
                return [event for event in self._cached_events if start <= event.scheduled_at.date() <= end]
        payload = get_json(self.endpoint, timeout=5)
        if not isinstance(payload, list):
            raise ProviderError("O calendário econômico público retornou uma resposta inesperada.")
        events = []
        for row in payload:
            try:
                when = datetime.fromisoformat(str(row.get("date", "")).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                continue
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            else:
                when = when.astimezone(timezone.utc)
            events.append(EconomicEvent(
                FinnhubEconomicCalendar._currency(row),
                str(row.get("title") or row.get("event") or "Evento econômico"),
                when, str(row.get("impact", "medium")).upper(),
                str(row.get("previous", "")), str(row.get("forecast", "")),
                str(row.get("actual", "")),
            ))
        events.sort(key=lambda item: item.scheduled_at)
        with self._lock:
            self._cached_events = events
            self._cached_at = clock.monotonic()
        return [event for event in events if start <= event.scheduled_at.date() <= end]

    blocking_event = staticmethod(FinnhubEconomicCalendar.blocking_event)


class ResilientEconomicCalendar:
    def __init__(self, finnhub_key: str = "") -> None:
        self.finnhub = FinnhubEconomicCalendar(finnhub_key)
        self.public = PublicEconomicCalendar()
        self.last_source = "CALENDÁRIO PÚBLICO"

    def fetch(self, start: date, end: date) -> list[EconomicEvent]:
        providers = ([self.finnhub] if self.finnhub.api_key else []) + [self.public]
        errors = []
        for provider in providers:
            try:
                events = provider.fetch(start, end)
                self.last_source = "FINNHUB" if provider is self.finnhub else "CALENDÁRIO PÚBLICO"
                return events
            except ProviderError as exc:
                errors.append(str(exc))
        raise ProviderError(errors[-1] if errors else "Calendário econômico indisponível.")

    blocking_event = staticmethod(FinnhubEconomicCalendar.blocking_event)

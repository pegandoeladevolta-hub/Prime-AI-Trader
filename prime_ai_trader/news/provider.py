from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from threading import Lock
import time

from ..market.base import ProviderError
from ..market.http import get_json


POSITIVE = {"approval", "approved", "growth", "surge", "rally", "adoption", "record", "gain", "bullish", "recovery"}
NEGATIVE = {"hack", "fraud", "war", "ban", "lawsuit", "liquidation", "crash", "loss", "bearish", "attack", "sec"}
HIGH_RISK = {"hack", "sec", "etf", "exchange", "fraud", "liquidation", "war", "fed", "interest rate", "cpi", "payroll", "unemployment", "ecb", "boe"}


@dataclass(slots=True)
class NewsItem:
    title: str
    url: str
    published_at: datetime
    sentiment: str
    high_risk: bool
    source: str = ""


def classify_text(text: str) -> tuple[str, bool]:
    lower = text.lower()
    contains = lambda term: re.search(rf"(?<!\w){re.escape(term)}(?!\w)", lower) is not None
    positive = sum(contains(word) for word in POSITIVE)
    negative = sum(contains(word) for word in NEGATIVE)
    sentiment = "POSITIVA" if positive > negative else "NEGATIVA" if negative > positive else "NEUTRA"
    return sentiment, any(contains(word) for word in HIGH_RISK)


class NewsProvider(ABC):
    @abstractmethod
    def fetch(self, query: str, limit: int = 20) -> list[NewsItem]:
        raise NotImplementedError


class GdeltNewsProvider(NewsProvider):
    endpoint = "https://api.gdeltproject.org/api/v2/doc/doc"

    def __init__(self, cache_seconds: int = 180, failure_cooldown_seconds: int = 90) -> None:
        self.cache_seconds = cache_seconds
        self.failure_cooldown_seconds = failure_cooldown_seconds
        self._cache: dict[str, tuple[float, list[NewsItem]]] = {}
        self._failure_until = 0.0
        self._last_error = ""
        self._lock = Lock()

    def fetch(self, query: str, limit: int = 20) -> list[NewsItem]:
        cache_key = f"{query.lower().strip()}:{min(limit, 250)}"
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(cache_key)
            if cached and now - cached[0] <= self.cache_seconds:
                return cached[1].copy()
            if now < self._failure_until:
                raise ProviderError(self._last_error or "Notícias temporariamente indisponíveis.")
        try:
            data = get_json(
                self.endpoint,
                {"query": query, "mode": "ArtList", "maxrecords": min(limit, 250), "format": "json", "sort": "HybridRel"},
                timeout=3.5,
            )
        except ProviderError as exc:
            with self._lock:
                self._last_error = str(exc)
                self._failure_until = time.monotonic() + self.failure_cooldown_seconds
            raise
        result = []
        for row in data.get("articles", []):
            sentiment, risky = classify_text(row.get("title", ""))
            raw_date = row.get("seendate", "")
            try:
                published = datetime.strptime(raw_date[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
            except ValueError:
                published = datetime.now(timezone.utc)
            result.append(NewsItem(row.get("title", "Sem título"), row.get("url", ""), published, sentiment, risky, row.get("domain", "GDELT")))
        with self._lock:
            self._cache[cache_key] = (time.monotonic(), result.copy())
            self._failure_until = 0.0
            self._last_error = ""
        return result

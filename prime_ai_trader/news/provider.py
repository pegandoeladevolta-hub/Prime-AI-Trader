from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone

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
    positive = sum(word in lower for word in POSITIVE)
    negative = sum(word in lower for word in NEGATIVE)
    sentiment = "POSITIVA" if positive > negative else "NEGATIVA" if negative > positive else "NEUTRA"
    return sentiment, any(word in lower for word in HIGH_RISK)


class NewsProvider(ABC):
    @abstractmethod
    def fetch(self, query: str, limit: int = 20) -> list[NewsItem]:
        raise NotImplementedError


class GdeltNewsProvider(NewsProvider):
    endpoint = "https://api.gdeltproject.org/api/v2/doc/doc"

    def fetch(self, query: str, limit: int = 20) -> list[NewsItem]:
        data = get_json(self.endpoint, {"query": query, "mode": "ArtList", "maxrecords": min(limit, 250), "format": "json", "sort": "HybridRel"})
        result = []
        for row in data.get("articles", []):
            sentiment, risky = classify_text(row.get("title", ""))
            raw_date = row.get("seendate", "")
            try:
                published = datetime.strptime(raw_date[:14], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
            except ValueError:
                published = datetime.now(timezone.utc)
            result.append(NewsItem(row.get("title", "Sem título"), row.get("url", ""), published, sentiment, risky, row.get("domain", "GDELT")))
        return result


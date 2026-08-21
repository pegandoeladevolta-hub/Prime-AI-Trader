from __future__ import annotations

from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import re
from threading import Lock
import time
from xml.etree import ElementTree

from ..core.models import CRYPTO_NAMES
from ..market.base import ProviderError
from ..market.http import get_json, get_text


POSITIVE = {"approval", "approved", "growth", "surge", "rally", "adoption", "record", "gain", "bullish", "recovery",
            "alta", "aprovação", "crescimento", "recuperação", "ganho", "valorização"}
NEGATIVE = {"hack", "fraud", "war", "ban", "lawsuit", "liquidation", "crash", "loss", "bearish", "attack", "sec",
            "queda", "fraude", "guerra", "ataque", "liquidação", "prejuízo", "proibição"}
HIGH_RISK = {"hack", "sec", "fraud", "liquidation", "war", "fed", "interest rate", "cpi", "payroll", "unemployment",
             "ecb", "boe", "fomc", "taxa de juros", "inflação", "ataque hacker", "falência"}


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


def market_news_query(symbol: str, market: str) -> str:
    base = symbol.split("/")[0].upper()
    if market == "Criptomoedas":
        name = CRYPTO_NAMES.get(base, base)
        if name.lower() == base.lower():
            return f"({base} OR cryptocurrency OR crypto)"
        return f'("{name}" OR {base} OR cryptocurrency)'
    quote = symbol.split("/")[-1].upper()
    currency_names = {
        "USD": "dollar", "EUR": "euro", "GBP": "pound", "JPY": "yen",
        "CHF": "franc", "AUD": "Australian dollar", "CAD": "Canadian dollar",
        "NZD": "New Zealand dollar",
    }
    first = currency_names.get(base, base)
    second = currency_names.get(quote, quote)
    return f'("{first}" OR "{second}" OR forex OR "interest rate")'


class RssNewsProvider(NewsProvider):
    def __init__(self, name: str, endpoint: str, search: bool = False) -> None:
        self.name = name
        self.endpoint = endpoint
        self.search = search

    @staticmethod
    def _date(raw: str | None) -> datetime:
        if raw:
            try:
                value = parsedate_to_datetime(raw)
                return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError, IndexError):
                try:
                    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
                except (TypeError, ValueError):
                    pass
        return datetime.now(timezone.utc)

    def fetch(self, query: str, limit: int = 20) -> list[NewsItem]:
        params = None
        if self.search:
            simplified = query.replace("(", "").replace(")", "").replace(" OR ", " ").replace('"', "")
            params = {"q": simplified, "hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"}
        try:
            root = ElementTree.fromstring(get_text(self.endpoint, params, timeout=3.5))
        except ElementTree.ParseError as exc:
            raise ProviderError(f"O feed {self.name} retornou XML inválido.") from exc
        rows = root.findall("./channel/item")
        atom = "{http://www.w3.org/2005/Atom}"
        if not rows:
            rows = root.findall(f"./{atom}entry")
        results = []
        for row in rows[: max(limit * 2, 10)]:
            title = (row.findtext("title") or row.findtext(f"{atom}title") or "").strip()
            if not title:
                continue
            link = row.findtext("link") or ""
            atom_link = row.find(f"{atom}link")
            if not link and atom_link is not None:
                link = atom_link.attrib.get("href", "")
            date_text = row.findtext("pubDate") or row.findtext(f"{atom}published") or row.findtext(f"{atom}updated")
            sentiment, risky = classify_text(title)
            source = (row.findtext("source") or self.name).strip()
            results.append(NewsItem(title, link, self._date(date_text), sentiment, risky, source))
            if len(results) >= limit:
                break
        return results


class CompositeNewsProvider(NewsProvider):
    """Combina GDELT e feeds públicos, com cache e redundância entre fontes."""

    def __init__(self, cache_seconds: int = 90) -> None:
        self.gdelt = GdeltNewsProvider(cache_seconds=cache_seconds)
        self.google = RssNewsProvider("Google Notícias", "https://news.google.com/rss/search", search=True)
        self.cointelegraph = RssNewsProvider("Cointelegraph", "https://cointelegraph.com/rss")
        self.coindesk = RssNewsProvider("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/")
        self.fxstreet = RssNewsProvider("FXStreet", "https://www.fxstreet.com/rss/news")
        self.forexlive = RssNewsProvider("ForexLive", "https://www.forexlive.com/feed/news")
        self.cache_seconds = cache_seconds
        self._cache: dict[str, tuple[float, list[NewsItem], list[str]]] = {}
        self._lock = Lock()
        self.last_sources: list[str] = []
        self.last_errors: list[str] = []

    @staticmethod
    def _is_forex(query: str) -> bool:
        lowered = query.lower()
        return any(term in lowered for term in (
            "forex", "dollar", "euro", "pound", "yen", "franc", "interest rate",
        ))

    def fetch(self, query: str, limit: int = 20) -> list[NewsItem]:
        cache_key = f"{query.strip().lower()}:{limit}"
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(cache_key)
            if cached and now - cached[0] < self.cache_seconds:
                self.last_sources = cached[2].copy()
                return cached[1].copy()
        specific = [self.fxstreet, self.forexlive] if self._is_forex(query) else [self.cointelegraph, self.coindesk]
        providers: list[NewsProvider] = [self.gdelt, self.google, *specific]
        items: list[NewsItem] = []
        sources: list[str] = []
        errors: list[str] = []
        with ThreadPoolExecutor(max_workers=len(providers), thread_name_prefix="prime-news") as executor:
            jobs = [(provider, executor.submit(provider.fetch, query, min(limit, 12))) for provider in providers]
            for provider, job in jobs:
                label = getattr(provider, "name", "GDELT")
                try:
                    found = job.result()
                except Exception as exc:
                    errors.append(f"{label}: {exc}")
                    continue
                if found:
                    items.extend(found)
                    sources.append(label)
        if not items and len(errors) == len(providers):
            self.last_errors = errors
            raise ProviderError("Nenhuma fonte pública de notícias respondeu. " + errors[0])
        deduplicated: dict[str, NewsItem] = {}
        for item in sorted(items, key=lambda row: row.published_at, reverse=True):
            normalized_title = re.sub(r"\W+", "", item.title.lower())
            key = normalized_title or item.url
            deduplicated.setdefault(key, item)
        result = list(deduplicated.values())[:limit]
        with self._lock:
            self.last_sources = sources.copy()
            self.last_errors = errors
            self._cache[cache_key] = (time.monotonic(), result.copy(), sources.copy())
        return result

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

from ..core.models import CRYPTO_NAMES, FOREX_DEFAULTS, Market


VEX_TRADEROOM_URL = "https://vexinvest.com/traderoom"
_CURRENCIES = {part for pair in FOREX_DEFAULTS for part in pair.split("/")}
_CRYPTO_ALIASES = {
    **{symbol: symbol for symbol in CRYPTO_NAMES},
    **{name.upper(): symbol for symbol, name in CRYPTO_NAMES.items()},
    "DOGE": "DOGE", "DOGECOIN": "DOGE", "RIPPLE": "XRP",
    "STELLAR LUMENS": "XLM", "BINANCE COIN": "BNB",
}


# Retorna somente textos visíveis que já são números/ativos. O contexto é uma
# lista fixa de rótulos permitidos: nunca inclui saldo, credenciais, cookies,
# armazenamento do navegador, campos digitados ou textos privados da conta.
VISIBLE_TRADEROOM_SCRIPT = r"""(() => {
  const labels = ["payout", "lucro", "retorno", "rentabilidade", "profit",
    "expiração", "expiracao", "expiration", "tempo", "restante", "remaining",
    "preço", "preco", "price", "cotação", "cotacao", "ativo", "asset",
    "mercado", "market", "compra", "venda", "trade"];
  const sensitive = /saldo|balance|carteira|wallet|depósito|deposito|deposit|saque|withdraw|email|e-mail|senha|password|conta|account/i;
  const asset = /\b(?:BITCOIN|LITECOIN|CARDANO|ETHEREUM|SOLANA|DOGECOIN|DOGE|STELLAR|RIPPLE|BTC|LTC|ADA|BNB|XRP|ETH|SOL|SUI|XLM|TRX|AVAX|LINK|DOT|BCH|SHIB|PEPE|NEAR|AAVE|UNI|ICP|ETC|ATOM|FIL|ARB|INJ|SEI|FET|RENDER|WIF|EUR\s*[/\\-]?\s*USD|GBP\s*[/\\-]?\s*USD|USD\s*[/\\-]?\s*JPY|(?:EUR|GBP|USD|AUD|NZD|CAD|CHF|JPY)\s*[/\\-]\s*(?:EUR|GBP|USD|AUD|NZD|CAD|CHF|JPY))\b/i;
  const nodes = document.querySelectorAll("main *, [role='main'] *, [class*='trad'] *, [class*='Trad'] *");
  const pool = nodes.length ? nodes : document.body ? document.body.querySelectorAll("*") : [];
  const candidates = [];
  for (const element of pool) {
    if (candidates.length >= 96) break;
    if (element.children.length || /^(SCRIPT|STYLE|INPUT|TEXTAREA|SELECT|OPTION)$/i.test(element.tagName)) continue;
    const rect = element.getBoundingClientRect();
    if (!rect.width || !rect.height || rect.bottom < 0 || rect.right < 0) continue;
    const style = getComputedStyle(element);
    if (style.visibility === "hidden" || style.display === "none" || Number(style.opacity) === 0) continue;
    const text = (element.innerText || element.textContent || "").trim().replace(/\s+/g, " ").slice(0, 64);
    if (!text || sensitive.test(text) || text.includes("@")) continue;
    const percent = /^\s*(?:lucro|retorno|payout|profit)?\s*\+?\d{1,3}(?:[,.]\d{1,2})?\s*%\s*$/i.test(text);
    const timer = /^\s*(?:\d{1,2}:)?\d{1,2}:\d{2}\s*$/.test(text);
    const period = /^\s*\d{1,3}\s*(?:m|min|mins|minuto|minutos|minute|minutes)\s*$/i.test(text);
    const money = /^\s*(?:R\$|US\$|\$)?\s*\d[\d., ]{1,18}\s*$/.test(text);
    const matchedAsset = asset.test(text) && text.length <= 32;
    if (!(percent || timer || period || money || matchedAsset)) continue;
    const parent = element.parentElement;
    const grandparent = parent && parent.parentElement;
    const vicinity = [element.className, element.getAttribute("aria-label"),
      parent && parent.className, parent && parent.getAttribute("aria-label"),
      parent && parent.innerText && parent.innerText.slice(0, 150),
      grandparent && grandparent.className].filter(Boolean).join(" ").toLowerCase();
    if (sensitive.test(vicinity)) continue;
    const context = labels.filter(label => vicinity.includes(label)).join(" ");
    const selected = element.getAttribute("aria-selected") === "true" ||
      (parent && parent.getAttribute("aria-selected") === "true") ||
      /active|selected|current|ativo/.test([element.className, parent && parent.className].join(" "));
    candidates.push({text, context, selected: Boolean(selected), y: Math.round(rect.top),
      kind: percent ? "percent" : timer ? "timer" : period ? "period" : matchedAsset ? "asset" : "price"});
  }
  return {url: location.href, login: Boolean(document.querySelector('input[type="password"]')),
          candidates, observed_at: new Date().toISOString()};
})()"""


@dataclass(slots=True, frozen=True)
class VexPlatformSnapshot:
    observed_at: datetime
    url: str
    authenticated: bool
    asset: str | None = None
    market: str | None = None
    payout_percent: int | None = None
    remaining_seconds: int | None = None
    horizon_minutes: int | None = None
    price: float | None = None
    otc: bool = False

    @property
    def expires_at(self) -> datetime | None:
        if self.remaining_seconds is None:
            return None
        return self.observed_at + timedelta(seconds=self.remaining_seconds)

    def fresh(self, max_age_seconds: float = 8.0, *, now: datetime | None = None) -> bool:
        current = now or datetime.now(timezone.utc)
        return abs((current - self.observed_at).total_seconds()) <= max_age_seconds


def _ascii(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", str(text)) if not unicodedata.combining(ch)).upper()


def normalize_vex_asset(text: str) -> tuple[str | None, str | None, bool]:
    normalized = _ascii(text).strip()
    otc = bool(re.search(r"\bOTC\b", normalized))
    normalized = re.sub(r"\bOTC\b", "", normalized).strip(" -_/()")
    pair = re.search(r"\b(EUR|GBP|USD|AUD|NZD|CAD|CHF|JPY)\s*[/\\-]?\s*(EUR|GBP|USD|AUD|NZD|CAD|CHF|JPY)\b", normalized)
    if pair and pair.group(1) != pair.group(2):
        return f"{pair.group(1)}/{pair.group(2)}", Market.FOREX.value, otc
    crypto_pair = re.search(r"\b([A-Z]{2,10})\s*[/\\-]\s*(USDT|USD)\b", normalized)
    if crypto_pair and crypto_pair.group(1) in _CRYPTO_ALIASES:
        return f"{_CRYPTO_ALIASES[crypto_pair.group(1)]}/USDT", Market.CRYPTO.value, otc
    for alias in sorted(_CRYPTO_ALIASES, key=len, reverse=True):
        if re.search(rf"(?<![A-Z]){re.escape(alias)}(?![A-Z])", normalized):
            return f"{_CRYPTO_ALIASES[alias]}/USDT", Market.CRYPTO.value, otc
    return None, None, otc


def parse_vex_percent(text: str) -> int | None:
    matched = re.search(r"(?<!\d)(\d{1,3})(?:[,.]\d{1,2})?\s*%", str(text))
    if not matched:
        return None
    value = int(matched.group(1))
    return value if 20 <= value <= 100 else None


def parse_vex_countdown(text: str) -> int | None:
    value = str(text).strip()
    if not re.fullmatch(r"(?:\d{1,2}:)?\d{1,2}:\d{2}", value):
        return None
    parts = [int(item) for item in value.split(":")]
    if parts[-1] >= 60 or len(parts) == 3 and parts[-2] >= 60:
        return None
    seconds = parts[-1] + parts[-2] * 60 + (parts[0] * 3600 if len(parts) == 3 else 0)
    return seconds if seconds <= 86_400 else None


def parse_localized_price(text: str) -> float | None:
    value = re.sub(r"(?:R\$|US\$|\$|\s)", "", str(text).strip())
    if not re.fullmatch(r"\d[\d.,]*", value):
        return None
    comma, point = value.rfind(","), value.rfind(".")
    if comma >= 0 and point >= 0:
        decimal, thousands = (",", ".") if comma > point else (".", ",")
        value = value.replace(thousands, "").replace(decimal, ".")
    elif comma >= 0:
        tail = len(value) - comma - 1
        value = value.replace(",", "") if tail == 3 and value.count(",") >= 1 else value.replace(",", ".")
    elif value.count(".") > 1:
        value = value.replace(".", "")
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) and number > 0 else None


def _score_candidate(item: dict, category: str) -> int:
    context = _ascii(item.get("context", ""))
    score = 12 if item.get("selected") else 0
    score += max(0, 8 - max(0, int(item.get("y", 0))) // 140)
    words = {
        "percent": ("PAYOUT", "LUCRO", "RETORNO", "RENTABILIDADE", "PROFIT"),
        "timer": ("EXPIRACAO", "EXPIRATION", "RESTANTE", "REMAINING", "TEMPO"),
        "period": ("EXPIRACAO", "EXPIRATION", "TEMPO", "TRADE"),
        "asset": ("ATIVO", "ASSET", "MERCADO", "MARKET", "TRADE"),
        "price": ("PRECO", "PRICE", "COTACAO", "ATIVO", "ASSET"),
    }.get(category, ())
    score += sum(15 for word in words if word in context)
    return score


def _best(candidates: list[dict], category: str, parser):
    found = []
    for item in candidates:
        if item.get("kind") != category:
            continue
        parsed = parser(item.get("text", ""))
        if parsed is not None and parsed != (None, None, False):
            found.append((_score_candidate(item, category), parsed))
    return max(found, key=lambda row: row[0])[1] if found else None


def snapshot_from_visible(payload: dict) -> VexPlatformSnapshot:
    url = str(payload.get("url", ""))
    parsed_url = urlparse(url)
    trusted = (
        parsed_url.scheme == "https"
        and parsed_url.hostname in {"vexinvest.com", "www.vexinvest.com"}
        and (parsed_url.path.rstrip("/") == "/traderoom" or parsed_url.path.startswith("/traderoom/"))
    )
    login = bool(payload.get("login"))
    try:
        observed = datetime.fromisoformat(str(payload.get("observed_at", "")).replace("Z", "+00:00"))
        observed = observed.astimezone(timezone.utc) if observed.tzinfo else observed.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        observed = datetime.now(timezone.utc)
    if not trusted or login:
        return VexPlatformSnapshot(observed, url, False)
    candidates = [item for item in payload.get("candidates", []) if isinstance(item, dict)][:96]
    normalized_asset = _best(candidates, "asset", normalize_vex_asset)
    asset, market, otc = normalized_asset if normalized_asset else (None, None, False)
    payout = _best(candidates, "percent", parse_vex_percent)
    countdown = _best(candidates, "timer", parse_vex_countdown)
    period = _best(candidates, "period", lambda text: int(re.match(r"\s*(\d+)", text).group(1)) if re.match(r"\s*(\d+)", text) else None)
    if period is not None and period not in {1, 2, 3, 5, 10, 15, 30, 60, 240}:
        period = None
    price_candidates = [item for item in candidates if item.get("kind") == "price" and _score_candidate(item, "price") >= 15]
    price = _best(price_candidates, "price", parse_localized_price)
    return VexPlatformSnapshot(observed, url, True, asset, market, payout, countdown, period, price, otc)


def compare_platform_market(snapshot: VexPlatformSnapshot | None, market: str, symbol: str,
                            reference_price: float | None = None) -> list[str]:
    if snapshot is None or not snapshot.authenticated or not snapshot.fresh():
        return []
    reasons = []
    if snapshot.otc:
        reasons.append("A VEX está em um ativo OTC; a cotação pública não representa esse mercado")
    if snapshot.market and snapshot.market != market:
        reasons.append(f"Mercado diferente: VEX {snapshot.market} / análise {market}")
    if snapshot.asset and snapshot.asset != symbol:
        reasons.append(f"Ativo diferente: VEX {snapshot.asset} / análise {symbol}")
    if snapshot.price and reference_price and reference_price > 0 and not reasons:
        distance = abs(snapshot.price - reference_price) / reference_price
        limit = 0.008 if market == Market.CRYPTO.value else 0.002
        if distance > limit:
            reasons.append(f"Preço da VEX diverge {distance * 100:.2f}% da fonte pública")
    return reasons


def _is_loopback_endpoint(url: str, port: int) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"ws", "http"} and parsed.hostname in {"127.0.0.1", "localhost"} and parsed.port == port


def _browser_executable() -> str | None:
    programs = [os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")]
    relatives = (Path("Google/Chrome/Application/chrome.exe"), Path("Microsoft/Edge/Application/msedge.exe"))
    for root in programs:
        if root:
            for relative in relatives:
                candidate = Path(root) / relative
                if candidate.is_file():
                    return str(candidate)
    for binary in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "msedge", "chrome"):
        located = shutil.which(binary)
        if located:
            return located
    return None


class VexBrowserBridge:
    """Lê somente o painel já visível em um navegador local dedicado ao usuário."""

    def __init__(self, profile_dir: Path, on_snapshot, on_status) -> None:
        self.profile_dir = Path(profile_dir)
        self.on_snapshot = on_snapshot
        self.on_status = on_status
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._port: int | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self._stop_event.is_set()

    def start(self) -> None:
        if self.running:
            return
        browser = _browser_executable()
        if not browser:
            raise RuntimeError("Instale Google Chrome ou Microsoft Edge para conectar a VEX Invest.")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            port = int(listener.getsockname()[1])
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        arguments = [
            browser, f"--remote-debugging-port={port}", "--remote-debugging-address=127.0.0.1",
            f"--user-data-dir={self.profile_dir}", "--no-first-run", "--no-default-browser-check",
            "--new-window", VEX_TRADEROOM_URL,
        ]
        kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(arguments, **kwargs)
        self._port = port
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="prime-vex-visible-sync")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _run(self) -> None:
        try:
            asyncio.run(self._observe())
        except Exception as exc:
            if not self._stop_event.is_set():
                self.on_status(f"VEX temporariamente indisponível: {str(exc)[:90]}")

    def _target(self) -> str | None:
        assert self._port is not None
        endpoint = f"http://127.0.0.1:{self._port}/json/list"
        with urlopen(endpoint, timeout=2.0) as response:
            targets = json.load(response)
        for item in targets:
            address = urlparse(str(item.get("url", "")))
            websocket = str(item.get("webSocketDebuggerUrl", ""))
            if address.hostname in {"vexinvest.com", "www.vexinvest.com"} and _is_loopback_endpoint(websocket, self._port):
                return websocket
        return None

    async def _observe(self) -> None:
        import websockets

        attempts = 0
        announced = ""
        while not self._stop_event.is_set():
            try:
                target = await asyncio.to_thread(self._target)
                if not target:
                    status = "VEX aberta • faça login e entre no traderoom"
                    if status != announced:
                        self.on_status(status)
                        announced = status
                    await asyncio.sleep(1.2)
                    continue
                async with websockets.connect(target, ping_interval=15, ping_timeout=10, close_timeout=2) as channel:
                    attempts = 0
                    identifier = 0
                    while not self._stop_event.is_set():
                        identifier += 1
                        await channel.send(json.dumps({
                            "id": identifier, "method": "Runtime.evaluate",
                            "params": {"expression": VISIBLE_TRADEROOM_SCRIPT, "returnByValue": True, "awaitPromise": False},
                        }))
                        while True:
                            message = json.loads(await asyncio.wait_for(channel.recv(), timeout=4))
                            if message.get("id") == identifier:
                                break
                        payload = message.get("result", {}).get("result", {}).get("value", {})
                        if isinstance(payload, dict):
                            snapshot = snapshot_from_visible(payload)
                            if snapshot.authenticated:
                                self.on_snapshot(snapshot)
                                announced = ""
                            else:
                                status = "VEX aberta • faça login diretamente no navegador"
                                if status != announced:
                                    self.on_status(status)
                                    announced = status
                        await asyncio.sleep(0.8)
            except (OSError, TimeoutError, asyncio.TimeoutError, json.JSONDecodeError,
                    websockets.WebSocketException):
                attempts += 1
                if attempts in {3, 10, 25}:
                    self.on_status("Aguardando o navegador da VEX abrir e conectar…")
                await asyncio.sleep(min(2.0, 0.4 + attempts * 0.1))

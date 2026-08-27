from __future__ import annotations

from ..core.models import Market
from ..platform.mt5 import MT5AccountSnapshot, MT5Bridge
from .controller import TradingController


_CRYPTO_HINTS = (
    "BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "LTC", "BCH", "DOT", "AVAX",
    "LINK", "XLM", "UNI", "ATOM", "NEAR", "TRX", "BNB", "MATIC", "POL",
    "USDT", "USDC", "CRYPTO", "BITCOIN", "ETHEREUM",
)


class _NoExternalNews:
    def fetch(self, *args, **kwargs):
        return []

    def clear_cache(self) -> None:
        return None


class _NoExternalCalendar:
    def fetch(self, *args, **kwargs):
        return []

    def blocking_event(self, *args, **kwargs):
        return None


class MT5TradingController(TradingController):
    """Controlador em que candles, ticks, ativos e ordens vêm do mesmo MT5."""

    def __init__(self) -> None:
        super().__init__()
        self.mt5 = MT5Bridge(self.settings.mt5_terminal_path or None)
        # O motor 1.2.6 mantém as mesmas interfaces, porém todas apontam para o
        # terminal MT5. Binance/Yahoo deixam de participar da leitura do gráfico.
        self.binance = self.mt5
        self.crypto = self.mt5
        self.forex = self.mt5
        self.news_provider = _NoExternalNews()
        self.calendar_provider = _NoExternalCalendar()
        self.settings.market_data_source = "MT5"
        self.settings.external_context_enabled = False
        self.settings.platform_name = "MT5"
        self.settings.platform_sync_enabled = False
        self.platform_snapshot = None

    def connect_mt5(self) -> MT5AccountSnapshot:
        self.mt5.terminal_path = self.settings.mt5_terminal_path or None
        account = self.mt5.connect()
        symbols = self.mt5.list_symbols()
        current = self.settings.mt5_symbol.strip()
        if not current or current not in symbols:
            preferred = self._preferred_symbol(symbols)
            if preferred:
                self.select_mt5_symbol(preferred, save=False)
        self.save_settings()
        return account

    @staticmethod
    def _preferred_symbol(symbols: list[str]) -> str:
        if not symbols:
            return ""
        for symbol in symbols:
            if "BTC" in symbol.upper():
                return symbol
        return symbols[0]

    def infer_market(self, symbol: str) -> str:
        details = self.mt5.symbol_details(symbol) if self.mt5.connected else {}
        haystack = " ".join([
            symbol,
            str(details.get("description") or ""),
            str(details.get("path") or ""),
            str(details.get("currency_base") or ""),
            str(details.get("currency_profit") or ""),
        ]).upper()
        return (
            Market.CRYPTO.value
            if any(hint in haystack for hint in _CRYPTO_HINTS)
            else Market.FOREX.value
        )

    def select_mt5_symbol(self, symbol: str, *, save: bool = True) -> None:
        symbol = str(symbol or "").strip()
        if not symbol:
            return
        market = self.infer_market(symbol)
        self.settings.mt5_symbol = symbol
        self.settings.market = market
        if market == Market.CRYPTO.value:
            self.settings.crypto_symbol = symbol
        else:
            self.settings.forex_symbol = symbol
        if save:
            self.save_settings()

    def provider(self):
        return self.mt5

    def symbol(self) -> str:
        if self.settings.mt5_symbol:
            return self.settings.mt5_symbol
        return super().symbol()

    def symbols(self) -> list[str]:
        try:
            return self.mt5.list_symbols()
        except Exception:
            return []

    def refresh_symbols(self) -> list[str]:
        return self.mt5.list_symbols()

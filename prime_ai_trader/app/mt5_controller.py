from __future__ import annotations

from ..core.models import Market
from ..ml.models import TrainingReport
from ..platform.mt5 import MT5AccountSnapshot
from ..platform.mt5_positions import MT5Bridge
from .controller import TradingController


_CRYPTO_HINTS = (
    "BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "LTC", "BCH", "DOT", "AVAX",
    "LINK", "XLM", "UNI", "ATOM", "NEAR", "TRX", "BNB", "MATIC", "POL",
    "USDT", "USDC", "CRYPTO", "BITCOIN", "ETHEREUM",
)

ANALYSIS_DEPTHS = {500, 1000, 1500, 2000, 3000}
LIVE_CHART_CANDLES = 200


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
    """Controlador em que candles, ticks, ativos, IA e ordens usam o mesmo MT5."""

    def __init__(self) -> None:
        super().__init__()
        self.mt5 = MT5Bridge(self.settings.mt5_terminal_path or None)
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

    def analysis_candles(self) -> int:
        """Profundidade realmente usada pelo motor ao vivo, não só pelo gráfico."""
        try:
            depth = int(self.settings.mt5_analysis_candles)
        except (TypeError, ValueError, AttributeError):
            depth = 2000
        if depth not in ANALYSIS_DEPTHS:
            depth = 2000
            self.settings.mt5_analysis_candles = depth
        return depth

    def _live_analysis_windows(self, history, timeframe: str):
        """Usa contexto profundo para decisão e mantém só 200 candles visíveis.

        Indicadores, price action, estrutura, Fibonacci e features recebem a janela
        completa escolhida pelo usuário. A janela menor existe apenas para desenho.
        """
        depth = self.analysis_candles()
        if len(history) < depth:
            raise ValueError(
                f"O MT5 entregou apenas {len(history)} candles. A análise atual exige "
                f"{depth} candles. Reduza a profundidade ou carregue mais histórico no MT5."
            )
        chart_candles = history[-LIVE_CHART_CANDLES:]
        candidates = history[-min(len(history), depth + 1):]
        eligible = self._decision_candles(candidates, timeframe)
        next_candle_entry = len(eligible) < len(candidates)
        decision_candles = eligible[-depth:]
        if len(decision_candles) < depth:
            raise ValueError(
                f"A análise aguarda {depth} candles analíticos fechados. "
                "O MT5 ainda não entregou histórico fechado suficiente."
            )
        return chart_candles, decision_candles, next_candle_entry

    def analyze(self, limit: int = 500):
        """Força o MT5 a fornecer a profundidade escolhida para cada releitura."""
        required = self.analysis_candles() + 1
        return super().analyze(limit=max(int(limit), required))

    def model_context(self) -> dict[str, str | int]:
        """Cada combinação escolhida pelo usuário possui seu próprio modelo."""
        context = super().model_context()
        context["execution_profile"] = self.settings.mt5_execution_profile
        context["analysis_candles"] = self.analysis_candles()
        context["training_candles"] = int(self.settings.mt5_training_candles)
        return context

    def ai_training_state(self) -> dict[str, object]:
        context = self.model_context()
        compatible = self.model_manager.is_compatible(context)
        report = self.model_manager.report if compatible else None
        return {
            "compatible": compatible,
            "context": context,
            "report": report,
            "analysis_candles": self.analysis_candles(),
            "requested_candles": int(self.settings.mt5_training_candles),
            "loaded_candles": len(self.snapshot.history_candles) if self.snapshot else 0,
        }

    def train(self) -> TrainingReport:
        """Treina a IA com histórico profundo vindo exclusivamente do MT5.

        O treinamento pode usar até 10.000 candles e o motor ao vivo passa a usar
        de 500 a 3.000 candles, conforme a profundidade selecionada pelo usuário.
        """
        limit = int(self.settings.mt5_training_candles)
        if limit not in {2000, 3000, 5000, 10000}:
            limit = 5000
            self.settings.mt5_training_candles = limit
        snapshot = self.analyze(limit=limit)
        loaded = len(snapshot.history_candles)
        if loaded < 1600:
            raise ValueError(
                f"O MT5 entregou apenas {loaded} candles para treinamento. "
                "São necessários pelo menos 1600 candles históricos para manter "
                "a validação temporal da IA."
            )
        return super().train()

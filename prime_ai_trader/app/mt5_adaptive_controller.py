from __future__ import annotations

from ..platform.mt5_dual import MT5Bridge
from .mt5_market_controller import MT5MarketTradingController


MT5_HISTORY_LOADING_PREFIX = "HISTÓRICO MT5 EM CARREGAMENTO"


class MT5AdaptiveTradingController(MT5MarketTradingController):
    """Controller MT5 que opera com o histórico disponível enquanto ele é carregado."""

    MIN_LIVE_CANDLES = 200
    LIVE_CHART_CANDLES = 200

    def __init__(self) -> None:
        super().__init__()
        # Troca somente a ponte MT5. O motor técnico/IA/sinais permanece o mesmo.
        old = self.mt5
        try:
            old.disconnect()
        except Exception:
            pass
        self.mt5 = MT5Bridge(self.settings.mt5_terminal_path or None)
        self.binance = self.mt5
        self.crypto = self.mt5
        self.forex = self.mt5
        self._effective_analysis_candles = 0
        self._analysis_reduced_warning = ""

    def configure_mt5_profile(
        self,
        environment: str,
        terminal_path: str = "",
    ) -> None:
        self.mt5.set_environment(environment, terminal_path or None)
        self.settings.mt5_terminal_path = str(terminal_path or "")

    def connect_mt5(self):
        account = self.mt5.connect()
        resolved = str(self.mt5.terminal_path or "")
        if resolved:
            self.settings.mt5_terminal_path = resolved
        symbols = self.mt5.list_symbols()
        current = self.settings.mt5_symbol.strip()
        if not current or current not in symbols:
            preferred = self._preferred_symbol(symbols)
            if preferred:
                self.select_mt5_symbol(preferred, save=False)
        self.save_settings()
        return account

    def _live_analysis_windows(self, history, timeframe: str):
        requested = self.analysis_candles()
        available = len(history)
        if available < self.MIN_LIVE_CANDLES:
            raise ValueError(
                f"{MT5_HISTORY_LOADING_PREFIX} [{available}/{self.MIN_LIVE_CANDLES}] • "
                "o Prime Trader solicitou mais barras ao servidor da corretora e tentará novamente."
            )

        effective = min(requested, available)
        self._effective_analysis_candles = effective
        if effective < requested:
            self._analysis_reduced_warning = (
                f"ANÁLISE ADAPTATIVA • usando {effective}/{requested} candles disponíveis; "
                "a profundidade aumenta automaticamente conforme o MT5 carregar histórico"
            )
        else:
            self._analysis_reduced_warning = ""

        chart_candles = history[-min(self.LIVE_CHART_CANDLES, available):]
        decision_candles = history[-effective:]
        return chart_candles, decision_candles, False

    def analysis_depth_status(self) -> dict[str, object]:
        return {
            "requested": self.analysis_candles(),
            "effective": int(self._effective_analysis_candles or 0),
            "reduced": bool(self._analysis_reduced_warning),
            "message": self._analysis_reduced_warning,
        }

    def model_context(self) -> dict[str, str | int]:
        context = super().model_context()
        context["mt5_environment"] = str(getattr(self.mt5, "environment", "CLEAR REAL"))
        return context


__all__ = ["MT5AdaptiveTradingController", "MT5_HISTORY_LOADING_PREFIX"]

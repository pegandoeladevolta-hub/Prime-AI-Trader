from __future__ import annotations

from datetime import datetime, timezone

from ..core.models import Market
from ..ml.models import TrainingReport
from ..ml.triple_barrier import build_mt5_barrier_labels
from ..platform.mt5 import MT5AccountSnapshot
from ..platform.mt5_positions import MT5Bridge
from ..priceaction.mt5_levels import label_lookahead_bars
from ..signals.mt5_engine import MT5SignalEngine
from .controller import TradingController


_CRYPTO_HINTS = (
    "BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "LTC", "BCH", "DOT", "AVAX",
    "LINK", "XLM", "UNI", "ATOM", "NEAR", "TRX", "BNB", "MATIC", "POL",
    "USDT", "USDC", "CRYPTO", "BITCOIN", "ETHEREUM",
)

ANALYSIS_DEPTHS = {500, 1000, 1500, 2000, 3000}
LIVE_CHART_CANDLES = 200
_TIMEFRAME_MINUTES = {
    "1m": 1, "3m": 3, "5m": 5, "15m": 15,
    "30m": 30, "1h": 60, "4h": 240,
}


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
    """Controlador MT5 orientado a Entrada + Stop Loss + Take Profit."""

    def __init__(self) -> None:
        super().__init__()
        self.mt5 = MT5Bridge(self.settings.mt5_terminal_path or None)
        self.binance = self.mt5
        self.crypto = self.mt5
        self.forex = self.mt5
        self.news_provider = _NoExternalNews()
        self.calendar_provider = _NoExternalCalendar()
        self.signal_engine = MT5SignalEngine(self.model_manager, self.model_context)
        self.settings.market_data_source = "MT5"
        self.settings.external_context_enabled = False
        self.settings.platform_name = "MT5"
        self.settings.platform_sync_enabled = False
        self.settings.horizon_minutes = 0
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
        try:
            depth = int(self.settings.mt5_analysis_candles)
        except (TypeError, ValueError, AttributeError):
            depth = 2000
        if depth not in ANALYSIS_DEPTHS:
            depth = 2000
            self.settings.mt5_analysis_candles = depth
        return depth

    def management_mode(self) -> str:
        mode = str(getattr(self.settings, "mt5_management_mode", "SCALP") or "SCALP").upper()
        if mode not in {"SCALP", "INTRADAY"}:
            mode = "SCALP"
            self.settings.mt5_management_mode = mode
        return mode

    def minimum_rr(self) -> float:
        try:
            value = float(getattr(self.settings, "mt5_min_rr", 1.5))
        except (TypeError, ValueError):
            value = 1.5
        allowed = {1.0, 1.5, 2.0, 2.5, 3.0}
        if value not in allowed:
            value = 1.5
            self.settings.mt5_min_rr = value
        return value

    def _decision_candles(self, candles, timeframe: str):
        """MT5 não possui 'entrada na próxima vela' herdada de opções binárias."""
        return candles

    def _live_analysis_windows(self, history, timeframe: str):
        depth = self.analysis_candles()
        if len(history) < depth:
            raise ValueError(
                f"O MT5 entregou apenas {len(history)} candles. A análise atual exige "
                f"{depth} candles. Reduza a profundidade ou carregue mais histórico no MT5."
            )
        chart_candles = history[-LIVE_CHART_CANDLES:]
        candidates = history[-min(len(history), depth + 1):]
        decision_candles = candidates[-depth:]
        if len(decision_candles) < depth:
            raise ValueError(
                f"A análise aguarda {depth} candles analíticos. "
                "O MT5 ainda não entregou histórico suficiente."
            )
        return chart_candles, decision_candles, False

    def analyze(self, limit: int = 500):
        required = self.analysis_candles() + 1
        return super().analyze(limit=max(int(limit), required))

    def model_context(self) -> dict[str, str | int]:
        """Contexto do modelo SL/TP, incluindo purga temporal da janela de labels."""
        context = super().model_context()
        lookahead = label_lookahead_bars(self.management_mode())
        timeframe_minutes = _TIMEFRAME_MINUTES.get(self.settings.timeframe, 1)
        # Este campo existe apenas porque o validador 1.2.6 usa horizon_minutes
        # para calcular a purga entre treino/teste. Não representa expiração real.
        context["horizon_minutes"] = lookahead * timeframe_minutes
        context["execution_profile"] = self.settings.mt5_execution_profile
        context["analysis_candles"] = self.analysis_candles()
        context["training_candles"] = int(self.settings.mt5_training_candles)
        context["trade_management"] = "SLTP"
        context["management_mode"] = self.management_mode()
        context["minimum_rr_x100"] = int(round(self.minimum_rr() * 100))
        context["label_lookahead_bars"] = lookahead
        return context

    def _labels_for_horizon(self, threshold: float, *, candles=None, indicators=None):
        history = candles or self._history_candles()
        values = indicators if indicators is not None else self.snapshot.indicators
        return build_mt5_barrier_labels(
            history, values,
            minimum_rr=self.minimum_rr(),
            management_mode=self.management_mode(),
        )

    def _settle_pending(self, symbol: str, timeframe: str, current_price: float,
                        candles=None) -> None:
        """Avalia sinais por barreiras SL/TP; nunca encerra resultado por tempo."""
        closed = [item for item in (candles or []) if item.closed]
        if not closed:
            return
        for row in self.repository.pending(symbol, timeframe):
            stop = row.get("technical_stop")
            target = row.get("technical_target")
            entry = row.get("entry")
            if stop is None or target is None or entry is None:
                continue
            try:
                created = datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                continue
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            direction = str(row.get("direction") or "")
            for candle in closed:
                if candle.open_time < created:
                    continue
                high, low = float(candle.high), float(candle.low)
                if direction == "COMPRA":
                    hit_stop, hit_target = low <= float(stop), high >= float(target)
                else:
                    hit_stop, hit_target = high >= float(stop), low <= float(target)
                if not hit_stop and not hit_target:
                    continue
                result = "LOSS" if hit_stop else "WIN"
                exit_price = float(stop) if hit_stop else float(target)
                self.repository.set_result(
                    int(row["id"]), exit_price, result, result_source="INFERRED",
                )
                break

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
            "management_mode": self.management_mode(),
            "minimum_rr": self.minimum_rr(),
            "label_lookahead_bars": label_lookahead_bars(self.management_mode()),
        }

    def train(self) -> TrainingReport:
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

    def backtest(self):
        original_payout = self.settings.payout_percent
        try:
            self.settings.payout_percent = int(round(self.minimum_rr() * 100))
            return super().backtest()
        finally:
            self.settings.payout_percent = original_payout

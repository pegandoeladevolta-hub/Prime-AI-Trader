from __future__ import annotations

import time
from datetime import datetime, timezone

from ..app.controller import AnalysisSnapshot, TradingController
from ..features.builder import FEATURE_SCHEMA_VERSION, build_features
from ..fibonacci.auto import automatic_fibonacci
from ..indicators.technical import calculate_all, candles_frame
from ..news.provider import summarize_asset_news
from ..priceaction.structure import analyze_structure
from ..strategies.context import strategy_key


MT5_MARKET = "B3"


class MT5AnalysisAdapter:
    """Adapta candles do MT5 ao mesmo motor analítico usado na v1.2.6.

    Não altera SignalEngine, Price Action, indicadores, thresholds ou política
    RÁPIDO/PRICE ACTION. A única diferença é a origem dos candles: o terminal
    MetaTrader 5 autenticado pelo próprio usuário.
    """

    def __init__(self, controller: TradingController) -> None:
        self.controller = controller
        self._last_record_signature = None

    def analyze(self, candles, symbol: str, timeframe: str) -> AnalysisSnapshot:
        settings = self.controller.settings
        if len(candles) < 201:
            raise ValueError(
                "O MetaTrader 5 ainda não entregou histórico suficiente. "
                "São necessários pelo menos 201 candles para preservar a lógica da v1.2.6."
            )

        chart_candles, decision_candles, next_candle_entry = (
            self.controller._live_analysis_windows(candles, timeframe)
        )
        frame = candles_frame(decision_candles)
        indicators = calculate_all(frame)
        last_atr = self.controller._value(indicators["atr_14"].iloc[-1])
        structure = analyze_structure(indicators, last_atr)
        chart_indicators, chart_structure = self.controller._chart_context(
            chart_candles, decision_candles, indicators, structure,
        )
        fibonacci = automatic_fibonacci(indicators)
        features = build_features(frame, MT5_MARKET, symbol)
        context = {
            "market": MT5_MARKET,
            "symbol": symbol,
            "timeframe": timeframe,
            "horizon_minutes": settings.horizon_minutes,
            "feature_schema": FEATURE_SCHEMA_VERSION,
            "strategy": strategy_key(MT5_MARKET),
            "sensitivity": settings.sensitivity,
            "mode": settings.mode,
        }

        # 100% é usado apenas como parâmetro neutro de compatibilidade do motor.
        # No modo PRICE ACTION sem modelo B3 treinado, payout não veta a leitura.
        signal = self.controller.signal_engine.generate(
            indicators,
            features,
            structure,
            fibonacci,
            settings.horizon_minutes,
            settings.sensitivity,
            decision_candles[-1].closed,
            [],
            settings.mode,
            context,
            payout_percent=100,
            source_lag_seconds=self.controller._source_lag_seconds(
                decision_candles, timeframe,
            ),
        )
        signal.next_candle_entry = next_candle_entry
        news_context, news = summarize_asset_news([], symbol, MT5_MARKET)

        snapshot = AnalysisSnapshot(
            candles=chart_candles,
            indicators=indicators,
            chart_indicators=chart_indicators,
            features=features,
            structure=structure,
            chart_structure=chart_structure,
            fibonacci=fibonacci,
            signal=signal,
            news=news,
            news_context=news_context,
            calendar_events=[],
            symbol=symbol,
            timeframe=timeframe,
            market=MT5_MARKET,
            generated_at=datetime.now(timezone.utc),
            data_source="MetaTrader 5",
            history_candles=list(candles),
        )
        self.controller.snapshot = snapshot
        self.controller._snapshot_cache[(MT5_MARKET, symbol, timeframe)] = (
            time.monotonic(), snapshot,
        )

        record_signature = (
            symbol,
            timeframe,
            decision_candles[-1].open_time,
            signal.state.value,
            signal.direction.value,
        )
        if record_signature != self._last_record_signature:
            try:
                self.controller._record_decision(snapshot)
                self._last_record_signature = record_signature
            except Exception:
                self.controller.logger.exception(
                    "Não foi possível registrar a decisão MT5 no histórico local"
                )
        return snapshot

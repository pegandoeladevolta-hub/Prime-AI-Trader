from __future__ import annotations

import json
import logging
import math
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from ..backtest.engine import BacktestEngine, BacktestResult
from ..config.settings import AppSettings, SecretStore, SettingsStore, app_data_dir
from ..core.models import (
    CRYPTO_DEFAULTS, FOREX_DEFAULTS, PLATFORM_CRYPTO_DEFAULTS, Candle,
    Direction, HealthStatus, Market, Signal, SignalState,
)
from ..crypto.binance import BinanceSpotProvider
from ..crypto.public import ResilientCryptoProvider
from ..database.repository import Repository
from ..economic_calendar.finnhub import EconomicEvent, ResilientEconomicCalendar
from ..features.builder import FEATURE_SCHEMA_VERSION, build_features, build_labels, build_time_labels
from ..fibonacci.auto import FibonacciResult, automatic_fibonacci
from ..forex.public import ResilientForexProvider
from ..indicators.technical import calculate_all, candles_frame
from ..ml.models import ModelManager, TrainingReport, purge_size_from_context
from ..news.provider import (
    AssetNewsContext, CompositeNewsProvider, NewsItem, market_news_query,
    summarize_asset_news,
)
from ..platform.vex import VexPlatformSnapshot, compare_platform_market
from ..priceaction.structure import MarketStructure, analyze_structure
from ..radar.engine import RadarEngine, RadarItem
from ..signals.engine import SignalEngine, sensitivity_profile
from ..signals.timing import (
    effective_platform_entry_remaining_seconds, use_last_closed_candle_for_entry,
)
from ..strategies.context import strategy_key


LIVE_MINIMUM_CANDLES = 200
LIVE_FETCH_MINIMUM_CANDLES = 201
LIVE_MAXIMUM_CANDLES = 200
TRAINING_MINIMUM_CANDLES = 1600
GRAPH_EVALUATION_PLATFORM = "AVALIAÇÃO GRÁFICA"
HIGHER_TIMEFRAME_MAP = {
    "1m": "5m", "3m": "15m", "5m": "15m", "15m": "1h",
    "30m": "4h", "1h": "4h",
}


@dataclass(slots=True)
class HigherTimeframeContext:
    timeframe: str
    bias: str
    regime: str
    structure: str
    candle_count: int
    source: str
    adx: float | None = None
    available: bool = True
    note: str = ""


@dataclass(slots=True)
class AnalysisSnapshot:
    candles: list[Candle]
    indicators: pd.DataFrame
    chart_indicators: pd.DataFrame
    features: pd.DataFrame
    structure: MarketStructure
    chart_structure: MarketStructure
    fibonacci: FibonacciResult | None
    signal: Signal
    news: list[NewsItem]
    news_context: AssetNewsContext
    calendar_events: list[EconomicEvent]
    symbol: str
    timeframe: str
    market: str
    generated_at: datetime
    data_source: str = ""
    forex_reference_rate: float | None = None
    history_candles: list[Candle] = field(default_factory=list)
    higher_timeframe: HigherTimeframeContext | None = None
    chart_evaluations: list[dict] = field(default_factory=list)


@dataclass(slots=True)
class EvaluationSummary:
    started_at: datetime
    initial_balance: float
    current_balance: float
    profit_loss: float
    operations: int
    wins: int
    losses: int
    draws: int
    pending: int
    status: str


class TradingController:
    def __init__(self) -> None:
        self.logger = logging.getLogger("prime_ai_trader.controller")
        self.settings_store = SettingsStore()
        self.secret_store = SecretStore()
        self.settings = self.settings_store.load()
        self.secrets = self.secret_store.load()
        self.binance = BinanceSpotProvider()
        self.crypto = ResilientCryptoProvider(self.binance)
        self.forex = ResilientForexProvider(
            self.secrets.get("twelve_data_key", ""),
            self.secrets.get("alpha_vantage_key", ""),
        )
        self.model_manager = ModelManager()
        self.signal_engine = SignalEngine(self.model_manager)
        self.backtest_engine = BacktestEngine()
        self.radar_engine = RadarEngine()
        self.repository = Repository()
        self.news_provider = CompositeNewsProvider()
        self.calendar_provider = ResilientEconomicCalendar(self.secrets.get("finnhub_key", ""))
        self.snapshot: AnalysisSnapshot | None = None
        self._snapshot_cache: dict[tuple[str, str, str], tuple[float, AnalysisSnapshot]] = {}
        self._higher_timeframe_cache: dict[
            tuple[str, str, str], tuple[float, HigherTimeframeContext]
        ] = {}
        self._quality_gate: dict[tuple, BacktestResult] = {}
        self._last_saved_signature: tuple | None = None
        self._radar_offset = 0
        self.last_radar_note = ""
        self.websocket_online = False
        self.platform_snapshot: VexPlatformSnapshot | None = None
        self._evaluation_fallback_started_at = datetime.now(timezone.utc)
        if not self.settings.evaluation_started_at:
            self.settings.evaluation_started_at = self._evaluation_fallback_started_at.isoformat()
            self.settings_store.save(self.settings)
        self._last_settings_signature = json.dumps(
            asdict(self.settings), sort_keys=True, ensure_ascii=False,
        )

    def save_settings(self) -> None:
        self.settings_store.save(self.settings)
        signature = json.dumps(asdict(self.settings), sort_keys=True, ensure_ascii=False)
        if signature != self._last_settings_signature:
            self._last_settings_signature = signature
            try:
                self.repository.record_decision({
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "event_type": "CONFIGURAÇÃO ALTERADA",
                    "market": self.settings.market,
                    "symbol": self.symbol(),
                    "timeframe": self.settings.timeframe,
                    "horizon_minutes": self.settings.horizon_minutes,
                    "platform": self.settings.platform_name,
                    "strategy": strategy_key(self.settings.market),
                    "sensitivity": self.settings.sensitivity,
                    "mode": self.settings.mode,
                    "direction": "AGUARDAR",
                    "state": "CONFIGURAÇÃO",
                    "score": 0,
                    "payout_percent": self.settings.payout_percent,
                    "stake_amount": self.settings.stake_amount,
                    "reason_summary": (
                        f"{self.settings.market} • {self.symbol()} • "
                        f"{self.settings.timeframe}/{self.settings.horizon_minutes}m • "
                        f"{self.settings.sensitivity} • {self.settings.mode} • "
                        "avaliação gráfica automática"
                    ),
                    "settings": asdict(self.settings),
                })
            except Exception:
                self.logger.exception("Não foi possível registrar a alteração de configuração")

    def save_secrets(self, values: dict[str, str]) -> None:
        self.secrets.update(values)
        self.secret_store.save(self.secrets)
        self.forex = ResilientForexProvider(
            self.secrets.get("twelve_data_key", ""),
            self.secrets.get("alpha_vantage_key", ""),
        )
        self.calendar_provider = ResilientEconomicCalendar(self.secrets.get("finnhub_key", ""))
        self.logger.info("Chaves de API atualizadas com armazenamento protegido")

    def provider(self):
        return self.crypto if self.settings.market == Market.CRYPTO.value else self.forex

    def symbol(self) -> str:
        return self.settings.crypto_symbol if self.settings.market == Market.CRYPTO.value else self.settings.forex_symbol

    def symbols(self) -> list[str]:
        if self.settings.market == Market.CRYPTO.value:
            return CRYPTO_DEFAULTS.copy()
        return FOREX_DEFAULTS.copy()

    def model_context(self) -> dict[str, str | int]:
        return {
            "market": self.settings.market, "symbol": self.symbol(), "timeframe": self.settings.timeframe,
            "horizon_minutes": self.settings.horizon_minutes, "feature_schema": FEATURE_SCHEMA_VERSION,
            "strategy": strategy_key(self.settings.market),
            "sensitivity": self.settings.sensitivity,
            "mode": self.settings.mode,
        }

    @staticmethod
    def _source_lag_seconds(candles: list[Candle], timeframe: str) -> float | None:
        if not candles:
            return None
        candle = candles[-1]
        minutes = {"1m": 1, "3m": 3, "5m": 5, "15m": 15,
                   "30m": 30, "1h": 60, "4h": 240}.get(timeframe, 1)
        expected = candle.open_time.astimezone(timezone.utc) + timedelta(minutes=minutes)
        # A vela aberta recebe atualizações do stream/quote; a idade do horário de
        # abertura não é confundida com atraso da fonte.
        if not candle.closed and datetime.now(timezone.utc) <= expected + timedelta(seconds=15):
            return 0.0
        return max(0.0, (datetime.now(timezone.utc) - expected).total_seconds())

    def _decision_candles(self, candles: list[Candle], timeframe: str) -> list[Candle]:
        if use_last_closed_candle_for_entry(
            candles, timeframe=timeframe,
            horizon_minutes=self.settings.horizon_minutes,
            sensitivity=self.settings.sensitivity, mode=self.settings.mode,
        ):
            return candles[:-1]
        return candles

    def _live_analysis_windows(self, history: list[Candle], timeframe: str
                               ) -> tuple[list[Candle], list[Candle], bool]:
        """Separa as 200 velas do gráfico das 200 velas válidas para decisão."""
        if len(history) < LIVE_MINIMUM_CANDLES:
            raise ValueError(
                "A API retornou poucos candles. São necessários pelo menos "
                "200 candles para analisar o contexto do ativo."
            )
        chart_candles = history[-LIVE_MAXIMUM_CANDLES:]
        candidates = history[-LIVE_FETCH_MINIMUM_CANDLES:]
        eligible = self._decision_candles(candidates, timeframe)
        next_candle_entry = len(eligible) < len(candidates)
        decision_candles = eligible[-LIVE_MINIMUM_CANDLES:]
        if len(decision_candles) < LIVE_MINIMUM_CANDLES:
            raise ValueError(
                "A análise aguarda 200 candles analíticos fechados. "
                "A fonte entregou uma vela aberta sem histórico fechado suficiente."
            )
        return chart_candles, decision_candles, next_candle_entry

    @staticmethod
    def _chart_context(candles: list[Candle], decision_candles: list[Candle],
                       indicators: pd.DataFrame,
                       structure: MarketStructure) -> tuple[pd.DataFrame, MarketStructure]:
        """Mantém overlays alinhados ao gráfico sem usar a vela aberta na decisão."""
        if ([item.open_time for item in candles]
                == [item.open_time for item in decision_candles]):
            return indicators, structure
        chart_indicators = calculate_all(candles_frame(candles))
        chart_atr = TradingController._value(chart_indicators["atr_14"].iloc[-1])
        return chart_indicators, analyze_structure(chart_indicators, chart_atr)

    @staticmethod
    def _apply_news_context(signal: Signal, context: AssetNewsContext, *,
                            strict: bool) -> Signal:
        signal.news_context_label = context.label
        signal.news_context_summary = context.summary
        signal.news_relevant_count = context.relevant_count
        signal.news_latest_age_minutes = context.latest_age_minutes
        if context.relevant_count == 0:
            signal.warnings.append(
                "Contexto noticioso sem manchetes relevantes; decisão baseada apenas no mercado e nos indicadores"
            )
            return signal
        if context.fresh_count == 0:
            signal.warnings.append(
                "As notícias relevantes encontradas estão desatualizadas e não influenciaram a direção"
            )
            return signal
        if signal.direction == Direction.WAIT or not context.directional_bias:
            return signal
        if signal.direction.value == context.directional_bias:
            signal.confluences.append(
                f"Contexto de notícias recentes {context.label.lower()} alinhado com a direção"
            )
            return signal
        conflict = (
            f"Contexto de notícias recentes {context.label.lower()} conflita com o sinal "
            f"de {signal.direction.value.lower()}"
        )
        if not strict:
            signal.warnings.append(conflict)
            return signal
        signal.blockers.append(conflict)
        signal.waiting_reasons.insert(0, conflict)
        signal.all_waiting_reasons.insert(0, conflict)
        signal.direction = Direction.WAIT
        signal.state = SignalState.BLOCKED
        signal.entry = None
        signal.technical_stop = None
        signal.technical_target = None
        signal.technical_room_ratio = None
        signal.technical_levels_note = ""
        return signal

    def _evaluation_started_at(self) -> datetime:
        raw = self.settings.evaluation_started_at
        try:
            parsed = datetime.fromisoformat(raw)
            return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            return self._evaluation_fallback_started_at

    def reset_evaluation(self) -> EvaluationSummary:
        started = datetime.now(timezone.utc)
        self._evaluation_fallback_started_at = started
        self.settings.evaluation_started_at = started.isoformat()
        self._last_saved_signature = None
        self.save_settings()
        return self.evaluation_summary()

    def evaluation_summary(self) -> EvaluationSummary:
        started_at = self._evaluation_started_at()
        values = self.repository.evaluation_session(started_at)
        profit_loss = float(values.get("profit_loss") or 0.0)
        initial = max(0.01, float(self.settings.evaluation_initial_balance))
        current = initial + profit_loss
        status = "SALDO ESGOTADO" if current <= 0 else "ACOMPANHANDO SINAIS"
        return EvaluationSummary(
            started_at=started_at, initial_balance=initial,
            current_balance=current, profit_loss=profit_loss,
            operations=int(values.get("operations") or 0),
            wins=int(values.get("wins") or 0), losses=int(values.get("losses") or 0),
            draws=int(values.get("draws") or 0), pending=int(values.get("pending") or 0),
            status=status,
        )

    def _higher_timeframe_context(self, provider, market: str, symbol: str,
                                  timeframe: str) -> HigherTimeframeContext:
        target = HIGHER_TIMEFRAME_MAP.get(timeframe)
        if not target:
            return HigherTimeframeContext(
                timeframe="", bias="INDEFINIDA", regime="SEM CONTEXTO SUPERIOR",
                structure="", candle_count=0, source="", available=False,
                note=f"Não há timeframe superior público configurado acima de {timeframe}",
            )
        key = (market, symbol, target)
        cached = self._higher_timeframe_cache.get(key)
        if cached and time.monotonic() - cached[0] <= 120.0:
            return cached[1]
        try:
            history = provider.fetch_candles(
                symbol, target, limit=LIVE_FETCH_MINIMUM_CANDLES,
            )
            closed = [candle for candle in history if candle.closed]
            if len(closed) < LIVE_MINIMUM_CANDLES:
                raise ValueError(
                    f"A fonte entregou {len(closed)}/200 candles fechados em {target}"
                )
            candles = closed[-LIVE_MINIMUM_CANDLES:]
            indicators = calculate_all(candles_frame(candles))
            last = indicators.iloc[-1]
            close = float(last["close"])
            ema_21 = float(last["ema_21"])
            ema_50 = float(last["ema_50"])
            adx = self._value(last.get("adx_14"))
            plus_di = float(last.get("plus_di") or 0.0)
            minus_di = float(last.get("minus_di") or 0.0)
            atr = self._value(last.get("atr_14"))
            structure = analyze_structure(indicators, atr)
            if (close > ema_21 > ema_50 and plus_di >= minus_di
                    and structure.trend != "BAIXA"):
                bias = "ALTA"
            elif (close < ema_21 < ema_50 and minus_di >= plus_di
                    and structure.trend != "ALTA"):
                bias = "BAIXA"
            else:
                bias = "LATERAL"
            regime = (
                "TENDÊNCIA FORTE" if bias in {"ALTA", "BAIXA"} and (adx or 0) >= 23
                else "TENDÊNCIA" if bias in {"ALTA", "BAIXA"}
                else "TRANSIÇÃO / LATERAL"
            )
            structure_label = " / ".join(
                [*structure.sequence, *([structure.breakout] if structure.breakout else [])]
            ) or structure.trend
            context = HigherTimeframeContext(
                timeframe=target, bias=bias, regime=regime,
                structure=structure_label, candle_count=len(candles),
                source=str(getattr(provider, "last_provider_name", "") or "fonte pública"),
                adx=adx,
            )
        except Exception as exc:
            self.logger.warning("Contexto real de timeframe superior indisponível: %s", exc)
            context = HigherTimeframeContext(
                timeframe=target, bias="INDEFINIDA", regime="INDISPONÍVEL",
                structure="", candle_count=0,
                source=str(getattr(provider, "last_provider_name", "") or "fonte pública"),
                available=False, note=str(exc),
            )
        self._higher_timeframe_cache[key] = (time.monotonic(), context)
        return context

    @staticmethod
    def _apply_higher_timeframe_context(
        signal: Signal, context: HigherTimeframeContext,
    ) -> Signal:
        signal.higher_timeframe_bias = context.bias
        signal.higher_timeframe_label = context.timeframe
        signal.higher_timeframe_regime = context.regime
        signal.higher_timeframe_candles = context.candle_count
        signal.higher_timeframe_source = context.source
        if not context.available:
            warning = (
                f"Timeframe superior real {context.timeframe or 'indisponível'}: "
                f"{context.note or 'sem dados públicos suficientes'}"
            )
            if warning not in signal.warnings:
                signal.warnings.append(warning)
            return signal
        label = (
            f"Timeframe superior real {context.timeframe}: {context.bias.lower()} • "
            f"{context.candle_count} candles fechados"
        )
        if signal.direction == Direction.WAIT:
            return signal
        aligned = (
            signal.direction == Direction.BUY and context.bias == "ALTA"
            or signal.direction == Direction.SELL and context.bias == "BAIXA"
        )
        conflict = (
            signal.direction == Direction.BUY and context.bias == "BAIXA"
            or signal.direction == Direction.SELL and context.bias == "ALTA"
        )
        if aligned:
            if label not in signal.confluences:
                signal.confluences.append(label)
            return signal
        if not conflict:
            warning = f"{label}; contexto superior misto, sem confirmação adicional"
            if warning not in signal.warnings:
                signal.warnings.append(warning)
            return signal
        reason = (
            f"Sinal contra o timeframe superior real {context.timeframe} "
            f"({context.bias.lower()}, {context.regime.lower()})"
        )
        signal.blockers.insert(0, reason)
        signal.waiting_reasons.insert(0, reason)
        signal.all_waiting_reasons.insert(0, reason)
        signal.direction = Direction.WAIT
        signal.state = SignalState.BLOCKED
        signal.entry = None
        signal.technical_stop = None
        signal.technical_target = None
        signal.technical_room_ratio = None
        signal.technical_levels_note = ""
        return signal

    @staticmethod
    def _merge_history_candle(history: list[Candle], candle: Candle) -> list[Candle]:
        merged = history.copy()
        if merged and merged[-1].open_time == candle.open_time:
            merged[-1] = candle
        else:
            if (merged and merged[-1].open_time < candle.open_time
                    and not merged[-1].closed):
                previous = merged[-1]
                merged[-1] = replace(
                    previous, closed=True,
                    close_time=previous.close_time or candle.open_time,
                )
            merged.append(candle)
        return merged[-5000:]

    def cached_snapshot(self, max_age_seconds: float = 120.0) -> AnalysisSnapshot | None:
        key = (self.settings.market, self.symbol(), self.settings.timeframe)
        cached = self._snapshot_cache.get(key)
        if not cached or time.monotonic() - cached[0] > max_age_seconds:
            return None
        return cached[1]

    def refresh_symbols(self) -> list[str]:
        symbols = self.provider().list_symbols()
        if self.settings.market == Market.CRYPTO.value and symbols:
            priority = [symbol for symbol in PLATFORM_CRYPTO_DEFAULTS if symbol in symbols]
            return priority + [symbol for symbol in symbols if symbol not in priority]
        return symbols or self.symbols()

    @staticmethod
    def _value(value: float) -> float | None:
        return None if value is None or not math.isfinite(float(value)) else float(value)

    def analyze(self, limit: int = 500) -> AnalysisSnapshot:
        market = self.settings.market
        timeframe = self.settings.timeframe
        horizon_minutes = self.settings.horizon_minutes
        sensitivity = self.settings.sensitivity
        payout_percent = self.settings.payout_percent
        mode = self.settings.mode
        high_impact_block_minutes = self.settings.high_impact_block_minutes
        strict_risk_blocks = self.settings.strict_risk_blocks
        symbol = self.settings.crypto_symbol if market == Market.CRYPTO.value else self.settings.forex_symbol
        provider = self.crypto if market == Market.CRYPTO.value else self.forex
        context = {
            "market": market, "symbol": symbol, "timeframe": timeframe,
            "horizon_minutes": horizon_minutes, "feature_schema": FEATURE_SCHEMA_VERSION,
            "strategy": strategy_key(market), "sensitivity": sensitivity, "mode": mode,
        }
        self.logger.info("Iniciando análise | mercado=%s símbolo=%s timeframe=%s", market, symbol, timeframe)
        history_candles = provider.fetch_candles(
            symbol, timeframe, limit=max(limit, LIVE_FETCH_MINIMUM_CANDLES),
        )
        data_source = str(getattr(provider, "last_provider_name", "") or "fonte pública")
        provider_warning = str(getattr(provider, "last_warning", "") or "")
        higher_timeframe = self._higher_timeframe_context(
            provider, market, symbol, timeframe,
        )
        candles, decision_candles, next_candle_entry = self._live_analysis_windows(
            history_candles, timeframe,
        )
        frame = candles_frame(decision_candles)
        indicators = calculate_all(frame)
        last_atr = self._value(indicators["atr_14"].iloc[-1])
        structure = analyze_structure(indicators, last_atr)
        chart_indicators, chart_structure = self._chart_context(
            candles, decision_candles, indicators, structure,
        )
        fibonacci = automatic_fibonacci(indicators)
        features = build_features(frame, market, symbol)
        raw_news: list[NewsItem] = []
        news: list[NewsItem] = []
        calendar_events: list[EconomicEvent] = []
        blockers: list[str] = []
        warnings: list[str] = []
        reference_rate = None
        query = market_news_query(symbol, market)
        if market == Market.FOREX.value:
            today = datetime.now(timezone.utc).date()
            with ThreadPoolExecutor(max_workers=3, thread_name_prefix="prime-context") as executor:
                news_job = executor.submit(self.news_provider.fetch, query, 12)
                calendar_job = executor.submit(
                    self.calendar_provider.fetch, today, today + timedelta(days=1),
                )
                reference_job = executor.submit(self.forex.reference.fetch_reference_rate, symbol)
                try:
                    raw_news = news_job.result()
                except Exception as exc:
                    self.logger.warning("Notícias indisponíveis: %s", exc)
                try:
                    calendar_events = calendar_job.result()
                except Exception as exc:
                    self.logger.warning("Calendário econômico público indisponível: %s", exc)
                try:
                    reference_rate = reference_job.result()
                except Exception as exc:
                    self.logger.info("Referência diária opcional indisponível: %s", exc)
        else:
            try:
                raw_news = self.news_provider.fetch(query, limit=12)
            except Exception as exc:
                self.logger.warning("Notícias indisponíveis: %s", exc)

        news_context, news = summarize_asset_news(raw_news, symbol, market)

        recent_limit = datetime.now(timezone.utc) - timedelta(minutes=60)
        risky = [item for item in news if item.high_risk and item.published_at >= recent_limit]
        if risky:
            message = f"Notícia de alto risco: {risky[0].title[:90]}"
            (blockers if strict_risk_blocks else warnings).append(message)
        if market == Market.FOREX.value and calendar_events:
            event = self.calendar_provider.blocking_event(
                calendar_events, datetime.now(timezone.utc), high_impact_block_minutes,
                tuple(symbol.split("/")),
            )
            if event:
                message = f"Evento de alto impacto: {event.event} ({event.currency})"
                (blockers if strict_risk_blocks else warnings).append(message)
        if market == Market.CRYPTO.value and provider_warning:
            warnings.append(provider_warning)
        signal = self.signal_engine.generate(
            indicators, features, structure, fibonacci, horizon_minutes,
            sensitivity, decision_candles[-1].closed, blockers, mode, context,
            payout_percent=payout_percent,
            source_lag_seconds=self._source_lag_seconds(decision_candles, timeframe),
        )
        signal.next_candle_entry = next_candle_entry
        signal.warnings.extend(warnings)
        signal = self._apply_news_context(signal, news_context, strict=strict_risk_blocks)
        signal = self._apply_higher_timeframe_context(signal, higher_timeframe)
        signal = self._apply_quality_gate(signal, market, symbol, timeframe, horizon_minutes)
        signal = self._apply_platform_alignment(signal, market, symbol, float(indicators["close"].iloc[-1]))
        calibrated, samples = self.repository.calibration(
            signal.score, market, symbol, timeframe, horizon_minutes, mode,
            sensitivity=sensitivity, strategy=strategy_key(market), result_source="MANUAL",
        )
        signal.calibrated_rate, signal.calibrated_samples = calibrated, samples
        snapshot = AnalysisSnapshot(
            candles=candles, indicators=indicators, chart_indicators=chart_indicators,
            features=features, structure=structure, chart_structure=chart_structure,
            fibonacci=fibonacci, signal=signal, news=news,
            news_context=news_context, calendar_events=calendar_events,
            symbol=symbol, timeframe=timeframe, market=market,
            generated_at=datetime.now(timezone.utc), data_source=data_source,
            forex_reference_rate=reference_rate, history_candles=history_candles,
            higher_timeframe=higher_timeframe,
        )
        self.snapshot = snapshot
        self._snapshot_cache[(market, symbol, timeframe)] = (time.monotonic(), snapshot)
        self._settle_pending(symbol, timeframe, float(indicators["close"].iloc[-1]), candles)
        signal_id = self._record_signal(
            signal, market, symbol, timeframe, decision_candles, indicators, mode,
        )
        snapshot.chart_evaluations = self.repository.chart_evaluations(
            symbol, timeframe, started_at=self._evaluation_started_at(),
        )
        self._record_decision(snapshot, signal_id=signal_id)
        return snapshot

    def _record_signal(self, signal: Signal, market: str, symbol: str,
                       timeframe: str, candles: list[Candle],
                       indicators: pd.DataFrame, mode: str) -> int | None:
        if signal.state != SignalState.CONFIRMED or signal.direction == Direction.WAIT or not candles:
            return None
        signature = (
            symbol, timeframe, candles[-1].open_time, signal.direction.value,
        )
        if signature == self._last_saved_signature:
            return None
        last = indicators.iloc[-1]
        values = {key: self._value(last.get(key)) for key in (
            "rsi_14", "macd", "macd_signal", "adx_14", "plus_di", "minus_di",
            "atr_14", "vwap", "obv", "cci_20", "williams_r", "volume_relative",
        )}
        signal_id = self.repository.save_signal(
            signal, market, symbol, timeframe, values, mode,
            platform=GRAPH_EVALUATION_PLATFORM,
            strategy=strategy_key(market), sensitivity=self.settings.sensitivity,
            stake_amount=self.settings.stake_amount,
        )
        self._last_saved_signature = signature
        self.logger.info("Sinal salvo | %s %s score=%s setup=%s", symbol,
                         signal.direction.value, signal.score, signal.setup_name)
        return signal_id

    @staticmethod
    def _history_json(value):
        if isinstance(value, datetime):
            return value.isoformat()
        if is_dataclass(value) and not isinstance(value, type):
            return TradingController._history_json(asdict(value))
        if isinstance(value, dict):
            return {str(key): TradingController._history_json(item)
                    for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [TradingController._history_json(item) for item in value]
        if hasattr(value, "item") and not isinstance(value, (str, bytes)):
            return TradingController._history_json(value.item())
        if isinstance(value, float):
            return value if math.isfinite(value) else None
        if isinstance(value, (str, int, bool)) or value is None:
            return value
        return str(value)

    def _record_decision(self, snapshot: AnalysisSnapshot, *,
                         signal_id: int | None = None) -> int | None:
        """Grava a leitura completa sem expor chaves, cookies ou dados de conta."""
        signal = snapshot.signal
        settings = asdict(self.settings)
        reasons = signal.waiting_reasons or signal.blockers or signal.confluences
        platform = self.platform_snapshot
        visible_platform = None
        if platform is not None:
            visible_platform = {
                "platform_name": platform.platform_name,
                "observed_at": platform.observed_at,
                "authenticated": platform.authenticated,
                "fresh": platform.fresh(),
                "asset": platform.asset,
                "market": platform.market,
                "payout_percent": platform.payout_percent,
                "remaining_seconds": platform.remaining_seconds,
                "horizon_minutes": platform.horizon_minutes,
                "price": platform.price,
                "otc": platform.otc,
            }
        if signal.state == SignalState.CONFIRMED:
            event_type = "SINAL CONFIRMADO" if signal_id is not None else "REAVALIAÇÃO DO SINAL"
        elif signal.state == SignalState.FORMING:
            event_type = "SINAL EM FORMAÇÃO"
        elif signal.state == SignalState.BLOCKED:
            event_type = "ANÁLISE BLOQUEADA"
        else:
            event_type = "ANÁLISE / AGUARDAR"

        signal_data = asdict(signal)
        payload = self._history_json({
            "created_at": snapshot.generated_at,
            "event_type": event_type,
            "signal_id": signal_id,
            "market": snapshot.market,
            "symbol": snapshot.symbol,
            "timeframe": snapshot.timeframe,
            "horizon_minutes": signal.horizon_minutes,
            "platform": settings.get("platform_name") or "MANUAL",
            "strategy": signal.strategy_name or strategy_key(snapshot.market),
            "sensitivity": settings.get("sensitivity", ""),
            "mode": settings.get("mode", ""),
            "direction": signal.direction.value,
            "state": signal.state.value,
            "score": signal.score,
            "payout_percent": signal.payout_percent,
            "stake_amount": settings.get("stake_amount", 1.0),
            "pullback_state": signal.pullback_state,
            "market_regime": signal.market_regime,
            "structure_event": signal.structure_event,
            "reason_summary": " | ".join(str(item) for item in reasons[:4]),
            "technical_score": signal.technical_score,
            "model_score": signal.model_score,
            "source_name": snapshot.data_source,
            "settings": settings,
            "signal": signal_data,
            "indicators": snapshot.indicators.iloc[-1].to_dict(),
            "features": snapshot.features.iloc[-1].to_dict() if not snapshot.features.empty else {},
            "structure": asdict(snapshot.structure),
            "fibonacci": asdict(snapshot.fibonacci) if snapshot.fibonacci else None,
            "recent_candles": [item.as_dict() for item in snapshot.candles[-8:]],
            "news": [asdict(item) for item in snapshot.news[:12]],
            "news_context": asdict(snapshot.news_context),
            "economic_events": [asdict(item) for item in snapshot.calendar_events[:12]],
            "visible_platform": visible_platform,
            "source_lag_seconds": signal.source_lag_seconds,
            "forex_reference_rate": snapshot.forex_reference_rate,
            "analysis_candles": len(snapshot.indicators),
            "chart_candles": len(snapshot.candles),
            "training_candles": len(snapshot.history_candles or snapshot.candles),
            "higher_timeframe": (
                asdict(snapshot.higher_timeframe) if snapshot.higher_timeframe else None
            ),
            "evaluation": asdict(self.evaluation_summary()),
        })
        try:
            return self.repository.record_decision(payload)
        except Exception:
            self.logger.exception("Não foi possível registrar a decisão operacional")
            return None

    def _settle_pending(self, symbol: str, timeframe: str, current_price: float,
                        candles: list[Candle] | None = None) -> None:
        now = datetime.now(timezone.utc)
        for row in self.repository.pending(symbol, timeframe):
            created = datetime.fromisoformat(row["created_at"])
            expires_at = created + timedelta(minutes=int(row["horizon_minutes"]))
            if now < expires_at:
                continue
            entry = float(row["entry"])
            expiry_candle = next((item for item in candles or [] if item.open_time >= expires_at), None)
            exit_price = expiry_candle.open if expiry_candle is not None else current_price
            move = (exit_price - entry) / entry if entry else 0
            signed = move if row["direction"] == "COMPRA" else -move
            try:
                indicator_values = json.loads(row.get("indicators_json") or "{}")
                atr_value = float(indicator_values.get("atr_14") or 0)
            except (TypeError, ValueError, json.JSONDecodeError):
                atr_value = 0.0
            atr_pct = atr_value / entry if entry and atr_value > 0 else 0.0
            market_floor = 0.00001 if row.get("market") == Market.CRYPTO.value else 0.000002
            neutral_threshold = max(market_floor, atr_pct * 0.01)
            result = "DRAW" if abs(signed) < neutral_threshold else "WIN" if signed > 0 else "LOSS"
            self.repository.set_result(
                int(row["id"]), exit_price, result, result_source="INFERRED",
            )

    def merge_live_candle(self, candle: Candle) -> AnalysisSnapshot | None:
        if not self.snapshot:
            return None
        snapshot = self.snapshot
        current_key = (self.settings.market, self.symbol(), self.settings.timeframe)
        snapshot_key = (snapshot.market, snapshot.symbol, snapshot.timeframe)
        if current_key != snapshot_key:
            return None
        history_candles = self._merge_history_candle(
            snapshot.history_candles or snapshot.candles, candle,
        )
        candles, decision_candles, next_candle_entry = self._live_analysis_windows(
            history_candles, snapshot.timeframe,
        )
        frame = candles_frame(decision_candles)
        indicators = calculate_all(frame)
        last_atr = self._value(indicators["atr_14"].iloc[-1])
        structure = analyze_structure(indicators, last_atr)
        chart_indicators, chart_structure = self._chart_context(
            candles, decision_candles, indicators, structure,
        )
        fibonacci = automatic_fibonacci(indicators)
        features = build_features(frame, snapshot.market, snapshot.symbol)
        blockers: list[str] = []
        warnings: list[str] = []
        news_context, news = summarize_asset_news(
            snapshot.news, snapshot.symbol, snapshot.market,
        )
        higher_timeframe = self._higher_timeframe_context(
            self.provider(), snapshot.market, snapshot.symbol, snapshot.timeframe,
        )
        recent_limit = datetime.now(timezone.utc) - timedelta(minutes=60)
        risky = [item for item in news if item.high_risk and item.published_at >= recent_limit]
        if risky:
            message = f"Notícia de alto risco: {risky[0].title[:90]}"
            (blockers if self.settings.strict_risk_blocks else warnings).append(message)
        if snapshot.market == Market.FOREX.value and snapshot.calendar_events:
            event = self.calendar_provider.blocking_event(
                snapshot.calendar_events, datetime.now(timezone.utc), self.settings.high_impact_block_minutes,
                tuple(snapshot.symbol.split("/")),
            )
            if event:
                message = f"Evento de alto impacto: {event.event} ({event.currency})"
                (blockers if self.settings.strict_risk_blocks else warnings).append(message)
        signal = self.signal_engine.generate(
            indicators, features, structure, fibonacci, self.settings.horizon_minutes,
            self.settings.sensitivity, decision_candles[-1].closed,
            blockers, self.settings.mode,
            self.model_context(), payout_percent=self.settings.payout_percent,
            source_lag_seconds=self._source_lag_seconds(
                decision_candles, snapshot.timeframe,
            ),
        )
        signal.next_candle_entry = next_candle_entry
        signal.warnings.extend(warnings)
        signal = self._apply_news_context(
            signal, news_context, strict=self.settings.strict_risk_blocks,
        )
        signal = self._apply_higher_timeframe_context(signal, higher_timeframe)
        signal = self._apply_quality_gate(
            signal, snapshot.market, snapshot.symbol, snapshot.timeframe, self.settings.horizon_minutes,
        )
        signal = self._apply_platform_alignment(
            signal, snapshot.market, snapshot.symbol, float(indicators["close"].iloc[-1]),
        )
        signal.calibrated_rate, signal.calibrated_samples = self.repository.calibration(
            signal.score, snapshot.market, snapshot.symbol, snapshot.timeframe,
            self.settings.horizon_minutes, self.settings.mode,
            sensitivity=self.settings.sensitivity, strategy=strategy_key(snapshot.market),
            result_source="MANUAL",
        )
        self.snapshot = AnalysisSnapshot(
            candles=candles, indicators=indicators, chart_indicators=chart_indicators,
            features=features, structure=structure, chart_structure=chart_structure,
            fibonacci=fibonacci, signal=signal, news=news,
            news_context=news_context, calendar_events=snapshot.calendar_events,
            symbol=snapshot.symbol, timeframe=snapshot.timeframe, market=snapshot.market,
            generated_at=datetime.now(timezone.utc), data_source=snapshot.data_source,
            forex_reference_rate=snapshot.forex_reference_rate,
            history_candles=history_candles,
            higher_timeframe=higher_timeframe,
        )
        self._snapshot_cache[snapshot_key] = (time.monotonic(), self.snapshot)
        self._settle_pending(snapshot.symbol, snapshot.timeframe,
                             float(indicators["close"].iloc[-1]), candles)
        signal_id = self._record_signal(signal, snapshot.market, snapshot.symbol, snapshot.timeframe,
                                        decision_candles, indicators, self.settings.mode)
        self.snapshot.chart_evaluations = self.repository.chart_evaluations(
            snapshot.symbol, snapshot.timeframe,
            started_at=self._evaluation_started_at(),
        )
        self._record_decision(self.snapshot, signal_id=signal_id)
        return self.snapshot

    def _apply_platform_alignment(self, signal: Signal, market: str, symbol: str,
                                  reference_price: float | None) -> Signal:
        if not self.settings.platform_sync_enabled:
            return signal
        snapshot = self.platform_snapshot
        reasons = (
            compare_platform_market(snapshot, market, symbol, reference_price)
            if self.settings.platform_block_mismatch else []
        )
        if (not reasons and signal.direction != Direction.WAIT and snapshot
                and snapshot.fresh() and snapshot.expires_at is not None
                and (not snapshot.asset or snapshot.asset == symbol)):
            current = datetime.now(timezone.utc)
            remaining = (snapshot.expires_at - current).total_seconds()
            minimum = 8.0 if signal.horizon_minutes <= 1 else 12.0
            remaining, projected = effective_platform_entry_remaining_seconds(
                remaining, signal, timeframe=self.settings.timeframe,
                horizon_minutes=signal.horizon_minutes,
                sensitivity=self.settings.sensitivity, mode=self.settings.mode,
                platform_horizon_minutes=snapshot.horizon_minutes, now=current,
            )
            if projected:
                platform_name = getattr(
                    snapshot, "platform_name", self.settings.platform_name,
                )
                warning = (
                    f"Contador da {platform_name} ainda estava no ciclo anterior; "
                    "sinal destinado à próxima vela. Confirme o reinício visível antes de entrar"
                )
                if warning not in signal.warnings:
                    signal.warnings.append(warning)
                timing_note = (
                    f"Sinal confirmado para a próxima vela da {platform_name}; "
                    "entre somente após o contador reiniciar."
                )
                signal.validation_note = (
                    f"{timing_note} {signal.validation_note}".strip()
                )
            if remaining <= minimum:
                platform_name = getattr(snapshot, "platform_name", self.settings.platform_name)
                if remaining <= 0:
                    reasons.append(
                        f"Vencimento da {platform_name} acabou de fechar; aguarde a próxima vela"
                    )
                else:
                    reasons.append(
                        f"Vencimento da {platform_name} em {max(0, round(remaining))}s; "
                        "entrada tardia tem risco de reversão"
                    )
        if not reasons:
            return signal
        signal.direction = Direction.WAIT
        signal.state = SignalState.WAITING
        signal.entry = None
        signal.technical_stop = None
        signal.technical_target = None
        signal.technical_room_ratio = None
        signal.technical_levels_note = ""
        signal.waiting_reasons = (reasons + signal.waiting_reasons)[:4]
        platform = getattr(snapshot, "platform_name", self.settings.platform_name)
        if any("Vencimento" in reason for reason in reasons):
            signal.validation_note = (
                f"Aguarde um novo ciclo completo da {platform} antes de entrar."
            )
        else:
            signal.validation_note = (
                f"Análise pausada até a {platform} e a fonte pública estarem alinhadas."
            )
        return signal

    def train(self) -> TrainingReport:
        if (not self._snapshot_matches_settings() or self.snapshot is None
                or len(self._history_candles()) < TRAINING_MINIMUM_CANDLES):
            self.analyze(limit=2000)
        assert self.snapshot is not None
        history = self._history_candles()
        history_frame = candles_frame(history)
        history_indicators = calculate_all(history_frame)
        threshold = self._label_threshold(history_indicators)
        labels = self._labels_for_horizon(
            threshold, candles=history, indicators=history_indicators,
        )
        features = build_features(
            history_frame, self.snapshot.market, self.snapshot.symbol,
        )
        report = self.model_manager.train(features, labels, self.model_context())
        self.logger.info("IA treinada | modelo=%s versão=%s amostras=%s", report.selected_model, report.version, report.samples)
        return report

    def backtest(self) -> BacktestResult:
        if (not self._snapshot_matches_settings() or self.snapshot is None
                or len(self._history_candles()) < TRAINING_MINIMUM_CANDLES):
            self.analyze(limit=2000)
        assert self.snapshot is not None
        history = self._history_candles()
        history_frame = candles_frame(history)
        history_indicators = calculate_all(history_frame)
        threshold = self._label_threshold(history_indicators)
        labels = self._labels_for_horizon(
            threshold, candles=history, indicators=history_indicators,
        )
        sensitivity = self.settings.sensitivity.upper()
        profile = sensitivity_profile(sensitivity)
        break_even = 1 / (1 + self.settings.payout_percent / 100)
        confidence = max(profile.probability_floor, break_even + profile.payout_margin)
        probability_edge = profile.probability_edge
        compatible_model = self.model_manager.is_compatible(self.model_context())
        model_name = self.model_manager.report.selected_model if compatible_model and self.model_manager.report else "Logistic Regression"
        features = build_features(
            history_frame, self.snapshot.market, self.snapshot.symbol,
        )
        result = self.backtest_engine.run(
            features, labels, model_name, confidence, probability_edge,
            purge_size_from_context(self.model_context()), sensitivity,
            self.settings.payout_percent,
            self.settings.stake_amount,
        )
        gate_key = self._quality_gate_key(
            self.snapshot.market, self.snapshot.symbol, self.snapshot.timeframe,
            self.settings.horizon_minutes,
        )
        self._quality_gate[gate_key] = result
        self.logger.info("Backtest concluído | operações=%s acerto=%.3f cobertura=%.3f", result.operations, result.accuracy, result.coverage)
        return result

    def _snapshot_matches_settings(self) -> bool:
        return bool(
            self.snapshot
            and self.snapshot.market == self.settings.market
            and self.snapshot.symbol == self.symbol()
            and self.snapshot.timeframe == self.settings.timeframe
            and self.snapshot.signal.horizon_minutes == self.settings.horizon_minutes
        )

    def _history_candles(self) -> list[Candle]:
        if self.snapshot is None:
            return []
        return self.snapshot.history_candles or self.snapshot.candles

    def _label_threshold(self, indicators: pd.DataFrame | None = None) -> float:
        assert self.snapshot is not None
        values = indicators if indicators is not None else self.snapshot.indicators
        median_atr = float(values["atr_14"].median())
        median_price = float(values["close"].median())
        floor = 0.00008 if self.settings.market == Market.CRYPTO.value else 0.000015
        factor = 0.12 if self.settings.horizon_minutes <= 3 else 0.18
        return max((median_atr / median_price) * factor, floor)

    def _apply_quality_gate(self, signal: Signal, market: str, symbol: str, timeframe: str,
                            horizon_minutes: int) -> Signal:
        result = self._quality_gate.get(
            self._quality_gate_key(market, symbol, timeframe, horizon_minutes),
        )
        # Compatibilidade somente em memória com chaves criadas pela versão 0.9.0.
        result = result or self._quality_gate.get((market, symbol, timeframe, horizon_minutes))
        if not result:
            return signal
        if result.quality in {"AMOSTRA EM FORMAÇÃO", "AMOSTRA INSUFICIENT", "AMOSTRA INSUFICIENTE"}:
            signal.validation_note = (
                f"Backtest em formação: {result.directional_operations}/20 operações "
                f"({result.accuracy * 100:.1f}% parcial). Não bloqueia entradas."
            )
            return signal
        if result.quality == "FRACA":
            minimum = getattr(result, "break_even_rate", 1 / (1 + self.settings.payout_percent / 100))
            reason = (
                f"Backtest fora da amostra abaixo do equilíbrio: {result.accuracy * 100:.1f}% de acerto "
                f"em {result.directional_operations} operações; payout exige {minimum * 100:.1f}%"
            )
            if reason not in signal.warnings:
                signal.warnings.append(reason)
        else:
            signal.validation_note = (
                f"Backtest: {result.accuracy * 100:.1f}% em "
                f"{result.directional_operations} operações fora da amostra."
            )
        return signal

    def _quality_gate_key(self, market: str, symbol: str, timeframe: str,
                          horizon_minutes: int) -> tuple:
        return (
            market, symbol, timeframe, horizon_minutes, strategy_key(market),
            self.settings.sensitivity, self.settings.mode, FEATURE_SCHEMA_VERSION,
        )

    def refresh_news(self, force: bool = False) -> AnalysisSnapshot | None:
        if force:
            self.news_provider.clear_cache()
        query = market_news_query(self.symbol(), self.settings.market)
        raw_items = self.news_provider.fetch(query, limit=12)
        context, items = summarize_asset_news(
            raw_items, self.symbol(), self.settings.market,
        )
        if self.snapshot and self._snapshot_matches_settings():
            self.snapshot.news = items
            self.snapshot.news_context = context
            self._snapshot_cache[(self.settings.market, self.symbol(), self.settings.timeframe)] = (
                time.monotonic(), self.snapshot,
            )
        return self.snapshot

    def _labels_for_horizon(self, threshold: float, *,
                            candles: list[Candle] | None = None,
                            indicators: pd.DataFrame | None = None) -> pd.Series:
        assert self.snapshot is not None
        history = candles or self._history_candles()
        values = indicators if indicators is not None else self.snapshot.indicators
        timeframe_minutes = {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240}[self.settings.timeframe]
        if self.settings.horizon_minutes < timeframe_minutes:
            required = min(5000, len(history) * timeframe_minutes + self.settings.horizon_minutes + 10)
            base_candles = self.provider().fetch_candles(self.symbol(), "1m", required)
            base_close = candles_frame(base_candles)["close"]
            return build_time_labels(values.index, base_close, self.settings.horizon_minutes, threshold)
        horizon_candles = max(1, round(self.settings.horizon_minutes / timeframe_minutes))
        return build_labels(values["close"], horizon_candles, threshold)

    def radar(self) -> list[RadarItem]:
        symbols = self.symbols()
        if self.settings.market == Market.FOREX.value:
            # O plano gratuito da Twelve Data não permite consultar 28 pares de
            # uma vez. Cada clique analisa um lote diferente sem estourar a cota.
            batch_size = min(6, len(symbols))
            start = self._radar_offset % len(symbols)
            doubled = symbols + symbols
            selected = doubled[start:start + batch_size]
            self._radar_offset = (start + batch_size) % len(symbols)
            self.last_radar_note = (
                f"Forex gratuito: {len(selected)} de {len(symbols)} pares analisados neste lote. "
                "Clique novamente para o próximo lote."
            )
        else:
            selected = [symbol for symbol in PLATFORM_CRYPTO_DEFAULTS if symbol in symbols]
            self.last_radar_note = (
                f"{len(selected)} criptomoedas aceitas pela sua plataforma analisadas."
            )
        items = self.radar_engine.analyze(self.provider(), selected, self.settings.timeframe)
        self.logger.info("Radar concluído | ativos=%s", len(items))
        return items

    def cleanup_cache(self) -> dict[str, list[str]]:
        """Remove somente dados regeneráveis e preserva chaves, preferências e histórico."""
        data_root = app_data_dir().resolve()
        candidates = [
            data_root / "models", data_root / "cache", data_root / "temp",
            data_root / "old_versions", data_root / "updates",
        ]
        removed: list[str] = []
        failures: list[str] = []
        for candidate in candidates:
            resolved = candidate.resolve()
            if data_root not in resolved.parents:
                failures.append(candidate.name)
                continue
            if not resolved.exists():
                continue
            try:
                shutil.rmtree(resolved)
                removed.append(candidate.name)
            except OSError as exc:
                failures.append(f"{candidate.name}: {exc}")
        self._snapshot_cache.clear()
        self._higher_timeframe_cache.clear()
        self._quality_gate.clear()
        self.snapshot = None
        self._last_saved_signature = None
        self.websocket_online = False
        self.binance = BinanceSpotProvider()
        self.crypto = ResilientCryptoProvider(self.binance)
        self.forex = ResilientForexProvider(
            self.secrets.get("twelve_data_key", ""),
            self.secrets.get("alpha_vantage_key", ""),
        )
        self.news_provider = CompositeNewsProvider()
        self.calendar_provider = ResilientEconomicCalendar(self.secrets.get("finnhub_key", ""))
        self.model_manager = ModelManager()
        self.signal_engine = SignalEngine(self.model_manager)
        self.logger.info("Limpeza segura concluída | removidos=%s falhas=%s", removed, failures)
        return {"removed": removed, "failures": failures}

    def health(self) -> list[HealthStatus]:
        crypto_ok, crypto_latency, crypto_detail = self.binance.test_connection()
        forex_ok, forex_latency, forex_detail = self.forex.test_connection()
        model_ready = self.model_manager.is_compatible(self.model_context())
        news_started = time.perf_counter()
        try:
            items = self.news_provider.fetch(market_news_query(self.symbol(), self.settings.market), 6)
            sources = ", ".join(self.news_provider.last_sources[:3]) or "fontes públicas"
            news_ok = bool(items)
            news_detail = f"{len(items)} NOTÍCIAS • {sources}" if items else "SEM NOTÍCIAS RECENTES"
            news_latency = (time.perf_counter() - news_started) * 1000
        except Exception as exc:
            news_ok, news_detail, news_latency = False, str(exc), None
        database_ok = False
        try:
            with self.repository.connect() as connection:
                database_ok = connection.execute("SELECT 1").fetchone()[0] == 1
        except Exception:
            pass
        last_detail = "SEM CANDLE"
        if self.snapshot and self.snapshot.candles:
            age = max(0.0, (datetime.now(timezone.utc) - self.snapshot.candles[-1].open_time).total_seconds())
            last_detail = f"ÚLTIMO CANDLE HÁ {age:.1f}s"
        return [
            HealthStatus("BINANCE", crypto_ok, crypto_detail, crypto_latency),
            HealthStatus("FOREX", forex_ok, forex_detail, forex_latency),
            HealthStatus("WEBSOCKET", self.websocket_online, last_detail),
            HealthStatus("IA", model_ready, "TREINADA PARA ESTE ATIVO" if model_ready else "RETREINAR PARA ESTE ATIVO/CONTEXTO"),
            HealthStatus("NEWS", news_ok, news_detail, news_latency),
            HealthStatus("DATABASE", database_ok, "ONLINE" if database_ok else "ERRO"),
            HealthStatus("ÁUDIO", os.name == "nt" and shutil.which("powershell") is not None, "DISPONÍVEL" if os.name == "nt" else "SOMENTE WINDOWS"),
        ]

    @property
    def logs_path(self) -> Path:
        return app_data_dir() / "logs" / "app.log"

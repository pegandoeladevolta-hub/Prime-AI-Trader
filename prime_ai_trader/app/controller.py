from __future__ import annotations

import logging
import math
import os
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from ..backtest.engine import BacktestEngine, BacktestResult
from ..config.settings import AppSettings, SecretStore, SettingsStore, app_data_dir
from ..core.models import CRYPTO_DEFAULTS, FOREX_DEFAULTS, Candle, Direction, HealthStatus, Market, Signal, SignalState
from ..crypto.binance import BinanceSpotProvider
from ..database.repository import Repository
from ..economic_calendar.finnhub import EconomicEvent, FinnhubEconomicCalendar
from ..features.builder import FEATURE_SCHEMA_VERSION, build_features, build_labels, build_time_labels
from ..fibonacci.auto import FibonacciResult, automatic_fibonacci
from ..forex.twelve_data import TwelveDataProvider
from ..indicators.technical import calculate_all, candles_frame
from ..ml.models import ModelManager, TrainingReport
from ..news.provider import GdeltNewsProvider, NewsItem
from ..priceaction.structure import MarketStructure, analyze_structure
from ..radar.engine import RadarEngine, RadarItem
from ..signals.engine import SignalEngine, THRESHOLDS


@dataclass(slots=True)
class AnalysisSnapshot:
    candles: list[Candle]
    indicators: pd.DataFrame
    features: pd.DataFrame
    structure: MarketStructure
    fibonacci: FibonacciResult | None
    signal: Signal
    news: list[NewsItem]
    calendar_events: list[EconomicEvent]
    symbol: str
    timeframe: str
    market: str
    generated_at: datetime


class TradingController:
    def __init__(self) -> None:
        self.logger = logging.getLogger("prime_ai_trader.controller")
        self.settings_store = SettingsStore()
        self.secret_store = SecretStore()
        self.settings = self.settings_store.load()
        self.secrets = self.secret_store.load()
        self.binance = BinanceSpotProvider()
        self.forex = TwelveDataProvider(self.secrets.get("twelve_data_key", ""))
        self.model_manager = ModelManager()
        self.signal_engine = SignalEngine(self.model_manager)
        self.backtest_engine = BacktestEngine()
        self.radar_engine = RadarEngine()
        self.repository = Repository()
        self.news_provider = GdeltNewsProvider()
        self.calendar_provider = FinnhubEconomicCalendar(self.secrets.get("finnhub_key", ""))
        self.snapshot: AnalysisSnapshot | None = None
        self._snapshot_cache: dict[tuple[str, str, str], tuple[float, AnalysisSnapshot]] = {}
        self._quality_gate: dict[tuple[str, str, str, int], BacktestResult] = {}
        self._last_saved_signature: tuple | None = None
        self.websocket_online = False

    def save_settings(self) -> None:
        self.settings_store.save(self.settings)

    def save_secrets(self, values: dict[str, str]) -> None:
        self.secrets.update(values)
        self.secret_store.save(self.secrets)
        self.forex = TwelveDataProvider(self.secrets.get("twelve_data_key", ""))
        self.calendar_provider = FinnhubEconomicCalendar(self.secrets.get("finnhub_key", ""))
        self.logger.info("Chaves de API atualizadas com armazenamento protegido")

    def provider(self):
        return self.binance if self.settings.market == Market.CRYPTO.value else self.forex

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
        }

    def cached_snapshot(self, max_age_seconds: float = 120.0) -> AnalysisSnapshot | None:
        key = (self.settings.market, self.symbol(), self.settings.timeframe)
        cached = self._snapshot_cache.get(key)
        if not cached or time.monotonic() - cached[0] > max_age_seconds:
            return None
        return cached[1]

    def refresh_symbols(self) -> list[str]:
        symbols = self.provider().list_symbols()
        return symbols or self.symbols()

    @staticmethod
    def _value(value: float) -> float | None:
        return None if value is None or not math.isfinite(float(value)) else float(value)

    def analyze(self, limit: int = 500) -> AnalysisSnapshot:
        market = self.settings.market
        timeframe = self.settings.timeframe
        horizon_minutes = self.settings.horizon_minutes
        sensitivity = self.settings.sensitivity
        mode = self.settings.mode
        high_impact_block_minutes = self.settings.high_impact_block_minutes
        strict_risk_blocks = self.settings.strict_risk_blocks
        symbol = self.settings.crypto_symbol if market == Market.CRYPTO.value else self.settings.forex_symbol
        provider = self.binance if market == Market.CRYPTO.value else self.forex
        context = {"market": market, "symbol": symbol, "timeframe": timeframe, "horizon_minutes": horizon_minutes}
        self.logger.info("Iniciando análise | mercado=%s símbolo=%s timeframe=%s", market, symbol, timeframe)
        candles = provider.fetch_candles(symbol, timeframe, limit=limit)
        if len(candles) < 80:
            raise ValueError("A API retornou poucos candles. São necessários pelo menos 80.")
        frame = candles_frame(candles)
        indicators = calculate_all(frame)
        last_atr = self._value(indicators["atr_14"].iloc[-1])
        structure = analyze_structure(indicators, last_atr)
        fibonacci = automatic_fibonacci(indicators)
        features = build_features(frame)
        news: list[NewsItem] = []
        calendar_events: list[EconomicEvent] = []
        blockers: list[str] = []
        warnings: list[str] = []
        try:
            query = symbol.split("/")[0] if market == Market.CRYPTO.value else " OR ".join(symbol.split("/"))
            news = self.news_provider.fetch(query, limit=12)
            recent_limit = datetime.now(timezone.utc) - timedelta(minutes=60)
            risky = [item for item in news if item.high_risk and item.published_at >= recent_limit]
            if risky:
                message = f"Notícia de alto risco: {risky[0].title[:90]}"
                (blockers if strict_risk_blocks else warnings).append(message)
        except Exception as exc:
            self.logger.warning("Notícias indisponíveis: %s", exc)
        if market == Market.FOREX.value and self.secrets.get("finnhub_key"):
            try:
                today = datetime.now(timezone.utc).date()
                calendar_events = self.calendar_provider.fetch(today, today + timedelta(days=1))
                event = self.calendar_provider.blocking_event(
                    calendar_events, datetime.now(timezone.utc), high_impact_block_minutes,
                    tuple(symbol.split("/")),
                )
                if event:
                    message = f"Evento de alto impacto: {event.event} ({event.currency})"
                    (blockers if strict_risk_blocks else warnings).append(message)
            except Exception as exc:
                self.logger.warning("Calendário econômico indisponível: %s", exc)
        signal = self.signal_engine.generate(
            indicators, features, structure, fibonacci, horizon_minutes,
            sensitivity, candles[-1].closed, blockers, mode, context,
        )
        signal.warnings.extend(warnings)
        signal = self._apply_quality_gate(signal, market, symbol, timeframe, horizon_minutes)
        calibrated, samples = self.repository.calibration(signal.score)
        signal.calibrated_rate, signal.calibrated_samples = calibrated, samples
        snapshot = AnalysisSnapshot(candles, indicators, features, structure, fibonacci, signal, news, calendar_events,
                                    symbol, timeframe, market, datetime.now(timezone.utc))
        self.snapshot = snapshot
        self._snapshot_cache[(market, symbol, timeframe)] = (time.monotonic(), snapshot)
        if signal.state == SignalState.CONFIRMED and signal.direction != Direction.WAIT:
            signature = (symbol, timeframe, candles[-1].open_time, signal.direction.value)
            if signature != self._last_saved_signature:
                last = indicators.iloc[-1]
                values = {key: self._value(last.get(key)) for key in (
                    "rsi_14", "macd", "macd_signal", "adx_14", "plus_di", "minus_di", "atr_14",
                    "vwap", "obv", "cci_20", "williams_r", "volume_relative",
                )}
                self.repository.save_signal(signal, market, symbol, timeframe, values, mode)
                self._last_saved_signature = signature
                self.logger.info("Sinal salvo | %s %s score=%s", symbol, signal.direction.value, signal.score)
        self._settle_pending(symbol, timeframe, float(indicators["close"].iloc[-1]))
        return snapshot

    def _settle_pending(self, symbol: str, timeframe: str, current_price: float) -> None:
        now = datetime.now(timezone.utc)
        for row in self.repository.pending(symbol, timeframe):
            created = datetime.fromisoformat(row["created_at"])
            if now < created + timedelta(minutes=int(row["horizon_minutes"])):
                continue
            entry = float(row["entry"])
            move = (current_price - entry) / entry if entry else 0
            signed = move if row["direction"] == "COMPRA" else -move
            result = "DRAW" if abs(signed) < 0.0002 else "WIN" if signed > 0 else "LOSS"
            self.repository.set_result(int(row["id"]), current_price, result)

    def merge_live_candle(self, candle: Candle) -> AnalysisSnapshot | None:
        if not self.snapshot:
            return None
        snapshot = self.snapshot
        current_key = (self.settings.market, self.symbol(), self.settings.timeframe)
        snapshot_key = (snapshot.market, snapshot.symbol, snapshot.timeframe)
        if current_key != snapshot_key:
            return None
        candles = snapshot.candles.copy()
        if candles and candles[-1].open_time == candle.open_time:
            candles[-1] = candle
        else:
            candles.append(candle)
            candles = candles[-500:]
        frame = candles_frame(candles)
        indicators = calculate_all(frame)
        last_atr = self._value(indicators["atr_14"].iloc[-1])
        structure = analyze_structure(indicators, last_atr)
        fibonacci = automatic_fibonacci(indicators)
        feature_frame = frame.iloc[-180:] if len(frame) > 180 else frame
        features = build_features(feature_frame)
        blockers = list(snapshot.signal.blockers)
        warnings = list(snapshot.signal.warnings)
        signal = self.signal_engine.generate(indicators, features, structure, fibonacci,
            self.settings.horizon_minutes, self.settings.sensitivity, candle.closed, blockers, self.settings.mode, self.model_context())
        signal.warnings.extend(warnings)
        signal = self._apply_quality_gate(
            signal, snapshot.market, snapshot.symbol, snapshot.timeframe, self.settings.horizon_minutes,
        )
        signal.calibrated_rate, signal.calibrated_samples = self.repository.calibration(signal.score)
        self.snapshot = AnalysisSnapshot(candles, indicators, features, structure, fibonacci, signal,
            snapshot.news, snapshot.calendar_events, snapshot.symbol, snapshot.timeframe, snapshot.market, datetime.now(timezone.utc))
        self._snapshot_cache[snapshot_key] = (time.monotonic(), self.snapshot)
        return self.snapshot

    def train(self) -> TrainingReport:
        if self.snapshot is None or len(self.snapshot.candles) < 130:
            self.analyze(limit=1000)
        assert self.snapshot is not None
        threshold = max(float(self.snapshot.indicators["atr_14"].median() / self.snapshot.indicators["close"].median()) * 0.35, 0.0004)
        labels = self._labels_for_horizon(threshold)
        features = self.snapshot.features
        if len(features) != len(self.snapshot.indicators):
            features = build_features(candles_frame(self.snapshot.candles))
        report = self.model_manager.train(features, labels, self.model_context())
        self.logger.info("IA treinada | modelo=%s versão=%s amostras=%s", report.selected_model, report.version, report.samples)
        return report

    def backtest(self) -> BacktestResult:
        if self.snapshot is None:
            self.analyze(limit=1000)
        assert self.snapshot is not None
        median_atr = float(self.snapshot.indicators["atr_14"].median())
        median_price = float(self.snapshot.indicators["close"].median())
        threshold = max((median_atr / median_price) * 0.35, 0.0004)
        labels = self._labels_for_horizon(threshold)
        confidence = THRESHOLDS.get(self.settings.sensitivity, 68) / 100
        compatible_model = self.model_manager.is_compatible(self.model_context())
        model_name = self.model_manager.report.selected_model if compatible_model and self.model_manager.report else "Logistic Regression"
        features = self.snapshot.features
        if len(features) != len(self.snapshot.indicators):
            features = build_features(candles_frame(self.snapshot.candles))
        result = self.backtest_engine.run(features, labels, model_name, confidence)
        gate_key = (self.snapshot.market, self.snapshot.symbol, self.snapshot.timeframe, self.settings.horizon_minutes)
        self._quality_gate[gate_key] = result
        self.logger.info("Backtest concluído | operações=%s acerto=%.3f cobertura=%.3f", result.operations, result.accuracy, result.coverage)
        return result

    def _apply_quality_gate(self, signal: Signal, market: str, symbol: str, timeframe: str,
                            horizon_minutes: int) -> Signal:
        result = self._quality_gate.get((market, symbol, timeframe, horizon_minutes))
        if not result or result.quality not in {"FRACA", "AMOSTRA INSUFICIENT"}:
            return signal
        reason = (
            f"Backtest fora da amostra {result.quality.lower()}: "
            f"{result.accuracy * 100:.1f}% de acerto direcional em {result.directional_operations} operações"
        )
        if reason not in signal.warnings:
            signal.warnings.append(reason)
        return signal

    def _labels_for_horizon(self, threshold: float) -> pd.Series:
        assert self.snapshot is not None
        timeframe_minutes = {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240}[self.settings.timeframe]
        if self.settings.horizon_minutes < timeframe_minutes:
            required = min(5000, len(self.snapshot.candles) * timeframe_minutes + self.settings.horizon_minutes + 10)
            base_candles = self.provider().fetch_candles(self.symbol(), "1m", required)
            base_close = candles_frame(base_candles)["close"]
            return build_time_labels(self.snapshot.indicators.index, base_close, self.settings.horizon_minutes, threshold)
        horizon_candles = max(1, round(self.settings.horizon_minutes / timeframe_minutes))
        return build_labels(self.snapshot.indicators["close"], horizon_candles, threshold)

    def radar(self) -> list[RadarItem]:
        items = self.radar_engine.analyze(self.provider(), self.symbols(), self.settings.timeframe)
        self.logger.info("Radar concluído | ativos=%s", len(items))
        return items

    def health(self) -> list[HealthStatus]:
        crypto_ok, crypto_latency, crypto_detail = self.binance.test_connection()
        forex_ok, forex_latency, forex_detail = self.forex.test_connection()
        model_ready = self.model_manager.is_compatible(self.model_context())
        news_started = time.perf_counter()
        try:
            self.news_provider.fetch("bitcoin", 1)
            news_ok, news_detail, news_latency = True, "ONLINE", (time.perf_counter() - news_started) * 1000
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

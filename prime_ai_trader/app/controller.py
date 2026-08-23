from __future__ import annotations

import json
import logging
import math
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
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
from ..news.provider import CompositeNewsProvider, NewsItem, market_news_query
from ..platform.vex import VexPlatformSnapshot, compare_platform_market
from ..priceaction.structure import MarketStructure, analyze_structure
from ..radar.engine import RadarEngine, RadarItem
from ..signals.engine import SignalEngine, sensitivity_profile
from ..strategies.context import strategy_key


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
    data_source: str = ""
    forex_reference_rate: float | None = None


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
        self._quality_gate: dict[tuple, BacktestResult] = {}
        self._last_saved_signature: tuple | None = None
        self._radar_offset = 0
        self.last_radar_note = ""
        self.websocket_online = False
        self.platform_snapshot: VexPlatformSnapshot | None = None

    def save_settings(self) -> None:
        self.settings_store.save(self.settings)

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
        candles = provider.fetch_candles(symbol, timeframe, limit=limit)
        if len(candles) < 80:
            raise ValueError("A API retornou poucos candles. São necessários pelo menos 80.")
        frame = candles_frame(candles)
        indicators = calculate_all(frame)
        last_atr = self._value(indicators["atr_14"].iloc[-1])
        structure = analyze_structure(indicators, last_atr)
        fibonacci = automatic_fibonacci(indicators)
        features = build_features(frame, market, symbol)
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
                    news = news_job.result()
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
                news = self.news_provider.fetch(query, limit=12)
            except Exception as exc:
                self.logger.warning("Notícias indisponíveis: %s", exc)

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
        if market == Market.CRYPTO.value and provider.last_warning:
            warnings.append(provider.last_warning)
        signal = self.signal_engine.generate(
            indicators, features, structure, fibonacci, horizon_minutes,
            sensitivity, candles[-1].closed, blockers, mode, context,
            payout_percent=payout_percent,
            source_lag_seconds=self._source_lag_seconds(candles, timeframe),
        )
        signal.warnings.extend(warnings)
        signal = self._apply_quality_gate(signal, market, symbol, timeframe, horizon_minutes)
        signal = self._apply_platform_alignment(signal, market, symbol, float(indicators["close"].iloc[-1]))
        calibrated, samples = self.repository.calibration(
            signal.score, market, symbol, timeframe, horizon_minutes, mode,
            sensitivity=sensitivity, strategy=strategy_key(market), result_source="MANUAL",
        )
        signal.calibrated_rate, signal.calibrated_samples = calibrated, samples
        snapshot = AnalysisSnapshot(
            candles, indicators, features, structure, fibonacci, signal, news,
            calendar_events, symbol, timeframe, market, datetime.now(timezone.utc),
            provider.last_provider_name, reference_rate,
        )
        self.snapshot = snapshot
        self._snapshot_cache[(market, symbol, timeframe)] = (time.monotonic(), snapshot)
        self._record_signal(signal, market, symbol, timeframe, candles, indicators, mode)
        self._settle_pending(symbol, timeframe, float(indicators["close"].iloc[-1]), candles)
        return snapshot

    def _record_signal(self, signal: Signal, market: str, symbol: str,
                       timeframe: str, candles: list[Candle],
                       indicators: pd.DataFrame, mode: str) -> None:
        if signal.state != SignalState.CONFIRMED or signal.direction == Direction.WAIT or not candles:
            return
        signature = (symbol, timeframe, candles[-1].open_time, signal.direction.value)
        if signature == self._last_saved_signature:
            return
        last = indicators.iloc[-1]
        values = {key: self._value(last.get(key)) for key in (
            "rsi_14", "macd", "macd_signal", "adx_14", "plus_di", "minus_di",
            "atr_14", "vwap", "obv", "cci_20", "williams_r", "volume_relative",
        )}
        self.repository.save_signal(
            signal, market, symbol, timeframe, values, mode,
            platform=self.settings.platform_name,
            strategy=strategy_key(market), sensitivity=self.settings.sensitivity,
            stake_amount=self.settings.stake_amount,
        )
        self._last_saved_signature = signature
        self.logger.info("Sinal salvo | %s %s score=%s setup=%s", symbol,
                         signal.direction.value, signal.score, signal.setup_name)

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
        features = build_features(feature_frame, snapshot.market, snapshot.symbol)
        blockers: list[str] = []
        warnings: list[str] = []
        recent_limit = datetime.now(timezone.utc) - timedelta(minutes=60)
        risky = [item for item in snapshot.news if item.high_risk and item.published_at >= recent_limit]
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
            self.settings.sensitivity, candle.closed, blockers, self.settings.mode,
            self.model_context(), payout_percent=self.settings.payout_percent,
            source_lag_seconds=self._source_lag_seconds(candles, snapshot.timeframe),
        )
        signal.warnings.extend(warnings)
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
            candles, indicators, features, structure, fibonacci, signal,
            snapshot.news, snapshot.calendar_events, snapshot.symbol,
            snapshot.timeframe, snapshot.market, datetime.now(timezone.utc),
            snapshot.data_source, snapshot.forex_reference_rate,
        )
        self._snapshot_cache[snapshot_key] = (time.monotonic(), self.snapshot)
        self._record_signal(signal, snapshot.market, snapshot.symbol, snapshot.timeframe,
                            candles, indicators, self.settings.mode)
        self._settle_pending(snapshot.symbol, snapshot.timeframe,
                             float(indicators["close"].iloc[-1]), candles)
        return self.snapshot

    def _apply_platform_alignment(self, signal: Signal, market: str, symbol: str,
                                  reference_price: float | None) -> Signal:
        if not self.settings.platform_sync_enabled or not self.settings.platform_block_mismatch:
            return signal
        reasons = compare_platform_market(self.platform_snapshot, market, symbol, reference_price)
        if not reasons:
            return signal
        signal.direction = Direction.WAIT
        signal.state = SignalState.WAITING
        signal.entry = None
        signal.waiting_reasons = (reasons + signal.waiting_reasons)[:4]
        platform = getattr(self.platform_snapshot, "platform_name", self.settings.platform_name)
        signal.validation_note = f"Análise pausada até a {platform} e a fonte pública estarem alinhadas."
        return signal

    def train(self) -> TrainingReport:
        if not self._snapshot_matches_settings() or self.snapshot is None or len(self.snapshot.candles) < 1600:
            self.analyze(limit=2000)
        assert self.snapshot is not None
        threshold = self._label_threshold()
        labels = self._labels_for_horizon(threshold)
        features = self.snapshot.features
        if len(features) != len(self.snapshot.indicators):
            features = build_features(candles_frame(self.snapshot.candles), self.snapshot.market, self.snapshot.symbol)
        report = self.model_manager.train(features, labels, self.model_context())
        self.logger.info("IA treinada | modelo=%s versão=%s amostras=%s", report.selected_model, report.version, report.samples)
        return report

    def backtest(self) -> BacktestResult:
        if not self._snapshot_matches_settings() or self.snapshot is None or len(self.snapshot.candles) < 1600:
            self.analyze(limit=2000)
        assert self.snapshot is not None
        threshold = self._label_threshold()
        labels = self._labels_for_horizon(threshold)
        sensitivity = self.settings.sensitivity.upper()
        profile = sensitivity_profile(sensitivity)
        break_even = 1 / (1 + self.settings.payout_percent / 100)
        confidence = max(profile.probability_floor, break_even + profile.payout_margin)
        probability_edge = profile.probability_edge
        compatible_model = self.model_manager.is_compatible(self.model_context())
        model_name = self.model_manager.report.selected_model if compatible_model and self.model_manager.report else "Logistic Regression"
        features = self.snapshot.features
        if len(features) != len(self.snapshot.indicators):
            features = build_features(candles_frame(self.snapshot.candles), self.snapshot.market, self.snapshot.symbol)
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

    def _label_threshold(self) -> float:
        assert self.snapshot is not None
        median_atr = float(self.snapshot.indicators["atr_14"].median())
        median_price = float(self.snapshot.indicators["close"].median())
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
        items = self.news_provider.fetch(query, limit=12)
        if self.snapshot and self._snapshot_matches_settings():
            self.snapshot.news = items
            self._snapshot_cache[(self.settings.market, self.symbol(), self.settings.timeframe)] = (
                time.monotonic(), self.snapshot,
            )
        return self.snapshot

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

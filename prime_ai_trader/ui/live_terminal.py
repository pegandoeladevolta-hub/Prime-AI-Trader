from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime

from ..core.models import Direction, SignalState
from ..platform.mt5 import MT5ExecutionError, MT5UnavailableError
from .prime_terminal import EXEC_AUTO
from .prime_terminal_execution import PrimeTraderApp


class PrimeTraderLiveApp(PrimeTraderApp):
    """Atualização ao vivo e execução automática usando o mesmo terminal MT5."""

    def __init__(self, controller) -> None:
        self._last_auto_signature = None
        self._auto_job = None
        super().__init__(controller)
        self._auto_job = self.after(350, self._auto_execution_tick)

    @staticmethod
    def _fast_analysis_interval(timeframe: str, sensitivity: str) -> float:
        """Recalcula sinais com baixa latência sem mudar os critérios da estratégia."""
        base = {
            "1m": 1.25,
            "3m": 1.75,
            "5m": 2.5,
            "15m": 4.0,
            "30m": 5.5,
            "1h": 7.0,
            "4h": 10.0,
        }.get(timeframe, 2.5)
        factor = {
            "RÁPIDO": 0.75,
            "EQUILIBRADO": 1.0,
            "CONSERVADOR": 1.35,
        }.get(str(sensitivity).upper(), 1.0)
        return max(0.9, min(12.0, base * factor))

    def _analysis_ready(self, snapshot, token: int, context: tuple[str, str, str]) -> None:
        current = (self.market_var.get(), self.symbol_var.get(), self.timeframe_var.get())
        if token != self._analysis_token or context != current or not self._analysis_active:
            return
        self.render_snapshot(snapshot)
        interval = self._fast_analysis_interval(
            snapshot.timeframe, self.sensitivity_var.get(),
        )
        self.status_var.set(
            f"MT5 ativo • {snapshot.symbol} • {snapshot.timeframe} • "
            f"{self.sensitivity_var.get()} • {self.mode_var.get()} • "
            f"releitura ~{interval:.1f}s"
        )
        self._start_crypto_stream(token, context)

    def _start_crypto_stream(self, token: int, context: tuple[str, str, str]) -> None:
        """Stream de candles MT5 com reavaliação rápida do motor 1.2.6."""
        symbol = self.controller.symbol()
        timeframe = self.controller.settings.timeframe
        stop_event = self._stop_event

        def on_candle(candle) -> None:
            if stop_event.is_set() or token != self._analysis_token:
                return
            self.controller.websocket_online = True
            self._post_ui(self._queue_live_chart, candle, token)
            now = time.monotonic()
            interval = self._fast_analysis_interval(
                timeframe, self.controller.settings.sensitivity,
            )
            if candle.closed or now - self._last_live_analysis >= interval:
                self._last_live_analysis = now
                self._post_ui(self._process_live, candle, token, context)

        async def run() -> None:
            await self.controller.mt5.stream_candles(
                symbol, timeframe, on_candle, stop_event,
            )

        self._stream_thread = threading.Thread(
            target=lambda: asyncio.run(run()), daemon=True,
            name="prime-mt5-live",
        )
        self._stream_thread.start()

    def _flush_live_chart(self, token: int) -> None:
        self._live_ui_job = None
        if token != self._analysis_token or self._pending_live_candle is None:
            return
        candle = self._pending_live_candle
        self._pending_live_candle = None
        self.chart.update_last_candle(candle)
        self.updated_var.set(f"MT5 • PREÇO AO VIVO {datetime.now().strftime('%H:%M:%S')}")

    def _auto_execution_tick(self) -> None:
        try:
            snapshot = self.controller.snapshot
            enabled = (
                self.execution_profile_var.get() == EXEC_AUTO
                and bool(self.mt5_auto.get())
                and bool(self.mt5_armed.get())
            )
            if enabled and snapshot is not None:
                signal = snapshot.signal
                if signal.state == SignalState.CONFIRMED and signal.direction != Direction.WAIT:
                    candle_key = snapshot.candles[-1].open_time if snapshot.candles else snapshot.generated_at
                    signature = (
                        snapshot.market, snapshot.symbol, snapshot.timeframe,
                        self.sensitivity_var.get(), self.mode_var.get(),
                        candle_key, signal.direction.value,
                    )
                    if signature != self._last_auto_signature:
                        self._last_auto_signature = signature
                        self._execute_confirmed_signal(snapshot)
        finally:
            if self.winfo_exists():
                self._auto_job = self.after(350, self._auto_execution_tick)

    def _execute_confirmed_signal(self, snapshot) -> None:
        try:
            if not self.mt5_connected.get():
                self._connect_mt5()
            if not self.mt5_connected.get():
                raise MT5UnavailableError("MT5 não conectado; sinal não foi executado.")
            signal = snapshot.signal
            volume = float(self.mt5_volume.get().replace(",", "."))
            kwargs = dict(
                symbol=snapshot.symbol,
                volume=volume,
                sl=float(signal.technical_stop or 0.0),
                tp=float(signal.technical_target or 0.0),
                deviation=self.controller.settings.mt5_deviation_points,
                armed=True,
            )
            if signal.direction == Direction.BUY:
                result = self.mt5.buy(**kwargs)
            elif signal.direction == Direction.SELL:
                result = self.mt5.sell(**kwargs)
            else:
                return
            self.status_var.set(
                f"AUTO MT5: {signal.direction.value} executada • "
                f"{result.deal or result.order} • {result.price}"
            )
            self._refresh_positions()
        except (ValueError, MT5ExecutionError, MT5UnavailableError) as exc:
            self.status_var.set(f"AUTO MT5 NÃO EXECUTOU: {exc}")

    def start_analysis(self):
        return super().start_analysis()

    def refresh_analysis(self):
        return super().refresh_analysis()

    def open_performance(self):
        return super().open_performance()

    def open_decision_history(self):
        return super().open_decision_history()

    def pause_analysis(self, silent: bool = False):
        return super().pause_analysis(silent=silent)

    def _close(self) -> None:
        if self._auto_job is not None:
            try:
                self.after_cancel(self._auto_job)
            except Exception:
                pass
            self._auto_job = None
        super()._close()

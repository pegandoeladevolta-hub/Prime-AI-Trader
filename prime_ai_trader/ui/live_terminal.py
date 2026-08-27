from __future__ import annotations

from datetime import datetime

from ..core.models import Direction, SignalState
from ..platform.mt5 import MT5ExecutionError, MT5UnavailableError
from .prime_terminal import EXEC_AUTO, PrimeTraderApp


class PrimeTraderLiveApp(PrimeTraderApp):
    """Atualização ao vivo e execução automática usando o mesmo terminal MT5."""

    def __init__(self, controller) -> None:
        self._last_auto_signature = None
        self._auto_job = None
        super().__init__(controller)
        self._auto_job = self.after(350, self._auto_execution_tick)

    def _analysis_ready(self, snapshot, token: int, context: tuple[str, str, str]) -> None:
        current = (self.market_var.get(), self.symbol_var.get(), self.timeframe_var.get())
        if token != self._analysis_token or context != current or not self._analysis_active:
            return
        self.render_snapshot(snapshot)
        self.status_var.set(
            f"MT5 ativo • {snapshot.symbol} • {snapshot.timeframe} • "
            f"{self.sensitivity_var.get()} • {self.mode_var.get()}"
        )
        # O método legado chama controller.binance.stream_candles; no controlador
        # MT5 essa referência aponta para o próprio MT5Bridge.
        self._start_crypto_stream(token, context)

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

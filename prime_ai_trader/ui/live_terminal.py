from __future__ import annotations

from ..core.models import Direction, SignalState
from ..platform.mt5 import MT5ExecutionError, MT5UnavailableError
from .prime_terminal import PrimeTraderApp


class PrimeTraderLiveApp(PrimeTraderApp):
    """Acrescenta autoexecução opcional sem alterar o motor de sinais 1.2.6."""

    def __init__(self, controller) -> None:
        self._last_auto_signature = None
        self._auto_job = None
        super().__init__(controller)
        self._auto_job = self.after(350, self._auto_execution_tick)

    def _auto_execution_tick(self) -> None:
        try:
            snapshot = self.controller.snapshot
            enabled = bool(self.mt5_auto.get()) and bool(self.mt5_armed.get())
            if enabled and snapshot is not None:
                signal = snapshot.signal
                if signal.state == SignalState.CONFIRMED and signal.direction != Direction.WAIT:
                    candle_key = snapshot.candles[-1].open_time if snapshot.candles else snapshot.generated_at
                    signature = (
                        snapshot.market, snapshot.symbol, snapshot.timeframe,
                        candle_key, signal.direction.value,
                    )
                    if signature != self._last_auto_signature:
                        # Marca antes do envio para impedir ordem duplicada caso a
                        # corretora demore ou a interface atualize a mesma vela.
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
            symbol = self._mt5_symbol(snapshot.symbol)
            volume = float(self.mt5_volume.get().replace(",", "."))
            sl = float(signal.technical_stop or 0.0)
            tp = float(signal.technical_target or 0.0)
            kwargs = dict(
                symbol=symbol,
                volume=volume,
                sl=sl,
                tp=tp,
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

    def _close(self) -> None:
        if self._auto_job is not None:
            try:
                self.after_cancel(self._auto_job)
            except Exception:
                pass
            self._auto_job = None
        super()._close()

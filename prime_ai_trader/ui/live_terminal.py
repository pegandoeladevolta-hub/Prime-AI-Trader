from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import replace
from datetime import datetime

from ..app.mt5_history import initialize_mt5_history_epoch
from ..core.models import Direction, SignalState
from ..platform.mt5 import MT5ExecutionError, MT5UnavailableError
from .prime_terminal import EXEC_AUTO
from .prime_terminal_ai import PrimeTraderApp


class PrimeTraderLiveApp(PrimeTraderApp):
    """Atualização ao vivo e execução automática usando o mesmo terminal MT5.

    O contexto profundo continua sendo analisado pelo motor, mas uma pré-leitura
    intravela só é anunciada depois de permanecer na mesma direção por leituras
    consecutivas. Fechamentos de candle têm prioridade e ordens são geridas por
    Stop Loss / Take Profit, sem contrato de expiração.
    """

    FORMING_STREAK_REQUIRED = 3
    FORMING_MIN_STABLE_SECONDS = 1.6
    AUTO_RETRY_SECONDS = 3.0
    AUTO_MAX_ATTEMPTS = 3

    def __init__(self, controller) -> None:
        self._last_auto_signature = None
        self._auto_job = None
        self._auto_failures: dict[tuple, tuple[int, float]] = {}
        self._forming_candidate = None
        self._forming_streak = 0
        self._forming_first_seen = 0.0
        self._pending_closed_analysis = None
        self._closed_retry_job = None
        # Nova etapa MT5-SLTP: apaga uma única vez históricos incompatíveis.
        # O histórico oficial da conta no MetaTrader não é tocado.
        self._history_reset_result = initialize_mt5_history_epoch(controller.repository)
        super().__init__(controller)
        if self._history_reset_result.reset:
            self.status_var.set(
                "Nova etapa MT5-SLTP iniciada • histórico anterior do Prime Trader foi zerado"
            )
            self._refresh_recent_signals()
        self._auto_job = self.after(350, self._auto_execution_tick)

    def _save_form(self) -> None:
        """Garante que o legado nunca reative uma expiração no runtime MT5."""
        super()._save_form()
        changed = self.controller.settings.horizon_minutes != 0
        self.controller.settings.horizon_minutes = 0
        if hasattr(self, "horizon_var"):
            self.horizon_var.set("0")
        if changed:
            self.controller.save_settings()

    @staticmethod
    def _fast_analysis_interval(timeframe: str, sensitivity: str) -> float:
        """Cadência da pré-leitura; confirmação continua prioritária no fechamento."""
        base = {
            "1m": 1.8,
            "3m": 2.2,
            "5m": 3.0,
            "15m": 4.5,
            "30m": 6.0,
            "1h": 8.0,
            "4h": 11.0,
        }.get(timeframe, 3.0)
        factor = {
            "RÁPIDO": 0.90,
            "EQUILIBRADO": 1.0,
            "CONSERVADOR": 1.25,
        }.get(str(sensitivity).upper(), 1.0)
        return max(1.5, min(14.0, base * factor))

    def _effective_analysis_interval(self, timeframe: str, sensitivity: str) -> float:
        """Evita sobrepor cálculos profundos sem atrasar o fechamento do candle."""
        base = self._fast_analysis_interval(timeframe, sensitivity)
        try:
            depth = int(self.controller.analysis_candles())
        except Exception:
            depth = 500
        depth_floor = {
            500: 1.5,
            1000: 1.7,
            1500: 1.9,
            2000: 2.1,
            3000: 2.6,
        }.get(depth, 2.1)
        return max(base, depth_floor)

    def _reset_forming_stability(self) -> None:
        self._forming_candidate = None
        self._forming_streak = 0
        self._forming_first_seen = 0.0

    def _forming_is_stable(self, signal) -> bool:
        """Exige persistência antes de exibir/locutar COMPRA ou VENDA intravela."""
        if signal.state != SignalState.FORMING or signal.direction == Direction.WAIT:
            self._reset_forming_stability()
            return True
        now = time.monotonic()
        if signal.direction != self._forming_candidate:
            self._forming_candidate = signal.direction
            self._forming_streak = 1
            self._forming_first_seen = now
            return False
        self._forming_streak += 1
        stable_for = now - self._forming_first_seen
        return (
            self._forming_streak >= self.FORMING_STREAK_REQUIRED
            and stable_for >= self.FORMING_MIN_STABLE_SECONDS
        )

    def _stable_display_snapshot(self, snapshot):
        """Filtra somente a apresentação da pré-leitura; não altera o sinal real."""
        signal = snapshot.signal
        if signal.state == SignalState.CONFIRMED:
            self._reset_forming_stability()
            return snapshot
        if signal.state != SignalState.FORMING or signal.direction == Direction.WAIT:
            self._reset_forming_stability()
            return snapshot
        if self._forming_is_stable(signal):
            return snapshot
        display_signal = replace(
            signal,
            direction=Direction.WAIT,
            state=SignalState.WAITING,
            entry=None,
            waiting_reasons=[
                "Pré-leitura intravela ainda oscilando; aguardando direção estabilizar"
            ],
            validation_note=(
                f"Estabilizando pré-sinal: {self._forming_streak}/"
                f"{self.FORMING_STREAK_REQUIRED} leituras na mesma direção"
            ),
        )
        return replace(snapshot, signal=display_signal)

    def render_snapshot(self, snapshot) -> None:
        # O controller.snapshot permanece intacto para histórico/autoexecução.
        super().render_snapshot(self._stable_display_snapshot(snapshot))
        # Ao receber CONFIRMADO, tenta executar no evento; o timer é redundância.
        self._maybe_execute_auto(snapshot)

    def _refresh_recent_signals(self) -> None:
        """O card Últimos sinais mostra somente a nova etapa MetaTrader 5."""
        if self._history_refresh_running:
            return
        self._history_refresh_running = True

        def worker() -> None:
            try:
                rows = self.controller.repository.recent(40)
                mt5_rows = [
                    row for row in rows
                    if str(row.get("platform") or "").upper() == "MT5"
                ][:3]
                self._post_ui(self._recent_signals_ready, mt5_rows)
            except Exception as exc:
                self.controller.logger.debug(
                    "Histórico visual MT5 indisponível: %s", exc,
                )
                self._post_ui(self._recent_signals_ready, [])

        threading.Thread(
            target=worker, daemon=True, name="prime-mt5-signal-history-ui",
        ).start()

    def _analysis_ready(self, snapshot, token: int, context: tuple[str, str, str]) -> None:
        current = (self.market_var.get(), self.symbol_var.get(), self.timeframe_var.get())
        if token != self._analysis_token or context != current or not self._analysis_active:
            return
        self.render_snapshot(snapshot)
        interval = self._effective_analysis_interval(
            snapshot.timeframe, self.sensitivity_var.get(),
        )
        try:
            depth = int(self.controller.analysis_candles())
            management = self.controller.management_mode()
            rr = self.controller.minimum_rr()
        except Exception:
            depth, management, rr = 0, "SL/TP", 1.5
        self.status_var.set(
            f"MT5 ativo • {snapshot.symbol} • {snapshot.timeframe} • "
            f"{self.sensitivity_var.get()} • {self.mode_var.get()} • "
            f"{management} • R:R mín 1:{rr:g} • {depth or '—'} candles"
        )
        self._start_crypto_stream(token, context)

    def _start_crypto_stream(self, token: int, context: tuple[str, str, str]) -> None:
        """Stream MT5: ticks atualizam o gráfico e fechamento recebe prioridade."""
        symbol = self.controller.symbol()
        timeframe = self.controller.settings.timeframe
        stop_event = self._stop_event

        def on_candle(candle) -> None:
            if stop_event.is_set() or token != self._analysis_token:
                return
            self.controller.websocket_online = True
            self._post_ui(self._queue_live_chart, candle, token)
            now = time.monotonic()
            if candle.closed:
                self._last_live_analysis = now
                self._post_ui(self._queue_closed_analysis, candle, token, context)
                return
            if self._pending_closed_analysis is not None:
                return
            interval = self._effective_analysis_interval(
                timeframe, self.controller.settings.sensitivity,
            )
            if now - self._last_live_analysis >= interval:
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

    def _queue_closed_analysis(self, candle, token: int, context: tuple[str, str, str]) -> None:
        """Nunca descarta o fechamento só porque outra análise ainda está rodando."""
        if self._stop_event.is_set() or token != self._analysis_token:
            return
        self._pending_closed_analysis = candle
        if self._closed_retry_job is None:
            self._try_closed_analysis(token, context)

    def _try_closed_analysis(self, token: int, context: tuple[str, str, str]) -> None:
        self._closed_retry_job = None
        if self._stop_event.is_set() or token != self._analysis_token:
            self._pending_closed_analysis = None
            return
        candle = self._pending_closed_analysis
        if candle is None:
            return
        if self._task_running:
            self._closed_retry_job = self.after(
                70, self._try_closed_analysis, token, context,
            )
            return
        self._pending_closed_analysis = None
        super()._process_live(candle, token, context)

    def _flush_live_chart(self, token: int) -> None:
        self._live_ui_job = None
        if token != self._analysis_token or self._pending_live_candle is None:
            return
        candle = self._pending_live_candle
        self._pending_live_candle = None
        self.chart.update_last_candle(candle)
        self.updated_var.set(f"MT5 • PREÇO AO VIVO {datetime.now().strftime('%H:%M:%S')}")

    def _auto_signature_for(self, snapshot):
        candle_key = (
            snapshot.candles[-1].open_time
            if snapshot.candles else snapshot.generated_at
        )
        return (
            snapshot.market,
            snapshot.symbol,
            snapshot.timeframe,
            self.sensitivity_var.get(),
            self.mode_var.get(),
            self.controller.management_mode(),
            int(round(self.controller.minimum_rr() * 100)),
            candle_key,
            snapshot.signal.direction.value,
        )

    def _maybe_execute_auto(self, snapshot) -> None:
        if snapshot is None:
            return
        enabled = (
            self.execution_profile_var.get() == EXEC_AUTO
            and bool(self.mt5_auto.get())
            and bool(self.mt5_armed.get())
        )
        if not enabled:
            return
        signal = snapshot.signal
        if signal.state != SignalState.CONFIRMED or signal.direction == Direction.WAIT:
            return
        if not signal.technical_stop or not signal.technical_target:
            self.status_var.set("AUTO MT5 aguardando plano válido de Stop/Alvo")
            return
        signature = self._auto_signature_for(snapshot)
        if signature == self._last_auto_signature:
            return
        attempts, retry_at = self._auto_failures.get(signature, (0, 0.0))
        now = time.monotonic()
        if attempts >= self.AUTO_MAX_ATTEMPTS or now < retry_at:
            return
        self._last_auto_signature = signature
        success = self._execute_confirmed_signal(snapshot)
        if success:
            self._auto_failures.pop(signature, None)
            return
        attempts += 1
        self._auto_failures[signature] = (attempts, now + self.AUTO_RETRY_SECONDS)
        # Libera a assinatura para uma nova tentativa controlada, nunca em loop de
        # 350 ms. Após três falhas o sinal fica bloqueado até a próxima assinatura.
        self._last_auto_signature = None
        if attempts >= self.AUTO_MAX_ATTEMPTS:
            self.status_var.set(
                "AUTO MT5: 3 tentativas recusadas para este sinal • aguarde o próximo"
            )

    def _auto_execution_tick(self) -> None:
        try:
            self._maybe_execute_auto(self.controller.snapshot)
        finally:
            if self.winfo_exists():
                self._auto_job = self.after(350, self._auto_execution_tick)

    def _execute_confirmed_signal(self, snapshot) -> bool:
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
                return False
            self.status_var.set(
                f"AUTO MT5: {signal.direction.value} executada • "
                f"{result.deal or result.order} • entrada {result.price} • "
                f"SL {signal.technical_stop:g} • TP {signal.technical_target:g}"
            )
            self._refresh_positions()
            return True
        except (ValueError, MT5ExecutionError, MT5UnavailableError) as exc:
            self.status_var.set(f"AUTO MT5 NÃO EXECUTOU: {exc}")
            return False

    def start_analysis(self):
        self._reset_forming_stability()
        self._pending_closed_analysis = None
        self._auto_failures.clear()
        return super().start_analysis()

    def refresh_analysis(self):
        self._reset_forming_stability()
        return super().refresh_analysis()

    def open_performance(self):
        return super().open_performance()

    def open_decision_history(self):
        return super().open_decision_history()

    def pause_analysis(self, silent: bool = False):
        self._reset_forming_stability()
        self._pending_closed_analysis = None
        if self._closed_retry_job is not None:
            try:
                self.after_cancel(self._closed_retry_job)
            except Exception:
                pass
            self._closed_retry_job = None
        return super().pause_analysis(silent=silent)

    def _close(self) -> None:
        if self._auto_job is not None:
            try:
                self.after_cancel(self._auto_job)
            except Exception:
                pass
            self._auto_job = None
        if self._closed_retry_job is not None:
            try:
                self.after_cancel(self._closed_retry_job)
            except Exception:
                pass
            self._closed_retry_job = None
        self._pending_closed_analysis = None
        super()._close()

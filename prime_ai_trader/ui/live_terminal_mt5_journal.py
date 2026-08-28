from __future__ import annotations

from ..database.mt5_journal import MT5TradeJournal
from ..strategies.context import strategy_key
from .live_terminal_fast import PrimeTraderLiveApp as GuardedPrimeTraderLiveApp
from .mt5_journal_dialogs import MT5PerformanceDialog, MT5TradeHistoryDialog


class PrimeTraderLiveApp(GuardedPrimeTraderLiveApp):
    """Runtime final: uma posição por vez + diário financeiro nativo do MT5."""

    JOURNAL_SYNC_MS = 900

    def __init__(self, controller) -> None:
        self.mt5_journal = MT5TradeJournal()
        self._journal_job = None
        super().__init__(controller)
        self._journal_job = self.after(self.JOURNAL_SYNC_MS, self._journal_tick)

    def _journal_context(self) -> dict[str, str]:
        settings = self.controller.settings
        return {
            "timeframe": str(settings.timeframe),
            "strategy": str(strategy_key(settings.market)),
            "sensitivity": str(settings.sensitivity),
            "mode": str(settings.mode),
            "management": str(self.controller.management_mode()),
        }

    def _sync_journal(self) -> None:
        if not self.mt5_connected.get():
            return
        try:
            self.mt5_journal.sync_with_mt5(self.mt5, **self._journal_context())
        except Exception as exc:
            self.controller.logger.debug("Diário MT5 aguardando sincronização: %s", exc)

    def _journal_tick(self) -> None:
        self._journal_job = None
        try:
            self._sync_journal()
        finally:
            if self.winfo_exists():
                self._journal_job = self.after(self.JOURNAL_SYNC_MS, self._journal_tick)

    def _execute_confirmed_signal(self, snapshot) -> bool:
        success = super()._execute_confirmed_signal(snapshot)
        if success:
            try:
                volume = float(self.mt5_volume.get().replace(",", "."))
                context = self._journal_context()
                self.mt5_journal.record_open(
                    snapshot,
                    volume=volume,
                    strategy=context["strategy"],
                    sensitivity=context["sensitivity"],
                    mode=context["mode"],
                    management=context["management"],
                )
                self._sync_journal()
            except Exception as exc:
                # A ordem real já foi aceita. Falha de diário nunca dispara segunda ordem.
                self.controller.logger.exception("Não foi possível registrar a operação no diário MT5: %s", exc)
        return success

    def _currency(self) -> str:
        try:
            return str(self.mt5.account().currency or "USD") if self.mt5_connected.get() else "USD"
        except Exception:
            return "USD"

    def open_performance(self):
        self._sync_journal()
        return MT5PerformanceDialog(
            self,
            self.mt5_journal.statistics(),
            currency=self._currency(),
        )

    def open_decision_history(self):
        self._sync_journal()
        return MT5TradeHistoryDialog(
            self,
            self.mt5_journal,
            self.mt5_journal.recent(2000),
            currency=self._currency(),
        )

    def _close(self) -> None:
        if self._journal_job is not None:
            try:
                self.after_cancel(self._journal_job)
            except Exception:
                pass
            self._journal_job = None
        self._sync_journal()
        super()._close()


__all__ = ["PrimeTraderLiveApp"]

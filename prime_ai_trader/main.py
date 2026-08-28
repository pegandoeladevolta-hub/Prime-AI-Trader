from __future__ import annotations

import sys
import tkinter as tk
from tkinter import messagebox

from .app.clean_start import initialize_clean_mt5_start
from .app.mt5_market_controller import MT5MarketTradingController
from .logging_setup import configure_logging
from .ui.live_terminal_mt5_journal import PrimeTraderLiveApp


def main() -> int:
    # A limpeza precisa acontecer antes de abrir logs, banco, configurações ou IA.
    # Ela roda somente uma vez para esta nova era MT5 e preserva tudo criado depois.
    try:
        clean_start = initialize_clean_mt5_start()
    except Exception as exc:
        try:
            root = tk.Tk(); root.withdraw()
            messagebox.showerror(
                "PRIME TRADER",
                f"Não foi possível preparar a instalação limpa.\n\n{exc}",
            )
            root.destroy()
        except Exception:
            pass
        return 1

    logger = configure_logging()
    if clean_start.reset:
        logger.info(
            "Nova era MT5 iniciada com dados locais limpos | itens removidos=%s | pasta=%s",
            clean_start.removed_entries,
            clean_start.data_dir,
        )
    try:
        controller = MT5MarketTradingController()
        app = PrimeTraderLiveApp(controller)
        app.mainloop()
        return 0
    except Exception as exc:
        logger.exception("Falha fatal na inicialização")
        try:
            root = tk.Tk(); root.withdraw()
            messagebox.showerror(
                "PRIME TRADER",
                f"Não foi possível iniciar o programa.\n\n{exc}\n\nOs detalhes foram salvos no log.",
            )
            root.destroy()
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())

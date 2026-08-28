from __future__ import annotations

import sys
import tkinter as tk
from tkinter import messagebox

from .app.mt5_fast_controller import MT5FastTradingController
from .logging_setup import configure_logging
from .ui.live_terminal_fast import PrimeTraderLiveApp


def main() -> int:
    logger = configure_logging()
    try:
        controller = MT5FastTradingController()
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

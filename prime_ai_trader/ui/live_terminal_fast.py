from __future__ import annotations

from .live_terminal_layout import PrimeTraderLiveApp as LayoutPrimeTraderLiveApp


class PrimeTraderLiveApp(LayoutPrimeTraderLiveApp):
    """Terminal MT5 responsivo usando confirmação rápida controlada pelo controller.

    A promoção FORMING -> CONFIRMED não depende mais da renderização Tkinter. O
    controller devolve o snapshot já confirmado quando a estabilidade, score e
    plano SL/TP forem válidos; esta classe mantém somente a camada visual.
    """

    pass


__all__ = ["PrimeTraderLiveApp"]

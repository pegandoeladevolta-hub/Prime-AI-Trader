from __future__ import annotations

from ..core.models import Direction
from .mt5_fast_controller import MT5FastTradingController


class MT5MarketTradingController(MT5FastTradingController):
    """Identifica oportunidades por tese, não por candle nem preço exato.

    Entrada, Stop e Alvo continuam sendo recalculados a cada leitura. A persistência
    necessária para CONFIRMADO acompanha apenas ativo + timeframe + direção. Isso
    evita que pequenas variações de ATR/SL durante a mesma oportunidade reiniciem
    o contador e prendam o bot eternamente em SINAL EM FORMAÇÃO.
    """

    @staticmethod
    def _opportunity_key(snapshot) -> tuple | None:
        signal = snapshot.signal
        if signal.direction == Direction.WAIT:
            return None
        if not signal.entry or not signal.technical_stop or not signal.technical_target:
            return None
        return (
            snapshot.symbol,
            snapshot.timeframe,
            signal.direction.value,
        )


__all__ = ["MT5MarketTradingController"]

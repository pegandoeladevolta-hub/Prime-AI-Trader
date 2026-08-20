from __future__ import annotations

from dataclasses import dataclass

from ..indicators.technical import calculate_all, candles_frame
from ..market.base import MarketDataProvider, ProviderError
from ..priceaction.structure import analyze_structure


@dataclass(slots=True)
class RadarItem:
    symbol: str
    score: int
    reason: str
    spread_pct: float | None = None


class RadarEngine:
    def analyze(self, provider: MarketDataProvider, symbols: list[str], timeframe: str, limit: int = 180) -> list[RadarItem]:
        results = []
        failures: list[str] = []
        for symbol in symbols:
            try:
                candles = provider.fetch_candles(symbol, timeframe, limit)
                indicators = calculate_all(candles_frame(candles))
                last = indicators.iloc[-1]
                structure = analyze_structure(indicators, float(last["atr_14"]))
                score = 20
                reasons = []
                volume_rel = float(last["volume_relative"]) if last["volume_relative"] == last["volume_relative"] else 0
                adx = float(last["adx_14"]) if last["adx_14"] == last["adx_14"] else 0
                volatility = float(last["atr_14"] / last["close"] * 100)
                score += min(round(volume_rel * 10), 20)
                score += min(round(adx / 2), 20)
                score += min(round(volatility * 6), 20)
                if structure.trend in {"ALTA", "BAIXA"}:
                    score += 12; reasons.append(f"estrutura de {structure.trend.lower()}")
                if structure.breakout:
                    score += 8; reasons.append("rompimento")
                reasons.append(f"ADX {adx:.1f}")
                results.append(RadarItem(symbol, min(score, 100), ", ".join(reasons)))
            except Exception as exc:
                failures.append(f"{symbol}: {exc}")
        if not results:
            detail = failures[0] if failures else "nenhum ativo disponível"
            raise ProviderError(f"Não foi possível analisar os ativos do radar. {detail}")
        return sorted(results, key=lambda item: item.score, reverse=True)

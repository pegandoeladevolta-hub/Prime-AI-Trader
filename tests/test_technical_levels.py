from __future__ import annotations

import unittest

from prime_ai_trader.core.models import Direction, TIMEFRAMES, Zone
from prime_ai_trader.indicators.technical import calculate_all, candles_frame
from prime_ai_trader.priceaction.levels import calculate_technical_levels
from prime_ai_trader.priceaction.structure import MarketStructure, analyze_structure, display_zones
from tests.helpers import synthetic_candles


class TechnicalLevelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.indicators = calculate_all(candles_frame(synthetic_candles(200, seed=42)))
        atr = float(self.indicators["atr_14"].iloc[-1])
        self.structure = analyze_structure(self.indicators, atr)

    def test_buy_and_sell_levels_are_symmetric_around_entry(self) -> None:
        buy = calculate_technical_levels(
            self.indicators, self.structure, Direction.BUY, "1m", 1,
        )
        sell = calculate_technical_levels(
            self.indicators, self.structure, Direction.SELL, "1m", 1,
        )
        self.assertIsNotNone(buy)
        self.assertIsNotNone(sell)
        assert buy is not None and sell is not None
        self.assertLess(buy.invalidation, buy.entry)
        self.assertGreater(buy.target, buy.entry)
        self.assertGreater(sell.invalidation, sell.entry)
        self.assertLess(sell.target, sell.entry)
        self.assertGreater(buy.room_ratio, 0)
        self.assertGreater(sell.room_ratio, 0)

    def test_every_timeframe_gets_finite_technical_levels(self) -> None:
        for timeframe in TIMEFRAMES:
            with self.subTest(timeframe=timeframe):
                levels = calculate_technical_levels(
                    self.indicators, self.structure, Direction.BUY,
                    timeframe, 1,
                )
                self.assertIsNotNone(levels)
                assert levels is not None
                self.assertGreater(levels.target, levels.entry)
                self.assertLess(levels.invalidation, levels.entry)

    def test_display_keeps_only_relevant_supports_and_resistances(self) -> None:
        structure = MarketStructure(
            "LATERAL", [], None, False, False,
            [
                Zone("SUPORTE", 98.8, 99.0, 1, 20),
                Zone("SUPORTE", 97.8, 98.0, 4, 18),
                Zone("SUPORTE", 80.0, 81.0, 9, 10),
            ],
            [
                Zone("RESISTÊNCIA", 101.0, 101.2, 1, 19),
                Zone("RESISTÊNCIA", 102.0, 102.2, 5, 17),
                Zone("RESISTÊNCIA", 120.0, 121.0, 9, 9),
            ],
            [], [],
        )
        selected = display_zones(structure, 100.0, atr_value=1.0, max_each=2)
        supports = [zone for zone in selected if zone.kind == "SUPORTE"]
        resistances = [zone for zone in selected if zone.kind == "RESISTÊNCIA"]
        self.assertLessEqual(len(supports), 2)
        self.assertLessEqual(len(resistances), 2)
        self.assertNotIn(80.5, [zone.midpoint for zone in selected])
        self.assertNotIn(120.5, [zone.midpoint for zone in selected])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import math
import tkinter as tk
from collections.abc import Callable

import pandas as pd

from ..core.models import Candle, Direction, Signal, Zone
from ..fibonacci.auto import FibonacciResult
from ..priceaction.structure import MarketStructure
from .theme import COLORS


class CandleChart(tk.Canvas):
    def __init__(self, master, on_ohlc: Callable[[str], None] | None = None, **kwargs) -> None:
        super().__init__(master, bg=COLORS["card_alt"], highlightthickness=0, **kwargs)
        self.candles: list[Candle] = []
        self.indicators = pd.DataFrame()
        self.zones: list[Zone] = []
        self.fibonacci: FibonacciResult | None = None
        self.structure: MarketStructure | None = None
        self.signal: Signal | None = None
        self.overlays = {"sr": True, "fibonacci": True, "ema": True, "bollinger": True, "swings": True, "trend": True, "signals": True}
        self.visible_count = 90
        self.offset = 0
        self.drag_x: int | None = None
        self.on_ohlc = on_ohlc
        self._context_key = ""
        self._redraw_job: str | None = None
        self.bind("<Configure>", lambda _: self.schedule_redraw(60))
        self.bind("<MouseWheel>", self._zoom)
        self.bind("<Button-4>", lambda e: self._zoom_linux(e, 1))
        self.bind("<Button-5>", lambda e: self._zoom_linux(e, -1))
        self.bind("<ButtonPress-1>", self._drag_start)
        self.bind("<B1-Motion>", self._drag_move)
        self.bind("<Motion>", self._crosshair)
        self.bind("<Leave>", self._crosshair_leave)

    def set_data(self, candles: list[Candle], indicators: pd.DataFrame, zones: list[Zone], fibonacci: FibonacciResult | None,
                 structure: MarketStructure | None = None, signal: Signal | None = None,
                 context_key: str = "") -> None:
        context_changed = bool(context_key and context_key != self._context_key)
        self.candles, self.indicators, self.zones, self.fibonacci = candles, indicators, zones, fibonacci
        self.structure, self.signal = structure, signal
        if context_changed:
            self.offset = 0
        self._context_key = context_key or self._context_key
        self.schedule_redraw()

    def update_last_candle(self, candle: Candle) -> None:
        """Atualiza somente o preço visual; indicadores pesados são recalculados em outro ritmo."""
        if not self.candles:
            return
        if self.candles[-1].open_time == candle.open_time:
            self.candles[-1] = candle
        elif candle.open_time > self.candles[-1].open_time:
            self.candles.append(candle)
            self.candles = self.candles[-500:]
        self.schedule_redraw(80)

    def schedule_redraw(self, delay_ms: int = 16) -> None:
        if self._redraw_job is not None:
            try:
                self.after_cancel(self._redraw_job)
            except tk.TclError:
                pass
        self._redraw_job = self.after(delay_ms, self.redraw)

    def set_overlay(self, name: str, value: bool) -> None:
        self.overlays[name] = value
        self.schedule_redraw()

    def fit(self) -> None:
        self.visible_count = min(max(len(self.candles), 30), 180)
        self.offset = 0
        self.schedule_redraw()

    def _zoom_linux(self, event, direction: int) -> None:
        self.visible_count = max(25, min(len(self.candles) or 200, self.visible_count - direction * 8))
        self.schedule_redraw()

    def _zoom(self, event) -> None:
        self._zoom_linux(event, 1 if event.delta > 0 else -1)

    def _drag_start(self, event) -> None:
        self.drag_x = event.x

    def _drag_move(self, event) -> None:
        if self.drag_x is None or not self.candles:
            return
        width = max(self.winfo_width() - 90, 1)
        candle_width = width / max(self.visible_count, 1)
        shift = round((self.drag_x - event.x) / max(candle_width, 1))
        if shift:
            self.offset = max(0, min(max(len(self.candles) - self.visible_count, 0), self.offset + shift))
            self.drag_x = event.x
            self.schedule_redraw()

    def _slice(self) -> tuple[list[Candle], int]:
        end = len(self.candles) - self.offset
        start = max(0, end - self.visible_count)
        return self.candles[start:end], start

    def _bounds(self, visible: list[Candle]) -> tuple[float, float]:
        low, high = min(c.low for c in visible), max(c.high for c in visible)
        margin = (high - low) * 0.08 or high * 0.001
        return low - margin, high + margin

    def redraw(self) -> None:
        self._redraw_job = None
        self.delete("all")
        width, height = self.winfo_width(), self.winfo_height()
        if width < 120 or height < 100:
            return
        left, right, top, bottom = 16, width - 74, 16, height - 70
        visible, start = self._slice()
        if not visible:
            self.create_text(width / 2, height / 2, text="Clique em INICIAR ANÁLISE", fill=COLORS["muted"], font=("Segoe UI", 12))
            return
        low, high = self._bounds(visible)
        price_height = bottom - top
        def y(price: float) -> float:
            return bottom - (price - low) / (high - low) * price_height
        count = len(visible)
        step = (right - left) / max(count, 1)
        for line in range(6):
            yy = top + price_height * line / 5
            price = high - (high - low) * line / 5
            self.create_line(left, yy, right, yy, fill=COLORS["grid"], width=1)
            self.create_text(right + 8, yy, anchor="w", text=f"{price:,.4f}", fill=COLORS["muted"], font=("Segoe UI", 8))
        if self.overlays.get("sr"):
            for zone in self.zones:
                color = COLORS["green"] if zone.kind == "SUPORTE" else COLORS["red"]
                self.create_rectangle(left, y(zone.high), right, y(zone.low), fill=color, stipple="gray12", outline=color, width=1)
                self.create_text(left + 8, y(zone.high) - 3, anchor="sw", text=f"{zone.kind} {zone.low:,.4f}–{zone.high:,.4f}", fill=color, font=("Segoe UI", 8))
        if self.overlays.get("fibonacci") and self.fibonacci:
            for ratio, price in self.fibonacci.levels.items():
                yy = y(price)
                if top <= yy <= bottom:
                    self.create_line(left, yy, right, yy, fill=COLORS["purple"], dash=(3, 4))
                    self.create_text(right - 5, yy - 2, anchor="se", text=f"FIB {ratio * 100:.1f}%", fill=COLORS["purple"], font=("Segoe UI", 8))
        if not self.indicators.empty and self.overlays.get("bollinger"):
            self._draw_line("bb_upper", start, count, left, step, y, "#466483")
            self._draw_line("bb_lower", start, count, left, step, y, "#466483")
        if not self.indicators.empty and self.overlays.get("ema"):
            self._draw_line("ema_9", start, count, left, step, y, COLORS["amber"])
            self._draw_line("ema_21", start, count, left, step, y, COLORS["accent2"])
            self._draw_line("ema_50", start, count, left, step, y, COLORS["purple"])
        max_volume = max((c.volume for c in visible), default=1) or 1
        volume_base, volume_height = height - 12, 34
        body_width = max(2, min(step * 0.66, 11))
        for index, candle in enumerate(visible):
            x = left + (index + 0.5) * step
            color = COLORS["green"] if candle.close >= candle.open else COLORS["red"]
            self.create_line(x, y(candle.high), x, y(candle.low), fill=color, width=1)
            y_open, y_close = y(candle.open), y(candle.close)
            if abs(y_open - y_close) < 1:
                self.create_line(x - body_width / 2, y_open, x + body_width / 2, y_close, fill=color, width=2)
            else:
                self.create_rectangle(x - body_width / 2, min(y_open, y_close), x + body_width / 2, max(y_open, y_close), fill=color, outline=color)
            bar_height = candle.volume / max_volume * volume_height
            self.create_rectangle(x - body_width / 2, volume_base - bar_height, x + body_width / 2, volume_base, fill=color, outline="")
        if self.structure and self.overlays.get("swings"):
            for pivot_index, marker, color, anchor in (
                *[(i, "▼", COLORS["red"], "s") for i in self.structure.pivot_highs[-8:]],
                *[(i, "▲", COLORS["green"], "n") for i in self.structure.pivot_lows[-8:]],
            ):
                local = pivot_index - start
                if 0 <= local < count:
                    candle = visible[local]
                    marker_y = y(candle.high) - 4 if marker == "▼" else y(candle.low) + 4
                    self.create_text(left + (local + 0.5) * step, marker_y, text=marker, fill=color, anchor=anchor, font=("Segoe UI", 9))
        if self.structure and self.overlays.get("trend"):
            pivots = self.structure.pivot_lows if self.structure.trend == "ALTA" else self.structure.pivot_highs
            if len(pivots) >= 2:
                i1, i2 = pivots[-2], pivots[-1]
                field = "low" if self.structure.trend == "ALTA" else "high"
                if i2 >= start and i1 < start + count:
                    price1 = float(self.indicators[field].iloc[i1]); price2 = float(self.indicators[field].iloc[i2])
                    x1 = left + (i1 - start + 0.5) * step; x2 = left + (i2 - start + 0.5) * step
                    self.create_line(x1, y(price1), x2, y(price2), fill=COLORS["amber"], width=2, dash=(6, 3))
        if self.signal and self.signal.direction != Direction.WAIT and self.overlays.get("signals"):
            marker = "▲ COMPRA" if self.signal.direction == Direction.BUY else "▼ VENDA"
            color = COLORS["green"] if self.signal.direction == Direction.BUY else COLORS["red"]
            self.create_text(right - 12, top + 14, text=marker, fill=color, anchor="ne", font=("Segoe UI Semibold", 10))
        current = visible[-1].close
        self.create_line(left, y(current), right, y(current), fill=COLORS["accent2"], dash=(2, 3))
        self.create_rectangle(right, y(current) - 9, width, y(current) + 9, fill=COLORS["accent"], outline="")
        self.create_text(right + 5, y(current), anchor="w", text=f"{current:,.4f}", fill="white", font=("Segoe UI Semibold", 8))

    def _draw_line(self, column: str, start: int, count: int, left: float, step: float, y, color: str) -> None:
        if column not in self.indicators:
            return
        values = self.indicators[column].iloc[start:start + count]
        points = []
        for index, value in enumerate(values):
            if pd.notna(value):
                points.extend([left + (index + 0.5) * step, y(float(value))])
        if len(points) >= 4:
            self.create_line(*points, fill=color, width=1.5)

    def _crosshair(self, event) -> None:
        visible, _ = self._slice()
        if not visible:
            return
        width, height = self.winfo_width(), self.winfo_height()
        left, right = 16, width - 74
        if not (left <= event.x <= right and 16 <= event.y <= height - 70):
            return
        index = min(max(int((event.x - left) / max((right - left) / len(visible), 1)), 0), len(visible) - 1)
        candle = visible[index]
        self.delete("crosshair")
        self.create_line(event.x, 16, event.x, height - 70, fill=COLORS["muted"], dash=(2, 3), tags="crosshair")
        self.create_line(left, event.y, right, event.y, fill=COLORS["muted"], dash=(2, 3), tags="crosshair")
        if self.on_ohlc:
            self.on_ohlc(f"{candle.open_time.astimezone().strftime('%d/%m %H:%M')}   O {candle.open:,.4f}   H {candle.high:,.4f}   L {candle.low:,.4f}   C {candle.close:,.4f}   V {candle.volume:,.2f}")

    def _crosshair_leave(self, _event) -> None:
        self.delete("crosshair")

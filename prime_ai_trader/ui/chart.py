from __future__ import annotations

import math
import tkinter as tk
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import pandas as pd

from ..core.models import Candle, Direction, Signal, Zone
from ..fibonacci.auto import FibonacciResult
from ..priceaction.structure import MarketStructure
from .theme import COLORS


def market_price_decimals(context_key: str, price: float = 0.0) -> int:
    parts = context_key.split("|")
    if parts and parts[0].casefold() == "forex":
        symbol = parts[1] if len(parts) > 1 else ""
        return 3 if symbol.upper().endswith("/JPY") else 5
    if parts and parts[0].casefold() == "b3":
        symbol = parts[1].upper() if len(parts) > 1 else ""
        if symbol.startswith(("WIN", "IND")):
            return 0
        if symbol.startswith(("WDO", "DOL")):
            return 1
        return 2
    return 4


def has_real_volume(candles: list[Candle]) -> bool:
    return any(math.isfinite(candle.volume) and candle.volume > 0 for candle in candles)


class CandleChart(tk.Canvas):
    def __init__(self, master, on_ohlc: Callable[[str], None] | None = None, **kwargs) -> None:
        super().__init__(master, bg=COLORS["card_alt"], highlightthickness=0, **kwargs)
        self.candles: list[Candle] = []
        self.indicators = pd.DataFrame()
        self.zones: list[Zone] = []
        self.fibonacci: FibonacciResult | None = None
        self.structure: MarketStructure | None = None
        self.signal: Signal | None = None
        self.evaluations: list[dict] = []
        self.overlays = {
            "sr": True, "fibonacci": True, "ema": True, "bollinger": True,
            "swings": True, "trend": True, "signals": True, "levels": True,
        }
        self.visible_count = 90
        self.offset = 0
        self.drag_x: int | None = None
        self.on_ohlc = on_ohlc
        self._context_key = ""
        self._redraw_job: str | None = None
        self._live_redraw_job: str | None = None
        self._plot_state: dict[str, float | int] | None = None
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
                 evaluations: list[dict] | None = None,
                 context_key: str = "") -> None:
        context_changed = bool(context_key and context_key != self._context_key)
        self.candles, self.indicators, self.zones, self.fibonacci = candles, indicators, zones, fibonacci
        self.structure, self.signal = structure, signal
        self.evaluations = list(evaluations or [])
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
            self._schedule_live_redraw()
        elif candle.open_time > self.candles[-1].open_time:
            self.candles.append(candle)
            self.candles = self.candles[-500:]
            self.schedule_redraw(40)

    def _schedule_live_redraw(self, delay_ms: int = 100) -> None:
        if self._live_redraw_job is not None:
            try:
                self.after_cancel(self._live_redraw_job)
            except tk.TclError:
                pass
        self._live_redraw_job = self.after(delay_ms, self._redraw_live_candle)

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
        right_padding = 92 if self._is_forex() else 74
        width = max(self.winfo_width() - right_padding - 16, 1)
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
        if (self.overlays.get("levels") and self.signal
                and self.signal.direction != Direction.WAIT and self.signal.entry is not None):
            level_values = (
                self.signal.entry, self.signal.technical_stop,
                self.signal.technical_target,
            )
            valid_levels = [
                float(value) for value in level_values
                if value is not None and math.isfinite(float(value))
            ]
            if valid_levels:
                low, high = min(low, *valid_levels), max(high, *valid_levels)
        if self._is_forex():
            tick = 10 ** -market_price_decimals(self._context_key, visible[-1].close)
            if high - low < tick * 8:
                midpoint = (high + low) / 2
                low, high = midpoint - tick * 4, midpoint + tick * 4
        margin = (high - low) * 0.08 or high * 0.001
        return low - margin, high + margin

    def _is_forex(self) -> bool:
        return self._context_key.split("|", 1)[0].casefold() == "forex"

    def _format_price(self, price: float) -> str:
        decimals = market_price_decimals(self._context_key, price)
        return f"{price:,.{decimals}f}"

    def redraw(self) -> None:
        self._redraw_job = None
        if self._live_redraw_job is not None:
            try:
                self.after_cancel(self._live_redraw_job)
            except tk.TclError:
                pass
            self._live_redraw_job = None
        self.delete("all")
        width, height = self.winfo_width(), self.winfo_height()
        if width < 120 or height < 100:
            return
        visible, start = self._slice()
        if not visible:
            self.create_text(width / 2, height / 2, text="Clique em INICIAR ANÁLISE", fill=COLORS["muted"], font=("Segoe UI", 12))
            return
        volume_visible = has_real_volume(visible)
        left, right, top, bottom = 16, width - (92 if self._is_forex() else 74), 16, height - (70 if volume_visible else 28)
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
            self.create_text(right + 8, yy, anchor="w", text=self._format_price(price), fill=COLORS["muted"], font=("Segoe UI", 8))
        if self.overlays.get("sr"):
            support_number = resistance_number = 0
            for zone in self.zones:
                color = COLORS["green"] if zone.kind == "SUPORTE" else COLORS["red"]
                zone_top, zone_bottom = y(zone.high), y(zone.low)
                if zone_bottom < top or zone_top > bottom:
                    continue
                if zone.kind == "SUPORTE":
                    support_number += 1
                    label = f"S{support_number}  {self._format_price(zone.midpoint)}"
                else:
                    resistance_number += 1
                    label = f"R{resistance_number}  {self._format_price(zone.midpoint)}"
                clipped_top, clipped_bottom = max(top, zone_top), min(bottom, zone_bottom)
                self.create_rectangle(
                    left, clipped_top, right, clipped_bottom, fill=color,
                    stipple="gray12", outline="", tags="structure-zone",
                )
                midpoint_y = y(zone.midpoint)
                self.create_line(
                    left, midpoint_y, right, midpoint_y, fill=color,
                    width=1, dash=(3, 5), tags="structure-zone",
                )
                self.create_text(
                    right - 5, midpoint_y - 2, anchor="se", text=label,
                    fill=color, font=("Segoe UI Semibold", 8), tags="structure-zone",
                )
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
            tags = ("market-candle", "live-candle") if index == count - 1 else ("market-candle",)
            self.create_line(x, y(candle.high), x, y(candle.low), fill=color, width=1, tags=tags)
            y_open, y_close = y(candle.open), y(candle.close)
            if abs(y_open - y_close) < 1:
                self.create_line(x - body_width / 2, y_open, x + body_width / 2, y_close, fill=color, width=2, tags=tags)
            else:
                self.create_rectangle(x - body_width / 2, min(y_open, y_close), x + body_width / 2, max(y_open, y_close), fill=color, outline=color, tags=tags)
            if volume_visible:
                bar_height = candle.volume / max_volume * volume_height
                self.create_rectangle(x - body_width / 2, volume_base - bar_height, x + body_width / 2, volume_base, fill=color, outline="", tags=tags)
        if self.overlays.get("signals") and self.evaluations:
            self._draw_evaluations(visible, left, step, y, top, bottom)
        if self.structure and self.overlays.get("swings"):
            for pivot_index, marker, color, anchor in (
                *[(i, "▼", COLORS["red"], "s") for i in self.structure.pivot_highs[-4:]],
                *[(i, "▲", COLORS["green"], "n") for i in self.structure.pivot_lows[-4:]],
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
        if (self.signal and self.signal.direction != Direction.WAIT
                and self.signal.entry is not None and self.overlays.get("levels")):
            self._draw_trade_levels(left, right, top, bottom, y)
        if self.signal and self.signal.direction != Direction.WAIT and self.overlays.get("signals"):
            marker = "▲ COMPRA" if self.signal.direction == Direction.BUY else "▼ VENDA"
            color = COLORS["green"] if self.signal.direction == Direction.BUY else COLORS["red"]
            self.create_text(right - 12, top + 14, text=marker, fill=color, anchor="ne", font=("Segoe UI Semibold", 10))
        current = visible[-1].close
        self.create_line(left, y(current), right, y(current), fill=COLORS["accent2"], dash=(2, 3), tags="live-price")
        self.create_rectangle(right, y(current) - 9, width, y(current) + 9, fill=COLORS["accent"], outline="", tags="live-price")
        self.create_text(right + 5, y(current), anchor="w", text=self._format_price(current), fill="white", font=("Segoe UI Semibold", 8), tags="live-price")
        self._plot_state = {
            "width": width, "height": height, "left": left, "right": right,
            "top": top, "bottom": bottom, "low": low, "high": high,
            "step": step, "count": count, "max_volume": max_volume,
            "volume_base": volume_base, "volume_height": volume_height,
            "body_width": body_width, "volume_visible": volume_visible,
        }

    @staticmethod
    def _operation_time(value) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _candle_index_at_or_after(visible: list[Candle], target: datetime) -> int:
        for index, candle in enumerate(visible):
            if candle.open_time.astimezone(timezone.utc) >= target:
                return index
        return len(visible) - 1

    def _draw_evaluations(self, visible: list[Candle], left: float, step: float,
                          y, top: float, bottom: float) -> None:
        if not visible:
            return
        first = visible[0].open_time.astimezone(timezone.utc)
        last = visible[-1].open_time.astimezone(timezone.utc)
        for operation in self.evaluations[-30:]:
            created = self._operation_time(operation.get("created_at"))
            if created is None or created < first - timedelta(minutes=5) or created > last + timedelta(minutes=5):
                continue
            entry_index = self._candle_index_at_or_after(visible, created)
            entry_price = operation.get("entry")
            try:
                entry_price = float(entry_price)
            except (TypeError, ValueError):
                continue
            entry_y = y(entry_price)
            if not top <= entry_y <= bottom:
                continue
            entry_x = left + (entry_index + 0.5) * step
            buy = operation.get("direction") == "COMPRA"
            color = COLORS["green"] if buy else COLORS["red"]
            marker = "▲ C" if buy else "▼ V"
            anchor = "s" if buy else "n"
            offset = -5 if buy else 5
            self.create_text(
                entry_x, entry_y + offset, text=marker, anchor=anchor, fill=color,
                font=("Segoe UI Semibold", 8), tags="evaluated-signal",
            )
            result = str(operation.get("result") or "")
            if result not in {"WIN", "LOSS", "DRAW"}:
                continue
            expiry = created + timedelta(minutes=max(1, int(operation.get("horizon_minutes") or 1)))
            result_index = self._candle_index_at_or_after(visible, expiry)
            result_x = left + (result_index + 0.5) * step
            exit_price = operation.get("exit")
            try:
                result_y = y(float(exit_price))
            except (TypeError, ValueError):
                result_y = entry_y
            result_y = min(max(result_y, top + 9), bottom - 9)
            result_color = (
                COLORS["green"] if result == "WIN" else
                COLORS["red"] if result == "LOSS" else COLORS["amber"]
            )
            source = "OBS" if operation.get("result_source") == "MANUAL" else "PÚB"
            self.create_line(
                entry_x, entry_y, result_x, result_y, fill=result_color,
                width=1, dash=(2, 3), tags="evaluated-signal",
            )
            self.create_text(
                result_x, result_y - 7, text=f"{result}·{source}", anchor="s",
                fill=result_color, font=("Segoe UI Semibold", 8),
                tags="evaluated-signal",
            )

    def _draw_trade_levels(self, left: float, right: float, top: float,
                           bottom: float, y) -> None:
        assert self.signal is not None and self.signal.entry is not None
        levels = (
            ("ENTRADA", self.signal.entry, COLORS["accent2"], (2, 4)),
            ("STOP TÉCNICO", self.signal.technical_stop, COLORS["red"], (6, 3)),
            ("ALVO TÉCNICO", self.signal.technical_target, COLORS["green"], (6, 3)),
        )
        for label, price, color, dash in levels:
            if price is None or not math.isfinite(float(price)):
                continue
            yy = y(float(price))
            if not top <= yy <= bottom:
                continue
            self.create_line(
                left, yy, right, yy, fill=color, width=1.5, dash=dash,
                tags="trade-level",
            )
            self.create_text(
                left + 7, yy - 3, anchor="sw",
                text=f"{label}  {self._format_price(float(price))}",
                fill=color, font=("Segoe UI Semibold", 8), tags="trade-level",
            )

    def _redraw_live_candle(self) -> None:
        """Redesenha só a última vela e o preço; mantém grid, overlays e histórico intactos."""
        self._live_redraw_job = None
        state = self._plot_state
        if not state or not self.candles or self.offset != 0:
            return
        candle = self.candles[-1]
        low, high = float(state["low"]), float(state["high"])
        if candle.low < low or candle.high > high or candle.volume > float(state["max_volume"]) * 1.05:
            self.schedule_redraw(16)
            return
        left, right = float(state["left"]), float(state["right"])
        top, bottom = float(state["top"]), float(state["bottom"])
        height, width = float(state["height"]), float(state["width"])
        price_height = bottom - top
        y = lambda price: bottom - (price - low) / (high - low) * price_height
        x = left + (int(state["count"]) - 0.5) * float(state["step"])
        body_width = float(state["body_width"])
        color = COLORS["green"] if candle.close >= candle.open else COLORS["red"]
        self.delete("live-candle")
        self.create_line(x, y(candle.high), x, y(candle.low), fill=color, width=1, tags="live-candle")
        y_open, y_close = y(candle.open), y(candle.close)
        if abs(y_open - y_close) < 1:
            self.create_line(x - body_width / 2, y_open, x + body_width / 2, y_close, fill=color, width=2, tags="live-candle")
        else:
            self.create_rectangle(x - body_width / 2, min(y_open, y_close), x + body_width / 2, max(y_open, y_close), fill=color, outline=color, tags="live-candle")
        if state["volume_visible"]:
            bar_height = candle.volume / max(float(state["max_volume"]), 1) * float(state["volume_height"])
            volume_base = float(state["volume_base"])
            self.create_rectangle(x - body_width / 2, volume_base - bar_height, x + body_width / 2, volume_base, fill=color, outline="", tags="live-candle")
        self.delete("live-price")
        current_y = y(candle.close)
        self.create_line(left, current_y, right, current_y, fill=COLORS["accent2"], dash=(2, 3), tags="live-price")
        self.create_rectangle(right, current_y - 9, width, current_y + 9, fill=COLORS["accent"], outline="", tags="live-price")
        self.create_text(right + 5, current_y, anchor="w", text=self._format_price(candle.close), fill="white", font=("Segoe UI Semibold", 8), tags="live-price")

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
        state = self._plot_state
        if state is None:
            return
        left, right = float(state["left"]), float(state["right"])
        top, bottom = float(state["top"]), float(state["bottom"])
        if not (left <= event.x <= right and top <= event.y <= bottom):
            return
        index = min(max(int((event.x - left) / max((right - left) / len(visible), 1)), 0), len(visible) - 1)
        candle = visible[index]
        self.delete("crosshair")
        self.create_line(event.x, top, event.x, bottom, fill=COLORS["muted"], dash=(2, 3), tags="crosshair")
        self.create_line(left, event.y, right, event.y, fill=COLORS["muted"], dash=(2, 3), tags="crosshair")
        if self.on_ohlc:
            volume = f"{candle.volume:,.2f}" if state["volume_visible"] else "—"
            self.on_ohlc(
                f"{candle.open_time.astimezone().strftime('%d/%m %H:%M')}"
                f"   O {self._format_price(candle.open)}   H {self._format_price(candle.high)}"
                f"   L {self._format_price(candle.low)}   C {self._format_price(candle.close)}   V {volume}"
            )

    def _crosshair_leave(self, _event) -> None:
        self.delete("crosshair")

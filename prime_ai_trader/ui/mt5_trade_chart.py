from __future__ import annotations

import math
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from .chart import CandleChart
from .theme import COLORS


class MT5TradeChart(CandleChart):
    """Gráfico da v1.2.6 com posições reais do MT5 sobrepostas.

    Sinais analíticos continuam sendo desenhados pelo CandleChart original. Esta
    camada desenha somente ordens/posições reais e permite arrastar SL/TP.
    """

    def __init__(
        self, master, *, on_ohlc=None,
        on_modify_position: Callable[[int, float, float], bool] | None = None,
        **kwargs,
    ) -> None:
        self.positions: list[dict[str, Any]] = []
        self.on_modify_position = on_modify_position
        self._level_drag: tuple[int, str] | None = None
        self._level_drag_original: tuple[float, float] | None = None
        super().__init__(master, on_ohlc=on_ohlc, **kwargs)
        self.bind("<ButtonRelease-1>", self._drag_release)

    def set_positions(self, positions: list[dict[str, Any]]) -> None:
        self.positions = [dict(row) for row in positions]
        self.schedule_redraw(10)

    def _bounds(self, visible):
        low, high = super()._bounds(visible)
        prices: list[float] = []
        for row in self.positions:
            for key in ("price_open", "sl", "tp"):
                try:
                    value = float(row.get(key) or 0.0)
                except (TypeError, ValueError):
                    continue
                if value > 0 and math.isfinite(value):
                    prices.append(value)
        if not prices:
            return low, high
        expanded_low = min(low, *prices)
        expanded_high = max(high, *prices)
        margin = (expanded_high - expanded_low) * 0.04 or abs(expanded_high) * 0.0001
        return expanded_low - margin, expanded_high + margin

    def redraw(self) -> None:
        super().redraw()
        self._draw_mt5_positions()

    def _price_y(self, price: float) -> float | None:
        state = self._plot_state
        if not state:
            return None
        low = float(state["low"])
        high = float(state["high"])
        top = float(state["top"])
        bottom = float(state["bottom"])
        if high <= low:
            return None
        return bottom - (price - low) / (high - low) * (bottom - top)

    def _y_price(self, y: float) -> float | None:
        state = self._plot_state
        if not state:
            return None
        low = float(state["low"])
        high = float(state["high"])
        top = float(state["top"])
        bottom = float(state["bottom"])
        if bottom <= top:
            return None
        clamped = max(top, min(bottom, float(y)))
        return low + (bottom - clamped) / (bottom - top) * (high - low)

    def _entry_x(self, row: dict[str, Any]) -> float | None:
        state = self._plot_state
        if not state or not self.candles:
            return None
        try:
            opened = datetime.fromtimestamp(float(row.get("time") or 0), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            return None
        visible, start = self._slice()
        if not visible:
            return None
        nearest_local = min(
            range(len(visible)),
            key=lambda index: abs((visible[index].open_time - opened).total_seconds()),
        )
        candle = visible[nearest_local]
        if abs((candle.open_time - opened).total_seconds()) > 86400:
            return None
        left = float(state["left"])
        step = float(state["step"])
        return left + (nearest_local + 0.5) * step

    @staticmethod
    def _side(row: dict[str, Any]) -> str:
        try:
            return "BUY" if int(row.get("type", 0)) == 0 else "SELL"
        except (TypeError, ValueError):
            return "BUY"

    def _draw_mt5_positions(self) -> None:
        state = self._plot_state
        if not state:
            return
        self.delete("mt5-position")
        left = float(state["left"])
        right = float(state["right"])
        top = float(state["top"])
        bottom = float(state["bottom"])

        for row in self.positions:
            try:
                ticket = int(row.get("ticket") or 0)
                entry = float(row.get("price_open") or 0.0)
                sl = float(row.get("sl") or 0.0)
                tp = float(row.get("tp") or 0.0)
                volume = float(row.get("volume") or 0.0)
            except (TypeError, ValueError):
                continue
            if not ticket or entry <= 0:
                continue
            side = self._side(row)
            side_color = COLORS["green"] if side == "BUY" else COLORS["red"]
            entry_y = self._price_y(entry)
            if entry_y is not None and top <= entry_y <= bottom:
                self.create_line(
                    left, entry_y, right, entry_y, fill="#e6edf3", width=1,
                    dash=(6, 4), tags=("mt5-position", f"entry-{ticket}"),
                )
                label = (
                    f"{'COMPRA' if side == 'BUY' else 'VENDA'} #{ticket}  "
                    f"{self._format_price(entry)}  •  {volume:g}"
                )
                self.create_text(
                    left + 6, entry_y - 4, text=label, anchor="sw",
                    fill="#e6edf3", font=("Segoe UI Semibold", 8),
                    tags="mt5-position",
                )
                marker_x = self._entry_x(row)
                if marker_x is not None:
                    marker = "▲" if side == "BUY" else "▼"
                    self.create_text(
                        marker_x, entry_y, text=marker, fill=side_color,
                        font=("Segoe UI", 12, "bold"), anchor="s" if side == "BUY" else "n",
                        tags="mt5-position",
                    )

            for level_name, price, color, label in (
                ("sl", sl, COLORS["red"], "SL"),
                ("tp", tp, COLORS["green"], "TP"),
            ):
                if price <= 0:
                    continue
                yy = self._price_y(price)
                if yy is None or not (top <= yy <= bottom):
                    continue
                self.create_line(
                    left, yy, right, yy, fill=color, width=2, dash=(4, 3),
                    tags=("mt5-position", f"mt5-{level_name}-{ticket}"),
                )
                self.create_rectangle(
                    right - 92, yy - 9, right, yy + 9, fill=color, outline="",
                    tags="mt5-position",
                )
                self.create_text(
                    right - 5, yy, anchor="e",
                    text=f"{label} {self._format_price(price)}  ↕",
                    fill="white", font=("Segoe UI Semibold", 8),
                    tags="mt5-position",
                )

    def _hit_level(self, event) -> tuple[int, str] | None:
        state = self._plot_state
        if not state:
            return None
        left, right = float(state["left"]), float(state["right"])
        if not (left <= event.x <= right):
            return None
        best: tuple[float, int, str] | None = None
        for row in self.positions:
            try:
                ticket = int(row.get("ticket") or 0)
            except (TypeError, ValueError):
                continue
            for name in ("sl", "tp"):
                try:
                    price = float(row.get(name) or 0.0)
                except (TypeError, ValueError):
                    continue
                if price <= 0:
                    continue
                yy = self._price_y(price)
                if yy is None:
                    continue
                distance = abs(float(event.y) - yy)
                if distance <= 8 and (best is None or distance < best[0]):
                    best = (distance, ticket, name)
        return (best[1], best[2]) if best else None

    def _drag_start(self, event) -> None:
        hit = self._hit_level(event)
        if hit:
            ticket, name = hit
            row = next((item for item in self.positions if int(item.get("ticket") or 0) == ticket), None)
            if row is not None:
                self._level_drag = (ticket, name)
                self._level_drag_original = (
                    float(row.get("sl") or 0.0), float(row.get("tp") or 0.0),
                )
                self.drag_x = None
                self.configure(cursor="sb_v_double_arrow")
                return
        self._level_drag = None
        self._level_drag_original = None
        super()._drag_start(event)

    def _drag_move(self, event) -> None:
        if not self._level_drag:
            super()._drag_move(event)
            return
        ticket, name = self._level_drag
        price = self._y_price(event.y)
        if price is None:
            return
        row = next((item for item in self.positions if int(item.get("ticket") or 0) == ticket), None)
        if row is None:
            return
        row[name] = float(price)
        self.schedule_redraw(8)

    def _drag_release(self, _event) -> None:
        if not self._level_drag:
            self.drag_x = None
            return
        ticket, _name = self._level_drag
        original = self._level_drag_original
        row = next((item for item in self.positions if int(item.get("ticket") or 0) == ticket), None)
        self._level_drag = None
        self._level_drag_original = None
        self.configure(cursor="")
        if row is None:
            return
        sl = float(row.get("sl") or 0.0)
        tp = float(row.get("tp") or 0.0)
        accepted = False
        if self.on_modify_position is not None:
            try:
                accepted = bool(self.on_modify_position(ticket, sl, tp))
            except Exception:
                accepted = False
        if not accepted and original is not None:
            row["sl"], row["tp"] = original
        self.schedule_redraw(10)

    def _crosshair(self, event) -> None:
        super()._crosshair(event)
        if self._level_drag:
            self.configure(cursor="sb_v_double_arrow")
        elif self._hit_level(event):
            self.configure(cursor="sb_v_double_arrow")
        else:
            self.configure(cursor="")

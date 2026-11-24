# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Max-Woont
"""Floating always-on-top HUD with several display modes.

The widget is fully custom-painted: each mode has a ``_measure_*`` method (returns the
window size for the current state) and a ``_paint_*`` method. All sizes are multiplied by
``overlay_scale``; colours come from :func:`overlay_style.resolve_palette`.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from power_monitor.config import OVERLAY_MODES, OVERLAY_THEMES, AppConfig
from power_monitor.models import STATUS_COLORS, STATUS_LABELS, Interval, current_period
from power_monitor.overlay_style import (
    WARNING_COLOR,
    Palette,
    anchored_position,
    clamp_to_screen,
    format_countdown,
    period_progress,
    resolve_palette,
    should_auto_hide,
    snap_to_edges,
)

_MONO_FAMILIES = ["Cascadia Mono", "Consolas", "SF Mono", "Menlo", "DejaVu Sans Mono", "monospace"]
_SCALE_PRESETS = (75, 100, 125, 150, 200)
_DRAG_THRESHOLD = 4


def _qcolor(rgba: tuple[int, int, int, int]) -> QColor:
    return QColor(*rgba)


class OverlayWidget(QWidget):
    config_changed = Signal()  # emitted after the overlay itself changed + saved the config
    settings_requested = Signal()

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._status = "unknown"
        self._countdown: Optional[timedelta] = None
        self._next_text = "Ожидание данных"
        self._hint = ""
        self._intervals: list[Interval] = []
        self._now = datetime.now().astimezone()
        self._progress: Optional[float] = None

        self._press_pos: Optional[QPoint] = None
        self._drag_offset: Optional[QPoint] = None
        self._dragging = False

        self.apply_config()

    # ------------------------------------------------------------------ config
    def apply_config(self, config: Optional[AppConfig] = None) -> None:
        """Re-reads settings. Passing ``config`` swaps the config object (used for live preview)."""
        if config is not None:
            self.config = config
        cfg = self.config
        flags = Qt.FramelessWindowHint | Qt.Tool
        if cfg.overlay_always_on_top:
            flags |= Qt.WindowStaysOnTopHint
        if cfg.overlay_click_through:
            flags |= Qt.WindowTransparentForInput
        if self.windowFlags() != flags:
            self.setWindowFlags(flags)  # note: hides the window; visibility restored below
        self.setWindowOpacity(cfg.overlay_opacity / 100.0)
        self.setCursor(Qt.ArrowCursor if cfg.overlay_lock_position else Qt.SizeAllCursor)
        self._relayout(force_move=True)
        self._update_visibility()
        self.update()

    def _save_and_notify(self) -> None:
        self.config.sanitize()
        self.config.save()
        self.apply_config()
        self.config_changed.emit()

    # ------------------------------------------------------------------- state
    def update_state(
        self,
        status: str,
        countdown: Optional[timedelta],
        next_text: str,
        intervals: list[Interval],
        now: datetime,
        short_window_warning: str = "",
    ) -> None:
        self._status = status
        self._countdown = countdown
        self._next_text = next_text
        self._intervals = intervals
        self._now = now
        self._hint = short_window_warning
        start, end, _ = current_period(intervals, now)
        self._progress = period_progress(start, end, now)
        self._relayout()
        self._update_visibility()
        self.update()

    def _update_visibility(self) -> None:
        visible = self.config.overlay_visible and not should_auto_hide(
            self._status, self._countdown, self.config.overlay_auto_hide_min
        )
        if visible != self.isVisible():
            self.setVisible(visible)

    # ----------------------------------------------------------------- helpers
    @property
    def _s(self) -> float:
        return self.config.overlay_scale / 100.0

    def _px(self, value: float) -> int:
        return max(1, round(value * self._s))

    def _font(self, size: float, bold: bool = False, mono: bool = False) -> QFont:
        font = QFont()
        if self.config.overlay_font_family:
            font.setFamily(self.config.overlay_font_family)
        elif mono:
            font.setFamilies(_MONO_FAMILIES)
            font.setStyleHint(QFont.TypeWriter)
        font.setPixelSize(self._px(size))
        font.setBold(bold)
        return font

    def _palette(self) -> Palette:
        cfg = self.config
        return resolve_palette(
            cfg.overlay_theme,
            STATUS_COLORS.get(self._status, STATUS_COLORS["unknown"]),
            cfg.overlay_bg_opacity,
            cfg.overlay_bg_color,
            cfg.overlay_text_color,
            cfg.overlay_accent_color,
        )

    def _timer_text(self) -> str:
        return format_countdown(self._countdown, self.config.overlay_show_seconds)

    def _timer_sample(self) -> str:
        return "00:00:00" if self.config.overlay_show_seconds else "00:00"

    def _is_warning(self) -> bool:
        warn = self.config.overlay_warn_min
        return bool(warn) and self._countdown is not None and self._countdown <= timedelta(minutes=warn)

    def _timer_color(self, pal: Palette) -> QColor:
        return _qcolor(pal.warning) if self._is_warning() else _qcolor(pal.text)

    def _status_text(self) -> str:
        return STATUS_LABELS.get(self._status, "Неизвестно")

    def _queue_text(self) -> str:
        return f"Оч. {self.config.queue}"

    def _radius(self, height: float) -> float:
        return min(self.config.overlay_corner_radius * self._s, height / 2)

    # ------------------------------------------------------------------ layout
    def _measure(self) -> tuple[int, int]:
        mode = self.config.overlay_mode
        return getattr(self, f"_measure_{mode}", self._measure_full)()

    def _relayout(self, force_move: bool = False) -> None:
        w, h = self._measure()
        if (w, h) != (self.width(), self.height()):
            self.setFixedSize(w, h)
            force_move = True
        if force_move and not self._dragging:
            self._reposition()

    def _screen_rect(self) -> tuple[int, int, int, int]:
        screen = QApplication.screenAt(QPoint(self.config.overlay_x, self.config.overlay_y))
        screen = screen or QApplication.primaryScreen()
        g = screen.availableGeometry()
        return g.x(), g.y(), g.width(), g.height()

    def _reposition(self) -> None:
        cfg = self.config
        screen = self._screen_rect()
        size = (self.width(), self.height())
        pos = anchored_position(cfg.overlay_anchor, screen, size, round(cfg.overlay_margin * self._s))
        if pos is None:
            pos = clamp_to_screen((cfg.overlay_x, cfg.overlay_y), size, screen)
        self.move(*pos)

    # ------------------------------------------------------------------- modes
    def _measure_full(self) -> tuple[int, int]:
        cfg = self.config
        pad_v, gap = self._px(10) + self._px(2), self._px(5)
        rows: list[int] = []
        if cfg.overlay_show_status or cfg.overlay_show_queue:
            rows.append(QFontMetrics(self._font(13, bold=True)).height())
        rows.append(QFontMetrics(self._font(26, bold=True, mono=True)).height())
        if cfg.overlay_show_next:
            rows.append(QFontMetrics(self._font(11)).height())
        if cfg.overlay_show_hint and self._hint:
            rows.append(QFontMetrics(self._font(11)).height())
        if cfg.overlay_show_timeline:
            rows.append(self._px(10))
        height = pad_v * 2 + sum(rows) + gap * (len(rows) - 1)
        return self._px(cfg.overlay_width), height

    def _paint_full(self, p: QPainter, pal: Palette) -> None:
        cfg = self.config
        pad_h, pad_v, gap = self._px(14), self._px(12), self._px(5)
        inner_w = self.width() - 2 * pad_h
        y = float(pad_v)

        if cfg.overlay_show_status or cfg.overlay_show_queue:
            f_status = self._font(13, bold=True)
            row_h = QFontMetrics(f_status).height()
            x = float(pad_h)
            if cfg.overlay_show_status:
                r = self._px(4)
                p.setPen(Qt.NoPen)
                p.setBrush(_qcolor(pal.accent))
                p.drawEllipse(QRectF(x, y + row_h / 2 - r, 2 * r, 2 * r))
                x += 2 * r + self._px(8)
                p.setFont(f_status)
                p.setPen(_qcolor(pal.text))
                p.drawText(QRectF(x, y, inner_w, row_h), Qt.AlignLeft | Qt.AlignVCenter, self._status_text())
            if cfg.overlay_show_queue:
                p.setFont(self._font(12))
                p.setPen(_qcolor(pal.muted))
                p.drawText(
                    QRectF(pad_h, y, inner_w, row_h), Qt.AlignRight | Qt.AlignVCenter, self._queue_text()
                )
            y += row_h + gap

        f_timer = self._font(26, bold=True, mono=True)
        row_h = QFontMetrics(f_timer).height()
        p.setFont(f_timer)
        p.setPen(self._timer_color(pal))
        p.drawText(QRectF(pad_h, y, inner_w, row_h), Qt.AlignLeft | Qt.AlignVCenter, self._timer_text())
        y += row_h + gap

        f_small = self._font(11)
        fm_small = QFontMetrics(f_small)
        if cfg.overlay_show_next:
            p.setFont(f_small)
            p.setPen(_qcolor(pal.muted))
            text = fm_small.elidedText(self._next_text, Qt.ElideRight, inner_w)
            p.drawText(QRectF(pad_h, y, inner_w, fm_small.height()), Qt.AlignLeft | Qt.AlignVCenter, text)
            y += fm_small.height() + gap
        if cfg.overlay_show_hint and self._hint:
            p.setFont(f_small)
            p.setPen(_qcolor(pal.warning))
            text = fm_small.elidedText(self._hint, Qt.ElideRight, inner_w)
            p.drawText(QRectF(pad_h, y, inner_w, fm_small.height()), Qt.AlignLeft | Qt.AlignVCenter, text)
            y += fm_small.height() + gap
        if cfg.overlay_show_timeline:
            self._draw_timeline(p, QRectF(pad_h, y, inner_w, self._px(10)), pal)

    def _compact_parts(self) -> list[tuple[str, QFont, str]]:
        """(text, font, role) for the compact row, left to right."""
        cfg = self.config
        parts: list[tuple[str, QFont, str]] = []
        if cfg.overlay_show_status:
            parts.append((self._status_text(), self._font(12, bold=True), "text"))
        parts.append((self._timer_sample(), self._font(15, bold=True, mono=True), "timer"))
        if cfg.overlay_show_queue:
            parts.append((self._queue_text(), self._font(11), "muted"))
        return parts

    def _measure_compact(self) -> tuple[int, int]:
        parts = self._compact_parts()
        gap = self._px(8)
        dot = self._px(8)
        width = self._px(12) * 2 + dot + gap
        width += sum(QFontMetrics(f).horizontalAdvance(t) for t, f, _ in parts) + gap * (len(parts) - 1)
        height = max(QFontMetrics(f).height() for _, f, _ in parts) + self._px(8) * 2
        if self.config.overlay_show_timeline:
            height += self._px(6)
        return width, height

    def _paint_compact(self, p: QPainter, pal: Palette) -> None:
        parts = self._compact_parts()
        pad_h, pad_v, gap = self._px(12), self._px(8), self._px(8)
        row_h = max(QFontMetrics(f).height() for _, f, _ in parts)
        x = float(pad_h)
        dot = self._px(8)
        p.setPen(Qt.NoPen)
        p.setBrush(_qcolor(pal.accent))
        p.drawEllipse(QRectF(x, pad_v + row_h / 2 - dot / 2, dot, dot))
        x += dot + gap
        for text, font, role in parts:
            w = QFontMetrics(font).horizontalAdvance(text)
            if role == "timer":
                text = self._timer_text()
                p.setPen(self._timer_color(pal))
            else:
                p.setPen(_qcolor(pal.text if role == "text" else pal.muted))
            p.setFont(font)
            p.drawText(QRectF(x, pad_v, w + 2, row_h), Qt.AlignLeft | Qt.AlignVCenter, text)
            x += w + gap
        if self.config.overlay_show_timeline:
            y = pad_v + row_h + self._px(2)
            self._draw_timeline(p, QRectF(pad_h, y, self.width() - 2 * pad_h, self._px(4)), pal)

    def _measure_minimal(self) -> tuple[int, int]:
        fm = QFontMetrics(self._font(18, bold=True, mono=True))
        return fm.horizontalAdvance(self._timer_sample()) + self._px(10) * 3 + self._px(
            4
        ), fm.height() + self._px(6) * 2

    def _paint_minimal(self, p: QPainter, pal: Palette) -> None:
        bar_w = self._px(4)
        pad = self._px(10)
        p.setPen(Qt.NoPen)
        p.setBrush(_qcolor(pal.accent))
        p.drawRoundedRect(
            QRectF(pad, self._px(7), bar_w, self.height() - 2 * self._px(7)), bar_w / 2, bar_w / 2
        )
        p.setFont(self._font(18, bold=True, mono=True))
        p.setPen(self._timer_color(pal))
        rect = QRectF(pad * 2 + bar_w, 0, self.width() - pad * 3 - bar_w, self.height())
        p.drawText(rect, Qt.AlignCenter, self._timer_text())

    def _measure_ring(self) -> tuple[int, int]:
        d = self._px(124)
        return d, d

    def _paint_ring(self, p: QPainter, pal: Palette) -> None:
        cfg = self.config
        d = float(self.width())
        thick = self._px(8)
        inset = thick / 2 + self._px(6)
        arc = QRectF(inset, inset, d - 2 * inset, d - 2 * inset)

        pen = QPen(_qcolor(pal.track), thick)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(arc)
        if self._progress is not None:
            remaining = 1.0 - self._progress
            pen.setColor(_qcolor(pal.warning) if self._is_warning() else _qcolor(pal.accent))
            p.setPen(pen)
            p.drawArc(arc, 90 * 16, round(remaining * 360 * 16))  # counter-clockwise from 12 o'clock

        f_timer = self._font(17 if cfg.overlay_show_seconds else 22, bold=True, mono=True)
        f_small = self._font(10)
        th = QFontMetrics(f_timer).height()
        sh = QFontMetrics(f_small).height()
        center_y = d / 2
        p.setFont(f_timer)
        p.setPen(self._timer_color(pal))
        p.drawText(QRectF(0, center_y - th / 2, d, th), Qt.AlignCenter, self._timer_text())
        p.setFont(f_small)
        p.setPen(_qcolor(pal.muted))
        if cfg.overlay_show_status:
            p.drawText(QRectF(0, center_y + th / 2, d, sh), Qt.AlignCenter, self._status_text())
        if cfg.overlay_show_queue:
            p.drawText(QRectF(0, center_y - th / 2 - sh, d, sh), Qt.AlignCenter, self._queue_text())

    def _measure_bar(self) -> tuple[int, int]:
        fm = QFontMetrics(self._font(12, bold=True))
        return self._px(max(self.config.overlay_width, 340)), fm.height() + self._px(8) * 2

    def _paint_bar(self, p: QPainter, pal: Palette) -> None:
        cfg = self.config
        rect = QRectF(0, 0, self.width(), self.height())
        self._draw_timeline(p, rect, pal, radius=self._radius(self.height()), alpha=200, ticks=True)
        pad = self._px(10)
        inner = rect.adjusted(pad, 0, -pad, 0)
        left = self._timer_text()
        if cfg.overlay_show_status:
            left = f"{self._status_text()} · {left}"
        right_parts = []
        if cfg.overlay_show_next:
            right_parts.append(self._next_text)
        if cfg.overlay_show_queue:
            right_parts.append(self._queue_text())
        right = " · ".join(right_parts)

        f_main = self._font(12, bold=True)
        fm = QFontMetrics(f_main)
        left_w = fm.horizontalAdvance(left)
        right = fm.elidedText(right, Qt.ElideRight, max(0, int(inner.width() - left_w - pad)))
        for dx, color in ((1, QColor(0, 0, 0, 170)), (0, QColor("#ffffff"))):
            p.setFont(f_main)
            p.setPen(
                QColor(WARNING_COLOR) if dx == 0 and self._is_warning() else color
            )  # bar is always dark-ish
            p.drawText(inner.translated(dx, dx), Qt.AlignLeft | Qt.AlignVCenter, left)
            p.setPen(color)
            p.drawText(inner.translated(dx, dx), Qt.AlignRight | Qt.AlignVCenter, right)

    # ---------------------------------------------------------------- painting
    def _draw_timeline(
        self,
        p: QPainter,
        rect: QRectF,
        pal: Palette,
        radius: Optional[float] = None,
        alpha: int = 255,
        ticks: bool = False,
    ) -> None:
        radius = rect.height() / 2 if radius is None else radius
        horizon = timedelta(hours=self.config.overlay_timeline_hours)
        start, end = self._now, self._now + horizon
        total = horizon.total_seconds()

        p.save()
        p.setPen(Qt.NoPen)
        on = QColor(STATUS_COLORS["on"])
        on.setAlpha(alpha)
        p.setBrush(on)
        p.drawRoundedRect(rect, radius, radius)
        for iv in self._intervals:
            if iv.end <= start or iv.start >= end:
                continue
            x1 = rect.x() + (max(iv.start, start) - start).total_seconds() / total * rect.width()
            x2 = rect.x() + (min(iv.end, end) - start).total_seconds() / total * rect.width()
            color = QColor(STATUS_COLORS.get(iv.kind, STATUS_COLORS["off"]))
            color.setAlpha(alpha)
            p.setBrush(color)
            seg = QRectF(x1, rect.y(), max(2.0, x2 - x1), rect.height())
            p.drawRoundedRect(seg, min(radius, seg.width() / 2), min(radius, seg.height() / 2))
        if ticks:
            p.setPen(QPen(QColor(255, 255, 255, 70), 1))
            first_hour = (start + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
            t = first_hour
            while t < end:
                x = rect.x() + (t - start).total_seconds() / total * rect.width()
                p.drawLine(QPointF(x, rect.bottom() - rect.height() * 0.3), QPointF(x, rect.bottom()))
                t += timedelta(hours=1)
        p.restore()

    def paintEvent(self, event) -> None:  # noqa: N802
        pal = self._palette()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        mode = self.config.overlay_mode
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        if mode != "bar":
            p.setBrush(_qcolor(pal.bg))
            p.setPen(QPen(_qcolor(pal.border), 1) if self.config.overlay_border else Qt.NoPen)
            if mode == "ring":
                p.drawEllipse(rect)
            else:
                r = self._radius(rect.height())
                p.drawRoundedRect(rect, r, r)

        getattr(self, f"_paint_{mode}", self._paint_full)(p, pal)

        if mode == "bar" and self.config.overlay_border:
            r = self._radius(rect.height())
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(_qcolor(pal.border), 1))
            p.drawRoundedRect(rect, r, r)
        p.end()

    # ------------------------------------------------------------ interaction
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and not self.config.overlay_lock_position:
            self._press_pos = event.globalPosition().toPoint()
            self._drag_offset = self._press_pos - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is None or not (event.buttons() & Qt.LeftButton):
            return
        pos = event.globalPosition().toPoint()
        if not self._dragging and (pos - self._press_pos).manhattanLength() < _DRAG_THRESHOLD:
            return
        self._dragging = True
        self.move(pos - self._drag_offset)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        was_dragging = self._dragging
        self._press_pos = self._drag_offset = None
        self._dragging = False
        if not was_dragging:
            return
        screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        g = screen.availableGeometry()
        x, y = snap_to_edges(
            (self.x(), self.y()), (self.width(), self.height()), (g.x(), g.y(), g.width(), g.height())
        )
        self.config.overlay_x, self.config.overlay_y = x, y
        self.config.overlay_anchor = "free"  # manual drag detaches from a screen corner
        self._save_and_notify()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            modes = list(OVERLAY_MODES)
            self.config.overlay_mode = modes[(modes.index(self.config.overlay_mode) + 1) % len(modes)]
            self._save_and_notify()

    def wheelEvent(self, event) -> None:  # noqa: N802
        if event.modifiers() & Qt.ControlModifier:
            step = 10 if event.angleDelta().y() > 0 else -10
            self.config.overlay_scale += step
            self._save_and_notify()

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        menu = QMenu(self)
        self.populate_menu(menu)
        menu.exec(event.globalPos())
        menu.deleteLater()

    def populate_menu(self, menu: QMenu) -> None:
        """Fills ``menu`` with quick overlay settings (used by the context menu and the tray)."""
        cfg = self.config

        def setter(field: str, value):
            def apply(*_):
                setattr(self.config, field, value)
                self._save_and_notify()

            return apply

        def radio_submenu(title: str, field: str, options: dict) -> None:
            sub = menu.addMenu(title)
            group = QActionGroup(sub)
            for key, label in options.items():
                act = QAction(label, sub, checkable=True, checked=getattr(cfg, field) == key)
                act.triggered.connect(setter(field, key))
                group.addAction(act)
                sub.addAction(act)

        radio_submenu("Режим", "overlay_mode", OVERLAY_MODES)
        radio_submenu("Тема", "overlay_theme", OVERLAY_THEMES)
        radio_submenu("Масштаб", "overlay_scale", {v: f"{v} %" for v in _SCALE_PRESETS})
        menu.addSeparator()
        for field, label in (
            ("overlay_show_timeline", "Шкала времени"),
            ("overlay_show_seconds", "Секунды в таймере"),
            ("overlay_lock_position", "Закрепить позицию"),
            ("overlay_always_on_top", "Поверх всех окон"),
        ):
            act = QAction(label, menu, checkable=True, checked=getattr(cfg, field))
            act.triggered.connect(lambda checked, f=field: setter(f, checked)())
            menu.addAction(act)
        menu.addSeparator()
        settings = menu.addAction("Настройки оверлея…")
        settings.triggered.connect(self.settings_requested.emit)
        hide = menu.addAction("Скрыть оверлей")
        hide.triggered.connect(setter("overlay_visible", False))

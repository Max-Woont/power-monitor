# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Max-Woont
"""Built-in pop-up notifications drawn by the app itself.

Used when system notifications are unavailable or blocked by the OS (Windows notification
settings, Focus Assist / Do Not Disturb, no notification daemon on Linux, ...).
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

_WIDTH = 330
_PAD = 14
_GAP = 10
_MARGIN = 16


class ToastWidget(QWidget):
    def __init__(self, title: str, message: str, accent: str, duration_ms: int, on_closed) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Нажмите, чтобы закрыть")
        self._title = title
        self._message = message
        self._accent = QColor(accent)
        self._on_closed = on_closed

        self._title_font = QFont()
        self._title_font.setPixelSize(14)
        self._title_font.setBold(True)
        self._text_font = QFont()
        self._text_font.setPixelSize(12)

        text_w = _WIDTH - 2 * _PAD - 8
        title_h = (
            QFontMetrics(self._title_font).boundingRect(0, 0, text_w, 1000, Qt.TextWordWrap, title).height()
        )
        text_h = (
            QFontMetrics(self._text_font).boundingRect(0, 0, text_w, 1000, Qt.TextWordWrap, message).height()
        )
        self._title_h = title_h
        self.setFixedSize(_WIDTH, _PAD * 2 + title_h + (6 + text_h if message else 0))

        QTimer.singleShot(duration_ms, self.close)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setBrush(QColor(17, 24, 39, 245))
        p.setPen(QPen(QColor(75, 85, 99), 1))
        p.drawRoundedRect(rect, 10, 10)
        p.setPen(Qt.NoPen)
        p.setBrush(self._accent)
        p.drawRoundedRect(QRectF(6, 10, 4, self.height() - 20), 2, 2)

        x = _PAD + 8
        text_w = self.width() - x - _PAD
        p.setPen(QColor("#f9fafb"))
        p.setFont(self._title_font)
        p.drawText(QRectF(x, _PAD, text_w, self._title_h), Qt.TextWordWrap, self._title)
        if self._message:
            p.setPen(QColor("#d1d5db"))
            p.setFont(self._text_font)
            y = _PAD + self._title_h + 6
            p.drawText(QRectF(x, y, text_w, self.height() - y - _PAD), Qt.TextWordWrap, self._message)
        p.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.close()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._on_closed(self)
        super().closeEvent(event)


class ToastManager:
    """Shows toasts stacked upwards from the bottom-right corner of the primary screen."""

    MAX_VISIBLE = 4

    def __init__(self) -> None:
        self._toasts: list[ToastWidget] = []

    def show(self, title: str, message: str, accent: str = "#3b82f6", duration_ms: int = 8000) -> ToastWidget:
        while len(self._toasts) >= self.MAX_VISIBLE:
            self._toasts[0].close()
        toast = ToastWidget(title, message, accent, duration_ms, self._forget)
        self._toasts.append(toast)
        self._layout()
        toast.show()
        return toast

    def _forget(self, toast: ToastWidget) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
            self._layout()

    def _layout(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        g = screen.availableGeometry()
        y = g.bottom() - _MARGIN
        for toast in reversed(self._toasts):  # newest at the bottom
            y -= toast.height()
            toast.move(g.right() - _MARGIN - toast.width(), y)
            y -= _GAP

    @property
    def visible_count(self) -> int:
        return len(self._toasts)


_manager: Optional[ToastManager] = None


def toast_manager() -> ToastManager:
    global _manager
    if _manager is None:
        _manager = ToastManager()
    return _manager

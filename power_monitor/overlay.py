from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from power_monitor.config import AppConfig
from power_monitor.models import Interval, STATUS_COLORS, STATUS_LABELS, format_duration


class TimelineBar(QWidget):
    """12-hour lookahead timeline bar."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(10)
        self.intervals: list[Interval] = []
        self.now: datetime = datetime.now().astimezone()

    def update_data(self, intervals: list[Interval], now: datetime) -> None:
        self.intervals = intervals
        self.now = now
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(0, 1, self.width(), self.height() - 2)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(STATUS_COLORS["on"]))
        painter.drawRoundedRect(rect, 4, 4)

        horizon = timedelta(hours=12)
        window_end = self.now + horizon
        total_sec = horizon.total_seconds()

        for iv in self.intervals:
            if iv.end <= self.now or iv.start >= window_end:
                continue
            seg_start = max(iv.start, self.now)
            seg_end = min(iv.end, window_end)
            x1 = ((seg_start - self.now).total_seconds() / total_sec) * self.width()
            x2 = ((seg_end - self.now).total_seconds() / total_sec) * self.width()
            painter.setBrush(QColor(STATUS_COLORS.get(iv.kind, STATUS_COLORS["off"])))
            painter.drawRoundedRect(QRectF(x1, 1, max(2.0, x2 - x1), self.height() - 2), 2, 2)

        painter.end()


class OverlayWidget(QWidget):
    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config
        self._drag_pos: Optional[QPoint] = None
        self._init_ui()
        self.apply_config()

    def _init_ui(self) -> None:
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(264)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(5)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.dot_label = QLabel("⚡")
        self.dot_label.setFont(QFont("Segoe UI", 11))

        self.status_label = QLabel("Загрузка...")
        self.status_label.setFont(QFont("Segoe UI", 10, QFont.Bold))

        self.queue_label = QLabel(f"Оч. {self.config.queue}")
        self.queue_label.setFont(QFont("Segoe UI", 9))

        top_row.addWidget(self.dot_label)
        top_row.addWidget(self.status_label)
        top_row.addStretch()
        top_row.addWidget(self.queue_label)

        self.timer_label = QLabel("--:--:--")
        self.timer_label.setFont(QFont("Consolas", 19, QFont.Bold))

        self.next_label = QLabel("Ожидание данных")
        self.next_label.setFont(QFont("Segoe UI", 8))

        self.hint_label = QLabel("")
        self.hint_label.setFont(QFont("Segoe UI", 8))
        self.hint_label.setVisible(False)

        self.timeline = TimelineBar()

        layout.addLayout(top_row)
        layout.addWidget(self.timer_label)
        layout.addWidget(self.next_label)
        layout.addWidget(self.hint_label)
        layout.addWidget(self.timeline)

    def apply_config(self) -> None:
        flags = Qt.FramelessWindowHint | Qt.Tool
        if self.config.overlay_always_on_top:
            flags |= Qt.WindowStaysOnTopHint
        if self.config.overlay_click_through:
            flags |= Qt.WindowTransparentForInput
        self.setWindowFlags(flags)
        self.setWindowOpacity(self.config.overlay_opacity / 100.0)
        self.queue_label.setText(f"Оч. {self.config.queue}")
        self.timeline.setVisible(self.config.overlay_show_timeline)

        if self.config.overlay_theme == "light":
            self.status_label.setStyleSheet("color: #111827;")
            self.timer_label.setStyleSheet("color: #030712;")
            self.next_label.setStyleSheet("color: #4b5563;")
            self.queue_label.setStyleSheet("color: #6b7280;")
        else:
            self.status_label.setStyleSheet("color: #f9fafb;")
            self.timer_label.setStyleSheet("color: #ffffff;")
            self.next_label.setStyleSheet("color: #d1d5db;")
            self.queue_label.setStyleSheet("color: #9ca3af;")

        self.move(self.config.overlay_x, self.config.overlay_y)
        self.setVisible(self.config.overlay_visible)

    def update_state(
        self,
        status: str,
        countdown: Optional[timedelta],
        next_text: str,
        intervals: list[Interval],
        now: datetime,
        short_window_warning: str = "",
    ) -> None:
        color = STATUS_COLORS.get(status, STATUS_COLORS["unknown"])
        self.dot_label.setStyleSheet(f"color: {color};")
        self.status_label.setText(STATUS_LABELS.get(status, "Неизвестно"))
        self.queue_label.setText(f"Оч. {self.config.queue}")
        self.timer_label.setText(format_duration(countdown))
        self.next_label.setText(next_text)
        if short_window_warning:
            self.hint_label.setText(short_window_warning)
            self.hint_label.setStyleSheet("color: #fbbf24;")
            self.hint_label.setVisible(True)
        else:
            self.hint_label.setVisible(False)
        self.timeline.update_data(intervals, now)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self.config.overlay_theme == "light":
            bg = QColor(249, 250, 251, 235)
            border = QColor(209, 213, 219, 210)
        else:
            bg = QColor(17, 24, 39, 230)
            border = QColor(75, 85, 99, 180)
        painter.setBrush(bg)
        painter.setPen(QPen(border, 1))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 12, 12)
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and not self.config.overlay_click_through:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_pos is not None:
            self._drag_pos = None
            self.config.overlay_x = self.x()
            self.config.overlay_y = self.y()
            self.config.save()

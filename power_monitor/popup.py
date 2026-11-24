from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from power_monitor.models import Interval, STATUS_LABELS


class SchedulePopup(QWidget):
    """Compact popup showing Today and Tomorrow outage intervals."""

    def __init__(self, on_refresh, on_settings) -> None:
        super().__init__()
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setFixedSize(330, 380)
        self._on_refresh = on_refresh
        self._on_settings = on_settings
        self._init_ui()

    def _init_ui(self) -> None:
        self.setStyleSheet(
            """
            QWidget { background-color: #111827; color: #f9fafb; font-family: 'Segoe UI'; }
            QTabWidget::pane { border: 1px solid #374151; border-radius: 6px; }
            QTabBar::tab { background: #1f2937; color: #9ca3af; padding: 6px 14px; border-top-left-radius: 6px; border-top-right-radius: 6px; }
            QTabBar::tab:selected { background: #374151; color: #ffffff; font-weight: bold; }
            QListWidget { background: #111827; border: none; padding: 4px; }
            QPushButton { background: #1f2937; border: 1px solid #374151; border-radius: 6px; padding: 6px 10px; color: #e5e7eb; }
            QPushButton:hover { background: #374151; }
            """
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        self.header_label = QLabel("Расписание отключений")
        self.header_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
        root.addWidget(self.header_label)

        self.tabs = QTabWidget()
        self.today_list = QListWidget()
        self.tomorrow_list = QListWidget()
        self.tabs.addTab(self.today_list, "Сегодня")
        self.tabs.addTab(self.tomorrow_list, "Завтра")
        root.addWidget(self.tabs)

        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("color: #9ca3af; font-size: 11px;")
        root.addWidget(self.summary_label)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("Обновить")
        refresh_btn.clicked.connect(self._on_refresh)
        settings_btn = QPushButton("Настройки")
        settings_btn.clicked.connect(self._on_settings)
        btn_row.addWidget(refresh_btn)
        btn_row.addWidget(settings_btn)
        root.addLayout(btn_row)

    def update_schedule(self, queue: str, intervals: list[Interval], now: datetime) -> None:
        self.header_label.setText(f"График · Очередь {queue}")
        today_date = now.date()
        tomorrow_date = (now + timedelta(days=1)).date()

        today_ivs = [iv for iv in intervals if iv.start.date() == today_date]
        tomorrow_ivs = [iv for iv in intervals if iv.start.date() == tomorrow_date]

        self._fill_list(self.today_list, today_ivs)
        self._fill_list(self.tomorrow_list, tomorrow_ivs)

        off_mins = sum(iv.duration_minutes for iv in today_ivs if iv.kind == "off")
        poss_mins = sum(iv.duration_minutes for iv in today_ivs if iv.kind == "possible")
        self.summary_label.setText(
            f"Сегодня без света: {off_mins / 60:.1f} ч"
            + (f" (+{poss_mins / 60:.1f} ч жёлтых)" if poss_mins else "")
        )

    def _fill_list(self, widget: QListWidget, ivs: list[Interval]) -> None:
        widget.clear()
        if not ivs:
            widget.addItem(QListWidgetItem("Отключений в графике нет"))
            return
        for iv in ivs:
            icon = "🔴" if iv.kind == "off" else "🟡"
            label = STATUS_LABELS.get(iv.kind, iv.kind)
            text = f"{icon}  {iv.start.strftime('%H:%M')} – {iv.end.strftime('%H:%M')}   ({label}, {iv.duration_minutes} мин)"
            widget.addItem(QListWidgetItem(text))

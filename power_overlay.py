"""
Power Outage Monitor & Overlay (PySide6 Prototype)
Monitors outage schedules (default: Mykolaivoblenergo via mrkaktuz/outages-data JSON),
shows status in the system tray, displays a floating countdown overlay, and sends
native desktop notifications.

Dependencies:
    pip install PySide6 requests
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests
from PySide6.QtCore import (
    QObject,
    QPoint,
    QRectF,
    Qt,
    QThread,
    QTimer,
    Signal,
)
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSlider,
    QSpinBox,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

# Normalized JSON feeds from https://github.com/mrkaktuz/outages-data (CC BY 4.0)
REGIONS = {
    "mykolaiv": "Миколаївська область (off.energy.mk.ua)",
    "dtek-kem": "м. Київ (ДТЕК КЕМ)",
    "dtek-krem": "Київська область (ДТЕК КРЕМ)",
    "dtek-dnem": "Дніпропетровська область (ДТЕК ДНЕМ)",
    "dtek-oem": "Одеська область (ДТЕК ОЕМ)",
    "ztoe": "Житомирська область (Житомиробленерго)",
}

FEED_URL_TEMPLATE = "https://raw.githubusercontent.com/mrkaktuz/outages-data/data/{region}.json"
CONFIG_PATH = Path.home() / ".power_overlay_config.json"

STATUS_COLORS = {
    "on": "#22c55e",        # Green: power is on
    "off": "#ef4444",       # Red: scheduled outage
    "possible": "#f59e0b",  # Amber: yellow/possible outage zone
    "unknown": "#6b7280",   # Gray: no data / error
}

STATUS_LABELS = {
    "on": "Свет есть",
    "off": "Отключение",
    "possible": "Жёлтая зона",
    "unknown": "Нет данных",
}


@dataclass
class AppConfig:
    region: str = "mykolaiv"
    queue: str = "4.1"
    poll_interval_min: int = 5
    remind_before_off_min: int = 15
    remind_before_on_min: int = 5
    overlay_visible: bool = True
    overlay_always_on_top: bool = True
    overlay_click_through: bool = False
    overlay_opacity: int = 90  # 20..100
    overlay_x: int = 40
    overlay_y: int = 40

    @classmethod
    def load(cls) -> "AppConfig":
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                valid_fields = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
                return cls(**valid_fields)
            except Exception:
                pass
        return cls()

    def save(self) -> None:
        CONFIG_PATH.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


@dataclass
class Interval:
    start: datetime
    end: datetime
    kind: str  # "off" | "possible"


class FetchWorker(QObject):
    finished = Signal(dict, str)  # payload, sha256_hash
    failed = Signal(str)

    def __init__(self, region: str) -> None:
        super().__init__()
        self.region = region

    def run(self) -> None:
        url = FEED_URL_TEMPLATE.format(region=self.region)
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            schedules = data.get("schedules", {})
            digest = hashlib.sha256(
                json.dumps(schedules, sort_keys=True).encode("utf-8")
            ).hexdigest()
            self.finished.emit(data, digest)
        except Exception as exc:
            self.failed.emit(str(exc))


def make_status_icon(status: str, size: int = 64) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    color = QColor(STATUS_COLORS.get(status, STATUS_COLORS["unknown"]))
    painter.setBrush(color)
    painter.setPen(QPen(QColor("#111827"), 3))
    margin = 6
    painter.drawEllipse(margin, margin, size - margin * 2, size - margin * 2)
    painter.end()
    return QIcon(pixmap)


def format_duration(delta: timedelta) -> str:
    total_sec = max(0, int(delta.total_seconds()))
    hours, rem = divmod(total_sec, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


class TimelineBar(QWidget):
    """Compact 12-hour lookahead bar rendered with QPainter."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(10)
        self.intervals: list[Interval] = []
        self.now: datetime = datetime.now(timezone.utc).astimezone()

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
            color = QColor(STATUS_COLORS.get(iv.kind, STATUS_COLORS["off"]))
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(x1, 1, max(2.0, x2 - x1), self.height() - 2), 2, 2)

        painter.end()


class OverlayWidget(QWidget):
    """Floating translucent HUD with status, countdown timer, and 12h bar."""

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config
        self._drag_pos: Optional[QPoint] = None
        self._init_ui()
        self.apply_config()

    def _init_ui(self) -> None:
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(250)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.dot_label = QLabel("●")
        self.dot_label.setFont(QFont("Segoe UI", 12))

        self.status_label = QLabel("Загрузка...")
        self.status_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.status_label.setStyleSheet("color: #f9fafb;")

        self.queue_label = QLabel(f"Оч. {self.config.queue}")
        self.queue_label.setFont(QFont("Segoe UI", 9))
        self.queue_label.setStyleSheet("color: #9ca3af;")

        top_row.addWidget(self.dot_label)
        top_row.addWidget(self.status_label)
        top_row.addStretch()
        top_row.addWidget(self.queue_label)

        self.timer_label = QLabel("--:--:--")
        self.timer_label.setFont(QFont("Consolas", 18, QFont.Bold))
        self.timer_label.setStyleSheet("color: #ffffff;")

        self.next_label = QLabel("Ожидание данных")
        self.next_label.setFont(QFont("Segoe UI", 8))
        self.next_label.setStyleSheet("color: #d1d5db;")

        self.timeline = TimelineBar()

        layout.addLayout(top_row)
        layout.addWidget(self.timer_label)
        layout.addWidget(self.next_label)
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
        self.move(self.config.overlay_x, self.config.overlay_y)
        self.setVisible(self.config.overlay_visible)

    def update_state(
        self,
        status: str,
        countdown: Optional[timedelta],
        next_text: str,
        intervals: list[Interval],
        now: datetime,
    ) -> None:
        color = STATUS_COLORS.get(status, STATUS_COLORS["unknown"])
        self.dot_label.setStyleSheet(f"color: {color};")
        self.status_label.setText(STATUS_LABELS.get(status, "Неизвестно"))
        self.queue_label.setText(f"Оч. {self.config.queue}")
        self.timer_label.setText(format_duration(countdown) if countdown else "--:--:--")
        self.next_label.setText(next_text)
        self.timeline.update_data(intervals, now)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(17, 24, 39, 225))
        painter.setPen(QPen(QColor(75, 85, 99, 180), 1))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 12, 12)
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and not self.config.overlay_click_through:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            new_pos = event.globalPosition().toPoint() - self._drag_pos
            self.move(new_pos)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_pos is not None:
            self._drag_pos = None
            self.config.overlay_x = self.x()
            self.config.overlay_y = self.y()
            self.config.save()


class SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, available_groups: list[str], parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Настройки монитора отключений")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.region_combo = QComboBox()
        for key, label in REGIONS.items():
            self.region_combo.addItem(label, key)
        idx = self.region_combo.findData(config.region)
        if idx >= 0:
            self.region_combo.setCurrentIndex(idx)

        self.queue_combo = QComboBox()
        self.queue_combo.setEditable(True)
        groups = available_groups or ["1.1", "1.2", "2.1", "2.2", "3.1", "3.2", "4.1", "4.2", "5.1", "5.2", "6.1", "6.2"]
        for g in groups:
            self.queue_combo.addItem(g)
        self.queue_combo.setCurrentText(config.queue)

        self.poll_spin = QSpinBox()
        self.poll_spin.setRange(1, 60)
        self.poll_spin.setSuffix(" мин")
        self.poll_spin.setValue(config.poll_interval_min)

        self.rem_off_spin = QSpinBox()
        self.rem_off_spin.setRange(0, 60)
        self.rem_off_spin.setSuffix(" мин")
        self.rem_off_spin.setValue(config.remind_before_off_min)

        self.rem_on_spin = QSpinBox()
        self.rem_on_spin.setRange(0, 60)
        self.rem_on_spin.setSuffix(" мин")
        self.rem_on_spin.setValue(config.remind_before_on_min)

        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(25, 100)
        self.opacity_slider.setValue(config.overlay_opacity)

        self.on_top_check = QCheckBox("Поверх всех окон (Always on Top)")
        self.on_top_check.setChecked(config.overlay_always_on_top)

        self.click_through_check = QCheckBox("Пропускать клики мыши (Click-through)")
        self.click_through_check.setChecked(config.overlay_click_through)

        form.addRow("Регион:", self.region_combo)
        form.addRow("Очередь:", self.queue_combo)
        form.addRow("Опрос API:", self.poll_spin)
        form.addRow("Напомнить до отключения:", self.rem_off_spin)
        form.addRow("Напомнить до включения:", self.rem_on_spin)
        form.addRow("Прозрачность оверлея:", self.opacity_slider)
        form.addRow("", self.on_top_check)
        form.addRow("", self.click_through_check)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addLayout(form)
        layout.addWidget(buttons)

    def apply_to_config(self) -> bool:
        region_changed = self.region_combo.currentData() != self.config.region
        self.config.region = self.region_combo.currentData()
        self.config.queue = self.queue_combo.currentText().strip()
        self.config.poll_interval_min = self.poll_spin.value()
        self.config.remind_before_off_min = self.rem_off_spin.value()
        self.config.remind_before_on_min = self.rem_on_spin.value()
        self.config.overlay_opacity = self.opacity_slider.value()
        self.config.overlay_always_on_top = self.on_top_check.isChecked()
        self.config.overlay_click_through = self.click_through_check.isChecked()
        self.config.save()
        return region_changed


class PowerMonitorApp:
    def __init__(self, qt_app: QApplication) -> None:
        self.qt_app = qt_app
        self.config = AppConfig.load()
        self.raw_data: dict = {}
        self.last_hash: Optional[str] = None
        self.intervals: list[Interval] = []
        self.last_status: Optional[str] = None
        self.sent_reminders: set[str] = set()
        self._thread: Optional[QThread] = None

        self.overlay = OverlayWidget(self.config)
        self.tray = QSystemTrayIcon(make_status_icon("unknown"), self.qt_app)
        self._setup_tray()

        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(self.fetch_schedule)
        self.poll_timer.start(self.config.poll_interval_min * 60 * 1000)

        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.tick_ui)
        self.ui_timer.start(1000)

        self.fetch_schedule()

    def _setup_tray(self) -> None:
        menu = QMenu()

        self.toggle_overlay_action = QAction("Показать / скрыть оверлей", menu)
        self.toggle_overlay_action.triggered.connect(self.toggle_overlay)

        self.click_through_action = QAction("Click-through (пропускать клики)", menu)
        self.click_through_action.setCheckable(True)
        self.click_through_action.setChecked(self.config.overlay_click_through)
        self.click_through_action.triggered.connect(self.toggle_click_through)

        refresh_action = QAction("Обновить сейчас", menu)
        refresh_action.triggered.connect(self.fetch_schedule)

        settings_action = QAction("Настройки...", menu)
        settings_action.triggered.connect(self.open_settings)

        quit_action = QAction("Выход", menu)
        quit_action.triggered.connect(self.qt_app.quit)

        menu.addAction(self.toggle_overlay_action)
        menu.addAction(self.click_through_action)
        menu.addSeparator()
        menu.addAction(refresh_action)
        menu.addAction(settings_action)
        menu.addSeparator()
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self.toggle_overlay()

    def toggle_overlay(self) -> None:
        self.config.overlay_visible = not self.config.overlay_visible
        self.config.save()
        self.overlay.apply_config()

    def toggle_click_through(self, checked: bool) -> None:
        self.config.overlay_click_through = checked
        self.config.save()
        self.overlay.apply_config()

    def open_settings(self) -> None:
        groups = self.raw_data.get("groups", [])
        dlg = SettingsDialog(self.config, groups)
        if dlg.exec() == QDialog.Accepted:
            region_changed = dlg.apply_to_config()
            self.click_through_action.setChecked(self.config.overlay_click_through)
            self.overlay.apply_config()
            self.poll_timer.setInterval(self.config.poll_interval_min * 60 * 1000)
            if region_changed:
                self.last_hash = None
                self.fetch_schedule()
            else:
                self._parse_intervals()
                self.tick_ui()

    def fetch_schedule(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        self._thread = QThread()
        self._worker = FetchWorker(self.config.region)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_fetch_success)
        self._worker.failed.connect(self._on_fetch_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.start()

    def _on_fetch_success(self, data: dict, digest: str) -> None:
        self.raw_data = data
        if self.last_hash is not None and digest != self.last_hash:
            self.notify("График обновлён", f"Расписание для очереди {self.config.queue} изменилось.")
        self.last_hash = digest
        self._parse_intervals()
        self.tick_ui()

    def _on_fetch_error(self, err: str) -> None:
        self.tray.setToolTip(f"Ошибка обновления (используется кэш): {err[:80]}")

    def _parse_intervals(self) -> None:
        sched = self.raw_data.get("schedules", {}).get(self.config.queue, {})
        parsed: list[Interval] = []
        for item in sched.get("intervals", []):
            try:
                start = datetime.fromisoformat(item["start"])
                end = datetime.fromisoformat(item["end"])
                kind = item.get("kind", "off")
                parsed.append(Interval(start=start, end=end, kind=kind))
            except Exception:
                continue
        parsed.sort(key=lambda x: x.start)
        self.intervals = parsed

    def notify(self, title: str, message: str) -> None:
        self.tray.showMessage(title, message, QSystemTrayIcon.Information, 7000)

    def tick_ui(self) -> None:
        if not self.intervals:
            self.overlay.update_state("unknown", None, "Нет данных по очереди", [], datetime.now().astimezone())
            return

        now = datetime.now(self.intervals[0].start.tzinfo)
        current_iv = next((iv for iv in self.intervals if iv.start <= now < iv.end), None)

        if current_iv is not None:
            status = current_iv.kind
            next_change = current_iv.end
            next_event_type = "on"
            next_text = f"До включения: {next_change.strftime('%H:%M')}"
        else:
            status = "on"
            future = [iv for iv in self.intervals if iv.start > now]
            if future:
                next_change = future[0].start
                next_event_type = future[0].kind
                next_text = f"Следующее отключение: {next_change.strftime('%H:%M')}"
            else:
                next_change = None
                next_event_type = ""
                next_text = "Отключений в графике нет"

        countdown = (next_change - now) if next_change else None

        # Status change notification
        if self.last_status is not None and status != self.last_status:
            self.notify(
                STATUS_LABELS.get(status, status),
                f"Очередь {self.config.queue}: {next_text}",
            )
        if status != self.last_status:
            self.tray.setIcon(make_status_icon(status))
            self.last_status = status

        # Pre-event reminders
        if countdown is not None and next_change is not None:
            mins_left = int(countdown.total_seconds() // 60)
            key = f"{next_change.isoformat()}_{next_event_type}"
            if status == "on" and self.config.remind_before_off_min > 0:
                if mins_left <= self.config.remind_before_off_min and f"off_{key}" not in self.sent_reminders:
                    self.sent_reminders.add(f"off_{key}")
                    self.notify("Скоро отключение", f"Через ~{mins_left} мин ({next_change.strftime('%H:%M')}) по очереди {self.config.queue}.")
            elif status in ("off", "possible") and self.config.remind_before_on_min > 0:
                if mins_left <= self.config.remind_before_on_min and f"on_{key}" not in self.sent_reminders:
                    self.sent_reminders.add(f"on_{key}")
                    self.notify("Скоро дадут свет", f"Через ~{mins_left} мин ({next_change.strftime('%H:%M')}) по очереди {self.config.queue}.")

        cd_str = format_duration(countdown) if countdown else "--:--"
        self.tray.setToolTip(f"Очередь {self.config.queue} · {STATUS_LABELS.get(status)} · {cd_str}")
        self.overlay.update_state(status, countdown, next_text, self.intervals, now)


def main() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    _monitor = PowerMonitorApp(app)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
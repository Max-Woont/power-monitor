# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Max-Woont
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from PySide6.QtCore import QThread, QTimer
from PySide6.QtGui import QAction, QCursor
from PySide6.QtWidgets import QApplication, QDialog, QMenu, QSystemTrayIcon

from power_monitor.config import AppConfig
from power_monitor.models import (
    STATUS_LABELS,
    Interval,
    compute_schedule_hash,
    find_next_on_window_minutes,
    parse_intervals,
    summarize_diff,
)
from power_monitor.notifier import NotificationManager
from power_monitor.overlay import OverlayWidget
from power_monitor.popup import SchedulePopup
from power_monitor.providers import FetchWorker, load_cached_data
from power_monitor.settings_dialog import SettingsDialog
from power_monitor.tray_icons import make_tray_icon

log = logging.getLogger(__name__)


class PowerMonitorApp:
    def __init__(self, qt_app: QApplication) -> None:
        self.qt_app = qt_app
        self.config = AppConfig.load()
        self.raw_data: dict = load_cached_data(self.config.region) or {}
        self.last_hash: Optional[str] = None
        self.intervals: list[Interval] = []
        self.last_status: Optional[str] = None
        self._thread: Optional[QThread] = None
        self.fetch_error = ""
        self._tooltip = ""

        self.overlay = OverlayWidget(self.config)
        self.overlay.config_changed.connect(self._sync_tray_actions)
        self.overlay.settings_requested.connect(lambda: self.open_settings(SettingsDialog.TAB_OVERLAY_LOOK))
        self.tray = QSystemTrayIcon(
            make_tray_icon("unknown", self.config.tray_icon_style),
            self.qt_app,
        )
        self.notifier = NotificationManager(self.tray, self.config)
        self.popup = SchedulePopup(self.fetch_schedule, self.open_settings)
        self._setup_tray()

        if self.raw_data:
            self.intervals = parse_intervals(
                self.raw_data, self.config.queue, self.config.treat_possible_as_off
            )
            self.last_hash = compute_schedule_hash(self.raw_data, self.config.queue)

        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(self.fetch_schedule)
        self.poll_timer.start(self.config.poll_interval_min * 60 * 1000)

        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.tick_ui)
        self.ui_timer.start(1000)

        self.tick_ui()
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

        test_notify_action = QAction("Тестовое уведомление", menu)
        test_notify_action.triggered.connect(self.send_test_notification)

        settings_action = QAction("Настройки...", menu)
        settings_action.triggered.connect(self.open_settings)

        quit_action = QAction("Выход", menu)
        quit_action.triggered.connect(self.qt_app.quit)

        # Quick overlay settings (mode, theme, scale, ...); rebuilt each time so check marks are current.
        self.overlay_menu = QMenu("Оверлей", menu)
        self.overlay_menu.aboutToShow.connect(self._rebuild_overlay_menu)

        menu.addAction(self.toggle_overlay_action)
        menu.addAction(self.click_through_action)
        menu.addMenu(self.overlay_menu)
        menu.addSeparator()
        menu.addAction(refresh_action)
        menu.addAction(test_notify_action)
        menu.addAction(settings_action)
        menu.addSeparator()
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            pos = QCursor.pos()
            self.popup.move(pos.x() - self.popup.width() // 2, max(20, pos.y() - self.popup.height() - 16))
            self.popup.show()
            self.popup.activateWindow()

    def _rebuild_overlay_menu(self) -> None:
        self.overlay_menu.clear()
        self.overlay.populate_menu(self.overlay_menu)

    def _sync_tray_actions(self) -> None:
        self.click_through_action.setChecked(self.config.overlay_click_through)

    def toggle_overlay(self) -> None:
        self.config.overlay_visible = not self.config.overlay_visible
        self.config.save()
        self.overlay.apply_config()

    def toggle_click_through(self, checked: bool) -> None:
        self.config.overlay_click_through = checked
        self.config.save()
        self.overlay.apply_config()

    def open_settings(self, initial_tab: int = 0) -> None:
        groups = self.raw_data.get("groups", [])
        dlg = SettingsDialog(
            self.config,
            groups,
            preview=self.overlay.apply_config,
            initial_tab=initial_tab,
            notifier=self.notifier,
        )
        accepted = dlg.exec() == QDialog.Accepted
        if not accepted:
            self.overlay.apply_config(self.config)  # drop the live preview
            return
        region_changed = dlg.apply_to_config()
        self._sync_tray_actions()
        self.overlay.apply_config(self.config)
        self.poll_timer.setInterval(self.config.poll_interval_min * 60 * 1000)
        self.tray.setIcon(make_tray_icon(self.last_status or "unknown", self.config.tray_icon_style))
        if region_changed:
            self.last_hash = None
            self.fetch_schedule()
        else:
            self.intervals = parse_intervals(
                self.raw_data, self.config.queue, self.config.treat_possible_as_off
            )
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

    def _on_fetch_success(self, data: dict) -> None:
        self.fetch_error = ""
        old_intervals = self.intervals
        new_intervals = parse_intervals(data, self.config.queue, self.config.treat_possible_as_off)
        new_hash = compute_schedule_hash(data, self.config.queue)
        self.raw_data = data
        self.intervals = new_intervals

        if self.last_hash is not None and new_hash != self.last_hash:
            now = (
                datetime.now(new_intervals[0].start.tzinfo) if new_intervals else datetime.now().astimezone()
            )
            diff_text = summarize_diff(old_intervals, new_intervals)
            self.notifier.send(f"График обновлён (оч. {self.config.queue})", diff_text, now, kind="info")
        self.last_hash = new_hash
        self.tick_ui()

    def _on_fetch_error(self, err: str) -> None:
        log.warning("Schedule fetch failed: %s", err)
        self.fetch_error = err

    def _set_tooltip(self, text: str) -> None:
        if self.fetch_error:
            text += f"\nОшибка сети (работа по кэшу): {self.fetch_error[:80]}"
        if text != self._tooltip:  # avoid re-sending the tray icon data to the OS every second
            self._tooltip = text
            self.tray.setToolTip(text)

    def send_test_notification(self) -> None:
        channels = self.notifier.send_test()
        log.info("Test notification channels: %s\n%s", channels, self.notifier.diagnostics())

    def tick_ui(self) -> None:
        if not self.intervals:
            now = datetime.now().astimezone()
            self.overlay.update_state("unknown", None, "Нет данных по очереди", [], now)
            self._set_tooltip(f"Очередь {self.config.queue} · нет данных")
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
                next_text = f"Отключение в {next_change.strftime('%H:%M')}"
            else:
                next_change = None
                next_event_type = ""
                next_text = "Отключений в графике нет"

        countdown = (next_change - now) if next_change else None

        if self.last_status is not None and status != self.last_status:
            self.notifier.send(
                f"{STATUS_LABELS.get(status, status)} (оч. {self.config.queue})", next_text, now, kind=status
            )
        if status != self.last_status:
            self.tray.setIcon(make_tray_icon(status, self.config.tray_icon_style))
            self.last_status = status

        if countdown is not None and next_change is not None:
            mins_left = int(countdown.total_seconds() // 60)
            key = f"{next_change.isoformat()}_{next_event_type}"
            if status == "on" and self.config.remind_before_off_min > 0:
                if mins_left <= self.config.remind_before_off_min:
                    self.notifier.send_once(
                        f"off_{key}",
                        "Скоро отключение",
                        f"Через ~{mins_left} мин ({next_change.strftime('%H:%M')}) "
                        f"по очереди {self.config.queue}.",
                        now,
                        kind="off",
                    )
            elif status in ("off", "possible") and self.config.remind_before_on_min > 0:
                if mins_left <= self.config.remind_before_on_min:
                    self.notifier.send_once(
                        f"on_{key}",
                        "Скоро дадут свет",
                        f"Через ~{mins_left} мин ({next_change.strftime('%H:%M')}), можно готовить зарядку.",
                        now,
                        kind="on",
                    )

        short_warning = ""
        on_win = find_next_on_window_minutes(self.intervals, now)
        if on_win is not None and on_win < self.config.min_charge_window_min:
            short_warning = f"⚠ Окно со светом {on_win} мин (< {self.config.min_charge_window_min} мин)"

        mins = int(countdown.total_seconds() // 60) if countdown is not None else None
        left = f"{mins // 60}:{mins % 60:02d}" if mins is not None else "--:--"
        self._set_tooltip(f"Очередь {self.config.queue} · {STATUS_LABELS.get(status)} · {left}")
        self.overlay.update_state(status, countdown, next_text, self.intervals, now, short_warning)
        self.popup.update_schedule(self.config.queue, self.intervals, now)

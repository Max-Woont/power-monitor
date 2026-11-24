# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Max-Woont
"""Notification routing: system tray balloons/toasts, the app's own pop-ups, quiet hours, logging."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from datetime import datetime
from typing import Optional

from PySide6.QtWidgets import QSystemTrayIcon

from power_monitor.config import AppConfig

log = logging.getLogger(__name__)

# Notification kinds -> accent colour of the built-in pop-up.
KIND_COLORS = {
    "off": "#ef4444",
    "on": "#22c55e",
    "possible": "#f59e0b",
    "info": "#3b82f6",
}


def is_quiet_time(hour: int, enabled: bool, start: int, end: int) -> bool:
    """True if ``hour`` falls into quiet hours [start, end), wrapping over midnight."""
    if not enabled or start == end:
        return False
    return (hour >= start or hour < end) if start > end else (start <= hour < end)


def pick_channels(method: str, system_available: bool) -> list[str]:
    """Which channels to use: 'system', 'builtin' or both. Falls back to built-in pop-ups."""
    if method == "builtin":
        return ["builtin"]
    if method == "both":
        return ["system", "builtin"] if system_available else ["builtin"]
    return ["system"] if system_available else ["builtin"]


class NotificationManager:
    def __init__(
        self,
        tray: QSystemTrayIcon,
        config: AppConfig,
        show_builtin: Optional[Callable[[str, str, str, int], object]] = None,
    ) -> None:
        self.tray = tray
        self.config = config
        self.sent_keys: set[str] = set()
        self.muted_until: Optional[datetime] = None
        if show_builtin is None:
            from power_monitor.toast import toast_manager

            show_builtin = toast_manager().show
        self._show_builtin = show_builtin

    # ------------------------------------------------------------ diagnostics
    def system_available(self) -> bool:
        return (
            QSystemTrayIcon.isSystemTrayAvailable()
            and QSystemTrayIcon.supportsMessages()
            and self.tray.isVisible()
        )

    def diagnostics(self) -> str:
        lines = [
            f"ОС: {sys.platform}",
            f"Системный трей доступен: {'да' if QSystemTrayIcon.isSystemTrayAvailable() else 'нет'}",
            f"Трей поддерживает уведомления: {'да' if QSystemTrayIcon.supportsMessages() else 'нет'}",
            f"Иконка в трее показана: {'да' if self.tray.isVisible() else 'нет'}",
        ]
        return "\n".join(lines)

    def is_quiet_now(self, now: datetime) -> bool:
        if self.muted_until and now < self.muted_until:
            return True
        c = self.config
        return is_quiet_time(now.hour, c.quiet_hours_enabled, c.quiet_start_hour, c.quiet_end_hour)

    # ---------------------------------------------------------------- sending
    def send(
        self, title: str, message: str, now: datetime, kind: str = "info", force: bool = False
    ) -> list[str]:
        """Shows a notification. ``force`` ignores quiet hours. Returns the channels used."""
        if not force and self.is_quiet_now(now):
            log.info("Suppressed by quiet hours: %s | %s", title, message)
            return []
        channels = pick_channels(self.config.notify_method, self.system_available())
        if "system" in channels:
            self.tray.showMessage(
                title, message, QSystemTrayIcon.Information, self.config.notify_duration_sec * 1000
            )
        if "builtin" in channels:
            self._show_builtin(
                title,
                message,
                KIND_COLORS.get(kind, KIND_COLORS["info"]),
                self.config.notify_duration_sec * 1000,
            )
        if self.config.notify_method != "builtin" and "system" not in channels:
            log.warning("System notifications unavailable, used built-in pop-up.\n%s", self.diagnostics())
        log.info("Notification via %s: %s | %s", "+".join(channels), title, message)
        return channels

    def send_once(
        self, key: str, title: str, message: str, now: datetime, kind: str = "info", force: bool = False
    ) -> list[str]:
        if key in self.sent_keys:
            return []
        self.sent_keys.add(key)
        return self.send(title, message, now, kind=kind, force=force)

    def send_test(self) -> list[str]:
        return self.send(
            "Power Monitor: тестовое уведомление",
            "Если вы видите это сообщение, уведомления работают.",
            datetime.now().astimezone(),
            kind="info",
            force=True,
        )

from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import QSystemTrayIcon

from power_monitor.config import AppConfig


class NotificationManager:
    def __init__(self, tray: QSystemTrayIcon, config: AppConfig) -> None:
        self.tray = tray
        self.config = config
        self.sent_keys: set[str] = set()
        self.muted_until: datetime | None = None

    def is_quiet_now(self, now: datetime) -> bool:
        if self.muted_until and now < self.muted_until:
            return True
        if not self.config.quiet_hours_enabled:
            return False
        s, e = self.config.quiet_start_hour, self.config.quiet_end_hour
        h = now.hour
        return (h >= s or h < e) if s > e else (s <= h < e)

    def send(self, title: str, message: str, now: datetime, force: bool = False) -> None:
        if not force and self.is_quiet_now(now):
            return
        icon = QSystemTrayIcon.Information if force else QSystemTrayIcon.NoIcon
        self.tray.showMessage(title, message, icon, 7000)

    def send_once(self, key: str, title: str, message: str, now: datetime, force: bool = False) -> None:
        if key in self.sent_keys:
            return
        self.sent_keys.add(key)
        self.send(title, message, now, force=force)

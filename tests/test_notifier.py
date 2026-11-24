# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Max-Woont
import os
import unittest
from datetime import datetime, timedelta, timezone

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
except ImportError:  # pragma: no cover
    QApplication = None

if QApplication is not None:
    from power_monitor.config import AppConfig
    from power_monitor.notifier import NotificationManager, is_quiet_time, pick_channels

TZ = timezone(timedelta(hours=2))


@unittest.skipIf(QApplication is None, "PySide6 is not available")
class TestRules(unittest.TestCase):
    def test_quiet_time_wraps_midnight(self):
        self.assertTrue(is_quiet_time(23, True, 23, 7))
        self.assertTrue(is_quiet_time(3, True, 23, 7))
        self.assertFalse(is_quiet_time(7, True, 23, 7))
        self.assertFalse(is_quiet_time(3, False, 23, 7))
        self.assertTrue(is_quiet_time(13, True, 12, 14))
        self.assertFalse(is_quiet_time(5, True, 5, 5))

    def test_pick_channels(self):
        self.assertEqual(pick_channels("system", True), ["system"])
        self.assertEqual(pick_channels("system", False), ["builtin"])
        self.assertEqual(pick_channels("builtin", True), ["builtin"])
        self.assertEqual(pick_channels("both", True), ["system", "builtin"])
        self.assertEqual(pick_channels("both", False), ["builtin"])


class FakeTray:
    def __init__(self, visible=True):
        self.messages = []
        self._visible = visible

    def isVisible(self):  # noqa: N802
        return self._visible

    def showMessage(self, *args):  # noqa: N802
        self.messages.append(args)


@unittest.skipIf(QApplication is None, "PySide6 is not available")
class TestManager(unittest.TestCase):
    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.tray = FakeTray()
        self.popups = []
        self.cfg = AppConfig(
            notify_method="builtin", quiet_hours_enabled=True, quiet_start_hour=23, quiet_end_hour=7
        )
        self.n = NotificationManager(self.tray, self.cfg, show_builtin=lambda *a: self.popups.append(a))

    def test_builtin_delivery(self):
        self.assertEqual(
            self.n.send("T", "M", datetime(2026, 11, 24, 12, tzinfo=TZ), kind="off"), ["builtin"]
        )
        self.assertEqual(self.popups[0][:3], ("T", "M", "#ef4444"))
        self.assertEqual(self.tray.messages, [])

    def test_quiet_hours_respected_and_force_bypasses(self):
        night = datetime(2026, 11, 24, 2, tzinfo=TZ)
        self.assertEqual(self.n.send("T", "M", night), [])
        self.assertEqual(self.n.send("T", "M", night, force=True), ["builtin"])

    def test_send_once(self):
        noon = datetime(2026, 11, 24, 12, tzinfo=TZ)
        self.n.send_once("k", "T", "M", noon)
        self.n.send_once("k", "T", "M", noon)
        self.assertEqual(len(self.popups), 1)

    def test_test_notification_ignores_quiet_hours(self):
        self.assertEqual(self.n.send_test(), ["builtin"])

    def test_builtin_toast_widget(self):
        from power_monitor.toast import ToastManager

        mgr = ToastManager()
        for i in range(6):
            mgr.show(f"Title {i}", "Message " * 10, "#22c55e", 1000)
        self.assertEqual(mgr.visible_count, ToastManager.MAX_VISIBLE)


if __name__ == "__main__":
    unittest.main()

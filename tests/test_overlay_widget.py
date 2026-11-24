# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Max-Woont
"""Smoke tests that paint every overlay mode off-screen. Skipped when Qt is unavailable."""

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
except ImportError:  # pragma: no cover - PySide6 or system GL libs missing
    QApplication = None


@unittest.skipIf(QApplication is None, "PySide6 is not available")
class TestOverlayWidget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls._tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls._tmp.name)
        cls._patches = [  # never touch the real ~/.power_monitor
            mock.patch("power_monitor.config.CONFIG_DIR", new=tmp),
            mock.patch("power_monitor.config.CONFIG_PATH", new=tmp / "config.json"),
        ]
        for p in cls._patches:
            p.start()

    @classmethod
    def tearDownClass(cls):
        for p in cls._patches:
            p.stop()
        cls._tmp.cleanup()

    def _make(self, **overrides):
        from power_monitor.config import AppConfig
        from power_monitor.models import Interval
        from power_monitor.overlay import OverlayWidget

        cfg = AppConfig(**overrides)
        widget = OverlayWidget(cfg)
        tz = timezone(timedelta(hours=2))
        now = datetime(2026, 11, 24, 9, 0, tzinfo=tz)
        ivs = [Interval(now.replace(hour=8), now.replace(hour=10), "off")]
        widget.update_state("off", timedelta(minutes=5), "До включения: 10:00", ivs, now, "⚠ short")
        return widget

    def test_every_mode_and_theme_paints(self):
        from power_monitor.config import OVERLAY_MODES, OVERLAY_THEMES

        for mode in OVERLAY_MODES:
            for theme in OVERLAY_THEMES:
                with self.subTest(mode=mode, theme=theme):
                    widget = self._make(overlay_mode=mode, overlay_theme=theme)
                    image = widget.grab().toImage()
                    self.assertGreater(image.width(), 0)
                    self.assertGreater(image.height(), 0)

    def test_scale_changes_size(self):
        small = self._make(overlay_mode="compact", overlay_scale=100)
        big = self._make(overlay_mode="compact", overlay_scale=200)
        self.assertGreater(big.width(), small.width() * 1.5)

    def test_auto_hide(self):
        widget = self._make(overlay_auto_hide_min=30)
        self.assertTrue(widget.isVisible())  # status "off" -> always shown
        widget.update_state("on", timedelta(hours=2), "", [], datetime.now().astimezone())
        self.assertFalse(widget.isVisible())


if __name__ == "__main__":
    unittest.main()

import unittest
from datetime import datetime, timedelta, timezone

from power_monitor.models import Interval, current_period
from power_monitor.overlay_style import (
    WARNING_COLOR,
    WARNING_COLOR_ON_LIGHT,
    anchored_position,
    clamp_to_screen,
    format_countdown,
    mix,
    period_progress,
    readable_text_on,
    resolve_palette,
    should_auto_hide,
    snap_to_edges,
)

TZ = timezone(timedelta(hours=2))
SCREEN = (0, 0, 1920, 1040)


def at(h, m=0):
    return datetime(2026, 11, 24, h, m, tzinfo=TZ)


class TestColors(unittest.TestCase):
    def test_mix(self):
        self.assertEqual(mix("#000000", "#ffffff", 0.5), "#808080")
        self.assertEqual(mix("#123456", "#abcdef", 0), "#123456")

    def test_readable_text(self):
        self.assertEqual(readable_text_on("#ffffff"), "#111827")
        self.assertEqual(readable_text_on("#000000"), "#f9fafb")

    def test_palette_themes(self):
        dark = resolve_palette("dark", "#ef4444", bg_opacity=100)
        light = resolve_palette("light", "#ef4444", bg_opacity=100)
        self.assertEqual(dark.bg[3], 255)
        self.assertNotEqual(dark.text, light.text)
        self.assertEqual(dark.accent[:3], (0xEF, 0x44, 0x44))
        self.assertEqual(
            light.warning[:3], tuple(int(WARNING_COLOR_ON_LIGHT[i : i + 2], 16) for i in (1, 3, 5))
        )
        self.assertEqual(dark.warning[:3], tuple(int(WARNING_COLOR[i : i + 2], 16) for i in (1, 3, 5)))

    def test_accent_override_and_custom(self):
        pal = resolve_palette("custom", "#22c55e", 50, bg_color="#ffffff", accent_color="#0000ff")
        self.assertEqual(pal.accent[:3], (0, 0, 255))
        self.assertEqual(pal.bg, (255, 255, 255, 128))
        self.assertEqual(pal.text[:3], (0x11, 0x18, 0x27))  # auto contrast on white

    def test_transparent_background(self):
        pal = resolve_palette("dark", "#22c55e", bg_opacity=0)
        self.assertEqual(pal.bg[3], 0)
        self.assertEqual(pal.border[3], 0)


class TestFormatting(unittest.TestCase):
    def test_format_countdown(self):
        d = timedelta(hours=1, minutes=5, seconds=9)
        self.assertEqual(format_countdown(d), "01:05:09")
        self.assertEqual(format_countdown(d, show_seconds=False), "1:05")
        self.assertEqual(format_countdown(None, show_seconds=False), "--:--")
        self.assertEqual(format_countdown(timedelta(seconds=-5)), "00:00:00")


class TestProgress(unittest.TestCase):
    def test_period_progress(self):
        self.assertAlmostEqual(period_progress(at(8), at(10), at(9)), 0.5)
        self.assertIsNone(period_progress(None, at(10), at(9)))
        self.assertEqual(period_progress(at(8), at(10), at(11)), 1.0)

    def test_current_period(self):
        ivs = [Interval(at(8), at(10), "off"), Interval(at(14), at(16), "off")]
        self.assertEqual(current_period(ivs, at(9))[:2], (at(8), at(10)))
        start, end, iv = current_period(ivs, at(12))
        self.assertEqual((start, end, iv), (at(10), at(14), None))
        self.assertEqual(current_period(ivs, at(7))[:2], (None, at(8)))
        self.assertEqual(current_period(ivs, at(17))[:2], (at(16), None))

    def test_auto_hide(self):
        self.assertFalse(should_auto_hide("on", timedelta(hours=3), 0))
        self.assertTrue(should_auto_hide("on", timedelta(hours=3), 60))
        self.assertFalse(should_auto_hide("on", timedelta(minutes=30), 60))
        self.assertFalse(should_auto_hide("off", timedelta(hours=3), 60))
        self.assertTrue(should_auto_hide("on", None, 60))


class TestGeometry(unittest.TestCase):
    def test_anchors(self):
        size = (200, 100)
        self.assertIsNone(anchored_position("free", SCREEN, size, 10))
        self.assertEqual(anchored_position("top-left", SCREEN, size, 10), (10, 10))
        self.assertEqual(anchored_position("bottom-right", SCREEN, size, 10), (1710, 930))
        self.assertEqual(anchored_position("top-center", SCREEN, size, 10), (860, 10))

    def test_clamp(self):
        self.assertEqual(clamp_to_screen((5000, -50), (200, 100), SCREEN), (1720, 0))

    def test_snap(self):
        self.assertEqual(snap_to_edges((10, 500), (200, 100), SCREEN), (0, 500))
        self.assertEqual(snap_to_edges((1710, 935), (200, 100), SCREEN), (1720, 940))
        self.assertEqual(snap_to_edges((300, 300), (200, 100), SCREEN), (300, 300))


if __name__ == "__main__":
    unittest.main()

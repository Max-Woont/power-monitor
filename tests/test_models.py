import unittest
from datetime import datetime, timedelta, timezone

from power_monitor.models import (
    Interval,
    find_next_on_window_minutes,
    parse_intervals,
    summarize_diff,
)


class TestModels(unittest.TestCase):
    def test_parse_and_merge(self):
        raw = {
            "schedules": {
                "4.2": {
                    "intervals": [
                        {
                            "start": "2026-11-24T08:00:00+02:00",
                            "end": "2026-11-24T10:00:00+02:00",
                            "kind": "off",
                        },
                        {
                            "start": "2026-11-24T10:00:00+02:00",
                            "end": "2026-11-24T11:30:00+02:00",
                            "kind": "off",
                        },
                    ]
                }
            }
        }
        ivs = parse_intervals(raw, "4.2")
        self.assertEqual(len(ivs), 1)
        self.assertEqual(ivs[0].duration_minutes, 210)

    def test_short_on_window_detection(self):
        tz = timezone(timedelta(hours=2))
        now = datetime(2026, 11, 24, 9, 0, tzinfo=tz)
        ivs = [
            Interval(
                datetime(2026, 11, 24, 8, 0, tzinfo=tz), datetime(2026, 11, 24, 10, 0, tzinfo=tz), "off"
            ),
            Interval(
                datetime(2026, 11, 24, 10, 45, tzinfo=tz), datetime(2026, 11, 24, 14, 0, tzinfo=tz), "off"
            ),
        ]
        self.assertEqual(find_next_on_window_minutes(ivs, now), 45)

    def test_diff_summary(self):
        tz = timezone(timedelta(hours=2))
        old = [
            Interval(datetime(2026, 11, 24, 8, 0, tzinfo=tz), datetime(2026, 11, 24, 10, 0, tzinfo=tz), "off")
        ]
        new = [
            Interval(
                datetime(2026, 11, 24, 12, 0, tzinfo=tz), datetime(2026, 11, 24, 14, 0, tzinfo=tz), "off"
            )
        ]
        diff = summarize_diff(old, new)
        self.assertIn("Добавлено", diff)
        self.assertIn("Убрано", diff)


if __name__ == "__main__":
    unittest.main()

import unittest

from power_monitor.config import OVERLAY_MODES, AppConfig


class TestConfig(unittest.TestCase):
    def test_defaults_are_valid(self):
        cfg = AppConfig()
        before = vars(cfg).copy()
        cfg.sanitize()
        self.assertEqual(vars(cfg), before)

    def test_from_dict_drops_unknown_and_wrong_types(self):
        cfg = AppConfig.from_dict({"bogus": 1, "queue": 42, "overlay_border": "yes", "overlay_scale": 130.7})
        self.assertEqual(cfg.queue, AppConfig().queue)
        self.assertTrue(cfg.overlay_border)
        self.assertEqual(cfg.overlay_scale, 130)

    def test_clamps_and_resets_enums(self):
        cfg = AppConfig.from_dict(
            {"overlay_scale": 9999, "overlay_opacity": 1, "overlay_mode": "hologram", "region": "mars"}
        )
        self.assertEqual(cfg.overlay_scale, 250)
        self.assertEqual(cfg.overlay_opacity, 25)
        self.assertEqual(cfg.overlay_mode, "full")
        self.assertEqual(cfg.region, "mykolaiv")

    def test_bool_is_not_accepted_as_int(self):
        cfg = AppConfig.from_dict({"overlay_scale": True})
        self.assertEqual(cfg.overlay_scale, 100)

    def test_colors_validated(self):
        cfg = AppConfig.from_dict({"overlay_bg_color": "#ABCDEF", "overlay_text_color": "red"})
        self.assertEqual(cfg.overlay_bg_color, "#abcdef")
        self.assertEqual(cfg.overlay_text_color, "")

    def test_reset_overlay_look_keeps_position_and_behaviour(self):
        cfg = AppConfig(
            overlay_mode="ring", overlay_scale=180, overlay_x=500, overlay_click_through=True, queue="1.1"
        )
        cfg.reset_overlay_look()
        self.assertEqual(cfg.overlay_mode, "full")
        self.assertEqual(cfg.overlay_scale, 100)
        self.assertEqual(cfg.overlay_x, 500)
        self.assertTrue(cfg.overlay_click_through)
        self.assertEqual(cfg.queue, "1.1")

    def test_every_mode_accepted(self):
        for mode in OVERLAY_MODES:
            self.assertEqual(AppConfig.from_dict({"overlay_mode": mode}).overlay_mode, mode)


if __name__ == "__main__":
    unittest.main()

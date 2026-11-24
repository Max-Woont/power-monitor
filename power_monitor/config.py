"""Persistent application settings (``~/.power_monitor/config.json``)."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, fields
from pathlib import Path

CONFIG_DIR = Path.home() / ".power_monitor"
CONFIG_PATH = CONFIG_DIR / "config.json"
STATE_CACHE_PATH = CONFIG_DIR / "state_cache.json"

REGIONS = {
    "mykolaiv": "Миколаївська область (off.energy.mk.ua)",
    "dtek-kem": "м. Київ (ДТЕК КЕМ)",
    "dtek-krem": "Київська область (ДТЕК КРЕМ)",
    "dtek-dnem": "Дніпропетровська область (ДТЕК ДНЕМ)",
    "dtek-oem": "Одеська область (ДТЕК ОЕМ)",
    "ztoe": "Житомирська область (Житомиробленерго)",
}

# Display modes of the floating overlay.
OVERLAY_MODES = {
    "full": "Полный (карточка)",
    "compact": "Компактный (одна строка)",
    "minimal": "Минимальный (только таймер)",
    "ring": "Кольцо прогресса",
    "bar": "Полоса-шкала",
}

OVERLAY_THEMES = {
    "dark": "Тёмная",
    "light": "Светлая",
    "status": "Цвет статуса",
    "custom": "Своя (цвета ниже)",
}

OVERLAY_ANCHORS = {
    "free": "Свободно (перетаскивание)",
    "top-left": "Сверху слева",
    "top-center": "Сверху по центру",
    "top-right": "Сверху справа",
    "bottom-left": "Снизу слева",
    "bottom-center": "Снизу по центру",
    "bottom-right": "Снизу справа",
}

TRAY_ICON_STYLES = {
    "bolt_badge": "Бейдж с молнией (⚡)",
    "battery": "Батарея",
}

# Field name -> (min, max) for integer settings; out-of-range values are clamped on load.
_INT_RANGES: dict[str, tuple[int, int]] = {
    "poll_interval_min": (1, 60),
    "remind_before_off_min": (0, 60),
    "remind_before_on_min": (0, 60),
    "quiet_start_hour": (0, 23),
    "quiet_end_hour": (0, 23),
    "min_charge_window_min": (15, 240),
    "overlay_opacity": (25, 100),
    "overlay_bg_opacity": (0, 100),
    "overlay_scale": (50, 250),
    "overlay_width": (160, 640),
    "overlay_corner_radius": (0, 32),
    "overlay_margin": (0, 200),
    "overlay_timeline_hours": (3, 24),
    "overlay_warn_min": (0, 120),
    "overlay_auto_hide_min": (0, 720),
    "overlay_x": (-10000, 10000),
    "overlay_y": (-10000, 10000),
}

# Field name -> allowed values for enumerated settings; unknown values fall back to the default.
_CHOICES: dict[str, tuple[str, ...]] = {
    "region": tuple(REGIONS),
    "tray_icon_style": tuple(TRAY_ICON_STYLES),
    "overlay_mode": tuple(OVERLAY_MODES),
    "overlay_theme": tuple(OVERLAY_THEMES),
    "overlay_anchor": tuple(OVERLAY_ANCHORS),
}

# Colour fields accept "#rrggbb" or "" (= use the theme / status colour).
_COLOR_FIELDS = ("overlay_bg_color", "overlay_text_color", "overlay_accent_color")
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass
class AppConfig:
    region: str = "mykolaiv"
    queue: str = "4.2"
    poll_interval_min: int = 5
    treat_possible_as_off: bool = False

    # Notifications & QOL
    remind_before_off_min: int = 15
    remind_before_on_min: int = 5
    quiet_hours_enabled: bool = True
    quiet_start_hour: int = 23
    quiet_end_hour: int = 7
    silent_tomorrow_notify: bool = True
    min_charge_window_min: int = 60  # ALLPOWERS R1500 Lite full charge ~60 min

    # Tray
    tray_icon_style: str = "bolt_badge"

    # Overlay: behaviour
    overlay_visible: bool = True
    overlay_always_on_top: bool = True
    overlay_click_through: bool = False
    overlay_lock_position: bool = False
    overlay_anchor: str = "free"
    overlay_margin: int = 24
    overlay_x: int = 40
    overlay_y: int = 40
    overlay_auto_hide_min: int = 0  # 0 = off; hide while power is on and the outage is further away

    # Overlay: look
    overlay_mode: str = "full"
    overlay_theme: str = "dark"
    overlay_opacity: int = 92  # whole window, 25..100
    overlay_bg_opacity: int = 90  # background only, 0..100
    overlay_scale: int = 100  # percent
    overlay_width: int = 264  # px at 100 % (full / bar modes)
    overlay_corner_radius: int = 12
    overlay_border: bool = True
    overlay_font_family: str = ""  # "" = system default
    overlay_bg_color: str = ""
    overlay_text_color: str = ""
    overlay_accent_color: str = ""  # "" = colour of current status

    # Overlay: elements
    overlay_show_status: bool = True
    overlay_show_queue: bool = True
    overlay_show_next: bool = True
    overlay_show_hint: bool = True
    overlay_show_timeline: bool = True
    overlay_show_seconds: bool = True
    overlay_timeline_hours: int = 12
    overlay_warn_min: int = 10  # highlight the timer during the last N minutes; 0 = off

    @classmethod
    def load(cls) -> AppConfig:
        if CONFIG_PATH.exists():
            try:
                raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    return cls.from_dict(raw)
            except (OSError, ValueError):
                pass
        return cls()

    @classmethod
    def from_dict(cls, raw: dict) -> AppConfig:
        """Builds a config from untrusted JSON: unknown keys are dropped, bad values reset/clamped."""
        cfg = cls()
        for f in fields(cls):
            if f.name not in raw:
                continue
            default = getattr(cfg, f.name)
            value = raw[f.name]
            if isinstance(default, bool):
                if isinstance(value, bool):
                    setattr(cfg, f.name, value)
            elif isinstance(default, int):
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    setattr(cfg, f.name, int(value))
            elif isinstance(default, str):
                if isinstance(value, str):
                    setattr(cfg, f.name, value)
        cfg.sanitize()
        return cfg

    def sanitize(self) -> None:
        defaults = type(self)()
        for name, (lo, hi) in _INT_RANGES.items():
            setattr(self, name, max(lo, min(hi, int(getattr(self, name)))))
        for name, choices in _CHOICES.items():
            if getattr(self, name) not in choices:
                setattr(self, name, getattr(defaults, name))
        for name in _COLOR_FIELDS:
            value = getattr(self, name).strip()
            setattr(self, name, value.lower() if _HEX_RE.match(value) else "")
        self.queue = self.queue.strip() or defaults.queue

    def reset_overlay_look(self) -> None:
        """Restores every overlay appearance setting (not position/behaviour) to defaults."""
        defaults = type(self)()
        keep = {
            "overlay_visible",
            "overlay_always_on_top",
            "overlay_click_through",
            "overlay_lock_position",
            "overlay_anchor",
            "overlay_margin",
            "overlay_x",
            "overlay_y",
            "overlay_auto_hide_min",
        }
        for f in fields(self):
            if f.name.startswith("overlay_") and f.name not in keep:
                setattr(self, f.name, getattr(defaults, f.name))

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

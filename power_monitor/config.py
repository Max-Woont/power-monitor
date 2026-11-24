from __future__ import annotations

import json
from dataclasses import asdict, dataclass
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

    # Tray & Overlay UI
    tray_icon_style: str = "bolt_badge"  # "bolt_badge" | "battery"
    overlay_visible: bool = True
    overlay_always_on_top: bool = True
    overlay_click_through: bool = False
    overlay_theme: str = "dark"  # "dark" | "light"
    overlay_opacity: int = 92  # 25..100
    overlay_x: int = 40
    overlay_y: int = 40
    overlay_show_timeline: bool = True

    @classmethod
    def load(cls) -> "AppConfig":
        if CONFIG_PATH.exists():
            try:
                raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                valid = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
                return cls(**valid)
            except Exception:
                pass
        return cls()

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

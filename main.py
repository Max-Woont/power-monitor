# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Max-Woont
import logging
import sys
from logging.handlers import RotatingFileHandler

from PySide6.QtWidgets import QApplication

from power_monitor.app import PowerMonitorApp
from power_monitor.config import CONFIG_DIR

LOG_PATH = CONFIG_DIR / "power_monitor.log"


def setup_logging() -> None:
    """Writes a small rotating log to ~/.power_monitor/power_monitor.log (the exe has no console)."""
    handlers: list[logging.Handler] = []
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(LOG_PATH, maxBytes=512_000, backupCount=2, encoding="utf-8"))
    except OSError:
        pass
    if sys.stderr is not None:  # None in a windowed PyInstaller build
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def main() -> None:
    setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("PowerMonitor")
    app.setApplicationDisplayName("Power Monitor")
    app.setQuitOnLastWindowClosed(False)
    _monitor = PowerMonitorApp(app)
    logging.getLogger(__name__).info("Started, log file: %s", LOG_PATH)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

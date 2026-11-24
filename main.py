import sys
from PySide6.QtWidgets import QApplication
from power_monitor.app import PowerMonitorApp


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("PowerMonitor")
    app.setQuitOnLastWindowClosed(False)
    _monitor = PowerMonitorApp(app)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from power_monitor.config import AppConfig, REGIONS


class SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, available_groups: list[str], parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Настройки Power Monitor")
        self.setMinimumWidth(420)

        root = QVBoxLayout(self)
        tabs = QTabWidget()

        # Tab 1: Region & Data
        tab_data = QWidget()
        form_data = QFormLayout(tab_data)

        self.region_combo = QComboBox()
        for key, label in REGIONS.items():
            self.region_combo.addItem(label, key)
        idx = self.region_combo.findData(config.region)
        if idx >= 0:
            self.region_combo.setCurrentIndex(idx)

        self.queue_combo = QComboBox()
        self.queue_combo.setEditable(True)
        groups = available_groups or [
            "1.1", "1.2", "2.1", "2.2", "3.1", "3.2",
            "4.1", "4.2", "5.1", "5.2", "6.1", "6.2",
        ]
        for g in groups:
            self.queue_combo.addItem(g)
        self.queue_combo.setCurrentText(config.queue)

        self.poll_spin = QSpinBox()
        self.poll_spin.setRange(1, 60)
        self.poll_spin.setSuffix(" мин")
        self.poll_spin.setValue(config.poll_interval_min)

        self.possible_as_off_check = QCheckBox("Считать «жёлтую» зону отключением")
        self.possible_as_off_check.setChecked(config.treat_possible_as_off)

        self.charge_min_spin = QSpinBox()
        self.charge_min_spin.setRange(15, 240)
        self.charge_min_spin.setSuffix(" мин")
        self.charge_min_spin.setValue(config.min_charge_window_min)

        form_data.addRow("Регион:", self.region_combo)
        form_data.addRow("Очередь / подочередь:", self.queue_combo)
        form_data.addRow("Интервал опроса:", self.poll_spin)
        form_data.addRow("Порог зарядки станции:", self.charge_min_spin)
        form_data.addRow("", self.possible_as_off_check)

        # Tab 2: Tray & Overlay Graphics
        tab_ui = QWidget()
        form_ui = QFormLayout(tab_ui)

        self.tray_style_combo = QComboBox()
        self.tray_style_combo.addItem("Бейдж с молнией (⚡)", "bolt_badge")
        self.tray_style_combo.addItem("Батарея", "battery")
        t_idx = self.tray_style_combo.findData(config.tray_icon_style)
        if t_idx >= 0:
            self.tray_style_combo.setCurrentIndex(t_idx)

        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Тёмная", "dark")
        self.theme_combo.addItem("Светлая", "light")
        th_idx = self.theme_combo.findData(config.overlay_theme)
        if th_idx >= 0:
            self.theme_combo.setCurrentIndex(th_idx)

        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(25, 100)
        self.opacity_slider.setValue(config.overlay_opacity)

        self.overlay_vis_check = QCheckBox("Показывать оверлей")
        self.overlay_vis_check.setChecked(config.overlay_visible)

        self.on_top_check = QCheckBox("Поверх всех окон (Always on Top)")
        self.on_top_check.setChecked(config.overlay_always_on_top)

        self.click_through_check = QCheckBox("Пропускать клики мыши (Click-through)")
        self.click_through_check.setChecked(config.overlay_click_through)

        self.timeline_check = QCheckBox("Показывать 12-часовую шкалу в оверлее")
        self.timeline_check.setChecked(config.overlay_show_timeline)

        form_ui.addRow("Иконка в трее:", self.tray_style_combo)
        form_ui.addRow("Тема оверлея:", self.theme_combo)
        form_ui.addRow("Прозрачность:", self.opacity_slider)
        form_ui.addRow("", self.overlay_vis_check)
        form_ui.addRow("", self.on_top_check)
        form_ui.addRow("", self.click_through_check)
        form_ui.addRow("", self.timeline_check)

        # Tab 3: Notifications & QOL
        tab_notif = QWidget()
        form_notif = QFormLayout(tab_notif)

        self.rem_off_spin = QSpinBox()
        self.rem_off_spin.setRange(0, 60)
        self.rem_off_spin.setSuffix(" мин")
        self.rem_off_spin.setValue(config.remind_before_off_min)

        self.rem_on_spin = QSpinBox()
        self.rem_on_spin.setRange(0, 60)
        self.rem_on_spin.setSuffix(" мин")
        self.rem_on_spin.setValue(config.remind_before_on_min)

        self.quiet_check = QCheckBox("Тихие часы (не беспокоить ночью)")
        self.quiet_check.setChecked(config.quiet_hours_enabled)

        self.quiet_start_spin = QSpinBox()
        self.quiet_start_spin.setRange(0, 23)
        self.quiet_start_spin.setSuffix(":00")
        self.quiet_start_spin.setValue(config.quiet_start_hour)

        self.quiet_end_spin = QSpinBox()
        self.quiet_end_spin.setRange(0, 23)
        self.quiet_end_spin.setSuffix(":00")
        self.quiet_end_spin.setValue(config.quiet_end_hour)

        form_notif.addRow("Напомнить до отключения:", self.rem_off_spin)
        form_notif.addRow("Напомнить до включения:", self.rem_on_spin)
        form_notif.addRow("", self.quiet_check)
        form_notif.addRow("Тихие часы с:", self.quiet_start_spin)
        form_notif.addRow("Тихие часы до:", self.quiet_end_spin)

        tabs.addTab(tab_data, "Регион и данные")
        tabs.addTab(tab_ui, "Трей и оверлей")
        tabs.addTab(tab_notif, "Уведомления")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root.addWidget(tabs)
        root.addWidget(buttons)

    def apply_to_config(self) -> bool:
        region_changed = self.region_combo.currentData() != self.config.region
        self.config.region = self.region_combo.currentData()
        self.config.queue = self.queue_combo.currentText().strip()
        self.config.poll_interval_min = self.poll_spin.value()
        self.config.treat_possible_as_off = self.possible_as_off_check.isChecked()
        self.config.min_charge_window_min = self.charge_min_spin.value()

        self.config.tray_icon_style = self.tray_style_combo.currentData()
        self.config.overlay_theme = self.theme_combo.currentData()
        self.config.overlay_opacity = self.opacity_slider.value()
        self.config.overlay_visible = self.overlay_vis_check.isChecked()
        self.config.overlay_always_on_top = self.on_top_check.isChecked()
        self.config.overlay_click_through = self.click_through_check.isChecked()
        self.config.overlay_show_timeline = self.timeline_check.isChecked()

        self.config.remind_before_off_min = self.rem_off_spin.value()
        self.config.remind_before_on_min = self.rem_on_spin.value()
        self.config.quiet_hours_enabled = self.quiet_check.isChecked()
        self.config.quiet_start_hour = self.quiet_start_spin.value()
        self.config.quiet_end_hour = self.quiet_end_spin.value()

        self.config.save()
        return region_changed

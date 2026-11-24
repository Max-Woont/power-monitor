# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Max-Woont
"""Settings dialog. Overlay changes are previewed live and reverted on Cancel."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFontComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from power_monitor.config import (
    OVERLAY_ANCHORS,
    OVERLAY_MODES,
    OVERLAY_THEMES,
    REGIONS,
    TRAY_ICON_STYLES,
    AppConfig,
)
from power_monitor.providers import DATA_ATTRIBUTION_HTML

DEFAULT_GROUPS = ["1.1", "1.2", "2.1", "2.2", "3.1", "3.2", "4.1", "4.2", "5.1", "5.2", "6.1", "6.2"]


class ColorPicker(QWidget):
    """Colour swatch button with an "auto" reset. ``value()`` is ``"#rrggbb"`` or ``""``."""

    changed = Signal()

    def __init__(self, value: str, auto_text: str = "авто", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._value = value
        self._auto_text = auto_text
        self.button = QPushButton()
        self.button.setMinimumWidth(110)
        self.button.clicked.connect(self._pick)
        reset = QPushButton("×")
        reset.setFixedWidth(28)
        reset.setToolTip("Сбросить на автоматический цвет")
        reset.clicked.connect(lambda: self.set_value(""))
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.button)
        row.addWidget(reset)
        row.addStretch()
        self._refresh()

    def value(self) -> str:
        return self._value

    def set_value(self, value: str) -> None:
        self._value = value
        self._refresh()
        self.changed.emit()

    def _pick(self) -> None:
        color = QColorDialog.getColor(QColor(self._value or "#888888"), self, "Выбор цвета")
        if color.isValid():
            self.set_value(color.name())

    def _refresh(self) -> None:
        if self._value:
            text_color = "#000" if QColor(self._value).lightness() > 140 else "#fff"
            self.button.setText(self._value)
            self.button.setStyleSheet(f"background:{self._value}; color:{text_color};")
        else:
            self.button.setText(self._auto_text)
            self.button.setStyleSheet("")


def _combo(options: dict, current) -> QComboBox:
    combo = QComboBox()
    for key, label in options.items():
        combo.addItem(label, key)
    idx = combo.findData(current)
    if idx >= 0:
        combo.setCurrentIndex(idx)
    return combo


def _spin(lo: int, hi: int, value: int, suffix: str = "", special: str = "") -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(lo, hi)
    spin.setValue(value)
    if suffix:
        spin.setSuffix(suffix)
    if special:
        spin.setSpecialValueText(special)  # shown instead of the minimum value
    return spin


def _check(text: str, value: bool) -> QCheckBox:
    box = QCheckBox(text)
    box.setChecked(value)
    return box


def _slider(lo: int, hi: int, value: int, suffix: str = " %") -> tuple[QWidget, QSlider]:
    slider = QSlider(Qt.Horizontal)
    slider.setRange(lo, hi)
    slider.setValue(value)
    label = QLabel(f"{value}{suffix}")
    label.setMinimumWidth(44)
    slider.valueChanged.connect(lambda v: label.setText(f"{v}{suffix}"))
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    row.addWidget(slider)
    row.addWidget(label)
    return box, slider


class SettingsDialog(QDialog):
    TAB_DATA, TAB_OVERLAY_LOOK, TAB_OVERLAY_BEHAVIOUR, TAB_NOTIFY = range(4)

    def __init__(
        self,
        config: AppConfig,
        available_groups: list[str],
        preview: Optional[Callable[[AppConfig], None]] = None,
        parent: Optional[QWidget] = None,
        initial_tab: int = 0,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self._preview = preview
        self._draft = replace(config)
        self.setWindowTitle("Настройки Power Monitor")
        self.setMinimumWidth(460)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_data_tab(available_groups), "Регион и данные")
        self.tabs.addTab(self._build_look_tab(), "Оверлей: вид")
        self.tabs.addTab(self._build_behaviour_tab(), "Оверлей: поведение")
        self.tabs.addTab(self._build_notify_tab(), "Трей и уведомления")
        self.tabs.setCurrentIndex(initial_tab)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addWidget(self.tabs)
        root.addWidget(buttons)

        self._wire_preview()
        self._sync_enabled()

    # ------------------------------------------------------------------ tabs
    def _build_data_tab(self, groups: list[str]) -> QWidget:
        c = self.config
        tab = QWidget()
        form = QFormLayout(tab)
        self.region_combo = _combo(REGIONS, c.region)
        self.queue_combo = QComboBox()
        self.queue_combo.setEditable(True)
        self.queue_combo.addItems(groups or DEFAULT_GROUPS)
        self.queue_combo.setCurrentText(c.queue)
        self.poll_spin = _spin(1, 60, c.poll_interval_min, " мин")
        self.charge_min_spin = _spin(15, 240, c.min_charge_window_min, " мин")
        self.possible_as_off_check = _check("Считать «жёлтую» зону отключением", c.treat_possible_as_off)
        form.addRow("Регион:", self.region_combo)
        form.addRow("Очередь / подочередь:", self.queue_combo)
        form.addRow("Интервал опроса:", self.poll_spin)
        form.addRow("Порог зарядки станции:", self.charge_min_spin)
        form.addRow("", self.possible_as_off_check)
        source = QLabel(DATA_ATTRIBUTION_HTML)
        source.setWordWrap(True)
        source.setOpenExternalLinks(True)
        source.setStyleSheet("color: gray;")
        form.addRow(source)
        return tab

    def _build_look_tab(self) -> QWidget:
        c = self.config
        tab = QWidget()
        layout = QVBoxLayout(tab)

        style_box = QGroupBox("Режим и оформление")
        form = QFormLayout(style_box)
        self.mode_combo = _combo(OVERLAY_MODES, c.overlay_mode)
        self.theme_combo = _combo(OVERLAY_THEMES, c.overlay_theme)
        self.accent_picker = ColorPicker(c.overlay_accent_color, "цвет статуса")
        self.bg_picker = ColorPicker(c.overlay_bg_color)
        self.text_picker = ColorPicker(c.overlay_text_color, "авто-контраст")
        scale_box, self.scale_slider = _slider(50, 250, c.overlay_scale)
        opacity_box, self.opacity_slider = _slider(25, 100, c.overlay_opacity)
        bg_opacity_box, self.bg_opacity_slider = _slider(0, 100, c.overlay_bg_opacity)
        self.width_spin = _spin(160, 640, c.overlay_width, " px")
        self.radius_spin = _spin(0, 32, c.overlay_corner_radius, " px")
        self.border_check = _check("Рамка", c.overlay_border)

        self.system_font_check = _check("Системный шрифт", not c.overlay_font_family)
        self.font_combo = QFontComboBox()
        if c.overlay_font_family:
            self.font_combo.setCurrentFont(QFont(c.overlay_font_family))
        font_row = QWidget()
        fr = QHBoxLayout(font_row)
        fr.setContentsMargins(0, 0, 0, 0)
        fr.addWidget(self.system_font_check)
        fr.addWidget(self.font_combo, 1)

        form.addRow("Режим:", self.mode_combo)
        form.addRow("Тема:", self.theme_combo)
        form.addRow("Акцентный цвет:", self.accent_picker)
        form.addRow("Цвет фона:", self.bg_picker)
        form.addRow("Цвет текста:", self.text_picker)
        form.addRow("Масштаб:", scale_box)
        form.addRow("Прозрачность окна:", opacity_box)
        form.addRow("Непрозрачность фона:", bg_opacity_box)
        form.addRow("Ширина (полный / полоса):", self.width_spin)
        form.addRow("Скругление углов:", self.radius_spin)
        form.addRow("Шрифт:", font_row)
        form.addRow("", self.border_check)

        elem_box = QGroupBox("Элементы")
        ef = QFormLayout(elem_box)
        self.show_status_check = _check("Статус", c.overlay_show_status)
        self.show_queue_check = _check("Номер очереди", c.overlay_show_queue)
        self.show_next_check = _check("Строка «следующее событие»", c.overlay_show_next)
        self.show_hint_check = _check("Предупреждение о коротком окне", c.overlay_show_hint)
        self.show_seconds_check = _check("Секунды в таймере", c.overlay_show_seconds)
        self.timeline_check = _check("Шкала времени", c.overlay_show_timeline)
        self.timeline_hours_spin = _spin(3, 24, c.overlay_timeline_hours, " ч")
        self.warn_spin = _spin(0, 120, c.overlay_warn_min, " мин", special="выкл.")
        grid = QHBoxLayout()
        col1, col2 = QVBoxLayout(), QVBoxLayout()
        for w in (self.show_status_check, self.show_queue_check, self.show_next_check):
            col1.addWidget(w)
        for w in (self.show_hint_check, self.show_seconds_check, self.timeline_check):
            col2.addWidget(w)
        grid.addLayout(col1)
        grid.addLayout(col2)
        ef.addRow(grid)
        ef.addRow("Горизонт шкалы:", self.timeline_hours_spin)
        ef.addRow("Подсветка таймера за:", self.warn_spin)

        reset_btn = QPushButton("Сбросить оформление")
        reset_btn.clicked.connect(self._reset_look)

        layout.addWidget(style_box)
        layout.addWidget(elem_box)
        layout.addWidget(reset_btn, 0, Qt.AlignRight)
        return tab

    def _build_behaviour_tab(self) -> QWidget:
        c = self.config
        tab = QWidget()
        form = QFormLayout(tab)
        self.overlay_vis_check = _check("Показывать оверлей", c.overlay_visible)
        self.on_top_check = _check("Поверх всех окон (Always on Top)", c.overlay_always_on_top)
        self.click_through_check = _check("Пропускать клики мыши (Click-through)", c.overlay_click_through)
        self.lock_check = _check("Закрепить позицию (запретить перетаскивание)", c.overlay_lock_position)
        self.anchor_combo = _combo(OVERLAY_ANCHORS, c.overlay_anchor)
        self.margin_spin = _spin(0, 200, c.overlay_margin, " px")
        self.auto_hide_spin = _spin(0, 720, c.overlay_auto_hide_min, " мин", special="никогда")
        self.auto_hide_spin.setToolTip(
            "Прятать оверлей, пока свет есть и до отключения больше указанного времени."
        )
        hint = QLabel(
            "Подсказки: ПКМ по оверлею открывает быстрое меню, двойной клик включает следующий режим, "
            "Ctrl + колесо меняет масштаб. При включённом Click-through оверлей управляется только из трея."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        form.addRow("", self.overlay_vis_check)
        form.addRow("", self.on_top_check)
        form.addRow("", self.click_through_check)
        form.addRow("", self.lock_check)
        form.addRow("Привязка к краю экрана:", self.anchor_combo)
        form.addRow("Отступ от края:", self.margin_spin)
        form.addRow("Прятать, если до отключения больше:", self.auto_hide_spin)
        form.addRow(hint)
        return tab

    def _build_notify_tab(self) -> QWidget:
        c = self.config
        tab = QWidget()
        form = QFormLayout(tab)
        self.tray_style_combo = _combo(TRAY_ICON_STYLES, c.tray_icon_style)
        self.rem_off_spin = _spin(0, 60, c.remind_before_off_min, " мин", special="выкл.")
        self.rem_on_spin = _spin(0, 60, c.remind_before_on_min, " мин", special="выкл.")
        self.quiet_check = _check("Тихие часы (не беспокоить ночью)", c.quiet_hours_enabled)
        self.quiet_start_spin = _spin(0, 23, c.quiet_start_hour, ":00")
        self.quiet_end_spin = _spin(0, 23, c.quiet_end_hour, ":00")
        form.addRow("Иконка в трее:", self.tray_style_combo)
        form.addRow("Напомнить до отключения:", self.rem_off_spin)
        form.addRow("Напомнить до включения:", self.rem_on_spin)
        form.addRow("", self.quiet_check)
        form.addRow("Тихие часы с:", self.quiet_start_spin)
        form.addRow("Тихие часы до:", self.quiet_end_spin)
        return tab

    # --------------------------------------------------------------- preview
    def _overlay_widgets(self) -> list[QWidget]:
        return [
            self.mode_combo,
            self.theme_combo,
            self.accent_picker,
            self.bg_picker,
            self.text_picker,
            self.scale_slider,
            self.opacity_slider,
            self.bg_opacity_slider,
            self.width_spin,
            self.radius_spin,
            self.border_check,
            self.system_font_check,
            self.font_combo,
            self.show_status_check,
            self.show_queue_check,
            self.show_next_check,
            self.show_hint_check,
            self.show_seconds_check,
            self.timeline_check,
            self.timeline_hours_spin,
            self.warn_spin,
            self.overlay_vis_check,
            self.on_top_check,
            self.click_through_check,
            self.lock_check,
            self.anchor_combo,
            self.margin_spin,
            self.auto_hide_spin,
        ]

    def _wire_preview(self) -> None:
        for w in self._overlay_widgets():
            for sig in ("currentIndexChanged", "valueChanged", "toggled", "changed", "currentFontChanged"):
                if hasattr(w, sig):
                    getattr(w, sig).connect(self._on_overlay_changed)
                    break

    def _on_overlay_changed(self, *_) -> None:
        self._sync_enabled()
        if self._preview is not None:
            self._collect(self._draft)
            self._preview(self._draft)

    def _sync_enabled(self) -> None:
        custom = self.theme_combo.currentData() == "custom"
        self.bg_picker.setEnabled(custom)
        self.text_picker.setEnabled(custom)
        self.font_combo.setEnabled(not self.system_font_check.isChecked())
        self.timeline_hours_spin.setEnabled(
            self.timeline_check.isChecked() or self.mode_combo.currentData() == "bar"
        )
        self.margin_spin.setEnabled(self.anchor_combo.currentData() != "free")

    def _reset_look(self) -> None:
        defaults = replace(self.config)
        defaults.reset_overlay_look()
        self._load_look(defaults)

    def _load_look(self, c: AppConfig) -> None:
        for combo, value in (
            (self.mode_combo, c.overlay_mode),
            (self.theme_combo, c.overlay_theme),
        ):
            combo.setCurrentIndex(max(0, combo.findData(value)))
        self.accent_picker.set_value(c.overlay_accent_color)
        self.bg_picker.set_value(c.overlay_bg_color)
        self.text_picker.set_value(c.overlay_text_color)
        self.scale_slider.setValue(c.overlay_scale)
        self.opacity_slider.setValue(c.overlay_opacity)
        self.bg_opacity_slider.setValue(c.overlay_bg_opacity)
        self.width_spin.setValue(c.overlay_width)
        self.radius_spin.setValue(c.overlay_corner_radius)
        self.border_check.setChecked(c.overlay_border)
        self.system_font_check.setChecked(not c.overlay_font_family)
        self.show_status_check.setChecked(c.overlay_show_status)
        self.show_queue_check.setChecked(c.overlay_show_queue)
        self.show_next_check.setChecked(c.overlay_show_next)
        self.show_hint_check.setChecked(c.overlay_show_hint)
        self.show_seconds_check.setChecked(c.overlay_show_seconds)
        self.timeline_check.setChecked(c.overlay_show_timeline)
        self.timeline_hours_spin.setValue(c.overlay_timeline_hours)
        self.warn_spin.setValue(c.overlay_warn_min)

    # ----------------------------------------------------------------- apply
    def _collect(self, c: AppConfig) -> None:
        c.region = self.region_combo.currentData()
        c.queue = self.queue_combo.currentText().strip()
        c.poll_interval_min = self.poll_spin.value()
        c.treat_possible_as_off = self.possible_as_off_check.isChecked()
        c.min_charge_window_min = self.charge_min_spin.value()

        c.overlay_mode = self.mode_combo.currentData()
        c.overlay_theme = self.theme_combo.currentData()
        c.overlay_accent_color = self.accent_picker.value()
        c.overlay_bg_color = self.bg_picker.value()
        c.overlay_text_color = self.text_picker.value()
        c.overlay_scale = self.scale_slider.value()
        c.overlay_opacity = self.opacity_slider.value()
        c.overlay_bg_opacity = self.bg_opacity_slider.value()
        c.overlay_width = self.width_spin.value()
        c.overlay_corner_radius = self.radius_spin.value()
        c.overlay_border = self.border_check.isChecked()
        c.overlay_font_family = (
            "" if self.system_font_check.isChecked() else self.font_combo.currentFont().family()
        )
        c.overlay_show_status = self.show_status_check.isChecked()
        c.overlay_show_queue = self.show_queue_check.isChecked()
        c.overlay_show_next = self.show_next_check.isChecked()
        c.overlay_show_hint = self.show_hint_check.isChecked()
        c.overlay_show_seconds = self.show_seconds_check.isChecked()
        c.overlay_show_timeline = self.timeline_check.isChecked()
        c.overlay_timeline_hours = self.timeline_hours_spin.value()
        c.overlay_warn_min = self.warn_spin.value()

        c.overlay_visible = self.overlay_vis_check.isChecked()
        c.overlay_always_on_top = self.on_top_check.isChecked()
        c.overlay_click_through = self.click_through_check.isChecked()
        c.overlay_lock_position = self.lock_check.isChecked()
        c.overlay_anchor = self.anchor_combo.currentData()
        c.overlay_margin = self.margin_spin.value()
        c.overlay_auto_hide_min = self.auto_hide_spin.value()

        c.tray_icon_style = self.tray_style_combo.currentData()
        c.remind_before_off_min = self.rem_off_spin.value()
        c.remind_before_on_min = self.rem_on_spin.value()
        c.quiet_hours_enabled = self.quiet_check.isChecked()
        c.quiet_start_hour = self.quiet_start_spin.value()
        c.quiet_end_hour = self.quiet_end_spin.value()
        c.sanitize()

    def apply_to_config(self) -> bool:
        """Writes the dialog values into the live config and saves it. Returns True if the region changed."""
        region_changed = self.region_combo.currentData() != self.config.region
        self._collect(self.config)
        self.config.save()
        return region_changed

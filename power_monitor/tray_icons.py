# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Max-Woont
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from power_monitor.models import STATUS_COLORS


def make_tray_icon(status: str, style: str = "bolt_badge", size: int = 128) -> QIcon:
    """
    Draws a crisp vector tray icon that does NOT resemble a green voice-activity ring:
    - 'bolt_badge': dark rounded-square badge with a colored border and a central lightning bolt / X.
    - 'battery': vertical battery silhouette filled according to status.
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)

    accent = QColor(STATUS_COLORS.get(status, STATUS_COLORS["unknown"]))
    bg = QColor("#111827")

    if style == "battery":
        _draw_battery_icon(p, size, accent, bg, status)
    else:
        _draw_bolt_badge(p, size, accent, bg, status)

    p.end()
    return QIcon(pixmap)


def _draw_bolt_badge(p: QPainter, size: int, accent: QColor, bg: QColor, status: str) -> None:
    pad = size * 0.08
    rect = QRectF(pad, pad, size - 2 * pad, size - 2 * pad)
    radius = size * 0.24

    # Rounded square badge
    p.setBrush(bg)
    p.setPen(QPen(accent, size * 0.085))
    p.drawRoundedRect(rect, radius, radius)

    # Lightning bolt path inside
    bolt = QPainterPath()
    bolt.moveTo(QPointF(size * 0.56, size * 0.20))
    bolt.lineTo(QPointF(size * 0.30, size * 0.54))
    bolt.lineTo(QPointF(size * 0.49, size * 0.54))
    bolt.lineTo(QPointF(size * 0.42, size * 0.80))
    bolt.lineTo(QPointF(size * 0.70, size * 0.45))
    bolt.lineTo(QPointF(size * 0.51, size * 0.45))
    bolt.closeSubpath()

    p.setPen(Qt.NoPen)
    p.setBrush(accent)
    p.drawPath(bolt)

    # Diagonal slash when power is OFF so it's unmistakable even for colorblind users
    if status == "off":
        p.setPen(QPen(QColor("#ffffff"), size * 0.08, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(size * 0.24, size * 0.76), QPointF(size * 0.76, size * 0.24))


def _draw_battery_icon(p: QPainter, size: int, accent: QColor, bg: QColor, status: str) -> None:
    # Battery cap
    cap_w = size * 0.28
    cap_h = size * 0.08
    p.setPen(Qt.NoPen)
    p.setBrush(accent)
    p.drawRoundedRect(QRectF((size - cap_w) / 2, size * 0.08, cap_w, cap_h), 4, 4)

    # Battery body
    body_rect = QRectF(size * 0.22, size * 0.16, size * 0.56, size * 0.74)
    p.setBrush(bg)
    p.setPen(QPen(accent, size * 0.075))
    p.drawRoundedRect(body_rect, size * 0.10, size * 0.10)

    # Fill level bar
    fill_h = body_rect.height() * (0.72 if status == "on" else 0.42 if status == "possible" else 0.20)
    fill_rect = QRectF(
        body_rect.left() + size * 0.09,
        body_rect.bottom() - fill_h - size * 0.07,
        body_rect.width() - size * 0.18,
        fill_h,
    )
    p.setPen(Qt.NoPen)
    p.setBrush(accent)
    p.drawRoundedRect(fill_rect, 4, 4)

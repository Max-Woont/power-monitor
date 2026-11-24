"""Qt-free helpers for the overlay: colour palettes, text formatting and window geometry.

Kept separate from ``overlay.py`` so the logic can be unit-tested without a display.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

RGBA = tuple[int, int, int, int]
Rect = tuple[int, int, int, int]  # x, y, width, height

_BASE_THEMES: dict[str, dict[str, str]] = {
    "dark": {"bg": "#111827", "border": "#4b5563", "text": "#f9fafb", "muted": "#9ca3af"},
    "light": {"bg": "#f9fafb", "border": "#d1d5db", "text": "#111827", "muted": "#4b5563"},
}
WARNING_COLOR = "#fbbf24"
WARNING_COLOR_ON_LIGHT = "#b45309"


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def mix(a: str, b: str, t: float) -> str:
    """Linear blend of two hex colours: t=0 -> a, t=1 -> b."""
    ra, rb = hex_to_rgb(a), hex_to_rgb(b)
    return rgb_to_hex(tuple(round(x + (y - x) * t) for x, y in zip(ra, rb, strict=True)))  # type: ignore[arg-type]


def luminance(color: str) -> float:
    """WCAG relative luminance (0..1)."""

    def channel(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in hex_to_rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def readable_text_on(bg: str) -> str:
    return "#111827" if luminance(bg) > 0.4 else "#f9fafb"


def _rgba(color: str, alpha: int = 255) -> RGBA:
    r, g, b = hex_to_rgb(color)
    return r, g, b, max(0, min(255, alpha))


@dataclass(frozen=True)
class Palette:
    bg: RGBA
    border: RGBA
    text: RGBA
    muted: RGBA
    accent: RGBA
    track: RGBA  # empty part of progress bars / rings
    warning: RGBA  # "last minutes" timer highlight and short-window hint


def resolve_palette(
    theme: str,
    status_color: str,
    bg_opacity: int = 90,
    bg_color: str = "",
    text_color: str = "",
    accent_color: str = "",
) -> Palette:
    """Computes overlay colours for a theme.

    ``bg_color``/``text_color`` are only used by the ``custom`` theme; ``accent_color``
    overrides the status colour in every theme. Empty strings mean "automatic".
    """
    accent = accent_color or status_color

    if theme == "status":
        bg = mix("#0b0f19", status_color, 0.35)
        text = "#ffffff"
        border = status_color
        muted = mix(text, bg, 0.3)
    elif theme == "custom":
        bg = bg_color or _BASE_THEMES["dark"]["bg"]
        text = text_color or readable_text_on(bg)
        border = mix(text, bg, 0.7)
        muted = mix(text, bg, 0.4)
    else:
        base = _BASE_THEMES.get(theme, _BASE_THEMES["dark"])
        bg, text, border, muted = base["bg"], base["text"], base["border"], base["muted"]

    alpha = round(255 * max(0, min(100, bg_opacity)) / 100)
    return Palette(
        bg=_rgba(bg, alpha),
        border=_rgba(border, max(alpha, 120) if alpha else 0),
        text=_rgba(text),
        muted=_rgba(muted),
        accent=_rgba(accent),
        track=_rgba(mix(bg, text, 0.18), max(alpha, 140)),
        warning=_rgba(WARNING_COLOR_ON_LIGHT if luminance(bg) > 0.4 and bg_opacity >= 50 else WARNING_COLOR),
    )


def format_countdown(delta: Optional[timedelta], show_seconds: bool = True) -> str:
    """``01:05:09`` with seconds, ``1:05`` (h:mm) without; ``--`` placeholders when unknown."""
    if delta is None:
        return "--:--:--" if show_seconds else "--:--"
    total = max(0, int(delta.total_seconds()))
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    if show_seconds:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{hours}:{minutes:02d}"


def period_progress(start: Optional[datetime], end: Optional[datetime], now: datetime) -> Optional[float]:
    """Fraction (0..1) of the period [start, end) that has elapsed, or None if unbounded."""
    if start is None or end is None or end <= start:
        return None
    frac = (now - start).total_seconds() / (end - start).total_seconds()
    return max(0.0, min(1.0, frac))


def anchored_position(
    anchor: str, screen: Rect, size: tuple[int, int], margin: int
) -> Optional[tuple[int, int]]:
    """Top-left corner for a window of ``size`` pinned to ``anchor`` of ``screen``; None for 'free'."""
    if anchor == "free" or "-" not in anchor:
        return None
    sx, sy, sw, sh = screen
    w, h = size
    vert, horiz = anchor.split("-", 1)
    y = sy + margin if vert == "top" else sy + sh - h - margin
    if horiz == "left":
        x = sx + margin
    elif horiz == "right":
        x = sx + sw - w - margin
    else:
        x = sx + (sw - w) // 2
    return x, y


def clamp_to_screen(pos: tuple[int, int], size: tuple[int, int], screen: Rect) -> tuple[int, int]:
    """Keeps the whole window inside ``screen`` (if it fits)."""
    sx, sy, sw, sh = screen
    w, h = size
    x = max(sx, min(pos[0], sx + sw - w))
    y = max(sy, min(pos[1], sy + sh - h))
    return x, y


def snap_to_edges(
    pos: tuple[int, int], size: tuple[int, int], screen: Rect, threshold: int = 16
) -> tuple[int, int]:
    """Sticks the window to a screen edge when dropped within ``threshold`` px of it."""
    sx, sy, sw, sh = screen
    w, h = size
    x, y = pos
    if abs(x - sx) <= threshold:
        x = sx
    elif abs(sx + sw - (x + w)) <= threshold:
        x = sx + sw - w
    if abs(y - sy) <= threshold:
        y = sy
    elif abs(sy + sh - (y + h)) <= threshold:
        y = sy + sh - h
    return x, y


def should_auto_hide(status: str, countdown: Optional[timedelta], threshold_min: int) -> bool:
    """True when power is on and the next outage is further away than ``threshold_min`` minutes."""
    if threshold_min <= 0 or status != "on":
        return False
    if countdown is None:
        return True
    return countdown > timedelta(minutes=threshold_min)

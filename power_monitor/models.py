from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

STATUS_COLORS = {
    "on": "#22c55e",
    "off": "#ef4444",
    "possible": "#f59e0b",
    "unknown": "#6b7280",
}

STATUS_LABELS = {
    "on": "Свет есть",
    "off": "Отключение",
    "possible": "Жёлтая зона",
    "unknown": "Нет данных",
}


@dataclass(frozen=True)
class Interval:
    start: datetime
    end: datetime
    kind: str  # "off" | "possible"

    @property
    def duration_minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


def parse_intervals(raw_data: dict, queue: str, treat_possible_as_off: bool = False) -> list[Interval]:
    sched = raw_data.get("schedules", {}).get(queue, {})
    parsed: list[Interval] = []
    for item in sched.get("intervals", []):
        try:
            start = datetime.fromisoformat(item["start"])
            end = datetime.fromisoformat(item["end"])
            kind = item.get("kind", "off")
            if treat_possible_as_off and kind == "possible":
                kind = "off"
            if end > start:
                parsed.append(Interval(start=start, end=end, kind=kind))
        except Exception:
            continue
    parsed.sort(key=lambda x: x.start)
    return merge_adjacent_intervals(parsed)


def merge_adjacent_intervals(intervals: list[Interval]) -> list[Interval]:
    if not intervals:
        return []
    merged: list[Interval] = [intervals[0]]
    for iv in intervals[1:]:
        prev = merged[-1]
        if prev.kind == iv.kind and prev.end >= iv.start:
            merged[-1] = Interval(start=prev.start, end=max(prev.end, iv.end), kind=prev.kind)
        else:
            merged.append(iv)
    return merged


def compute_schedule_hash(raw_data: dict, queue: str) -> str:
    sched = raw_data.get("schedules", {}).get(queue, {})
    return hashlib.sha256(json.dumps(sched, sort_keys=True).encode("utf-8")).hexdigest()


def summarize_diff(old_intervals: list[Interval], new_intervals: list[Interval]) -> str:
    old_set = {(iv.start.strftime("%d.%m %H:%M"), iv.end.strftime("%H:%M"), iv.kind) for iv in old_intervals}
    new_set = {(iv.start.strftime("%d.%m %H:%M"), iv.end.strftime("%H:%M"), iv.kind) for iv in new_intervals}
    added = sorted(new_set - old_set)
    removed = sorted(old_set - new_set)
    parts: list[str] = []
    if added:
        parts.append("Добавлено: " + ", ".join(f"{s}–{e}" for s, e, _ in added[:3]))
    if removed:
        parts.append("Убрано: " + ", ".join(f"{s}–{e}" for s, e, _ in removed[:3]))
    return "; ".join(parts) if parts else "Обновлены детали расписания."


def format_duration(delta: Optional[timedelta]) -> str:
    if delta is None:
        return "--:--:--"
    total_sec = max(0, int(delta.total_seconds()))
    hours, rem = divmod(total_sec, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def find_next_on_window_minutes(intervals: list[Interval], now: datetime) -> Optional[int]:
    """Returns duration in minutes of the next 'on' window (or current 'on' window remaining)."""
    future_offs = [iv for iv in intervals if iv.end > now]
    if not future_offs:
        return None
    current_off = next((iv for iv in future_offs if iv.start <= now < iv.end), None)
    if current_off:
        next_start = current_off.end
        after = [iv for iv in future_offs if iv.start > next_start]
        if not after:
            return None
        return int((after[0].start - next_start).total_seconds() // 60)
    return int((future_offs[0].start - now).total_seconds() // 60)


def current_period(
    intervals: list[Interval], now: datetime
) -> tuple[Optional[datetime], Optional[datetime], Optional[Interval]]:
    """Bounds of the period ``now`` falls into.

    Returns ``(start, end, interval)``: inside an outage interval it is that interval;
    otherwise it is the "power on" gap between the previous interval's end and the next
    one's start (either bound may be None when there is no such interval).
    """
    for iv in intervals:
        if iv.start <= now < iv.end:
            return iv.start, iv.end, iv
    prev_end = max((iv.end for iv in intervals if iv.end <= now), default=None)
    next_start = min((iv.start for iv in intervals if iv.start > now), default=None)
    return prev_end, next_start, None

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Max-Woont
from __future__ import annotations

import json

import requests
from PySide6.QtCore import QObject, Signal

from power_monitor.config import STATE_CACHE_PATH

FEED_URL_TEMPLATE = "https://raw.githubusercontent.com/mrkaktuz/outages-data/data/{region}.json"

# The feed is licensed CC BY 4.0 and must be credited in this exact form (see THIRD_PARTY_NOTICES.md).
DATA_SOURCE_URL = "https://github.com/mrkaktuz/outages-data"
DATA_ATTRIBUTION_HTML = (
    f'Данные: outages-data, <a href="{DATA_SOURCE_URL}">{DATA_SOURCE_URL}</a> '
    '(<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>), '
    "обработаны приложением"
)


class FetchWorker(QObject):
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, region: str) -> None:
        super().__init__()
        self.region = region

    def run(self) -> None:
        url = FEED_URL_TEMPLATE.format(region=self.region)
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            STATE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            STATE_CACHE_PATH.write_text(
                json.dumps({"region": self.region, "data": data}, ensure_ascii=False),
                encoding="utf-8",
            )
            self.finished.emit(data)
        except Exception as exc:
            self.failed.emit(str(exc))


def load_cached_data(region: str) -> dict | None:
    if not STATE_CACHE_PATH.exists():
        return None
    try:
        cached = json.loads(STATE_CACHE_PATH.read_text(encoding="utf-8"))
        if cached.get("region") == region and isinstance(cached.get("data"), dict):
            return cached["data"]
    except Exception:
        pass
    return None

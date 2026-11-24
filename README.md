# ⚡ Power Monitor

**English** | [Українська](README.uk.md) | [Русский](README.ru.md)

[![CI](https://github.com/Max-Woont/power-monitor/actions/workflows/ci.yml/badge.svg)](https://github.com/Max-Woont/power-monitor/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![PySide6](https://img.shields.io/badge/GUI-PySide6-41cd52)

A desktop app (**Python + PySide6**) that tracks hourly power outage schedules in Ukraine (ГПВ):
a system tray icon, a customizable floating countdown overlay, a today/tomorrow schedule popup
and native notifications.

The app interface is currently in Russian.

## Contents

- [Features](#features)
- [Overlay modes](#overlay-modes)
- [Overlay customization](#overlay-customization)
- [Quick start](#quick-start)
- [Building the `.exe`](#building-the-exe-windows)
- [Development](#development)
- [Project structure](#project-structure)
- [Data source](#data-source)
- [AI assistance](#ai-assistance)

## Features

- **Several regions:** Mykolaiv region (`off.energy.mk.ua`), Kyiv city, Kyiv, Dnipropetrovsk,
  Odesa and Zhytomyr regions.
- **Tray icon:** rounded badge with a lightning bolt, a cross or a "maybe" indicator, or a battery style.
  Click it to open a compact schedule for today and tomorrow.
- **Floating overlay (HUD):** five display modes, themes, custom colours, scaling, screen-corner anchoring,
  auto-hide, click-through and always-on-top. Every change in the settings is previewed live.
- **Notifications:** N minutes before an outage starts or ends, and when the schedule changes; quiet hours.
- **Power station hint:** a warning when the next window with power is shorter than a set threshold
  (for example, under 60 minutes for a full charge).
- **Offline cache:** if the network fails, the schedule is read from a local cache and the countdown continues.

## Overlay modes

| Mode | Shows | Good for |
|---|---|---|
| **Full** (`full`) | status, queue, large timer, next event, warning, timeline | default |
| **Compact** (`compact`) | one line: status dot, status, timer, queue (+ thin timeline) | on top of games or video |
| **Minimal** (`minimal`) | the timer with a coloured status mark | maximum free screen space |
| **Ring** (`ring`) | circular progress of the current period, timer in the centre | a widget in a screen corner |
| **Bar** (`bar`) | an N-hour timeline with hour ticks and text on top | along the top or bottom screen edge |

Switch modes in the settings, in the tray menu (**Оверлей → Режим**), from the overlay's right-click menu
or by **double-clicking** the overlay (cycles through the modes).

## Overlay customization

**Settings → "Оверлей: вид" (look)**

- Theme: dark, light, **status colour** (the background is tinted with the current state colour) or **custom**
  (pick background and text colours; text contrast is chosen automatically if left on auto).
- Accent colour (status colour by default), scale 50-250 %, window opacity and a separate background opacity
  (the background can be fully transparent), width, corner radius, border, font.
- Elements: status, queue, "next event" line, short-window warning, seconds in the timer,
  timeline and its horizon (3-24 h), timer highlight during the last N minutes.
- "Сбросить оформление" (reset look) restores the default look without moving the overlay.

**Settings → "Оверлей: поведение" (behaviour)**

- Show overlay, always on top, click-through, lock position.
- Anchor to a screen corner or edge centre with a margin, so the overlay stays in place when its size changes.
- Auto-hide: hide the overlay while power is on and the next outage is more than N minutes away.

**Mouse controls**

| Action | Result |
|---|---|
| Drag | move (snaps to screen edges; removes corner anchoring) |
| Double-click | next mode |
| Right-click | quick menu: mode, theme, scale, elements, lock |
| Ctrl + wheel | scale ±10 % |

Settings are stored in `~/.power_monitor/config.json`. Invalid values are corrected automatically on load.

## Quick start

Requires Python 3.10+.

```bash
python -m venv .venv
```

```bash
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate
```

```bash
pip install -r requirements.txt
```

```bash
python main.py
```

## Building the `.exe` (Windows)

```bash
pip install pyinstaller
```

```bash
pyinstaller --noconfirm PowerMonitor.spec
```

The result is `dist/PowerMonitor.exe`. Pushing a `v*` tag makes GitHub Actions build the exe
and attach it to the release.

## Development

```bash
pip install -r requirements-dev.txt
```

```bash
python -m pytest
```

```bash
ruff check . && ruff format --check .
```

Overlay widget tests render every mode without a display (`QT_QPA_PLATFORM=offscreen`); they are skipped
if PySide6 is unavailable. CI runs the linter and tests on Ubuntu and Windows.

## Project structure

```
power-monitor/
├── main.py                       # entry point
├── power_monitor/
│   ├── app.py                    # tray, timers, wiring
│   ├── config.py                 # AppConfig: settings, validation, saving
│   ├── models.py                 # intervals, feed parsing, schedule calculations
│   ├── providers.py              # feed download and offline cache
│   ├── overlay.py                # overlay widget (all modes)
│   ├── overlay_style.py          # palettes, formatting, geometry (no Qt)
│   ├── settings_dialog.py        # settings window with live preview
│   ├── popup.py                  # schedule popup from the tray
│   ├── notifier.py               # notifications and quiet hours
│   └── tray_icons.py             # vector tray icons
├── tests/                        # unittest/pytest
├── PowerMonitor.spec             # PyInstaller configuration
└── .github/workflows/            # CI and exe build
```

## Data source

Normalized JSON feeds from [mrkaktuz/outages-data](https://github.com/mrkaktuz/outages-data)
(CC BY 4.0). This app is not an official product of any power distribution company; always check the
original source.

## AI assistance

Parts of this project (code, tests and documentation) were developed with the help of
[Claude Code](https://claude.com/claude-code), an AI coding assistant by Anthropic.
AI-assisted commits are marked with a `Co-Authored-By` trailer in the git history.
The maintainer reviews these changes and is responsible for the project.

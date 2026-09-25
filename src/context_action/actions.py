"""
actions.py — Batch 2: the input-injection fallback tier only (tier 3 of
the Action Broker's priority list, Track B prompt section 6). UI
Automation (tier 1) and named per-app adapters (tier 2) land in Batch 3
and will be tried before this tier once they exist.

Every entry in ACTIONS is a zero-arg callable that does one OS-level
thing via pyautogui — keyboard/mouse injection, never a hard-coded pixel
coordinate as the default path. Windows-only in practice (pyautogui needs
a display); not imported by anything that doesn't need to execute.
"""

from __future__ import annotations

import pyautogui

# Moving the mouse to a screen corner aborts pyautogui mid-action — a
# manual kill switch during development. Keep this on.
pyautogui.FAILSAFE = True


def _keys(*keys: str) -> None:
    pyautogui.hotkey(*keys)


def _key(key: str) -> None:
    pyautogui.press(key)


ACTIONS = {
    "next_virtual_desktop": lambda: _keys("win", "ctrl", "right"),
    "prev_virtual_desktop": lambda: _keys("win", "ctrl", "left"),
    "browser_forward": lambda: _keys("alt", "right"),
    "browser_back": lambda: _keys("alt", "left"),
    "next_slide": lambda: _key("right"),
    "prev_slide": lambda: _key("left"),
    "advance_slide_click": lambda: _key("right"),
    "next_track": lambda: _key("nexttrack"),
    "prev_track": lambda: _key("prevtrack"),
    "play_pause": lambda: _key("playpause"),
    "click": lambda: pyautogui.click(),
    "scroll_down": lambda: pyautogui.scroll(-300),
    "scroll_up": lambda: pyautogui.scroll(300),
    "volume_down": lambda: _key("volumedown"),
    "volume_up": lambda: _key("volumeup"),
    # R3 demo action (see action_broker.RISK_LEVELS + mapping.yaml) —
    # closes the active window without checking for unsaved work, so
    # it's gated behind a second, distinct-gesture confirmation.
    "close_active_window": lambda: _keys("alt", "f4"),
}
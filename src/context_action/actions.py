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

pyautogui.FAILSAFE = True


def _keys(*keys: str) -> None:
    pyautogui.hotkey(*keys)


def _key(key: str) -> None:
    pyautogui.press(key)


def _type(text: str) -> None:
    pyautogui.typewrite(text, interval=0.02)


def _make_typer(ch: str):
    """Factory, not an inline lambda in the loop below — avoids the
    classic late-binding closure bug where every generated lambda would
    otherwise end up referencing the same final loop variable."""
    return lambda: _type(ch)


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
    "close_active_window": lambda: _keys("alt", "f4"),

    # --- Search & Launch / AirType demo path ---
    "open_windows_search": lambda: _keys("win", "s"),
    "switch_window": lambda: _keys("alt", "tab"),
    "type_space": lambda: _key("space"),
    "type_backspace": lambda: _key("backspace"),
    "type_enter": lambda: _key("enter"),
}

for _ch in "abcdefghijklmnopqrstuvwxyz":
    ACTIONS[f"type_char_{_ch}"] = _make_typer(_ch)
del _ch
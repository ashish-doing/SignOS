"""
window_detector.py — foreground app/window detection for Windows.

Read-only: the currently focused window's process name and title, plus a
best-effort fullscreen check. No writes, no side effects on the OS.
Windows-only module (pywin32).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import psutil
import win32gui
import win32process


@dataclass
class ForegroundWindow:
    hwnd: int
    process_name: str  # lowercase, e.g. "chrome.exe"; "" if undeterminable
    window_title: str
    is_fullscreen: bool


def _is_fullscreen(hwnd: int) -> bool:
    """Best-effort: window rect matches its monitor's rect. Good enough for
    Batch 1's PRESENTATION-mode gate; revisit if PowerPoint's Slide Show
    window doesn't satisfy this on your machine (some setups use a borderless
    window that's slightly inset — tell me the exact symptom and we'll add a
    title-text fallback like 'PowerPoint Slide Show')."""
    try:
        import win32api
        import win32con

        rect = win32gui.GetWindowRect(hwnd)
        monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
        monitor_rect = win32api.GetMonitorInfo(monitor)["Monitor"]
        return rect == monitor_rect
    except Exception:
        return False


def get_foreground_window() -> Optional[ForegroundWindow]:
    """Returns the currently focused window's info, or None if nothing is
    focused / detection fails outright."""
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return None

    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process_name = psutil.Process(pid).name().lower()
    except Exception:
        process_name = ""

    window_title = win32gui.GetWindowText(hwnd)

    return ForegroundWindow(
        hwnd=hwnd,
        process_name=process_name,
        window_title=window_title,
        is_fullscreen=_is_fullscreen(hwnd),
    )
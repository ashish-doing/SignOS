"""
adapters/powerpoint.py — tier 2 named per-app adapter for PowerPoint, via
its COM application object model (Track B prompt section 6: "application
object model where available" for Presentation mode). More reliable than
generic UI Automation for slide navigation. Every function returns
False/None on any failure (PowerPoint not running, not in Slide Show,
COM error, anything) so the caller falls through to the next tier —
never raises.
"""

from __future__ import annotations

from typing import Optional


def _get_active_slideshow():
    import win32com.client

    ppt = win32com.client.GetActiveObject("PowerPoint.Application")
    if ppt.SlideShowWindows.Count == 0:
        return None
    return ppt.SlideShowWindows(1)


def current_slide_index() -> Optional[int]:
    """Read-only: used for before/after verification. Returns None if
    unavailable (not in Slide Show, etc.) rather than raising."""
    try:
        window = _get_active_slideshow()
        if window is None:
            return None
        return window.View.Slide.SlideIndex
    except Exception:
        return None


def next_slide() -> bool:
    try:
        window = _get_active_slideshow()
        if window is None:
            return False
        window.View.Next()
        return True
    except Exception:
        return False


def prev_slide() -> bool:
    try:
        window = _get_active_slideshow()
        if window is None:
            return False
        window.View.Previous()
        return True
    except Exception:
        return False
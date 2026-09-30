"""
mode_resolver.py — deterministic lookup-table mode resolution from a
ForegroundWindow. No AI/LLM here by design (Track B prompt, section 5).

Five prototype modes: DESKTOP, BROWSER, PRESENTATION, MEDIA, TEXT.

TEXT is resolved via a focused-editable-control check (window_detector.
get_focused_control_type) — a global UI Automation lookup, independent
of which process owns the control. It's checked LAST, as a fallback
before DESKTOP: known process types (browser/media/presentation) still
win first, so e.g. typing into a browser's own address bar is not yet
routed to TEXT mode. That's a real limitation, not an oversight — call
it out if it matters for your demo.
"""

from __future__ import annotations

from typing import Optional

from context_action.window_detector import ForegroundWindow

MODES = ("DESKTOP", "BROWSER", "PRESENTATION", "MEDIA", "TEXT")

_BROWSER_PROCESSES = {"chrome.exe", "msedge.exe", "firefox.exe"}
_MEDIA_PROCESSES = {
    "vlc.exe",
    "wmplayer.exe",
    "spotify.exe",
    "musicbee.exe",
    "foobar2000.exe",
}
_PRESENTATION_PROCESSES = {"powerpnt.exe"}

# UIA control-type strings that count as "editable" for TEXT mode.
_EDITABLE_CONTROL_TYPES = {"Edit", "Document", "ComboBox"}

# Sentinel so tests can force a specific (or absent) focused-control-type
# result without depending on whatever's really focused on the machine
# running the tests. Default behavior (no override) does the real check.
_UNSET = object()


def resolve_mode(fg: Optional[ForegroundWindow], focused_control_type=_UNSET) -> str:
    """Resolve the current mode from a ForegroundWindow snapshot.
    `fg is None` (nothing focused / detection failed) resolves to DESKTOP,
    the safe default.

    `focused_control_type` is normally left unset, which does a real,
    live UI Automation check of whatever control currently has focus.
    Tests pass an explicit value (a UIA control-type string, or None) to
    make TEXT-mode resolution deterministic instead of depending on
    whatever happens to be focused on the machine running the tests."""
    if fg is None or not fg.process_name:
        return "DESKTOP"

    proc = fg.process_name

    if proc in _PRESENTATION_PROCESSES:
        return "PRESENTATION" if fg.is_fullscreen else "DESKTOP"

    if proc in _BROWSER_PROCESSES:
        return "BROWSER"

    if proc in _MEDIA_PROCESSES:
        return "MEDIA"

    if focused_control_type is _UNSET:
        focused_control_type = _get_focused_control_type()
    if focused_control_type in _EDITABLE_CONTROL_TYPES:
        return "TEXT"

    return "DESKTOP"


def _get_focused_control_type() -> Optional[str]:
    from context_action.window_detector import get_focused_control_type

    return get_focused_control_type()
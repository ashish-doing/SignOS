"""
mode_resolver.py — deterministic lookup-table mode resolution from a
ForegroundWindow. No AI/LLM here by design (Track B prompt, section 5).

Five prototype modes: DESKTOP, BROWSER, PRESENTATION, MEDIA, TEXT.

TEXT (a focused editable control via UI Automation) is stubbed for Batch 1:
it is never returned yet, and unmatched apps fall through to DESKTOP. Wired
properly once UIA lands in Batch 3.
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


def resolve_mode(fg: Optional[ForegroundWindow]) -> str:
    """Resolve the current mode from a ForegroundWindow snapshot.
    `fg is None` (nothing focused / detection failed) resolves to DESKTOP,
    the safe default."""
    if fg is None or not fg.process_name:
        return "DESKTOP"

    proc = fg.process_name

    if proc in _PRESENTATION_PROCESSES:
        # Only PRESENTATION while actually in Slide Show (fullscreen).
        # Editing a deck in the normal window falls through to DESKTOP for
        # now; PowerPoint gets a real adapter in Batch 3.
        return "PRESENTATION" if fg.is_fullscreen else "DESKTOP"

    if proc in _BROWSER_PROCESSES:
        return "BROWSER"

    if proc in _MEDIA_PROCESSES:
        return "MEDIA"

    # TODO(Batch 3): TEXT via UI Automation focused-control check.
    return "DESKTOP"
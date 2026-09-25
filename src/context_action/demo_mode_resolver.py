"""
demo_mode_resolver.py — Batch 1 acceptance check.

Run this, then alt-tab between a browser and PowerPoint (put PowerPoint
into Slide Show / F5) on the same machine. It prints a new line every time
the resolved mode changes.

    python -m context_action.demo_mode_resolver

Expected shape (your app/title text will differ):
    [12:03:41] mode=DESKTOP      app=explorer.exe       title=
    [12:03:44] mode=BROWSER      app=chrome.exe         title=New Tab - Google Chrome
    [12:03:51] mode=PRESENTATION app=powerpnt.exe       title=PowerPoint Slide Show
    [12:03:58] mode=BROWSER      app=chrome.exe         title=New Tab - Google Chrome

Ctrl+C to stop.
"""

from __future__ import annotations

import time
from datetime import datetime

from context_action.mode_resolver import resolve_mode
from context_action.window_detector import get_foreground_window

POLL_INTERVAL_SECONDS = 0.5


def main() -> None:
    print("Watching foreground window for mode changes. Ctrl+C to stop.\n")
    last_mode = None
    try:
        while True:
            fg = get_foreground_window()
            mode = resolve_mode(fg)
            if mode != last_mode:
                ts = datetime.now().strftime("%H:%M:%S")
                app = fg.process_name if fg else "?"
                title = fg.window_title if fg else ""
                print(f"[{ts}] mode={mode:<13} app={app:<22} title={title}")
                last_mode = mode
            time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
"""
dashboard.py — SignOS Mission Control. Read-only web UI: live camera feed
(from run_perception.py's MJPEG stream), current mode/context, event
timeline, a self-documenting gesture library (built live from
config/mapping.yaml so it can never go stale), and a routine/memory panel
(OBSERVE + SUGGEST level only — see routine_engine.py docstring for what
is and isn't implemented). This process never writes to the intent bus
and never executes actions — pure observer + a MemoryStore reader.

Run in a separate terminal alongside run_perception.py and main_loop.py:
    python -m context_action.dashboard
Then open http://localhost:8420
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

from context_action.intent_bus import IntentBusReader, STATE_DIR
from context_action.mapping import MAPPING_PATH
from context_action.memory_store import MemoryStore, bucket_index
from context_action.mode_resolver import resolve_mode
from context_action.routine_engine import current_suggestion
from context_action.window_detector import get_foreground_window

ASSETS_DIR = Path(__file__).resolve().parent / "dashboard_assets"
HISTORY_MAX = 40

GESTURE_DESCRIPTIONS = {
    "POINT": "Index finger extended, others curled. Cursor follows the index knuckle.",
    "PINCH": "Touch thumb and index tip together, then release quickly (< 450ms). One click.",
    "PINCH_HOLD_STILL": "Pinch and hold still for ~450ms without moving. Right-click / context action.",
    "PINCH_HOLD_MOVE": "Pinch, then move your hand while still pinched. Drag.",
    "SCROLL_V": "Index + middle finger extended, others curled, move hand up/down.",
    "SCROLL_H": "Index + middle finger extended, others curled, move hand left/right.",
    "SWIPE_LEFT": "Open palm, move hand left quickly (fast, short motion).",
    "SWIPE_RIGHT": "Open palm, move hand right quickly (fast, short motion).",
    "PALM_HOLD": "Open palm held still in place for ~800ms.",
    "CLUTCH_ON / CLUTCH_OFF": "Make a fist and hold for ~700ms. Toggles pointer control on/off — "
                              "use this so ordinary signing doesn't move the cursor.",
    "DOUBLE_PINCH": "[PLANNED — not yet triggerable live] no detector currently emits this; only "
                    "present in mapping.yaml as a placeholder for the R3 confirmation demo.",
}

_lock = threading.Lock()
_state = {"mode": "DESKTOP", "app": "", "title": "", "last_intent": "-",
          "last_confidence": 0.0, "history": []}

_memory = MemoryStore()


def _poller() -> None:
    # Own offset file — must NOT collide with main_loop.py's reader, which
    # uses the default offset path. Two independent IntentBusReader
    # instances pointed at the same offset file race and silently drop
    # intents for whichever one loses the write.
    reader = IntentBusReader(offset_path=STATE_DIR / "intent_bus_dashboard.offset")
    while True:
        for intent in reader.poll():
            fg = get_foreground_window()
            mode = resolve_mode(fg)
            with _lock:
                _state["mode"] = mode
                _state["app"] = fg.process_name if fg else "?"
                _state["title"] = fg.window_title if fg else ""
                if intent.is_actionable():
                    _state["last_intent"] = intent.intent
                    _state["last_confidence"] = round(intent.confidence, 2)
                    _state["history"].append({
                        "ts": intent.ts, "intent": intent.intent, "kind": intent.kind,
                        "mode": mode, "confidence": round(intent.confidence, 2),
                    })
                    _state["history"] = _state["history"][-HISTORY_MAX:]
        time.sleep(0.1)


def _mapping_table() -> dict:
    with open(MAPPING_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/state":
            with _lock:
                self._json(_state)
            return
        if self.path == "/api/gestures":
            self._json({"descriptions": GESTURE_DESCRIPTIONS, "mapping": _mapping_table()})
            return
        if self.path == "/api/routine":
            with _lock:
                actual_mode = _state["mode"]
            sugg = current_suggestion(_memory, actual_mode)
            self._json({
                "suggestion": sugg,
                "total_observations": _memory.total_events(),
                "daily": _memory.recent_daily_summary(),
                "current_bucket": bucket_index(datetime.now()),
                "day_of_week": datetime.now().weekday(),
            })
            return
        if self.path in ("/", "/index.html"):
            page = (ASSETS_DIR / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)
            return
        self.send_response(404)
        self.end_headers()


def main() -> None:
    threading.Thread(target=_poller, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", 8420), Handler)
    print("SignOS Mission Control: http://localhost:8420  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
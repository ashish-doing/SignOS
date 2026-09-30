"""
main_loop.py — Batch 2 acceptance script. Wires everything end-to-end:

    intent bus -> mode resolver -> mapping table -> Action Broker (tier 3)

Run this in one terminal, then in a second terminal (same venv) run the
synthetic intent generator while a target app is focused:

    python -m context_action.main_loop
    (second terminal)
    python -m context_action.synthetic_intent_gen --enable --only SWIPE_RIGHT --interval 2

Expected: focus a browser, a SWIPE_RIGHT intent moves it forward. Focus
PowerPoint in Slide Show, the same SWIPE_RIGHT advances the slide. Same
intent, different real result, depending on what's focused.

Ctrl+C to stop (stop both terminals).
"""

from __future__ import annotations

import time

from context_action.action_broker import ActionBroker
from context_action.intent_bus import IntentBusReader
from context_action.mapping import MappingTable
from context_action.mode_resolver import resolve_mode
from context_action.window_detector import get_foreground_window

from context_action.memory_store import MemoryStore

POLL_INTERVAL_SECONDS = 0.1

_SCROLL_FLIP = {"scroll_down": "scroll_up", "scroll_up": "scroll_down",
                "volume_down": "volume_up", "volume_up": "volume_down"}
_SCROLL_AXIS = {"SCROLL_V": "y", "SCROLL_H": "x"}
_DIRECTION_DEADZONE = 0.004   # camera-normalized units, ignore sub-pixel jitter
_STALE_S = 0.5                # gap this large = new scroll stream, don't trust the old anchor


def _resolve_scroll_action(intent, base_action, last_ptr, now):
    axis = _SCROLL_AXIS.get(intent.intent)
    if not axis or base_action not in _SCROLL_FLIP or not intent.pointer:
        return base_action
    cur = (intent.pointer["x"], intent.pointer["y"])
    prev = last_ptr.get(intent.intent)
    last_ptr[intent.intent] = (*cur, now)
    if prev is None or now - prev[2] > _STALE_S:
        return None   # first frame of a new scroll stream — no motion measured yet, don't fire
    delta = (cur[0] - prev[0]) if axis == "x" else (cur[1] - prev[1])
    if abs(delta) < _DIRECTION_DEADZONE:
        return None   # hand essentially static this frame — don't scroll on nothing
    wants_down = delta > 0
    return base_action if wants_down == base_action.endswith("_down") else _SCROLL_FLIP[base_action]


def main() -> None:
    reader = IntentBusReader()
    mapping = MappingTable()
    broker = ActionBroker()
    last_ptr: dict = {}
    store = MemoryStore()

    print("Track B main loop running. Ctrl+C to stop.")
    print(f"Reading intents from: {reader.bus_path}")
    print(f"Mapping table: {mapping.path}\n")

    try:
        while True:
            for intent in reader.poll():
                if not intent.is_actionable():
                    continue
                fg = get_foreground_window()
                mode = resolve_mode(fg)

                broker.check_confirmation(intent.intent)

                action = mapping.resolve(intent.intent, mode)
                if action and intent.intent in _SCROLL_AXIS:
                    action = _resolve_scroll_action(intent, action, last_ptr, time.time())
                    if action is None:
                        continue  # no net motion this frame — skip silently, no log spam
                app = fg.process_name if fg else "?"
                if action is None:
                    print(f"{intent.intent:<18} mode={mode:<12} app={app:<18} -> no mapping, ignored")
                    continue
                print(f"{intent.intent:<18} mode={mode:<12} app={app:<18} -> {action}")
                if broker.execute(action, intent.intent):
                    store.log_event(mode, app, intent.intent, action)
            time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
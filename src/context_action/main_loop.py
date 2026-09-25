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

POLL_INTERVAL_SECONDS = 0.1


def main() -> None:
    reader = IntentBusReader()
    mapping = MappingTable()
    broker = ActionBroker()

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

                # Every actionable intent gets a chance to confirm a
                # pending R3 action first (Batch 3: risk gating).
                broker.check_confirmation(intent.intent)

                action = mapping.resolve(intent.intent, mode)
                app = fg.process_name if fg else "?"
                if action is None:
                    print(f"{intent.intent:<18} mode={mode:<12} app={app:<18} -> no mapping, ignored")
                    continue
                print(f"{intent.intent:<18} mode={mode:<12} app={app:<18} -> {action}")
                broker.execute(action, intent.intent)
            time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
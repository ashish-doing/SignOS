"""
synthetic_intent_gen.py — appends synthetic signos.intent.v1 lines to
signos/state/intent_bus.jsonl on a timer, so Track B can be built and
tested before Track A produces real gesture/ISL data.

GATED: requires --enable to run at all, and is never imported or
auto-started by any other Track B module. Do not leave this running during
a real demo — it will collide with real Track A output on the same file.

    python -m context_action.synthetic_intent_gen --enable
    python -m context_action.synthetic_intent_gen --enable --only SWIPE_RIGHT --interval 1 --count 5
    python -m context_action.synthetic_intent_gen --enable --spell NOTEPAD --search-first --lead-in 4
"""

from __future__ import annotations

import argparse
import json
import random
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

STATE_DIR = Path(__file__).resolve().parents[2] / "state"
INTENT_BUS_PATH = STATE_DIR / "intent_bus.jsonl"

_INTENTS = [
    "POINT",
    "PINCH",
    "DOUBLE_PINCH",
    "PINCH_HOLD_MOVE",
    "PINCH_HOLD_STILL",
    "SCROLL_V",
    "SCROLL_H",
    "SWIPE_LEFT",
    "SWIPE_RIGHT",
    "PALM_HOLD",
    "CLUTCH_ON",
    "CLUTCH_OFF",
]


def make_intent(name: Optional[str] = None) -> dict:
    intent = name or random.choice(_INTENTS)
    has_pointer = intent in {"POINT", "PINCH_HOLD_MOVE"}
    ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return {
        "schema": "signos.intent.v1",
        "ts": ts,
        "id": str(uuid.uuid4()),
        "kind": "isl" if intent.startswith("ISL_") else "gesture",
        "intent": intent,
        "confidence": round(random.uniform(0.75, 0.99), 2),
        "pointer": {"x": round(random.random(), 3), "y": round(random.random(), 3)} if has_pointer else None,
        "hand": random.choice(["left", "right"]),
        "raw_duration_ms": random.randint(80, 400),
        "source_fps": 30.0,
    }


def _spell_sequence(word: str, search_first: bool) -> list:
    """Builds the ISL_<LETTER> intent sequence for --spell. Only a-z are
    supported (fingerspelling placeholder — see mapping.yaml note)."""
    sequence = []
    if search_first:
        sequence.append("ISL_SEARCH")
    for ch in word:
        if ch == " ":
            sequence.append("ISL_SPACE")
        elif ch.isalpha():
            sequence.append(f"ISL_{ch.upper()}")
        else:
            raise ValueError(f"--spell only supports letters and spaces, got {ch!r} in {word!r}")
    sequence.append("ISL_ENTER")
    return sequence


def run(interval_seconds: float, only: Optional[str], count: Optional[int]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Appending synthetic intents to {INTENT_BUS_PATH} every {interval_seconds}s. Ctrl+C to stop.")
    n = 0
    try:
        with open(INTENT_BUS_PATH, "a", encoding="utf-8") as f:
            while count is None or n < count:
                record = make_intent(only)
                f.write(json.dumps(record) + "\n")
                f.flush()
                print(f"  wrote {record['intent']}")
                n += 1
                if count is None or n < count:
                    time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("\nStopped.")


def run_spell(word: str, search_first: bool, interval_seconds: float, lead_in_seconds: float) -> None:
    """Demo convenience: spells `word` letter-by-letter as ISL_<LETTER>
    intents, ending with ISL_ENTER — the 'type with signs, launch an app'
    demo path. Give yourself `lead_in_seconds` to switch focus (e.g. to
    let Windows Search actually open) before the first letter fires."""
    sequence = _spell_sequence(word, search_first)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Will spell {word!r} as: {' -> '.join(sequence)}")
    if lead_in_seconds > 0:
        print(f"Starting in {lead_in_seconds:.0f}s — switch focus now if needed...")
        time.sleep(lead_in_seconds)
    try:
        with open(INTENT_BUS_PATH, "a", encoding="utf-8") as f:
            for name in sequence:
                record = make_intent(name)
                f.write(json.dumps(record) + "\n")
                f.flush()
                print(f"  wrote {record['intent']}")
                time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("\nStopped.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable", action="store_true", required=True,
                         help="Required — prevents this from starting by accident.")
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between synthetic intents.")
    parser.add_argument("--only", type=str, default=None, help="Always emit this one intent name instead of random.")
    parser.add_argument("--count", type=int, default=None, help="Stop after N intents (default: until Ctrl+C).")
    parser.add_argument("--spell", type=str, default=None,
                         help="Demo mode: spell this word as ISL_<LETTER> intents ending in ISL_ENTER "
                              "(letters and spaces only). Ignores --only/--count.")
    parser.add_argument("--search-first", action="store_true",
                         help="With --spell: fire ISL_SEARCH before the letters, to open Windows Search first.")
    parser.add_argument("--lead-in", type=float, default=4.0,
                         help="With --spell: seconds to wait before the first letter, so you can switch focus.")
    args = parser.parse_args()

    if args.spell:
        run_spell(args.spell, args.search_first, args.interval, args.lead_in)
    else:
        run(args.interval, args.only, args.count)


if __name__ == "__main__":
    main()
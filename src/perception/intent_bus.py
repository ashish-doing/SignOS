"""Intent bus writer + validator. Schema signos.intent.v1 is a fixed contract with Track B."""
from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "signos.intent.v1"
# <repo>/signos/src/perception/intent_bus.py -> <repo>/signos/state/
DEFAULT_BUS_PATH = Path(__file__).resolve().parents[2] / "state" / "intent_bus.jsonl"

GESTURE_INTENTS = {
    "POINT", "PINCH", "DOUBLE_PINCH", "PINCH_HOLD_MOVE", "PINCH_HOLD_STILL",
    "SCROLL_V", "SCROLL_H", "SWIPE_LEFT", "SWIPE_RIGHT", "PALM_HOLD",
    "CLUTCH_ON", "CLUTCH_OFF", "NONE", "TRANSITION",
}
SHARED_INTENTS = {"NONE", "TRANSITION"}  # allowed under both kinds
POINTER_INTENTS = {"POINT", "PINCH_HOLD_MOVE", "SCROLL_V", "SCROLL_H"}
HANDS = {"left", "right", "two"}
ISL_RE = re.compile(r"^ISL_[A-Z0-9_]+$")
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
REQUIRED = {
    "schema", "ts", "id", "kind", "intent", "confidence",
    "pointer", "hand", "raw_duration_ms", "source_fps",
}


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def now_ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def make_intent(kind, intent, confidence, pointer=None, hand="right",
                raw_duration_ms=0, source_fps=0.0) -> dict:
    """Build an intent dict. Does not validate; the writer does."""
    return {
        "schema": SCHEMA,
        "ts": now_ts(),
        "id": str(uuid.uuid4()),
        "kind": kind,
        "intent": intent,
        "confidence": confidence,
        "pointer": pointer,
        "hand": hand,
        "raw_duration_ms": raw_duration_ms,
        "source_fps": source_fps,
    }


def validate_intent(obj) -> None:
    """Raise ValueError if obj violates signos.intent.v1."""
    if not isinstance(obj, dict):
        raise ValueError("intent must be an object")
    missing, extra = REQUIRED - obj.keys(), obj.keys() - REQUIRED
    if missing:
        raise ValueError(f"missing fields: {sorted(missing)}")
    if extra:
        raise ValueError(f"unexpected fields: {sorted(extra)}")
    if obj["schema"] != SCHEMA:
        raise ValueError(f"schema must be {SCHEMA}")
    if not (isinstance(obj["ts"], str) and TS_RE.match(obj["ts"])):
        raise ValueError("ts must be UTC ISO-8601 with ms, e.g. 2026-09-24T10:15:32.123Z")
    try:
        ok = uuid.UUID(obj["id"]).version == 4
    except (ValueError, AttributeError, TypeError):
        ok = False
    if not ok:
        raise ValueError("id must be a uuid4 string")

    kind, intent = obj["kind"], obj["intent"]
    if kind == "gesture":
        if intent not in GESTURE_INTENTS:
            raise ValueError(f"unknown gesture intent: {intent!r}")
    elif kind == "isl":
        if not (intent in SHARED_INTENTS or (isinstance(intent, str) and ISL_RE.match(intent))):
            raise ValueError(f"isl intent must be ISL_<NAME>, NONE or TRANSITION: {intent!r}")
    else:
        raise ValueError("kind must be 'gesture' or 'isl'")

    if not (_is_num(obj["confidence"]) and 0.0 <= obj["confidence"] <= 1.0):
        raise ValueError("confidence must be a number in 0-1")
    if obj["hand"] not in HANDS:
        raise ValueError("hand must be left|right|two")
    rd = obj["raw_duration_ms"]
    if not (isinstance(rd, int) and not isinstance(rd, bool) and rd >= 0):
        raise ValueError("raw_duration_ms must be an int >= 0")
    if not (_is_num(obj["source_fps"]) and obj["source_fps"] >= 0):
        raise ValueError("source_fps must be a number >= 0")

    ptr = obj["pointer"]
    if intent in POINTER_INTENTS:
        if not (isinstance(ptr, dict) and set(ptr) == {"x", "y"}
                and all(_is_num(ptr[k]) and 0.0 <= ptr[k] <= 1.0 for k in ("x", "y"))):
            raise ValueError(f"{intent} needs pointer {{x,y}} in 0-1")
    elif ptr is not None:
        raise ValueError(f"{intent} must have pointer null")


class IntentBusWriter:
    """Append-only JSONL writer. flush + fsync after every line (Track B tails live)."""

    def __init__(self, path=None):
        self.path = Path(path) if path else DEFAULT_BUS_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = open(self.path, "ab")
        self._lock = threading.Lock()

    def write(self, obj: dict) -> dict:
        validate_intent(obj)
        line = (json.dumps(obj, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
        with self._lock:
            self._f.write(line)
            self._f.flush()
            os.fsync(self._f.fileno())
        return obj

    def emit(self, kind, intent, confidence, **kw) -> dict:
        return self.write(make_intent(kind, intent, confidence, **kw))

    def close(self) -> None:
        with self._lock:
            if not self._f.closed:
                self._f.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
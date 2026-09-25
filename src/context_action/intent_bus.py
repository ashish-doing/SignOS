"""
intent_bus.py — Track B's read-only tailer for signos/state/intent_bus.jsonl.

Track A appends JSON lines to this file; we never write to it. We tail from
a saved byte offset (persisted to intent_bus.offset) so restarts don't
re-process old lines, and a line that fails to parse is treated as a
transient partial write — held back and retried next poll, not raised as
an error.

Schema (fixed — do not modify):
    signos.intent.v1
See the Track B prompt, section 2, for the full field list.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

STATE_DIR = Path(__file__).resolve().parents[2] / "state"
INTENT_BUS_PATH = STATE_DIR / "intent_bus.jsonl"
OFFSET_PATH = STATE_DIR / "intent_bus.offset"

EXPECTED_SCHEMA = "signos.intent.v1"


@dataclass
class Intent:
    schema: str
    ts: str
    id: str
    kind: str
    intent: str
    confidence: float
    pointer: Optional[dict]
    hand: str
    raw_duration_ms: int
    source_fps: float

    @classmethod
    def from_dict(cls, d: dict) -> "Intent":
        return cls(
            schema=d.get("schema", ""),
            ts=d.get("ts", ""),
            id=d.get("id", ""),
            kind=d.get("kind", ""),
            intent=d.get("intent", "NONE"),
            confidence=float(d.get("confidence", 0.0)),
            pointer=d.get("pointer"),
            hand=d.get("hand", ""),
            raw_duration_ms=int(d.get("raw_duration_ms", 0)),
            source_fps=float(d.get("source_fps", 0.0)),
        )

    def is_actionable(self) -> bool:
        """NONE/TRANSITION exist for Track A's own state machine — ignore
        them for action purposes (still loggable at debug level if wanted)."""
        return self.intent not in ("NONE", "TRANSITION")


class IntentBusReader:
    """Tails intent_bus.jsonl from a persisted byte offset.

    Usage:
        reader = IntentBusReader()
        while True:
            for intent in reader.poll():
                handle(intent)
            time.sleep(0.05)
    """

    def __init__(self, bus_path: Path = INTENT_BUS_PATH, offset_path: Path = OFFSET_PATH):
        self.bus_path = bus_path
        self.offset_path = offset_path
        self._offset = self._load_offset()

    def _load_offset(self) -> int:
        if self.offset_path.exists():
            try:
                return int(self.offset_path.read_text().strip())
            except (ValueError, OSError):
                return 0
        return 0

    def _save_offset(self, offset: int) -> None:
        self.offset_path.parent.mkdir(parents=True, exist_ok=True)
        self.offset_path.write_text(str(offset))

    def poll(self) -> Iterator[Intent]:
        if not self.bus_path.exists():
            return

        size = self.bus_path.stat().st_size
        if size < self._offset:
            # File was truncated/rotated underneath us — start over rather
            # than error.
            self._offset = 0
            self._save_offset(0)

        with open(self.bus_path, "rb") as f:
            f.seek(self._offset)
            data = f.read()

        if not data:
            return

        if data.endswith(b"\n"):
            lines = data.split(b"\n")[:-1]
            partial_len = 0
        else:
            parts = data.split(b"\n")
            lines = parts[:-1]
            partial_len = len(parts[-1])

        consumed = len(data) - partial_len

        for raw in lines:
            if not raw.strip():
                continue
            try:
                d = json.loads(raw.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                # A malformed but newline-terminated line is unexpected;
                # skip it rather than crash the tailer.
                continue
            if d.get("schema") != EXPECTED_SCHEMA:
                continue
            yield Intent.from_dict(d)

        self._offset += consumed
        self._save_offset(self._offset)
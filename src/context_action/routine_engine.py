"""
routine_engine.py — OBSERVE + SUGGEST level only. See module docstring
context in memory_store.py and this file's usage in dashboard.py for what
is and isn't implemented (no ASSIST/AUTO — nothing here executes anything).
"""
from __future__ import annotations

from datetime import datetime

from context_action.memory_store import MemoryStore, bucket_index

MIN_OBSERVATIONS = 5
CONFIDENCE_THRESHOLD = 0.6


def current_suggestion(store: MemoryStore, actual_mode: str, now: datetime | None = None) -> dict | None:
    now = now or datetime.now()
    counts = store.mode_counts_for_bucket(now.weekday(), bucket_index(now))
    total = sum(counts.values())
    if total < MIN_OBSERVATIONS:
        return None
    top_mode, top_n = max(counts.items(), key=lambda kv: kv[1])
    confidence = top_n / total
    if confidence < CONFIDENCE_THRESHOLD or top_mode == actual_mode:
        return None
    return {"suggested_mode": top_mode, "confidence": round(confidence, 2), "observations": total}
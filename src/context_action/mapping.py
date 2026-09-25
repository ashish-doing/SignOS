"""
mapping.py — loads the gesture-to-action mapping table (config/mapping.yaml,
Track B prompt section 5) and resolves (intent, mode) -> action name or
None. Config-driven by design: retargeting SWIPE_RIGHT in BROWSER mode is
a YAML edit, not a code change.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

MAPPING_PATH = Path(__file__).resolve().parents[2] / "config" / "mapping.yaml"


class MappingTable:
    def __init__(self, path: Path = MAPPING_PATH):
        self.path = path
        self._table: dict = {}
        self.reload()

    def reload(self) -> None:
        with open(self.path, "r", encoding="utf-8") as f:
            self._table = yaml.safe_load(f) or {}

    def resolve(self, intent: str, mode: str) -> Optional[str]:
        """Returns the action name for this (intent, mode) pair, or None
        if there's no mapping (unknown intent, or an explicit `null` in
        the YAML for that mode — both are "no action", not errors)."""
        modes = self._table.get(intent)
        if not modes:
            return None
        return modes.get(mode)
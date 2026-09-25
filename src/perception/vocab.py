from __future__ import annotations

import json
import re
from pathlib import Path

VOCAB_PATH = Path(__file__).resolve().parents[2] / "docs" / "isl_vocab.json"
NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def confirmed_signs(path=VOCAB_PATH) -> list:
    signs = json.loads(Path(path).read_text(encoding="utf-8"))["signs"]
    return [s["name"] for s in signs if s.get("confirmed") and s.get("source") and NAME_RE.match(s["name"])]
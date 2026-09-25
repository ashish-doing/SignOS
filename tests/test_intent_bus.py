import json
import os

import pytest

from src.perception import intent_bus as ib


def _mk(**kw):
    base = dict(kind="gesture", intent="NONE", confidence=0.0)
    base.update(kw)
    return ib.make_intent(**base)


def test_valid_none_roundtrip(tmp_path):
    p = tmp_path / "bus.jsonl"
    with ib.IntentBusWriter(p) as bus:
        bus.write(_mk())
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])
    ib.validate_intent(obj)
    assert obj["schema"] == "signos.intent.v1" and obj["pointer"] is None


def test_fsync_called_per_write(tmp_path, monkeypatch):
    calls, real = [], os.fsync
    monkeypatch.setattr(ib.os, "fsync", lambda fd: (calls.append(fd), real(fd))[1])
    with ib.IntentBusWriter(tmp_path / "b.jsonl") as bus:
        for _ in range(3):
            bus.write(_mk())
    assert len(calls) == 3


def test_line_visible_before_close(tmp_path):
    p = tmp_path / "b.jsonl"
    bus = ib.IntentBusWriter(p)
    bus.write(_mk())
    assert len(p.read_text(encoding="utf-8").splitlines()) == 1  # a tailer would see it now
    bus.close()


INVALID = [
    ("bad_intent", lambda o: o.update(intent="CLICK")),
    ("conf_high", lambda o: o.update(confidence=1.5)),
    ("conf_bool", lambda o: o.update(confidence=True)),
    ("bad_hand", lambda o: o.update(hand="middle")),
    ("isl_in_gesture", lambda o: o.update(intent="ISL_COPY")),
    ("extra_field", lambda o: o.update(foo=1)),
    ("bad_ts", lambda o: o.update(ts="2026-09-24 10:15:32")),
    ("bad_uuid", lambda o: o.update(id="not-a-uuid")),
    ("bad_schema", lambda o: o.update(schema="v2")),
    ("neg_duration", lambda o: o.update(raw_duration_ms=-1)),
    ("pointer_on_none", lambda o: o.update(pointer={"x": 0.5, "y": 0.5})),
    ("missing_field", lambda o: o.pop("hand")),
]


@pytest.mark.parametrize("name,mutate", INVALID, ids=[n for n, _ in INVALID])
def test_invalid_rejected(name, mutate):
    obj = _mk()
    mutate(obj)
    with pytest.raises(ValueError):
        ib.validate_intent(obj)


def test_pointer_intent_requires_pointer():
    with pytest.raises(ValueError):
        ib.validate_intent(ib.make_intent("gesture", "POINT", 0.9))


def test_pointer_out_of_range():
    with pytest.raises(ValueError):
        ib.validate_intent(ib.make_intent("gesture", "POINT", 0.9, pointer={"x": 1.2, "y": 0.5}))


def test_valid_point():
    ib.validate_intent(ib.make_intent("gesture", "POINT", 0.9, pointer={"x": 0.4, "y": 0.6}))


def test_valid_isl():
    ib.validate_intent(ib.make_intent("isl", "ISL_COPY", 0.9))
from pathlib import Path

from context_action.mapping import MappingTable

MAPPING_PATH = Path(__file__).resolve().parents[1] / "config" / "mapping.yaml"


def _table():
    return MappingTable(MAPPING_PATH)


def test_swipe_right_differs_by_mode():
    table = _table()
    assert table.resolve("SWIPE_RIGHT", "DESKTOP") == "next_virtual_desktop"
    assert table.resolve("SWIPE_RIGHT", "BROWSER") == "browser_forward"
    assert table.resolve("SWIPE_RIGHT", "PRESENTATION") == "next_slide"
    assert table.resolve("SWIPE_RIGHT", "MEDIA") == "next_track"


def test_swipe_right_null_in_text_mode_is_none():
    assert _table().resolve("SWIPE_RIGHT", "TEXT") is None


def test_pinch_differs_by_mode():
    table = _table()
    assert table.resolve("PINCH", "PRESENTATION") == "advance_slide_click"
    assert table.resolve("PINCH", "MEDIA") == "play_pause"
    assert table.resolve("PINCH", "DESKTOP") == "click"


def test_unknown_intent_returns_none():
    assert _table().resolve("NOT_A_REAL_INTENT", "DESKTOP") is None


def test_unknown_mode_returns_none():
    assert _table().resolve("SWIPE_RIGHT", "NOT_A_REAL_MODE") is None
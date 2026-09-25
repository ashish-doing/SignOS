from context_action.mode_resolver import resolve_mode
from context_action.window_detector import ForegroundWindow


def _fg(process_name, title="", fullscreen=False):
    return ForegroundWindow(hwnd=1, process_name=process_name, window_title=title, is_fullscreen=fullscreen)


def test_none_defaults_to_desktop():
    assert resolve_mode(None) == "DESKTOP"


def test_browser():
    assert resolve_mode(_fg("chrome.exe")) == "BROWSER"
    assert resolve_mode(_fg("msedge.exe")) == "BROWSER"


def test_presentation_requires_fullscreen():
    assert resolve_mode(_fg("powerpnt.exe", "Deck.pptx - PowerPoint", fullscreen=False)) == "DESKTOP"
    assert resolve_mode(_fg("powerpnt.exe", "PowerPoint Slide Show", fullscreen=True)) == "PRESENTATION"


def test_media():
    assert resolve_mode(_fg("spotify.exe")) == "MEDIA"
    assert resolve_mode(_fg("vlc.exe")) == "MEDIA"


def test_unknown_app_falls_back_to_desktop():
    assert resolve_mode(_fg("notepad.exe")) == "DESKTOP"
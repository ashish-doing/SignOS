"""
uia_actions.py — tier 1 of the Action Broker: generic Windows UI
Automation semantic actions (InvokePattern, etc.) against whatever
control actually exists in the focused window — no app-specific
hardcoding beyond "find a control by role + name" (Track B prompt
section 6, tier 1). Every function returns False on any failure —
control not found, backend error, anything — so the caller falls
through to the next tier. Never raises, never uses hard-coded pixel
coordinates.
"""

from __future__ import annotations


def _invoke_named_button(hwnd: int, name: str) -> bool:
    try:
        from pywinauto import Desktop

        window = Desktop(backend="uia").window(handle=hwnd)
        btn = window.child_window(title=name, control_type="Button")
        if not btn.exists(timeout=0.5):
            return False
        btn.invoke()
        return True
    except Exception:
        return False


def browser_back(hwnd: int) -> bool:
    return _invoke_named_button(hwnd, "Back")


def browser_forward(hwnd: int) -> bool:
    return _invoke_named_button(hwnd, "Forward")
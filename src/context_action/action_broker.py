"""
action_broker.py — the single execution point for every resolved action
(Track B prompt section 6). Nothing else should call ACTIONS,
uia_actions, or an adapter directly.

Batch 3 adds:
  - tier 1 (generic UI Automation) and tier 2 (named per-app adapters),
    tried in priority order before tier 3 (input-injection fallback,
    Batch 2)
  - post-execution verification where a reliable before/after check
    exists (currently: PowerPoint slide navigation, via slide index)
  - risk levels R0-R3 (Track B prompt section 6 / blueprint section 11):
    R0/R1 fire immediately, R2 fires immediately but logs prominently,
    R3 requires a second, DISTINCT gesture (never the same one twice)
    within CONFIRM_WINDOW_SECONDS before executing

Imports needed only for tier 1/2/3 execution are deliberately lazy
(inside _run_tiers) so this module — and the R3 risk-gating logic
specifically — can be imported and unit-tested without
pywin32/pyautogui/pywinauto installed.
"""

from __future__ import annotations

import time
from typing import Optional, Tuple

# --- Risk levels (Track B prompt section 6 / blueprint section 11) ---
# R0: hover/scroll/inspect            — fire immediately
# R1: click/pause/navigate            — fire immediately
# R2: close window/change setting     — fire immediately, log prominently
# R3: delete/bulk operation           — needs a second, distinct-gesture
#                                        confirmation before executing
RISK_LEVELS = {
    "scroll_down": "R0",
    "scroll_up": "R0",
    "click": "R0",
    "next_virtual_desktop": "R1",
    "prev_virtual_desktop": "R1",
    "browser_forward": "R1",
    "browser_back": "R1",
    "next_slide": "R1",
    "prev_slide": "R1",
    "advance_slide_click": "R1",
    "next_track": "R1",
    "prev_track": "R1",
    "play_pause": "R1",
    "volume_up": "R1",
    "volume_down": "R1",
    # Demo-only R3 action for Batch 3's acceptance check — see mapping.yaml
    # (DOUBLE_PINCH -> close_active_window, DESKTOP mode only). Closes the
    # active window (Alt+F4) without checking for unsaved work, so it's
    # gated the same way the blueprint requires for "close without saving".
    "close_active_window": "R3",
}
DEFAULT_RISK = "R1"

CONFIRM_WINDOW_SECONDS = 5.0


class ActionBroker:
    def __init__(self) -> None:
        # (action_name, arming_intent, armed_at) or None
        self._pending_r3: Optional[Tuple[str, str, float]] = None

    def check_confirmation(self, intent_name: str) -> bool:
        """Call this for every actionable intent, before resolving its
        own mapped action. If an R3 action is currently armed and this
        intent is a DIFFERENT gesture than the one that armed it, this
        confirms and executes the pending action (Track B prompt section
        6: destructive actions "require a second, explicitly different
        gesture/intent ... never the same intent twice"). Returns True
        if this intent was consumed as a confirmation."""
        if not self._pending_r3:
            return False
        action_name, arming_intent, armed_at = self._pending_r3
        if time.time() - armed_at > CONFIRM_WINDOW_SECONDS:
            print(f"  [broker] R3 confirmation window expired for {action_name!r} — disarming")
            self._pending_r3 = None
            return False
        if intent_name == arming_intent:
            return False  # same gesture repeated is not a confirmation
        print(
            f"  [broker] R3 CONFIRMED: {arming_intent!r} armed {action_name!r}, "
            f"{intent_name!r} confirmed it (distinct gesture) — executing"
        )
        self._pending_r3 = None
        self._run_tiers(action_name)
        return True

    def execute(self, action_name: str, source_intent: str = "") -> bool:
        """Executes action_name, gated by its risk level. Returns True
        only if something actually ran on THIS call — an R3 action being
        armed or blocked returns False even though the broker did
        something (logged it); confirmation and real execution happen on
        a later, distinct intent via check_confirmation()."""
        risk = RISK_LEVELS.get(action_name, DEFAULT_RISK)

        if risk == "R3":
            if (
                self._pending_r3
                and self._pending_r3[0] == action_name
                and self._pending_r3[1] == source_intent
            ):
                print(
                    f"  [broker] R3 BLOCKED: {action_name!r} still armed — same gesture "
                    f"({source_intent!r}) repeated, need a DIFFERENT gesture to confirm"
                )
                return False
            print(
                f"  [broker] R3 ARMED: {action_name!r} needs a second, DISTINCT gesture "
                f"within {CONFIRM_WINDOW_SECONDS:.0f}s to confirm (armed by {source_intent!r})"
            )
            self._pending_r3 = (action_name, source_intent, time.time())
            return False

        if risk == "R2":
            print(f"  [broker] R2 ACTION (logged prominently): {action_name}")

        return self._run_tiers(action_name)

    def _run_tiers(self, action_name: str) -> bool:
        from context_action.window_detector import get_foreground_window
        from context_action.actions import ACTIONS
        from context_action import uia_actions
        from context_action.adapters import powerpoint as ppt_adapter

        fg = get_foreground_window()

        # Tier 1 — generic UI Automation (InvokePattern via pywinauto)
        if action_name == "browser_back" and fg and uia_actions.browser_back(fg.hwnd):
            print(f"  [broker] executed via UIA (tier 1): {action_name}")
            return True
        if action_name == "browser_forward" and fg and uia_actions.browser_forward(fg.hwnd):
            print(f"  [broker] executed via UIA (tier 1): {action_name}")
            return True

        # Tier 2 — named per-app adapter, with verification where possible
        if action_name == "next_slide":
            before = ppt_adapter.current_slide_index()
            if ppt_adapter.next_slide():
                after = ppt_adapter.current_slide_index()
                self._log_verify(action_name, before, after, expect_delta=1)
                return True
        if action_name == "prev_slide":
            before = ppt_adapter.current_slide_index()
            if ppt_adapter.prev_slide():
                after = ppt_adapter.current_slide_index()
                self._log_verify(action_name, before, after, expect_delta=-1)
                return True

        # Tier 3 — input-injection fallback (Batch 2)
        fn = ACTIONS.get(action_name)
        if fn is None:
            print(f"  [broker] unknown action: {action_name!r} — skipped")
            return False
        fn()
        print(f"  [broker] executed via input injection (tier 3): {action_name}")
        return True

    @staticmethod
    def _log_verify(action_name: str, before, after, expect_delta: int) -> None:
        if before is None or after is None:
            print(
                f"  [broker] executed via app adapter (tier 2): {action_name} "
                f"(verification unavailable — couldn't read slide index)"
            )
            return
        if after - before == expect_delta:
            print(
                f"  [broker] executed via app adapter (tier 2): {action_name} "
                f"— VERIFIED (slide {before} -> {after})"
            )
        else:
            print(
                f"  [broker] executed via app adapter (tier 2): {action_name} "
                f"— VERIFICATION FAILED (expected slide {before + expect_delta}, got {after})"
            )
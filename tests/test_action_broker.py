import time

from context_action.action_broker import ActionBroker, CONFIRM_WINDOW_SECONDS


def _stub_broker():
    """ActionBroker with _run_tiers stubbed out so these tests exercise
    only the risk-gating logic, not real Windows execution."""
    broker = ActionBroker()
    broker._run_tiers = lambda action_name: True
    return broker


def test_r1_action_executes_immediately():
    broker = _stub_broker()
    assert broker.execute("browser_forward", "SWIPE_RIGHT") is True


def test_unknown_action_defaults_to_r1_and_executes():
    broker = _stub_broker()
    assert broker.execute("some_future_action", "PINCH") is True


def test_r3_action_is_blocked_on_first_attempt():
    broker = _stub_broker()
    assert broker.execute("close_active_window", "DOUBLE_PINCH") is False


def test_r3_same_gesture_repeated_stays_blocked():
    broker = _stub_broker()
    broker.execute("close_active_window", "DOUBLE_PINCH")
    assert broker.execute("close_active_window", "DOUBLE_PINCH") is False


def test_r3_distinct_gesture_confirms_and_executes():
    broker = _stub_broker()
    broker.execute("close_active_window", "DOUBLE_PINCH")
    assert broker.check_confirmation("SWIPE_RIGHT") is True
    # confirmed and cleared — a further confirmation attempt has nothing pending
    assert broker.check_confirmation("SWIPE_LEFT") is False


def test_confirmation_with_no_pending_action_is_a_no_op():
    broker = _stub_broker()
    assert broker.check_confirmation("SWIPE_RIGHT") is False


def test_r3_confirmation_window_expires():
    broker = _stub_broker()
    broker.execute("close_active_window", "DOUBLE_PINCH")
    action_name, arming_intent, _ = broker._pending_r3
    broker._pending_r3 = (action_name, arming_intent, time.time() - CONFIRM_WINDOW_SECONDS - 1)
    assert broker.check_confirmation("SWIPE_RIGHT") is False
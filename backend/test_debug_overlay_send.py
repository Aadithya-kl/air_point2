"""
Unit tests for debug_overlay.py SEND display diagnostics (Phase P0.1 / P0.3).

Tests that draw_debug_frame handles all _last_send_input_result values
without crashing. The specific SEND:OK/FAIL/UNCERTAIN/N/A mapping is
verified by code inspection and execution of backend/core/debug_overlay.py lines 231-250:

- lr is True        -> "OK"      (legacy Boolean True)
- lr is False       -> "FAIL"    (legacy Boolean False)
- lr is None        -> "N/A"
- hasattr(lr,"value"):
    lr.value == "CONFIRMED"   -> "OK"
    lr.value == "FAILED"      -> "FAIL"
    lr.value == "UNCONFIRMED" -> "UNCERTAIN"
    else                      -> "N/A"
- else                        -> "N/A"

Uses real installed dependencies without modifying sys.modules,
ensuring complete isolation and preventing cross-test contamination.
"""
import unittest
from unittest.mock import MagicMock
import numpy as np

import config  # noqa: E402
from core.actuator import SendInputResult  # noqa: E402
from core.debug_overlay import draw_debug_frame  # noqa: E402


class _FakeLandmark:
    def __init__(self, x=0.5, y=0.5, z=0.0):
        self.x = x
        self.y = y
        self.z = z


class _FakeHandsResult:
    def __init__(self, left=None, right=None, left_score=1.0, right_score=1.0):
        self.left = left
        self.right = right
        self.left_score = left_score
        self.right_score = right_score


class _FakeActuator:
    def __init__(self, send_result=None, dragging=False):
        self._last_send_input_result = send_result
        self._dragging = dragging

    @property
    def is_dragging(self):
        return self._dragging

    def get_native_left_button_state(self):
        return "UNKNOWN"


class _FakeOrchestrator:
    def __init__(self, actuator=None, drag_enabled=True):
        self._actuator = actuator
        self.drag_enabled = drag_enabled
        self.pointer_owner = "NONE"
        self.cursor_source_name = "NONE"
        self.is_cursor_moving = False
        self._left = None


class _FakeLeftProc:
    def __init__(
        self,
        drag_state_name="READY",
        last_pinch_norm=0.0,
        is_in_dropout_grace=False,
        is_pinch_candidate=False,
        release_reason=None,
    ):
        self.drag_state_name = drag_state_name
        self.last_pinch_norm = last_pinch_norm
        self.is_in_dropout_grace = is_in_dropout_grace
        self.is_pinch_candidate = is_pinch_candidate
        self.release_reason = release_reason


class TestSendDisplayDiagnostics(unittest.TestCase):
    """Tests that draw_debug_frame handles all send result values without crashing."""

    def setUp(self):
        config.POINTER_ONLY_MODE = False
        config.LEFT_DRAG_ENABLED = True
        self.frame = np.zeros((480, 640, 3), dtype=np.uint8)

    def _make_hands(self, left_landmarks=None):
        if left_landmarks is None:
            left_landmarks = [_FakeLandmark() for _ in range(21)]
        return _FakeHandsResult(left=left_landmarks, right=None)

    def test_confirmed_no_crash(self):
        """SendInputResult.CONFIRMED does not crash draw_debug_frame."""
        actuator = _FakeActuator(send_result=SendInputResult.CONFIRMED)
        orch = _FakeOrchestrator(actuator=actuator)
        orch._left = _FakeLeftProc()
        draw_debug_frame(self.frame, self._make_hands(), "IDLE", orchestrator=orch)

    def test_failed_no_crash(self):
        """SendInputResult.FAILED does not crash draw_debug_frame."""
        actuator = _FakeActuator(send_result=SendInputResult.FAILED)
        orch = _FakeOrchestrator(actuator=actuator)
        orch._left = _FakeLeftProc()
        draw_debug_frame(self.frame, self._make_hands(), "IDLE", orchestrator=orch)

    def test_unconfirmed_no_crash(self):
        """SendInputResult.UNCONFIRMED does not crash draw_debug_frame."""
        actuator = _FakeActuator(send_result=SendInputResult.UNCONFIRMED)
        orch = _FakeOrchestrator(actuator=actuator)
        orch._left = _FakeLeftProc()
        draw_debug_frame(self.frame, self._make_hands(), "IDLE", orchestrator=orch)

    def test_none_no_crash(self):
        """None does not crash draw_debug_frame."""
        actuator = _FakeActuator(send_result=None)
        orch = _FakeOrchestrator(actuator=actuator)
        orch._left = _FakeLeftProc()
        draw_debug_frame(self.frame, self._make_hands(), "IDLE", orchestrator=orch)

    def test_legacy_bool_true_no_crash(self):
        """Legacy Boolean True does not crash draw_debug_frame."""
        actuator = _FakeActuator(send_result=True)
        orch = _FakeOrchestrator(actuator=actuator)
        orch._left = _FakeLeftProc()
        draw_debug_frame(self.frame, self._make_hands(), "IDLE", orchestrator=orch)

    def test_legacy_bool_false_no_crash(self):
        """Legacy Boolean False does not crash draw_debug_frame."""
        actuator = _FakeActuator(send_result=False)
        orch = _FakeOrchestrator(actuator=actuator)
        orch._left = _FakeLeftProc()
        draw_debug_frame(self.frame, self._make_hands(), "IDLE", orchestrator=orch)

    def test_unknown_enum_no_crash(self):
        """Unknown enum value does not crash draw_debug_frame."""

        class _UnknownResult:
            value = "UNKNOWN_VALUE"

        actuator = _FakeActuator(send_result=_UnknownResult())
        orch = _FakeOrchestrator(actuator=actuator)
        orch._left = _FakeLeftProc()
        draw_debug_frame(self.frame, self._make_hands(), "IDLE", orchestrator=orch)

    def test_no_actuator_attribute_no_crash(self):
        """Actuator without _last_send_input_result does not crash."""
        actuator = MagicMock()
        del actuator._last_send_input_result
        orch = _FakeOrchestrator(actuator=actuator)
        orch._left = _FakeLeftProc()
        draw_debug_frame(self.frame, self._make_hands(), "IDLE", orchestrator=orch)

    def test_no_actuator_at_all_no_crash(self):
        """No actuator does not crash draw_debug_frame."""
        orch = _FakeOrchestrator(actuator=None)
        orch._left = _FakeLeftProc()
        draw_debug_frame(self.frame, self._make_hands(), "IDLE", orchestrator=orch)


if __name__ == "__main__":
    unittest.main()

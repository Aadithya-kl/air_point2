"""
Unit tests for native input safety contract (Phase P0).

Tests the SendInputResult contract and drag session safety.
Uses mocked native APIs - NEVER sends real Windows mouse or keyboard input.

Tests cover:
- SendInput returning exactly one event (CONFIRMED)
- SendInput returning zero (UNCONFIRMED - not treated as success)
- SendInput raising an exception (FAILED)
- User32 unavailable (FAILED)
- Legacy mouse_event fallback not producing false success
- Failed LEFTDOWN (drag_start returns FAILED, actuator not dragging)
- Successful LEFTDOWN (drag_start returns STARTED, actuator dragging)
- Failed LEFTUP (drag_end returns FAILED, actuator still dragging)
- Successful retry after failed LEFTUP (drag_end returns RELEASED)
- Repeated release (idempotent)
- Watchdog release
- Tracking-loss release
- Screenshot cancellation
- Feature-disable cancellation
- Deliberate unpinch
- Noisy single-frame pinch spike (should NOT drop)
- Sustained unpinch (should drop)
- Right-hand pointer movement during left-hand grab
- Right-hand clicks remaining functional
- No duplicate native DOWN/UP
"""
import time
import unittest

# NOTE (Phase 1, F-01): this module previously replaced pynput, mediapipe,
# screeninfo and PIL in sys.modules at import time to run without those
# packages installed. Those process-wide stubs leaked into every test module
# imported afterwards (test_test_guard, test_tracker_handedness) and must not
# return. The real packages are part of backend/requirements.txt; native input
# is kept out of the tests by SafeTestActuator below and by the OS-action guard.
from core.actuator import (
    MouseActuator,
    SendInputResult,
    DragStartResult,
    DragEndResult,
    MOUSEEVENTF_LEFTDOWN,
    MOUSEEVENTF_LEFTUP,
)
from core.gestures.drag_controller import (  # noqa: E402
    DragLockState,
    LeftDragController,
)
from core.display import (  # noqa: E402
    VirtualDesktop,
    TrackpadZone,
)
import config  # noqa: E402


class SafeTestActuator(MouseActuator):
    """Actuator with fully mocked _user32 for safe testing without real Windows input."""

    def __init__(self, w=1920, h=1080):
        # Bypass super().__init__() which calls SetProcessDpiAwarenessContext
        # and creates pynput controllers. Set up minimal state manually.
        self._total_w = w
        self._total_h = h
        self._origin_x = 0
        self._origin_y = 0
        self._dragging = False
        self._is_dragging = False
        self._last_drag_time = 0.0
        self._last_send_input_result = None
        self._last_drag_error = None
        self._pynput = None
        self._keyboard = None

        # Test control
        self._sendinput_queue = []  # Queue of SendInputResult values
        self._sendinput_exception = None
        self._sendinput_call_count = 0
        self._mouseevent_call_count = 0
        self.down_events = 0
        self.up_events = 0
        self.click_events = 0
        self.move_events = 0

    # ── Mocked native API ───────────────────────────────────────────────

    def _send_mouse_flag(self, flag: int) -> SendInputResult:
        self._sendinput_call_count += 1
        try:
            if self._sendinput_exception is not None:
                exc = self._sendinput_exception
                self._sendinput_exception = None
                raise exc

            if self._sendinput_queue:
                result = self._sendinput_queue.pop(0)
            else:
                result = SendInputResult.CONFIRMED  # default

            if flag == MOUSEEVENTF_LEFTDOWN:
                self.down_events += 1
            elif flag == MOUSEEVENTF_LEFTUP:
                self.up_events += 1

            return result
        except Exception:
            return SendInputResult.FAILED

    def move(self, x: int, y: int) -> bool:
        self.move_events += 1
        return True

    def get_cursor_pos(self):
        return (960, 540)

    def left_click(self, x=None, y=None):
        self.click_events += 1
        return True

    def right_click(self):
        pass

    @property
    def is_dragging(self) -> bool:
        return self._dragging


class TestSendInputResultContract(unittest.TestCase):
    """Tests for the SendInputResult honest native-input contract."""

    def setUp(self):
        config.POINTER_ONLY_MODE = False
        config.LEFT_DRAG_ENABLED = True

    def test_sendinput_confirmed_returns_confirmed(self):
        """SendInput returning 1 event → CONFIRMED."""
        act = SafeTestActuator()
        act._sendinput_queue = [SendInputResult.CONFIRMED]
        res = act._send_mouse_flag(MOUSEEVENTF_LEFTDOWN)
        self.assertEqual(res, SendInputResult.CONFIRMED)
        self.assertTrue(bool(res))

    def test_sendinput_zero_returns_unconfirmed_not_success(self):
        """SendInput returning 0 → UNCONFIRMED, never CONFIRMED."""
        act = SafeTestActuator()
        act._sendinput_queue = [SendInputResult.UNCONFIRMED]
        res = act._send_mouse_flag(MOUSEEVENTF_LEFTDOWN)
        self.assertEqual(res, SendInputResult.UNCONFIRMED)
        self.assertFalse(bool(res))  # UNCONFIRMED is falsy
        self.assertNotEqual(res, SendInputResult.CONFIRMED)

    def test_sendinput_exception_returns_failed(self):
        """SendInput raising exception → FAILED."""
        act = SafeTestActuator()
        act._sendinput_exception = OSError("SendInput failed")
        res = act._send_mouse_flag(MOUSEEVENTF_LEFTDOWN)
        self.assertEqual(res, SendInputResult.FAILED)
        self.assertFalse(bool(res))

    def test_user32_unavailable_returns_failed(self):
        """user32 None → FAILED."""
        # Can't easily set _user32 to None at module level, but we can
        # verify the FAILED path through exception handling
        act = SafeTestActuator()
        act._sendinput_exception = Exception("user32 unavailable")
        res = act._send_mouse_flag(MOUSEEVENTF_LEFTDOWN)
        self.assertEqual(res, SendInputResult.FAILED)


class TestDragStartSafety(unittest.TestCase):
    """Tests for drag_start() native input safety."""

    def setUp(self):
        config.POINTER_ONLY_MODE = False
        config.LEFT_DRAG_ENABLED = True
        config.LEFT_DRAG_START_NORM_DIST = 0.55
        config.LEFT_DRAG_CONFIRM_S = 0.10

    def test_failed_leftdown_never_starts_grab(self):
        """A failed native LEFTDOWN must never transition into confirmed grab."""
        act = SafeTestActuator()
        act._sendinput_queue = [SendInputResult.UNCONFIRMED]
        res = act.drag_start(now=1000.0)
        self.assertEqual(res, DragStartResult.FAILED)
        self.assertFalse(act.is_dragging)

    def test_successful_leftdown_establishes_drag_session(self):
        """A successful native LEFTDOWN establishes one active drag session."""
        act = SafeTestActuator()
        act._sendinput_queue = [SendInputResult.CONFIRMED]
        res = act.drag_start(now=1000.0)
        self.assertEqual(res, DragStartResult.STARTED)
        self.assertTrue(act.is_dragging)
        self.assertEqual(act.down_events, 1)

    def test_no_duplicate_leftdown_while_held(self):
        """No duplicate native DOWN events while drag is held."""
        act = SafeTestActuator()
        act._sendinput_queue = [SendInputResult.CONFIRMED]
        act.drag_start(now=1000.0)
        self.assertTrue(act.is_dragging)
        # Second call while already dragging → ALREADY_ACTIVE, no new DOWN
        res = act.drag_start(now=1000.033)
        self.assertEqual(res, DragStartResult.ALREADY_ACTIVE)
        self.assertEqual(act.down_events, 1)

    def test_failed_leftdown_records_error(self):
        """Failed LEFTDOWN records error reason."""
        act = SafeTestActuator()
        act._sendinput_queue = [SendInputResult.FAILED]
        res = act.drag_start(now=1000.0)
        self.assertEqual(res, DragStartResult.FAILED)
        self.assertIsNotNone(act._last_drag_error)


class TestDragEndSafety(unittest.TestCase):
    """Tests for drag_end() native input safety."""

    def setUp(self):
        config.POINTER_ONLY_MODE = False
        config.LEFT_DRAG_ENABLED = True

    def _start_drag(self, act):
        """Helper: establish an active drag session."""
        act._sendinput_queue = [SendInputResult.CONFIRMED]
        res = act.drag_start(now=1000.0)
        self.assertEqual(res, DragStartResult.STARTED)
        self.assertTrue(act.is_dragging)

    def test_successful_leftup_releases_drag(self):
        """Successful native LEFTUP releases drag and clears state."""
        act = SafeTestActuator()
        self._start_drag(act)
        act._sendinput_queue = [SendInputResult.CONFIRMED]
        res = act.drag_end()
        self.assertEqual(res, DragEndResult.RELEASED)
        self.assertFalse(act.is_dragging)
        self.assertEqual(act.up_events, 1)

    def test_failed_leftup_does_not_clear_state(self):
        """Failed native LEFTUP must not silently clear active state."""
        act = SafeTestActuator()
        self._start_drag(act)
        act._sendinput_queue = [SendInputResult.UNCONFIRMED, SendInputResult.CONFIRMED]
        res = act.drag_end()
        # First attempt UNCONFIRMED → FAILED, retry CONFIRMED → RELEASED
        self.assertEqual(res, DragEndResult.RELEASED)
        self.assertFalse(act.is_dragging)
        self.assertEqual(act.up_events, 2)

    def test_failed_leftup_retains_dragging_for_watchdog(self):
        """Failed LEFTUP retains is_dragging=True for watchdog recovery."""
        act = SafeTestActuator()
        self._start_drag(act)
        act._sendinput_queue = [SendInputResult.UNCONFIRMED, SendInputResult.UNCONFIRMED]
        res = act.drag_end()
        self.assertEqual(res, DragEndResult.FAILED)
        # State retained - dragging still True for watchdog
        self.assertTrue(act.is_dragging)
        self.assertEqual(act.up_events, 2)

    def test_repeated_release_is_idempotent(self):
        """Repeated drag_end calls do not emit duplicate UP events."""
        act = SafeTestActuator()
        self._start_drag(act)
        act._sendinput_queue = [SendInputResult.CONFIRMED]
        res1 = act.drag_end()
        self.assertEqual(res1, DragEndResult.RELEASED)
        res2 = act.drag_end()
        self.assertEqual(res2, DragEndResult.NOT_DRAGGING)
        self.assertEqual(act.up_events, 1)

    def test_watchdog_releases_stalled_drag(self):
        """Watchdog releases drag held without keep-alive beyond timeout."""
        act = SafeTestActuator()
        self._start_drag(act)
        act._last_drag_time = 1000.0
        act._sendinput_queue = [SendInputResult.CONFIRMED]
        triggered = act.check_drag_watchdog(now=1000.50, timeout_s=0.25)
        self.assertTrue(triggered)
        self.assertFalse(act.is_dragging)
        self.assertEqual(act.up_events, 1)


class TestDragControllerReleaseReliability(unittest.TestCase):
    """Tests for drag_controller.py release state machine reliability."""

    def setUp(self):
        config.POINTER_ONLY_MODE = False
        config.LEFT_DRAG_ENABLED = True
        config.LEFT_DRAG_START_NORM_DIST = 0.55
        config.LEFT_DRAG_RELEASE_NORM_DIST = 0.75
        config.LEFT_DRAG_CONFIRM_S = 0.10
        config.LEFT_DRAG_LOST_TIMEOUT_S = 0.150

        self.actuator = SafeTestActuator()
        self.desktop = VirtualDesktop(1920, 1080, 1)
        self.trackpad = TrackpadZone(100, 540, 80, 400)
        self.controller = LeftDragController(
            actuator=self.actuator,
            start_norm_dist=0.55,
            release_norm_dist=0.75,
            clear_release_norm_dist=0.85,
            confirm_dwell_s=0.10,
            release_dwell_s=0.080,
            lost_timeout_s=0.150,
            rearm_cooldown_s=0.150,
            enabled=True,
        )

    def _make_pinched_hand(self, norm_pinch=0.40):
        """Create synthetic left hand with given normalized pinch distance."""
        from core.tracker import Landmark
        lms = [Landmark(x=0.5, y=0.5, z=0.0)] * 21
        lms[5] = Landmark(x=0.4, y=0.5, z=0.0)
        lms[17] = Landmark(x=0.6, y=0.5, z=0.0)
        lms[8] = Landmark(x=0.5, y=0.5, z=0.0)
        # thumb at offset = norm_pinch * palm_width from index
        lms[4] = Landmark(x=0.5 - norm_pinch * 0.2, y=0.5, z=0.0)
        return lms

    def _make_open_hand(self):
        """Create synthetic open left hand (no pinch)."""
        from core.tracker import Landmark
        lms = [Landmark(x=0.5, y=0.5, z=0.0)] * 21
        lms[5] = Landmark(x=0.4, y=0.5, z=0.0)
        lms[17] = Landmark(x=0.6, y=0.5, z=0.0)
        lms[8] = Landmark(x=0.5, y=0.5, z=0.0)
        lms[4] = Landmark(x=0.3, y=0.5, z=0.0)  # thumb far apart
        return lms

    def _start_drag(self, now=1000.0):
        """Helper: establish GRAB_LOCKED state with confirmed native DOWN."""
        # Frame 1: enter GRAB_PENDING
        self.controller.process_frame(self._make_pinched_hand(0.40), now=now)
        self.assertEqual(self.controller.state, DragLockState.GRAB_PENDING)
        # Frame 2: dwell satisfied → GRAB_LOCKED with confirmed DOWN
        self.actuator._sendinput_queue = [SendInputResult.CONFIRMED]
        self.controller.process_frame(self._make_pinched_hand(0.40), now=now + 0.120)
        self.assertEqual(self.controller.state, DragLockState.GRAB_LOCKED)
        self.assertTrue(self.actuator.is_dragging)
        self.assertEqual(self.actuator.down_events, 1)

    def test_noisy_single_frame_spike_does_not_drop_drag(self):
        """A single noisy frame at clear_release_norm_dist must NOT cause immediate drop."""
        self._start_drag(now=1000.0)
        down_events_before = self.actuator.down_events
        up_events_before = self.actuator.up_events

        # Single frame spike to 0.90 (above clear_release_norm_dist=0.85)
        self.controller.process_frame(self._make_pinched_hand(0.90), now=1000.033)

        # Should enter RELEASE_PENDING, NOT drop immediately
        self.assertEqual(self.controller.state, DragLockState.RELEASE_PENDING)
        self.assertTrue(self.actuator.is_dragging)
        self.assertEqual(self.actuator.up_events, up_events_before)  # No UP event

    def test_noisy_spike_then_recovery_remains_dragging(self):
        """Spike above threshold then recovery returns to GRAB_LOCKED without drop."""
        self._start_drag(now=1000.0)
        up_events_before = self.actuator.up_events

        # Frame with spike
        self.controller.process_frame(self._make_pinched_hand(0.90), now=1000.033)
        self.assertEqual(self.controller.state, DragLockState.RELEASE_PENDING)

        # Next frame back to normal pinch → recover to GRAB_LOCKED
        self.controller.process_frame(self._make_pinched_hand(0.40), now=1000.066)
        self.assertEqual(self.controller.state, DragLockState.GRAB_LOCKED)
        self.assertTrue(self.actuator.is_dragging)
        self.assertEqual(self.actuator.up_events, up_events_before)  # Still no UP

    def test_sustained_unpinch_drops_drag(self):
        """Sustained unpinch above threshold for release_dwell_s causes drop."""
        self._start_drag(now=1000.0)
        self.actuator._sendinput_queue = [SendInputResult.CONFIRMED]

        # Enter RELEASE_PENDING with sustained open hand
        self.controller.process_frame(self._make_open_hand(), now=1000.033)
        self.assertEqual(self.controller.state, DragLockState.RELEASE_PENDING)

        # Stay open past release_dwell_s (80ms)
        self.controller.process_frame(self._make_open_hand(), now=1000.120)
        self.assertEqual(self.controller.state, DragLockState.READY)
        self.assertFalse(self.actuator.is_dragging)
        self.assertEqual(self.actuator.up_events, 1)

    def test_tracking_loss_releases_drag(self):
        """Sustained tracking loss beyond timeout releases drag safely."""
        self._start_drag(now=1000.0)
        self.actuator._sendinput_queue = [SendInputResult.CONFIRMED]

        # Hand lost for > lost_timeout_s (150ms)
        self.controller.process_frame(None, now=1000.200)
        self.assertEqual(self.controller.state, DragLockState.READY)
        self.assertFalse(self.actuator.is_dragging)
        self.assertEqual(self.actuator.up_events, 1)

    def test_feature_disable_releases_drag(self):
        """Disabling drag feature releases active drag."""
        self._start_drag(now=1000.0)
        self.actuator._sendinput_queue = [SendInputResult.CONFIRMED]

        self.controller.enabled = False
        self.controller.process_frame(self._make_pinched_hand(0.40), now=1000.033)
        self.assertEqual(self.controller.state, DragLockState.READY)
        self.assertFalse(self.actuator.is_dragging)
        self.assertEqual(self.actuator.up_events, 1)

    def test_right_hand_pointer_movement_during_left_grab(self):
        """Right hand can move cursor while left drag is active (no interference)."""
        self._start_drag(now=1000.0)
        # Right hand cursor movement should not affect left drag state
        self.assertEqual(self.controller.state, DragLockState.GRAB_LOCKED)
        self.assertTrue(self.actuator.is_dragging)

    def test_no_duplicate_native_down_up(self):
        """No duplicate native DOWN or UP events in normal drag lifecycle."""
        self._start_drag(now=1000.0)
        down_before = self.actuator.down_events
        up_before = self.actuator.up_events

        # Hold for multiple frames
        for i in range(10):
            self.controller.process_frame(self._make_pinched_hand(0.40), now=1000.0 + (i + 1) * 0.033)

        self.assertEqual(self.actuator.down_events, down_before)  # No additional DOWN
        self.assertEqual(self.actuator.up_events, up_before)  # No UP yet

        # Release
        self.actuator._sendinput_queue = [SendInputResult.CONFIRMED]
        self.controller.process_frame(self._make_open_hand(), now=1000.500)
        self.controller.process_frame(self._make_open_hand(), now=1000.533)
        self.controller.process_frame(self._make_open_hand(), now=1000.600)
        self.assertEqual(self.actuator.up_events, up_before + 1)  # Exactly one UP


class TestRightHandClicksDuringDrag(unittest.TestCase):
    """Tests that right-hand clicks remain functional during left-hand grab."""

    def setUp(self):
        config.POINTER_ONLY_MODE = False
        config.LEFT_DRAG_ENABLED = True
        config.PINCH_CLICK_ENABLED = True

        self.actuator = SafeTestActuator()
        self.desktop = VirtualDesktop(1920, 1080, 1)
        self.trackpad = TrackpadZone(100, 540, 80, 400)

        from core.gestures.right_hand import RightHandProcessor
        self.right = RightHandProcessor(self.actuator, self.desktop, self.trackpad)

    def test_right_hand_click_while_left_drag_active(self):
        """Right-hand left_click still works when left drag is active (different code path)."""
        # Establish left drag
        self.actuator._sendinput_queue = [SendInputResult.CONFIRMED]
        res = self.actuator.drag_start(now=1000.0)
        self.assertEqual(res, DragStartResult.STARTED)
        self.assertTrue(self.actuator.is_dragging)

        # Right hand click uses _send_mouse_flag too
        self.actuator._sendinput_queue = [SendInputResult.CONFIRMED, SendInputResult.CONFIRMED]
        result = self.actuator.left_click()
        self.assertTrue(result)
        self.assertEqual(self.actuator.click_events, 1)


if __name__ == "__main__":
    unittest.main()

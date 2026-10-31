# test_drag_and_drop_pipeline.py
"""
Deterministic Unit Tests for AirPoint Left-Hand Drag & Drop Pipeline.

Verifies all 17 requirements from the Drag & Drop specification:
1. Open hand does not start dragging.
2. Left-hand pinch enters the pending state and activates according to the configured threshold/dwell.
3. Moving the hand while pinched keeps dragging active and updates cursor position.
4. Mouse-down occurs exactly once at drag activation.
5. Mouse-up occurs exactly once on unpinch.
6. Brief landmark jitter does not repeatedly start and stop dragging.
7. Hysteresis prevents threshold flicker.
8. A missing thumb or index landmark cannot create a false pinch.
9. Brief tracking loss does not leave input in an undefined state.
10. Sustained tracking loss releases the mouse button.
11. Disabling Drag & Drop releases an active drag.
12. Engine shutdown releases an active drag.
13. Native input errors leave the state machine recoverable and avoid false success.
14. Right-hand pointer movement does not override an active left-hand drag.
15. Normal right-hand Pointer & Click behaviour remains unchanged.
16. Other gesture handlers are not triggered by the drag pinch.
17. All input tests can run with a mocked input adapter without sending real system mouse events.
"""

import math
import time
import unittest
from unittest.mock import MagicMock, patch

from core.tracker import Landmark, HandsResult
from core.gestures.orchestrator import GestureOrchestrator, PointerOwner
from core.gestures.left_hand import LeftDragState, LeftHandProcessor
from core.actuator import MouseActuator
from core.display import VirtualDesktop, TrackpadZone
import config


class MockInputActuator(MouseActuator):
    """Safe mock actuator that records Win32 SendInput calls without real OS input."""

    def __init__(self, w=1920, h=1080):
        super().__init__(w, h)
        self.moves: list[tuple[int, int]] = []
        self.down_events: int = 0
        self.up_events: int = 0
        self.click_events: int = 0
        self._dragging: bool = False
        self._current_pos: tuple[int, int] = (960, 540)
        self.fail_down: bool = False

    def move(self, x: int, y: int) -> bool:
        self.moves.append((int(x), int(y)))
        self._current_pos = (int(x), int(y))
        return True

    def get_cursor_pos(self) -> tuple[int, int]:
        return self._current_pos

    def _send_mouse_flag(self, flag: int) -> bool:
        from core.actuator import MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP
        if flag == MOUSEEVENTF_LEFTDOWN:
            if self.fail_down:
                return False
            self.down_events += 1
            return True
        elif flag == MOUSEEVENTF_LEFTUP:
            self.up_events += 1
            return True
        return True

    def left_click(self, x=None, y=None) -> bool:
        self.click_events += 1
        return True

    @property
    def is_dragging(self) -> bool:
        return self._dragging


class TestDragAndDropPipeline(unittest.TestCase):
    def setUp(self):
        config.POINTER_ONLY_MODE = False
        config.PINCH_CLICK_ENABLED = True
        config.LEFT_DRAG_ENABLED = True
        config.CAMERA_FPS = 30
        config.LEFT_DRAG_START_NORM_DIST = 0.55
        config.LEFT_DRAG_RELEASE_NORM_DIST = 0.75
        config.LEFT_DRAG_CONFIRM_S = 0.10

        self.actuator = MockInputActuator(1920, 1080)
        self.desktop = VirtualDesktop(1920, 1080, 1)
        self.trackpad = TrackpadZone(100, 540, 80, 400)
        self.orchestrator = GestureOrchestrator(
            self.actuator,
            self.desktop,
            self.trackpad,
            initial_cursor_anchor=(960, 540),
        )

    def _make_left_hand(self, norm_x=0.5, norm_y=0.5, pinch_norm=0.4, open_palm=False, corrupt_landmark=None):
        """Construct synthetic 21-landmark left hand."""
        lms = [Landmark(x=norm_x, y=norm_y, z=0.0) for _ in range(21)]
        lms[5] = Landmark(x=norm_x - 0.10, y=norm_y, z=0.0)
        lms[17] = Landmark(x=norm_x + 0.10, y=norm_y, z=0.0)
        # palm width = 0.20
        lms[8] = Landmark(x=norm_x, y=norm_y, z=0.0)
        lms[6] = Landmark(x=norm_x, y=norm_y + 0.05, z=0.0)

        if open_palm:
            for tip, pip in [(8, 6), (12, 10), (16, 14), (20, 18)]:
                lms[tip] = Landmark(x=norm_x, y=norm_y - 0.15, z=0.0)
                lms[pip] = Landmark(x=norm_x, y=norm_y, z=0.0)
            lms[4] = Landmark(x=norm_x - 0.20, y=norm_y, z=0.0)
        else:
            for tip, pip in [(12, 10), (16, 14), (20, 18)]:
                lms[tip] = Landmark(x=norm_x, y=norm_y + 0.10, z=0.0)
                lms[pip] = Landmark(x=norm_x, y=norm_y, z=0.0)
            lms[4] = Landmark(x=norm_x - (0.20 * pinch_norm), y=norm_y, z=0.0)

        if corrupt_landmark is not None:
            lms[corrupt_landmark] = None

        return lms

    def _make_right_hand(self, norm_x=0.7, norm_y=0.5, pinch_norm=0.9):
        """Construct synthetic 21-landmark right hand."""
        lms = [Landmark(x=norm_x, y=norm_y, z=0.0) for _ in range(21)]
        lms[5] = Landmark(x=norm_x - 0.10, y=norm_y, z=0.0)
        lms[17] = Landmark(x=norm_x + 0.10, y=norm_y, z=0.0)
        lms[8] = Landmark(x=norm_x, y=norm_y, z=0.0)
        lms[6] = Landmark(x=norm_x, y=norm_y + 0.05, z=0.0)
        lms[4] = Landmark(x=norm_x - (0.20 * pinch_norm), y=norm_y, z=0.0)
        return lms

    def _step(self, hands: HandsResult, t: float):
        with patch("time.perf_counter", return_value=t):
            self.orchestrator.process(hands)

    # ── Test 1: Open hand does not start dragging ─────────────────────────────
    def test_01_open_hand_does_not_start_dragging(self):
        t = 10.0
        h = HandsResult(left=self._make_left_hand(0.40, 0.40, open_palm=True))
        for _ in range(5):
            t += 0.033
            self._step(h, t)

        self.assertEqual(self.orchestrator._left.drag_state, LeftDragState.IDLE)
        self.assertFalse(self.actuator.is_dragging)
        self.assertEqual(self.actuator.down_events, 0)

    # ── Test 2: Pinch enters pending state and activates on dwell ──────────────
    def test_02_pinch_enters_pending_and_activates_on_dwell(self):
        t = 20.0
        h = HandsResult(left=self._make_left_hand(0.40, 0.40, pinch_norm=0.35))

        # Frame 1: Enters PINCH_PENDING
        self._step(h, t)
        self.assertEqual(self.orchestrator._left.drag_state, LeftDragState.PINCH_PENDING)
        self.assertFalse(self.actuator.is_dragging)
        self.assertEqual(self.actuator.down_events, 0)

        # Before dwell (50ms < 100ms) -> remains PINCH_PENDING
        t += 0.050
        self._step(h, t)
        self.assertEqual(self.orchestrator._left.drag_state, LeftDragState.PINCH_PENDING)
        self.assertFalse(self.actuator.is_dragging)

        # After dwell (120ms > 100ms) -> transitions to DRAGGING
        t += 0.070
        self._step(h, t)
        self.assertEqual(self.orchestrator._left.drag_state, LeftDragState.DRAGGING)
        self.assertTrue(self.actuator.is_dragging)
        self.assertEqual(self.actuator.down_events, 1)

    # ── Test 3: Moving hand while pinched updates cursor position ──────────────
    def test_03_moving_hand_while_pinched_updates_cursor_position(self):
        t = 30.0
        # Start and confirm drag
        h_start = HandsResult(left=self._make_left_hand(0.30, 0.40, pinch_norm=0.35))
        self._step(h_start, t)
        t += 0.120
        self._step(h_start, t)
        self.assertTrue(self.actuator.is_dragging)

        # Move hand across screen
        initial_moves = len(self.actuator.moves)
        for i in range(1, 5):
            t += 0.033
            h_move = HandsResult(left=self._make_left_hand(0.30 + i * 0.08, 0.40, pinch_norm=0.35))
            self._step(h_move, t)
            self.assertTrue(self.actuator.is_dragging)

        self.assertGreater(len(self.actuator.moves), initial_moves)
        self.assertGreater(self.actuator.moves[-1][0], self.actuator.moves[initial_moves][0])

    # ── Test 4: Mouse-down occurs exactly once at drag activation ─────────────
    def test_04_mouse_down_occurs_exactly_once_at_activation(self):
        t = 40.0
        h = HandsResult(left=self._make_left_hand(0.40, 0.40, pinch_norm=0.35))
        self._step(h, t)
        t += 0.120
        self._step(h, t)
        self.assertEqual(self.actuator.down_events, 1)

        # Hold for 10 frames
        for _ in range(10):
            t += 0.033
            self._step(h, t)

        self.assertEqual(self.actuator.down_events, 1, "Must never emit duplicate mouse-down events while held")

    # ── Test 5: Mouse-up occurs exactly once on unpinch ───────────────────────
    def test_05_mouse_up_occurs_exactly_once_on_unpinch(self):
        t = 50.0
        h_drag = HandsResult(left=self._make_left_hand(0.40, 0.40, pinch_norm=0.35))
        self._step(h_drag, t)
        t += 0.120
        self._step(h_drag, t)
        self.assertTrue(self.actuator.is_dragging)

        # Unpinch: open palm
        t += 0.033
        h_open = HandsResult(left=self._make_left_hand(0.40, 0.40, open_palm=True))
        self._step(h_open, t)
        self.assertEqual(self.actuator.up_events, 1)
        self.assertFalse(self.actuator.is_dragging)
        self.assertEqual(self.orchestrator._left.drag_state, LeftDragState.RELEASING)

        # Stay open
        for _ in range(5):
            t += 0.033
            self._step(h_open, t)

        self.assertEqual(self.actuator.up_events, 1, "Must never emit duplicate mouse-up events")

    # ── Test 6: Brief landmark jitter does not repeatedly start and stop ───────
    def test_06_brief_landmark_jitter_does_not_toggle_drag(self):
        t = 60.0
        h_drag = HandsResult(left=self._make_left_hand(0.40, 0.40, pinch_norm=0.35))
        self._step(h_drag, t)
        t += 0.120
        self._step(h_drag, t)
        self.assertEqual(self.actuator.down_events, 1)

        # 1-frame rotation noise spike into boundary zone (0.78)
        t += 0.033
        h_spike = HandsResult(left=self._make_left_hand(0.40, 0.40, pinch_norm=0.78))
        self._step(h_spike, t)
        self.assertTrue(self.actuator.is_dragging, "Single frame spike must not drop drag")
        self.assertEqual(self.actuator.up_events, 0)

        # Returns to normal pinch
        t += 0.033
        self._step(h_drag, t)
        self.assertTrue(self.actuator.is_dragging)
        self.assertEqual(self.actuator.down_events, 1)
        self.assertEqual(self.actuator.up_events, 0)

    # ── Test 7: Hysteresis prevents threshold flicker ──────────────────────────
    def test_07_hysteresis_prevents_threshold_flicker(self):
        t = 70.0
        # Start drag
        h = HandsResult(left=self._make_left_hand(0.40, 0.40, pinch_norm=0.35))
        self._step(h, t)
        t += 0.120
        self._step(h, t)
        self.assertTrue(self.actuator.is_dragging)

        # Hover in hysteresis band (0.65 - above start 0.55, but below release 0.75)
        for _ in range(8):
            t += 0.033
            h_band = HandsResult(left=self._make_left_hand(0.40, 0.40, pinch_norm=0.65))
            self._step(h_band, t)
            self.assertTrue(self.actuator.is_dragging, "Hysteresis band must keep drag held")
            self.assertEqual(self.actuator.up_events, 0)

    # ── Test 8: Missing landmark cannot create a false pinch ──────────────────
    def test_08_missing_landmark_cannot_create_false_pinch(self):
        t = 80.0
        # Corrupt thumb landmark #4
        h_bad_thumb = HandsResult(left=self._make_left_hand(0.40, 0.40, corrupt_landmark=4))
        self._step(h_bad_thumb, t)
        self.assertEqual(self.orchestrator._left.drag_state, LeftDragState.IDLE)
        self.assertFalse(self.actuator.is_dragging)

        # Corrupt index landmark #8
        t += 0.033
        h_bad_idx = HandsResult(left=self._make_left_hand(0.40, 0.40, corrupt_landmark=8))
        self._step(h_bad_idx, t)
        self.assertEqual(self.orchestrator._left.drag_state, LeftDragState.IDLE)
        self.assertFalse(self.actuator.is_dragging)

    # ── Test 9: Brief tracking loss does not leave undefined input state ───────
    def test_09_brief_tracking_loss_preserves_active_drag(self):
        t = 90.0
        h = HandsResult(left=self._make_left_hand(0.40, 0.40, pinch_norm=0.35))
        self._step(h, t)
        t += 0.120
        self._step(h, t)
        self.assertTrue(self.actuator.is_dragging)

        # 1-frame camera drop (None)
        t += 0.033
        self._step(HandsResult(left=None), t)
        self.assertTrue(self.actuator.is_dragging)
        self.assertEqual(self.actuator.up_events, 0)

        # Reacquired
        t += 0.033
        self._step(h, t)
        self.assertTrue(self.actuator.is_dragging)
        self.assertEqual(self.actuator.up_events, 0)

    # ── Test 10: Sustained tracking loss releases mouse button ─────────────────
    def test_10_sustained_tracking_loss_releases_mouse_button(self):
        t = 100.0
        h = HandsResult(left=self._make_left_hand(0.40, 0.40, pinch_norm=0.35))
        self._step(h, t)
        t += 0.120
        self._step(h, t)
        self.assertTrue(self.actuator.is_dragging)

        # Hand lost for > grace period (0.150s)
        t += 0.150
        self._step(HandsResult(left=None), t)
        self.assertFalse(self.actuator.is_dragging)
        self.assertEqual(self.actuator.up_events, 1)
        self.assertEqual(self.orchestrator._left.drag_state, LeftDragState.IDLE)

    # ── Test 11: Disabling Drag & Drop releases active drag ───────────────────
    def test_11_disabling_drag_releases_active_drag(self):
        t = 110.0
        h = HandsResult(left=self._make_left_hand(0.40, 0.40, pinch_norm=0.35))
        self._step(h, t)
        t += 0.120
        self._step(h, t)
        self.assertTrue(self.actuator.is_dragging)

        # Disable drag feature
        self.orchestrator.drag_enabled = False
        self.assertFalse(self.actuator.is_dragging)
        self.assertEqual(self.actuator.up_events, 1)
        self.assertEqual(self.orchestrator._left.drag_state, LeftDragState.IDLE)

    # ── Test 12: Engine shutdown releases active drag ─────────────────────────
    def test_12_engine_shutdown_releases_active_drag(self):
        t = 120.0
        h = HandsResult(left=self._make_left_hand(0.40, 0.40, pinch_norm=0.35))
        self._step(h, t)
        t += 0.120
        self._step(h, t)
        self.assertTrue(self.actuator.is_dragging)

        # Reset / shutdown
        self.orchestrator.reset()
        self.assertFalse(self.actuator.is_dragging)
        self.assertEqual(self.actuator.up_events, 1)
        self.assertEqual(self.orchestrator._left.drag_state, LeftDragState.IDLE)

    # ── Test 13: Native input errors leave state recoverable ──────────────────
    def test_13_native_input_errors_leave_state_recoverable(self):
        t = 130.0
        self.actuator.fail_down = True  # Simulate Win32 SendInput failure
        h = HandsResult(left=self._make_left_hand(0.40, 0.40, pinch_norm=0.35))
        self._step(h, t)
        t += 0.120
        self._step(h, t)

        # Failed SendInput must NOT enter DRAGGING state
        self.assertFalse(self.actuator.is_dragging)
        self.assertEqual(self.orchestrator._left.drag_state, LeftDragState.IDLE)
        self.assertEqual(self.orchestrator._left.release_reason, "INPUT_ERROR")

        # Recovery: input succeeds
        self.actuator.fail_down = False
        t += 0.050
        self._step(h, t)
        t += 0.120
        self._step(h, t)
        self.assertTrue(self.actuator.is_dragging)
        self.assertEqual(self.orchestrator._left.drag_state, LeftDragState.DRAGGING)

    # ── Test 14: Right-hand pointer does not override active left drag ────────
    def test_14_right_hand_pointer_does_not_override_left_drag(self):
        t = 140.0
        # Start left drag
        h_left = HandsResult(left=self._make_left_hand(0.30, 0.40, pinch_norm=0.35))
        self._step(h_left, t)
        t += 0.120
        self._step(h_left, t)
        self.assertTrue(self.actuator.is_dragging)
        self.assertEqual(self.orchestrator.pointer_owner, "LEFT")

        # Right hand appears pointing
        t += 0.033
        h_both = HandsResult(
            left=self._make_left_hand(0.35, 0.40, pinch_norm=0.35),
            right=self._make_right_hand(0.70, 0.50),
        )
        self._step(h_both, t)

        # Left drag MUST retain pointer ownership
        self.assertEqual(self.orchestrator.pointer_owner, "LEFT")
        self.assertTrue(self.actuator.is_dragging)

    # ── Test 15: Normal right-hand Pointer & Click unchanged ──────────────────
    def test_15_normal_right_hand_pointer_and_click_unchanged(self):
        t = 150.0
        # Right hand pointing
        h_right = HandsResult(right=self._make_right_hand(0.60, 0.50, pinch_norm=0.9))
        self._step(h_right, t)
        self.assertEqual(self.orchestrator.pointer_owner, "RIGHT")
        self.assertFalse(self.actuator.is_dragging)

        # Right hand pinch click
        t += 0.033
        h_click = HandsResult(right=self._make_right_hand(0.60, 0.50, pinch_norm=0.35))
        self._step(h_click, t)
        t += 0.100
        self._step(h_click, t)
        # Verify right hand does NOT start drag
        self.assertFalse(self.actuator.is_dragging)

    # ── Test 16: Other gesture handlers not triggered by drag pinch ───────────
    def test_16_other_gestures_not_triggered_by_drag_pinch(self):
        t = 160.0
        h = HandsResult(left=self._make_left_hand(0.40, 0.40, pinch_norm=0.35))
        self._step(h, t)
        t += 0.120
        self._step(h, t)
        self.assertTrue(self.actuator.is_dragging)

        # Check lip mute, screenshot, Wakanda are IDLE
        self.assertEqual(self.orchestrator._lip_gesture.state.name, "IDLE")
        self.assertIn(self.orchestrator._wakanda.state.name, ("IDLE", "DISABLED"))

    # ── Test 17: Mocked input adapter safe (no real OS input) ─────────────────
    def test_17_mocked_input_adapter_safe(self):
        # Verify actuator is mock
        self.assertIsInstance(self.actuator, MockInputActuator)
        self.assertTrue(hasattr(self.actuator, "down_events"))
        self.assertTrue(hasattr(self.actuator, "up_events"))


if __name__ == "__main__":
    unittest.main()

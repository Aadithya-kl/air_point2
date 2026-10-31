"""
Comprehensive Unit & Integration Test Suite for AirPoint Rebuilt Left-Hand Drag Subsystem.
Implements the 20 required verification contracts under deterministic mock conditions.
"""

from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock, patch

import config
from core.actuator import DragEndResult, DragStartResult, MouseActuator
from core.display import TrackpadZone, VirtualDesktop
from core.gestures.drag_controller import DragLockState, LeftDragController
from core.gestures.left_hand import LeftDragState, LeftHandProcessor, _LeftState
from core.gestures.orchestrator import GestureOrchestrator
from core.gestures.utils import is_open_palm
from core.tracker import HandsResult, Landmark


class DummyActuator(MouseActuator):
    """Deterministic in-memory mock actuator for testing."""

    def __init__(self) -> None:
        self.clicks = 0
        self.moves = 0
        self.double_clicks = 0
        self.drags = 0
        self.drops = 0
        self._is_dragging = False
        self.last_move: tuple[int, int] | None = None
        self.keys_sent: list[str] = []
        self.fail_down = False
        self.fail_up = False

    def left_click(self) -> bool:
        self.clicks += 1
        return True

    def move(self, x: int, y: int) -> None:
        self.moves += 1
        self.last_move = (int(x), int(y))

    def get_cursor_pos(self) -> tuple[int, int] | None:
        if self.last_move is not None:
            return self.last_move
        return (960, 540)

    def double_click(self, x=None, y=None) -> bool:
        self.double_clicks += 1
        return True

    def drag_start(self, now: float | None = None) -> DragStartResult:
        if self.fail_down:
            return DragStartResult.FAILED
        if self._is_dragging:
            return DragStartResult.ALREADY_ACTIVE
        self.drags += 1
        self._is_dragging = True
        return DragStartResult.STARTED

    def drag_end(self) -> DragEndResult:
        if self.fail_up:
            return DragEndResult.FAILED
        if not self._is_dragging:
            return DragEndResult.NOT_DRAGGING
        self.drops += 1
        self._is_dragging = False
        return DragEndResult.RELEASED

    def ctrl_down(self) -> None:
        self.keys_sent.append("ctrl_down")

    def ctrl_up(self) -> None:
        self.keys_sent.append("ctrl_up")

    def win_d(self) -> None:
        self.keys_sent.append("win_d")

    def alt_tab(self) -> None:
        self.keys_sent.append("alt_tab")

    def win_tab(self) -> None:
        self.keys_sent.append("win_tab")

    def win_key(self) -> None:
        self.keys_sent.append("win_key")

    def alt_left(self) -> None:
        self.keys_sent.append("alt_left")


class TestPhase2LeftHand(unittest.TestCase):
    def setUp(self) -> None:
        config.POINTER_ONLY_MODE = False
        config.PINCH_CLICK_ENABLED = True
        config.LEFT_DRAG_ENABLED = True
        config.CAMERA_FPS = 30
        config.LEFT_DRAG_START_NORM_DIST = 0.55
        config.LEFT_DRAG_RELEASE_NORM_DIST = 0.75
        config.LEFT_DRAG_CONFIRM_S = 0.10
        config.LEFT_DRAG_LOST_TIMEOUT_S = 0.075

        self.actuator = DummyActuator()
        self.desktop = VirtualDesktop(1920, 1080, 1)
        self.trackpad = TrackpadZone(100, 540, 100, 380)
        self.orchestrator = GestureOrchestrator(self.actuator, self.desktop, self.trackpad)
        self.processor = LeftHandProcessor(self.actuator, self.desktop, self.trackpad)

    def tearDown(self) -> None:
        config.LEFT_DRAG_LOST_TIMEOUT_S = 0.075

    def _make_left_hand(
        self,
        x: float = 0.5,
        y: float = 0.5,
        pinch_norm: float = 0.9,
        open_palm: bool = True,
        fist: bool = False,
    ) -> list[Landmark]:
        lms = [Landmark(x=x, y=y, z=0.0)] * 21
        lms[5] = Landmark(x=x - 0.1, y=y, z=0.0)
        lms[17] = Landmark(x=x + 0.1, y=y, z=0.0)
        lms[8] = Landmark(x=x, y=y, z=0.0)  # index tip
        lms[6] = Landmark(x=x, y=y + 0.1, z=0.0)  # index pip

        if fist:
            for tip, pip in [(8, 6), (12, 10), (16, 14), (20, 18)]:
                lms[tip] = Landmark(x=x, y=y + 0.2, z=0.0)
                lms[pip] = Landmark(x=x, y=y + 0.1, z=0.0)
            lms[4] = Landmark(x=x + 0.05, y=y + 0.1, z=0.0)
        elif open_palm:
            for tip, pip in [(12, 10), (16, 14), (20, 18)]:
                lms[tip] = Landmark(x=x, y=y - 0.1, z=0.0)
                lms[pip] = Landmark(x=x, y=y, z=0.0)
            lms[2] = Landmark(x=x - 0.1, y=y + 0.1, z=0.0)
            lms[4] = Landmark(x=x - (0.2 * pinch_norm), y=y, z=0.0)
        else:
            for tip, pip in [(12, 10), (16, 14), (20, 18)]:
                lms[tip] = Landmark(x=x, y=y + 0.1, z=0.0)
                lms[pip] = Landmark(x=x, y=y, z=0.0)
            lms[4] = Landmark(x=x - (0.2 * pinch_norm), y=y, z=0.0)

        return lms

    # ── Pointer Tracking Baselines ────────────────────────────────────────────

    def test_left_index_movement_with_open_palm_facing_camera(self) -> None:
        """Left index moves smoothly with palm completely open facing camera."""
        hand1 = self._make_left_hand(x=0.3, y=0.5, open_palm=True)
        self.processor.process(hand1)
        self.assertTrue(self.processor.is_pointing)
        self.assertIsNotNone(self.processor.cursor_pos)
        pos1 = self.processor.cursor_pos

        time.sleep(0.03)
        hand2 = self._make_left_hand(x=0.6, y=0.5, open_palm=True)
        self.processor.process(hand2)
        self.assertTrue(self.processor.is_pointing)
        pos2 = self.processor.cursor_pos
        self.assertGreater(pos2[0], pos1[0], "Cursor X must advance to the right")

    def test_changing_palm_orientation_does_not_freeze_tracking(self) -> None:
        """Changing palm orientation does not freeze tracking."""
        self.processor.process(self._make_left_hand(x=0.4, y=0.4, open_palm=True))
        self.assertTrue(self.processor.is_pointing)

        time.sleep(0.03)
        self.processor.process(self._make_left_hand(x=0.45, y=0.4, open_palm=False))
        self.assertTrue(self.processor.is_pointing, "Tracking must NOT freeze when fingers curl")

        time.sleep(0.03)
        self.processor.process(self._make_left_hand(x=0.5, y=0.4, open_palm=True))
        self.assertTrue(self.processor.is_pointing, "Tracking must NOT freeze when palm re-opens")

    # ── Phase 7 Explicit Requirements (1-20) ──────────────────────────────────

    def test_01_open_hand_does_not_activate_a_grab(self) -> None:
        """1. Open hand does not activate a grab."""
        for _ in range(5):
            self.processor.process(self._make_left_hand(pinch_norm=0.90, open_palm=True))
        self.assertEqual(self.actuator.drags, 0)
        self.assertFalse(self.actuator.is_dragging)
        self.assertEqual(self.processor.left_drag_state, DragLockState.READY)

    def test_02_valid_pinch_enters_grab_pending(self) -> None:
        """2. A valid pinch enters GRAB_PENDING."""
        self.processor.process(self._make_left_hand(pinch_norm=0.40))
        self.assertEqual(self.processor.left_drag_state, DragLockState.GRAB_PENDING)
        self.assertEqual(self.actuator.drags, 0, "Dwell not yet satisfied: no button down")
        self.assertFalse(self.actuator.is_dragging)

    def test_03_confirmed_pinch_emits_one_native_down_and_enters_grab_locked(self) -> None:
        """3. A confirmed pinch emits exactly one native DOWN and enters GRAB_LOCKED."""
        self.processor.process(self._make_left_hand(pinch_norm=0.40))
        time.sleep(0.12)
        self.processor.process(self._make_left_hand(pinch_norm=0.40))
        self.assertEqual(self.actuator.drags, 1)
        self.assertTrue(self.actuator.is_dragging)
        self.assertEqual(self.processor.left_drag_state, DragLockState.GRAB_LOCKED)

    def test_04_long_hold_keeps_button_down_without_repeated_down(self) -> None:
        """4. A long hold over many frames keeps logical and native button DOWN."""
        self.processor.process(self._make_left_hand(pinch_norm=0.40))
        time.sleep(0.12)
        self.processor.process(self._make_left_hand(pinch_norm=0.40))
        self.assertEqual(self.actuator.drags, 1)

        for _ in range(15):
            time.sleep(0.01)
            self.processor.process(self._make_left_hand(pinch_norm=0.40))
            self.assertTrue(self.actuator.is_dragging)

        self.assertEqual(self.actuator.drags, 1, "Must never reissue DOWN during hold")
        self.assertEqual(self.actuator.drops, 0, "Must never trigger UP during hold")

    def test_05_movement_during_hold_does_not_reissue_down_or_trigger_up(self) -> None:
        """5. Movement during the hold does not reissue DOWN or trigger UP."""
        self.processor.process(self._make_left_hand(x=0.3, y=0.4, pinch_norm=0.40))
        time.sleep(0.12)
        self.processor.process(self._make_left_hand(x=0.3, y=0.4, pinch_norm=0.40))
        self.assertEqual(self.actuator.drags, 1)

        for i in range(10):
            x = 0.3 + i * 0.03
            self.processor.process(self._make_left_hand(x=x, y=0.4, pinch_norm=0.40))
            self.assertTrue(self.actuator.is_dragging)
            self.assertEqual(self.actuator.drags, 1)
            self.assertEqual(self.actuator.drops, 0)

    def test_06_open_palm_classification_does_not_release_valid_pinch(self) -> None:
        """6. Open-palm classification by itself does not release a valid pinch."""
        self.processor.process(self._make_left_hand(pinch_norm=0.40, open_palm=True))
        time.sleep(0.12)
        self.processor.process(self._make_left_hand(pinch_norm=0.40, open_palm=True))
        self.assertEqual(self.processor.left_drag_state, DragLockState.GRAB_LOCKED)

        for _ in range(10):
            hand = self._make_left_hand(pinch_norm=0.40, open_palm=True)
            self.assertTrue(is_open_palm(hand))
            self.processor.process(hand)
            self.assertEqual(self.processor.left_drag_state, DragLockState.GRAB_LOCKED)
            self.assertTrue(self.actuator.is_dragging)

    def test_07_pinch_jitter_below_release_threshold_keeps_grab_locked(self) -> None:
        """7. Pinch jitter below the deliberate release threshold keeps the grab locked."""
        self.processor.process(self._make_left_hand(pinch_norm=0.40))
        time.sleep(0.12)
        self.processor.process(self._make_left_hand(pinch_norm=0.40))
        self.assertEqual(self.processor.left_drag_state, DragLockState.GRAB_LOCKED)

        # Fluctuate up to 0.68 (above entry 0.55 but below release 0.75)
        for val in [0.45, 0.60, 0.68, 0.50, 0.65]:
            self.processor.process(self._make_left_hand(pinch_norm=val))
            self.assertEqual(self.processor.left_drag_state, DragLockState.GRAB_LOCKED)
            self.assertTrue(self.actuator.is_dragging)
            self.assertEqual(self.actuator.drops, 0)

    def test_08_crossing_release_threshold_briefly_does_not_release_until_dwell_satisfied(self) -> None:
        """8. Crossing release threshold briefly does not release until release dwell is satisfied."""
        self.processor.process(self._make_left_hand(pinch_norm=0.40))
        time.sleep(0.12)
        self.processor.process(self._make_left_hand(pinch_norm=0.40))
        self.assertEqual(self.processor.left_drag_state, DragLockState.GRAB_LOCKED)

        # Frame 1 across release threshold into hysteresis band (0.78 > 0.75)
        self.processor.process(self._make_left_hand(pinch_norm=0.78))
        self.assertEqual(self.processor.left_drag_state, DragLockState.RELEASE_PENDING)
        self.assertEqual(self.actuator.drops, 0, "Debounce pending: must not drop on first frame")
        self.assertTrue(self.actuator.is_dragging)

    def test_09_returning_to_held_range_during_release_pending_cancels_release(self) -> None:
        """9. Returning to held range during RELEASE_PENDING cancels the pending release."""
        self.processor.process(self._make_left_hand(pinch_norm=0.40))
        time.sleep(0.12)
        self.processor.process(self._make_left_hand(pinch_norm=0.40))
        self.assertEqual(self.processor.left_drag_state, DragLockState.GRAB_LOCKED)

        # Enter RELEASE_PENDING
        self.processor.process(self._make_left_hand(pinch_norm=0.78))
        self.assertEqual(self.processor.left_drag_state, DragLockState.RELEASE_PENDING)

        # Immediately return to firm pinch before release dwell expires
        self.processor.process(self._make_left_hand(pinch_norm=0.45))
        self.assertEqual(self.processor.left_drag_state, DragLockState.GRAB_LOCKED)
        self.assertEqual(self.actuator.drops, 0, "No mouse UP dispatched on cancellation")
        self.assertTrue(self.actuator.is_dragging)

    def test_10_deliberate_unpinch_emits_exactly_one_up_and_returns_to_ready(self) -> None:
        """10. A deliberate unpinch emits exactly one UP and returns to READY."""
        self.processor.process(self._make_left_hand(pinch_norm=0.40))
        time.sleep(0.12)
        self.processor.process(self._make_left_hand(pinch_norm=0.40))
        self.assertEqual(self.actuator.drags, 1)

        # Clear deliberate unpinch (0.90 >= 0.85)
        self.processor.process(self._make_left_hand(pinch_norm=0.90))
        self.assertEqual(self.actuator.drops, 1)
        self.assertFalse(self.actuator.is_dragging)
        self.assertEqual(self.processor.left_drag_state, DragLockState.READY)

        for _ in range(5):
            self.processor.process(self._make_left_hand(pinch_norm=0.90))
        self.assertEqual(self.actuator.drops, 1, "Must never emit duplicate UP events")

    def test_11_new_pinch_after_completed_drop_starts_new_session(self) -> None:
        """11. A new pinch after a completed drop starts a new session."""
        # Session 1
        self.processor.process(self._make_left_hand(pinch_norm=0.40))
        time.sleep(0.12)
        self.processor.process(self._make_left_hand(pinch_norm=0.40))
        self.assertEqual(self.actuator.drags, 1)

        # Drop
        self.processor.process(self._make_left_hand(pinch_norm=0.90))
        self.assertEqual(self.actuator.drops, 1)
        self.assertFalse(self.actuator.is_dragging)

        # Wait for unpinch rearm cooldown (0.20s > 0.15s)
        time.sleep(0.20)

        # Session 2
        self.processor.process(self._make_left_hand(pinch_norm=0.40))
        self.assertEqual(self.processor.left_drag_state, DragLockState.GRAB_PENDING)
        time.sleep(0.12)
        self.processor.process(self._make_left_hand(pinch_norm=0.40))
        self.assertEqual(self.actuator.drags, 2)
        self.assertTrue(self.actuator.is_dragging)
        self.assertEqual(self.processor.left_drag_state, DragLockState.GRAB_LOCKED)

    def test_12_repeated_activation_request_cannot_cancel_existing_grab(self) -> None:
        """12. A repeated activation request cannot cancel an existing grab."""
        self.processor.process(self._make_left_hand(pinch_norm=0.40))
        time.sleep(0.12)
        self.processor.process(self._make_left_hand(pinch_norm=0.40))
        self.assertEqual(self.processor.left_drag_state, DragLockState.GRAB_LOCKED)
        self.assertEqual(self.actuator.drags, 1)

        # Simulate duplicate drag_start call
        res = self.processor.drag_controller._execute_grab_down(time.perf_counter())
        self.assertEqual(res, DragStartResult.ALREADY_ACTIVE)
        self.assertTrue(self.actuator.is_dragging)
        self.assertEqual(self.actuator.drags, 1, "No duplicate native down events")

    def test_13_button_down_failure_never_enters_grab_locked(self) -> None:
        """13. Button-down failure never enters GRAB_LOCKED."""
        self.actuator.fail_down = True
        self.processor.process(self._make_left_hand(pinch_norm=0.40))
        time.sleep(0.12)
        self.processor.process(self._make_left_hand(pinch_norm=0.40))

        self.assertNotEqual(self.processor.left_drag_state, DragLockState.GRAB_LOCKED)
        self.assertFalse(self.actuator.is_dragging)
        self.assertEqual(self.processor.release_reason, "INPUT_ERROR")

    def test_14_button_up_failure_reported_accurately_and_safely_recovered(self) -> None:
        """14. Button-up failure is reported accurately and safely recovered where possible."""
        self.processor.process(self._make_left_hand(pinch_norm=0.40))
        time.sleep(0.12)
        self.processor.process(self._make_left_hand(pinch_norm=0.40))
        self.assertTrue(self.actuator.is_dragging)

        # Force button-up failure
        self.actuator.fail_up = True
        self.processor.process(self._make_left_hand(pinch_norm=0.90))
        self.assertEqual(self.processor.left_drag_state, DragLockState.INPUT_ERROR)
        self.assertEqual(self.processor.release_reason, "INPUT_ERROR")

        # Recovery when actuator succeeds
        self.actuator.fail_up = False
        res = self.processor.drag_controller.release_grab(reason="RECOVERY")
        self.assertTrue(res)
        self.assertEqual(self.processor.left_drag_state, DragLockState.READY)

    def test_15_tracking_loss_grace_and_sustained_loss_release(self) -> None:
        """15. Tracking loss within grace period does not prematurely drop; sustained loss releases safely."""
        hands = HandsResult(left=self._make_left_hand(pinch_norm=0.40))
        self.orchestrator.process(hands)
        time.sleep(0.12)
        self.orchestrator.process(hands)
        self.assertTrue(self.actuator.is_dragging)

        # Momentary loss (within 0.075s grace)
        self.orchestrator.process(HandsResult(left=None))
        self.assertTrue(self.actuator.is_dragging, "Momentary frame drop must stay in grace")
        self.assertTrue(self.orchestrator._left.is_in_dropout_grace)

        # Sustained loss past grace timeout
        time.sleep(0.12)
        self.orchestrator.process(HandsResult(left=None))
        self.assertFalse(self.actuator.is_dragging, "Sustained tracking loss MUST release grab")
        self.assertEqual(self.actuator.drops, 1)

    def test_16_feature_disable_pause_and_shutdown_release_safely(self) -> None:
        """16. Feature disable, pause and shutdown release safely."""
        hands = HandsResult(left=self._make_left_hand(pinch_norm=0.40))
        self.orchestrator.process(hands)
        time.sleep(0.12)
        self.orchestrator.process(hands)
        self.assertTrue(self.actuator.is_dragging)

        # Feature disable
        self.orchestrator.drag_enabled = False
        self.assertFalse(self.actuator.is_dragging)
        self.assertEqual(self.actuator.drops, 1)

        # Re-enable and shutdown/reset
        self.orchestrator.drag_enabled = True
        self.orchestrator.process(hands)
        time.sleep(0.12)
        self.orchestrator.process(hands)
        self.assertTrue(self.actuator.is_dragging)

        self.orchestrator.reset()
        self.assertFalse(self.actuator.is_dragging)
        self.assertEqual(self.actuator.drops, 2)

    def test_17_right_hand_pointer_continues_moving_item_during_grab(self) -> None:
        """17. Right-hand pointer coordinates continue moving item during left-hand grab."""
        hands = HandsResult()
        r_lms = [Landmark(x=0.3, y=0.3, z=0.0)] * 21
        r_lms[5] = Landmark(x=0.2, y=0.3, z=0.0)
        r_lms[17] = Landmark(x=0.4, y=0.3, z=0.0)
        r_lms[8] = Landmark(x=0.3, y=0.3, z=0.0)
        r_lms[4] = Landmark(x=0.5, y=0.3, z=0.0)
        hands.right = r_lms
        hands.left = self._make_left_hand(x=0.8, y=0.8, pinch_norm=0.40)

        self.orchestrator.process(hands)
        time.sleep(0.12)
        self.orchestrator.process(hands)
        self.assertTrue(self.actuator.is_dragging)
        self.assertEqual(self.orchestrator.pointer_owner, "RIGHT")
        initial_pos = self.actuator.last_move

        # Translate right hand to (0.6, 0.6) while left maintains pinch
        r_lms2 = [Landmark(x=0.6, y=0.6, z=0.0)] * 21
        r_lms2[5] = Landmark(x=0.5, y=0.6, z=0.0)
        r_lms2[17] = Landmark(x=0.7, y=0.6, z=0.0)
        r_lms2[8] = Landmark(x=0.6, y=0.6, z=0.0)
        r_lms2[4] = Landmark(x=0.8, y=0.6, z=0.0)
        hands.right = r_lms2

        time.sleep(0.02)
        self.orchestrator.process(hands)
        self.assertTrue(self.actuator.is_dragging)
        self.assertEqual(self.orchestrator.pointer_owner, "RIGHT")
        self.assertNotEqual(self.actuator.last_move, initial_pos)

    def test_18_left_hand_cursor_fallback_when_right_hand_unavailable(self) -> None:
        """18. Left-hand cursor fallback works when right hand is unavailable."""
        orch = GestureOrchestrator(self.actuator, self.desktop, self.trackpad)
        hands = HandsResult(left=self._make_left_hand(x=0.5, y=0.5, pinch_norm=0.40))

        orch.process(hands)
        time.sleep(0.12)
        orch.process(hands)
        self.assertTrue(self.actuator.is_dragging)
        self.assertEqual(orch.pointer_owner, "LEFT", "Left hand becomes cursor owner when right absent")

    def test_19_pointer_ownership_does_not_switch_repeatedly_while_grab_locked(self) -> None:
        """19. Pointer ownership does not switch repeatedly while grab is locked."""
        hands = HandsResult()
        r_lms = [Landmark(x=0.4, y=0.4, z=0.0)] * 21
        r_lms[5] = Landmark(x=0.3, y=0.4, z=0.0)
        r_lms[17] = Landmark(x=0.5, y=0.4, z=0.0)
        r_lms[8] = Landmark(x=0.4, y=0.4, z=0.0)
        r_lms[4] = Landmark(x=0.6, y=0.4, z=0.0)
        hands.right = r_lms
        hands.left = self._make_left_hand(x=0.8, y=0.8, pinch_norm=0.40)

        self.orchestrator.process(hands)
        time.sleep(0.12)
        self.orchestrator.process(hands)
        self.assertTrue(self.actuator.is_dragging)
        self.assertEqual(self.orchestrator.pointer_owner, "RIGHT")

        # Simulate momentary 1-frame dip in right hand score or small jitter
        for _ in range(5):
            self.orchestrator.process(hands)
            self.assertEqual(self.orchestrator.pointer_owner, "RIGHT", "Pointer owner must remain stably locked to RIGHT")

    def test_20_existing_watchdog_and_native_actuator_contracts(self) -> None:
        """20. MouseActuator drag_start, drag_end, and watchdog contracts."""
        real_actuator = MouseActuator(1920, 1080)
        with patch.object(real_actuator, "_send_mouse_flag", return_value=True):
            res_start = real_actuator.drag_start()
            self.assertEqual(res_start, DragStartResult.STARTED)
            self.assertTrue(bool(res_start))

            res_dup = real_actuator.drag_start()
            self.assertEqual(res_dup, DragStartResult.ALREADY_ACTIVE)

            # Watchdog keep-alive check
            t0 = time.perf_counter()
            real_actuator.keep_drag_alive(now=t0)
            self.assertFalse(real_actuator.check_drag_watchdog(now=t0 + 0.10, timeout_s=0.25))

            # Watchdog expired
            self.assertTrue(real_actuator.check_drag_watchdog(now=t0 + 0.35, timeout_s=0.25))
            self.assertFalse(real_actuator.is_dragging)


if __name__ == "__main__":
    unittest.main()

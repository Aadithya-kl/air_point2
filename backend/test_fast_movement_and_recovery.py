"""
Comprehensive Acceptance Tests for Fast-Movement Tracking, Temporary Hand Loss Handling,
Responsiveness, and Safety Invariants.

Verifies:
1. Smooth tracking during rapid but valid hand movement.
2. One or several temporarily missing frames (dropout grace & safe freeze).
3. Hand loss followed by successful reacquisition (genuine loss & clean rebaseline).
4. A different hand identity appearing (safe rebaselining without teleportation).
5. Stale camera frames and long inference delays (freshness check & derivative clamp).
6. No cursor movement during uncertain tracking (low confidence suppression).
7. No excessive cursor jump after reacquisition (bounded step headroom).
8. Preservation of all safety limits and existing gestures.
"""

import math
import time
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from core.actuator import MouseActuator
from core.camera import FrameFreshnessDetector
from core.display import VirtualDesktop, TrackpadZone
from core.filter import OneEuroFilter
from core.gestures.left_hand import LeftHandProcessor
from core.gestures.orchestrator import GestureOrchestrator, PointerOwner
from core.gestures.right_hand import RightHandProcessor
from core.tracker import HandsResult, Landmark


def make_hand(norm_x: float, norm_y: float) -> list[Landmark]:
    """Construct a synthetic 21-landmark hand with index tip at (norm_x, norm_y)."""
    lms = []
    for i in range(21):
        if i == 8:  # Index tip
            lms.append(Landmark(x=norm_x, y=norm_y, z=0.0))
        elif i == 4:  # Thumb tip (separated from index)
            lms.append(Landmark(x=norm_x - 0.12, y=norm_y + 0.10, z=0.0))
        elif i == 5:  # Index MCP
            lms.append(Landmark(x=norm_x - 0.04, y=norm_y + 0.15, z=0.0))
        elif i == 17:  # Pinky MCP
            lms.append(Landmark(x=norm_x + 0.08, y=norm_y + 0.15, z=0.0))
        else:
            lms.append(Landmark(x=norm_x, y=norm_y + 0.18, z=0.0))
    return lms


class TestFastMovementAndRecovery(unittest.TestCase):
    def setUp(self) -> None:
        self.desktop = VirtualDesktop(total_width=1920, total_height=1080, monitor_count=1)
        self.actuator = MouseActuator(1920, 1080)
        self.actuator.move = MagicMock(return_value=True)
        self.actuator.get_cursor_pos = MagicMock(return_value=(960, 540))
        self.trackpad = TrackpadZone(100, 540, 100, 380)

        self.right = RightHandProcessor(self.actuator, self.desktop, self.trackpad)
        self.left = LeftHandProcessor(self.actuator, self.desktop, self.trackpad)
        self.orchestrator = GestureOrchestrator(
            actuator=self.actuator,
            desktop=self.desktop,
            trackpad=self.trackpad,
            initial_cursor_anchor=(960, 540),
        )

    # -------------------------------------------------------------------------
    # 1. Smooth tracking during rapid but valid hand movement
    # -------------------------------------------------------------------------
    def test_smooth_tracking_during_rapid_valid_movement(self) -> None:
        """Verify that rapid continuous hand motion advances cursor smoothly each frame without lag-stalls."""
        now = 100.0
        dt = 1.0 / 30.0

        # Sweep hand across trackpad over 6 frames (~0.03 norm units per frame)
        positions = []
        for i in range(6):
            t = now + i * dt
            h = HandsResult(right=make_hand(0.35 + i * 0.035, 0.35 + i * 0.035), right_score=0.95)
            with patch("time.perf_counter", return_value=t):
                self.orchestrator.process(h)
            pos = self.orchestrator.cursor_pos
            self.assertIsNotNone(pos)
            positions.append(pos)

        # Confirm movement progressed monotonically on both axes
        for i in range(1, len(positions)):
            self.assertGreater(positions[i][0], positions[i - 1][0], f"Frame {i} stalled horizontally")
            self.assertGreater(positions[i][1], positions[i - 1][1], f"Frame {i} stalled vertically")

        # Confirm actuator received calls on all frames
        self.assertEqual(self.actuator.move.call_count, 6)

    # -------------------------------------------------------------------------
    # 2. One or several temporarily missing frames (dropout grace)
    # -------------------------------------------------------------------------
    def test_temporarily_missing_frames_freeze_cursor_and_recover_without_reset(self) -> None:
        """
        Verify that 1 or 2 missing frames enter dropout grace, freezing cursor safely
        without resetting 1€ filter state or dropping active tracking.
        """
        now = 100.0
        dt = 1.0 / 30.0

        # Frame 1: Valid hand
        h1 = HandsResult(right=make_hand(0.50, 0.50), right_score=0.90)
        with patch("time.perf_counter", return_value=now):
            self.orchestrator.process(h1)

        p1 = self.orchestrator.cursor_pos
        self.assertIsNotNone(p1)
        self.assertEqual(self.orchestrator.pointer_owner, "RIGHT")
        self.assertFalse(self.orchestrator._right.is_in_dropout_grace)

        # Frame 2: Sudden motion dropout (1 frame missing)
        h_none = HandsResult(right=None)
        with patch("time.perf_counter", return_value=now + dt):
            self.orchestrator.process(h_none)

        # In dropout grace: cursor remains safely frozen at p1, owner preserved
        self.assertTrue(self.orchestrator._right.is_in_dropout_grace)
        self.assertEqual(self.orchestrator.cursor_pos, p1)
        self.assertEqual(self.orchestrator.pointer_owner, "RIGHT")

        # Frame 3: Second consecutive dropout frame (still within 3-frame / 120ms grace)
        with patch("time.perf_counter", return_value=now + 2 * dt):
            self.orchestrator.process(h_none)

        self.assertTrue(self.orchestrator._right.is_in_dropout_grace)
        self.assertEqual(self.orchestrator.cursor_pos, p1)

        # Frame 4: Hand re-detected!
        h_return = HandsResult(right=make_hand(0.54, 0.54), right_score=0.92)
        with patch("time.perf_counter", return_value=now + 3 * dt):
            self.orchestrator.process(h_return)

        p4 = self.orchestrator.cursor_pos
        self.assertFalse(self.orchestrator._right.is_in_dropout_grace)
        self.assertIsNotNone(p4)
        # Resumed smoothly from p1 without jumping to None or stalling
        self.assertGreater(p4[0], p1[0])
        self.assertGreater(p4[1], p1[1])

    # -------------------------------------------------------------------------
    # 3. Hand loss followed by successful reacquisition
    # -------------------------------------------------------------------------
    def test_hand_loss_followed_by_successful_reacquisition(self) -> None:
        """
        Verify that when a hand is missing for > grace timeout, it transitions to
        genuine loss (filters reset), and upon returning after a prolonged absence,
        it reacquires cleanly and resumes tracking.
        """
        now = 200.0
        dt = 1.0 / 30.0

        # Step 1: Active hand
        h1 = HandsResult(right=make_hand(0.40, 0.40), right_score=0.90)
        with patch("time.perf_counter", return_value=now):
            self.orchestrator.process(h1)
        self.assertIsNotNone(self.orchestrator.cursor_pos)

        # Step 2: Hand missing for 5 frames (> 120ms timeout)
        h_none = HandsResult(right=None)
        for i in range(1, 6):
            with patch("time.perf_counter", return_value=now + i * dt):
                self.orchestrator.process(h_none)

        # Now genuinely lost: grace is over, position cleared, owner NONE
        self.assertFalse(self.orchestrator._right.is_in_dropout_grace)
        self.assertIsNone(self.orchestrator._right.cursor_pos)
        self.assertEqual(self.orchestrator.pointer_owner, "NONE")

        # Step 3: Hand returns 1.0s later
        now_return = now + 1.0
        h_return = HandsResult(right=make_hand(0.45, 0.45), right_score=0.90)
        with patch("time.perf_counter", return_value=now_return):
            self.orchestrator.process(h_return)

        # Successfully reacquired!
        self.assertEqual(self.orchestrator.pointer_owner, "RIGHT")
        self.assertIsNotNone(self.orchestrator.cursor_pos)

    # -------------------------------------------------------------------------
    # 4. A different hand identity appearing
    # -------------------------------------------------------------------------
    def test_different_hand_identity_appearing_rebaselines_safely(self) -> None:
        """
        Verify that when pointer ownership transfers between hands (e.g. RIGHT to LEFT),
        the anchor is rebaselined to current cursor pos, preventing an explosive jump.
        """
        now = 300.0
        dt = 1.0 / 30.0

        # Step 1: Right hand active at (0.40, 0.40)
        h_right = HandsResult(right=make_hand(0.40, 0.40), right_score=0.90)
        with patch("time.perf_counter", return_value=now):
            self.orchestrator.process(h_right)
        pos_right = self.orchestrator.cursor_pos
        self.assertEqual(self.orchestrator.pointer_owner, "RIGHT")

        # Step 2: Right hand departs, Left hand appears at (0.75, 0.75) pointing
        left_hand_lms = make_hand(0.75, 0.75)
        h_left = HandsResult(left=left_hand_lms, left_score=0.90)
        # Left hand requires pointing posture (index extended, others curled)
        self.orchestrator._left.is_pointing = True
        self.orchestrator._left.cursor_pos = (1500, 800)

        # Advance past 80ms owner switch delay
        with patch("time.perf_counter", return_value=now + 0.10):
            self.orchestrator.process(h_left)

        # Owner switched to LEFT smoothly
        self.assertEqual(self.orchestrator.pointer_owner, "LEFT")
        # Step was safely clamped and rebaselined without teleportation
        pos_left = self.orchestrator.cursor_pos
        self.assertIsNotNone(pos_left)
        step_disp = math.hypot(pos_left[0] - pos_right[0], pos_left[1] - pos_right[1])
        # Maximum step bound strictly enforced
        self.assertLessEqual(step_disp, 960.0 + 1e-6)

    # -------------------------------------------------------------------------
    # 5. Stale camera frames and long inference delays
    # -------------------------------------------------------------------------
    def test_stale_camera_frames_and_long_inference_delays(self) -> None:
        """
        Verify:
        a) FrameFreshnessDetector detects and rejects consecutive identical buffers.
        b) OneEuroFilter handles large dt (>150ms) without derivative speed spikes.
        """
        # Part A: Freshness detector
        detector = FrameFreshnessDetector(stale_threshold_count=2)
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        dummy_frame[10:50, 10:50] = 200

        self.assertTrue(detector.check(dummy_frame))   # frame 1 fresh
        self.assertTrue(detector.check(dummy_frame))   # frame 2 identical (below threshold)
        self.assertFalse(detector.check(dummy_frame))  # frame 3 identical -> STALE rejected!
        self.assertTrue(detector.is_stale)

        # New distinct frame recovers freshness
        new_frame = dummy_frame.copy()
        new_frame[0, 0] = 255
        self.assertTrue(detector.check(new_frame))
        self.assertFalse(detector.is_stale)

        # Part B: Filter derivative resilience across large gap (> 150ms)
        f = OneEuroFilter(freq=30.0, mincutoff=0.40, beta=0.035)
        f(0.50, 0.0)

        # 200ms inference stall / camera pause, hand moved by 0.10
        out = f(0.60, 0.200)
        # Because gap > 150ms, derivative was reset; output blends cleanly without spiking
        self.assertGreater(out, 0.50)
        self.assertLessEqual(out, 0.60)

    # -------------------------------------------------------------------------
    # 6. No cursor movement during uncertain tracking
    # -------------------------------------------------------------------------
    def test_no_cursor_movement_during_uncertain_tracking(self) -> None:
        """
        Verify that when hand landmark detection confidence is below 0.40 (uncertain),
        cursor movement is suppressed (safe freeze), issuing zero actuator movements.
        """
        now = 400.0
        # Frame 1: Valid high-confidence tracking
        h_good = HandsResult(right=make_hand(0.50, 0.50), right_score=0.85)
        with patch("time.perf_counter", return_value=now):
            self.orchestrator.process(h_good)

        pos_initial = self.orchestrator.cursor_pos
        self.assertIsNotNone(pos_initial)
        initial_moves = self.actuator.move.call_count

        # Frame 2: Hand landmarks reported with uncertain confidence (0.25 < 0.40)
        h_uncertain = HandsResult(right=make_hand(0.65, 0.65), right_score=0.25)
        with patch("time.perf_counter", return_value=now + 0.033):
            self.orchestrator.process(h_uncertain)

        # Cursor position must NOT move to the uncertain target coordinates
        pos_after = self.orchestrator.cursor_pos
        self.assertEqual(pos_after, pos_initial)
        # Zero additional actuator moves issued for uncertain frame
        self.assertEqual(self.actuator.move.call_count, initial_moves)

        # Frame 3: Confidence restores to 0.90
        h_recovered = HandsResult(right=make_hand(0.53, 0.53), right_score=0.90)
        with patch("time.perf_counter", return_value=now + 0.066):
            self.orchestrator.process(h_recovered)

        self.assertNotEqual(self.orchestrator.cursor_pos, pos_initial)
        self.assertEqual(self.actuator.move.call_count, initial_moves + 1)

    # -------------------------------------------------------------------------
    # 7. No excessive cursor jump after reacquisition
    # -------------------------------------------------------------------------
    def test_no_excessive_cursor_jump_after_reacquisition(self) -> None:
        """
        Verify that when a hand returns at an extreme coordinate offset (e.g. 1500px away),
        the reacquisition step is bounded and does not emit an uncontrolled jump.
        """
        now = 500.0
        # Initialize at center
        self.orchestrator.set_cursor_anchor((960, 540))

        # Reacquire at extreme bottom right of webcam frame
        h_extreme = HandsResult(right=make_hand(0.95, 0.95), right_score=0.90)

        with patch("time.perf_counter", return_value=now + 0.033):
            self.orchestrator.process(h_extreme)

        new_pos = self.orchestrator.cursor_pos
        self.assertIsNotNone(new_pos)
        step_disp = math.hypot(new_pos[0] - 960, new_pos[1] - 540)

        # Dynamic step limit is capped at 960px in normal mode
        self.assertLessEqual(step_disp, 960.0 + 1e-6)

    # -------------------------------------------------------------------------
    # 8. Preservation of safety limits and existing gestures
    # -------------------------------------------------------------------------
    def test_conservative_phase_b_step_limit_preserved(self) -> None:
        """
        Verify that under max_step_limit (Phase B conservative mode, e.g. 48.0px),
        all steps — including rapid sweeps — remain strictly <= 48.0px.
        """
        orch = GestureOrchestrator(
            actuator=self.actuator,
            desktop=self.desktop,
            trackpad=self.trackpad,
            initial_cursor_anchor=(500, 500),
            max_step_limit=48.0,
        )

        now = 600.0
        # Frame 1: establishes anchor
        h1 = HandsResult(right=make_hand(0.50, 0.50), right_score=0.95)
        with patch("time.perf_counter", return_value=now):
            orch.process(h1)

        pos1 = orch.cursor_pos
        self.assertIsNotNone(pos1)

        # Frame 2: huge hand jump across screen
        h2 = HandsResult(right=make_hand(0.90, 0.90), right_score=0.95)
        with patch("time.perf_counter", return_value=now + 0.033):
            orch.process(h2)

        pos2 = orch.cursor_pos
        self.assertIsNotNone(pos2)
        step = math.hypot(pos2[0] - pos1[0], pos2[1] - pos1[1])
        self.assertLessEqual(step, 48.0 + 1e-6, f"Phase B step limit violated: {step:.2f}px > 48.0px")


if __name__ == "__main__":
    unittest.main()

# test_power_runtime_integration.py
"""
Synthetic integration tests for Air Point Stage 3: Runtime Integration.

Verifies the integration contracts between main.py, PowerStateManager,
FrameFreshnessDetector, GestureOrchestrator, and MouseActuator:
1. Zero actuator calls during SKIP, PROBE, and CONFIRMATION cadences.
2. Zero actuator calls during detected freeze frames (consecutive identical buffers).
3. 120-second sleep transition boundary with processor state reset.
4. Immediate inactivity accumulator reset on camera gap / stall > 150ms.
5. Post-wake cursor anchor synchronization via actuator.get_cursor_pos().
6. Fail-closed suppression if cursor query returns None.
7. Thread-safe settings dispatch via settings_queue and dynamic power_save toggle.
8. Robustness of extract_hand_measurements under invalid/degenerate landmarks.

Strictly synthetic: no live camera hardware, no real OS mouse/keyboard actions,
no workstation locking. Compatible with test_guard.py.
"""

import math
from queue import Queue
import time
from typing import Any
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from core.actuator import MouseActuator
from core.camera import FrameFreshnessDetector
from core.display import TrackpadZone, VirtualDesktop
from core.gestures.orchestrator import GestureOrchestrator
from core.power_state_machine import (
    InferenceCadence,
    PowerDecision,
    PowerState,
    PowerStateManager,
    PowerTransitionEvent,
)
from core.tracker import HandsResult, Landmark
from main import extract_hand_measurements


class MockActuator:
    """Mock mouse actuator that captures every call without issuing Win32 SendInput."""

    def __init__(self, width: int = 1920, height: int = 1080) -> None:
        self.total_width = width
        self.total_height = height
        self.is_dragging = False
        self.cursor_pos: tuple[int, int] | None = (960, 540)
        self.move_calls: list[tuple[int, int]] = []
        self.move_to_calls: list[tuple[int, int]] = []
        self.click_calls: int = 0
        self.press_calls: int = 0
        self.release_calls: int = 0
        self.drag_start_calls: int = 0
        self.drag_end_calls: int = 0

    def get_cursor_pos(self) -> tuple[int, int] | None:
        return self.cursor_pos

    def move(self, x: int, y: int) -> bool:
        self.move_calls.append((int(x), int(y)))
        if self.cursor_pos is not None:
            self.cursor_pos = (self.cursor_pos[0] + int(x), self.cursor_pos[1] + int(y))
        return True

    def move_to(self, x: int, y: int) -> bool:
        self.move_to_calls.append((int(x), int(y)))
        self.cursor_pos = (int(x), int(y))
        return True

    def left_click(self, x: int | None = None, y: int | None = None) -> bool:
        self.click_calls += 1
        return True

    def right_click(self, x: int | None = None, y: int | None = None) -> bool:
        self.click_calls += 1
        return True

    def double_click(self) -> bool:
        self.click_calls += 1
        return True

    def drag_start(self) -> bool:
        self.is_dragging = True
        self.drag_start_calls += 1
        return True

    def drag_end(self) -> bool:
        self.is_dragging = False
        self.drag_end_calls += 1
        return True

    @property
    def total_action_count(self) -> int:
        return (
            len(self.move_calls)
            + len(self.move_to_calls)
            + self.click_calls
            + self.press_calls
            + self.release_calls
            + self.drag_start_calls
            + self.drag_end_calls
        )


def _make_mock_landmarks(
    cx: float = 0.5,
    cy: float = 0.5,
    palm_width: float = 0.15,
) -> list[Landmark]:
    """Create a minimal valid set of 21 landmarks with known palm center and width."""
    half_w = palm_width / 2.0
    landmarks = [Landmark(x=cx, y=cy, z=0.0) for _ in range(21)]
    # Landmark 0: wrist
    landmarks[0] = Landmark(x=cx, y=cy + half_w, z=0.0)
    # Landmark 5: index MCP
    landmarks[5] = Landmark(x=cx - half_w, y=cy - half_w, z=0.0)
    # Landmark 17: pinky MCP
    landmarks[17] = Landmark(x=cx + half_w, y=cy - half_w, z=0.0)
    # Landmark 8: index fingertip (for pointer interaction)
    landmarks[8] = Landmark(x=cx, y=cy - half_w - 0.05, z=0.0)
    # Landmark 4: thumb tip
    landmarks[4] = Landmark(x=cx - half_w - 0.03, y=cy, z=0.0)
    return landmarks


class TestPowerRuntimeIntegration(unittest.TestCase):
    def setUp(self) -> None:
        self.simulated_time = 1000.0
        self.desktop = VirtualDesktop(total_width=1920, total_height=1080, monitor_count=1)
        self.trackpad = TrackpadZone(x_min=0.2, x_max=0.8, y_min=0.2, y_max=0.8)
        self.actuator = MockActuator(1920, 1080)
        self.processor = GestureOrchestrator(self.actuator, self.desktop, self.trackpad)
        self.power_manager = PowerStateManager(
            inactivity_timeout_s=120.0,
            wake_trigger_velocity=0.50,
            wake_confirm_velocity=0.40,
            wake_confirm_duration_s=0.15,
            wake_dwell_duration_s=10.0,
            probe_stride=3,
            min_confirm_frames=3,
            max_healthy_frame_interval_s=0.150,
            clock_fn=lambda: self.simulated_time,
        )
        self.freshness_detector = FrameFreshnessDetector(stale_threshold_count=3)
        self.settings_queue: Queue[dict[str, Any]] = Queue()
        self.last_accepted_frame_time = self.simulated_time
        self.last_frame_id = -1

    def _drain_settings(self) -> None:
        """Mirror of drain_settings_queue from main.py."""
        while not self.settings_queue.empty():
            new_settings = self.settings_queue.get_nowait()
            if "power_save" in new_settings:
                evt = self.power_manager.set_enabled(new_settings["power_save"])
                if evt == PowerTransitionEvent.FEATURE_DISABLED:
                    queried = self.actuator.get_cursor_pos()
                    self.processor.set_cursor_anchor(queried)

    def _step_pipeline(
        self,
        frame: np.ndarray | None,
        frame_id: int,
        hands: HandsResult | None = None,
        dt: float = 0.0333333,
    ) -> tuple[PowerDecision | None, bool]:
        """
        Executes one iteration of the main.py processing loop.
        Returns (decision, was_processed_by_gesture_orchestrator).
        """
        self._drain_settings()
        self.simulated_time += dt
        t_now = self.simulated_time

        # 1. Timeout / duplicate frame check
        if frame is None or frame_id == self.last_frame_id:
            elapsed = t_now - self.last_accepted_frame_time
            if frame is None or elapsed > 0.150:
                self.power_manager.evaluate_cadence(now=t_now, frame_valid=False, frame_id=frame_id)
            return None, False

        # 2. Freshness check
        is_fresh = self.freshness_detector.check(frame)
        elapsed = t_now - self.last_accepted_frame_time
        if not is_fresh or elapsed > 0.150:
            self.power_manager.evaluate_cadence(now=t_now, frame_valid=False, frame_id=frame_id)
            return None, False

        # Fresh frame accepted
        self.last_accepted_frame_time = t_now
        self.last_frame_id = frame_id

        interaction_guard_clear = not self.actuator.is_dragging
        decision = self.power_manager.evaluate_cadence(
            now=t_now,
            frame_valid=True,
            frame_id=frame_id,
            interaction_guard_clear=interaction_guard_clear,
        )

        if decision.cadence == InferenceCadence.SKIP:
            return decision, False

        elif decision.cadence in (InferenceCadence.PROBE, InferenceCadence.CONFIRMATION):
            has_hands_m, p_center, p_width, p_hand_id = extract_hand_measurements(hands)
            probe_dec = self.power_manager.update_probe_measurements(
                now=self.simulated_time,
                has_hands=has_hands_m,
                palm_center=p_center,
                palm_width=p_width,
                hand_id=p_hand_id,
            )
            if probe_dec.transition_event == PowerTransitionEvent.WAKE_CONFIRMED:
                queried = self.actuator.get_cursor_pos()
                self.processor.set_cursor_anchor(queried)
            # Zero actuator calls during probe/confirmation
            return probe_dec, False

        else:  # FULL_RATE (NORMAL)
            has_hands_m, p_center, p_width, p_hand_id = extract_hand_measurements(hands)
            norm_dec = self.power_manager.update_normal_activity(
                now=self.simulated_time,
                has_hands=has_hands_m,
                palm_center=p_center,
                palm_width=p_width,
                hand_id=p_hand_id,
                interaction_guard_clear=interaction_guard_clear,
            )
            if norm_dec.transition_event == PowerTransitionEvent.ENTERED_POWER_SAVE:
                self.processor.process(None, None)
                return norm_dec, False
            else:
                self.processor.process(hands, None)
                return norm_dec, True

    # ── Test 1: Zero Actuator Calls during SKIP, PROBE, and CONFIRMATION ───────

    def test_zero_actuator_calls_during_power_save_cadences(self) -> None:
        """
        Verify that during POWER_SAVE mode, regardless of whether a frame is
        a SKIP, a PROBE, or a CONFIRMATION, ZERO actuator actions are emitted.
        """
        self.power_manager.set_enabled(True)
        self.power_manager._state = PowerState.POWER_SAVE
        self.power_manager._last_healthy_frame_ts = self.simulated_time

        hand_result = HandsResult()
        hand_result.right = _make_mock_landmarks(0.5, 0.5)

        # Baseline count
        initial_actions = self.actuator.total_action_count

        # Step 9 frames through POWER_SAVE: with probe_stride=3, this includes:
        # Frames 1,2: SKIP
        # Frame 3: PROBE
        # Frames 4,5: SKIP
        # Frame 6: PROBE
        # Frames 7,8: SKIP
        # Frame 9: PROBE
        for fid in range(1, 10):
            frame = np.full((100, 100, 3), fid, dtype=np.uint8)
            dec, was_processed = self._step_pipeline(frame, fid, hands=hand_result)
            self.assertFalse(was_processed, f"Frame {fid} must not be processed by gesture orchestrator")

        # Entire 9 frames in POWER_SAVE must produce 0 actuator actions!
        self.assertEqual(self.actuator.total_action_count, initial_actions)
        self.assertEqual(len(self.actuator.move_calls), 0)
        self.assertEqual(self.actuator.click_calls, 0)

    # ── Test 2: Zero Actuator Calls during Detected Freeze Frames ──────────────

    def test_zero_actuator_calls_during_frozen_camera_buffers(self) -> None:
        """
        When consecutive identical frames arrive, FrameFreshnessDetector detects
        stale buffer freeze. The pipeline must reject them and emit ZERO actuator calls.
        """
        self.power_manager.set_enabled(True)
        self.power_manager._last_healthy_frame_ts = self.simulated_time

        frozen_frame = np.full((100, 100, 3), 123, dtype=np.uint8)
        hand_result = HandsResult()
        hand_result.right = _make_mock_landmarks(0.5, 0.5)

        # Establish baseline frame 1
        dec1, p1 = self._step_pipeline(frozen_frame, 1, hands=hand_result)
        # Identical frame 2 (stale count 1)
        dec2, p2 = self._step_pipeline(frozen_frame, 2, hands=hand_result)
        # Identical frame 3 (stale count 2)
        dec3, p3 = self._step_pipeline(frozen_frame, 3, hands=hand_result)

        actuator_actions_before_freeze = self.actuator.total_action_count

        # Identical frame 4 (stale count 3 -> THRESHOLD REACHED -> FRESHNESS REJECTED!)
        dec4, p4 = self._step_pipeline(frozen_frame, 4, hands=hand_result)
        self.assertIsNone(dec4, "Stale frame 4 must be rejected before cadence evaluation")
        self.assertFalse(p4, "Stale frame 4 must not invoke orchestrator")

        # Identical frame 5 (still stale)
        dec5, p5 = self._step_pipeline(frozen_frame, 5, hands=hand_result)
        self.assertIsNone(dec5)
        self.assertFalse(p5)

        # Confirm zero new actuator calls during the freeze
        self.assertEqual(self.actuator.total_action_count, actuator_actions_before_freeze)
        self.assertTrue(self.power_manager._had_camera_gap)
        self.assertEqual(self.power_manager.accumulated_inactive_s, 0.0)

    # ── Test 3: 120-Second Sleep Transition Boundary ──────────────────────────

    def test_120s_sleep_transition_boundary(self) -> None:
        """
        In NORMAL mode with power_save enabled:
        Continuous stationary frames accumulate inactivity.
        At t = 120.0s, pipeline triggers ENTERED_POWER_SAVE and calls
        processor.process(None, None) to cleanly clear state.
        """
        self.power_manager.set_enabled(True)
        self.power_manager._last_healthy_frame_ts = self.simulated_time

        hand_result = HandsResult()
        hand_result.right = _make_mock_landmarks(0.5, 0.5)

        dt = 1.0 / 30.0
        # Step 3599 frames (119.966s)
        for fid in range(1, 3600):
            frame = np.full((10, 10, 3), fid % 250, dtype=np.uint8)
            dec, processed = self._step_pipeline(frame, fid, hands=hand_result, dt=dt)
            self.assertEqual(self.power_manager.state, PowerState.NORMAL)

        # Frame 3600 crosses the 120.0s threshold
        frame_120 = np.full((10, 10, 3), 251, dtype=np.uint8)
        dec_120, processed_120 = self._step_pipeline(frame_120, 3600, hands=hand_result, dt=dt)

        self.assertEqual(self.power_manager.state, PowerState.POWER_SAVE)
        self.assertEqual(dec_120.transition_event, PowerTransitionEvent.ENTERED_POWER_SAVE)
        self.assertFalse(processed_120, "At sleep transition, orchestrator must receive (None, None) not real hands")

    # ── Test 4: Immediate Reset on Camera Gap / Stall > 150ms ─────────────────

    def test_immediate_reset_on_camera_stall_exceeding_150ms(self) -> None:
        """
        When an inter-frame interval exceeds 150ms (continuity threshold),
        the pipeline must immediately classify it as a discontinuity,
        reset accumulated inactivity to 0.0s, and suppress motion tracking.
        """
        self.power_manager.set_enabled(True)
        self.power_manager._last_healthy_frame_ts = self.simulated_time

        hand_result = HandsResult()
        hand_result.right = _make_mock_landmarks(0.5, 0.5)

        # Accumulate ~2 seconds of inactivity
        for fid in range(1, 61):
            frame = np.full((10, 10, 3), fid, dtype=np.uint8)
            self._step_pipeline(frame, fid, hands=hand_result, dt=0.0333333)

        self.assertGreater(self.power_manager.accumulated_inactive_s, 1.9)

        # Camera stalls: next frame arrives 250ms later (> 150ms)
        stall_frame = np.full((10, 10, 3), 99, dtype=np.uint8)
        dec, processed = self._step_pipeline(stall_frame, 61, hands=hand_result, dt=0.250)

        # Stall resets inactivity to 0.0s immediately!
        self.assertEqual(self.power_manager.accumulated_inactive_s, 0.0)
        self.assertEqual(self.power_manager._last_frame_dt, 0.0)

    # ── Test 5: Post-Wake Cursor Anchor Synchronization ───────────────────────

    def test_post_wake_cursor_anchor_synchronization(self) -> None:
        """
        When waking from POWER_SAVE via confirmed intentional motion,
        the pipeline must query actuator.get_cursor_pos() and synchronize
        processor.set_cursor_anchor(queried) on the main loop thread.
        """
        self.power_manager.set_enabled(True)
        self.power_manager._state = PowerState.POWER_SAVE
        self.power_manager._last_healthy_frame_ts = self.simulated_time

        # Initial physical cursor position
        self.actuator.cursor_pos = (750, 430)

        # Force cadence to PROBE for baseline
        self.power_manager._probe_counter = self.power_manager._probe_stride - 1
        # Baseline probe: palm at (0.1, 0.5)
        h1 = HandsResult()
        h1.right = _make_mock_landmarks(cx=0.1, cy=0.5, palm_width=0.15)
        f1 = np.full((10, 10, 3), 1, dtype=np.uint8)
        self._step_pipeline(f1, 1, hands=h1, dt=0.0333333)

        # Force cadence to PROBE for arming frame
        self.power_manager._probe_counter = self.power_manager._probe_stride - 1
        # Probe 2: rapid motion to (0.35, 0.5) -> arms candidate (count = 1)
        h2 = HandsResult()
        h2.right = _make_mock_landmarks(cx=0.35, cy=0.5, palm_width=0.15)
        f2 = np.full((10, 10, 3), 2, dtype=np.uint8)
        self._step_pipeline(f2, 2, hands=h2, dt=0.0333333)
        self.assertTrue(self.power_manager.is_confirming_wake)

        # Confirmation Frame 2: motion to (0.45, 0.5) (count = 2)
        h3 = HandsResult()
        h3.right = _make_mock_landmarks(cx=0.45, cy=0.5, palm_width=0.15)
        f3 = np.full((10, 10, 3), 3, dtype=np.uint8)
        self._step_pipeline(f3, 3, hands=h3, dt=0.060)
        self.assertTrue(self.power_manager.is_confirming_wake)

        # Confirmation Frame 3: motion to (0.55, 0.5) at dt=0.100s (total elapsed >= 0.15s, count=3)
        h4 = HandsResult()
        h4.right = _make_mock_landmarks(cx=0.55, cy=0.5, palm_width=0.15)
        f4 = np.full((10, 10, 3), 4, dtype=np.uint8)
        dec4, _ = self._step_pipeline(f4, 4, hands=h4, dt=0.100)

        # Wake Confirmed!
        self.assertEqual(dec4.transition_event, PowerTransitionEvent.WAKE_CONFIRMED)
        self.assertEqual(self.power_manager.state, PowerState.NORMAL)

        # Cursor anchor must be synchronized to (750, 430)
        self.assertEqual(self.processor.trusted_cursor_anchor, (750, 430))
        self.assertEqual(self.processor._consecutive_jumps, 0)
        self.assertEqual(self.processor._last_move_time, 0.0)

    # ── Test 6: Fail-Closed Suppression If Cursor Query Returns None ──────────

    def test_post_wake_fail_closed_when_cursor_query_none(self) -> None:
        """
        If actuator.get_cursor_pos() returns None on wake (e.g. desktop coords unavailable),
        processor.set_cursor_anchor(None) must fail closed: no dummy anchor is invented,
        and movement remains safely suppressed until a valid anchor is established.
        """
        self.power_manager.set_enabled(True)
        self.power_manager._state = PowerState.POWER_SAVE
        self.power_manager._last_healthy_frame_ts = self.simulated_time

        # Simulate desktop query failure: returns None
        self.actuator.cursor_pos = None

        # Force cadence to PROBE for baseline
        self.power_manager._probe_counter = self.power_manager._probe_stride - 1
        # Probe 1: baseline
        h1 = HandsResult()
        h1.right = _make_mock_landmarks(cx=0.1, cy=0.5, palm_width=0.15)
        f1 = np.full((10, 10, 3), 1, dtype=np.uint8)
        self._step_pipeline(f1, 1, hands=h1, dt=0.0333333)

        # Force cadence to PROBE for arming frame
        self.power_manager._probe_counter = self.power_manager._probe_stride - 1
        # Probe 2: arm candidate
        h2 = HandsResult()
        h2.right = _make_mock_landmarks(cx=0.35, cy=0.5, palm_width=0.15)
        f2 = np.full((10, 10, 3), 2, dtype=np.uint8)
        self._step_pipeline(f2, 2, hands=h2, dt=0.0333333)

        # Confirmation Frame 2
        h3 = HandsResult()
        h3.right = _make_mock_landmarks(cx=0.45, cy=0.5, palm_width=0.15)
        f3 = np.full((10, 10, 3), 3, dtype=np.uint8)
        self._step_pipeline(f3, 3, hands=h3, dt=0.060)

        # Confirmation Frame 3: WAKE_CONFIRMED
        h4 = HandsResult()
        h4.right = _make_mock_landmarks(cx=0.55, cy=0.5, palm_width=0.15)
        f4 = np.full((10, 10, 3), 4, dtype=np.uint8)
        dec4, _ = self._step_pipeline(f4, 4, hands=h4, dt=0.100)

        self.assertEqual(dec4.transition_event, PowerTransitionEvent.WAKE_CONFIRMED)
        # Anchor must be None (fail closed)
        self.assertIsNone(self.processor.trusted_cursor_anchor)

        # When the next frame arrives in NORMAL mode, processor must NOT jump the cursor
        initial_moves = len(self.actuator.move_calls)
        f5 = np.full((10, 10, 3), 5, dtype=np.uint8)
        self._step_pipeline(f5, 5, hands=h4, dt=0.0333333)

        # Zero moves or safe fallback without jump
        self.assertEqual(len(self.actuator.move_calls), initial_moves)

    # ── Test 7: Thread-Safe Settings Dispatch ─────────────────────────────────

    def test_thread_safe_settings_dispatch_via_queue(self) -> None:
        """
        Settings changes enqueued from the UI thread must be safely drained
        on the main loop thread, dynamically toggling power optimization.
        Disabling optimization while in POWER_SAVE must immediately restore NORMAL
        and synchronize the cursor anchor.
        """
        self.assertFalse(self.power_manager.is_enabled)

        # 1. Enqueue enable
        self.settings_queue.put({"power_save": True})
        self._drain_settings()
        self.assertTrue(self.power_manager.is_enabled)

        # 2. Put system into POWER_SAVE
        self.power_manager._state = PowerState.POWER_SAVE
        self.actuator.cursor_pos = (1200, 700)

        # 3. User toggles power_save to False via UI
        self.settings_queue.put({"power_save": False})
        self._drain_settings()

        # State must immediately return to NORMAL
        self.assertFalse(self.power_manager.is_enabled)
        self.assertEqual(self.power_manager.state, PowerState.NORMAL)
        # Cursor anchor must be synchronized immediately
        self.assertEqual(self.processor.trusted_cursor_anchor, (1200, 700))

    # ── Test 8: Extract Hand Measurements Robustness ──────────────────────────

    def test_extract_hand_measurements_edge_cases(self) -> None:
        """
        Verify extract_hand_measurements fails closed under degenerate,
        missing, or non-finite landmark inputs.
        """
        # None input
        valid, center, width, h_id = extract_hand_measurements(None)
        self.assertFalse(valid)
        self.assertIsNone(center)

        # Empty HandsResult
        empty_res = HandsResult()
        valid, center, width, h_id = extract_hand_measurements(empty_res)
        self.assertFalse(valid)

        # Incomplete landmarks (< 18 points)
        short_res = HandsResult()
        short_res.right = [Landmark(x=0.5, y=0.5, z=0.0) for _ in range(10)]
        valid, center, width, h_id = extract_hand_measurements(short_res)
        self.assertFalse(valid)

        # Degenerate palm width (< 0.001)
        deg_res = HandsResult()
        deg_res.right = [Landmark(x=0.5, y=0.5, z=0.0) for _ in range(21)]
        valid, center, width, h_id = extract_hand_measurements(deg_res)
        self.assertFalse(valid)

        # Non-finite coordinates (NaN or Inf)
        nan_res = HandsResult()
        nan_lms = _make_mock_landmarks(0.5, 0.5)
        nan_lms[5] = Landmark(x=float("nan"), y=0.5, z=0.0)
        nan_res.right = nan_lms
        valid, center, width, h_id = extract_hand_measurements(nan_res)
        self.assertFalse(valid)

        inf_res = HandsResult()
        inf_lms = _make_mock_landmarks(0.5, 0.5)
        inf_lms[0] = Landmark(x=float("inf"), y=0.5, z=0.0)
        inf_res.left = inf_lms
        valid, center, width, h_id = extract_hand_measurements(inf_res)
        self.assertFalse(valid)

        # Valid left hand
        valid_res = HandsResult()
        valid_res.left = _make_mock_landmarks(0.3, 0.4, palm_width=0.12)
        valid, center, width, h_id = extract_hand_measurements(valid_res)
        self.assertTrue(valid)
        self.assertEqual(h_id, "left")
        self.assertAlmostEqual(width, 0.12, places=3)
        self.assertAlmostEqual(center[0], 0.3, places=3)
        self.assertAlmostEqual(center[1], 0.38, places=3)  # Centroid of (0, 5, 17) is cy - half_w / 3


if __name__ == "__main__":
    unittest.main()

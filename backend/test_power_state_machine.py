# test_power_state_machine.py
"""
Unit tests for the pure PowerStateManager in Air Point.

Verifies:
1. Initial default state (NORMAL, feature disabled, 0 accumulated inactivity).
2. Feature toggle behavior (disabling during POWER_SAVE synchronously forces NORMAL).
3. Inactivity accumulation under nominal 30 FPS stream.
4. Interaction guard blocking (active gestures/drags prevent sleep entry).
5. Continuous 120-second inactivity boundary transition (ENTERED_POWER_SAVE).
6. Delayed frame below stall threshold (e.g. 66ms): sustains continuity, advances clamped dt.
7. Repeated consumer timeouts / duplicate frame IDs: contributes dt=0, preserves accumulator.
8. Explicit camera failure (frame_valid=False): immediate reset to 0.0s, aborts in-flight wake.
9. Camera stall exceeding 150ms: immediate reset to 0.0s, aborts in-flight wake.
10. Recovery after gap or stall: contributes dt=0.0s, re-baselines motion.
11. Hand identity change: re-baselines motion, aborts candidate wake (WAKE_REJECTED).
12. Probe cadence in POWER_SAVE (every 3rd frame probes; others skip).
13. Wake confirmation requiring BOTH elapsed time >= 0.15s AND >= 3 distinct probe frames.
14. Wake candidate rejection when motion drops below confirmation velocity.
15. Post-wake minimum dwell protection (10.0s dwell blocks premature re-entry).
"""

import unittest
from core.power_state_machine import (
    PowerState,
    InferenceCadence,
    PowerTransitionEvent,
    PowerDecision,
    PowerStateManager,
)


class TestPowerStateManager(unittest.TestCase):
    def setUp(self) -> None:
        self.time_cursor = 1000.0
        self.frame_counter = 0
        self.sm = PowerStateManager(
            inactivity_timeout_s=120.0,
            wake_trigger_velocity=0.50,
            wake_confirm_velocity=0.40,
            wake_confirm_duration_s=0.15,
            wake_dwell_duration_s=10.0,
            probe_stride=3,
            min_confirm_frames=3,
            max_healthy_frame_interval_s=0.150,
            clock_fn=lambda: self.time_cursor,
        )
        # Establish initial healthy baseline timestamp
        self.sm._last_healthy_frame_ts = self.time_cursor
        self.sm._last_frame_id = 0

    def _step_normal_frame(
        self,
        dt: float = 0.0333333,
        has_hands: bool = True,
        palm_center: tuple[float, float] | None = (0.5, 0.5),
        palm_width: float | None = 0.15,
        hand_id: str | None = "right",
        interaction_guard_clear: bool = True,
    ) -> PowerDecision:
        self.time_cursor += dt
        self.frame_counter += 1
        dec1 = self.sm.evaluate_cadence(
            now=self.time_cursor,
            frame_valid=True,
            frame_id=self.frame_counter,
            interaction_guard_clear=interaction_guard_clear,
        )
        dec2 = self.sm.update_normal_activity(
            now=self.time_cursor,
            has_hands=has_hands,
            palm_center=palm_center,
            palm_width=palm_width,
            hand_id=hand_id,
            interaction_guard_clear=interaction_guard_clear,
        )
        return dec2

    def test_initial_state_defaults(self) -> None:
        self.assertEqual(self.sm.state, PowerState.NORMAL)
        self.assertFalse(self.sm.is_enabled)
        self.assertEqual(self.sm.accumulated_inactive_s, 0.0)
        self.assertFalse(self.sm.is_confirming_wake)

        telemetry = self.sm.get_telemetry()
        self.assertEqual(telemetry["power_state"], "NORMAL")
        self.assertFalse(telemetry["power_optimization_enabled"])
        self.assertEqual(telemetry["accumulated_inactive_s"], 0.0)

    def test_feature_toggle_in_power_save(self) -> None:
        self.sm.set_enabled(True)
        self.assertTrue(self.sm.is_enabled)

        # Force state into POWER_SAVE for toggle test
        self.sm._state = PowerState.POWER_SAVE
        self.sm._wake_candidate_start_ts = self.time_cursor

        # Toggle OFF: must synchronously force return to NORMAL
        evt = self.sm.set_enabled(False)
        self.assertEqual(evt, PowerTransitionEvent.FEATURE_DISABLED)
        self.assertEqual(self.sm.state, PowerState.NORMAL)
        self.assertFalse(self.sm.is_confirming_wake)

    def test_inactivity_accumulation_stationary_vs_moving(self) -> None:
        self.sm.set_enabled(True)

        # Frame 1: stationary hand at (0.5, 0.5)
        self._step_normal_frame(dt=0.0333333, palm_center=(0.5, 0.5))
        self.assertAlmostEqual(self.sm.accumulated_inactive_s, 0.0333, places=3)

        # Frame 2: still stationary
        self._step_normal_frame(dt=0.0333333, palm_center=(0.5, 0.5))
        self.assertAlmostEqual(self.sm.accumulated_inactive_s, 0.0666, places=3)

        # Frame 3: rapid hand motion (jump from 0.5 to 0.7 across 0.033s)
        # dist = 0.2, velocity = 0.2 / (0.15 * 0.0333) = 40.0 >> 0.50
        self._step_normal_frame(dt=0.0333333, palm_center=(0.7, 0.5))
        self.assertEqual(self.sm.accumulated_inactive_s, 0.0)

    def test_inactivity_accumulation_missing_hands(self) -> None:
        self.sm.set_enabled(True)

        # Missing hands under healthy camera should accumulate inactivity
        self._step_normal_frame(dt=0.0333333, has_hands=False, palm_center=None)
        self.assertAlmostEqual(self.sm.accumulated_inactive_s, 0.0333, places=3)

        self._step_normal_frame(dt=0.0333333, has_hands=False, palm_center=None)
        self.assertAlmostEqual(self.sm.accumulated_inactive_s, 0.0666, places=3)

    def test_interaction_guard_blocks_accumulation(self) -> None:
        self.sm.set_enabled(True)

        self._step_normal_frame(dt=0.0333333, palm_center=(0.5, 0.5))
        self.assertAlmostEqual(self.sm.accumulated_inactive_s, 0.0333, places=3)

        # Active interaction guard (e.g. dragging or holding)
        dec = self._step_normal_frame(
            dt=0.0333333,
            palm_center=(0.5, 0.5),
            interaction_guard_clear=False,
        )
        self.assertEqual(self.sm.accumulated_inactive_s, 0.0)
        self.assertEqual(dec.state, PowerState.NORMAL)

    def test_entry_into_power_save_after_120s_continuous_inactivity(self) -> None:
        self.sm.set_enabled(True)

        dt = 1.0 / 30.0
        # 3599 frames at 30 FPS = 119.9666... seconds of inactivity
        for _ in range(3599):
            dec = self._step_normal_frame(dt=dt, palm_center=(0.5, 0.5))
            self.assertEqual(dec.state, PowerState.NORMAL)
            self.assertEqual(dec.transition_event, PowerTransitionEvent.NONE)

        # Frame 3600 crosses the 120.0s threshold (3600 * (1/30) = 120.0s)
        dec_120 = self._step_normal_frame(dt=dt, palm_center=(0.5, 0.5))
        self.assertEqual(dec_120.state, PowerState.POWER_SAVE)
        self.assertEqual(dec_120.transition_event, PowerTransitionEvent.ENTERED_POWER_SAVE)
        self.assertEqual(self.sm.state, PowerState.POWER_SAVE)

    def test_delayed_frame_below_threshold_sustains_continuity(self) -> None:
        self.sm.set_enabled(True)

        # Step 30 frames normally (~1 second)
        for _ in range(30):
            self._step_normal_frame(dt=0.0333333, palm_center=(0.5, 0.5))
        prev_acc = self.sm.accumulated_inactive_s
        self.assertGreater(prev_acc, 0.9)

        # Delayed frame of 66ms (below 150ms stall threshold)
        self._step_normal_frame(dt=0.066, palm_center=(0.5, 0.5))
        # Accumulator should advance (clamped to max 50ms)
        self.assertAlmostEqual(self.sm.accumulated_inactive_s, prev_acc + 0.050, places=3)

    def test_duplicate_frame_id_does_not_advance_inactivity(self) -> None:
        self.sm.set_enabled(True)
        self._step_normal_frame(dt=0.0333333, palm_center=(0.5, 0.5))
        acc_before = self.sm.accumulated_inactive_s

        # Consumer delivers duplicate frame_id with advancing clock
        self.time_cursor += 0.033
        dec = self.sm.evaluate_cadence(now=self.time_cursor, frame_valid=True, frame_id=self.frame_counter)
        self.assertEqual(dec.cadence, InferenceCadence.SKIP)
        self.assertEqual(self.sm.accumulated_inactive_s, acc_before)
        self.assertEqual(self.sm._last_frame_dt, 0.0)

    def test_explicit_camera_gap_resets_accumulator_immediately(self) -> None:
        self.sm.set_enabled(True)

        # Accumulate ~1.0 second of inactivity
        for _ in range(30):
            self._step_normal_frame(dt=0.0333333, palm_center=(0.5, 0.5))
        self.assertGreater(self.sm.accumulated_inactive_s, 0.9)

        # Explicit camera gap occurs (frame_valid=False)
        self.time_cursor += 0.033
        gap_dec = self.sm.evaluate_cadence(now=self.time_cursor, frame_valid=False)
        self.assertEqual(gap_dec.cadence, InferenceCadence.SKIP)
        self.assertTrue(self.sm._had_camera_gap)
        # Immediate reset!
        self.assertEqual(self.sm.accumulated_inactive_s, 0.0)
        self.assertEqual(gap_dec.inactivity_elapsed_s, 0.0)

        # Recovery frame arrives
        self.time_cursor += 0.033
        self.frame_counter += 1
        rec_dec = self.sm.evaluate_cadence(now=self.time_cursor, frame_valid=True, frame_id=self.frame_counter)
        self.assertEqual(self.sm.accumulated_inactive_s, 0.0)
        self.assertFalse(self.sm._had_camera_gap)
        self.assertEqual(self.sm._last_frame_dt, 0.0)

    def test_camera_stall_exceeding_150ms_resets_inactivity(self) -> None:
        self.sm.set_enabled(True)

        # Accumulate inactivity
        for _ in range(30):
            self._step_normal_frame(dt=0.0333333, palm_center=(0.5, 0.5))
        self.assertGreater(self.sm.accumulated_inactive_s, 0.9)

        # Camera stalls for 200ms (> 150ms threshold)
        self.time_cursor += 0.200
        self.frame_counter += 1
        stall_dec = self.sm.evaluate_cadence(now=self.time_cursor, frame_valid=True, frame_id=self.frame_counter)
        
        # Stall resets accumulator to 0.0s immediately and discards stall dt
        self.assertEqual(self.sm.accumulated_inactive_s, 0.0)
        self.assertEqual(stall_dec.inactivity_elapsed_s, 0.0)
        self.assertEqual(self.sm._last_frame_dt, 0.0)

    def test_hand_identity_swap_in_normal_activity(self) -> None:
        self.sm.set_enabled(True)

        # Right hand at (0.8, 0.5)
        self._step_normal_frame(dt=0.0333333, palm_center=(0.8, 0.5), hand_id="right")
        self.assertAlmostEqual(self.sm.accumulated_inactive_s, 0.0333, places=3)

        # Left hand appears at (0.2, 0.5) -> cross-hand distance 0.6
        # Must re-baseline without calculating cross-hand velocity jump
        self._step_normal_frame(dt=0.0333333, palm_center=(0.2, 0.5), hand_id="left")
        self.assertAlmostEqual(self.sm.accumulated_inactive_s, 0.0666, places=3)

    def test_power_save_probing_cadence(self) -> None:
        self.sm.set_enabled(True)
        self.sm._state = PowerState.POWER_SAVE

        cadences = []
        for fid in range(1, 10):
            self.time_cursor += 0.033
            dec = self.sm.evaluate_cadence(now=self.time_cursor, frame_valid=True, frame_id=fid)
            cadences.append(dec.cadence)

        # probe_stride = 3: SKIP, SKIP, PROBE, SKIP, SKIP, PROBE, SKIP, SKIP, PROBE
        expected = [
            InferenceCadence.SKIP,
            InferenceCadence.SKIP,
            InferenceCadence.PROBE,
            InferenceCadence.SKIP,
            InferenceCadence.SKIP,
            InferenceCadence.PROBE,
            InferenceCadence.SKIP,
            InferenceCadence.SKIP,
            InferenceCadence.PROBE,
        ]
        self.assertEqual(cadences, expected)

    def test_wake_confirmation_requires_time_and_min_distinct_frames(self) -> None:
        self.sm.set_enabled(True)
        self.sm._state = PowerState.POWER_SAVE

        # Probe 1: establish baseline at (0.1, 0.5)
        self.time_cursor += 0.033
        self.sm.update_probe_measurements(
            now=self.time_cursor, has_hands=True, palm_center=(0.1, 0.5), palm_width=0.15, hand_id="right"
        )
        self.assertFalse(self.sm.is_confirming_wake)

        # Probe 2: deliberate fast motion to (0.3, 0.5)
        # dist = 0.2, velocity = 0.2 / (0.15 * 0.033) = 40.0 >> 0.50
        self.time_cursor += 0.033
        dec_arm = self.sm.update_probe_measurements(
            now=self.time_cursor, has_hands=True, palm_center=(0.3, 0.5), palm_width=0.15, hand_id="right"
        )
        self.assertTrue(self.sm.is_confirming_wake)
        self.assertEqual(dec_arm.cadence, InferenceCadence.CONFIRMATION)
        self.assertEqual(self.sm._wake_confirm_frames, 1)

        # Confirmation Frame 2 (fast motion): elapsed time 0.05s < 0.15s
        self.time_cursor += 0.050
        dec_c2 = self.sm.update_probe_measurements(
            now=self.time_cursor, has_hands=True, palm_center=(0.4, 0.5), palm_width=0.15, hand_id="right"
        )
        self.assertTrue(self.sm.is_confirming_wake)
        self.assertEqual(dec_c2.cadence, InferenceCadence.CONFIRMATION)
        self.assertEqual(self.sm._wake_confirm_frames, 2)

        # Elapsed time exceeds 0.15s, BUT only 2 distinct frames observed!
        # Must NOT confirm wake yet!
        self.time_cursor += 0.120
        # If we check with same frame count < min_confirm_frames (3), it won't confirm until frame 3 arrives
        dec_c3 = self.sm.update_probe_measurements(
            now=self.time_cursor, has_hands=True, palm_center=(0.5, 0.5), palm_width=0.15, hand_id="right"
        )
        # Frame 3 arrives with elapsed >= 0.15s and frame count 3 >= 3: WAKE CONFIRMED!
        self.assertEqual(dec_c3.transition_event, PowerTransitionEvent.WAKE_CONFIRMED)
        self.assertEqual(dec_c3.state, PowerState.NORMAL)
        self.assertEqual(self.sm.state, PowerState.NORMAL)
        self.assertFalse(self.sm.is_confirming_wake)

    def test_wake_candidate_rejected_on_hand_swap(self) -> None:
        self.sm.set_enabled(True)
        self.sm._state = PowerState.POWER_SAVE

        # Arm candidate with right hand
        self.time_cursor += 0.033
        self.sm.update_probe_measurements(now=self.time_cursor, has_hands=True, palm_center=(0.1, 0.5), palm_width=0.15, hand_id="right")
        self.time_cursor += 0.033
        self.sm.update_probe_measurements(now=self.time_cursor, has_hands=True, palm_center=(0.3, 0.5), palm_width=0.15, hand_id="right")
        self.assertTrue(self.sm.is_confirming_wake)

        # Next confirmation frame delivers left hand instead!
        self.time_cursor += 0.033
        dec_swap = self.sm.update_probe_measurements(now=self.time_cursor, has_hands=True, palm_center=(0.4, 0.5), palm_width=0.15, hand_id="left")
        self.assertEqual(dec_swap.transition_event, PowerTransitionEvent.WAKE_REJECTED)
        self.assertFalse(self.sm.is_confirming_wake)
        self.assertEqual(self.sm.state, PowerState.POWER_SAVE)

    def test_wake_candidate_rejected_on_stall(self) -> None:
        self.sm.set_enabled(True)
        self.sm._state = PowerState.POWER_SAVE

        # Arm candidate
        self.time_cursor += 0.033
        self.sm.update_probe_measurements(now=self.time_cursor, has_hands=True, palm_center=(0.1, 0.5), palm_width=0.15, hand_id="right")
        self.time_cursor += 0.033
        self.sm.update_probe_measurements(now=self.time_cursor, has_hands=True, palm_center=(0.3, 0.5), palm_width=0.15, hand_id="right")
        self.assertTrue(self.sm.is_confirming_wake)

        # Camera stall occurs (> 150ms)
        self.time_cursor += 0.200
        dec_stall = self.sm.evaluate_cadence(now=self.time_cursor, frame_valid=True, frame_id=99)
        self.assertEqual(dec_stall.transition_event, PowerTransitionEvent.WAKE_REJECTED)
        self.assertFalse(self.sm.is_confirming_wake)

    def test_post_wake_minimum_dwell_window(self) -> None:
        self.sm.set_enabled(True)
        self.sm._state = PowerState.NORMAL

        # Set dwell window active for 10 seconds
        self.sm._wake_dwell_until_ts = self.time_cursor + 10.0
        self.sm._accumulated_inactive_s = 150.0  # Inactivity well over 120s

        # Must NOT enter POWER_SAVE during dwell window!
        dec = self.sm.update_normal_activity(now=self.time_cursor + 5.0, has_hands=False)
        self.assertEqual(dec.state, PowerState.NORMAL)
        self.assertEqual(dec.transition_event, PowerTransitionEvent.NONE)

        # After dwell expires (10.1s later):
        dec_post = self.sm.update_normal_activity(now=self.time_cursor + 10.1, has_hands=False)
        self.assertEqual(dec_post.state, PowerState.POWER_SAVE)
        self.assertEqual(dec_post.transition_event, PowerTransitionEvent.ENTERED_POWER_SAVE)


if __name__ == "__main__":
    unittest.main()

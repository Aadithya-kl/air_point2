# test_wakanda_lock_fix.py
"""
Regression tests for the Wakanda Forever workstation-lock path
(see AIRPOINT_WAKANDA_GESTURE_FIX_REPORT.md).

Every lock in this file is a mock: either `lock_fn` is injected, or
`ctypes.windll.user32.LockWorkStation` is replaced with a stub for the duration
of the test. No test here can lock the developer's workstation, and nothing
opens a camera or injects native input.

Coverage (numbers follow the task brief):
  1  recognizer initialises enabled in normal runtime
  2  recognizer stays disabled where explicitly configured
  3  correct pose recognised / 4 incorrect and partial poses rejected
  5  hold duration respected / 6 short accidental pose does not trigger
  7  one sustained gesture -> exactly one lock request
  8  cooldown prevents repeated activation / 9 release rearms
  10 Windows API failure is reported, not assumed successful
  11 automated tests cannot invoke a real lock
  12 the recognizer never runs while a left drag is active or pending
  +  HUD state vocabulary and callback result propagation
"""

from __future__ import annotations

import ctypes
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np

import config
import test_guard
from core.face_tracker import FaceResult
from core.gestures import wakanda_gesture as wg
from core.gestures.wakanda_gesture import WakandaGestureRecognizer, WakandaState, check_wakanda_pose, lock_workstation
from core.tracker import HandsResult
from test_wakanda_gesture import create_crossed_arms_hands, create_fist_landmarks, create_uncrossed_hands

FACE = FaceResult(detected=True, lip_center=(0.50, 0.35, 0.0), mouth_width=0.08)
NO_REAL_LOCK = {"AIRPOINT_DISABLE_REAL_LOCK": ""}  # force the real code path (always with a stubbed API)


class TestRuntimeEnablement(unittest.TestCase):
    def test_1_enabled_in_normal_runtime(self) -> None:
        self.assertTrue(config.WAKANDA_ENABLED)
        rec = WakandaGestureRecognizer(lock_fn=MagicMock(return_value=True))
        self.assertTrue(rec.enabled)
        self.assertEqual(rec.state, WakandaState.IDLE)
        self.assertEqual(rec.hud_text, "SEARCHING")

    def test_2_disabled_where_explicitly_configured(self) -> None:
        with patch.object(config, "WAKANDA_ENABLED", False):
            rec = WakandaGestureRecognizer(lock_fn=MagicMock(return_value=True))
        self.assertFalse(rec.enabled)
        self.assertEqual(rec.state, WakandaState.DISABLED)
        self.assertEqual(rec.hud_text, "DISABLED")
        self.assertFalse(rec.process(create_crossed_arms_hands(), FACE, now=5.0))
        self.assertEqual(rec.hud_text, "DISABLED")

        explicit = WakandaGestureRecognizer(lock_fn=MagicMock(return_value=True), enabled=False)
        self.assertEqual(explicit.state, WakandaState.DISABLED)

    def test_2b_runtime_toggle_round_trip(self) -> None:
        rec = WakandaGestureRecognizer(lock_fn=MagicMock(return_value=True))
        rec.enabled = False
        self.assertEqual(rec.state, WakandaState.DISABLED)
        rec.enabled = True
        self.assertEqual(rec.state, WakandaState.IDLE)
        self.assertEqual(rec.hud_text, "SEARCHING")


class TestPoseRecognition(unittest.TestCase):
    def test_3_correct_pose_recognised(self) -> None:
        ok, reason = check_wakanda_pose(create_crossed_arms_hands(), FACE)
        self.assertTrue(ok, reason)

    def test_4_incorrect_and_partial_poses_rejected(self) -> None:
        crossed = create_crossed_arms_hands()

        ok, reason = check_wakanda_pose(create_uncrossed_hands(), FACE)
        self.assertFalse(ok)
        self.assertIn("ARMS_NOT_CROSSED", reason)

        one_hand = HandsResult(left=crossed.left, right=None, left_score=0.9)
        ok, reason = check_wakanda_pose(one_hand, FACE)
        self.assertFalse(ok)
        self.assertEqual(reason, "BOTH_HANDS_REQUIRED")

        low_conf = HandsResult(left=crossed.left, right=crossed.right, left_score=0.3, right_score=0.9)
        ok, reason = check_wakanda_pose(low_conf, FACE)
        self.assertFalse(ok)
        self.assertIn("LOW_CONFIDENCE", reason)

        # Crossed arms but the left hand is open (index/middle/ring/pinky extended)
        open_left = [lm for lm in crossed.left]
        for tip, pip in ((8, 6), (12, 10), (16, 14), (20, 18)):
            tip_lm = open_left[tip]
            pip_lm = open_left[pip]
            open_left[tip] = type(tip_lm)(x=tip_lm.x, y=pip_lm.y - 0.05, z=0.0)
        partial = HandsResult(left=open_left, right=crossed.right, left_score=0.9, right_score=0.9)
        ok, reason = check_wakanda_pose(partial, FACE)
        self.assertFalse(ok)
        self.assertEqual(reason, "LEFT_HAND_NOT_FIST")

        # Recognizer surfaces the rejection reason on the HUD while searching
        rec = WakandaGestureRecognizer(lock_fn=MagicMock(return_value=True))
        rec.process(partial, FACE, now=1.0)
        self.assertEqual(rec.state, WakandaState.IDLE)
        self.assertEqual(rec.hud_text, "SEARCHING (LEFT_HAND_NOT_FIST)")
        self.assertEqual(rec.last_reject_reason, "LEFT_HAND_NOT_FIST")


class TestTimingAndSingleRequest(unittest.TestCase):
    def setUp(self) -> None:
        self.lock = MagicMock(return_value=True)
        self.cb = MagicMock()
        self.rec = WakandaGestureRecognizer(lock_fn=self.lock, enabled=True, hold_duration=2.0, grace_period=0.15, cooldown=2.0)
        self.rec.set_activation_callback(self.cb)
        self.crossed = create_crossed_arms_hands()
        self.uncrossed = create_uncrossed_hands()

    def test_5_and_6_hold_duration_respected_short_pose_never_triggers(self) -> None:
        t = 0.0
        self.rec.process(self.crossed, FACE, now=t)
        self.assertEqual(self.rec.hud_text, "POSE DETECTED")
        while t < 1.9:
            t += 0.1
            self.rec.process(self.crossed, FACE, now=t)
            self.assertEqual(self.rec.state, WakandaState.HOLDING)
        self.assertTrue(self.rec.hud_text.startswith("HOLDING 1.9/2.0s"))
        self.lock.assert_not_called()
        # Released just before the 2.0 s mark: no request, back to searching
        self.rec.process(self.uncrossed, FACE, now=t + 0.2)
        self.assertEqual(self.rec.state, WakandaState.IDLE)
        self.assertTrue(self.rec.hud_text.startswith("SEARCHING ("))
        self.lock.assert_not_called()
        self.cb.assert_not_called()

    def test_single_frame_never_triggers(self) -> None:
        self.rec.process(self.crossed, FACE, now=0.0)
        self.rec.process(HandsResult(), None, now=0.4)  # pose gone past the grace period
        self.assertEqual(self.rec.state, WakandaState.IDLE)
        self.lock.assert_not_called()

    def test_7_one_sustained_gesture_one_request(self) -> None:
        t = 0.0
        while t <= 10.0:
            self.rec.process(self.crossed, FACE, now=t)
            t += 0.1
        self.assertEqual(self.lock.call_count, 1)
        self.cb.assert_called_once_with(True)
        self.assertEqual(self.rec.state, WakandaState.COOLDOWN)
        self.assertEqual(self.rec.hud_text, "COOLDOWN (release arms to rearm)")
        self.assertTrue(self.rec.last_lock_accepted)

    def test_8_and_9_cooldown_then_release_rearms_and_second_gesture_fires_once(self) -> None:
        self.rec.process(self.crossed, FACE, now=0.0)
        self.rec.process(self.crossed, FACE, now=2.0)
        self.assertEqual(self.lock.call_count, 1)
        self.assertIn("LOCK REQUEST ACCEPTED", self.rec.hud_text)

        # Inside cooldown: no second request; the lock result stays visible for
        # RESULT_DISPLAY_S, then the HUD switches to the countdown
        self.rec.process(self.crossed, FACE, now=2.5)
        self.assertEqual(self.lock.call_count, 1)
        self.assertEqual(self.rec.state, WakandaState.COOLDOWN)
        self.assertIn("LOCK REQUEST ACCEPTED", self.rec.hud_text)
        self.rec.process(self.crossed, FACE, now=3.5)
        self.assertEqual(self.lock.call_count, 1)
        self.assertTrue(self.rec.hud_text.startswith("COOLDOWN ("), self.rec.hud_text)

        # Cooldown over but still crossed: must release first
        self.rec.process(self.crossed, FACE, now=4.5)
        self.assertEqual(self.rec.state, WakandaState.COOLDOWN)
        self.assertEqual(self.lock.call_count, 1)

        # Release -> rearm; a new deliberate hold fires exactly once more
        self.rec.process(self.uncrossed, FACE, now=4.6)
        self.assertEqual(self.rec.state, WakandaState.IDLE)
        self.rec.process(self.crossed, FACE, now=4.7)
        self.rec.process(self.crossed, FACE, now=6.7)
        self.assertEqual(self.lock.call_count, 2)
        self.assertEqual(self.cb.call_count, 2)


class TestLockResultReporting(unittest.TestCase):
    def test_10_failed_lock_request_is_reported_not_assumed(self) -> None:
        lock = MagicMock(return_value=False)
        cb = MagicMock()
        rec = WakandaGestureRecognizer(lock_fn=lock, enabled=True)
        rec.set_activation_callback(cb)
        crossed = create_crossed_arms_hands()
        rec.process(crossed, FACE, now=0.0)
        with self.assertLogs("core.gestures.wakanda_gesture", level="ERROR") as logs:
            rec.process(crossed, FACE, now=2.0)
        self.assertEqual(rec.hud_text, "LOCK REQUEST FAILED")
        self.assertIs(rec.last_lock_accepted, False)
        cb.assert_called_once_with(False)
        self.assertTrue(any("LOCK REQUEST FAILED" in m for m in logs.output))
        # Failure still consumes the gesture: cooldown and release apply, no retry storm
        rec.process(crossed, FACE, now=2.5)
        self.assertEqual(lock.call_count, 1)
        self.assertEqual(rec.state, WakandaState.COOLDOWN)

    def test_lock_function_exception_is_reported_as_failure(self) -> None:
        rec = WakandaGestureRecognizer(lock_fn=MagicMock(side_effect=OSError("boom")), enabled=True)
        crossed = create_crossed_arms_hands()
        rec.process(crossed, FACE, now=0.0)
        rec.process(crossed, FACE, now=2.0)
        self.assertIs(rec.last_lock_accepted, False)
        self.assertEqual(rec.hud_text, "LOCK REQUEST FAILED")

    def test_lock_workstation_reports_api_return_value(self) -> None:
        """user32.LockWorkStation is stubbed: 0 -> False with GetLastError logged, 1 -> True."""
        stub = MagicMock(return_value=0)
        with patch.dict(os.environ, NO_REAL_LOCK), \
             patch.object(wg, "_running_under_test_runner", return_value=False), \
             patch.object(ctypes.windll.user32, "LockWorkStation", stub), \
             patch.object(ctypes, "GetLastError", MagicMock(return_value=1359), create=True), \
             self.assertLogs("core.gestures.wakanda_gesture", level="ERROR") as logs:
            self.assertFalse(lock_workstation())
        stub.assert_called_once_with()
        self.assertTrue(any("REJECTED" in m and "1359" in m for m in logs.output))

        stub_ok = MagicMock(return_value=1)
        with patch.dict(os.environ, NO_REAL_LOCK), \
             patch.object(wg, "_running_under_test_runner", return_value=False), \
             patch.object(ctypes.windll.user32, "LockWorkStation", stub_ok), \
             self.assertLogs("core.gestures.wakanda_gesture", level="INFO") as logs:
            self.assertTrue(lock_workstation())
        stub_ok.assert_called_once_with()
        self.assertTrue(any("ACCEPTED" in m for m in logs.output))

    def test_lock_workstation_api_unavailable_reported(self) -> None:
        with patch.dict(os.environ, NO_REAL_LOCK), \
             patch.object(wg, "_running_under_test_runner", return_value=False), \
             patch.object(ctypes.windll, "user32", SimpleNamespace(), create=True), \
             self.assertLogs("core.gestures.wakanda_gesture", level="ERROR") as logs:
            self.assertFalse(lock_workstation())
        self.assertTrue(any("unavailable" in m for m in logs.output))


class TestAutomatedTestsCannotLock(unittest.TestCase):
    def test_11a_env_flag_mocks_the_lock_without_touching_user32(self) -> None:
        spy = MagicMock(return_value=1)
        with patch.dict(os.environ, {"AIRPOINT_DISABLE_REAL_LOCK": "1"}), \
             patch.object(ctypes.windll.user32, "LockWorkStation", spy):
            self.assertTrue(wg.real_lock_disabled())
            self.assertTrue(lock_workstation())
        spy.assert_not_called()

    def test_11b_test_guard_blocks_the_native_call(self) -> None:
        with patch.dict(os.environ, NO_REAL_LOCK), \
             patch.object(wg, "_running_under_test_runner", return_value=False), \
             patch.object(ctypes.windll.user32, "LockWorkStation", test_guard._blocked_lock_workstation), \
             self.assertLogs("core.gestures.wakanda_gesture", level="ERROR") as logs:
            self.assertFalse(lock_workstation())
        self.assertTrue(any("BlockedOSActionError" in m for m in logs.output))

    def test_11d_test_runner_detected_and_real_call_refused(self) -> None:
        """This process IS a test runner: without the mock flag the real call is refused before user32."""
        self.assertTrue(wg._running_under_test_runner())
        spy = MagicMock(return_value=1)
        with patch.dict(os.environ, NO_REAL_LOCK), \
             patch.object(ctypes.windll.user32, "LockWorkStation", spy), \
             self.assertLogs("core.gestures.wakanda_gesture", level="ERROR") as logs:
            self.assertFalse(lock_workstation())
        spy.assert_not_called()
        self.assertTrue(any("refusing a real LockWorkStation call under a test runner" in m for m in logs.output))

    def test_11e_product_entry_point_is_not_mistaken_for_a_test_runner(self) -> None:
        fake_main = SimpleNamespace(__spec__=None, __file__=r"C:\x\backend\main.py")
        with patch.dict(sys.modules, {"__main__": fake_main}):
            self.assertFalse(wg._running_under_test_runner())

    def test_11c_recognizer_reports_mock_acceptance_distinctly(self) -> None:
        rec = WakandaGestureRecognizer(lock_fn=lock_workstation, enabled=True)
        crossed = create_crossed_arms_hands()
        spy = MagicMock(return_value=1)
        with patch.dict(os.environ, {"AIRPOINT_DISABLE_REAL_LOCK": "1"}), \
             patch.object(ctypes.windll.user32, "LockWorkStation", spy):
            rec.process(crossed, FACE, now=0.0)
            rec.process(crossed, FACE, now=2.0)
        spy.assert_not_called()
        self.assertEqual(rec.hud_text, "LOCK REQUEST ACCEPTED (MOCK)")


class TestDragNonInterference(unittest.TestCase):
    def setUp(self) -> None:
        from core.display import TrackpadZone, VirtualDesktop
        from core.gestures.orchestrator import GestureOrchestrator
        from test_phase1_drag_reliability import ScriptedActuator, make_left

        self._saved = {k: getattr(config, k) for k in ("LEFT_DRAG_ENABLED", "LEFT_DRAG_START_NORM_DIST", "LEFT_DRAG_RELEASE_NORM_DIST", "LEFT_DRAG_CONFIRM_S", "LEFT_DRAG_LOST_TIMEOUT_S", "POINTER_ONLY_MODE")}
        config.POINTER_ONLY_MODE = False
        config.LEFT_DRAG_ENABLED = True
        config.LEFT_DRAG_START_NORM_DIST = 0.55
        config.LEFT_DRAG_RELEASE_NORM_DIST = 0.75
        config.LEFT_DRAG_CONFIRM_S = 0.10
        config.LEFT_DRAG_LOST_TIMEOUT_S = 0.150
        self.make_left = make_left
        self.actuator = ScriptedActuator()
        self.orch = GestureOrchestrator(self.actuator, VirtualDesktop(1920, 1080, 1), TrackpadZone(100, 540, 80, 400), initial_cursor_anchor=(960, 540))
        # Stand-in recognizer that claims a valid, holding pose on every frame it is asked
        self.wakanda = MagicMock(spec=WakandaGestureRecognizer)
        self.wakanda.process.return_value = True
        self.wakanda.is_holding = True

    def tearDown(self) -> None:
        for k, v in self._saved.items():
            setattr(config, k, v)

    def _step(self, hands: HandsResult, t: float) -> None:
        with patch("time.perf_counter", return_value=t):
            self.orch.process(hands)

    def test_12_recognizer_not_evaluated_while_drag_active_or_pending(self) -> None:
        from core.gestures.drag_controller import DragLockState

        # Frame 1 with the real recognizer (one pinching hand never matches the pose):
        # the grab becomes pending.
        pinched = HandsResult(left=self.make_left(pinch=0.35))
        self._step(pinched, 100.0)
        self.assertEqual(self.orch._left.drag_controller.state, DragLockState.GRAB_PENDING)

        # From now on a recognizer that would match on every frame is in place.
        self.orch._wakanda = self.wakanda
        self._step(pinched, 100.05)                        # still pending -> protected
        self.wakanda.process.assert_not_called()
        self._step(pinched, 100.12)                        # dwell satisfied -> GRAB_LOCKED
        self.assertEqual(self.orch._left.drag_controller.state, DragLockState.GRAB_LOCKED)
        for i in range(5):
            self._step(pinched, 100.15 + 0.033 * i)
        self.wakanda.process.assert_not_called()
        self.assertTrue(self.wakanda.reset.called)        # a stale hold is cleared, never completed
        self.assertTrue(self.actuator.is_dragging)
        self.assertEqual(self.actuator.up_attempts, 0, "the drag must not be released by the Wakanda path")
        self.assertEqual(self.orch._left.drag_controller.state, DragLockState.GRAB_LOCKED)

        # After a deliberate release the recognizer is evaluated again
        open_hand = HandsResult(left=self.make_left(open_palm=True))
        t = 100.4
        for _ in range(6):
            t += 0.033
            self._step(open_hand, t)
        self.assertFalse(self.actuator.is_dragging)
        self.assertEqual(self.actuator.up_attempts, 1)
        self.assertTrue(self.wakanda.process.called)


class TestHudIntegration(unittest.TestCase):
    def test_debug_hud_renders_wakanda_line_without_crash(self) -> None:
        from core.debug_overlay import draw_debug_frame

        rec = WakandaGestureRecognizer(lock_fn=MagicMock(return_value=True), enabled=True)
        rec.process(HandsResult(), None, now=0.0)
        self.assertEqual(rec.hud_text, "SEARCHING (BOTH_HANDS_REQUIRED)")
        orch = SimpleNamespace(
            _actuator=SimpleNamespace(_last_send_input_result=None, is_dragging=False, get_native_left_button_state=lambda: "UNKNOWN"),
            _left=SimpleNamespace(drag_state_name="READY", drag_state_text="READY", last_pinch_norm=0.0, is_in_dropout_grace=False, is_pinch_candidate=False, release_reason=None),
            drag_enabled=True, pointer_owner="NONE", cursor_source_name="NONE", is_cursor_moving=False,
            _wakanda=rec,
        )
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        out = draw_debug_frame(frame, HandsResult(), "IDLE", None, {}, {}, 0.0, 0.0, 0.0, 0.0, "DISABLED", 0.0, False, orch)
        self.assertEqual(out.shape, frame.shape)


if __name__ == "__main__":
    unittest.main()

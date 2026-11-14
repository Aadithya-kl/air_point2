# test_watchdog_frame_gap.py
"""
Actuator watchdog versus frame gap (post-migration launch diagnostic, 2026-11-02).

Reproduces the sequence in logs/backend_20261102_225058.err.log: the engine ran
at 5-7 FPS (debug HUD on), and every inter-frame gap above 250 ms released a
healthy GRAB_LOCKED drag ("left button held for 0.257-0.378s without touch"),
after which the still-pinched hand re-grabbed 100 ms later. The root cause is
*where* the watchdog was evaluated, not the heartbeat itself: GestureOrchestrator
checked it at the top of process() against the heartbeat written by the drag
controller during the previous frame, so the 250 ms budget was spent on the
camera/processing gap instead of on "the controller stopped refreshing".

These tests drive the orchestrator with deterministic timestamps and a scripted
actuator (no native input, no camera). They prove the state machine, not that
Windows performed a drag.
"""

from __future__ import annotations

import unittest

import config
from core.actuator import SendInputResult
from core.gestures.drag_controller import DragLockState
from core.tracker import HandsResult
from test_phase1_drag_reliability import FRAME, _OrchestratorCase, make_left, make_right


SLOW_FRAME = 0.300  # one frame period at ~3 FPS (observed gaps: 0.257-0.378 s)


class TestWatchdogFrameGap(_OrchestratorCase):
    def test_slow_frames_never_release_a_healthy_drag(self) -> None:
        """
        GRAB_LOCKED + pinch held + frames 300 ms apart: the controller refreshes
        the heartbeat on every one of those frames, so the watchdog must not fire
        and no LEFTUP may be injected (before the fix: one LEFTUP per slow frame).
        """
        right = make_right(nx=0.60, ny=0.50)
        t = self.start_drag(100.0, right=right)
        hands = HandsResult(left=make_left(pinch=0.35), right=right)
        for i in range(4):
            t += SLOW_FRAME
            # steer with the right hand while the left pinch is held (Q4 of the brief)
            hands = HandsResult(left=make_left(pinch=0.35), right=make_right(nx=0.60 + 0.02 * i, ny=0.50))
            self.step(hands, t)
            self.assertEqual(self.ctrl.state, DragLockState.GRAB_LOCKED, f"released on slow frame {i}")
            self.assertTrue(self.actuator.is_dragging)
        self.assertEqual(self.actuator.up_attempts, 0)
        self.assertEqual(self.actuator.down_confirmed, 1)
        self.assertNotEqual(self.left.release_reason, "WATCHDOG_TIMEOUT")
        self.assertEqual(self.orch.pointer_owner, "RIGHT")
        self.assertGreaterEqual(len(self.actuator.moves), 4)

    def test_heartbeat_is_refreshed_on_every_active_frame(self) -> None:
        """The controller's keep-alive is the heartbeat: after an active frame it equals the frame time."""
        t = self.start_drag(200.0)
        for _ in range(3):
            t += SLOW_FRAME
            self.step(HandsResult(left=make_left(pinch=0.35)), t)
            self.assertEqual(self.actuator._last_drag_time, t)

    def test_watchdog_still_releases_when_the_controller_stops_refreshing(self) -> None:
        """
        Safety preserved: if the button is held while the controller is not in an
        active state (desynchronised), nothing refreshes the heartbeat and the
        watchdog releases after 250 ms of frames, exactly once.
        """
        t = self.start_drag(300.0)
        # Simulate the desynchronisation the watchdog exists for: controller READY, button still down.
        self.ctrl._state = DragLockState.READY
        self.assertTrue(self.actuator.is_dragging)
        released_at = None
        open_hand = HandsResult(left=make_left(open_palm=True))
        for _ in range(12):  # ~0.4 s of 33 ms frames
            t += FRAME
            self.step(open_hand, t)
            if not self.actuator.is_dragging:
                released_at = t
                break
        self.assertIsNotNone(released_at, "watchdog never released the orphaned button")
        self.assertGreater(released_at - 300.12, 0.25)
        self.assertLess(released_at - 300.12, 0.35)
        self.assertEqual(self.actuator.up_confirmed, 1)
        self.assertEqual(self.left.release_reason, "WATCHDOG_TIMEOUT")
        # No further LEFTUP afterwards
        for _ in range(5):
            t += FRAME
            self.step(open_hand, t)
        self.assertEqual(self.actuator.up_attempts, 1)

    def test_tracking_loss_releases_once_through_grace_not_the_watchdog(self) -> None:
        """Hand lost beyond the 150 ms grace: exactly one LEFTUP with reason TRACKING_LOSS."""
        t = self.start_drag(400.0)
        gone = HandsResult(left=None, right=None)
        t += 0.100
        self.step(gone, t)  # inside grace: keep-alive, still held
        self.assertTrue(self.actuator.is_dragging)
        self.assertEqual(self.actuator.up_attempts, 0)
        t += 0.100  # 200 ms without the hand: grace (150 ms) expired
        self.step(gone, t)
        self.assertFalse(self.actuator.is_dragging)
        self.assertEqual(self.actuator.up_confirmed, 1)
        self.assertEqual(self.left.release_reason, "TRACKING_LOSS")
        for _ in range(5):
            t += SLOW_FRAME
            self.step(gone, t)
        self.assertEqual(self.actuator.up_attempts, 1)

    def test_failed_leftup_retry_remains_rate_limited(self) -> None:
        """
        A LEFTUP that Windows does not confirm keeps the logical drag (INPUT_ERROR);
        the watchdog retries every 250 ms, not on every frame, and a confirmed
        retry clears the drag (Phase 1 contract, re-checked at the new call site).
        """
        t = self.start_drag(500.0)
        self.actuator.up_results = [SendInputResult.FAILED, SendInputResult.FAILED]  # first release + its retry
        open_hand = HandsResult(left=make_left(open_palm=True))
        t += FRAME
        self.step(open_hand, t)  # -> RELEASE_PENDING
        t += 0.100
        self.step(open_hand, t)  # dwell satisfied -> LEFTUP x2 fail -> INPUT_ERROR
        self.assertEqual(self.ctrl.state, DragLockState.INPUT_ERROR)
        self.assertTrue(self.actuator.is_dragging)
        self.assertEqual(self.actuator.up_attempts, 2)
        attempts_before = self.actuator.up_attempts
        released_at = None
        for _ in range(12):
            t += FRAME
            self.step(open_hand, t)
            if not self.actuator.is_dragging:
                released_at = t
                break
        self.assertIsNotNone(released_at)
        self.assertEqual(self.actuator.up_attempts, attempts_before + 1)  # one retry, 250 ms later
        self.assertEqual(self.left.release_reason, "WATCHDOG_TIMEOUT")
        self.assertEqual(self.ctrl.state, DragLockState.READY)


if __name__ == "__main__":
    unittest.main()

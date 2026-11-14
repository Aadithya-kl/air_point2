# test_phase1_drag_reliability.py
"""
Phase 1 drag reliability matrix (orchestrator level, deterministic time).

Every test drives GestureOrchestrator.process() with explicit timestamps
(time.perf_counter is patched per step) through a scripted actuator that
returns SendInputResult values exactly as the real actuator would, without
touching Windows. Nothing here is physical validation: these tests prove the
state machine and ownership logic, not that Windows performed a drag.

Scenarios:
  - failed LEFTDOWN through the orchestrator, then recovery
  - failed LEFTUP -> INPUT_ERROR, actuator keeps is_dragging, watchdog recovers
  - persistent LEFTUP failure -> watchdog retries are rate-limited
  - brief pinch opening (single noisy frame) never releases
  - sustained unpinch releases exactly once
  - re-pinch during RELEASE_PENDING keeps the grab
  - right-hand cursor keeps moving while the left drag is held
  - stale frames (identical landmarks, repeated timestamps) never release
  - tracking dropout inside the grace window keeps the drag; reacquisition continues it;
    sustained loss releases once
  - pointer-owner switching with and without an active drag
  - shutdown / pause release primitives (force_release_drag) on success and failure
  - small verified defects: max_step_limit getter, hashable result enums,
    drag_end logging with bool-returning mocks
"""

from __future__ import annotations

import logging
import unittest
from unittest.mock import patch

import config
from core.actuator import (
    DragEndResult,
    DragStartResult,
    MOUSEEVENTF_LEFTDOWN,
    MOUSEEVENTF_LEFTUP,
    MouseActuator,
    SendInputResult,
)
from core.display import TrackpadZone, VirtualDesktop
from core.gestures.drag_controller import DragLockState
from core.gestures.orchestrator import GestureOrchestrator
from core.tracker import HandsResult, Landmark


FRAME = 0.033  # ~30 fps


class ScriptedActuator(MouseActuator):
    """
    MouseActuator with the native layer replaced by a script.

    down_results / up_results are consumed one per LEFTDOWN / LEFTUP attempt;
    when the list is empty default_down / default_up is returned. Attempts and
    confirmations are counted separately so a test can distinguish "tried" from
    "accepted by Windows".
    """

    def __init__(self, w: int = 1920, h: int = 1080) -> None:
        # Deliberately bypass MouseActuator.__init__ (DPI call, pynput controllers).
        self._total_w = w
        self._total_h = h
        self._origin_x = 0
        self._origin_y = 0
        self._dragging = False
        self._last_drag_time = 0.0
        self._last_send_input_result = None
        self._last_drag_error = None
        self._pynput = None
        self._keyboard = None

        self.down_results: list[SendInputResult] = []
        self.up_results: list[SendInputResult] = []
        self.default_down = SendInputResult.CONFIRMED
        self.default_up = SendInputResult.CONFIRMED
        self.down_attempts = 0
        self.up_attempts = 0
        self.down_confirmed = 0
        self.up_confirmed = 0
        self.moves: list[tuple[int, int]] = []
        self.clicks = 0
        self._cursor = (960, 540)

    def _send_mouse_flag(self, flag: int) -> SendInputResult:
        if flag == MOUSEEVENTF_LEFTDOWN:
            self.down_attempts += 1
            res = self.down_results.pop(0) if self.down_results else self.default_down
            if res == SendInputResult.CONFIRMED:
                self.down_confirmed += 1
            return res
        if flag == MOUSEEVENTF_LEFTUP:
            self.up_attempts += 1
            res = self.up_results.pop(0) if self.up_results else self.default_up
            if res == SendInputResult.CONFIRMED:
                self.up_confirmed += 1
            return res
        return SendInputResult.CONFIRMED

    def move(self, x: int, y: int) -> bool:
        self.moves.append((int(x), int(y)))
        self._cursor = (int(x), int(y))
        return True

    def get_cursor_pos(self):
        return self._cursor

    def left_click(self, x=None, y=None) -> bool:
        self.clicks += 1
        return True

    def double_click(self, x=None, y=None) -> bool:
        self.clicks += 2
        return True

    def get_native_left_button_state(self) -> str:
        # Mirrors the logical state; the real query is not available in tests.
        return "DOWN" if self._dragging else "UP"

    @property
    def is_dragging(self) -> bool:
        return self._dragging


def make_left(nx: float = 0.40, ny: float = 0.40, pinch: float = 0.35, open_palm: bool = False) -> list[Landmark]:
    """Synthetic left hand; palm width 0.20 so norm pinch == 5 * |thumb - index|."""
    lms = [Landmark(x=nx, y=ny, z=0.0) for _ in range(21)]
    lms[5] = Landmark(x=nx - 0.10, y=ny, z=0.0)
    lms[17] = Landmark(x=nx + 0.10, y=ny, z=0.0)
    lms[8] = Landmark(x=nx, y=ny, z=0.0)
    lms[6] = Landmark(x=nx, y=ny + 0.05, z=0.0)
    if open_palm:
        for tip, pip in [(8, 6), (12, 10), (16, 14), (20, 18)]:
            lms[tip] = Landmark(x=nx, y=ny - 0.15, z=0.0)
            lms[pip] = Landmark(x=nx, y=ny, z=0.0)
        lms[4] = Landmark(x=nx - 0.20, y=ny, z=0.0)  # norm pinch 1.0
    else:
        for tip, pip in [(12, 10), (16, 14), (20, 18)]:
            lms[tip] = Landmark(x=nx, y=ny + 0.10, z=0.0)
            lms[pip] = Landmark(x=nx, y=ny, z=0.0)
        lms[4] = Landmark(x=nx - 0.20 * pinch, y=ny, z=0.0)
    return lms


def make_right(nx: float = 0.70, ny: float = 0.50, pinch: float = 0.90) -> list[Landmark]:
    """Synthetic pointing right hand (no pinch, no fist, no peace sign)."""
    lms = [Landmark(x=nx, y=ny, z=0.0) for _ in range(21)]
    lms[5] = Landmark(x=nx - 0.10, y=ny, z=0.0)
    lms[17] = Landmark(x=nx + 0.10, y=ny, z=0.0)
    lms[8] = Landmark(x=nx, y=ny, z=0.0)
    lms[6] = Landmark(x=nx, y=ny + 0.05, z=0.0)
    lms[4] = Landmark(x=nx - 0.20 * pinch, y=ny, z=0.0)
    return lms


class _OrchestratorCase(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {
            k: getattr(config, k)
            for k in (
                "POINTER_ONLY_MODE", "PINCH_CLICK_ENABLED", "LEFT_DRAG_ENABLED", "CAMERA_FPS",
                "LEFT_DRAG_START_NORM_DIST", "LEFT_DRAG_RELEASE_NORM_DIST", "LEFT_DRAG_CONFIRM_S",
                "LEFT_DRAG_LOST_TIMEOUT_S",
            )
        }
        config.POINTER_ONLY_MODE = False
        config.PINCH_CLICK_ENABLED = True
        config.LEFT_DRAG_ENABLED = True
        config.CAMERA_FPS = 30
        config.LEFT_DRAG_START_NORM_DIST = 0.55
        config.LEFT_DRAG_RELEASE_NORM_DIST = 0.75
        config.LEFT_DRAG_CONFIRM_S = 0.10
        config.LEFT_DRAG_LOST_TIMEOUT_S = 0.150

        self.actuator = ScriptedActuator()
        self.orch = GestureOrchestrator(
            self.actuator,
            VirtualDesktop(1920, 1080, 1),
            TrackpadZone(100, 540, 80, 400),
            initial_cursor_anchor=(960, 540),
        )
        self.left = self.orch._left
        self.ctrl = self.left.drag_controller

    def tearDown(self) -> None:
        for k, v in self._saved.items():
            setattr(config, k, v)

    def step(self, hands: HandsResult | None, t: float) -> None:
        with patch("time.perf_counter", return_value=t):
            self.orch.process(hands)

    def start_drag(self, t: float, right: list[Landmark] | None = None) -> float:
        """Pinch at t, confirm at t+0.12 s. Returns the time of the confirming frame."""
        hands = HandsResult(left=make_left(pinch=0.35), right=right)
        self.step(hands, t)
        self.assertEqual(self.ctrl.state, DragLockState.GRAB_PENDING)
        t += 0.120
        self.step(hands, t)
        self.assertEqual(self.ctrl.state, DragLockState.GRAB_LOCKED)
        self.assertTrue(self.actuator.is_dragging)
        self.assertEqual(self.actuator.down_confirmed, 1)
        return t


class TestNativeFailurePaths(_OrchestratorCase):
    def test_failed_leftdown_through_orchestrator_then_recovery(self) -> None:
        """An unconfirmed LEFTDOWN never produces a logical drag; the next confirmed one does."""
        self.actuator.down_results = [SendInputResult.UNCONFIRMED]
        hands = HandsResult(left=make_left(pinch=0.35))
        t = 100.0
        self.step(hands, t)
        t += 0.120
        self.step(hands, t)  # dwell satisfied -> LEFTDOWN attempt (UNCONFIRMED)

        self.assertFalse(self.actuator.is_dragging)
        self.assertEqual(self.actuator.down_attempts, 1)
        self.assertEqual(self.actuator.down_confirmed, 0)
        self.assertEqual(self.ctrl.state, DragLockState.READY)
        self.assertEqual(self.left.release_reason, "INPUT_ERROR")
        self.assertEqual(self.orch.pointer_owner, "LEFT")  # left hand still points, no drag lock

        # Pinch still held: a new dwell runs and the confirmed LEFTDOWN starts the drag.
        for _ in range(5):
            t += FRAME
            self.step(hands, t)
        self.assertTrue(self.actuator.is_dragging)
        self.assertEqual(self.actuator.down_attempts, 2)
        self.assertEqual(self.actuator.down_confirmed, 1)
        self.assertEqual(self.ctrl.state, DragLockState.GRAB_LOCKED)

    def test_failed_leftup_enters_input_error_and_watchdog_recovers(self) -> None:
        """Failed LEFTUP keeps the logical drag; the actuator watchdog retries and clears it."""
        t = self.start_drag(200.0)

        # Deliberate release whose two native attempts are both unconfirmed.
        self.actuator.up_results = [SendInputResult.UNCONFIRMED, SendInputResult.UNCONFIRMED]
        open_hand = HandsResult(left=make_left(open_palm=True))
        t += FRAME
        self.step(open_hand, t)
        self.assertEqual(self.ctrl.state, DragLockState.RELEASE_PENDING)
        t += 0.100
        self.step(open_hand, t)  # dwell satisfied -> _execute_drop -> FAILED
        self.assertEqual(self.ctrl.state, DragLockState.INPUT_ERROR)
        self.assertTrue(self.actuator.is_dragging, "logical drag must be retained after a failed LEFTUP")
        self.assertEqual(self.actuator.up_attempts, 2)
        self.assertEqual(self.actuator.up_confirmed, 0)
        self.assertEqual(self.actuator._last_drag_error, "SENDINPUT_LEFTUP_FAILED")
        self.assertEqual(self.orch.pointer_owner, "LEFT")  # ownership stays locked while held

        # No keep-alive in INPUT_ERROR -> after 250 ms the watchdog retries with a confirmed UP.
        t_fail = t
        released_at = None
        while t - t_fail < 0.60:
            t += FRAME
            self.step(open_hand, t)
            if not self.actuator.is_dragging:
                released_at = t
                break
        self.assertIsNotNone(released_at, "watchdog never recovered the failed release")
        self.assertGreaterEqual(released_at - t_fail, 0.25 - FRAME)
        self.assertEqual(self.actuator.up_confirmed, 1)
        self.assertEqual(self.ctrl.state, DragLockState.READY)
        self.assertEqual(self.left.release_reason, "WATCHDOG_TIMEOUT")
        self.assertIsNone(self.actuator._last_drag_error)

    def test_persistent_leftup_failure_watchdog_retry_is_rate_limited(self) -> None:
        """When every LEFTUP is unconfirmed the watchdog retries every 250 ms, not every frame."""
        t = self.start_drag(300.0)
        self.actuator.default_up = SendInputResult.UNCONFIRMED
        open_hand = HandsResult(left=make_left(open_palm=True))
        t += FRAME
        self.step(open_hand, t)
        t += 0.100
        self.step(open_hand, t)
        self.assertEqual(self.ctrl.state, DragLockState.INPUT_ERROR)
        attempts_after_drop = self.actuator.up_attempts  # 2 (attempt + retry)

        t_fail = t
        while t - t_fail < 1.0:
            t += FRAME
            self.step(open_hand, t)
        extra_attempts = self.actuator.up_attempts - attempts_after_drop
        # ~30 frames elapsed; one watchdog fire per 250 ms = 4 fires x 2 attempts = 8,
        # with a little slack for frame alignment. Unlimited retry would be ~60.
        self.assertGreaterEqual(extra_attempts, 4)
        self.assertLessEqual(extra_attempts, 12)
        self.assertTrue(self.actuator.is_dragging, "fault must stay visible while unconfirmed")
        self.assertEqual(self.actuator.up_confirmed, 0)


class TestReleaseSemantics(_OrchestratorCase):
    def test_brief_pinch_opening_does_not_release(self) -> None:
        t = self.start_drag(400.0)
        held = HandsResult(left=make_left(pinch=0.35))
        spike = HandsResult(left=make_left(pinch=0.90))  # above the 0.85 "clear" value too
        t += FRAME
        self.step(spike, t)
        self.assertEqual(self.ctrl.state, DragLockState.RELEASE_PENDING)
        self.assertTrue(self.actuator.is_dragging)
        self.assertEqual(self.actuator.up_attempts, 0)
        t += FRAME
        self.step(held, t)
        self.assertEqual(self.ctrl.state, DragLockState.GRAB_LOCKED)
        self.assertEqual(self.actuator.up_attempts, 0)

    def test_sustained_unpinch_releases_exactly_once(self) -> None:
        t = self.start_drag(500.0)
        open_hand = HandsResult(left=make_left(open_palm=True))
        t += FRAME
        self.step(open_hand, t)
        self.assertEqual(self.actuator.up_attempts, 0)
        for _ in range(4):  # +132 ms > 80 ms dwell
            t += FRAME
            self.step(open_hand, t)
        self.assertFalse(self.actuator.is_dragging)
        self.assertEqual(self.actuator.up_confirmed, 1)
        self.assertEqual(self.ctrl.state, DragLockState.READY)
        for _ in range(10):
            t += FRAME
            self.step(open_hand, t)
        self.assertEqual(self.actuator.up_attempts, 1)
        self.assertEqual(self.actuator.down_attempts, 1)

    def test_repinch_during_release_pending_keeps_grab(self) -> None:
        t = self.start_drag(600.0)
        t += FRAME
        self.step(HandsResult(left=make_left(pinch=0.78)), t)
        self.assertEqual(self.ctrl.state, DragLockState.RELEASE_PENDING)
        t += 0.050  # inside the 80 ms dwell
        self.step(HandsResult(left=make_left(pinch=0.40)), t)
        self.assertEqual(self.ctrl.state, DragLockState.GRAB_LOCKED)
        self.assertTrue(self.actuator.is_dragging)
        self.assertEqual(self.actuator.up_attempts, 0)
        self.assertEqual(self.actuator.down_attempts, 1)

    def test_stale_frames_never_release(self) -> None:
        """Identical landmarks with advancing time, then repeated timestamps, keep the grab."""
        t = self.start_drag(700.0)
        same = HandsResult(left=make_left(pinch=0.35))
        for _ in range(20):
            t += FRAME
            self.step(same, t)
        for _ in range(5):
            self.step(same, t)  # timestamp does not advance
        self.assertTrue(self.actuator.is_dragging)
        self.assertEqual(self.ctrl.state, DragLockState.GRAB_LOCKED)
        self.assertEqual(self.actuator.down_attempts, 1)
        self.assertEqual(self.actuator.up_attempts, 0)


class TestTrackingDropout(_OrchestratorCase):
    def test_dropout_within_grace_then_reacquisition_continues_drag(self) -> None:
        t = self.start_drag(800.0)
        held = HandsResult(left=make_left(pinch=0.35))
        for _ in range(3):  # 99 ms of missing left hand < 150 ms grace
            t += FRAME
            self.step(HandsResult(left=None), t)
            self.assertTrue(self.actuator.is_dragging)
            self.assertTrue(self.left.is_in_dropout_grace)
        t += FRAME
        self.step(held, t)
        self.assertTrue(self.actuator.is_dragging)
        self.assertFalse(self.left.is_in_dropout_grace)
        self.assertEqual(self.actuator.down_attempts, 1, "reacquisition must not re-issue LEFTDOWN")
        self.assertEqual(self.actuator.up_attempts, 0)

    def test_sustained_dropout_releases_once(self) -> None:
        t = self.start_drag(900.0)
        released_at = None
        t_lost = t
        for _ in range(12):
            t += FRAME
            self.step(HandsResult(left=None), t)
            if not self.actuator.is_dragging and released_at is None:
                released_at = t
        self.assertIsNotNone(released_at)
        self.assertGreater(released_at - t_lost, 0.150 - 1e-9)
        self.assertLess(released_at - t_lost, 0.150 + 2 * FRAME)
        self.assertEqual(self.actuator.up_confirmed, 1)
        self.assertEqual(self.actuator.up_attempts, 1)
        self.assertEqual(self.ctrl.state, DragLockState.READY)
        self.assertEqual(self.left.release_reason, "TRACKING_LOSS")


class TestPointerOwnership(_OrchestratorCase):
    def test_right_cursor_moves_while_left_drag_held(self) -> None:
        t = self.start_drag(1000.0, right=make_right(0.40, 0.50))
        self.assertEqual(self.orch.pointer_owner, "RIGHT")
        moves_before = len(self.actuator.moves)
        xs = []
        for i in range(1, 9):
            t += FRAME
            hands = HandsResult(left=make_left(pinch=0.35), right=make_right(0.40 + 0.03 * i, 0.50))
            self.step(hands, t)
            self.assertTrue(self.actuator.is_dragging)
            self.assertEqual(self.orch.pointer_owner, "RIGHT")
            xs.append(self.actuator.moves[-1][0])
        self.assertGreater(len(self.actuator.moves), moves_before)
        self.assertGreater(xs[-1], xs[0], "right hand must keep steering during the drag")
        self.assertEqual(self.actuator.down_attempts, 1)
        self.assertEqual(self.actuator.up_attempts, 0)

    def test_owner_switches_to_right_when_right_hand_appears_without_drag(self) -> None:
        t = 1100.0
        self.step(HandsResult(left=make_left(pinch=0.90)), t)
        self.assertEqual(self.orch.pointer_owner, "LEFT")
        t += FRAME
        self.step(HandsResult(left=make_left(pinch=0.90), right=make_right()), t)
        self.assertEqual(self.orch.pointer_owner, "RIGHT")

    def test_left_steers_when_right_absent_during_drag(self) -> None:
        t = self.start_drag(1200.0)
        self.assertEqual(self.orch.pointer_owner, "LEFT")
        first = self.actuator.moves[-1]
        for i in range(1, 6):
            t += FRAME
            self.step(HandsResult(left=make_left(0.40 + 0.04 * i, 0.40, pinch=0.35)), t)
        self.assertEqual(self.orch.pointer_owner, "LEFT")
        self.assertGreater(self.actuator.moves[-1][0], first[0])
        self.assertTrue(self.actuator.is_dragging)

    def test_owner_stays_right_and_cursor_freezes_when_right_lost_during_drag(self) -> None:
        """
        Documents current behaviour (finding F-22): during a drag the owner is
        locked to RIGHT; once the right hand is lost beyond the 120 ms grace the
        cursor stops and the left hand does not take over until the drag ends.
        Changing this is a product decision (see the Phase 1 report).
        """
        t = self.start_drag(1300.0, right=make_right(0.40, 0.50))
        self.assertEqual(self.orch.pointer_owner, "RIGHT")
        for _ in range(6):  # ~200 ms without the right hand
            t += FRAME
            self.step(HandsResult(left=make_left(pinch=0.35), right=None), t)
        moves_after_loss = len(self.actuator.moves)
        for i in range(1, 5):
            t += FRAME
            self.step(HandsResult(left=make_left(0.40 + 0.04 * i, 0.40, pinch=0.35), right=None), t)
        self.assertEqual(self.orch.pointer_owner, "RIGHT")
        self.assertEqual(len(self.actuator.moves), moves_after_loss)
        self.assertTrue(self.actuator.is_dragging)


class TestShutdownAndPausePrimitives(_OrchestratorCase):
    def test_force_release_drag_success(self) -> None:
        self.start_drag(1400.0)
        res = self.actuator.force_release_drag(context="SHUTDOWN")
        self.assertEqual(res, DragEndResult.RELEASED)
        self.assertFalse(self.actuator.is_dragging)
        self.assertEqual(self.actuator.up_attempts, 1)
        self.assertIsNone(self.actuator._last_drag_error)
        self.assertEqual(self.actuator.force_release_drag(context="SHUTDOWN"), DragEndResult.NOT_DRAGGING)

    def test_force_release_drag_persistent_failure_is_bounded_and_visible(self) -> None:
        self.start_drag(1500.0)
        self.actuator.default_up = SendInputResult.UNCONFIRMED
        with self.assertLogs("core.actuator", level="CRITICAL") as logs:
            res = self.actuator.force_release_drag(max_attempts=3, retry_delay_s=0.0, context="SHUTDOWN")
        self.assertEqual(res, DragEndResult.FAILED)
        self.assertTrue(self.actuator.is_dragging, "an unconfirmed release must not be reported as released")
        self.assertEqual(self.actuator.up_attempts, 6)  # 3 attempts x (try + retry)
        self.assertEqual(self.actuator._last_drag_error, "DRAG_RELEASE_UNCONFIRMED_AT_SHUTDOWN")
        summary_lines = [m for m in logs.output if "SHUTDOWN: native left button release UNCONFIRMED" in m]
        self.assertEqual(len(summary_lines), 1)

    def test_shutdown_sequence_controller_then_actuator(self) -> None:
        """The main.py finally-block sequence: controller release first, actuator force-release second."""
        self.start_drag(1600.0)
        self.left.release_drag(reason="SHUTDOWN")
        self.assertEqual(self.ctrl.state, DragLockState.READY)
        self.assertFalse(self.actuator.is_dragging)
        self.assertEqual(self.actuator.force_release_drag(context="SHUTDOWN"), DragEndResult.NOT_DRAGGING)
        self.assertEqual(self.actuator.up_attempts, 1)

    def test_pause_sequence_with_failed_then_recovered_release(self) -> None:
        """Pause: controller release fails -> INPUT_ERROR; force-release recovers; next frame returns READY."""
        t = self.start_drag(1700.0)
        self.actuator.up_results = [SendInputResult.UNCONFIRMED, SendInputResult.UNCONFIRMED]
        self.left.release_drag(reason="PAUSE")
        self.assertEqual(self.ctrl.state, DragLockState.INPUT_ERROR)
        self.assertTrue(self.actuator.is_dragging)
        res = self.actuator.force_release_drag(context="PAUSE")
        self.assertEqual(res, DragEndResult.RELEASED)
        self.assertFalse(self.actuator.is_dragging)
        t += FRAME
        self.step(HandsResult(left=make_left(open_palm=True)), t)
        self.assertEqual(self.ctrl.state, DragLockState.READY)


class TestSmallVerifiedDefects(unittest.TestCase):
    def test_max_step_limit_property_roundtrip(self) -> None:
        act = ScriptedActuator()
        orch = GestureOrchestrator(act, VirtualDesktop(1920, 1080, 1), TrackpadZone(100, 540, 80, 400))
        self.assertIsNone(orch.max_step_limit)
        orch.max_step_limit = 50.0
        self.assertEqual(orch.max_step_limit, 50.0)
        orch.max_step_limit = 0
        self.assertIsNone(orch.max_step_limit)

    def test_result_enums_are_hashable(self) -> None:
        for enum_cls in (SendInputResult, DragStartResult, DragEndResult):
            members = set(enum_cls)
            self.assertEqual(len(members), len(list(enum_cls)))
            self.assertIn(list(enum_cls)[0], {list(enum_cls)[0]: 1})

    def test_drag_end_logging_tolerates_bool_results(self) -> None:
        """Legacy mocks returning bools from _send_mouse_flag must not crash the retry log."""

        class BoolActuator(ScriptedActuator):
            def _send_mouse_flag(self, flag: int):  # type: ignore[override]
                if flag == MOUSEEVENTF_LEFTUP:
                    self.up_attempts += 1
                    return False
                self.down_attempts += 1
                return True

        act = BoolActuator()
        self.assertEqual(act.drag_start(now=1.0), DragStartResult.STARTED)
        with self.assertLogs("core.actuator", level="ERROR"):
            res = act.drag_end()
        self.assertEqual(res, DragEndResult.FAILED)
        self.assertTrue(act.is_dragging)
        self.assertEqual(act.up_attempts, 2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    unittest.main()

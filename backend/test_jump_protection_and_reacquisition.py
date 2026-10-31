"""
Unit tests for Air Point Stage 2.5: Trusted Desktop Cursor Baseline and Bounded Reacquisition.

Verifies:
1. Cold start with real-position query mocked to (250, 250) and a distant first hand target.
2. Explicit initial anchor takes precedence over queried fallback.
3. Cursor query failure does not cause an unbounded movement (fails closed safely).
4. Reset followed by distant reacquisition does not teleport.
5. External cursor movement during pause/hand-loss refreshes anchor safely.
6. Query failure during reset preserves justified prior anchor.
7. Repeated reset/reacquisition cycles maintain safety invariants without degradation.
8. Consecutive jumps: Frame 1 AND Frame 2 remain bounded.
9. Long time gap: pause capped at 960px.
10. Pointer-owner handover: right-to-left transition remains bounded.
11. Ear-volume recovery: exiting ear gesture remains bounded.
12. Stationary tracking, missing-hand frames (0 actuator calls), and timestamp edge cases.
13. Multi-step monotonic convergence along collinear unit vector.
14. Integer rounding safety: Euclidean displacement strictly <= max_step across all angles.
"""

import math
import unittest
from unittest.mock import MagicMock, patch

from core.actuator import MouseActuator
from core.display import VirtualDesktop, TrackpadZone
from core.gestures.orchestrator import GestureOrchestrator, PointerOwner
from core.tracker import HandsResult


class MockMouseActuator:
    """Mock mouse actuator that captures every move call deterministically without OS interaction."""

    def __init__(
        self,
        width: int = 1920,
        height: int = 1080,
        current_cursor_pos: tuple[int, int] | None = None,
    ) -> None:
        self._total_w = width
        self._total_h = height
        self.moves: list[tuple[int, int]] = []
        self.is_dragging = False
        self._current_pos: tuple[int, int] | None = current_cursor_pos
        self.query_fail: bool = False

    def get_cursor_pos(self) -> tuple[int, int] | None:
        if self.query_fail:
            return None
        return self._current_pos

    def set_mock_cursor_pos(self, pos: tuple[int, int] | None) -> None:
        self._current_pos = pos

    def move(self, x: int, y: int) -> bool:
        self.moves.append((int(x), int(y)))
        self._current_pos = (int(x), int(y))
        return True

    def drag_end(self) -> None:
        self.is_dragging = False

    def clear(self) -> None:
        self.moves.clear()

    @property
    def last_move(self) -> tuple[int, int] | None:
        return self.moves[-1] if self.moves else None

    @property
    def total_moves(self) -> int:
        return len(self.moves)


class TestJumpProtectionAndReacquisition(unittest.TestCase):
    def setUp(self) -> None:
        self.desktop = VirtualDesktop(total_width=1920, total_height=1080, monitor_count=1)
        self.trackpad = TrackpadZone(170, 470, 120, 320)
        self.actuator = MockMouseActuator(1920, 1080, current_cursor_pos=(100, 100))
        self.orchestrator = GestureOrchestrator(self.actuator, self.desktop, self.trackpad)

    def _set_right_hand_target(self, pos: tuple[int, int] | None) -> None:
        """Synthetic right-hand cursor position injector."""
        self.orchestrator._right.process = MagicMock(
            side_effect=lambda h: setattr(self.orchestrator._right, '_cursor_pos', pos)
        )
        setattr(self.orchestrator._right, '_cursor_pos', pos)

    def _set_left_hand_target(self, pos: tuple[int, int] | None) -> None:
        """Synthetic left-hand cursor position injector."""
        self.orchestrator._left.process = MagicMock(
            side_effect=lambda h, now=None: (
                setattr(self.orchestrator._left, 'cursor_pos', pos),
                setattr(self.orchestrator._left, 'is_pointing', pos is not None)
            )
        )
        setattr(self.orchestrator._left, 'cursor_pos', pos)
        setattr(self.orchestrator._left, 'is_pointing', pos is not None)

    def _step(self, t: float, right: bool = True, left: bool = False) -> None:
        """Execute one orchestrator process tick at timestamp t."""
        hands = HandsResult(
            right=[MagicMock()] if right else None,
            left=[MagicMock()] if left else None,
        )
        with patch("time.perf_counter", return_value=t):
            self.orchestrator.process(hands)

    # ── 1. Cold Start with Real-Position Query ────────────────────────────────

    def test_cold_start_queried_desktop_cursor_bounds_first_move(self) -> None:
        """Verify cold start initializes anchor from actuator query and bounds first movement."""
        actuator = MockMouseActuator(1920, 1080, current_cursor_pos=(250, 250))
        orch = GestureOrchestrator(actuator, self.desktop, self.trackpad, initial_cursor_anchor=None)

        # Trusted anchor initialized from actuator without calling move()
        self.assertEqual(orch.trusted_cursor_anchor, (250, 250))
        self.assertEqual(actuator.total_moves, 0, "Initialization must not issue move calls")

        # Hand first appears 1600px distant at (1850, 250)
        orch._right.process = MagicMock(side_effect=lambda h: setattr(orch._right, '_cursor_pos', (1850, 250)))
        setattr(orch._right, '_cursor_pos', (1850, 250))

        hands = HandsResult(right=[MagicMock()])
        with patch("time.perf_counter", return_value=1.000):
            orch.process(hands)

        self.assertEqual(actuator.total_moves, 1)
        m = actuator.moves[0]
        # Uninitialized dt fallback 1/30s -> max_step = 800.0 px
        disp = math.hypot(m[0] - 250, m[1] - 250)
        self.assertLessEqual(disp, 800.0 + 1e-6)
        self.assertEqual(m, (1050, 250))
        self.assertNotEqual(m, (1850, 250), "Cold start must not teleport physical cursor to target")

    # ── 2. Explicit Initial Anchor Precedence ─────────────────────────────────

    def test_explicit_initial_anchor_takes_precedence_over_query(self) -> None:
        """Verify explicitly provided initial anchor overrides actuator query."""
        actuator = MockMouseActuator(1920, 1080, current_cursor_pos=(900, 900))
        orch = GestureOrchestrator(actuator, self.desktop, self.trackpad, initial_cursor_anchor=(400, 400))

        # Explicit anchor takes precedence
        self.assertEqual(orch.trusted_cursor_anchor, (400, 400))
        self.assertEqual(actuator.total_moves, 0)

        # Distant target at (1200, 400)
        orch._right.process = MagicMock(side_effect=lambda h: setattr(orch._right, '_cursor_pos', (1200, 400)))
        setattr(orch._right, '_cursor_pos', (1200, 400))

        hands = HandsResult(right=[MagicMock()])
        with patch("time.perf_counter", return_value=1.000):
            orch.process(hands)

        m = actuator.moves[0]
        # Bounded from (400, 400), not (900, 900)
        self.assertEqual(m, (1200, 400))

    # ── 3. Cursor Query Failure Handling (Fail Closed) ────────────────────────

    def test_cursor_query_failure_suppresses_unbounded_movement(self) -> None:
        """Verify that when cursor query fails and anchor is unknown, movement is safely suppressed."""
        actuator = MockMouseActuator(1920, 1080, current_cursor_pos=None)
        actuator.query_fail = True
        orch = GestureOrchestrator(actuator, self.desktop, self.trackpad, initial_cursor_anchor=None)

        self.assertIsNone(orch.trusted_cursor_anchor)

        orch._right.process = MagicMock(side_effect=lambda h: setattr(orch._right, '_cursor_pos', (1800, 500)))
        setattr(orch._right, '_cursor_pos', (1800, 500))

        hands = HandsResult(right=[MagicMock()])
        with patch("time.perf_counter", return_value=1.000):
            orch.process(hands)

        # Fail closed: no move call emitted
        self.assertEqual(actuator.total_moves, 0)
        self.assertIsNone(orch.cursor_pos)

        # Recovery: query succeeds
        actuator.query_fail = False
        actuator.set_mock_cursor_pos((500, 500))

        with patch("time.perf_counter", return_value=1.033):
            orch.process(hands)

        self.assertEqual(actuator.total_moves, 1)
        m = actuator.moves[0]
        disp = math.hypot(m[0] - 500, m[1] - 500)
        self.assertLessEqual(disp, 800.0 + 1e-6)
        self.assertEqual(m, (1300, 500))

    # ── 4. Reset Followed by Reacquisition Does Not Teleport ──────────────────

    def test_reset_followed_by_distant_reacquisition_bounded(self) -> None:
        """Verify calling reset() preserves/refreshes anchor so subsequent reacquisition is bounded."""
        self._set_right_hand_target((400, 400))
        self._step(1.000, right=True)
        self.assertEqual(self.orchestrator.trusted_cursor_anchor, (400, 400))
        self.actuator.clear()

        # Reset is triggered
        self.orchestrator.reset()
        self.assertEqual(self.actuator.total_moves, 0, "reset must not issue move calls")
        self.assertEqual(self.orchestrator.trusted_cursor_anchor, (400, 400), "reset must preserve anchor")
        self.assertIsNone(self.orchestrator.cursor_pos, "cursor_pos must clear on reset")

        # Hand reacquires 1400px distant at (1800, 400)
        # Because reset cleared _last_move_time to 0.0, fallback dt=1/30s -> max_step=800px
        self._set_right_hand_target((1800, 400))
        self._step(1.040, right=True)

        self.assertEqual(self.actuator.total_moves, 1)
        m = self.actuator.moves[0]
        disp = math.hypot(m[0] - 400, m[1] - 400)
        # Bounded by max_step (800.0 px), reaching (1200, 400)
        self.assertLessEqual(disp, 800.0 + 1e-6)
        self.assertEqual(m, (1200, 400))
        self.assertNotEqual(m, (1800, 400))

    # ── 5. External Mouse Movement During Pause / Tracking Loss ───────────────

    def test_external_mouse_movement_during_absence_refreshes_anchor(self) -> None:
        """Verify that external physical mouse movement during a tracking gap refreshes anchor safely."""
        self._set_right_hand_target((300, 300))
        self._step(1.000, right=True)
        self.actuator.clear()

        # Hand lost
        self._set_right_hand_target(None)
        self._step(1.033, right=False)
        self.assertEqual(self.actuator.total_moves, 0)

        # User moves physical mouse to (1200, 600) while hands are down
        self.actuator.set_mock_cursor_pos((1200, 600))

        # Hand reacquires at (1800, 600) (600px from current physical position)
        self._set_right_hand_target((1800, 600))
        self._step(3.000, right=True)

        self.assertEqual(self.actuator.total_moves, 1)
        m = self.actuator.moves[0]
        # Measured from the actual physical cursor position (1200, 600):
        disp_from_physical = math.hypot(m[0] - 1200, m[1] - 600)
        self.assertLessEqual(disp_from_physical, 960.0 + 1e-6)
        self.assertEqual(m, (1800, 600))

    # ── 6. Query Failure During Reset / Recovery ──────────────────────────────

    def test_query_failure_during_reset_preserves_known_anchor(self) -> None:
        """Verify that if query fails during reset, orchestrator safely retains its prior anchor."""
        self._set_right_hand_target((600, 600))
        self._step(1.000, right=True)
        self.actuator.clear()

        # Query starts failing
        self.actuator.query_fail = True
        self.orchestrator.reset()

        # Prior anchor preserved as safe baseline
        self.assertEqual(self.orchestrator.trusted_cursor_anchor, (600, 600))

        # Hand reacquires at (2000, 600) (1400px distant)
        # Fallback dt=1/30s -> max_step=800px
        self._set_right_hand_target((2000, 600))
        self._step(1.033, right=True)

        self.assertEqual(self.actuator.total_moves, 1)
        m = self.actuator.moves[0]
        disp = math.hypot(m[0] - 600, m[1] - 600)
        self.assertLessEqual(disp, 800.0 + 1e-6)
        self.assertEqual(m, (1400, 600))

    # ── 7. Repeated Reset and Reacquisition Cycles ────────────────────────────

    def test_repeated_reset_reacquisition_cycles_maintain_safety(self) -> None:
        """Verify repeated reset-reacquire cycles never lose bounded displacement invariants."""
        current_pos = (500, 500)
        self.orchestrator.set_cursor_anchor(current_pos)

        for cycle in range(5):
            self.actuator.clear()
            self.orchestrator.reset()
            # Distant target alternating corners
            tx = 1900 if cycle % 2 == 0 else 100
            ty = 1000 if cycle % 2 == 0 else 100
            self._set_right_hand_target((tx, ty))

            t = 1.000 + cycle * 1.000
            self._step(t, right=True)

            self.assertEqual(self.actuator.total_moves, 1)
            m = self.actuator.moves[0]
            disp = math.hypot(m[0] - current_pos[0], m[1] - current_pos[1])
            self.assertLessEqual(disp, 960.0 + 1e-6, f"Cycle {cycle} violated max_step: disp={disp}")
            current_pos = m

    # ── 8. Consecutive Excessive Jumps Bounded ────────────────────────────────

    def test_consecutive_excessive_jumps_both_bounded(self) -> None:
        """Verify Frame 1 AND Frame 2 remain bounded when remaining distance exceeds limit."""
        self.orchestrator.set_cursor_anchor((100, 100))
        self.orchestrator._last_move_time = 1.000
        self.orchestrator._pointer_owner = PointerOwner.RIGHT

        target = (2500, 100)
        self._set_right_hand_target(target)

        # Frame 1: dt=0.016s -> max_step = 384.0 px
        self._step(1.016, right=True)
        self.assertEqual(self.actuator.total_moves, 1)
        m1 = self.actuator.moves[0]
        d1 = math.hypot(m1[0] - 100, m1[1] - 100)
        self.assertLessEqual(d1, 384.0 + 1e-6)
        self.assertEqual(m1, (484, 100))

        # Frame 2: dt=0.033s -> max_step = 792.0 px. Clamping MUST be maintained!
        self._step(1.049, right=True)
        self.assertEqual(self.actuator.total_moves, 2)
        m2 = self.actuator.moves[1]
        d2 = math.hypot(m2[0] - m1[0], m2[1] - m1[1])
        self.assertLessEqual(d2, 792.0 + 1e-6)
        self.assertEqual(m2, (1276, 100))
        self.assertNotEqual(m2, target)

    # ── 9. Long Time Gap Capped at 960px ───────────────────────────────────────

    def test_long_time_gap_bounded_to_ceiling_960px(self) -> None:
        """Verify pause (2.0s) clamps dt_effective to 0.040s and max_step to 960px."""
        self.orchestrator.set_cursor_anchor((200, 200))
        self.orchestrator._last_move_time = 1.000
        self.orchestrator._pointer_owner = PointerOwner.RIGHT

        target = (1800, 200)
        self._set_right_hand_target(target)

        # t=3.000 (2.0s pause)
        self._step(3.000, right=True)
        self.assertEqual(self.actuator.total_moves, 1)
        m = self.actuator.moves[0]
        step_disp = math.hypot(m[0] - 200, m[1] - 200)
        self.assertLessEqual(step_disp, 960.0 + 1e-6)
        self.assertEqual(m, (1160, 200))

    # ── 10. Pointer-Owner Transitions ─────────────────────────────────────────

    def test_pointer_owner_transition_right_to_left_bounded(self) -> None:
        """Verify handover from right hand to left hand bounds step from anchor."""
        self._set_right_hand_target((600, 600))
        self._step(1.000, right=True, left=False)
        self.assertEqual(self.orchestrator.pointer_owner, "RIGHT")
        self.actuator.clear()

        # Right absent, Left pointing at (1800, 600) (1200px jump, dt=0.033s -> max_step=792px)
        self._set_right_hand_target(None)
        self._set_left_hand_target((1800, 600))
        self._step(1.033, right=False, left=True)

        self.assertEqual(self.orchestrator.pointer_owner, "LEFT")
        self.assertEqual(self.actuator.total_moves, 1)
        m = self.actuator.moves[0]
        disp = math.hypot(m[0] - 600, m[1] - 600)
        self.assertLessEqual(disp, 792.0 + 1e-6)
        self.assertEqual(m, (1392, 600))

    # ── 11. Ear-Volume Recovery Bounded ───────────────────────────────────────

    def test_ear_volume_recovery_bounded(self) -> None:
        """Verify exiting ear volume interaction bounds cursor reacquisition."""
        self._set_right_hand_target((400, 400))
        self._step(1.000, right=True)
        self.actuator.clear()

        self.orchestrator._was_ear_active = True
        self.orchestrator._pointer_owner = PointerOwner.NONE

        self._set_right_hand_target((1700, 400))
        self._step(1.050, right=True)

        self.assertEqual(self.actuator.total_moves, 1)
        m = self.actuator.moves[0]
        disp = math.hypot(m[0] - 400, m[1] - 400)
        self.assertLessEqual(disp, 960.0 + 1e-6)
        self.assertEqual(m, (1360, 400))
        self.assertFalse(self.orchestrator._was_ear_active)

    # ── 12. Stationary Tracking, Missing Hands, and Timestamp Edge Cases ──────

    def test_stationary_tracking_zero_drift(self) -> None:
        """Verify stationary hand generates exact target coordinates with zero drift."""
        self._set_right_hand_target((750, 450))
        for i in range(10):
            self._step(1.000 + i * 0.033, right=True)
            self.assertEqual(self.actuator.moves[-1], (750, 450))
            self.assertEqual(self.orchestrator.cursor_pos, (750, 450))

    def test_missing_hand_frames_issue_zero_actuator_calls(self) -> None:
        """Verify that frames with no hands generate zero actuator move calls."""
        self._set_right_hand_target((500, 500))
        self._step(1.000, right=True)
        self.actuator.clear()

        self._set_right_hand_target(None)
        for i in range(10):
            self._step(1.033 + i * 0.033, right=False)

        self.assertEqual(self.actuator.total_moves, 0, "No move calls permitted when hand is missing")

    def test_timestamp_edge_cases_dt_zero_and_negative(self) -> None:
        """Verify zero or backwards dt handled cleanly without divide-by-zero or crashes."""
        self.orchestrator.set_cursor_anchor((500, 500))
        self.orchestrator._last_move_time = 1.000
        self.orchestrator._pointer_owner = PointerOwner.RIGHT
        self._set_right_hand_target((1200, 500))

        # dt == 0: clamped to 0.001 -> max_step = 380px
        self._step(1.000, right=True)
        self.assertEqual(self.actuator.total_moves, 1)
        m1 = self.actuator.moves[0]
        self.assertEqual(m1, (880, 500))

        # backwards timestamp (now < last_move_time)
        self._set_right_hand_target((1500, 500))
        self._step(0.500, right=True)
        self.assertEqual(self.actuator.total_moves, 2)
        m2 = self.actuator.moves[1]
        self.assertEqual(m2, (1260, 500))

    # ── 13. Multi-Step Monotonic Convergence ──────────────────────────────────

    def test_multi_step_monotonic_convergence_to_target(self) -> None:
        """Verify step-by-step monotonic convergence along the exact vector to stationary target."""
        self.orchestrator.set_cursor_anchor((100, 100))
        self.orchestrator._last_move_time = 1.000
        self.orchestrator._pointer_owner = PointerOwner.RIGHT

        target = (1700, 1300)  # dx=1600, dy=1200, dist=2000px. Unit: (0.8, 0.6)
        self._set_right_hand_target(target)

        # Frame 1: dt = 1/30s -> max_step = 800.0 px
        t1 = 1.000 + (1.0 / 30.0)
        self._step(t1, right=True)
        m1 = self.actuator.moves[0]
        self.assertEqual(m1, (740, 580))
        rem1 = math.hypot(target[0] - m1[0], target[1] - m1[1])
        self.assertAlmostEqual(rem1, 1200.0, places=1)

        # Frame 2: dt = 1/30s -> max_step = 800.0 px
        t2 = t1 + (1.0 / 30.0)
        self._step(t2, right=True)
        m2 = self.actuator.moves[1]
        self.assertEqual(m2, (1380, 1060))
        rem2 = math.hypot(target[0] - m2[0], target[1] - m2[1])
        self.assertAlmostEqual(rem2, 400.0, places=1)
        self.assertLess(rem2, rem1)

        # Frame 3: remaining 400px <= 800px -> arrives at target
        t3 = t2 + (1.0 / 30.0)
        self._step(t3, right=True)
        m3 = self.actuator.moves[2]
        self.assertEqual(m3, target)
        rem3 = math.hypot(target[0] - m3[0], target[1] - m3[1])
        self.assertEqual(rem3, 0.0)

    # ── 14. Integer Coordinate Rounding Boundary Safety ───────────────────────

    def test_integer_rounding_guarantees_no_displacement_overshoot(self) -> None:
        """Verify conservative rounding prevents Euclidean displacement > max_step across diverse angles."""
        anchor = (500, 500)
        self.orchestrator.set_cursor_anchor(anchor)
        self.orchestrator._last_move_time = 1.000
        self.orchestrator._pointer_owner = PointerOwner.RIGHT

        for deg in range(0, 360, 15):
            rad = math.radians(deg)
            tx = int(round(anchor[0] + 2000 * math.cos(rad)))
            ty = int(round(anchor[1] + 2000 * math.sin(rad)))
            self._set_right_hand_target((tx, ty))

            self.actuator.clear()
            self.orchestrator.set_cursor_anchor(anchor)
            self.orchestrator._last_move_time = 1.000

            # dt=0.040s -> max_step = 960.0 px
            self._step(1.040, right=True)
            m = self.actuator.moves[0]
            disp = math.hypot(m[0] - anchor[0], m[1] - anchor[1])
            self.assertLessEqual(
                disp, 960.0 + 1e-6,
                f"Angle {deg} deg produced rounding overshoot: disp={disp} > max_step=960.0"
            )


    # ── 15. Conservative Phase B Limit & Internal/Physical Consistency ────────

    def test_conservative_max_step_limit_enforces_50px(self) -> None:
        """Verify that when max_step_limit=50.0 is set, displacement is capped at <= 50.0px."""
        self.orchestrator.max_step_limit = 50.0
        self.orchestrator.set_cursor_anchor((500, 500))
        self.actuator.clear()

        # Target 800px away
        self._set_right_hand_target((1300, 500))
        self._step(1.033, right=True)

        self.assertEqual(self.actuator.total_moves, 1)
        move = self.actuator.last_move
        disp = math.hypot(move[0] - 500, move[1] - 500)
        self.assertLessEqual(disp, 50.0 + 1e-6)
        self.assertEqual(move, (550, 500))

    def test_internal_versus_physical_cursor_position_consistency(self) -> None:
        """Verify that orchestrator.trusted_cursor_anchor exactly equals actuator.last_move."""
        self.orchestrator.max_step_limit = 50.0
        self.orchestrator.set_cursor_anchor((200, 200))

        # Perform 5 multi-directional jumps
        targets = [(800, 200), (800, 800), (100, 800), (500, 500), (1200, 300)]
        for i, target in enumerate(targets):
            self.actuator.clear()
            self._set_right_hand_target(target)
            self._step(1.000 + i * 0.033, right=True)

            self.assertEqual(self.actuator.total_moves, 1)
            actual_move = self.actuator.last_move
            trusted_anchor = self.orchestrator.trusted_cursor_anchor
            cursor_pos = self.orchestrator.cursor_pos

            # Strictest consistency: internal anchor MUST match physical move exactly
            self.assertEqual(trusted_anchor, actual_move)
            self.assertEqual(cursor_pos, actual_move)

    def test_invalid_or_none_anchor_suppresses_movement_fail_closed(self) -> None:
        """Verify that when anchor is None and query fails, movement is strictly suppressed."""
        self.orchestrator.set_cursor_anchor(None)
        self.actuator.query_fail = True
        self.actuator.clear()

        # Distant hand target
        self._set_right_hand_target((600, 600))
        self._step(1.033, right=True)

        # 0 actuator move calls must be emitted
        self.assertEqual(self.actuator.total_moves, 0)
        self.assertIsNone(self.orchestrator.cursor_pos)


class TestMouseActuatorCursorQuery(unittest.TestCase):
    """Unit tests for MouseActuator.get_cursor_pos() with mocked native Win32 calls."""

    def test_actuator_get_cursor_pos_success(self) -> None:
        """Verify get_cursor_pos maps valid Windows point to virtual desktop coordinates."""
        from ctypes import wintypes
        import core.actuator as act_mod

        actuator = act_mod.MouseActuator(1920, 1080, origin_x=0, origin_y=0)

        def mock_get_cursor_pos(pt_ref):
            pt_ref._obj.x = 550
            pt_ref._obj.y = 350
            return 1

        with patch.object(act_mod._user32, "GetCursorPos", side_effect=mock_get_cursor_pos):
            pos = actuator.get_cursor_pos()
            self.assertEqual(pos, (550, 350))

    def test_actuator_get_cursor_pos_multi_monitor_negative_origin(self) -> None:
        """Verify get_cursor_pos correctly offsets negative virtual desktop origin."""
        import core.actuator as act_mod

        # Secondary monitor to the left with width 1920: origin_x = -1920
        actuator = act_mod.MouseActuator(3840, 1080, origin_x=-1920, origin_y=0)

        def mock_get_cursor_pos(pt_ref):
            pt_ref._obj.x = -1000  # On left monitor
            pt_ref._obj.y = 450
            return 1

        with patch.object(act_mod._user32, "GetCursorPos", side_effect=mock_get_cursor_pos):
            pos = actuator.get_cursor_pos()
            # -1000 - (-1920) = 920
            self.assertEqual(pos, (920, 450))

    def test_actuator_get_cursor_pos_clamped_to_virtual_bounds(self) -> None:
        """Verify out-of-bounds cursor coordinates are clamped safely."""
        import core.actuator as act_mod

        actuator = act_mod.MouseActuator(1920, 1080, origin_x=0, origin_y=0)

        def mock_get_cursor_pos(pt_ref):
            pt_ref._obj.x = 2500
            pt_ref._obj.y = -50
            return 1

        with patch.object(act_mod._user32, "GetCursorPos", side_effect=mock_get_cursor_pos):
            pos = actuator.get_cursor_pos()
            self.assertEqual(pos, (1919, 0))

    def test_actuator_get_cursor_pos_api_failure_returns_none(self) -> None:
        """Verify API failure returns None explicitly without substituting dummy coordinates."""
        import core.actuator as act_mod

        actuator = act_mod.MouseActuator(1920, 1080, origin_x=0, origin_y=0)

        with patch.object(act_mod._user32, "GetCursorPos", return_value=0):
            pos = actuator.get_cursor_pos()
            self.assertIsNone(pos, "API failure must return None, not dummy (0, 0)")

    def test_actuator_get_cursor_pos_no_user32_returns_none(self) -> None:
        """Verify absence of user32 handles safely and returns None."""
        import core.actuator as act_mod

        actuator = act_mod.MouseActuator(1920, 1080, origin_x=0, origin_y=0)

        with patch.object(act_mod, "_user32", None):
            pos = actuator.get_cursor_pos()
            self.assertIsNone(pos)

    def test_actuator_get_cursor_pos_uninitialized_subclass_returns_none(self) -> None:
        """Verify subclass that did not call MouseActuator.__init__() returns None safely."""
        from core.actuator import MouseActuator

        class BareSubclass(MouseActuator):
            def __init__(self):
                # Omit super().__init__()
                pass

        sub = BareSubclass()
        pos = sub.get_cursor_pos()
        self.assertIsNone(pos)

    def test_actuator_get_cursor_pos_invalid_dimensions_returns_none(self) -> None:
        """Verify non-positive or invalid desktop dimensions return None safely."""
        from core.actuator import MouseActuator

        for invalid_w, invalid_h in [(0, 1080), (-1920, 1080), (1920, 0), ("invalid", 1080)]:
            act = MouseActuator.__new__(MouseActuator)
            act._total_w = invalid_w
            act._total_h = invalid_h
            self.assertIsNone(act.get_cursor_pos())


if __name__ == "__main__":
    unittest.main()

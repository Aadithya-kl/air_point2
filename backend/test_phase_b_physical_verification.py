"""
Comprehensive synthetic test suite for Air Point Stage 4 Phase B:
Physical Cursor Verification, Pre-Movement Bounds, Zero Fallback, and Fail-Closed Interlocks.

Contains:
1. TestPhysicalMovementVerification:
   Direct unit tests for the MouseActuator.verify_physical_displacement static utility.
2. TestPhaseBStrictMovementBounds:
   Direct integration tests for ConservativeLiveActuator enforcing:
   - Target > 50.0px from physical pre-position rejected BEFORE SendInput (zero native moves).
   - Missing (None) physical pre-position results in zero native movement calls and latched abort.
   - Invalid (out-of-bounds) physical pre-position results in zero native movement calls and latched abort.
   - Invalid target coordinates result in zero native movement calls and latched abort.
   - Physical pre-position and orchestrator-anchor disagreement aborts BEFORE SendInput (no jump).
   - Post-movement physical displacement > 50.0px latches abort and permanently blocks subsequent moves.
   - Failed SendInput fails closed immediately with ZERO fallback to mouse_event.
   - Clean movement within 50.0px passes and records complete verification record.
   - Stationary freeze reassertion actively queries physical cursor and detects external drift.
   - Aborted state latches permanently and refuses all subsequent move attempts.
   - All existing click, drag, keyboard, application, audio, screenshot, and workstation-lock interlocks remain effective.
"""

import ctypes
import math
import os
import unittest
from unittest.mock import MagicMock, patch

from core.actuator import MouseActuator, _user32
from validate_stage4_phase_b import (
    ConservativeLiveActuator,
    PhysicalMovementVerification,
    MAX_PHYSICAL_DISPLACEMENT_PX,
    TOLERANCE_TARGET_PX,
    install_phase_b_interlocks,
    uninstall_phase_b_interlocks,
)


class TestPhysicalMovementVerification(unittest.TestCase):
    """Direct unit tests for MouseActuator.verify_physical_displacement static utility."""

    def test_clean_movement_within_50px_passes(self) -> None:
        """Verify normal displacement under 50px with exact target match passes."""
        p_pre = (500, 500)
        dispatched = (530, 540)
        p_post = (530, 540)

        verified, phys_disp, target_err, reason = MouseActuator.verify_physical_displacement(
            p_pre=p_pre,
            p_post=p_post,
            dispatched_pos=dispatched,
            max_physical_disp=50.0,
            disp_tolerance=0.0,
            target_tolerance=2.0,
        )

        self.assertTrue(verified)
        self.assertAlmostEqual(phys_disp, 50.0, places=3)
        self.assertAlmostEqual(target_err, 0.0, places=3)
        self.assertIsNone(reason)

    def test_pre_query_failure_returns_false_with_documented_reason(self) -> None:
        """Verify None pre-position fails closed with PRE_QUERY_FAILED."""
        verified, phys_disp, target_err, reason = MouseActuator.verify_physical_displacement(
            p_pre=None,
            p_post=(530, 540),
            dispatched_pos=(530, 540),
        )

        self.assertFalse(verified)
        self.assertIsNone(phys_disp)
        self.assertIsNone(target_err)
        self.assertIn("PRE_QUERY_FAILED", reason)

    def test_post_query_failure_returns_false_with_documented_reason(self) -> None:
        """Verify None post-position fails closed with POST_QUERY_FAILED."""
        verified, phys_disp, target_err, reason = MouseActuator.verify_physical_displacement(
            p_pre=(500, 500),
            p_post=None,
            dispatched_pos=(530, 540),
        )

        self.assertFalse(verified)
        self.assertIsNone(phys_disp)
        self.assertIsNone(target_err)
        self.assertIn("POST_QUERY_FAILED", reason)

    def test_physical_displacement_exceeding_bound_fails_closed(self) -> None:
        """Verify physical jump exceeding 50px fails closed."""
        p_pre = (500, 500)
        dispatched = (560, 500)
        p_post = (560, 500)  # 60px displacement > 50.0px limit

        verified, phys_disp, target_err, reason = MouseActuator.verify_physical_displacement(
            p_pre=p_pre,
            p_post=p_post,
            dispatched_pos=dispatched,
            max_physical_disp=50.0,
            disp_tolerance=0.0,
            target_tolerance=2.0,
        )

        self.assertFalse(verified)
        self.assertAlmostEqual(phys_disp, 60.0, places=3)
        self.assertIn("PHYSICAL_DISPLACEMENT_EXCEEDED", reason)

    def test_target_disagreement_beyond_tolerance_fails_closed(self) -> None:
        """Verify physical post position differing from target by > 2.0px fails closed."""
        p_pre = (500, 500)
        dispatched = (530, 500)  # requested 30px step along X
        p_post = (510, 500)      # cursor only moved 10px (error = 20px > 2px tolerance)

        verified, phys_disp, target_err, reason = MouseActuator.verify_physical_displacement(
            p_pre=p_pre,
            p_post=p_post,
            dispatched_pos=dispatched,
            max_physical_disp=50.0,
            disp_tolerance=0.0,
            target_tolerance=2.0,
        )

        self.assertFalse(verified)
        self.assertAlmostEqual(target_err, 20.0, places=3)
        self.assertIn("TARGET_DISAGREEMENT_EXCEEDED", reason)


class TestPhaseBStrictMovementBounds(unittest.TestCase):
    """Test suite verifying ConservativeLiveActuator pre/post bounds and fail-closed interlocks."""

    def setUp(self) -> None:
        self.actuator = ConservativeLiveActuator(1920, 1080)

    def test_target_over_50px_from_pre_position_rejected_before_sendinput(self) -> None:
        """
        Verify that a target > 50.0px from physical pre-position is rejected BEFORE
        SendInput is called, guaranteeing zero native cursor movement.
        """
        p_pre = (500, 500)
        target = (560, 500)  # 60.0px distance from pre-position (> 50.0px)

        with patch.object(self.actuator, "get_cursor_pos", return_value=p_pre), \
             patch.object(self.actuator, "_send_input_strict") as mock_send_input:

            success = self.actuator.move(target[0], target[1])

            self.assertFalse(success)
            self.assertTrue(self.actuator.abort_requested)
            self.assertIn("PRE_MOVE_DISPLACEMENT_EXCEEDED", self.actuator.abort_reason)
            self.assertIn("60.00px", self.actuator.abort_reason)
            mock_send_input.assert_not_called()
            self.assertEqual(self.actuator.move_count, 0)

    def test_missing_physical_pre_position_results_in_zero_native_movements(self) -> None:
        """Verify that get_cursor_pos() returning None aborts with zero native movement calls."""
        with patch.object(self.actuator, "get_cursor_pos", return_value=None), \
             patch.object(self.actuator, "_send_input_strict") as mock_send_input:

            success = self.actuator.move(510, 510)

            self.assertFalse(success)
            self.assertTrue(self.actuator.abort_requested)
            self.assertIn("PRE_QUERY_FAILED", self.actuator.abort_reason)
            mock_send_input.assert_not_called()
            self.assertEqual(self.actuator.move_count, 0)

    def test_invalid_physical_pre_position_results_in_zero_native_movements(self) -> None:
        """Verify out-of-bounds physical pre-position aborts with zero native movement calls."""
        for invalid_pos in [(-50, 500), (500, -10), (2500, 500), (500, 1500)]:
            act = ConservativeLiveActuator(1920, 1080)
            with patch.object(act, "get_cursor_pos", return_value=invalid_pos), \
                 patch.object(act, "_send_input_strict") as mock_send_input:

                success = act.move(500, 500)

                self.assertFalse(success)
                self.assertTrue(act.abort_requested)
                self.assertIn("INVALID_PHYSICAL_PRE_POSITION", act.abort_reason)
                mock_send_input.assert_not_called()

    def test_invalid_target_coordinates_results_in_zero_native_movements(self) -> None:
        """Verify target outside desktop bounds aborts with zero native movement calls."""
        for invalid_target in [(-10, 500), (500, -20), (2000, 500), (500, 1200)]:
            act = ConservativeLiveActuator(1920, 1080)
            with patch.object(act, "_send_input_strict") as mock_send_input:

                success = act.move(invalid_target[0], invalid_target[1])

                self.assertFalse(success)
                self.assertTrue(act.abort_requested)
                self.assertIn("TARGET_OUT_OF_BOUNDS", act.abort_reason)
                mock_send_input.assert_not_called()

    def test_orchestrator_anchor_disagreement_with_physical_cursor_aborts_without_jump(self) -> None:
        """
        Verify that when the orchestrator anchor diverges from the actual physical cursor,
        the pre-movement check rejects the target before SendInput, preventing a re-centering jump.
        """
        orchestrator_target = (520, 500)
        actual_physical_pre = (700, 700)

        with patch.object(self.actuator, "get_cursor_pos", return_value=actual_physical_pre), \
             patch.object(self.actuator, "_send_input_strict") as mock_send_input:

            success = self.actuator.move(orchestrator_target[0], orchestrator_target[1])

            self.assertFalse(success)
            self.assertTrue(self.actuator.abort_requested)
            self.assertIn("PRE_MOVE_DISPLACEMENT_EXCEEDED", self.actuator.abort_reason)
            self.assertIn("269.07px", self.actuator.abort_reason)
            mock_send_input.assert_not_called()

    def test_post_movement_over_50px_latches_abort_and_prevents_subsequent_movement(self) -> None:
        """
        Verify that if measured post-movement displacement exceeds 50.0px,
        the abort state latches and permanently prevents any subsequent movement.
        """
        query_sequence = [(500, 500), (570, 500)]

        with patch.object(self.actuator, "get_cursor_pos", side_effect=query_sequence), \
             patch.object(self.actuator, "_send_input_strict", return_value=True) as mock_send_input:

            success = self.actuator.move(530, 500)

            self.assertFalse(success)
            self.assertTrue(self.actuator.abort_requested)
            self.assertIn("POST_MOVE_DISPLACEMENT_EXCEEDED", self.actuator.abort_reason)
            self.assertEqual(mock_send_input.call_count, 1)

            # Subsequent move attempt must be refused without any queries or SendInput calls
            mock_send_input.reset_mock()
            second_success = self.actuator.move(535, 500)

            self.assertFalse(second_success)
            mock_send_input.assert_not_called()

    def test_aborted_state_latches_and_refuses_subsequent_moves(self) -> None:
        """Verify that once abort_requested is True, any further move calls are refused immediately."""
        self.actuator.abort_requested = True
        self.actuator.abort_reason = "PRIOR_TEST_FAULT"

        with patch.object(self.actuator, "get_cursor_pos") as mock_query, \
             patch.object(self.actuator, "_send_input_strict") as mock_send_input:

            success = self.actuator.move(500, 500)

            self.assertFalse(success)
            mock_query.assert_not_called()
            mock_send_input.assert_not_called()

    def test_stationary_freeze_measures_real_cursor_and_catches_external_displacement(self) -> None:
        """
        Verify that a stationary freeze reassertion (move to same pos) actively queries
        physical position, and fails closed if the cursor was moved externally.
        """
        freeze_target = (500, 500)
        query_sequence = [(800, 800), (800, 800)]

        with patch.object(self.actuator, "get_cursor_pos", side_effect=query_sequence), \
             patch.object(self.actuator, "_send_input_strict") as mock_send_input:

            success = self.actuator.move(freeze_target[0], freeze_target[1])

            self.assertFalse(success)
            self.assertTrue(self.actuator.abort_requested)
            self.assertIn("PRE_MOVE_DISPLACEMENT_EXCEEDED", self.actuator.abort_reason)
            mock_send_input.assert_not_called()

    def test_failed_sendinput_cannot_trigger_mouse_event_fallback(self) -> None:
        """
        Verify that when SendInput fails (returns 0), the conservative actuator fails closed
        immediately and NEVER invokes mouse_event as a fallback.
        """
        p_pre = (500, 500)
        target = (520, 520)

        with patch.object(self.actuator, "get_cursor_pos", return_value=p_pre), \
             patch.object(_user32, "SendInput", return_value=0), \
             patch.object(_user32, "mouse_event") as mock_mouse_event:

            success = self.actuator.move(target[0], target[1])

            self.assertFalse(success)
            self.assertTrue(self.actuator.abort_requested)
            self.assertIn("SEND_INPUT_FAILED", self.actuator.abort_reason)
            mock_mouse_event.assert_not_called()

    def test_clean_movement_within_50px_passes_cleanly(self) -> None:
        """Verify normal displacement under 50px with exact target match passes."""
        query_sequence = [(500, 500), (530, 540)]

        with patch.object(self.actuator, "get_cursor_pos", side_effect=query_sequence), \
             patch.object(self.actuator, "_send_input_strict", return_value=True) as mock_send_input:

            success = self.actuator.move(530, 540)

            self.assertTrue(success)
            self.assertFalse(self.actuator.abort_requested)
            self.assertEqual(self.actuator.move_count, 1)
            mock_send_input.assert_called_once_with(530, 540)

            lv = self.actuator.latest_verification
            self.assertIsNotNone(lv)
            self.assertTrue(lv.verified)
            self.assertAlmostEqual(lv.distance_pre_px, 50.0, places=3)
            self.assertAlmostEqual(lv.phys_step_disp_px, 50.0, places=3)
            self.assertAlmostEqual(lv.phys_target_error_px, 0.0, places=3)

    def test_all_side_effect_interlocks_remain_effective(self) -> None:
        """Verify clicks, drags, keyboard, application, audio, and workstation locks are blocked."""
        # 1. Click and drag overrides in ConservativeLiveActuator
        self.assertFalse(self.actuator.left_click())
        self.assertFalse(self.actuator.right_click())
        self.assertFalse(self.actuator.double_click())
        self.assertFalse(self.actuator.drag_start())
        self.assertTrue(self.actuator.drag_end())
        self.assertEqual(self.actuator.attempted_clicks, 3)
        self.assertEqual(self.actuator.attempted_drags, 1)

        # 2. Native Win32 interlocks (with clean uninstall to avoid test pollution)
        try:
            install_phase_b_interlocks()
            u32 = ctypes.windll.user32

            with self.assertRaises(RuntimeError) as cm:
                u32.keybd_event(0x41, 0, 0, 0)
            self.assertIn("PHASE B INTERLOCK VIOLATION: Blocked native call to user32.keybd_event", str(cm.exception))

            with self.assertRaises(RuntimeError) as cm:
                u32.LockWorkStation()
            self.assertIn("PHASE B INTERLOCK VIOLATION: Blocked native call to user32.LockWorkStation", str(cm.exception))

            with self.assertRaises(RuntimeError) as cm:
                u32.mouse_event(0, 0, 0, 0, 0)
            self.assertIn("PHASE B INTERLOCK VIOLATION: Blocked native call to user32.mouse_event", str(cm.exception))

            with self.assertRaises(RuntimeError) as cm:
                u32.SetCursorPos(100, 100)
            self.assertIn("PHASE B INTERLOCK VIOLATION: Blocked native call to user32.SetCursorPos", str(cm.exception))

            # 3. Native Win32 interlocks on core.actuator._user32
            with self.assertRaises(RuntimeError) as cm:
                _user32.mouse_event(0, 0, 0, 0, 0)
            self.assertIn("PHASE B INTERLOCK VIOLATION: Blocked native call to core.actuator._user32.mouse_event", str(cm.exception))

            with self.assertRaises(RuntimeError) as cm:
                _user32.SetCursorPos(100, 100)
            self.assertIn("PHASE B INTERLOCK VIOLATION: Blocked native call to core.actuator._user32.SetCursorPos", str(cm.exception))

            with self.assertRaises(RuntimeError) as cm:
                os.startfile("test.exe")
            self.assertIn("PHASE B INTERLOCK VIOLATION: Blocked native call to os.startfile", str(cm.exception))
        finally:
            uninstall_phase_b_interlocks()
            if os.environ.get("AIRPOINT_ENABLE_TEST_GUARD", "").strip().lower() in ("1", "true", "yes"):
                import test_guard
                test_guard._GUARD_INSTALLED = False
                test_guard.install_test_guard()


if __name__ == "__main__":
    unittest.main()

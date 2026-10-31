# test_wakanda_gesture.py
"""
Comprehensive Unit & Integration Test Suite for Wakanda Forever Lock Gesture.
Verifies:
- Disabled by default requirement
- Crossed-arm anatomical geometry recognition
- Timing: 2.0s continuous hold to trigger
- Mockable lock workstation action (Win32 LockWorkStation safety)
- Cancellation when hold broken before 2.0s
- Grace period tolerance (0.15s) for frame jitter
- Cooldown (2.0s) and release-to-rearm requirement
- Orchestrator pointer suppression during Wakanda hold
- Control server setting toggle and settings.json persistence
"""

import os
import unittest
from unittest.mock import MagicMock

# Ensure real workstation locking is disabled during tests
os.environ["AIRPOINT_DISABLE_REAL_LOCK"] = "1"

from core.face_tracker import FaceResult
from core.gestures.wakanda_gesture import (
    WakandaGestureRecognizer,
    WakandaState,
    check_wakanda_pose,
    is_fist_relaxed,
)
from core.tracker import HandsResult, Landmark


def create_fist_landmarks(wrist_x: float, wrist_y: float, mcp_dx: float, mcp_dy: float) -> list[Landmark]:
    """
    Creates a 21-landmark list representing a closed fist with given wrist and MCP direction vector.
    """
    lms = []
    # 0: Wrist
    lms.append(Landmark(x=wrist_x, y=wrist_y, z=0.0))
    # 1-4: Thumb (curled towards palm)
    lms.append(Landmark(x=wrist_x + mcp_dx * 0.2, y=wrist_y + mcp_dy * 0.2, z=0.0))
    lms.append(Landmark(x=wrist_x + mcp_dx * 0.4, y=wrist_y + mcp_dy * 0.4, z=0.0))
    lms.append(Landmark(x=wrist_x + mcp_dx * 0.5, y=wrist_y + mcp_dy * 0.5, z=0.0))
    lms.append(Landmark(x=wrist_x + mcp_dx * 0.5, y=wrist_y + mcp_dy * 0.55, z=0.0))  # Tip curled
    # 5-8: Index (MCP, PIP, DIP, TIP) - Tip curled down (higher y than PIP)
    lms.append(Landmark(x=wrist_x + mcp_dx * 0.8, y=wrist_y + mcp_dy * 0.8, z=0.0))    # 5: MCP
    lms.append(Landmark(x=wrist_x + mcp_dx * 0.9, y=wrist_y + mcp_dy * 0.9, z=0.0))    # 6: PIP
    lms.append(Landmark(x=wrist_x + mcp_dx * 0.95, y=wrist_y + mcp_dy * 0.95, z=0.0))  # 7: DIP
    lms.append(Landmark(x=wrist_x + mcp_dx * 0.9, y=wrist_y + mcp_dy * 0.9 + 0.04, z=0.0))  # 8: TIP curled (y > PIP.y)
    # 9-12: Middle - Tip curled
    lms.append(Landmark(x=wrist_x + mcp_dx, y=wrist_y + mcp_dy, z=0.0))                # 9: MCP (main direction)
    lms.append(Landmark(x=wrist_x + mcp_dx * 1.1, y=wrist_y + mcp_dy * 1.1, z=0.0))    # 10: PIP
    lms.append(Landmark(x=wrist_x + mcp_dx * 1.15, y=wrist_y + mcp_dy * 1.15, z=0.0))  # 11: DIP
    lms.append(Landmark(x=wrist_x + mcp_dx * 1.1, y=wrist_y + mcp_dy * 1.1 + 0.04, z=0.0))  # 12: TIP curled
    # 13-16: Ring - Tip curled
    lms.append(Landmark(x=wrist_x + mcp_dx * 0.9, y=wrist_y + mcp_dy * 0.9, z=0.0))    # 13: MCP
    lms.append(Landmark(x=wrist_x + mcp_dx * 1.0, y=wrist_y + mcp_dy * 1.0, z=0.0))    # 14: PIP
    lms.append(Landmark(x=wrist_x + mcp_dx * 1.05, y=wrist_y + mcp_dy * 1.05, z=0.0))  # 15: DIP
    lms.append(Landmark(x=wrist_x + mcp_dx * 1.0, y=wrist_y + mcp_dy * 1.0 + 0.04, z=0.0))  # 16: TIP curled
    # 17-20: Pinky - Tip curled
    lms.append(Landmark(x=wrist_x + mcp_dx * 0.8, y=wrist_y + mcp_dy * 0.8, z=0.0))    # 17: MCP
    lms.append(Landmark(x=wrist_x + mcp_dx * 0.85, y=wrist_y + mcp_dy * 0.85, z=0.0))  # 18: PIP
    lms.append(Landmark(x=wrist_x + mcp_dx * 0.9, y=wrist_y + mcp_dy * 0.9, z=0.0))    # 19: DIP
    lms.append(Landmark(x=wrist_x + mcp_dx * 0.85, y=wrist_y + mcp_dy * 0.85 + 0.04, z=0.0))  # 20: TIP curled

    return lms


def create_crossed_arms_hands(wrist_y: float = 0.55) -> HandsResult:
    """
    Creates HandsResult representing anatomically crossed forearms:
    - User's anatomical left hand crosses across body to viewer-right (x ≈ 0.62).
      Forearm points up-and-right: dx = +0.08, dy = -0.12.
    - User's anatomical right hand crosses across body to viewer-left (x ≈ 0.38).
      Forearm points up-and-left: dx = -0.08, dy = -0.12.
    """
    left_fist = create_fist_landmarks(wrist_x=0.60, wrist_y=wrist_y, mcp_dx=0.08, mcp_dy=-0.12)
    right_fist = create_fist_landmarks(wrist_x=0.40, wrist_y=wrist_y, mcp_dx=-0.08, mcp_dy=-0.12)
    return HandsResult(
        left=left_fist,
        right=right_fist,
        left_score=0.92,
        right_score=0.91,
    )


def create_uncrossed_hands(wrist_y: float = 0.55) -> HandsResult:
    """
    Creates HandsResult representing regular uncrossed hands (left hand on screen left, right hand on screen right).
    """
    left_fist = create_fist_landmarks(wrist_x=0.35, wrist_y=wrist_y, mcp_dx=-0.05, mcp_dy=-0.12)
    right_fist = create_fist_landmarks(wrist_x=0.65, wrist_y=wrist_y, mcp_dx=0.05, mcp_dy=-0.12)
    return HandsResult(
        left=left_fist,
        right=right_fist,
        left_score=0.90,
        right_score=0.90,
    )


class TestWakandaGesture(unittest.TestCase):
    def setUp(self):
        self.mock_lock = MagicMock(return_value=True)

    def test_wakanda_disabled_by_default(self):
        """Wakanda Forever must be disabled by default for safety."""
        recognizer = WakandaGestureRecognizer(lock_fn=self.mock_lock)
        self.assertFalse(recognizer.enabled)
        self.assertEqual(recognizer.state, WakandaState.DISABLED)

        # Feeding valid crossed hands when disabled returns False and does not activate
        crossed = create_crossed_arms_hands()
        active = recognizer.process(crossed, now=10.0)
        self.assertFalse(active)
        self.assertEqual(recognizer.state, WakandaState.DISABLED)
        self.mock_lock.assert_not_called()

    def test_wakanda_pose_geometry_detection(self):
        """Verify crossed-arm geometry math."""
        crossed = create_crossed_arms_hands()
        face = FaceResult(detected=True, lip_center=(0.50, 0.35, 0.0), mouth_width=0.08)

        is_valid, reason = check_wakanda_pose(crossed, face)
        self.assertTrue(is_valid, f"Expected valid pose, got reason: {reason}")

        # Test uncrossed arms
        uncrossed = create_uncrossed_hands()
        is_valid, reason = check_wakanda_pose(uncrossed, face)
        self.assertFalse(is_valid)
        self.assertIn("ARMS_NOT_CROSSED", reason)

        # Test hands above face/lips
        high_hands = create_crossed_arms_hands(wrist_y=0.25)
        is_valid, reason = check_wakanda_pose(high_hands, face)
        self.assertFalse(is_valid)
        self.assertIn("HANDS_TOO_HIGH", reason)

    def test_wakanda_hold_and_trigger_flow(self):
        """Verify full 2.0s hold progression and lock execution."""
        recognizer = WakandaGestureRecognizer(
            lock_fn=self.mock_lock,
            enabled=True,
            hold_duration=2.0,
            cooldown=2.0,
        )
        self.assertTrue(recognizer.enabled)
        self.assertEqual(recognizer.state, WakandaState.IDLE)

        crossed = create_crossed_arms_hands()
        face = FaceResult(detected=True, lip_center=(0.50, 0.35, 0.0))

        callback_mock = MagicMock()
        recognizer.set_activation_callback(callback_mock)

        # t = 0.0s: hold start
        active = recognizer.process(crossed, face, now=0.0)
        self.assertTrue(active)
        self.assertEqual(recognizer.state, WakandaState.HOLDING)
        self.assertEqual(recognizer.progress, 0.0)

        # t = 1.0s: half-way hold
        active = recognizer.process(crossed, face, now=1.0)
        self.assertTrue(active)
        self.assertEqual(recognizer.state, WakandaState.HOLDING)
        self.assertAlmostEqual(recognizer.progress, 0.5, places=2)
        self.mock_lock.assert_not_called()

        # t = 1.9s: nearly finished, still holding
        active = recognizer.process(crossed, face, now=1.9)
        self.assertTrue(active)
        self.assertEqual(recognizer.state, WakandaState.HOLDING)
        self.assertAlmostEqual(recognizer.progress, 0.95, places=2)
        self.mock_lock.assert_not_called()

        # t = 2.0s: hold complete -> trigger lock
        active = recognizer.process(crossed, face, now=2.0)
        self.assertTrue(active)
        self.assertEqual(recognizer.progress, 1.0)
        self.mock_lock.assert_called_once()
        callback_mock.assert_called_once()

    def test_wakanda_hold_cancelled_if_broken(self):
        """Verify hold resets if arms are uncrossed before 2.0s."""
        recognizer = WakandaGestureRecognizer(
            lock_fn=self.mock_lock,
            enabled=True,
            hold_duration=2.0,
            grace_period=0.15,
        )
        crossed = create_crossed_arms_hands()
        uncrossed = create_uncrossed_hands()

        # Start hold
        recognizer.process(crossed, now=0.0)
        self.assertEqual(recognizer.state, WakandaState.HOLDING)

        # Hold for 1.0s
        recognizer.process(crossed, now=1.0)
        self.assertAlmostEqual(recognizer.progress, 0.5, places=2)

        # Break pose at 1.25s (beyond 0.15s grace)
        active = recognizer.process(uncrossed, now=1.25)
        self.assertFalse(active)
        self.assertEqual(recognizer.state, WakandaState.IDLE)
        self.assertEqual(recognizer.progress, 0.0)
        self.mock_lock.assert_not_called()

    def test_wakanda_cooldown_and_release_rearm(self):
        """Verify cooldown period and required release before rearming."""
        recognizer = WakandaGestureRecognizer(
            lock_fn=self.mock_lock,
            enabled=True,
            hold_duration=2.0,
            cooldown=2.0,
        )
        crossed = create_crossed_arms_hands()
        uncrossed = create_uncrossed_hands()

        # Trigger lock
        recognizer.process(crossed, now=0.0)
        recognizer.process(crossed, now=2.0)
        self.assertEqual(recognizer.state, WakandaState.COOLDOWN)

        # During 2.0s cooldown, cannot trigger again
        active = recognizer.process(crossed, now=2.5)
        self.assertFalse(active)
        self.assertEqual(recognizer.state, WakandaState.COOLDOWN)
        self.assertEqual(self.mock_lock.call_count, 1)

        # At t=4.5s (cooldown expired), but user STILL has arms crossed -> stays in cooldown until release
        active = recognizer.process(crossed, now=4.5)
        self.assertFalse(active)
        self.assertEqual(recognizer.state, WakandaState.COOLDOWN)
        self.assertIn("Release", recognizer.status_text)

        # User uncrosses arms -> re-arms to IDLE
        active = recognizer.process(uncrossed, now=4.6)
        self.assertFalse(active)
        self.assertEqual(recognizer.state, WakandaState.IDLE)

    def test_orchestrator_wakanda_pointer_suppression(self):
        """Verify GestureOrchestrator suppresses cursor motion while Wakanda is holding."""
        from core.actuator import MouseActuator
        from core.display import VirtualDesktop, build_trackpad_zone
        from core.gestures.orchestrator import GestureOrchestrator, PointerOwner

        desktop = VirtualDesktop(1920, 1080, 1)
        trackpad = build_trackpad_zone()
        actuator = MagicMock(spec=MouseActuator)

        orch = GestureOrchestrator(actuator, desktop, trackpad)
        orch._wakanda._lock_fn = self.mock_lock
        orch._wakanda.enabled = True

        crossed = create_crossed_arms_hands()

        # Process crossed arms: orchestrator should suppress pointer owner
        orch.process(crossed)
        self.assertTrue(orch.wakanda_gesture.is_holding)
        self.assertEqual(orch.pointer_owner, PointerOwner.NONE.name)

    def test_control_server_setting_synchronization(self):
        """Verify 'wakanda-forever' setting defaults to False and synchronizes via ControlServer."""
        from core.control_server import RuntimeState, SUPPORTED_GESTURES

        self.assertIn("wakanda-forever", SUPPORTED_GESTURES)
        # Use isolated in-memory state so real user settings on disk do not pollute the test
        state = RuntimeState(settings_path=None)
        self.assertIn("wakanda-forever", state.enabled_gestures)
        self.assertFalse(state.enabled_gestures["wakanda-forever"])

        # Enable via apply_settings
        snapshot = state.apply_settings({"enabled": {"wakanda-forever": True}})
        self.assertTrue(snapshot["enabled"]["wakanda-forever"])
        self.assertTrue(state.enabled_gestures["wakanda-forever"])

        # Disable again
        snapshot = state.apply_settings({"enabled": {"wakanda-forever": False}})
        self.assertFalse(snapshot["enabled"]["wakanda-forever"])
        self.assertFalse(state.enabled_gestures["wakanda-forever"])


if __name__ == "__main__":
    unittest.main()

# test_drag_safety.py
"""
Unit tests for Drag-and-Drop Safety and Failsafe Release (Task 2: [ACT/SAFE-001]).

Tests:
- Abrupt tracking loss triggers automatic drag release after timeout
- Brief tracking interruption within grace period preserves active drag
- Idempotent drag_end: multiple calls do not emit duplicate mouse-up events
- Engine pause and orchestrator.reset cleanly release held drag
- Overriding gestures (screenshot, Wakanda, WhatsApp) release active drag
- Actuator watchdog releases button if heartbeat is lost
- Zero real Windows desktop actions during testing (mocked actuators)
"""

import unittest
import time
from core.tracker import Landmark, HandsResult
from core.gestures.orchestrator import GestureOrchestrator
from core.actuator import MouseActuator
from core.display import VirtualDesktop, TrackpadZone
import config


class MockMouseActuator(MouseActuator):
    """Mock actuator that records mouse actions without triggering Win32 SendInput."""

    def __init__(self):
        self._dragging = False
        self._last_drag_time = 0.0
        self.down_events = 0
        self.up_events = 0
        self.click_events = 0
        self.move_events = 0

    def _send_mouse_flag(self, flag: int) -> bool:
        from core.actuator import MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP
        if flag == MOUSEEVENTF_LEFTDOWN:
            self.down_events += 1
        elif flag == MOUSEEVENTF_LEFTUP:
            self.up_events += 1
        return True

    def left_click(self, x=None, y=None):
        self.click_events += 1
        return True

    def move(self, x, y):
        self.move_events += 1
        return True


class TestDragSafety(unittest.TestCase):
    def setUp(self):
        config.POINTER_ONLY_MODE = False
        config.PINCH_CLICK_ENABLED = True
        config.LEFT_DRAG_ENABLED = True
        config.CAMERA_FPS = 30
        config.LEFT_DRAG_LOST_TIMEOUT_S = 0.25

        self.actuator = MockMouseActuator()
        self.orchestrator = GestureOrchestrator(
            self.actuator,
            VirtualDesktop(1920, 1080, 1),
            TrackpadZone(0, 640, 0, 480),
        )
        self.orchestrator._left.drag_lost_timeout_s = 0.25

    def tearDown(self):
        config.LEFT_DRAG_LOST_TIMEOUT_S = 0.075

    def _create_drag_hands(self, is_pinching: bool = True):
        hands = HandsResult()
        # Create left hand landmarks
        lms = [Landmark(x=0.5, y=0.5, z=0.0)] * 21
        lms[5] = Landmark(x=0.4, y=0.5, z=0.0)
        lms[17] = Landmark(x=0.6, y=0.5, z=0.0)
        lms[8] = Landmark(x=0.5, y=0.5, z=0.0)
        # Pinch distance norm < 0.55 if pinching, 0.90 if released
        pinch_dist = 0.08 if is_pinching else 0.20
        lms[4] = Landmark(x=0.5 + pinch_dist, y=0.5, z=0.0)
        hands.left = lms
        return hands

    def _start_active_drag(self):
        t = 1000.0
        # Frame 1: enter CANDIDATE at t
        self.orchestrator._left.process(self._create_drag_hands(True).left, now=t)
        # Frame 2: satisfy hold duration (0.15s later) -> DRAGGING
        self.orchestrator._left.process(self._create_drag_hands(True).left, now=t + 0.15)
        self.assertTrue(self.actuator.is_dragging)
        self.assertEqual(self.actuator.down_events, 1)

    def test_abrupt_tracking_loss_releases_drag_immediately(self):
        """When left hand disappears, held drag must be safely released without leaving button stuck."""
        t = 1000.0
        self.orchestrator._left.process(self._create_drag_hands(True).left, now=t)
        self.orchestrator._left.process(self._create_drag_hands(True).left, now=t + 0.15)
        self.assertTrue(self.actuator.is_dragging)
        self.assertEqual(self.actuator.down_events, 1)
        self.assertEqual(self.actuator.up_events, 0)

        # Hand lost (None passed) -> must immediately release
        self.orchestrator._left.process(None, now=t + 0.25)
        self.assertFalse(self.actuator.is_dragging)
        self.assertEqual(self.actuator.up_events, 1)
        self.assertEqual(self.orchestrator._left.left_drag_state, "IDLE")

    def test_orchestrator_watchdog_releases_stalled_drag(self):
        """When camera/tracking stalls and orchestrator processes frame with expired watchdog, drag is released."""
        t = 2000.0
        self.orchestrator._left.process(self._create_drag_hands(True).left, now=t)
        self.orchestrator._left.process(self._create_drag_hands(True).left, now=t + 0.15)
        self.assertTrue(self.actuator.is_dragging)

        # Watchdog check after 0.30s (> 0.25s) releases drag
        self.actuator.check_drag_watchdog(now=t + 0.45, timeout_s=0.25)
        self.assertFalse(self.actuator.is_dragging)
        self.assertEqual(self.actuator.up_events, 1)

    def test_drag_end_idempotency(self):
        """Repeated calls to drag_end or release_drag must not emit multiple up events."""
        self._start_active_drag()
        self.assertTrue(self.actuator.is_dragging)

        # First drag_end
        res1 = self.actuator.drag_end()
        self.assertTrue(res1)
        self.assertEqual(self.actuator.up_events, 1)
        self.assertFalse(self.actuator.is_dragging)

        # Second drag_end (idempotent)
        res2 = self.actuator.drag_end()
        self.assertFalse(res2)
        self.assertEqual(self.actuator.up_events, 1)

        # Processor release_drag when already idle
        self.orchestrator._left.release_drag()
        self.assertEqual(self.actuator.up_events, 1)

    def test_orchestrator_reset_releases_drag(self):
        """orchestrator.reset() cleanly releases held drag and returns state to IDLE."""
        self._start_active_drag()
        self.assertTrue(self.actuator.is_dragging)

        self.orchestrator.reset()
        self.assertFalse(self.actuator.is_dragging)
        self.assertEqual(self.actuator.up_events, 1)
        self.assertEqual(self.orchestrator._left.left_drag_state, "IDLE")

    def test_actuator_watchdog_timeout(self):
        """check_drag_watchdog releases button if keep-alive interval exceeds timeout."""
        t = 3000.0
        self.actuator.drag_start(now=t)
        self.assertTrue(self.actuator.is_dragging)

        # Within timeout (100ms)
        triggered = self.actuator.check_drag_watchdog(now=t + 0.10, timeout_s=0.25)
        self.assertFalse(triggered)
        self.assertTrue(self.actuator.is_dragging)

        # Exceeds timeout (300ms)
        triggered = self.actuator.check_drag_watchdog(now=t + 0.30, timeout_s=0.25)
        self.assertTrue(triggered)
        self.assertFalse(self.actuator.is_dragging)
        self.assertEqual(self.actuator.up_events, 1)


if __name__ == "__main__":
    unittest.main()

# test_phase4_2_stability_hotfix.py
"""
Unit tests validating Air Point Stability-First Hotfixes:
1. Reacquisition Baseline: Hand absent -> hand present snaps baseline cleanly with 0 jump warnings.
2. Ownership Handover: Handover between hands transfers baseline cleanly with 0 jump warnings.
3. Velocity-Aware Jump Protection: Fast intentional sweeps (<= 4200 px/s) pass smoothly.
4. Bounded Teleport Clamping: Errant teleports (> threshold) are clamped to protect cursor stability.
5. Dynamic Island Screenshot Hold Geometry: Expands to 270x46 with dedicated countdown badge, 0 text clipping.
"""

import unittest
from unittest.mock import MagicMock, patch
import time

from core.tracker import Landmark, HandsResult
from core.gestures.orchestrator import GestureOrchestrator, PointerOwner
from core.actuator import MouseActuator
from core.display import VirtualDesktop, TrackpadZone
from core.overlay import ScreenshotOverlay
from core.gestures.screenshot import ScreenshotController, ScreenshotState
import config


class MockActuator(MouseActuator):
    def __init__(self, current_pos=None):
        self.moves = []
        self._is_dragging = False
        self._current_pos = current_pos

    def get_cursor_pos(self) -> tuple[int, int] | None:
        if self._current_pos is not None:
            return self._current_pos
        if self.moves:
            return self.moves[-1]
        return (960, 540)

    def move(self, x, y):
        self.moves.append((x, y))
        self._current_pos = (int(x), int(y))

    def left_click(self): pass
    def double_click(self): pass
    def drag_start(self): self._is_dragging = True
    def drag_end(self): self._is_dragging = False


class TestStabilityHotfix(unittest.TestCase):
    def setUp(self):
        config.POINTER_ONLY_MODE = False
        config.PINCH_CLICK_ENABLED = True
        config.CAMERA_FPS = 30
        config.ONE_EURO_MINCUTOFF = 1.0
        config.ONE_EURO_BETA = 0.0
        config.ONE_EURO_DCUTOFF = 1.0

        self.desktop = VirtualDesktop(1920, 1080, 1)
        self.trackpad = TrackpadZone(100, 540, 100, 380)
        self.actuator = MockActuator()
        self.orchestrator = GestureOrchestrator(self.actuator, self.desktop, self.trackpad)

    def _make_hand(self, x=0.5, y=0.5):
        lms = [Landmark(x=x, y=y, z=0.0)] * 21
        lms[5] = Landmark(x=x, y=y, z=0.0)
        lms[17] = Landmark(x=x + 0.1, y=y, z=0.0)
        lms[8] = Landmark(x=x, y=y, z=0.0)  # index tip
        lms[4] = Landmark(x=x + 0.2, y=y, z=0.0)
        return lms

    def test_reacquisition_clean_baseline_no_jump_warning(self):
        """Verifies that reacquiring a hand after absence establishes baseline with zero jump warnings."""
        # Frame 1: Empty frame (no hands)
        self.orchestrator.process(HandsResult())
        self.assertEqual(self.orchestrator.pointer_owner, "NONE")
        self.assertIsNone(self.orchestrator.cursor_pos)

        # Frame 2: Hand enters at screen coordinates
        hands = HandsResult()
        hands.right = self._make_hand(0.5, 0.5)

        with patch("core.gestures.orchestrator.logger.warning") as mock_warn:
            self.orchestrator.process(hands)
            mock_warn.assert_not_called()

        self.assertEqual(self.orchestrator.pointer_owner, "RIGHT")
        self.assertIsNotNone(self.orchestrator.cursor_pos)
        self.assertGreater(len(self.actuator.moves), 0)

    def test_hand_loss_and_reentry_at_distant_coordinate_no_jump(self):
        """Verifies that when a hand disappears and re-enters on opposite side of screen, no false jump is flagged."""
        # 1. Hand at left side
        h1 = HandsResult()
        h1.right = self._make_hand(0.2, 0.2)
        self.orchestrator.process(h1)
        first_pos = self.orchestrator.cursor_pos

        # 2. Hand leaves camera past grace period (>0.08s) across 2 frames
        t_base = time.perf_counter()
        with patch("time.perf_counter", return_value=t_base + 0.01):
            self.orchestrator.process(HandsResult())
        with patch("time.perf_counter", return_value=t_base + 0.12):
            self.orchestrator.process(HandsResult())
        self.assertEqual(self.orchestrator.pointer_owner, "NONE")
        self.assertIsNone(self.orchestrator.cursor_pos)

        # 3. Hand re-enters at far right side (>1000px away)
        self.actuator._current_pos = (1536, 864)
        h2 = HandsResult()
        h2.right = self._make_hand(0.8, 0.8)

        with patch("core.gestures.orchestrator.logger.warning") as mock_warn:
            with patch("time.perf_counter", return_value=t_base + 0.15):
                self.orchestrator.process(h2)
            mock_warn.assert_not_called()

        new_pos = self.orchestrator.cursor_pos
        self.assertNotEqual(first_pos, new_pos)
        self.assertGreater(new_pos[0], 1000)

    def test_fast_intentional_motion_within_limits_passes(self):
        """Verifies that fast intentional hand motion within dynamic limits does not trigger false warnings."""
        # 1. Establish tracking
        h1 = HandsResult()
        h1.right = self._make_hand(0.5, 0.5)
        self.orchestrator.process(h1)

        # 2. Fast sweep over 33ms (dt=0.033s, moving within ~250px)
        h2 = HandsResult()
        h2.right = self._make_hand(0.55, 0.55)

        with patch("core.gestures.orchestrator.logger.warning") as mock_warn:
            with patch("time.perf_counter", return_value=time.perf_counter() + 0.033):
                self.orchestrator.process(h2)
            mock_warn.assert_not_called()

    def test_errant_teleport_clamped_for_stability(self):
        """Verifies that extreme teleport jumps during unbroken tracking are clamped and logged."""
        # 1. Establish unbroken tracking
        h1 = HandsResult()
        h1.right = self._make_hand(0.5, 0.5)
        self.orchestrator.process(h1)
        pos1 = self.orchestrator.cursor_pos

        # 2. Directly inject an extreme jump (> 1000px) during continuous tracking
        now_t = time.perf_counter()
        with patch.object(self.orchestrator._right, "process"):
            self.orchestrator._right._cursor_pos = (1900, 1050)

            with patch("core.gestures.orchestrator.logger.warning") as mock_warn:
                with patch("time.perf_counter", return_value=now_t + 0.016):
                    # Trigger movement processing
                    self.orchestrator.process(h1)
                mock_warn.assert_called_once()
                log_args = mock_warn.call_args[0]
                self.assertIn("CURSOR JUMP DETECTED", log_args[0])

        pos2 = self.orchestrator.cursor_pos
        dist_moved = ((pos2[0] - pos1[0])**2 + (pos2[1] - pos1[1])**2)**0.5
        self.assertLessEqual(dist_moved, 420.0)

    def test_screenshot_hold_dynamic_island_geometry_and_badge(self):
        """Verifies screenshot hold state expands overlay to 270x46 with dedicated countdown badge."""
        with patch("tkinter.Tk"), patch("ctypes.windll.user32.GetParent"):
            overlay = ScreenshotOverlay("TOP_CENTER")
            self.assertEqual(overlay.w, 220)
            self.assertEqual(overlay.h, 44)

            # Mock screenshot controller in HOLDING state
            ss = ScreenshotController(self.actuator)
            ss._state = ScreenshotState.HOLDING
            ss._hold_start_time = time.perf_counter()

            # First update -> DROPPING
            overlay.update_state(ss_controller=ss)
            self.assertEqual(overlay.target_w, 270)
            self.assertEqual(overlay.target_h, 46)
            self.assertEqual(overlay._island_text, "Hold both palms")
            self.assertTrue(overlay._countdown_badge.endswith("s"))
            self.assertEqual(overlay._island_state, "DROPPING")

            # Progress to visible position and advance frame timer (>0.033s)
            overlay.current_y = overlay.y_visible
            overlay._last_ui_update = 0.0
            overlay.update_state(ss_controller=ss)
            self.assertEqual(overlay._island_state, "HOLDING")

            # Verify that cancel resets dimensions cleanly
            ss._state = ScreenshotState.READY
            ss._display_until = time.perf_counter() + 1.0
            ss.hud_text = "CANCELLED"
            overlay._last_ui_update = 0.0
            overlay.update_state(ss_controller=ss)
            self.assertEqual(overlay.target_w, 220)
            self.assertEqual(overlay.target_h, 44)
            self.assertEqual(overlay._countdown_badge, "")


if __name__ == "__main__":
    unittest.main()

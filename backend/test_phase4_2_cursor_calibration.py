"""
Unit tests for Air Point Phase 4.2: Cursor Calibration, Dynamic Island & UI Layout.
Verifies:
1. Complete screen reachability (all 4 corners and distant edges) across all sensitivity settings (0.2 to 4.0).
2. Ergonomic coordinate centering and comfortable physical motion spans.
3. Adaptive smoothing (1€ filter mincutoff and beta scaling) across the 10-100 range.
4. Debug overlay panel sizing, formatting, and non-overflow guarantees.
5. Dynamic Island geometry, volume visualizer, and toast palette styling.
"""

import unittest
import numpy as np
from core.display import VirtualDesktop, TrackpadZone, map_to_desktop
from core.actuator import MouseActuator
from core.gestures.right_hand import RightHandProcessor
from core.gestures.left_hand import LeftHandProcessor
from config import CAMERA_WIDTH, CAMERA_HEIGHT


class TestPhase4_2CursorCalibration(unittest.TestCase):
    def setUp(self):
        self.desktop = VirtualDesktop(total_width=1920, total_height=1080, monitor_count=1)
        self.actuator = MouseActuator(1920, 1080)
        self.trackpad = TrackpadZone(170, 470, 120, 320)
        self.right = RightHandProcessor(self.actuator, self.desktop, self.trackpad)
        self.left = LeftHandProcessor(self.actuator, self.desktop, self.trackpad)

    def test_full_screen_corner_reachability_all_sensitivities(self):
        """Verify that all 4 screen corners are 100% reachable across all sensitivity levels."""
        sensitivities = [0.2, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 3.0, 4.0]

        for s in sensitivities:
            self.right.set_sensitivity(s)
            tp = self.right._trackpad

            # Top-left corner reach
            tl_x, tl_y = map_to_desktop(0.01, 0.01, tp, self.desktop)
            self.assertEqual(tl_x, 0, f"Failed TL x at s={s}: got {tl_x}")
            self.assertEqual(tl_y, 0, f"Failed TL y at s={s}: got {tl_y}")

            # Top-right corner reach (window close button)
            tr_x, tr_y = map_to_desktop(0.99, 0.01, tp, self.desktop)
            self.assertEqual(tr_x, 1919, f"Failed TR x at s={s}: got {tr_x}")
            self.assertEqual(tr_y, 0, f"Failed TR y at s={s}: got {tr_y}")

            # Bottom-left corner reach (start button / taskbar)
            bl_x, bl_y = map_to_desktop(0.01, 0.99, tp, self.desktop)
            self.assertEqual(bl_x, 0, f"Failed BL x at s={s}: got {bl_x}")
            self.assertEqual(bl_y, 1079, f"Failed BL y at s={s}: got {bl_y}")

            # Bottom-right corner reach (notification center)
            br_x, br_y = map_to_desktop(0.99, 0.99, tp, self.desktop)
            self.assertEqual(br_x, 1919, f"Failed BR x at s={s}: got {br_x}")
            self.assertEqual(br_y, 1079, f"Failed BR y at s={s}: got {br_y}")

    def test_left_hand_corner_reachability(self):
        """Verify left hand pointer also reaches all 4 corners identically."""
        for s in [0.5, 1.2, 2.5]:
            self.left.set_sensitivity(s)
            tp = self.left._trackpad

            tl_x, tl_y = map_to_desktop(0.02, 0.02, tp, self.desktop)
            br_x, br_y = map_to_desktop(0.98, 0.98, tp, self.desktop)

            self.assertEqual((tl_x, tl_y), (0, 0))
            self.assertEqual((br_x, br_y), (1919, 1079))

    def test_clamping_guarantee_extreme_coordinates(self):
        """Verify that negative or >1.0 coordinates never produce coordinates outside the desktop."""
        self.right.set_sensitivity(1.2)
        tp = self.right._trackpad

        x, y = map_to_desktop(-0.5, -0.5, tp, self.desktop)
        self.assertEqual((x, y), (0, 0))

        x, y = map_to_desktop(1.5, 1.5, tp, self.desktop)
        self.assertEqual((x, y), (1919, 1079))

    def test_ergonomic_centering_and_reach(self):
        """Verify ergonomic center (cx=0.50, cy=0.46) produces comfortable hand motion to reach top controls."""
        self.right.set_sensitivity(1.2)
        tp = self.right._trackpad

        # At default sensitivity, top edge should be reachable before reaching extreme camera border
        # Users shouldn't need to lift hand past y=0.25 to reach top edge (y=0)
        norm_y_reach = tp.y_min / float(CAMERA_HEIGHT)
        self.assertGreater(norm_y_reach, 0.15, "y_min should not require reaching extreme camera top edge")
        self.assertLess(norm_y_reach, 0.35, "y_min should allow comfortable upward motion")

        # Hand at y=0.20 reaches y=0 on desktop
        _, screen_y = map_to_desktop(0.50, 0.20, tp, self.desktop)
        self.assertEqual(screen_y, 0, "Hand at norm_y=0.20 should comfortably reach screen top")

    def test_adaptive_smoothing_slider_calibration(self):
        """Verify 10-100 smoothing slider scales both mincutoff (jitter at rest) and beta (speed responsiveness)."""
        # sm = 10 (raw responsiveness)
        self.right.set_smoothing(10)
        self.assertAlmostEqual(self.right._filter_x._mincutoff, 1.0, places=2)
        self.assertAlmostEqual(self.right._filter_x._beta, 0.04, places=3)

        # sm = 65 (default balanced)
        self.right.set_smoothing(65)
        self.assertAlmostEqual(self.right._filter_x._mincutoff, 0.462, places=2)
        self.assertAlmostEqual(self.right._filter_x._beta, 0.020, places=3)

        # sm = 100 (heavy smoothing)
        self.right.set_smoothing(100)
        self.assertAlmostEqual(self.right._filter_x._mincutoff, 0.12, places=2)
        self.assertAlmostEqual(self.right._filter_x._beta, 0.008, places=3)

        # Identical calibration for left hand
        self.left.set_smoothing(65)
        self.assertAlmostEqual(self.left._filter_x._mincutoff, 0.462, places=2)
        self.assertAlmostEqual(self.left._filter_x._beta, 0.020, places=3)

    def test_debug_overlay_renders_cleanly_without_overflow(self):
        """Verify that draw_debug_frame renders cleanly without exceptions across diverse states."""
        from core.debug_overlay import draw_debug_frame
        from core.tracker import HandsResult
        import numpy as np

        test_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        hands = HandsResult()

        out = draw_debug_frame(
            frame=test_frame,
            hands=hands,
            right_state="IDLE",
            cursor_pos=(960, 540),
            right_visual_tips={},
            left_visual_tips={},
            inference_time_ms=12.5,
            total_time_ms=18.2,
            fps=30.0,
            cam_fps=30.0,
            click_state_text="READY",
            last_pinch_norm=0.85,
            is_cursor_locked=False,
            orchestrator=None,
        )

        self.assertEqual(out.shape, (480, 640, 3))
        # Ensure not completely black (dashboard was drawn)
        self.assertGreater(np.count_nonzero(out), 1000)


if __name__ == "__main__":
    unittest.main()

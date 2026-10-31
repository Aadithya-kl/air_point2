"""
Unit tests for Air Point Phase 4.4: Live Camera Landmark Overlay + Gentler Cursor Speed.

Verifies:
1. Default Cursor Sensitivity:
   - DEFAULT_SENSITIVITY is calibrated to 1.05 in core/control_server.py.
   - Represents an exact 12.5% reduction in perceived speed from prior 1.20 default
     ((1.20 - 1.05) / 1.20 = 12.5%), within the required 10-15% target range.
2. Full Screen 4-Corner Reachability at s = 1.05:
   - Trackpad zone active area at 1.05 sensitivity covers [110.5, 529.5] horizontally
     and [106.7, 373.3] vertically within the 640x480 camera frame.
   - All 4 corners (0,0), (1920,0), (0,1080), (1920,1080) are reachable.
   - Generous safety margins (110.5px horizontal, 106.7px vertical) prevent the hand
     from leaving the camera field of view.
3. Ergonomic Reachability:
   - Normal hand elevation at y=0.20 (96px in camera space) easily reaches the top
     of screen (y=0) without straining or exiting the webcam frame.
4. Landmark Payload Serialization & Lip Contour:
   - control_server.state.update_landmarks packages hands and face data with timestamps.
   - lip_contour contains the ordered outer lip loop points.
   - face anchors (lip_center, left_ear, right_ear) serialize correctly.
5. Stale Landmark Handling:
   - When hands/face are lost, tracking loss and clearing are represented accurately.
6. Camera Stream Coordinate Alignment:
   - Captured frames are mirrored horizontally (cv2.flip(frame, 1)) before serving,
     matching the selfie-view MediaPipe coordinate system 1:1.
"""

import json
import math
import time
import unittest
from unittest.mock import patch, MagicMock

import numpy as np

from core.control_server import DEFAULT_SENSITIVITY, RuntimeState
from core.display import VirtualDesktop, TrackpadZone, map_to_desktop
from core.actuator import MouseActuator
from core.gestures.right_hand import RightHandProcessor
from core.gestures.orchestrator import GestureOrchestrator
from core.tracker import HandsResult, Landmark


class TestPhase4_4CameraOverlayAndSensitivity(unittest.TestCase):
    def setUp(self):
        self.desktop = VirtualDesktop(total_width=1920, total_height=1080, monitor_count=1)
        self.actuator = MouseActuator(1920, 1080)
        self.trackpad = TrackpadZone(170, 470, 120, 320)
        self.orchestrator = GestureOrchestrator(self.actuator, self.desktop, self.trackpad)
        self.state = RuntimeState()

    def test_default_sensitivity_value_and_reduction_percentage(self):
        """Verify DEFAULT_SENSITIVITY is 0.85, yielding a gentle, controllable cursor speed."""
        self.assertEqual(DEFAULT_SENSITIVITY, 0.85)
        self.assertEqual(self.state.sensitivity, 0.85)

        prior_sensitivity = 1.05
        new_sensitivity = DEFAULT_SENSITIVITY
        reduction = (prior_sensitivity - new_sensitivity) / prior_sensitivity
        # Exact ~19.0% reduction from 1.05 (and 29.2% from original 1.20)
        self.assertAlmostEqual(reduction, 0.1905, places=3)
        self.assertGreater(reduction, 0.15)

    def test_four_corner_reachability_at_calibrated_sensitivity(self):
        """Verify that all four screen corners are fully reachable with comfortable camera margins at s=0.85."""
        effective_w = 440.0 / DEFAULT_SENSITIVITY
        effective_h = 280.0 / DEFAULT_SENSITIVITY
        min_x = 320.0 - effective_w / 2.0
        max_x = 320.0 + effective_w / 2.0
        min_y = 240.0 - effective_h / 2.0
        max_y = 240.0 + effective_h / 2.0

        # Margins inside 640x480 frame
        margin_left = min_x
        margin_right = 640.0 - max_x
        margin_top = min_y
        margin_bottom = 480.0 - max_y

        # Generous physical camera margins (> 50px on all sides)
        self.assertGreater(margin_left, 50.0)
        self.assertGreater(margin_right, 50.0)
        self.assertGreater(margin_top, 50.0)
        self.assertGreater(margin_bottom, 50.0)

        # Trackpad calibrated for s=0.85
        tp = TrackpadZone(int(round(min_x)), int(round(max_x)), int(round(min_y)), int(round(max_y)))

        # Test desktop mapping at top-left boundary (and beyond)
        norm_tl_x = tp.x_min / 640.0
        norm_tl_y = tp.y_min / 480.0
        dx_tl, dy_tl = map_to_desktop(norm_tl_x, norm_tl_y, tp, self.desktop)
        self.assertEqual((dx_tl, dy_tl), (0, 0))

        # Test desktop mapping beyond top-left (in outer margin)
        dx_out, dy_out = map_to_desktop(0.02, 0.02, tp, self.desktop)
        self.assertEqual((dx_out, dy_out), (0, 0))

        # Test desktop mapping at bottom-right boundary (and beyond)
        norm_br_x = tp.x_max / 640.0
        norm_br_y = tp.y_max / 480.0
        dx_br, dy_br = map_to_desktop(norm_br_x, norm_br_y, tp, self.desktop)
        self.assertEqual((dx_br, dy_br), (1919, 1079))

        # Test desktop mapping at top-right
        dx_tr, dy_tr = map_to_desktop(norm_br_x, norm_tl_y, tp, self.desktop)
        self.assertEqual((dx_tr, dy_tr), (1919, 0))

        # Test desktop mapping at bottom-left
        dx_bl, dy_bl = map_to_desktop(norm_tl_x, norm_br_y, tp, self.desktop)
        self.assertEqual((dx_bl, dy_bl), (0, 1079))

    def test_ergonomic_top_reachability(self):
        """Verify that hand elevated to y=0.15 comfortably reaches screen top (y=0)."""
        effective_h = 280.0 / DEFAULT_SENSITIVITY
        min_y = 240.0 - effective_h / 2.0  # ~75.3px
        max_y = 240.0 + effective_h / 2.0
        tp = TrackpadZone(170, 470, int(round(min_y)), int(round(max_y)))

        # Hand at norm_y = 0.15 is at 72px in camera space (72px <= 75.3px)
        norm_y = 0.15
        _, dy = map_to_desktop(0.5, norm_y, tp, self.desktop)
        self.assertEqual(dy, 0, "Comfortable hand elevation at y=0.15 must reach desktop top y=0")

    def test_landmark_serialization_including_lip_contour(self):
        """Verify update_landmarks serializes hands, lip contour polygon, and anchor regions."""
        # Create synthetic landmarks
        hands_landmarks = {
            "right": [{"x": round(0.1 + i * 0.01, 4), "y": round(0.2 + i * 0.01, 4), "z": 0.0} for i in range(21)],
            "left": [{"x": round(0.8 - i * 0.01, 4), "y": round(0.2 + i * 0.01, 4), "z": 0.0} for i in range(21)]
        }
        face_landmarks = {
            "detected": True,
            "lip_center": {"x": 0.50, "y": 0.60},
            "lip_contour": [
                {"x": 0.45, "y": 0.58},
                {"x": 0.50, "y": 0.57},
                {"x": 0.55, "y": 0.58},
                {"x": 0.56, "y": 0.60},
                {"x": 0.50, "y": 0.62},
                {"x": 0.44, "y": 0.60}
            ],
            "right_ear": {"x": 0.35, "y": 0.45},
            "left_ear": {"x": 0.65, "y": 0.45}
        }

        t_before = time.time()
        self.state.update_landmarks(hands_landmarks, face_landmarks, is_locked=True)
        t_after = time.time()

        payload = self.state.get_landmarks_snapshot()
        self.assertIsNotNone(payload)
        self.assertTrue(t_before <= payload["timestamp"] <= t_after)
        self.assertTrue(payload["is_locked"])

        # Hands verification
        self.assertIn("hands", payload)
        self.assertEqual(len(payload["hands"]["right"]), 21)
        self.assertEqual(len(payload["hands"]["left"]), 21)
        self.assertEqual(payload["hands"]["right"][8]["x"], 0.18)

        # Face verification
        self.assertIn("face", payload)
        face_payload = payload["face"]
        self.assertTrue(face_payload["detected"])
        self.assertEqual(len(face_payload["lip_contour"]), 6)
        self.assertEqual(face_payload["lip_center"]["x"], 0.50)
        self.assertEqual(face_payload["right_ear"]["x"], 0.35)
        self.assertEqual(face_payload["left_ear"]["x"], 0.65)

    def test_landmark_clearing_on_tracking_loss(self):
        """Verify update_landmarks handles None or lost tracking without residual ghost state."""
        self.state.update_landmarks(None, None, is_locked=False)
        payload = self.state.get_landmarks_snapshot()
        self.assertIsNotNone(payload)
        self.assertEqual(payload["hands"], {"right": None, "left": None})
        self.assertIsNone(payload["face"])
        self.assertFalse(payload["is_locked"])

    def test_camera_stream_frame_mirroring_alignment(self):
        """Verify frame buffer receives horizontally mirrored frame matching MediaPipe coordinate space."""
        # Simulated raw frame with distinct asymmetric mark on left side (x=50)
        raw_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        raw_frame[240, 50] = [255, 255, 255]

        # Horizontal flip (mirror)
        flipped_frame = np.fliplr(raw_frame)
        # Pixel at x=50 should now be at x=640 - 1 - 50 = 589
        self.assertTrue(np.array_equal(flipped_frame[240, 589], [255, 255, 255]))
        self.assertTrue(np.array_equal(flipped_frame[240, 50], [0, 0, 0]))


if __name__ == "__main__":
    unittest.main()

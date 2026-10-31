# test_phase4_1_control_server.py
"""
Unit tests for Air Point Phase 4.1 Control Server extensions:
- Real-time landmarks endpoint (/api/landmarks)
- Camera snapshot endpoint (/api/camera/frame)
- Camera streaming endpoint (/api/camera/stream)
- Sensitivity and smoothing runtime configuration
"""

import json
import time
import unittest
import urllib.error
import urllib.request
import numpy as np

from core.control_server import ControlServer, RuntimeState
from core.gestures.orchestrator import GestureOrchestrator
from core.actuator import MouseActuator
from core.display import VirtualDesktop, TrackpadZone


class TestPhase41ControlServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ControlServer(host="127.0.0.1", port=0)
        cls.server.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def test_landmarks_endpoint(self):
        """Verify /api/landmarks returns updated landmark payload."""
        hands_mock = {
            "right": [{"x": 0.5, "y": 0.5, "z": 0.0}],
            "left": None,
        }
        face_mock = {
            "detected": True,
            "lip_center": [0.5, 0.45, 0.0],
            "right_ear": [0.35, 0.4, 0.0],
            "left_ear": [0.65, 0.4, 0.0],
            "mouth_width": 0.08,
        }

        self.server.state.update_telemetry(
            running=True,
            tracking="Right Hand",
            fps=30.0,
            owner="RIGHT",
            volume=60,
            muted=False,
            active_gesture="pointer",
        )
        self.server.state.update_landmarks(
            hands_data=hands_mock,
            face_data=face_mock,
            is_locked=True,
        )

        req = urllib.request.Request(f"{self.base_url}/api/landmarks")
        req.add_header("Host", f"127.0.0.1:{self.server.port}")
        req.add_header("Origin", "http://localhost:8080")

        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Content-Type"), "application/json; charset=utf-8")
            data = json.loads(resp.read().decode("utf-8"))

        self.assertIn("timestamp", data)
        self.assertEqual(data["tracking"], "Right Hand")
        self.assertEqual(data["owner"], "RIGHT")
        self.assertEqual(data["active_gesture"], "pointer")
        self.assertTrue(data["is_locked"])
        self.assertEqual(data["hands"]["right"][0]["x"], 0.5)
        self.assertTrue(data["face"]["detected"])
        self.assertEqual(data["face"]["lip_center"], [0.5, 0.45, 0.0])

    def test_camera_frame_and_stream(self):
        """Verify camera snapshot /api/camera/frame and MJPEG stream /api/camera/stream."""
        # 1. No frame available -> 503
        self.server.state.set_frame_provider(lambda: None)
        req_frame = urllib.request.Request(f"{self.base_url}/api/camera/frame")
        req_frame.add_header("Host", f"127.0.0.1:{self.server.port}")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req_frame, timeout=2.0)
        self.assertEqual(ctx.exception.code, 503)

        # 2. Frame provided -> 200 image/jpeg
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        self.server.state.set_frame_provider(lambda: dummy_frame)

        with urllib.request.urlopen(req_frame, timeout=2.0) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Content-Type"), "image/jpeg")
            body = resp.read()
            self.assertGreater(len(body), 100)
            # JPEG magic header 0xFF, 0xD8
            self.assertEqual(body[:2], b"\xff\xd8")

        # 3. Stream endpoint connects and yields multipart chunks
        req_stream = urllib.request.Request(f"{self.base_url}/api/camera/stream")
        req_stream.add_header("Host", f"127.0.0.1:{self.server.port}")
        with urllib.request.urlopen(req_stream, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("multipart/x-mixed-replace", resp.headers.get("Content-Type", ""))
            chunk = resp.read(1024)
            self.assertIn(b"--frame", chunk)
            self.assertIn(b"Content-Type: image/jpeg", chunk)

    def test_sensitivity_and_smoothing_engine_integration(self):
        """Verify sensitivity and smoothing sliders alter orchestrator trackpad and filter."""
        actuator = MouseActuator(1920, 1080)
        desktop = VirtualDesktop(1920, 1080, 1)
        trackpad = TrackpadZone(100, 540, 100, 380)
        orchestrator = GestureOrchestrator(actuator, desktop, trackpad)

        # Base trackpad width: 540 - 100 = 440
        self.assertEqual(orchestrator._right._trackpad.x_max - orchestrator._right._trackpad.x_min, 440)

        # Sensitivity 2.0 -> trackpad span halved to 220
        orchestrator.set_sensitivity(2.0)
        span_x = orchestrator._right._trackpad.x_max - orchestrator._right._trackpad.x_min
        self.assertEqual(span_x, 220)

        # Smoothing 90 -> mincutoff lower (heavy smoothing)
        orchestrator.set_smoothing(90)
        cutoff_high = orchestrator._right._filter_x._mincutoff
        orchestrator.set_smoothing(20)
        cutoff_low = orchestrator._right._filter_x._mincutoff
        self.assertLess(cutoff_high, cutoff_low)


if __name__ == "__main__":
    unittest.main()

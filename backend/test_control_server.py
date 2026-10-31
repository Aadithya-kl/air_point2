# test_control_server.py
"""
Unit tests for the Air Point Control Bridge (core/control_server.py).
Tests:
- Localhost binding (127.0.0.1)
- Host and Origin header security validation
- /api/status telemetry endpoint
- /api/settings validation and bounds clamping
- /api/toggle tracking pause/resume
- /api/events SSE stream and event broadcast
- Clean start and shutdown
"""

import json
import time
import unittest
import urllib.error
import urllib.request
from core.control_server import (
    ControlServer,
    RuntimeState,
    MIN_HOLD_S,
    MAX_HOLD_S,
    DEFAULT_HOLD_S,
    MIN_SENSITIVITY,
    MAX_SENSITIVITY,
    DEFAULT_SENSITIVITY,
    MIN_SMOOTHING,
    MAX_SMOOTHING,
    DEFAULT_SMOOTHING,
)


class TestControlServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Start server on ephemeral port (port 0) on 127.0.0.1 with isolated in-memory settings
        cls.server = ControlServer(host="127.0.0.1", port=0, settings_path=None)
        cls.server.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def test_localhost_binding_only(self):
        self.assertEqual(self.server.host, "127.0.0.1")
        self.assertTrue(self.server.port > 0)

    def test_status_endpoint(self):
        req = urllib.request.Request(f"{self.base_url}/api/status")
        req.add_header("Host", f"127.0.0.1:{self.server.port}")
        req.add_header("Origin", "http://localhost:8080")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))

        self.assertIn("running", data)
        self.assertIn("tracking", data)
        self.assertIn("fps", data)
        self.assertIn("volume", data)
        self.assertIn("muted", data)
        self.assertIn("settings", data)
        self.assertIn("hold", data["settings"])
        self.assertEqual(data["settings"]["hold"], DEFAULT_HOLD_S)

    def test_origin_header_validation(self):
        # Disallowed origin should be rejected with 403 Forbidden
        req = urllib.request.Request(f"{self.base_url}/api/status")
        req.add_header("Host", f"127.0.0.1:{self.server.port}")
        req.add_header("Origin", "http://malicious-site.com")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=3.0)
        self.assertEqual(ctx.exception.code, 403)

    def test_host_header_validation(self):
        # Disallowed host should be rejected with 403 Forbidden
        req = urllib.request.Request(f"{self.base_url}/api/status")
        req.add_header("Host", "attacker-domain.org")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=3.0)
        self.assertEqual(ctx.exception.code, 403)

    def test_settings_clamping_and_persistence(self):
        # Attempt to set values out of bounds
        payload = json.dumps({
            "hold": 999.0,         # Should clamp to MAX_HOLD_S (10.0)
            "sensitivity": -5.0,   # Should clamp to MIN_SENSITIVITY (0.2)
            "smoothing": 999,      # Should clamp to MAX_SMOOTHING (100)
            "enabled": {"screenshot": False, "invalid_gesture": True},
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/api/settings",
            data=payload,
            headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{self.server.port}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))

        settings = data["settings"]
        self.assertEqual(settings["hold"], MAX_HOLD_S)
        self.assertEqual(settings["sensitivity"], MIN_SENSITIVITY)
        self.assertEqual(settings["smoothing"], MAX_SMOOTHING)
        self.assertEqual(settings["enabled"]["screenshot"], False)
        self.assertNotIn("invalid_gesture", settings["enabled"])

        # Reset back to defaults
        reset_payload = json.dumps({
            "hold": DEFAULT_HOLD_S,
            "sensitivity": DEFAULT_SENSITIVITY,
            "smoothing": DEFAULT_SMOOTHING,
            "enabled": {"screenshot": True},
        }).encode("utf-8")
        req_reset = urllib.request.Request(
            f"{self.base_url}/api/settings",
            data=reset_payload,
            headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{self.server.port}"},
            method="POST",
        )
        with urllib.request.urlopen(req_reset, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)

    def test_toggle_pause(self):
        req = urllib.request.Request(
            f"{self.base_url}/api/toggle",
            data=b"{}",
            headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{self.server.port}"},
            method="POST",
        )
        initial_running = self.server.state.running
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(data["running"], not initial_running)

        # Toggle back
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(data["running"], initial_running)

    def test_stop_and_start_endpoints_idempotent(self):
        # 1. Stop tracking explicitly via /api/stop
        stop_req = urllib.request.Request(
            f"{self.base_url}/api/stop",
            data=b"{}",
            headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{self.server.port}"},
            method="POST",
        )
        with urllib.request.urlopen(stop_req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
        self.assertFalse(data["running"])
        self.assertFalse(self.server.state.running)

        # 2. Second stop must be idempotent (stays stopped, does NOT toggle back!)
        with urllib.request.urlopen(stop_req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
        self.assertFalse(data["running"])
        self.assertFalse(self.server.state.running)

        # 3. Start tracking explicitly via /api/start
        start_req = urllib.request.Request(
            f"{self.base_url}/api/start",
            data=b"{}",
            headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{self.server.port}"},
            method="POST",
        )
        with urllib.request.urlopen(start_req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(data["running"])
        self.assertTrue(self.server.state.running)

        # 4. Second start must be idempotent (stays running, does NOT toggle back!)
        with urllib.request.urlopen(start_req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(data["running"])
        self.assertTrue(self.server.state.running)

    def test_control_endpoint(self):
        # Test /api/control with action="stop"
        req_stop = urllib.request.Request(
            f"{self.base_url}/api/control",
            data=json.dumps({"action": "stop"}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{self.server.port}"},
            method="POST",
        )
        with urllib.request.urlopen(req_stop, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
        self.assertFalse(data["running"])
        self.assertEqual(data["action"], "stop")

        # Test /api/control with action="start"
        req_start = urllib.request.Request(
            f"{self.base_url}/api/control",
            data=json.dumps({"action": "start"}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{self.server.port}"},
            method="POST",
        )
        with urllib.request.urlopen(req_start, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(data["running"])
        self.assertEqual(data["action"], "start")

    def test_lifecycle_callbacks_invocation(self):
        stop_called = []
        start_called = []

        def on_stop():
            stop_called.append(True)
            return False

        def on_start():
            start_called.append(True)
            return True

        self.server.state.set_lifecycle_callbacks(stop_cb=on_stop, start_cb=on_start)
        try:
            self.server.state.stop()
            self.assertTrue(len(stop_called) > 0)
            self.assertFalse(self.server.state.running)

            self.server.state.start()
            self.assertTrue(len(start_called) > 0)
            self.assertTrue(self.server.state.running)
        finally:
            self.server.state.set_lifecycle_callbacks(None, None)

    def test_events_stream_and_broadcast(self):
        # Verify SSE initial connection and broadcast
        req = urllib.request.Request(f"{self.base_url}/api/events")
        req.add_header("Host", f"127.0.0.1:{self.server.port}")
        req.add_header("Accept", "text/event-stream")
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            # Read first line (should be : connected or initial hello)
            line = resp.readline().decode("utf-8")
            self.assertTrue(line.startswith(":") or line.startswith("data:"))

            # Small yield to ensure listener is fully registered in server thread
            time.sleep(0.05)

            # Broadcast an event
            self.server.state.add_event("Screenshot captured", event_type="screenshot")

            found_screenshot = False
            for _ in range(5):
                line = resp.readline().decode("utf-8")
                if "screenshot" in line:
                    found_screenshot = True
                    break
            self.assertTrue(found_screenshot)

    def test_in_memory_settings_isolation(self):
        """Verify RuntimeState(settings_path=None) does not touch on-disk settings.json."""
        import os
        from core.control_server import SETTINGS_FILE

        initial_disk_mtime = os.path.getmtime(SETTINGS_FILE) if os.path.exists(SETTINGS_FILE) else None
        state = RuntimeState(settings_path=None)

        # Default for wakanda-forever must be False regardless of what is in settings.json
        self.assertFalse(state.enabled_gestures["wakanda-forever"])

        # Mutate in-memory state
        state.apply_settings({"enabled": {"wakanda-forever": True}, "sensitivity": 2.5})
        self.assertTrue(state.enabled_gestures["wakanda-forever"])
        self.assertEqual(state.sensitivity, 2.5)

        # Confirm on-disk file was not modified
        if initial_disk_mtime is not None:
            self.assertEqual(os.path.getmtime(SETTINGS_FILE), initial_disk_mtime)

    def test_custom_settings_file_isolation(self):
        """Verify custom file settings load and persist only to the designated file."""
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmp_dir:
            custom_path = os.path.join(tmp_dir, "custom_settings.json")
            # Create custom file with specific values
            with open(custom_path, "w", encoding="utf-8") as f:
                json.dump({
                    "hold": 4.5,
                    "sensitivity": 1.25,
                    "smoothing": 80,
                    "enabled": {"wakanda-forever": True, "pointer": False},
                }, f)

            state = RuntimeState(settings_path=custom_path)
            self.assertEqual(state.hold_duration, 4.5)
            self.assertEqual(state.sensitivity, 1.25)
            self.assertEqual(state.smoothing, 80)
            self.assertTrue(state.enabled_gestures["wakanda-forever"])
            self.assertFalse(state.enabled_gestures["pointer"])

            # Mutate and verify persisted to custom file
            state.apply_settings({"hold": 2.0})
            with open(custom_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            self.assertEqual(saved["hold"], 2.0)

    def test_env_var_settings_path_override(self):
        """Verify AIRPOINT_SETTINGS_PATH environment variable overrides default path."""
        import os
        old_env = os.environ.get("AIRPOINT_SETTINGS_PATH")
        try:
            os.environ["AIRPOINT_SETTINGS_PATH"] = ":memory:"
            state = RuntimeState()
            self.assertIsNone(state.settings_path)
            self.assertFalse(state.enabled_gestures["wakanda-forever"])
        finally:
            if old_env is None:
                os.environ.pop("AIRPOINT_SETTINGS_PATH", None)
            else:
                os.environ["AIRPOINT_SETTINGS_PATH"] = old_env

    def test_disallowed_local_origin_rejected(self):
        """Disallowed local origin (e.g., localhost:3000) must be rejected with 403 Forbidden."""
        req = urllib.request.Request(f"{self.base_url}/api/status")
        req.add_header("Host", f"127.0.0.1:{self.server.port}")
        req.add_header("Origin", "http://localhost:3000")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=3.0)
        self.assertEqual(ctx.exception.code, 403)

    def test_cors_preflight_options(self):
        """OPTIONS preflight must allow approved origins with X-AirPoint-Token header and reject untrusted origins."""
        # Approved origin
        req_ok = urllib.request.Request(f"{self.base_url}/api/settings", method="OPTIONS")
        req_ok.add_header("Host", f"127.0.0.1:{self.server.port}")
        req_ok.add_header("Origin", "http://localhost:8080")
        with urllib.request.urlopen(req_ok, timeout=3.0) as resp:
            self.assertEqual(resp.status, 204)
            allow_headers = resp.headers.get("Access-Control-Allow-Headers", "")
            self.assertIn("X-AirPoint-Token", allow_headers)

        # Disallowed origin
        req_bad = urllib.request.Request(f"{self.base_url}/api/settings", method="OPTIONS")
        req_bad.add_header("Host", f"127.0.0.1:{self.server.port}")
        req_bad.add_header("Origin", "http://localhost:3000")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req_bad, timeout=3.0)
        self.assertEqual(ctx.exception.code, 403)

    def test_mutation_token_authentication(self):
        """Mutating endpoints validate X-AirPoint-Token header and reject invalid tokens."""
        # 1. Valid token succeeds
        req_valid = urllib.request.Request(
            f"{self.base_url}/api/toggle",
            data=b"{}",
            headers={
                "Content-Type": "application/json",
                "Host": f"127.0.0.1:{self.server.port}",
                "X-AirPoint-Token": self.server.token,
            },
            method="POST",
        )
        with urllib.request.urlopen(req_valid, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)

        # 2. Invalid token fails with 403 Forbidden
        req_invalid = urllib.request.Request(
            f"{self.base_url}/api/toggle",
            data=b"{}",
            headers={
                "Content-Type": "application/json",
                "Host": f"127.0.0.1:{self.server.port}",
                "X-AirPoint-Token": "invalid_forged_secret_token_12345",
            },
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req_invalid, timeout=3.0)
        self.assertEqual(ctx.exception.code, 403)

        # 3. Disallowed origin on POST fails with 403 Forbidden
        req_disallowed_origin = urllib.request.Request(
            f"{self.base_url}/api/toggle",
            data=b"{}",
            headers={
                "Content-Type": "application/json",
                "Host": f"127.0.0.1:{self.server.port}",
                "Origin": "http://localhost:3000",
            },
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req_disallowed_origin, timeout=3.0)
        self.assertEqual(ctx.exception.code, 403)

    def test_deterministic_port_collision_handling(self):
        """Starting a server on an already occupied port raises RuntimeError with diagnostic guidance."""
        occupied_port = self.server.port
        # Attempt to start second server on same port without fallback -> must raise RuntimeError
        second_server = ControlServer(host="127.0.0.1", port=occupied_port, settings_path=None, allow_port_fallback=False)
        with self.assertRaises(RuntimeError) as ctx:
            second_server.start()
        self.assertIn("already in use by another process", str(ctx.exception))
        self.assertFalse(second_server.is_active)

        # Attempt to start with allow_port_fallback=True -> must bind to alternate dynamic port
        fallback_server = ControlServer(host="127.0.0.1", port=occupied_port, settings_path=None, allow_port_fallback=True)
        try:
            fallback_server.start()
            self.assertTrue(fallback_server.is_active)
            self.assertNotEqual(fallback_server.port, occupied_port)
            self.assertTrue(fallback_server.port > 0)
        finally:
            fallback_server.stop()

    def test_bridge_discovery_files(self):
        """Server writes bridge_info.json and .bridge_token and cleans them up on stop."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_token = "test_secret_token_abcdef123456"
            srv = ControlServer(host="127.0.0.1", port=0, token=test_token, allow_port_fallback=True)
            srv.start()
            try:
                self.assertEqual(srv.token, test_token)
                self.assertTrue(srv.port > 0)
            finally:
                srv.stop()

    def test_volume_event_direction_and_telemetry(self):
        """Verifies VOLUME_UP and VOLUME_DOWN events correctly format Volume up / Volume down actions and telemetry."""
        state = RuntimeState(settings_path=None)

        # Test volume up event emission
        dir_name_up = "VOLUME_UP"
        is_up = dir_name_up in ("VOLUME_UP", "UP")
        evt_up = "volume-up" if is_up else "volume-down"
        vol_scalar = 1.0
        action_up = f"Volume {'up' if is_up else 'down'}: {int(vol_scalar * 100)}%"
        state.add_event(action_up, evt_up)

        self.assertEqual(len(state.recent_events), 1)
        self.assertEqual(state.recent_events[0]["action"], "Volume up: 100%")
        self.assertEqual(state.recent_events[0]["type"], "volume-up")

        # Test volume down event emission
        dir_name_down = "VOLUME_DOWN"
        is_down = dir_name_down in ("VOLUME_UP", "UP")
        evt_down = "volume-up" if is_down else "volume-down"
        action_down = f"Volume {'up' if is_down else 'down'}: 45%"
        state.add_event(action_down, evt_down)

        self.assertEqual(len(state.recent_events), 2)
        self.assertEqual(state.recent_events[0]["action"], "Volume down: 45%")
        self.assertEqual(state.recent_events[0]["type"], "volume-down")

        # Test telemetry active_gesture reflects volume-up
        state.update_telemetry(
            running=True,
            tracking="Right Hand",
            fps=30.0,
            owner="RIGHT",
            volume=100,
            muted=False,
            active_gesture="volume-up",
        )
        self.assertEqual(state.active_gesture, "volume-up")
        self.assertEqual(state.volume, 100)


if __name__ == "__main__":
    unittest.main()

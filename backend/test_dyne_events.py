# test_dyne_events.py
"""
Unified Dyne event system (migration Stage E) regression tests.

Covers, without camera, native input or a real Tk window:
  1. EventDispatcher: schema, catalogue defaults, monotonic ids, bounded history,
     fan-out, subscriber isolation, thread safety.
  2. DragEventTracker: controller transitions -> drag.started / completed /
     released / failed, nothing for pending or cancelled pinches.
  3. VolumeEventCoalescer: the 50 ms ear-volume tick becomes <= 4 events/s plus
     one final event (F-13).
  4. Dyne position / appearance sanitisers and the accent colour resolver.
  5. RuntimeState: publish_event / legacy add_event, status snapshot fields,
     persisted island_position and island_appearance, graceful exit callback.
  6. HTTP bridge: /api/events/history, SSE `id:` lines and Last-Event-ID replay
     without duplicates, /api/control {"action": "exit"}.
  7. Tk overlay (tkinter.Tk patched): position geometry, F-15 gating of toasts
     by island_enabled / notifications_enabled, handle_event mapping, and the
     dispatcher -> overlay subscription.
  8. Screenshot truth (F-12): the capture result callback reports the actuator's
     real result; no "captured" result is produced for a failed save.

Mocked tests prove the wiring, not the webcam gestures: a mocked tracking.lost
event is not evidence that the engine detects a lost hand.
"""

import json
import os
import tempfile
import threading
import time
import unittest
import urllib.request
from unittest.mock import MagicMock, patch

from core.events import (
    DEFAULT_ISLAND_APPEARANCE,
    DEFAULT_ISLAND_POSITION,
    DYNE_COLOURS,
    EVENT_CATALOGUE,
    DragEventTracker,
    DyneEvent,
    EventDispatcher,
    VolumeEventCoalescer,
    island_accent_hex,
    sanitize_island_appearance,
    sanitize_island_position,
)
from core.control_server import ControlServer, RuntimeState, STATUS_EVENT_COUNT, EVENT_HISTORY_LIMIT


# ── 1. EventDispatcher ───────────────────────────────────────────────────────────

class TestEventDispatcher(unittest.TestCase):
    def test_schema_and_catalogue_defaults(self):
        d = EventDispatcher(history_limit=10, session_id="abcd1234", clock=lambda: 1_700_000_000.0)
        ev = d.publish("screenshot.captured", "Saved x.png", source="gesture:screenshot", metadata={"path": "x.png"})
        self.assertIsInstance(ev, DyneEvent)
        spec = EVENT_CATALOGUE["screenshot.captured"]
        self.assertEqual(ev.id, 1)
        self.assertEqual(ev.session, "abcd1234")
        self.assertEqual(ev.title, spec.title)
        self.assertEqual(ev.priority, spec.priority)
        self.assertEqual(ev.duration_s, spec.duration_s)
        self.assertEqual(ev.kind, spec.kind)
        self.assertEqual(ev.message, "Saved x.png")
        data = ev.to_dict()
        for key in ("id", "session", "type", "timestamp", "time", "source", "title", "message",
                    "priority", "duration_s", "metadata", "event", "action"):
            self.assertIn(key, data)
        self.assertEqual(data["type"], "screenshot.captured")
        self.assertEqual(data["metadata"], {"path": "x.png"})
        self.assertEqual(data["action"], "Saved x.png")   # legacy alias of message
        self.assertEqual(data["event"], "screenshot")      # legacy kind
        self.assertEqual(data["timestamp"], 1_700_000_000.0)

    def test_unknown_type_uses_message_as_title_and_clamps(self):
        d = EventDispatcher()
        ev = d.publish("custom.thing", "Something happened", priority="bogus", duration_s=999)
        self.assertEqual(ev.title, "Something happened")
        self.assertEqual(ev.priority, "normal")
        self.assertEqual(ev.duration_s, 30.0)
        self.assertEqual(ev.kind, "custom.thing")
        ev2 = d.publish("custom.thing", duration_s=0.01)
        self.assertEqual(ev2.title, "custom.thing")
        self.assertEqual(ev2.duration_s, 0.5)

    def test_ids_monotonic_history_bounded_and_after_filter(self):
        d = EventDispatcher(history_limit=5)
        for _ in range(8):
            d.publish("tracking.lost")
        self.assertEqual(d.last_id, 8)
        hist = d.history()
        self.assertEqual([e.id for e in hist], [4, 5, 6, 7, 8])
        self.assertEqual([e.id for e in d.history(after_id=6)], [7, 8])
        self.assertEqual([e.id for e in d.history(limit=2)], [7, 8])
        self.assertEqual(d.history(after_id=8), [])

    def test_fanout_and_subscriber_isolation(self):
        d = EventDispatcher()
        seen = []

        def bad(_ev):
            raise RuntimeError("boom")

        d.subscribe(bad)
        d.subscribe(seen.append)
        ev = d.publish("engine.started")
        self.assertEqual(seen, [ev])
        d.unsubscribe(seen.append)
        d.publish("engine.started")
        self.assertEqual(len(seen), 1)
        self.assertEqual(d.subscriber_count, 1)

    def test_thread_safety_unique_ids(self):
        d = EventDispatcher(history_limit=1000)
        ids = []
        lock = threading.Lock()

        def worker():
            for _ in range(200):
                ev = d.publish("tracking.lost")
                with lock:
                    ids.append(ev.id)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(ids), 800)
        self.assertEqual(len(set(ids)), 800)
        self.assertEqual(d.last_id, 800)


# ── 2. DragEventTracker ─────────────────────────────────────────────────────────

class TestDragEventTracker(unittest.TestCase):
    def test_full_cycle_unpinch(self):
        t = DragEventTracker()
        self.assertEqual(t.observe("READY"), [])
        self.assertEqual(t.observe("GRAB_PENDING"), [])
        started = t.observe("GRAB_LOCKED")
        self.assertEqual([e[0] for e in started], ["drag.started"])
        self.assertEqual(t.observe("RELEASE_PENDING"), [])
        self.assertEqual(t.observe("GRAB_LOCKED"), [])   # jitter recovery, no event
        self.assertEqual(t.observe("RELEASE_PENDING"), [])
        done = t.observe("READY", release_reason="UNPINCH")
        self.assertEqual(done[0][0], "drag.completed")
        self.assertEqual(done[0][2]["reason"], "UNPINCH")

    def test_tracking_loss_and_pause_are_released_not_completed(self):
        t = DragEventTracker()
        t.observe("GRAB_LOCKED")
        ev = t.observe("READY", release_reason="TRACKING_LOSS")
        self.assertEqual(ev[0][0], "drag.released")
        self.assertIn("hand lost", ev[0][1].lower())
        t.observe("GRAB_LOCKED")
        ev = t.observe("READY", release_reason="PAUSE")
        self.assertEqual(ev[0][0], "drag.released")
        self.assertIn("paused", ev[0][1].lower())

    def test_native_failures_are_failed_events(self):
        t = DragEventTracker()
        t.observe("GRAB_LOCKED")
        ev = t.observe("INPUT_ERROR", release_reason="INPUT_ERROR", last_error="NATIVE_BUTTON_UP_FAILED")
        self.assertEqual(ev[0][0], "drag.failed")
        self.assertIn("LEFTUP", ev[0][1])
        self.assertEqual(ev[0][2]["error"], "NATIVE_BUTTON_UP_FAILED")
        rec = t.observe("READY")
        self.assertEqual(rec[0][0], "drag.released")
        self.assertIn("recovered", rec[0][1].lower())
        # LEFTDOWN failure straight from GRAB_PENDING
        t2 = DragEventTracker()
        t2.observe("GRAB_PENDING")
        ev2 = t2.observe("INPUT_ERROR", last_error="NATIVE_BUTTON_DOWN_FAILED")
        self.assertEqual(ev2[0][0], "drag.failed")
        self.assertIn("LEFTDOWN", ev2[0][1])

    def test_cancelled_pinch_and_repeats_are_silent(self):
        t = DragEventTracker()
        t.observe("GRAB_PENDING")
        self.assertEqual(t.observe("READY", release_reason="PINCH_CANCELLED"), [])
        self.assertEqual(t.observe("READY", release_reason="PINCH_CANCELLED"), [])


# ── 3. VolumeEventCoalescer ─────────────────────────────────────────────────────

class TestVolumeEventCoalescer(unittest.TestCase):
    def test_rate_limit_and_final_event(self):
        c = VolumeEventCoalescer(min_interval_s=0.25)
        emitted = []
        now = 100.0
        for i in range(20):  # 1 s of 50 ms ticks
            meta = c.offer("VOLUME_UP", 0.5 + i * 0.01, True, now + i * 0.05)
            if meta:
                emitted.append(meta)
        self.assertLessEqual(len(emitted), 5)
        self.assertGreaterEqual(len(emitted), 4)
        self.assertTrue(all(m["direction"] == "up" and m["final"] is False for m in emitted))
        final = c.offer("VOLUME_UP", 0.7, False, now + 1.05)
        self.assertIsNotNone(final)
        self.assertTrue(final["final"])
        self.assertEqual(final["percent"], 70)
        # A second inactive call without a new gesture stays silent
        self.assertIsNone(c.offer("VOLUME_UP", 0.7, False, now + 1.1))

    def test_inactive_without_gesture_is_silent(self):
        c = VolumeEventCoalescer()
        self.assertIsNone(c.offer("VOLUME_DOWN", 0.2, False, 1.0))
        meta = c.offer("DOWN", 0.2, True, 2.0)
        self.assertEqual(meta["direction"], "down")


# ── 4. Position / appearance sanitisers ─────────────────────────────────────────

class TestDyneSettingsSanitisers(unittest.TestCase):
    def test_position(self):
        self.assertEqual(sanitize_island_position("bottom-center"), "bottom-center")
        self.assertEqual(sanitize_island_position("TOP-LEFT"), "top-left")
        self.assertEqual(sanitize_island_position("sideways"), DEFAULT_ISLAND_POSITION)
        self.assertEqual(sanitize_island_position(None), DEFAULT_ISLAND_POSITION)

    def test_appearance_validation(self):
        app = sanitize_island_appearance({
            "accent": "Red", "texture": "Velvet", "fontSize": 99, "weight": 100,
            "roundness": 10, "customRgb": {"r": 300, "g": -5, "b": "12"}, "extra": 1,
        })
        self.assertEqual(app["accent"], "Red")
        self.assertEqual(app["texture"], DEFAULT_ISLAND_APPEARANCE["texture"])
        self.assertEqual(app["fontSize"], 28)
        self.assertEqual(app["weight"], 300)
        self.assertEqual(app["roundness"], 28)
        self.assertEqual(app["customRgb"], {"r": 255, "g": 0, "b": 12})
        self.assertNotIn("extra", app)
        self.assertEqual(sanitize_island_appearance("junk"), sanitize_island_appearance(DEFAULT_ISLAND_APPEARANCE))

    def test_accent_hex(self):
        self.assertEqual(island_accent_hex({"accent": "Red"}), DYNE_COLOURS["Red"])
        self.assertEqual(island_accent_hex({"accent": "Custom", "customRgb": {"r": 1, "g": 2, "b": 255}}), "#0102ff")
        self.assertEqual(island_accent_hex(None), DYNE_COLOURS["Gold"])


# ── 5. RuntimeState ─────────────────────────────────────────────────────────────

class TestRuntimeStateEvents(unittest.TestCase):
    def test_publish_and_legacy_add_event(self):
        state = RuntimeState(settings_path=None)
        ev = state.publish_event("tracking.lost", "No hand", source="tracking")
        top = state.recent_events[0]
        self.assertEqual(top["id"], ev.id)
        self.assertEqual(top["event_type"], "tracking.lost")
        self.assertEqual(top["type"], "lost")          # legacy short kind
        self.assertEqual(top["title"], "Hand lost")
        self.assertEqual(top["action"], "No hand")
        # Legacy shim: free-form kind + action
        state.add_event("Volume up: 50%", "volume-up")
        self.assertEqual(state.recent_events[0]["type"], "volume-up")
        self.assertEqual(state.recent_events[0]["action"], "Volume up: 50%")
        self.assertEqual(state.recent_events[0]["title"], "Volume up: 50%")

    def test_snapshot_fields_and_status_ring_limit(self):
        state = RuntimeState(settings_path=None)
        for i in range(STATUS_EVENT_COUNT + 5):
            state.publish_event("tracking.lost", f"n{i}")
        snap = state.get_snapshot()
        self.assertEqual(len(snap["events"]), STATUS_EVENT_COUNT)
        self.assertEqual(snap["events"][0]["message"], f"n{STATUS_EVENT_COUNT + 4}")
        self.assertEqual(snap["event_session"], state.events.session_id)
        self.assertEqual(snap["last_event_id"], STATUS_EVENT_COUNT + 5)
        self.assertEqual(snap["settings"]["island_position"], DEFAULT_ISLAND_POSITION)
        self.assertEqual(snap["settings"]["island_appearance"]["accent"], DEFAULT_ISLAND_APPEARANCE["accent"])
        self.assertEqual(len(state.event_history()), min(STATUS_EVENT_COUNT + 5, EVENT_HISTORY_LIMIT))
        self.assertEqual([e["id"] for e in state.event_history(after_id=STATUS_EVENT_COUNT + 3)],
                         [STATUS_EVENT_COUNT + 4, STATUS_EVENT_COUNT + 5])

    def test_island_position_and_appearance_persist(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "settings.json")
            state = RuntimeState(settings_path=path)
            state.apply_settings({"island_position": "bottom-center", "island_appearance": {"accent": "Purple", "roundness": 30}})
            with open(path, encoding="utf-8") as f:
                saved = json.load(f)
            self.assertEqual(saved["island_position"], "bottom-center")
            self.assertEqual(saved["island_appearance"]["accent"], "Purple")
            self.assertEqual(saved["island_appearance"]["roundness"], 30)
            # Partial update keeps the previously persisted values (base merge)
            state.apply_settings({"island_appearance": {"texture": "Matte"}})
            self.assertEqual(state.island_appearance["accent"], "Purple")
            self.assertEqual(state.island_appearance["texture"], "Matte")
            reloaded = RuntimeState(settings_path=path)
            self.assertEqual(reloaded.island_position, "bottom-center")
            self.assertEqual(reloaded.island_appearance["accent"], "Purple")
            # Invalid values never persist
            state.apply_settings({"island_position": "nowhere"})
            self.assertEqual(state.island_position, "bottom-center")

    def test_exit_callback(self):
        state = RuntimeState(settings_path=None)
        self.assertFalse(state.request_exit())
        called = []
        state.set_exit_cb(lambda: called.append(True) or True)
        self.assertTrue(state.request_exit())
        self.assertEqual(called, [True])


# ── 6. HTTP bridge ──────────────────────────────────────────────────────────────

class TestBridgeEventEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ControlServer(host="127.0.0.1", port=0, settings_path=None)
        cls.server.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def _get_json(self, path):
        req = urllib.request.Request(f"{self.base_url}{path}")
        req.add_header("Host", f"127.0.0.1:{self.server.port}")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def test_history_endpoint_and_after_filter(self):
        state = self.server.state
        before = state.events.last_id
        a = state.publish_event("tracking.lost", "h1")
        b = state.publish_event("tracking.recovered", "h2")
        data = self._get_json("/api/events/history")
        ids = [e["id"] for e in data["events"]]
        self.assertEqual(ids, sorted(ids))
        self.assertIn(a.id, ids)
        self.assertIn(b.id, ids)
        self.assertEqual(data["session"], state.events.session_id)
        self.assertEqual(data["last_event_id"], b.id)
        newer = self._get_json(f"/api/events/history?after={a.id}")
        self.assertEqual([e["id"] for e in newer["events"]], [b.id])
        self.assertEqual(newer["events"][0]["event_type"], "tracking.recovered")
        self.assertGreaterEqual(a.id, before + 1)

    def test_sse_ids_and_last_event_id_replay_without_duplicates(self):
        state = self.server.state
        first = state.publish_event("engine.started", "s1")
        missed = state.publish_event("tracking.lost", "s2")
        req = urllib.request.Request(f"{self.base_url}/api/events")
        req.add_header("Host", f"127.0.0.1:{self.server.port}")
        req.add_header("Accept", "text/event-stream")
        req.add_header("Last-Event-ID", str(first.id))
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            lines = []
            # hello comment + hello data + blank, then replayed id/data/blank
            for _ in range(6):
                lines.append(resp.readline().decode("utf-8").rstrip("\n"))
            self.assertEqual(lines[0], ": connected")
            hello = json.loads(lines[1][len("data: "):])
            self.assertEqual(hello["session"], state.events.session_id)
            self.assertIn(f"id: {missed.id}", lines)
            replay_data = [ln for ln in lines if ln.startswith("data: ") and '"s2"' in ln]
            self.assertEqual(len(replay_data), 1)

            time.sleep(0.05)
            live = state.publish_event("tracking.recovered", "s3")
            got = []
            for _ in range(6):
                ln = resp.readline().decode("utf-8").rstrip("\n")
                got.append(ln)
                if ln == "" and any(x.startswith("data: ") for x in got):
                    break
            self.assertIn(f"id: {live.id}", got)
            payload = json.loads([ln for ln in got if ln.startswith("data: ")][0][len("data: "):])
            self.assertEqual(payload["id"], live.id)
            self.assertEqual(payload["event_type"], "tracking.recovered")
            self.assertEqual(payload["title"], "Hand reacquired")
            self.assertEqual(payload["priority"], "normal")
            all_ids = [ln for ln in lines + got if ln.startswith("id: ")]
            self.assertEqual(len(all_ids), len(set(all_ids)))

    def test_control_exit_action(self):
        token = self.server.token

        def post(payload):
            req = urllib.request.Request(
                f"{self.base_url}/api/control",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{self.server.port}", "X-AirPoint-Token": token},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                return json.loads(resp.read().decode("utf-8"))

        self.server.state.set_exit_cb(None)
        data = post({"action": "exit"})
        self.assertEqual(data["action"], "exit")
        self.assertFalse(data["accepted"])
        flag = []
        self.server.state.set_exit_cb(lambda: flag.append(1) or True)
        data = post({"action": "exit"})
        self.assertTrue(data["accepted"])
        self.assertEqual(flag, [1])
        self.server.state.set_exit_cb(None)


# ── 7. Tk overlay (patched) ─────────────────────────────────────────────────────

class TestOverlayDyneIntegration(unittest.TestCase):
    def setUp(self):
        self.tk_patcher = patch("tkinter.Tk")
        self.parent_patcher = patch("ctypes.windll.user32.GetParent")
        mock_tk = self.tk_patcher.start()
        self.parent_patcher.start()
        self.root = MagicMock()
        self.root.winfo_screenwidth.return_value = 1920
        self.root.winfo_screenheight.return_value = 1080
        mock_tk.return_value = self.root
        from core.overlay import ScreenshotOverlay
        self.overlay = ScreenshotOverlay("TOP_CENTER")

    def tearDown(self):
        self.tk_patcher.stop()
        self.parent_patcher.stop()

    def test_position_geometry(self):
        o = self.overlay
        self.assertEqual(o.position, "top-center")
        self.assertEqual(o.x, (1920 - o.w) // 2)
        o.configure(position="top-left")
        self.assertEqual(o.x, o.pad_side)
        o.configure(position="top-right")
        self.assertEqual(o.x, 1920 - o.w - o.pad_side)
        o.configure(position="bottom-center")
        self.assertEqual(o.y_visible, 1080 - o.h - o.pad_top)
        self.assertEqual(o.y_hidden, 1080 + 10)
        self.assertEqual(o.current_y, float(o.y_hidden))
        o.configure(position="nonsense")
        self.assertEqual(o.position, DEFAULT_ISLAND_POSITION)
        self.assertEqual(o.y_visible, o.pad_top)

    def test_appearance_accent(self):
        self.overlay.configure(appearance={"accent": "Red"})
        self.assertEqual(self.overlay.accent_color, DYNE_COLOURS["Red"])

    def test_notifications_switch_gates_toasts_but_not_hud_state(self):
        o = self.overlay
        o.configure(notifications_enabled=False)
        o.show_tracking_toast("LOST")
        o.show_app_toast("WhatsApp", True)
        o.show_pause_toast(True)
        o.show_wakanda_complete()
        o.show_wakanda_failed()
        o.show_success_toast()
        o.show_error_toast()
        o.show_notice("x", ok=False)
        self.assertEqual(o._island_state, "IDLE")
        # Live volume bars are HUD state, still shown with notifications off
        o.show_ear_volume("VOLUME_UP", 0.5, True)
        self.assertEqual(o._island_state, "HOLDING")

    def test_island_switch_hides_everything(self):
        o = self.overlay
        o.configure(island_enabled=False)
        o.show_ear_volume("VOLUME_UP", 0.5, True)
        self.assertEqual(o._island_state, "IDLE")
        o.show_runtime_status({"fps": 30})
        self.assertEqual(o._island_state, "IDLE")
        o.update_state(None, False)
        self.assertTrue(o._is_hidden)
        # show() after a screenshot hide must not re-enable a disabled HUD
        o.hide()
        o.show()
        self.assertTrue(o._force_hide)
        o.configure(island_enabled=True)
        self.assertFalse(o._force_hide)

    def test_handle_event_mapping(self):
        o = self.overlay
        d = EventDispatcher()
        d.subscribe(o.handle_event)
        d.publish("tracking.lost")
        self.assertEqual(o._island_text, "Hand lost")
        o._last_event_time = 0.0  # defeat the 0.8 s duplicate suppression between cases
        d.publish("lock.failed")
        self.assertEqual(o._island_state, "ERROR")
        self.assertEqual(o._island_text, "Lock request failed")
        o._last_event_time = 0.0
        o._toast_until = 0.0
        d.publish("drag.failed", metadata={"error": "NATIVE_BUTTON_UP_FAILED"})
        self.assertEqual(o._island_state, "ERROR")
        self.assertIn("Drag fault", o._island_text)
        o._last_event_time = 0.0
        o._toast_until = 0.0
        d.publish("app.launched", metadata={"app": "WhatsApp"})
        self.assertEqual(o._island_text, "Opening WhatsApp")
        before = (o._island_state, o._island_text)
        d.publish("screenshot.captured", "Saved a.png")   # rendered from controller state, not here
        self.assertEqual((o._island_state, o._island_text), before)
        d.publish("lock.accepted")
        self.assertEqual(o._island_mode, "WAKANDA")
        self.assertEqual(o._island_text, "WAKANDA FOREVER")


# ── 8. Screenshot truth (F-12) ──────────────────────────────────────────────────

class _FakeScreenshotActuator:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def take_screenshot(self, directory, pre_cb=None, post_cb=None):
        if pre_cb:
            pre_cb()
        if post_cb:
            post_cb()
        self.calls.append(directory)
        return self.result


class TestScreenshotResultCallback(unittest.TestCase):
    def _run_hold(self, actuator):
        from core.gestures.screenshot import ScreenshotController, ScreenshotState
        ctrl = ScreenshotController(actuator)
        ctrl.hold_duration = 1.0
        results = []
        order = []
        ctrl.post_capture_cb = lambda: order.append("post")
        ctrl.capture_result_cb = lambda ok, path: (results.append((ok, path)), order.append("result"))
        # Drive the state machine without geometry: force HOLDING then expire the hold.
        ctrl._state = ScreenshotState.HOLDING
        ctrl._hold_start_time = 0.0
        ctrl._last_valid_time = 0.0
        with patch.object(ctrl, "_count_extended", return_value=5), \
             patch("core.gestures.screenshot.is_palm_facing_camera_left_hand", return_value=True), \
             patch("core.gestures.screenshot.is_palm_facing_camera_right_hand", return_value=True):
            hands = MagicMock()
            hands.left = [MagicMock()] * 21
            hands.right = [MagicMock()] * 21
            hands.left_score = 0.95
            hands.right_score = 0.95
            ctrl.process(hands, now=1.5)
        return ctrl, results, order

    def test_success_reports_path_after_post_callback(self):
        from core.gestures.screenshot import ScreenshotState
        ctrl, results, order = self._run_hold(_FakeScreenshotActuator("C:/shots/screenshot_1.png"))
        self.assertEqual(ctrl.state, ScreenshotState.CAPTURED)
        self.assertEqual(results, [(True, "C:/shots/screenshot_1.png")])
        self.assertEqual(order, ["post", "result"])

    def test_failure_reports_false_and_error_state(self):
        from core.gestures.screenshot import ScreenshotState
        ctrl, results, order = self._run_hold(_FakeScreenshotActuator(None))
        self.assertEqual(ctrl.state, ScreenshotState.ERROR)
        self.assertEqual(results, [(False, None)])
        self.assertEqual(order, ["post", "result"])


if __name__ == "__main__":
    unittest.main()

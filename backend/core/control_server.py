# core/control_server.py
"""
Air Point Control Server.
Lightweight, zero-dependency HTTP and Server-Sent Events (SSE) bridge
connecting the Python tracking engine to the React Control Center UI.

Security & Architecture:
- Exclusively binds to 127.0.0.1.
- Strict Origin and Host header validation to prevent cross-site request attacks.
- Input validation and bounds-clamping for all settings.
- Non-blocking daemon thread; zero impact on the 30+ FPS computer vision loop.
- Client disconnects and reconnects handled cleanly without interrupting tracking.
"""

import json
import logging
import os
import queue
import secrets
import socket
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

try:
    import cv2
except ImportError:
    cv2 = None

from core.events import (
    DEFAULT_ISLAND_APPEARANCE,
    DEFAULT_ISLAND_POSITION,
    ISLAND_POSITIONS,
    DyneEvent,
    EventDispatcher,
    sanitize_island_appearance,
    sanitize_island_position,
)

logger = logging.getLogger(__name__)

# Events kept in /api/status (the full ring is served by /api/events/history).
STATUS_EVENT_COUNT = 10
EVENT_HISTORY_LIMIT = 50

# Valid settings boundaries
MIN_HOLD_S = 1.0
MAX_HOLD_S = 10.0
DEFAULT_HOLD_S = 3.0

MIN_SENSITIVITY = 0.2
MAX_SENSITIVITY = 4.0
DEFAULT_SENSITIVITY = 0.85

MIN_SMOOTHING = 10
MAX_SMOOTHING = 100
DEFAULT_SMOOTHING = 65

MIN_ISLAND_HUD_DURATION_S = 10.0
MAX_ISLAND_HUD_DURATION_S = 1800.0
DEFAULT_ISLAND_HUD_DURATION_S = 120.0

MIN_ISLAND_COMPLETION_DURATION_S = 1.0
MAX_ISLAND_COMPLETION_DURATION_S = 5.0
DEFAULT_ISLAND_COMPLETION_DURATION_S = 2.0

SUPPORTED_GESTURES = (
    "pointer",
    "drag",
    "screenshot",
    "whatsapp",
    "mute",
    "volume-up",
    "volume-down",
    "wakanda-forever",
)

_SENTINEL = object()
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_FILE = os.path.join(PROJECT_ROOT, "settings.json")
BRIDGE_INFO_FILE = os.path.join(PROJECT_ROOT, "bridge_info.json")
BRIDGE_TOKEN_FILE = os.path.join(PROJECT_ROOT, ".bridge_token")

DEFAULT_ALLOWED_ORIGINS = {
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8765",
    "http://127.0.0.1:8765",
}


def get_allowed_origins() -> set[str]:
    """Returns the set of approved frontend origins."""
    origins = set(DEFAULT_ALLOWED_ORIGINS)
    env_origins = os.environ.get("AIRPOINT_ALLOWED_ORIGINS")
    if env_origins:
        for orig in env_origins.split(","):
            orig_clean = orig.strip().rstrip("/")
            if orig_clean:
                origins.add(orig_clean)
    return origins


def resolve_settings_path(settings_path: Any = _SENTINEL) -> str | None:
    """
    Resolves the settings file path.
    - If explicitly None or ':memory:', returns None (isolated in-memory mode, no disk reads/writes).
    - If a valid string path is provided, returns that path.
    - If _SENTINEL, checks AIRPOINT_SETTINGS_PATH environment variable:
        * If AIRPOINT_SETTINGS_PATH is set to ':memory:' or empty, returns None.
        * If set to a file path, returns that path.
        * If not set, returns default SETTINGS_FILE.
    """
    if settings_path is not _SENTINEL:
        if settings_path is None:
            return None
        if isinstance(settings_path, str) and (settings_path.strip() == "" or settings_path.strip().lower() == ":memory:"):
            return None
        return str(settings_path)

    env_val = os.environ.get("AIRPOINT_SETTINGS_PATH")
    if env_val is not None:
        if env_val.strip() == "" or env_val.strip().lower() == ":memory:":
            return None
        return os.path.abspath(env_val.strip())

    return SETTINGS_FILE


def clamp_val(val: float, min_val: float, max_val: float) -> float:
    return max(min_val, min(max_val, float(val)))


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _sse_block(event_dict: dict[str, Any]) -> bytes:
    """One SSE message: id line + JSON data line (default 'message' event)."""
    return f"id: {event_dict['id']}\ndata: {json.dumps(event_dict)}\n\n".encode("utf-8")


class RuntimeState:
    """Thread-safe state snapshot shared between Air Point engine and Control Server."""

    def __init__(self, settings_path: Any = _SENTINEL) -> None:
        self._lock = threading.Lock()
        self.settings_path: str | None = resolve_settings_path(settings_path)
        self.running: bool = True
        self.tracking_status: str = "No Hands"
        self.fps: float = 0.0
        self.pointer_owner: str = "NONE"
        self.volume: int = 50
        self.muted: bool = False
        self.active_gesture: str = "idle"
        # Unified Dyne event system: one dispatcher feeds the SSE stream, the
        # status snapshot and (via main.py) the Tk desktop overlay.
        self.events = EventDispatcher(history_limit=EVENT_HISTORY_LIMIT)
        self.recent_events: list[dict[str, Any]] = []
        self.events.subscribe(self._on_dyne_event)

        # Drag fault observability (Phase 1): the logical drag flag, the drag
        # controller state, the last native input error and the OS-reported
        # button state are published separately so that none of them can be
        # mistaken for proof of a completed drag.
        self.drag_state: str = "READY"
        self.drag_logical: bool = False
        self.drag_error: str | None = None
        self.native_button: str = "UNKNOWN"

        # Spatial landmarks snapshot & frame provider
        self._landmarks: dict[str, Any] = {
            "timestamp": 0.0,
            "hands": {"right": None, "left": None},
            "face": None,
            "tracking": "No Hands",
            "owner": "NONE",
            "active_gesture": "idle",
            "is_locked": False,
            "click_state": "DISABLED",
            "last_pinch_norm": 0.0,
        }
        self._frame_provider: Callable[[], Any] | None = None
        
        # Load persisted settings or use defaults
        self.hold_duration: float = DEFAULT_HOLD_S
        self.sensitivity: float = DEFAULT_SENSITIVITY
        self.smoothing: int = DEFAULT_SMOOTHING
        # All gestures, including the Wakanda Forever lock, are on by default; a
        # persisted settings.json or a Control Center toggle can turn any of them off.
        self.enabled_gestures: dict[str, bool] = {g: True for g in SUPPORTED_GESTURES}
        self.power_save: bool = False
        self.power_state: str = "NORMAL"
        self.island_enabled: bool = True
        self.island_notifications_enabled: bool = True
        self.island_timer_enabled: bool = True
        self.island_autohide_enabled: bool = True
        self.island_hud_duration_s: float = DEFAULT_ISLAND_HUD_DURATION_S
        self.island_completion_duration_s: float = DEFAULT_ISLAND_COMPLETION_DURATION_S
        # Dyne position and appearance are persisted so the Tk overlay and the
        # React island use the same choices after a restart.
        self.island_position: str = DEFAULT_ISLAND_POSITION
        self.island_appearance: dict[str, Any] = sanitize_island_appearance(DEFAULT_ISLAND_APPEARANCE)
        if self.settings_path:
            self._load_persisted_settings()

        # SSE listeners: called with each DyneEvent (outside the state lock)
        self._listeners: list[Callable[[DyneEvent], None]] = []
        self._pause_toggle_cb: Callable[[], bool] | None = None
        self._stop_cb: Callable[[], bool] | None = None
        self._start_cb: Callable[[], bool] | None = None
        self._settings_change_cb: Callable[[dict[str, Any]], None] | None = None
        self._exit_cb: Callable[[], bool] | None = None

    def _load_persisted_settings(self) -> None:
        if not self.settings_path or not os.path.exists(self.settings_path):
            return
        try:
            with open(self.settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "hold" in data:
                self.hold_duration = clamp_val(data["hold"], MIN_HOLD_S, MAX_HOLD_S)
            if "sensitivity" in data:
                self.sensitivity = clamp_val(data["sensitivity"], MIN_SENSITIVITY, MAX_SENSITIVITY)
            if "smoothing" in data:
                self.smoothing = int(clamp_val(data["smoothing"], MIN_SMOOTHING, MAX_SMOOTHING))
            if "enabled" in data and isinstance(data["enabled"], dict):
                for k, v in data["enabled"].items():
                    if k in SUPPORTED_GESTURES and isinstance(v, bool):
                        self.enabled_gestures[k] = v
            if "power_save" in data and isinstance(data["power_save"], bool):
                self.power_save = data["power_save"]
            if "island_enabled" in data and isinstance(data["island_enabled"], bool):
                self.island_enabled = data["island_enabled"]
            if "island_notifications_enabled" in data and isinstance(data["island_notifications_enabled"], bool):
                self.island_notifications_enabled = data["island_notifications_enabled"]
            if "island_timer_enabled" in data and isinstance(data["island_timer_enabled"], bool):
                self.island_timer_enabled = data["island_timer_enabled"]
            if "island_autohide_enabled" in data and isinstance(data["island_autohide_enabled"], bool):
                self.island_autohide_enabled = data["island_autohide_enabled"]
            if "island_hud_duration_s" in data and isinstance(data["island_hud_duration_s"], (int, float)):
                self.island_hud_duration_s = clamp_val(data["island_hud_duration_s"], MIN_ISLAND_HUD_DURATION_S, MAX_ISLAND_HUD_DURATION_S)
            if "island_completion_duration_s" in data and isinstance(data["island_completion_duration_s"], (int, float)):
                self.island_completion_duration_s = clamp_val(data["island_completion_duration_s"], MIN_ISLAND_COMPLETION_DURATION_S, MAX_ISLAND_COMPLETION_DURATION_S)
            if "island_position" in data:
                self.island_position = sanitize_island_position(data["island_position"])
            if "island_appearance" in data and isinstance(data["island_appearance"], dict):
                self.island_appearance = sanitize_island_appearance(data["island_appearance"])
        except Exception as e:
            logger.warning("Could not load %s: %s", self.settings_path, e)

    def persist_settings(self) -> None:
        if not self.settings_path:
            return
        try:
            parent_dir = os.path.dirname(os.path.abspath(self.settings_path))
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)
            with open(self.settings_path, "w", encoding="utf-8") as f:
                json.dump({
                    "hold": self.hold_duration,
                    "sensitivity": self.sensitivity,
                    "smoothing": self.smoothing,
                    "enabled": self.enabled_gestures,
                    "power_save": self.power_save,
                    "island_enabled": self.island_enabled,
                    "island_notifications_enabled": self.island_notifications_enabled,
                    "island_timer_enabled": self.island_timer_enabled,
                    "island_autohide_enabled": self.island_autohide_enabled,
                    "island_hud_duration_s": self.island_hud_duration_s,
                    "island_completion_duration_s": self.island_completion_duration_s,
                    "island_position": self.island_position,
                    "island_appearance": self.island_appearance,
                }, f, indent=2)
        except Exception as e:
            logger.warning("Could not persist %s: %s", self.settings_path, e)

    def update_telemetry(
        self,
        running: bool,
        tracking: str,
        fps: float,
        owner: str,
        volume: int,
        muted: bool,
        active_gesture: str = "idle",
        power_state: str = "NORMAL",
        drag_state: str = "READY",
        drag_logical: bool = False,
        drag_error: str | None = None,
        native_button: str = "UNKNOWN",
    ) -> None:
        with self._lock:
            self.running = running
            self.tracking_status = tracking
            self.fps = fps
            self.pointer_owner = owner
            self.volume = max(0, min(100, int(volume)))
            self.muted = muted
            self.active_gesture = active_gesture
            self.power_state = power_state
            self.drag_state = str(drag_state)
            self.drag_logical = bool(drag_logical)
            self.drag_error = str(drag_error) if drag_error else None
            self.native_button = str(native_button)

    def publish_event(
        self,
        event_type: str,
        message: str | None = None,
        **kwargs: Any,
    ) -> DyneEvent:
        """Publishes a catalogued Dyne event (see core/events.py) to every subscriber."""
        return self.events.publish(event_type, message, **kwargs)

    def add_event(self, action: str, event_type: str = "general") -> None:
        """
        Legacy producer kept for older callers: the free-form `event_type` becomes
        the event's type/kind and `action` its title and message. New code uses
        publish_event() with a catalogued type.
        """
        self.events.publish(event_type, action, title=action, kind=event_type, source="legacy")

    def _on_dyne_event(self, event: DyneEvent) -> None:
        """Dispatcher subscriber: mirror into the status ring and fan out to SSE clients."""
        event_dict = event.to_dict()
        # Older consumers read "type" as the legacy short kind; the catalogued type
        # is also exposed under "type" when no legacy kind exists for it.
        event_dict["type"] = event.kind or event.type
        event_dict["event_type"] = event.type
        with self._lock:
            self.recent_events = [event_dict] + self.recent_events[:EVENT_HISTORY_LIMIT - 1]
            listeners_snapshot = list(self._listeners)

        # Notify SSE clients outside the lock
        for listener in listeners_snapshot:
            try:
                listener(event)
            except Exception:
                pass

    def register_listener(self, listener: Callable[[DyneEvent], None]) -> None:
        with self._lock:
            self._listeners.append(listener)

    def unregister_listener(self, listener: Callable[[DyneEvent], None]) -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def event_history(self, after_id: int | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        """Bounded event ring in ascending id order, as serialisable dicts."""
        return [self._serialize_event(ev) for ev in self.events.history(after_id=after_id, limit=limit)]

    @staticmethod
    def _serialize_event(event: DyneEvent) -> dict[str, Any]:
        data = event.to_dict()
        data["type"] = event.kind or event.type
        data["event_type"] = event.type
        return data

    def get_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self.running,
                "tracking": self.tracking_status,
                "fps": round(self.fps, 1),
                "owner": self.pointer_owner,
                "volume": self.volume,
                "muted": self.muted,
                "active_gesture": self.active_gesture,
                "power_state": self.power_state,
                "drag": {
                    "state": self.drag_state,
                    "logical_held": self.drag_logical,
                    "native_button": self.native_button,
                    "last_error": self.drag_error,
                },
                "settings": {
                    "hold": self.hold_duration,
                    "sensitivity": self.sensitivity,
                    "smoothing": self.smoothing,
                    "enabled": dict(self.enabled_gestures),
                    "power_save": self.power_save,
                    "island_enabled": self.island_enabled,
                    "island_notifications_enabled": self.island_notifications_enabled,
                    "island_timer_enabled": self.island_timer_enabled,
                    "island_autohide_enabled": self.island_autohide_enabled,
                    "island_hud_duration_s": self.island_hud_duration_s,
                    "island_completion_duration_s": self.island_completion_duration_s,
                    "island_position": self.island_position,
                    "island_appearance": dict(self.island_appearance),
                },
                "events": list(self.recent_events[:STATUS_EVENT_COUNT]),
                "event_session": self.events.session_id,
                "last_event_id": self.events.last_id,
            }

    def update_landmarks(
        self,
        hands_data: dict[str, Any] | None = None,
        face_data: dict[str, Any] | None = None,
        is_locked: bool = False,
        click_state: str = "DISABLED",
        last_pinch_norm: float = 0.0,
    ) -> None:
        with self._lock:
            self._landmarks = {
                "timestamp": time.time(),
                "hands": hands_data if hands_data is not None else {"right": None, "left": None},
                "face": face_data,
                "tracking": self.tracking_status,
                "owner": self.pointer_owner,
                "active_gesture": self.active_gesture,
                "is_locked": is_locked,
                "click_state": click_state,
                "last_pinch_norm": round(last_pinch_norm, 3),
            }

    def get_landmarks_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._landmarks)

    def set_frame_provider(self, provider: Callable[[], Any] | None) -> None:
        with self._lock:
            self._frame_provider = provider

    def get_latest_jpeg(self, quality: int = 60, max_width: int = 480) -> bytes | None:
        if cv2 is None:
            return None
        with self._lock:
            provider = self._frame_provider
            cached_jpeg = getattr(self, "_cached_jpeg", None)
            cached_frame_id = getattr(self, "_cached_frame_id", None)
        if not provider:
            return None
        try:
            frame = provider()
            if frame is None:
                return None
            frame_id = id(frame)
            if frame_id == cached_frame_id and cached_jpeg is not None:
                return cached_jpeg

            h, w = frame.shape[:2]
            if w > max_width and max_width > 0:
                scale = max_width / float(w)
                new_h = int(h * scale)
                frame = cv2.resize(frame, (max_width, new_h), interpolation=cv2.INTER_LINEAR)
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), max(10, min(100, quality))]
            success, enc = cv2.imencode(".jpg", frame, encode_param)
            if success:
                jpeg_bytes = enc.tobytes()
                with self._lock:
                    self._cached_frame_id = frame_id
                    self._cached_jpeg = jpeg_bytes
                return jpeg_bytes
        except Exception as e:
            logger.debug("Error producing JPEG frame: %s", e)
        return None

    def apply_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if "hold" in updates:
                self.hold_duration = clamp_val(updates["hold"], MIN_HOLD_S, MAX_HOLD_S)
            if "sensitivity" in updates:
                self.sensitivity = clamp_val(updates["sensitivity"], MIN_SENSITIVITY, MAX_SENSITIVITY)
            if "smoothing" in updates:
                self.smoothing = int(clamp_val(updates["smoothing"], MIN_SMOOTHING, MAX_SMOOTHING))
            if "enabled" in updates and isinstance(updates["enabled"], dict):
                for k, v in updates["enabled"].items():
                    if k in SUPPORTED_GESTURES and isinstance(v, bool):
                        self.enabled_gestures[k] = v
            if "power_save" in updates and isinstance(updates["power_save"], bool):
                self.power_save = updates["power_save"]
            if "island_enabled" in updates and isinstance(updates["island_enabled"], bool):
                self.island_enabled = updates["island_enabled"]
            if "island_notifications_enabled" in updates and isinstance(updates["island_notifications_enabled"], bool):
                self.island_notifications_enabled = updates["island_notifications_enabled"]
            if "island_timer_enabled" in updates and isinstance(updates["island_timer_enabled"], bool):
                self.island_timer_enabled = updates["island_timer_enabled"]
            if "island_autohide_enabled" in updates and isinstance(updates["island_autohide_enabled"], bool):
                self.island_autohide_enabled = updates["island_autohide_enabled"]
            if "island_hud_duration_s" in updates and isinstance(updates["island_hud_duration_s"], (int, float)):
                self.island_hud_duration_s = clamp_val(updates["island_hud_duration_s"], MIN_ISLAND_HUD_DURATION_S, MAX_ISLAND_HUD_DURATION_S)
            if "island_completion_duration_s" in updates and isinstance(updates["island_completion_duration_s"], (int, float)):
                self.island_completion_duration_s = clamp_val(updates["island_completion_duration_s"], MIN_ISLAND_COMPLETION_DURATION_S, MAX_ISLAND_COMPLETION_DURATION_S)
            if "island_position" in updates and isinstance(updates["island_position"], str):
                candidate = updates["island_position"].strip().lower()
                if candidate in ISLAND_POSITIONS:
                    self.island_position = candidate  # unknown positions are ignored, never persisted
            if "island_appearance" in updates and isinstance(updates["island_appearance"], dict):
                self.island_appearance = sanitize_island_appearance(updates["island_appearance"], base=self.island_appearance)
            self.persist_settings()
            snapshot = {
                "hold": self.hold_duration,
                "sensitivity": self.sensitivity,
                "smoothing": self.smoothing,
                "enabled": dict(self.enabled_gestures),
                "power_save": self.power_save,
                "island_enabled": self.island_enabled,
                "island_notifications_enabled": self.island_notifications_enabled,
                "island_timer_enabled": self.island_timer_enabled,
                "island_autohide_enabled": self.island_autohide_enabled,
                "island_hud_duration_s": self.island_hud_duration_s,
                "island_completion_duration_s": self.island_completion_duration_s,
                "island_position": self.island_position,
                "island_appearance": dict(self.island_appearance),
            }
            cb = self._settings_change_cb

        if cb:
            try:
                cb(snapshot)
            except Exception as e:
                logger.error("Error invoking settings callback: %s", e)
        return snapshot

    def set_pause_toggle_cb(self, cb: Callable[[], bool]) -> None:
        self._pause_toggle_cb = cb

    def set_lifecycle_callbacks(
        self,
        stop_cb: Callable[[], bool] | None = None,
        start_cb: Callable[[], bool] | None = None,
    ) -> None:
        self._stop_cb = stop_cb
        self._start_cb = start_cb

    def set_settings_change_cb(self, cb: Callable[[dict[str, Any]], None]) -> None:
        self._settings_change_cb = cb

    def set_exit_cb(self, cb: Callable[[], bool] | None) -> None:
        """
        Registers the engine's graceful-exit request handler. The callback only
        raises a flag that the engine main loop consumes; the main loop then
        performs the normal shutdown (drag release, Windows settings restore),
        so no native input is ever injected from the HTTP thread.
        """
        self._exit_cb = cb

    def request_exit(self) -> bool:
        cb = self._exit_cb
        if not cb:
            return False
        try:
            return bool(cb())
        except Exception as e:
            logger.error("Error invoking exit callback: %s", e)
            return False

    def set_test_countdown_cb(self, cb: Callable[[float], Any] | None) -> None:
        self._test_countdown_cb = cb

    def trigger_test_countdown(self, duration_s: float = 5.0) -> bool:
        cb = getattr(self, "_test_countdown_cb", None)
        if cb:
            try:
                cb(float(duration_s))
                return True
            except Exception as e:
                logger.error("Error invoking test countdown callback: %s", e)
                return False
        return False

    def stop(self) -> bool:
        cb = self._stop_cb
        if cb:
            try:
                cb()
            except Exception as e:
                logger.error("Error invoking stop callback: %s", e)
        elif self._pause_toggle_cb and self.running:
            try:
                self._pause_toggle_cb()
            except Exception as e:
                logger.error("Error invoking pause callback: %s", e)
        with self._lock:
            self.running = False
            if self.tracking_status == "Active":
                self.tracking_status = "Stopped"
            return self.running

    def start(self) -> bool:
        cb = self._start_cb
        if cb:
            try:
                cb()
            except Exception as e:
                logger.error("Error invoking start callback: %s", e)
        elif self._pause_toggle_cb and not self.running:
            try:
                self._pause_toggle_cb()
            except Exception as e:
                logger.error("Error invoking resume callback: %s", e)
        with self._lock:
            self.running = True
            if self.tracking_status in ("Paused", "Stopped"):
                self.tracking_status = "Active"
            return self.running

    def toggle_pause(self) -> bool:
        with self._lock:
            curr_running = self.running
        if curr_running:
            return self.stop()
        else:
            return self.start()


class ControlRequestHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for the Air Point Control Bridge."""
    protocol_version = "HTTP/1.1"

    @property
    def control_server(self) -> "ControlServer":
        return getattr(self.server, "control_server", None)

    @property
    def state(self) -> RuntimeState:
        return getattr(self.server, "state", None)

    def _is_origin_allowed(self) -> tuple[bool, str]:
        origin = self.headers.get("Origin")
        if not origin:
            # Allow origin-less requests (direct browser navigation, curl, local scripts, unittests)
            return True, "*"
        origin_clean = origin.rstrip("/")
        allowed_origins = get_allowed_origins()
        if origin_clean in allowed_origins:
            return True, origin
        cs = self.control_server
        if cs:
            server_origin = f"http://{cs.host}:{cs.port}"
            server_origin_local = f"http://localhost:{cs.port}"
            if origin_clean in (server_origin, server_origin_local):
                return True, origin
        return False, ""

    def _is_host_allowed(self) -> bool:
        host = self.headers.get("Host", "")
        # Remove port if present
        host_name = host.split(":")[0].lower()
        return host_name in ("127.0.0.1", "localhost")

    def _is_mutation_authorized(self, origin: str) -> bool:
        # Check token if presented in header
        provided_token = self.headers.get("X-AirPoint-Token")
        server_token = getattr(getattr(self.server, "control_server", None), "token", None)
        if provided_token:
            if server_token and secrets.compare_digest(provided_token, server_token):
                return True
            else:
                logger.warning("Rejected mutation with invalid X-AirPoint-Token")
                return False

        # If origin header is present, ensure it is strictly in allowed origins
        origin_header = self.headers.get("Origin")
        if origin_header:
            allowed, _ = self._is_origin_allowed()
            return allowed

        # For origin-less requests (local tests / scripts), ensure Host header is local
        return self._is_host_allowed()

    def _send_cors_headers(self, origin: str) -> None:
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept, X-AirPoint-Token")
        self.send_header("Access-Control-Max-Age", "86400")

    def do_OPTIONS(self) -> None:
        allowed, origin = self._is_origin_allowed()
        if not allowed or not self._is_host_allowed():
            self.send_error(HTTPStatus.FORBIDDEN, "Forbidden origin or host")
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers(origin)
        self.end_headers()

    def do_GET(self) -> None:
        allowed, origin = self._is_origin_allowed()
        if not allowed or not self._is_host_allowed():
            self.send_error(HTTPStatus.FORBIDDEN, "Forbidden origin or host")
            return

        parsed_url = urlparse(self.path)
        path = parsed_url.path

        if path == "/api/status":
            data = self.state.get_snapshot()
            token = getattr(getattr(self.server, "control_server", None), "token", None)
            if token:
                data["token"] = token
            payload = json.dumps(data).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self._send_cors_headers(origin)
            self.end_headers()
            self.wfile.write(payload)

        elif path == "/api/events/history":
            # Bounded event ring (ascending ids). ?after=<id> returns only newer
            # events, which is how a reconnecting client fills a gap.
            params = parse_qs(parsed_url.query)
            after_id = _parse_int(params.get("after", [None])[0])
            limit = _parse_int(params.get("limit", [None])[0])
            if limit is None or limit <= 0 or limit > EVENT_HISTORY_LIMIT:
                limit = EVENT_HISTORY_LIMIT
            data = {
                "session": self.state.events.session_id,
                "last_event_id": self.state.events.last_id,
                "events": self.state.event_history(after_id=after_id, limit=limit),
            }
            payload = json.dumps(data).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-cache")
            self._send_cors_headers(origin)
            self.end_headers()
            self.wfile.write(payload)

        elif path == "/api/events":
            # Server-Sent Events stream. Every event carries an `id:` line so the
            # browser EventSource resends it as Last-Event-ID on reconnect and the
            # missed events (still in the ring) are replayed before live ones.
            params = parse_qs(parsed_url.query)
            resume_after = _parse_int(self.headers.get("Last-Event-ID"))
            if resume_after is None:
                resume_after = _parse_int(params.get("after", [None])[0])

            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self._send_cors_headers(origin)
            self.end_headers()

            client_queue: queue.Queue[DyneEvent] = queue.Queue(maxsize=100)

            def queue_event(event: DyneEvent) -> None:
                try:
                    client_queue.put_nowait(event)
                except queue.Full:
                    pass

            # Register before replaying so nothing published in between is lost;
            # duplicates (same id) are filtered below.
            self.state.register_listener(queue_event)
            last_sent_id = resume_after if resume_after is not None else 0
            try:
                hello = {
                    "event": "connected",
                    "status": "ok",
                    "session": self.state.events.session_id,
                    "last_event_id": self.state.events.last_id,
                }
                self.wfile.write(f": connected\ndata: {json.dumps(hello)}\n\n".encode("utf-8"))
                self.wfile.flush()

                if resume_after is not None:
                    for ev in self.state.events.history(after_id=resume_after):
                        self.wfile.write(_sse_block(self.state._serialize_event(ev)))
                        last_sent_id = max(last_sent_id, ev.id)
                    self.wfile.flush()

                while self.control_server and self.control_server.is_active:
                    try:
                        item = client_queue.get(timeout=10.0)
                        if item.id <= last_sent_id and item.session == self.state.events.session_id:
                            continue  # already replayed from history
                        self.wfile.write(_sse_block(self.state._serialize_event(item)))
                        self.wfile.flush()
                        last_sent_id = max(last_sent_id, item.id)
                    except queue.Empty:
                        # Keep-alive heartbeat
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, TimeoutError, ConnectionAbortedError):
                pass
            except Exception as e:
                logger.debug("SSE client connection closed: %s", e)
            finally:
                self.state.unregister_listener(queue_event)

        elif path == "/api/landmarks":
            data = self.state.get_landmarks_snapshot()
            payload = json.dumps(data).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self._send_cors_headers(origin)
            self.end_headers()
            self.wfile.write(payload)

        elif path == "/api/camera/frame":
            jpeg = self.state.get_latest_jpeg(quality=70, max_width=480)
            if jpeg is None:
                self.send_error(HTTPStatus.SERVICE_UNAVAILABLE, "Camera frame not available")
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(jpeg)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self._send_cors_headers(origin)
            self.end_headers()
            self.wfile.write(jpeg)

        elif path == "/api/camera/stream":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Connection", "close")
            self._send_cors_headers(origin)
            self.end_headers()

            try:
                while self.control_server and self.control_server.is_active:
                    jpeg = self.state.get_latest_jpeg(quality=55, max_width=480)
                    if jpeg is not None:
                        part = (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n"
                            b"Content-Length: " + str(len(jpeg)).encode("ascii") + b"\r\n\r\n"
                            + jpeg + b"\r\n"
                        )
                        self.wfile.write(part)
                        self.wfile.flush()
                    # Cap streaming at ~15 FPS to preserve tracking performance
                    time.sleep(0.066)
            except (BrokenPipeError, ConnectionResetError, TimeoutError, ConnectionAbortedError):
                pass
            except Exception as e:
                logger.debug("Camera stream connection closed: %s", e)

        elif path.startswith("/static/") or path == "/" or path.endswith((".js", ".css", ".svg", ".woff2")):
            # Optional: Serve static Control Center UI if available in web_dist
            self._serve_static_ui(path)
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def do_POST(self) -> None:
        content_len = int(self.headers.get("Content-Length", 0))
        allowed, origin = self._is_origin_allowed()
        if not allowed or not self._is_host_allowed() or not self._is_mutation_authorized(origin):
            if 0 < content_len <= 16384:
                try:
                    self.rfile.read(content_len)
                except Exception:
                    pass
            self.send_error(HTTPStatus.FORBIDDEN, "Forbidden origin or host")
            return

        parsed_url = urlparse(self.path)
        path = parsed_url.path

        content_len = int(self.headers.get("Content-Length", 0))
        if content_len > 16384:  # Restrict payload size to 16KB max
            self.send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Payload too large")
            return

        body = self.rfile.read(content_len) if content_len > 0 else b"{}"
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except json.JSONDecodeError:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid JSON")
            return

        if path == "/api/settings":
            if not isinstance(payload, dict):
                self.send_error(HTTPStatus.BAD_REQUEST, "Payload must be a JSON object")
                return
            updated = self.state.apply_settings(payload)
            resp = json.dumps({"status": "ok", "settings": updated}).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(resp)))
            self._send_cors_headers(origin)
            self.end_headers()
            self.wfile.write(resp)

        elif path == "/api/stop":
            new_running = self.state.stop()
            resp = json.dumps({"status": "ok", "running": new_running, "action": "stop"}).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(resp)))
            self._send_cors_headers(origin)
            self.end_headers()
            self.wfile.write(resp)

        elif path == "/api/start":
            new_running = self.state.start()
            resp = json.dumps({"status": "ok", "running": new_running, "action": "start"}).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(resp)))
            self._send_cors_headers(origin)
            self.end_headers()
            self.wfile.write(resp)

        elif path == "/api/control":
            if not isinstance(payload, dict):
                self.send_error(HTTPStatus.BAD_REQUEST, "Payload must be a JSON object")
                return
            action = str(payload.get("action", "")).lower()
            if action in ("stop", "shutdown", "pause"):
                new_running = self.state.stop()
            elif action in ("start", "resume"):
                new_running = self.state.start()
            elif action == "toggle":
                new_running = self.state.toggle_pause()
            elif action in ("test_countdown", "test_island_countdown"):
                dur = float(payload.get("duration", 5.0))
                ok = self.state.trigger_test_countdown(dur)
                resp = json.dumps({"status": "ok", "running": self.state.running, "action": action, "triggered": ok, "duration": dur}).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(resp)))
                self._send_cors_headers(origin)
                self.end_headers()
                self.wfile.write(resp)
                return
            elif action == "exit":
                # Graceful engine exit for the launcher's stop script: the main
                # loop ends its iteration and runs the normal shutdown path
                # (drag release first). "accepted" is False when no engine is
                # attached (control-server-only mode).
                accepted = self.state.request_exit()
                resp = json.dumps({"status": "ok", "action": "exit", "accepted": accepted}).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(resp)))
                self._send_cors_headers(origin)
                self.end_headers()
                self.wfile.write(resp)
                return
            else:
                self.send_error(HTTPStatus.BAD_REQUEST, f"Unknown action '{action}'")
                return
            resp = json.dumps({"status": "ok", "running": new_running, "action": action}).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(resp)))
            self._send_cors_headers(origin)
            self.end_headers()
            self.wfile.write(resp)

        elif path in ("/api/overlay/test", "/api/overlay/test_countdown"):
            dur = float(payload.get("duration", 5.0)) if isinstance(payload, dict) else 5.0
            ok = self.state.trigger_test_countdown(dur)
            resp = json.dumps({"status": "ok", "action": "test_countdown", "triggered": ok, "duration": dur}).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(resp)))
            self._send_cors_headers(origin)
            self.end_headers()
            self.wfile.write(resp)

        elif path == "/api/toggle":
            new_running = self.state.toggle_pause()
            resp = json.dumps({"status": "ok", "running": new_running, "action": "toggle"}).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(resp)))
            self._send_cors_headers(origin)
            self.end_headers()
            self.wfile.write(resp)

        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def _serve_static_ui(self, path: str) -> None:
        # Check if static build directory exists
        dist_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui_dist")
        if not os.path.exists(dist_dir):
            if path == "/":
                html = (
                    "<!DOCTYPE html><html><head><title>Air Point Control Bridge</title>"
                    "<style>body{font-family:system-ui,-apple-system,sans-serif;background:#0d1117;color:#e6edf3;padding:40px;line-height:1.6}"
                    "a{color:#58a6ff}code{background:#161b22;padding:2px 6px;border-radius:4px}</style></head>"
                    "<body><h2>🟢 Air Point Control Bridge Active</h2>"
                    "<p>Engine is running on <code>127.0.0.1:8765</code>.</p>"
                    "<p>Access the Control Center UI at <a href=\"http://localhost:8080\">http://localhost:8080</a></p>"
                    "<p>Raw status endpoint: <a href=\"/api/status\">/api/status</a></p></body></html>"
                ).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)
                return
            self.send_error(HTTPStatus.NOT_FOUND, "Static UI not found. Use dev server or run build.")
            return

        rel_path = path.lstrip("/")
        if not rel_path or rel_path == "/":
            rel_path = "index.html"
        file_path = os.path.abspath(os.path.join(dist_dir, rel_path))
        # Prevent directory traversal
        if not file_path.startswith(os.path.abspath(dist_dir)):
            self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
            return

        if not os.path.exists(file_path) or os.path.isdir(file_path):
            file_path = os.path.join(dist_dir, "index.html")

        content_type = "text/html"
        if file_path.endswith(".js"):
            content_type = "application/javascript"
        elif file_path.endswith(".css"):
            content_type = "text/css"
        elif file_path.endswith(".svg"):
            content_type = "image/svg+xml"
        elif file_path.endswith(".woff2"):
            content_type = "font/woff2"

        try:
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(e))

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress noisy standard HTTP request access logs
        logger.debug("%s - - [%s] %s", self.client_address[0], self.log_date_time_string(), format % args)


class _AirPointHTTPServer(ThreadingHTTPServer):
    """
    HTTP Server configured with exclusive address use on Windows
    to prevent port hijacking and enable reliable port collision detection.
    """
    allow_reuse_address = False

    def server_bind(self) -> None:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE") and os.name == "nt":
            try:
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            except OSError:
                pass
        super().server_bind()

    def handle_error(self, request: Any, client_address: Any) -> None:
        exc_type, exc_val, _ = sys.exc_info()
        if exc_type is not None and issubclass(exc_type, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
            logger.debug("Client %s disconnected: %s", client_address, exc_val)
            return
        super().handle_error(request, client_address)


class ControlServer:
    """Threaded HTTP/SSE server running on 127.0.0.1 in the background."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        settings_path: Any = _SENTINEL,
        state: RuntimeState | None = None,
        token: str | None = None,
        allow_port_fallback: bool = False,
    ) -> None:
        self.host = host
        self.port = port
        self.state = state if state is not None else RuntimeState(settings_path=settings_path)
        self.token = token if token is not None else secrets.token_hex(32)
        self.allow_port_fallback = allow_port_fallback or (os.environ.get("AIRPOINT_PORT_FALLBACK", "").lower() in ("1", "true"))
        self.is_active = False
        self._server: _AirPointHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._token_path: str | None = None
        self._info_path: str | None = None

    def start(self) -> None:
        if self.is_active:
            return
        self.is_active = True
        target_port = self.port

        try:
            self._server = _AirPointHTTPServer((self.host, target_port), ControlRequestHandler)
        except OSError as err:
            # Deterministic port collision handling
            if target_port != 0 and not self.allow_port_fallback:
                self.is_active = False
                logger.error(
                    "Port collision: Port %d on %s is already in use (%s). "
                    "Another instance of Air Point or another local service may be running. "
                    "To resolve: close the existing Air Point instance or run "
                    "'netstat -ano | findstr :%d' to find and terminate the occupying PID.",
                    target_port,
                    self.host,
                    err,
                    target_port,
                )
                raise RuntimeError(
                    f"Port collision: Port {target_port} on {self.host} is already in use by another process. "
                    f"Stop the existing process or specify another port."
                ) from err
            else:
                logger.warning("Port %d busy. Fallback enabled; binding to dynamic free port on %s", target_port, self.host)
                self._server = _AirPointHTTPServer((self.host, 0), ControlRequestHandler)

        self._server.control_server = self  # type: ignore[attr-defined]
        self._server.state = self.state  # type: ignore[attr-defined]
        self._server.token = self.token  # type: ignore[attr-defined]
        self.port = self._server.server_port
        logger.info("Air Point Control Bridge bound to http://%s:%d", self.host, self.port)

        # Write discovery files if not in isolated memory test mode
        if getattr(self.state, "settings_path", None) is not None and os.environ.get("AIRPOINT_SETTINGS_PATH") != ":memory:":
            self._write_bridge_files()

        self._thread = threading.Thread(target=self._run, name="AirPointControlServer", daemon=True)
        self._thread.start()

    def _write_bridge_files(self) -> None:
        try:
            self._token_path = BRIDGE_TOKEN_FILE
            with open(self._token_path, "w", encoding="utf-8") as f:
                f.write(self.token)

            self._info_path = BRIDGE_INFO_FILE
            info_data = {
                "host": self.host,
                "port": self.port,
                "pid": os.getpid(),
                "token": self.token,
                "started_at": time.time(),
            }
            with open(self._info_path, "w", encoding="utf-8") as f:
                json.dump(info_data, f, indent=2)
        except Exception as e:
            logger.debug("Failed writing bridge discovery files: %s", e)

    def _cleanup_bridge_files(self) -> None:
        for path in (self._token_path, self._info_path):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
        self._token_path = None
        self._info_path = None

    def _run(self) -> None:
        if self._server:
            try:
                self._server.serve_forever()
            except Exception as e:
                logger.debug("ControlServer exited: %s", e)

    def stop(self) -> None:
        self.is_active = False
        self._cleanup_bridge_files()
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        logger.info("Air Point Control Bridge stopped")


if __name__ == "__main__":
    import time
    server = ControlServer(host="127.0.0.1", port=8765)
    server.start()
    print(f"Air Point Control Bridge running at http://{server.host}:{server.port}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()

# core/events.py
"""
Dyne event system (unified migration, Stage E).

One normalised event schema serves every notification surface:

    gesture / engine code ─► EventDispatcher.publish() ─► subscribers
                                                          ├─ RuntimeState: bounded history, /api/status,
                                                          │  SSE fan-out with ids (React Control Center island)
                                                          └─ ScreenshotOverlay.handle_event (Tk desktop capsule)

Schema (DyneEvent.to_dict()):

    id          monotonic integer per engine process (1, 2, 3, ...)
    session     short random token identifying the engine process, so ids from
                an earlier run are never mistaken for new ones after a restart
    type        dotted event type from EVENT_CATALOGUE ("tracking.lost", ...)
    timestamp   epoch seconds (float);  time = local HH:MM:SS for display
    source      producer ("engine", "gesture:screenshot", "bridge", ...)
    title       short human title ("Screenshot captured")
    message     one-line detail ("Saved screenshot_20261102_221500.png")
    priority    "low" | "normal" | "high" | "critical"
    duration_s  suggested on-screen duration for the island
    metadata    free-form JSON object (paths, volumes, reasons, api results)
    event/action/kind   legacy keys kept for pre-migration consumers

Events are produced only where the corresponding real behaviour happened: the
producers publish after the native action returned its result (screenshot file
written, LockWorkStation return value, LEFTUP confirmed, ...). Nothing in this
module fabricates an outcome; failures are events of their own.
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

PRIORITY_LOW = "low"
PRIORITY_NORMAL = "normal"
PRIORITY_HIGH = "high"
PRIORITY_CRITICAL = "critical"
PRIORITIES: tuple[str, ...] = (PRIORITY_LOW, PRIORITY_NORMAL, PRIORITY_HIGH, PRIORITY_CRITICAL)

DEFAULT_DURATION_S = 2.0
MIN_DURATION_S = 0.5
MAX_DURATION_S = 30.0
DEFAULT_HISTORY_LIMIT = 50


@dataclass(frozen=True)
class EventSpec:
    """Catalogue entry: defaults for a known event type."""

    title: str
    priority: str
    duration_s: float
    kind: str  # legacy short kind kept for older bridge consumers


# Every type the engine publishes. Adding a type here is the documentation step;
# producers reference the type string and may override message / metadata.
EVENT_CATALOGUE: dict[str, EventSpec] = {
    # Engine lifecycle
    "engine.started": EventSpec("AirPoint started", PRIORITY_LOW, 2.0, "started"),
    "engine.paused": EventSpec("AirPoint paused", PRIORITY_HIGH, 2.0, "paused"),
    "engine.resumed": EventSpec("AirPoint resumed", PRIORITY_NORMAL, 2.0, "resumed"),
    "engine.stopping": EventSpec("AirPoint stopping", PRIORITY_HIGH, 2.0, "stopping"),
    # Hand tracking
    "tracking.acquired": EventSpec("Hand acquired", PRIORITY_NORMAL, 1.5, "acquired"),
    "tracking.lost": EventSpec("Hand lost", PRIORITY_NORMAL, 1.5, "lost"),
    "tracking.recovered": EventSpec("Hand reacquired", PRIORITY_NORMAL, 1.5, "reacquired"),
    # Screenshot gesture
    "screenshot.captured": EventSpec("Screenshot captured", PRIORITY_HIGH, 2.5, "screenshot"),
    "screenshot.failed": EventSpec("Screenshot failed", PRIORITY_CRITICAL, 3.0, "screenshot-failed"),
    # Application launch (WhatsApp W gesture)
    "app.launched": EventSpec("Application launched", PRIORITY_HIGH, 2.5, "whatsapp"),
    "app.launch_failed": EventSpec("Application not found", PRIORITY_CRITICAL, 3.0, "whatsapp-failed"),
    # Audio gestures
    "audio.volume": EventSpec("Volume changed", PRIORITY_NORMAL, 1.2, "volume"),
    "audio.muted": EventSpec("Mute enabled", PRIORITY_HIGH, 2.0, "muted"),
    "audio.unmuted": EventSpec("Mute disabled", PRIORITY_HIGH, 2.0, "unmuted"),
    "audio.failed": EventSpec("Audio control failed", PRIORITY_CRITICAL, 3.0, "audio-failed"),
    # Left-hand drag (native input)
    "drag.started": EventSpec("Drag started", PRIORITY_NORMAL, 1.5, "drag"),
    "drag.completed": EventSpec("Drag completed", PRIORITY_NORMAL, 2.0, "drag"),
    "drag.released": EventSpec("Drag released", PRIORITY_NORMAL, 2.0, "drag"),
    "drag.failed": EventSpec("Drag failed", PRIORITY_CRITICAL, 4.0, "drag-fault"),
    # Wakanda Forever / workstation lock
    "wakanda.confirmed": EventSpec("Wakanda Forever", PRIORITY_HIGH, 1.5, "wakanda-forever"),
    "lock.accepted": EventSpec("Lock request accepted", PRIORITY_CRITICAL, 3.0, "wakanda-forever"),
    "lock.failed": EventSpec("Lock request failed", PRIORITY_CRITICAL, 4.0, "wakanda-forever-failed"),
    # Power management
    "power.save_entered": EventSpec("Power saver", PRIORITY_NORMAL, 2.0, "power_save"),
    "power.wake": EventSpec("Woke from power saver", PRIORITY_NORMAL, 2.0, "wake"),
}


@dataclass(frozen=True)
class DyneEvent:
    id: int
    session: str
    type: str
    timestamp: float
    source: str
    title: str
    message: str
    priority: str
    duration_s: float
    metadata: dict[str, Any] = field(default_factory=dict)
    kind: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session": self.session,
            "type": self.type,
            "timestamp": round(self.timestamp, 3),
            "time": time.strftime("%H:%M:%S", time.localtime(self.timestamp)),
            "source": self.source,
            "title": self.title,
            "message": self.message,
            "priority": self.priority,
            "duration_s": self.duration_s,
            "metadata": dict(self.metadata),
            # Legacy keys (pre-migration SSE/status consumers read these).
            "event": self.kind,
            "action": self.message,
        }


Subscriber = Callable[[DyneEvent], None]


class EventDispatcher:
    """
    Thread-safe producer of DyneEvents with a bounded history and fan-out.

    publish() may be called from the engine main thread, the hotkey thread or
    an HTTP handler thread. Subscribers are invoked outside the lock, in
    publish() order, on the publishing thread; a subscriber that needs a
    particular thread (the Tk overlay) re-dispatches internally.
    """

    def __init__(
        self,
        history_limit: int = DEFAULT_HISTORY_LIMIT,
        session_id: str | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._lock = threading.Lock()
        self._next_id = 1
        self._history: deque[DyneEvent] = deque(maxlen=max(1, int(history_limit)))
        self._subscribers: list[Subscriber] = []
        self._clock = clock
        self.session_id: str = session_id or secrets.token_hex(4)

    # ── subscriptions ────────────────────────────────────────────────────────
    def subscribe(self, callback: Subscriber) -> None:
        with self._lock:
            if callback not in self._subscribers:
                self._subscribers.append(callback)

    def unsubscribe(self, callback: Subscriber) -> None:
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    # ── publishing ───────────────────────────────────────────────────────────
    def publish(
        self,
        event_type: str,
        message: str | None = None,
        *,
        title: str | None = None,
        priority: str | None = None,
        duration_s: float | None = None,
        source: str = "engine",
        metadata: dict[str, Any] | None = None,
        kind: str | None = None,
        timestamp: float | None = None,
    ) -> DyneEvent:
        spec = EVENT_CATALOGUE.get(event_type)
        resolved_title = title or (spec.title if spec else (message or event_type))
        resolved_message = message if message is not None else resolved_title
        resolved_priority = priority or (spec.priority if spec else PRIORITY_NORMAL)
        if resolved_priority not in PRIORITIES:
            resolved_priority = PRIORITY_NORMAL
        raw_duration = duration_s if duration_s is not None else (spec.duration_s if spec else DEFAULT_DURATION_S)
        try:
            resolved_duration = float(raw_duration)
        except (TypeError, ValueError):
            resolved_duration = DEFAULT_DURATION_S
        resolved_duration = max(MIN_DURATION_S, min(MAX_DURATION_S, resolved_duration))
        resolved_kind = kind or (spec.kind if spec else event_type)
        safe_metadata = dict(metadata) if isinstance(metadata, dict) else {}

        with self._lock:
            event = DyneEvent(
                id=self._next_id,
                session=self.session_id,
                type=str(event_type),
                timestamp=float(timestamp if timestamp is not None else self._clock()),
                source=str(source),
                title=str(resolved_title),
                message=str(resolved_message),
                priority=resolved_priority,
                duration_s=resolved_duration,
                metadata=safe_metadata,
                kind=str(resolved_kind),
            )
            self._next_id += 1
            self._history.append(event)
            subscribers = list(self._subscribers)

        for callback in subscribers:
            try:
                callback(event)
            except Exception as e:  # a broken subscriber must never break the producer
                logger.error("Dyne event subscriber %r failed on %s: %s", callback, event.type, e)
        return event

    # ── history ──────────────────────────────────────────────────────────────
    def history(self, after_id: int | None = None, limit: int | None = None) -> list[DyneEvent]:
        """Events in ascending id order, optionally only those with id > after_id."""
        with self._lock:
            items = list(self._history)
        if after_id is not None:
            items = [ev for ev in items if ev.id > int(after_id)]
        if limit is not None and limit >= 0:
            items = items[-int(limit):] if limit > 0 else []
        return items

    @property
    def last_id(self) -> int:
        with self._lock:
            return self._next_id - 1

    @property
    def history_limit(self) -> int:
        return self._history.maxlen or DEFAULT_HISTORY_LIMIT


# ── Producer helpers (pure, unit-testable without the engine) ───────────────────

_RELEASE_MESSAGES: dict[str, str] = {
    "UNPINCH": "Object dropped: left pinch released and native LEFTUP confirmed",
    "TRACKING_LOSS": "Released: left hand lost for longer than the tracking grace period",
    "PAUSE": "Released: tracking paused",
    "SHUTDOWN": "Released: engine shutting down",
    "SAFE_RELEASE": "Released: safety release",
    "RESET": "Released: controller reset",
    "FEATURE_DISABLED": "Released: drag gesture disabled",
}


class DragEventTracker:
    """
    Turns LeftDragController state transitions into drag events.

    The tracker only observes names already published in /api/status (state,
    release reason, last native error); it never touches the controller or the
    actuator, so it cannot become a second native-input owner.
    """

    def __init__(self) -> None:
        self._prev_state = "READY"

    @property
    def previous_state(self) -> str:
        return self._prev_state

    def observe(
        self,
        state_name: str | None,
        release_reason: str | None = None,
        last_error: str | None = None,
    ) -> list[tuple[str, str, dict[str, Any]]]:
        """
        Returns a list of (event_type, message, metadata) for the transition
        from the previously observed state to `state_name`. Empty when nothing
        changed or the change is not an event (READY -> GRAB_PENDING, cancelled
        pinches).
        """
        prev = self._prev_state
        cur = str(state_name or "READY")
        if cur == prev:
            return []
        self._prev_state = cur

        reason = str(release_reason) if release_reason else None
        error = str(last_error) if last_error else None
        meta: dict[str, Any] = {"from": prev, "to": cur}
        if reason:
            meta["reason"] = reason
        if error:
            meta["error"] = error

        if cur == "GRAB_LOCKED":
            if prev == "RELEASE_PENDING":
                return []  # jitter recovery inside the same grab, not a new drag
            return [("drag.started", "Left pinch locked: native LEFTDOWN confirmed, right hand steers", meta)]

        if cur == "INPUT_ERROR":
            what = "LEFTUP" if prev in ("GRAB_LOCKED", "RELEASE_PENDING") else "LEFTDOWN"
            return [(
                "drag.failed",
                f"Native {what} not confirmed ({error or 'SendInput error'}); the watchdog keeps retrying every 250 ms",
                meta,
            )]

        if cur == "READY" and prev in ("GRAB_LOCKED", "RELEASE_PENDING"):
            if reason == "INPUT_ERROR" or error:
                return [("drag.failed", f"Release not confirmed ({error or 'INPUT_ERROR'})", meta)]
            if reason == "UNPINCH":
                return [("drag.completed", _RELEASE_MESSAGES["UNPINCH"], meta)]
            text = _RELEASE_MESSAGES.get(reason or "", f"Released: {reason or 'unknown reason'}")
            return [("drag.released", text, meta)]

        if cur == "READY" and prev == "INPUT_ERROR":
            if error:
                return [("drag.failed", f"Left INPUT_ERROR with an unresolved native error ({error})", meta)]
            return [("drag.released", "Native release recovered; controller back to READY", meta)]

        # READY -> GRAB_PENDING, GRAB_PENDING -> READY (cancelled), GRAB_LOCKED ->
        # RELEASE_PENDING and similar are not notifications.
        return []


class VolumeEventCoalescer:
    """
    Rate-limits the continuous ear-volume callback (one call per 50 ms tick)
    into at most one event per `min_interval_s` while the gesture is active
    plus exactly one final event when it ends (F-13).
    """

    def __init__(self, min_interval_s: float = 0.25) -> None:
        self.min_interval_s = max(0.0, float(min_interval_s))
        self._last_emit: float | None = None
        self._active = False
        self._last_volume: float | None = None

    def offer(self, direction: str, volume: float, active: bool, now: float) -> dict[str, Any] | None:
        """
        Returns the metadata for an event to publish, or None to stay quiet.
        """
        vol = max(0.0, min(1.0, float(volume)))
        direction_name = "up" if str(direction).upper() in ("VOLUME_UP", "UP") else "down"
        if active:
            self._active = True
            if self._last_emit is not None and (now - self._last_emit) < self.min_interval_s:
                return None
            self._last_emit = now
            self._last_volume = vol
            return {"direction": direction_name, "volume": round(vol, 3), "percent": int(round(vol * 100)), "final": False}
        if not self._active:
            return None
        self._active = False
        self._last_emit = None
        self._last_volume = vol
        return {"direction": direction_name, "volume": round(vol, 3), "percent": int(round(vol * 100)), "final": True}


# ── Dyne appearance / position (shared by the Tk overlay and the React island) ─

ISLAND_POSITIONS: tuple[str, ...] = ("top-center", "top-left", "top-right", "bottom-center")
DEFAULT_ISLAND_POSITION = "top-center"

# Colour names shared with frontend/src/components/air-point/dyne-studio/studio.ts
DYNE_COLOURS: dict[str, str] = {
    "Brown": "#a7784c", "Red": "#ef505c", "Blue": "#348cff", "Neon": "#b1ed4e", "Green": "#3cd6a0",
    "White": "#edf5ff", "Grey": "#8794a1", "Gold": "#f4c75b", "Purple": "#b37bea", "Orange": "#f7a34e",
    "Cyan": "#48D8E8", "Teal": "#159E98", "Mint": "#91E7C0", "Lime": "#C4EE52", "Yellow": "#F4DB55",
    "Amber": "#ED9D42", "Coral": "#FF8075", "Crimson": "#BD334E", "Rose": "#F18BB3", "Magenta": "#DC5BD8",
}
DYNE_TEXTURES: tuple[str, ...] = ("Matte", "Glass", "Translucent")
DYNE_STYLES: tuple[str, ...] = ("Luminous", "Balanced", "Quiet")
DYNE_FONTS: tuple[str, ...] = ("System", "Mono", "Humanist")

DEFAULT_ISLAND_APPEARANCE: dict[str, Any] = {
    "accent": "Gold",
    "texture": "Glass",
    "font": "System",
    "fontSize": 23,
    "weight": 400,
    "intensity": 50,
    "matteIntensity": 50,
    "translucentIntensity": 50,
    "roundness": 56,
    "style": "Balanced",
    "customRgb": {"r": 140, "g": 80, "b": 255},
}


def _clamp_int(value: Any, lo: int, hi: int, default: int) -> int:
    try:
        return int(max(lo, min(hi, int(round(float(value))))))
    except (TypeError, ValueError):
        return default


def sanitize_island_position(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in ISLAND_POSITIONS else DEFAULT_ISLAND_POSITION


def sanitize_island_appearance(raw: Any, base: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Validates a Dyne Studio appearance object. Unknown keys are dropped, bad
    values fall back to `base` (or the defaults); the result is always complete
    so every consumer can rely on every key being present.
    """
    current = dict(DEFAULT_ISLAND_APPEARANCE if base is None else base)
    current["customRgb"] = dict(current.get("customRgb") or DEFAULT_ISLAND_APPEARANCE["customRgb"])
    if not isinstance(raw, dict):
        return current

    accent = raw.get("accent", current["accent"])
    if isinstance(accent, str) and (accent in DYNE_COLOURS or accent == "Custom"):
        current["accent"] = accent
    texture = raw.get("texture", current["texture"])
    if texture in DYNE_TEXTURES:
        current["texture"] = texture
    style = raw.get("style", current["style"])
    if style in DYNE_STYLES:
        current["style"] = style
    font = raw.get("font", current["font"])
    if font in DYNE_FONTS:
        current["font"] = font
    current["fontSize"] = _clamp_int(raw.get("fontSize", current["fontSize"]), 18, 28, int(current["fontSize"]))
    current["weight"] = _clamp_int(raw.get("weight", current["weight"]), 300, 800, int(current["weight"]))
    for key in ("intensity", "matteIntensity", "translucentIntensity"):
        current[key] = _clamp_int(raw.get(key, current[key]), 0, 100, int(current[key]))
    current["roundness"] = _clamp_int(raw.get("roundness", current["roundness"]), 28, 56, int(current["roundness"]))
    rgb = raw.get("customRgb")
    if isinstance(rgb, dict):
        current["customRgb"] = {
            ch: _clamp_int(rgb.get(ch, current["customRgb"].get(ch, 0)), 0, 255, int(current["customRgb"].get(ch, 0)))
            for ch in ("r", "g", "b")
        }
    return current


def island_accent_hex(appearance: dict[str, Any] | None) -> str:
    """Resolves the accent colour of an appearance object to a #rrggbb string."""
    app = sanitize_island_appearance(appearance)
    if app["accent"] == "Custom":
        rgb = app["customRgb"]
        return "#{:02x}{:02x}{:02x}".format(rgb["r"], rgb["g"], rgb["b"])
    return DYNE_COLOURS.get(app["accent"], DYNE_COLOURS["Gold"])

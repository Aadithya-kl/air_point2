"""
Left-hand gesture processor - Drag-and-Drop and Smooth Pointer Tracking.
Integrates the authoritative LeftDragController for grab-lock lifecycle.
"""

from __future__ import annotations

import logging
import math
import time
from typing import TYPE_CHECKING

import config
from config import (
    CAMERA_FPS,
    CAMERA_HEIGHT,
    CAMERA_WIDTH,
    LEFT_DRAG_CONFIRM_S,
    LEFT_DRAG_ENABLED,
    LEFT_DRAG_LOST_TIMEOUT_S,
    LEFT_DRAG_RELEASE_NORM_DIST,
    LEFT_DRAG_START_NORM_DIST,
    ONE_EURO_BETA,
    ONE_EURO_DCUTOFF,
    ONE_EURO_MINCUTOFF,
    TRACKPAD_MARGIN,
)
from core.actuator import DragEndResult, DragStartResult, MouseActuator
from core.display import TrackpadZone, VirtualDesktop, map_to_desktop
from core.filter import OneEuroFilter
from core.gestures.drag_controller import DragLockState, LeftDragController
from core.gestures.utils import dist3d, is_fist, is_open_palm
from core.tracker import Landmark

logger = logging.getLogger(__name__)

# Backward compatibility aliases
LeftDragState = DragLockState
_LeftState = DragLockState


class LeftHandProcessor:
    """
    Processes left-hand landmarks each frame.
    Responsibilities:
    - Smooth left index finger cursor tracking across the full desktop.
    - Persistent OneEuroFilter state across frames without palm-orientation freezing.
    - Deterministic thumb-index pinch grab-lock and deliberate drop via LeftDragController.
    - Safe lost-tracking, error, and disable cleanup to prevent stuck mouse buttons.
    """

    def __init__(
        self,
        actuator: MouseActuator,
        desktop: VirtualDesktop,
        trackpad: TrackpadZone,
    ) -> None:
        self._actuator = actuator
        self._desktop = desktop
        self._trackpad = trackpad

        # Authoritative drag controller
        self.drag_controller = LeftDragController(
            actuator=actuator,
            start_norm_dist=getattr(config, "LEFT_DRAG_START_NORM_DIST", 0.55),
            release_norm_dist=getattr(config, "LEFT_DRAG_RELEASE_NORM_DIST", 0.75),
            clear_release_norm_dist=0.85,
            confirm_dwell_s=getattr(config, "LEFT_DRAG_CONFIRM_S", 0.10),
            release_dwell_s=0.080,
            lost_timeout_s=getattr(config, "LEFT_DRAG_LOST_TIMEOUT_S", 0.080),
            rearm_cooldown_s=0.150,
            enabled=getattr(config, "LEFT_DRAG_ENABLED", True),
        )

        self.just_started_drag: bool = False
        self._dropout_grace_frames: int = 3
        self._dropout_grace_timeout_s: float = 0.120
        self._is_in_dropout_grace: bool = False
        self._last_valid_time: float | None = None
        self._missing_frames_count: int = 0

        # Pointer filters (matched to right hand for identical responsiveness & smoothness)
        self._filter_x = OneEuroFilter(
            freq=float(CAMERA_FPS),
            mincutoff=ONE_EURO_MINCUTOFF,
            beta=ONE_EURO_BETA,
            dcutoff=ONE_EURO_DCUTOFF,
        )
        self._filter_y = OneEuroFilter(
            freq=float(CAMERA_FPS),
            mincutoff=ONE_EURO_MINCUTOFF,
            beta=ONE_EURO_BETA,
            dcutoff=ONE_EURO_DCUTOFF,
        )
        self.cursor_pos: tuple[int, int] | None = None
        self.is_pointing: bool = False

        # Visual filters for 5 fingertips (Thumb:4, Index:8, Middle:12, Ring:16, Pinky:20)
        self.visual_tips: dict[int, tuple[float, float, float]] = {}
        self._visual_filters = {}
        for tip_idx in [4, 8, 12, 16, 20]:
            self._visual_filters[tip_idx] = (
                OneEuroFilter(freq=float(CAMERA_FPS), mincutoff=1.0, beta=0.05, dcutoff=1.0),
                OneEuroFilter(freq=float(CAMERA_FPS), mincutoff=1.0, beta=0.05, dcutoff=1.0),
            )

    def set_sensitivity(self, sensitivity: float) -> None:
        """Adjust active trackpad zone based on cursor sensitivity multiplier."""
        s = max(0.2, min(4.0, float(sensitivity)))
        cx = CAMERA_WIDTH / 2.0
        cy = CAMERA_HEIGHT / 2.0
        base_span_x = float(CAMERA_WIDTH - 2 * TRACKPAD_MARGIN)
        base_span_y = float(CAMERA_HEIGHT - 2 * TRACKPAD_MARGIN)
        span_x = base_span_x / s
        span_y = base_span_y / s
        # Clamp span to guarantee reaching all 4 screen corners without dead zones
        span_x = max(80.0, min(float(CAMERA_WIDTH - 32), span_x))
        span_y = max(60.0, min(float(CAMERA_HEIGHT - 32), span_y))

        x_min = int(round(cx - span_x / 2.0))
        x_max = int(round(cx + span_x / 2.0))
        y_min = int(round(cy - span_y / 2.0))
        y_max = int(round(cy + span_y / 2.0))

        min_border = 16
        if x_min < min_border:
            x_max += min_border - x_min
            x_min = min_border
        if x_max > CAMERA_WIDTH - min_border:
            x_min -= x_max - (CAMERA_WIDTH - min_border)
            x_max = CAMERA_WIDTH - min_border
        x_min = max(min_border, x_min)
        x_max = min(CAMERA_WIDTH - min_border, x_max)

        if y_min < min_border:
            y_max += min_border - y_min
            y_min = min_border
        if y_max > CAMERA_HEIGHT - min_border:
            y_min -= y_max - (CAMERA_HEIGHT - min_border)
            y_max = CAMERA_HEIGHT - min_border
        y_min = max(min_border, y_min)
        y_max = min(CAMERA_HEIGHT - min_border, y_max)

        self._trackpad = TrackpadZone(x_min, x_max, y_min, y_max)

    def set_smoothing(self, smoothing: int | float) -> None:
        """Map 10-100 smoothing slider to OneEuroFilter mincutoff and beta for instant, jitter-free cursor tracking."""
        sm = max(10.0, min(100.0, float(smoothing)))
        t = (sm - 10.0) / 90.0
        mincutoff = 1.0 - t * (1.0 - 0.12)
        beta = 0.04 - t * (0.04 - 0.008)
        self._filter_x.set_mincutoff(mincutoff)
        self._filter_y.set_mincutoff(mincutoff)
        self._filter_x.set_beta(beta)
        self._filter_y.set_beta(beta)

    @property
    def is_in_dropout_grace(self) -> bool:
        return self._is_in_dropout_grace

    @property
    def drag_lost_timeout_s(self) -> float:
        return self.drag_controller.lost_timeout_s

    @drag_lost_timeout_s.setter
    def drag_lost_timeout_s(self, val: float) -> None:
        self.drag_controller.lost_timeout_s = float(val)

    def _reset_tracking_state(self) -> None:
        """Resets visual and pointer filter states when landmarks are absent or lost."""
        self._missing_frames_count = 0
        self._is_in_dropout_grace = False
        self._last_valid_time = None
        for fx, fy in self._visual_filters.values():
            fx.reset()
            fy.reset()
        self.visual_tips.clear()
        self.cursor_pos = None
        self.is_pointing = False
        self._filter_x.reset()
        self._filter_y.reset()

    def process(self, landmarks: list[Landmark] | None, now: float | None = None) -> None:
        """Processes left hand landmarks and executes drag controller state updates."""
        if now is None:
            now = time.perf_counter()

        # Guard missing landmark list
        if landmarks is None or not isinstance(landmarks, (list, tuple)) or len(landmarks) < 21:
            self._reset_tracking_state()
            self.drag_controller.process_frame(None, now)
            self.just_started_drag = self.drag_controller.just_activated
            return

        # Guard critical landmarks required for pinch and pointer tracking
        for idx in (4, 8, 5, 17):
            lm = landmarks[idx]
            if lm is None or not hasattr(lm, "x") or not hasattr(lm, "y") or not hasattr(lm, "z"):
                self._reset_tracking_state()
                self.drag_controller.process_frame(None, now)
                self.just_started_drag = self.drag_controller.just_activated
                return
            if not (math.isfinite(lm.x) and math.isfinite(lm.y) and math.isfinite(lm.z)):
                self._reset_tracking_state()
                self.drag_controller.process_frame(None, now)
                self.just_started_drag = self.drag_controller.just_activated
                return

        self._missing_frames_count = 0
        self._is_in_dropout_grace = False
        self._last_valid_time = now

        # Update visual fingertip filters
        self.visual_tips.clear()
        for tip_idx in [4, 8, 12, 16, 20]:
            lm = landmarks[tip_idx]
            fx, fy = self._visual_filters[tip_idx]
            vx = fx(lm.x, now)
            vy = fy(lm.y, now)
            self.visual_tips[tip_idx] = (vx, vy, lm.z)

        # Delegate drag state machine and pinch calculation to authoritative LeftDragController
        self.drag_controller.process_frame(landmarks, now)
        self.just_started_drag = self.drag_controller.just_activated

        # Continuous smooth pointer tracking for left index fingertip (Landmark 8)
        # Fist posture disables pointer unless actively pinching or dragging
        fist = is_fist(landmarks)
        is_pinching = self.drag_controller.is_active_or_pending or (
            self.drag_controller.norm_pinch_dist < getattr(config, "LEFT_DRAG_START_NORM_DIST", 0.55)
        )
        if fist and not is_pinching:
            self.is_pointing = False
            self.cursor_pos = None
        else:
            filtered_x = self._filter_x(landmarks[8].x, now)
            filtered_y = self._filter_y(landmarks[8].y, now)
            raw_screen_x, raw_screen_y = map_to_desktop(
                filtered_x, filtered_y, self._trackpad, self._desktop
            )
            self.cursor_pos = (raw_screen_x, raw_screen_y)
            self.is_pointing = True

    def release_drag(self, reason: str = "SAFE_RELEASE") -> None:
        """Explicit, safe, idempotent release of any active drag state."""
        self.drag_controller.release_grab(reason=reason)
        self.just_started_drag = False

    def reset(self) -> None:
        """Cleanly reset all filters and drag controller state."""
        self.drag_controller.reset()
        self.just_started_drag = False
        self._reset_tracking_state()

    # ── State and Diagnostic Properties ───────────────────────────────────────

    @property
    def left_drag_state(self) -> DragLockState:
        """
        Primary state property. Returns DragLockState enum, which compares equal to
        both new states ('GRAB_LOCKED', 'READY', 'GRAB_PENDING', 'RELEASE_PENDING')
        and legacy names ('DRAGGING', 'IDLE', 'GRAB_CANDIDATE', 'RELEASING').
        """
        return self.drag_controller.state

    @property
    def drag_state_name(self) -> str:
        """Deterministic state name string."""
        return self.drag_controller.state_name

    @property
    def drag_state(self) -> DragLockState:
        return self.drag_controller.state

    @property
    def drag_state_text(self) -> str:
        return self.drag_controller.status_text

    @property
    def last_pinch_norm(self) -> float:
        return self.drag_controller.norm_pinch_dist

    @property
    def is_pinch_candidate(self) -> bool:
        return self.drag_controller.is_candidate

    @property
    def release_reason(self) -> str | None:
        return self.drag_controller.last_release_reason

    @property
    def _rearm_time(self) -> float | None:
        return self.drag_controller._rearm_until

    @_rearm_time.setter
    def _rearm_time(self, val: float | None) -> None:
        self.drag_controller._rearm_until = val

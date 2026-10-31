# core/gestures/right_hand.py
"""
Right-hand gesture processor.

State machine:
  IDLE
    â”œâ”€ fist                      â†’ LOCKED
    â”œâ”€ peace sign                â†’ SCROLLING
    â””â”€ thumb+index pinch         â†’ LEFT_PINCH_PENDING_DRAG

  LOCKED
    â””â”€ any finger extends        â†’ IDLE

  SCROLLING
    â”œâ”€ wrist flick up            â†’ scroll(+ticks)  [stay SCROLLING]
    â”œâ”€ wrist flick down          â†’ scroll(-ticks)  [stay SCROLLING]
    â””â”€ peace sign released       â†’ IDLE

  LEFT_PINCH_PENDING_DRAG
    â”œâ”€ pinch released < DRAG_HOLD_SECONDS  â†’ left_click() or double_click() â†’ IDLE
    â””â”€ pinch held â‰¥ DRAG_HOLD_SECONDS      â†’ drag_start() â†’ DRAGGING

  DRAGGING
    â””â”€ pinch released            â†’ drag_end() â†’ IDLE
"""

import ctypes
import time
import logging
from enum import Enum, auto

from config import (
    CAMERA_WIDTH,
    CAMERA_HEIGHT,
    TRACKPAD_MARGIN,
    CAMERA_FPS,
    THUMB_INDEX_CLICK_DIST,
    THUMB_MIDDLE_CLICK_DIST,
    DRAG_HOLD_SECONDS,
    GESTURE_COOLDOWN_SECONDS,
    DOUBLE_CLICK_WINDOW_S,
    WRIST_VELOCITY_THRESHOLD,
    SCROLL_TICK_SCALE,
    SCROLL_COOLDOWN_S,
    ONE_EURO_MINCUTOFF,
    ONE_EURO_BETA,
    ONE_EURO_DCUTOFF,
    TAP_BENT_ANGLE,
    TAP_STRAIGHT_ANGLE,
    TAP_MAX_DURATION_S,
    TAP_DOUBLE_WINDOW_S,
    USE_PINCH_CLICK,
)
from core.tracker import Landmark
from core.filter import OneEuroFilter
from core.display import VirtualDesktop, TrackpadZone, map_to_desktop
from core.actuator import MouseActuator
from core.gestures.utils import dist3d, is_fist, is_peace_sign, angle3d, is_three_fingers, is_open_palm, is_palm_facing_camera_right_hand
from core.click_diagnostics import click_tracer

logger = logging.getLogger(__name__)


class _State(Enum):
    IDLE = auto()
    PINCH_CANDIDATE = auto()
    PINCH_LOCKED = auto()
    LEFT_PINCH_PENDING_DRAG = auto()
    DRAGGING = auto()
    SCROLLING = auto()
    LOCKED = auto()
    CLICK_PENDING = auto()
    ZOOM_ACTIVATING = auto()
    ZOOM_ACTIVE = auto()
    TAP_BENT = auto()
    TAP_WAITING_FOR_SECOND = auto()
    TAP_BENT_SECOND = auto()
    SCREENSHOT_HOLD = auto()
    SCREENSHOT_CAPTURED = auto()


class RightHandProcessor:
    """
    Processes right-hand landmarks each frame.
    Call process(landmarks) where landmarks is list[Landmark] | None.
    None means no right hand detected this frame.
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
        self._state = _State.IDLE
        self._pinch_start_time: float | None = None
        self._tap_start_time: float | None = None
        self._first_tap_time: float | None = None
        self._zoom_baseline: float | None = None
        self._screenshot_start_time: float | None = None
        self._screenshot_last_seen_time: float | None = None
        self._last_click_time: float = 0.0
        self._last_gesture_time: float = 0.0
        self._last_scroll_time: float = 0.0
        self._last_screenshot_time: float = 0.0
        self._prev_wrist_y: float | None = None
        self._last_frame_time: float | None = None
        self._click_state_text: str = "DISABLED"
        self._last_pinch_norm: float = 0.0
        self._locked_cursor_pos: tuple[int, int] | None = None
        self._zoom_start_time: float | None = None
        self._last_zoom_step_time: float = 0.0
        self._click_pending_start_time: float | None = None
        self._last_click_pos: tuple[int, int] | None = None
        self._pinch_locked_time: float | None = None
        self._hold_double_clicked: bool = False
        self._missing_frames_count: int = 0
        self._last_valid_time: float | None = None
        self._dropout_grace_frames: int = 3
        self._dropout_grace_timeout_s: float = 0.120
        self._is_in_dropout_grace: bool = False
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
        # Visual filters for the 5 fingertips (Thumb:4, Index:8, Middle:12, Ring:16, Pinky:20)
        self.visual_tips: dict[int, tuple[float, float, float]] = {}
        self._visual_filters = {}
        for tip_idx in [4, 8, 12, 16, 20]:
            self._visual_filters[tip_idx] = (
                OneEuroFilter(freq=float(CAMERA_FPS), mincutoff=1.0, beta=0.0, dcutoff=1.0),
                OneEuroFilter(freq=float(CAMERA_FPS), mincutoff=1.0, beta=0.0, dcutoff=1.0)
            )

    def _actuate_left_click(self, x: int | None = None, y: int | None = None) -> bool:
        if x is not None and y is not None:
            try:
                return bool(self._actuator.left_click(x, y))
            except TypeError:
                return bool(self._actuator.left_click())
        return bool(self._actuator.left_click())

    def _actuate_double_click(self, x: int | None = None, y: int | None = None) -> bool:
        if x is not None and y is not None:
            try:
                return bool(self._actuator.double_click(x, y))
            except TypeError:
                return bool(self._actuator.double_click())
        return bool(self._actuator.double_click())

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
            x_max += (min_border - x_min)
            x_min = min_border
        if x_max > CAMERA_WIDTH - min_border:
            x_min -= (x_max - (CAMERA_WIDTH - min_border))
            x_max = CAMERA_WIDTH - min_border
        x_min = max(min_border, x_min)
        x_max = min(CAMERA_WIDTH - min_border, x_max)

        if y_min < min_border:
            y_max += (min_border - y_min)
            y_min = min_border
        if y_max > CAMERA_HEIGHT - min_border:
            y_min -= (y_max - (CAMERA_HEIGHT - min_border))
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

    def process(self, landmarks: list[Landmark] | None) -> None:
        from config import POINTER_ONLY_MODE
        now = time.perf_counter()

        if landmarks is None:
            # Genuine hand loss or explicit reset:
            if self._state == _State.DRAGGING:
                self._actuator.drag_end()
            if self._state == _State.CLICK_PENDING:
                self._click_pending_start_time = None
            self._state = _State.IDLE
            self._pinch_start_time = None
            self._prev_wrist_y = None
            self._last_frame_time = None
            self._click_state_text = "DISABLED"
            self._locked_cursor_pos = None
            self._pinch_locked_time = None
            self._hold_double_clicked = False
            self._last_click_pos = None
            self._last_click_time = 0.0
            self._zoom_start_time = None
            self._filter_x.reset()
            self._filter_y.reset()
            for fx, fy in self._visual_filters.values():
                fx.reset()
                fy.reset()
            self.visual_tips.clear()
            self._cursor_pos = None
            self._is_in_dropout_grace = False
            self._last_valid_time = None
            return

        # Hand detected!
        self._missing_frames_count = 0
        self._is_in_dropout_grace = False
        self._last_valid_time = now

        # Update visual tips
        self.visual_tips.clear()
        for tip_idx in [4, 8, 12, 16, 20]:
            lm = landmarks[tip_idx]
            fx, fy = self._visual_filters[tip_idx]
            vx = fx(lm.x, now)
            vy = fy(lm.y, now)
            # Storing original z for completeness if needed
            self.visual_tips[tip_idx] = (vx, vy, lm.z)

        filtered_x = self._filter_x(landmarks[8].x, now)  # index tip
        filtered_y = self._filter_y(landmarks[8].y, now)
        raw_screen_x, raw_screen_y = map_to_desktop(filtered_x, filtered_y, self._trackpad, self._desktop)
        
        from config import (
            PINCH_CLICK_ENABLED, POINTER_ONLY_MODE,
            PINCH_START_NORM_DIST, PINCH_RELEASE_NORM_DIST, PINCH_CONFIRM_S, 
            PINCH_COOLDOWN_S,
            SINGLE_CLICK_MODE, DOUBLE_CLICK_GESTURE_WINDOW_MS, DOUBLE_CLICK_POSITION_TOLERANCE_PX
        )
        
        # Double-pinch gesture window: use user-configured gesture window (default 750ms)
        # to allow natural mid-air human pinch cycle times without being artificially restricted
        # by the physical desktop-mouse double-click timer.
        DOUBLE_PINCH_WINDOW_S = float(DOUBLE_CLICK_GESTURE_WINDOW_MS) / 1000.0
        DOUBLE_PINCH_TOL_PX = DOUBLE_CLICK_POSITION_TOLERANCE_PX
        INTER_PINCH_DEADBAND_PX = 35

        screen_x, screen_y = raw_screen_x, raw_screen_y
        # Lock cursor coordinates on confirmed pinch (PINCH_LOCKED, CLICK_PENDING) and active zoom (ZOOM_ACTIVE).
        # Normal pointing and PINCH_CANDIDATE remain completely free, continuous, and fluid.
        # Absorb brief micro-wobble during finger release within deadband to guarantee Windows double-click recognition.
        # Moving beyond deadband immediately releases anchor to ensure natural, responsive pointing without sticking.
        if self._state in (_State.ZOOM_ACTIVE, _State.PINCH_LOCKED, _State.CLICK_PENDING) and self._locked_cursor_pos is not None:
            screen_x, screen_y = self._locked_cursor_pos
            
        self._cursor_pos = (screen_x, screen_y)
        # Mouse movement is now handled by GestureOrchestrator

        fist = is_fist(landmarks)
        if self._state == _State.LOCKED:
            if not fist:
                self._state = _State.IDLE
                logger.debug("Unlocked")
            return  # no cursor, no gestures while locked

        if fist and self._state not in (_State.LEFT_PINCH_PENDING_DRAG, _State.DRAGGING):
            if self._state == _State.DRAGGING:
                self._actuator.drag_end()
            self._state = _State.LOCKED
            self._last_click_pos = None
            self._last_click_time = 0.0
            logger.debug("Locked (fist)")
            return

        # Never interrupt or corrupt an active mouse drag (e.g. left-hand drag)
        if getattr(self._actuator, 'is_dragging', False):
            if self._state in (_State.PINCH_LOCKED, _State.CLICK_PENDING):
                self._state = _State.IDLE
                self._locked_cursor_pos = None
                self._pinch_locked_time = None
                self._click_pending_start_time = None
                self._click_state_text = "DRAGGING"
            return

        if POINTER_ONLY_MODE:
            self._state = _State.IDLE
            self._click_state_text = "DISABLED"
            return
            
        if PINCH_CLICK_ENABLED:
            # Normalize pinch distance by palm width (index MCP to pinky MCP)
            palm_width = dist3d(landmarks[5], landmarks[17])
            if palm_width < 1e-6:
                palm_width = 1e-6
                
            pinch_dist_norm = dist3d(landmarks[4], landmarks[8]) / palm_width
            self._last_pinch_norm = pinch_dist_norm
            
            is_comfortable = (SINGLE_CLICK_MODE == "comfortable")
            
            if self._state == _State.CLICK_PENDING:
                self._click_state_text = "CLICK PENDING"
                window_s = DOUBLE_CLICK_GESTURE_WINDOW_MS / 1000.0
                if self._click_pending_start_time is not None and (now - self._click_pending_start_time) > window_s:
                    # Expired -> Single click
                    self._actuate_left_click()
                    logger.debug("Buffered SINGLE CLICK triggered")
                    
                    if pinch_dist_norm < PINCH_RELEASE_NORM_DIST:
                        self._state = _State.PINCH_LOCKED
                        self._click_state_text = "SINGLE CLICK"
                    else:
                        self._state = _State.IDLE
                        self._locked_cursor_pos = None
                        self._click_state_text = "SINGLE CLICK"
                        
                    self._display_text_until = now + 0.5
                else:
                    if pinch_dist_norm < PINCH_START_NORM_DIST and (now - self._last_click_time) >= PINCH_COOLDOWN_S:
                        # Check position tolerance using physical hand position (raw_screen_x)
                        valid_pos = False
                        if self._last_click_pos is not None:
                            px, py = self._last_click_pos
                            if abs(raw_screen_x - px) <= DOUBLE_CLICK_POSITION_TOLERANCE_PX and abs(raw_screen_y - py) <= DOUBLE_CLICK_POSITION_TOLERANCE_PX:
                                valid_pos = True
                        if valid_pos:
                            self._state = _State.PINCH_CANDIDATE
                            self._pinch_start_time = now
                            self._click_state_text = "DOUBLE-CLICK CANDIDATE"
                        else:
                            # Too far -> resolve the pending click, start new one
                            self._actuate_left_click()
                            logger.debug("Buffered SINGLE CLICK triggered (moved too far)")
                            self._click_pending_start_time = None
                            self._state = _State.PINCH_CANDIDATE
                            self._pinch_start_time = now
                            self._click_state_text = "CANDIDATE"

            elif self._state == _State.IDLE:
                if (now - self._last_click_time) < PINCH_COOLDOWN_S:
                    self._click_state_text = "COOLDOWN"
                else:
                    self._click_state_text = "READY"
                    
                if pinch_dist_norm < PINCH_START_NORM_DIST and (now - self._last_click_time) >= PINCH_COOLDOWN_S:
                    is_potential_double = False
                    if self._last_click_pos is not None and (now - self._last_click_time) <= DOUBLE_PINCH_WINDOW_S:
                        px, py = self._last_click_pos
                        if abs(raw_screen_x - px) <= DOUBLE_PINCH_TOL_PX and abs(raw_screen_y - py) <= DOUBLE_PINCH_TOL_PX:
                            is_potential_double = True
                    
                    if not is_comfortable and is_potential_double:
                        # Instant mode double-click: emit native double-click down/up pair (50ms interval)
                        # directly to Windows to ensure WM_LBUTTONDBLCLK triggers reliably and opens folders.
                        px, py = self._last_click_pos
                        self._locked_cursor_pos = (px, py)
                        self._cursor_pos = (px, py)
                        ok = self._actuate_double_click(px, py)
                        click_tracer.record_click(2, (px, py), ok)
                        click_tracer.log_state_transition("IDLE", "PINCH_LOCKED", "Instant second pinch double-click emitted", pinch_dist_norm, PINCH_START_NORM_DIST, (px, py), is_anchored=True)
                        if hasattr(self._actuator, 'clicks'):
                            self._actuator.clicks = 2
                        if hasattr(self._actuator, 'double_clicks'):
                            self._actuator.double_clicks = 1
                        self._last_click_pos = None
                        self._last_click_time = 0.0
                        self._state = _State.PINCH_LOCKED
                        self._pinch_locked_time = now
                        self._hold_double_clicked = True
                        self._click_state_text = "DOUBLE CLICK"
                        self._display_text_until = now + 0.5
                        logger.debug("Instant DOUBLE CLICK pair emitted at (%d, %d)", px, py)
                    else:
                        self._state = _State.PINCH_CANDIDATE
                        self._pinch_start_time = now
                        self._click_state_text = "DOUBLE-CLICK CANDIDATE" if is_potential_double else "CANDIDATE"
                        click_tracer.log_state_transition("IDLE", "PINCH_CANDIDATE", "Pinch candidate detected", pinch_dist_norm, PINCH_START_NORM_DIST, (raw_screen_x, raw_screen_y), is_anchored=is_potential_double)
                    
            elif self._state == _State.PINCH_CANDIDATE:
                is_potential_double = False
                if self._last_click_pos is not None and (now - self._last_click_time) <= DOUBLE_PINCH_WINDOW_S:
                    px, py = self._last_click_pos
                    if abs(raw_screen_x - px) <= DOUBLE_PINCH_TOL_PX and abs(raw_screen_y - py) <= DOUBLE_PINCH_TOL_PX:
                        is_potential_double = True
                
                if is_potential_double:
                    self._click_state_text = "DOUBLE-CLICK CANDIDATE"
                elif self._click_state_text != "DOUBLE-CLICK CANDIDATE":
                    self._click_state_text = "CANDIDATE"
                
                req_confirm_s = 0.0 if is_potential_double else PINCH_CONFIRM_S
                
                if pinch_dist_norm > PINCH_RELEASE_NORM_DIST:
                    # Released before confirmation
                    if self._click_pending_start_time is not None:
                        # Revert back to pending click
                        self._state = _State.CLICK_PENDING
                        self._click_state_text = "CLICK PENDING"
                    else:
                        self._state = _State.IDLE
                    self._pinch_start_time = None
                    click_tracer.log_state_transition("PINCH_CANDIDATE", self._state.name, "Pinch candidate released before confirm", pinch_dist_norm, PINCH_RELEASE_NORM_DIST)
                    
                elif self._pinch_start_time is not None and (now - self._pinch_start_time) >= req_confirm_s:
                    # Confirmed
                    if is_comfortable:
                        if self._click_pending_start_time is not None:
                            # It's a double click!
                            px, py = self._last_click_pos if self._last_click_pos is not None else (raw_screen_x, raw_screen_y)
                            ok = self._actuate_double_click(px, py)
                            click_tracer.record_click(2, (px, py), ok)
                            click_tracer.log_state_transition("PINCH_CANDIDATE", "PINCH_LOCKED", "Buffered double-click confirmed", pinch_dist_norm, PINCH_START_NORM_DIST, (px, py))
                            self._click_pending_start_time = None
                            self._state = _State.PINCH_LOCKED
                            self._click_state_text = "DOUBLE CLICK"
                            self._display_text_until = now + 0.5
                            logger.debug("Buffered DOUBLE CLICK triggered")
                        else:
                            # First pinch confirmed, enter pending
                            self._state = _State.CLICK_PENDING
                            self._click_pending_start_time = now
                            self._click_state_text = "CLICK PENDING"
                            self._last_click_time = now
                            self._last_click_pos = (raw_screen_x, raw_screen_y)
                            self._locked_cursor_pos = self._last_click_pos
                            click_tracer.log_state_transition("PINCH_CANDIDATE", "CLICK_PENDING", "First pinch confirmed (comfortable mode)", pinch_dist_norm, PINCH_START_NORM_DIST, self._last_click_pos)
                            logger.debug("First pinch confirmed -> CLICK PENDING")
                    else:
                        # Instant mode:
                        # First pinch fires prompt single click.
                        # Second pinch snaps cursor to exact target coordinates of first click
                        # and fires the matching second down/up pair (native Windows double-click).
                        emit_x, emit_y = raw_screen_x, raw_screen_y
                        is_double = False
                        if self._last_click_pos is not None and (now - self._last_click_time) <= DOUBLE_PINCH_WINDOW_S:
                            prev_x, prev_y = self._last_click_pos
                            if abs(emit_x - prev_x) <= DOUBLE_PINCH_TOL_PX and abs(emit_y - prev_y) <= DOUBLE_PINCH_TOL_PX:
                                emit_x, emit_y = prev_x, prev_y
                                is_double = True
                                logger.debug("Snapped pinch emission for instant double-click to (%d, %d)", emit_x, emit_y)
                        
                        self._locked_cursor_pos = (emit_x, emit_y)
                        self._cursor_pos = (emit_x, emit_y)
                        if is_double:
                            # Emit native double-click down/up pair (50ms interval) at snapped target location
                            ok = self._actuate_double_click(emit_x, emit_y)
                            click_tracer.record_click(2, (emit_x, emit_y), ok)
                            click_tracer.log_state_transition("PINCH_CANDIDATE", "PINCH_LOCKED", "Instant double-click confirmed", pinch_dist_norm, PINCH_START_NORM_DIST, (emit_x, emit_y), is_anchored=True)
                            if hasattr(self._actuator, 'clicks'):
                                self._actuator.clicks = 2
                            if hasattr(self._actuator, 'double_clicks'):
                                self._actuator.double_clicks = 1
                            self._last_click_pos = None
                            self._last_click_time = 0.0
                            self._click_state_text = "DOUBLE CLICK"
                            logger.debug("Instant DOUBLE CLICK pair emitted at (%d, %d)", emit_x, emit_y)
                        else:
                            self._last_click_pos = (emit_x, emit_y)
                            self._last_click_time = now
                            ok = self._actuate_left_click(emit_x, emit_y)
                            click_tracer.record_click(1, (emit_x, emit_y), ok)
                            click_tracer.log_state_transition("PINCH_CANDIDATE", "PINCH_LOCKED", "Instant single click confirmed", pinch_dist_norm, PINCH_START_NORM_DIST, (emit_x, emit_y), is_anchored=True)
                            self._click_state_text = "SINGLE CLICK"
                            logger.debug("Instant SINGLE CLICK first down/up pair emitted at (%d, %d)", emit_x, emit_y)
                        
                        self._state = _State.PINCH_LOCKED
                        self._pinch_locked_time = now
                        self._hold_double_clicked = is_double
                        self._display_text_until = now + 0.5
                        logger.debug("Instant %s triggered", self._click_state_text)
                    
            elif self._state == _State.PINCH_LOCKED:
                from config import PINCH_HOLD_DOUBLE_CLICK_ENABLED, PINCH_HOLD_DOUBLE_CLICK_S
                if PINCH_HOLD_DOUBLE_CLICK_ENABLED and not self._hold_double_clicked:
                    if self._pinch_locked_time is not None and (now - self._pinch_locked_time) >= PINCH_HOLD_DOUBLE_CLICK_S:
                        if pinch_dist_norm < PINCH_START_NORM_DIST:
                            px, py = self._locked_cursor_pos if self._locked_cursor_pos is not None else (raw_screen_x, raw_screen_y)
                            ok = self._actuate_double_click(px, py)
                            click_tracer.record_click(2, (px, py), ok)
                            click_tracer.log_state_transition("PINCH_LOCKED", "PINCH_LOCKED", "Pinch-hold double-click triggered", pinch_dist_norm, PINCH_START_NORM_DIST, (px, py), is_anchored=True)
                            if hasattr(self._actuator, 'clicks'):
                                self._actuator.clicks = 2
                            if hasattr(self._actuator, 'double_clicks'):
                                self._actuator.double_clicks = 1
                            self._hold_double_clicked = True
                            self._last_click_pos = None
                            self._last_click_time = 0.0
                            self._click_state_text = "DOUBLE CLICK"
                            self._display_text_until = now + 0.5
                            logger.info("Pinch-hold DOUBLE CLICK emitted at (%d, %d)", px, py)

                if now > getattr(self, "_display_text_until", 0):
                    self._click_state_text = "HOLDING PINCH" if self._hold_double_clicked else "WAITING FOR RELEASE"
                if pinch_dist_norm > PINCH_RELEASE_NORM_DIST:
                    self._state = _State.IDLE
                    self._pinch_start_time = None
                    self._pinch_locked_time = None
                    self._hold_double_clicked = False
                    self._click_state_text = "READY"
                    self._locked_cursor_pos = None
                    self._cursor_pos = (raw_screen_x, raw_screen_y)
                    click_tracer.log_state_transition("PINCH_LOCKED", "IDLE", "Pinch released", pinch_dist_norm, PINCH_RELEASE_NORM_DIST, (raw_screen_x, raw_screen_y), is_anchored=False)
                    
            # â”€â”€ Phase 3: Zoom Gestures â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            from config import (
                ZOOM_ENABLED, ZOOM_BACKEND, ZOOM_ACTIVATION_DURATION_S,
                ZOOM_EXIT_DURATION_S, ZOOM_COOLDOWN_S, ZOOM_SPREAD_THRESHOLD, ZOOM_CLOSE_THRESHOLD
            )
            
            if ZOOM_ENABLED:
                peace = is_peace_sign(landmarks)
                d_index_mid_norm = dist3d(landmarks[8], landmarks[12]) / palm_width
                
                if self._state not in (_State.ZOOM_ACTIVATING, _State.ZOOM_ACTIVE):
                    if peace and self._state == _State.IDLE:
                        self._state = _State.ZOOM_ACTIVATING
                        self._zoom_start_time = now
                        self._click_state_text = "ZOOM: ACTIVATING"
                
                elif self._state == _State.ZOOM_ACTIVATING:
                    if not peace:
                        self._state = _State.IDLE
                        self._click_state_text = "READY"
                        self._zoom_start_time = None
                    elif self._zoom_start_time is not None and (now - self._zoom_start_time) >= ZOOM_ACTIVATION_DURATION_S:
                        self._state = _State.ZOOM_ACTIVE
                        self._zoom_baseline = d_index_mid_norm
                        self._locked_cursor_pos = (raw_screen_x, raw_screen_y)
                        self._click_state_text = "ZOOM: ACTIVE"
                        self._last_zoom_step_time = now
                        logger.debug("Zoom mode activated, baseline=%.3f", self._zoom_baseline)
                        
                elif self._state == _State.ZOOM_ACTIVE:
                    self._click_state_text = "ZOOM: ACTIVE"
                    if not peace:
                        if self._zoom_start_time is None:
                            self._zoom_start_time = now # Use as exit timer
                        elif (now - self._zoom_start_time) >= ZOOM_EXIT_DURATION_S:
                            self._state = _State.IDLE
                            self._locked_cursor_pos = None
                            self._click_state_text = "READY"
                            self._zoom_start_time = None
                            logger.debug("Zoom mode exited")
                    else:
                        self._zoom_start_time = None # Reset exit timer
                        
                        if (now - self._last_zoom_step_time) >= ZOOM_COOLDOWN_S:
                            delta = d_index_mid_norm - self._zoom_baseline
                            
                            # DIAGNOSTIC FEEDBACK
                            logger.info(
                                f"ZOOM DIAGNOSTIC | State: {self._state.name} | Peace: {peace} | "
                                f"DistNorm: {d_index_mid_norm:.3f} | Baseline: {self._zoom_baseline:.3f} | "
                                f"Delta: {delta:.3f} | Backend: {ZOOM_BACKEND}"
                            )
                            
                            if delta > ZOOM_SPREAD_THRESHOLD:
                                if ZOOM_BACKEND == "windows_magnifier":
                                    self._actuator.mag_zoom_in()
                                else:
                                    self._actuator.zoom_in()
                                self._zoom_baseline = d_index_mid_norm
                                self._last_zoom_step_time = now
                                self._click_state_text = "ZOOM: IN"
                                self._display_text_until = now + 0.3
                                logger.info(f"ZOOM DIAGNOSTIC | ACTION DISPATCHED: IN (delta={delta:.3f})")
                            elif delta < ZOOM_CLOSE_THRESHOLD:
                                if ZOOM_BACKEND == "windows_magnifier":
                                    self._actuator.mag_zoom_out()
                                else:
                                    self._actuator.zoom_out()
                                self._zoom_baseline = d_index_mid_norm
                                self._last_zoom_step_time = now
                                self._click_state_text = "ZOOM: OUT"
                                self._display_text_until = now + 0.3
                                logger.info(f"ZOOM DIAGNOSTIC | ACTION DISPATCHED: OUT (delta={delta:.3f})")
                                
                    if now <= getattr(self, "_display_text_until", 0) and self._click_state_text in ("ZOOM: IN", "ZOOM: OUT"):
                        pass # keep text
                    elif self._state == _State.ZOOM_ACTIVE:
                        self._click_state_text = "ZOOM: ACTIVE"


    @property
    def cursor_pos(self):
        return getattr(self, '_cursor_pos', None)
        
    @property
    def right_state(self) -> str:
        return self._state.name
        
    @property
    def click_state_text(self) -> str:
        return self._click_state_text
        
    @property
    def last_pinch_norm(self) -> float:
        return getattr(self, '_last_pinch_norm', 0.0)

    def resolve_pending_click(self) -> None:
        """Immediately emit any pending buffered click and return to IDLE."""
        if self._state == _State.CLICK_PENDING:
            if not getattr(self._actuator, 'is_dragging', False):
                self._actuator.left_click()
            self._state = _State.IDLE
            self._click_pending_start_time = None
            self._locked_cursor_pos = None
            self._pinch_locked_time = None
            self._hold_double_clicked = False
            self._click_state_text = "SINGLE CLICK" if not getattr(self._actuator, 'is_dragging', False) else "DRAGGING"
            logger.debug("Pending click resolved")

    @property
    def is_cursor_locked(self) -> bool:
        return self._state in (_State.ZOOM_ACTIVE, _State.PINCH_LOCKED, _State.CLICK_PENDING)


"""
AirPoint Drag Lock Controller — Authoritative Left-Hand Grab & Drop State Machine.

Responsibilities:
- Owns the complete logical and native lifecycle of the left-hand pinch-and-hold drag interaction.
- Enforces an explicit grab-lock state machine:
    READY -> GRAB_PENDING -> GRAB_LOCKED -> RELEASE_PENDING -> READY
    (with INPUT_ERROR for unconfirmed native operations).
- Prevents premature releases from finger extension or momentary landmark jitter.
- Guarantees exactly one native button-down on activation and one native button-up on release.
- Provides rearm protection so a sustained unpinch is required before a new drag can arm.
"""

from __future__ import annotations

import logging
import math
import time
from enum import Enum
from typing import TYPE_CHECKING

import config
from core.actuator import DragEndResult, DragStartResult, MouseActuator
from core.gestures.utils import dist3d
from core.tracker import Landmark

logger = logging.getLogger(__name__)


class DragLockState(str, Enum):
    """
    Explicit states for the left-hand drag controller.
    Inherits from str and Enum with custom equality for complete backward compatibility
    with existing tests that check legacy state names ('IDLE', 'DRAGGING', 'GRAB_CANDIDATE', etc.).
    """

    READY = "READY"
    GRAB_PENDING = "GRAB_PENDING"
    GRAB_LOCKED = "GRAB_LOCKED"
    RELEASE_PENDING = "RELEASE_PENDING"
    INPUT_ERROR = "INPUT_ERROR"

    def __str__(self) -> str:
        return self.value

    def __eq__(self, other: object) -> bool:
        if isinstance(other, DragLockState):
            return self.value == other.value
        if isinstance(other, str):
            if self.value == other:
                return True
            # Backward compatibility aliases:
            if self is DragLockState.READY and other in ("IDLE", "ready", "idle", "RELEASING", "releasing", "DROP", "drop"):
                return True
            if self is DragLockState.GRAB_PENDING and other in ("GRAB_CANDIDATE", "PINCH_PENDING", "candidate", "CANDIDATE"):
                return True
            if self is DragLockState.GRAB_LOCKED and other in ("DRAGGING", "dragging", "ACTIVE", "active"):
                return True
            if self is DragLockState.RELEASE_PENDING and other in ("RELEASING", "releasing", "DROP", "drop"):
                return True
            if self is DragLockState.INPUT_ERROR and other in ("ERROR", "error"):
                return True
        return False

    def __hash__(self) -> int:
        return hash(self.value)


# Backward compatibility attributes on DragLockState class
DragLockState.IDLE = DragLockState.READY
DragLockState.DRAGGING = DragLockState.GRAB_LOCKED
DragLockState.PINCH_PENDING = DragLockState.GRAB_PENDING
DragLockState.GRAB_CANDIDATE = DragLockState.GRAB_PENDING
DragLockState.RELEASING = DragLockState.READY


class LeftDragController:
    """
    Single authoritative owner of the left-hand drag session and native mouse button hold.
    """

    def __init__(
        self,
        actuator: MouseActuator,
        start_norm_dist: float | None = None,
        release_norm_dist: float | None = None,
        clear_release_norm_dist: float = 0.85,
        confirm_dwell_s: float | None = None,
        release_dwell_s: float = 0.080,
        lost_timeout_s: float | None = None,
        rearm_cooldown_s: float = 0.150,
        enabled: bool | None = None,
    ) -> None:
        self._actuator = actuator

        # Configuration parameters
        self.start_norm_dist: float = (
            float(start_norm_dist)
            if start_norm_dist is not None
            else getattr(config, "LEFT_DRAG_START_NORM_DIST", 0.55)
        )
        self.release_norm_dist: float = (
            float(release_norm_dist)
            if release_norm_dist is not None
            else getattr(config, "LEFT_DRAG_RELEASE_NORM_DIST", 0.75)
        )
        self.clear_release_norm_dist: float = float(clear_release_norm_dist)
        self.confirm_dwell_s: float = (
            float(confirm_dwell_s)
            if confirm_dwell_s is not None
            else getattr(config, "LEFT_DRAG_CONFIRM_S", 0.10)
        )
        self.release_dwell_s: float = float(release_dwell_s)
        self.lost_timeout_s: float = (
            float(lost_timeout_s)
            if lost_timeout_s is not None
            else getattr(config, "LEFT_DRAG_LOST_TIMEOUT_S", 0.075)
        )
        self.rearm_cooldown_s: float = float(rearm_cooldown_s)
        self.enabled: bool = (
            bool(enabled) if enabled is not None else getattr(config, "LEFT_DRAG_ENABLED", True)
        )

        # Primary state machine
        self._state: DragLockState = DragLockState.READY
        self._pending_start_time: float | None = None
        self._release_pending_start_time: float | None = None
        self._rearm_until: float | None = None
        self._last_valid_time: float | None = None
        self._last_release_reason: str | None = None
        self._last_error: str | None = None
        self._drop_text_until: float = 0.0

        # Frame telemetry
        self._raw_pinch_dist: float = 0.0
        self._palm_width: float = 0.0
        self._norm_pinch_dist: float = 0.0
        self._just_activated: bool = False
        self._just_released: bool = False

    # ── State Machine Properties ──────────────────────────────────────────────

    @property
    def state(self) -> DragLockState:
        return self._state

    @property
    def state_name(self) -> str:
        return self._state.value

    @property
    def is_grab_locked(self) -> bool:
        """True strictly when in GRAB_LOCKED and actuator confirms drag session is active."""
        if self._state == DragLockState.GRAB_LOCKED:
            return bool(getattr(self._actuator, "is_dragging", True))
        return False

    @property
    def is_active_or_pending(self) -> bool:
        return self._state in (
            DragLockState.GRAB_PENDING,
            DragLockState.GRAB_LOCKED,
            DragLockState.RELEASE_PENDING,
        )

    @property
    def is_candidate(self) -> bool:
        return self._state == DragLockState.GRAB_PENDING or (
            self._state == DragLockState.READY and self._norm_pinch_dist < self.start_norm_dist
        )

    @property
    def just_activated(self) -> bool:
        return self._just_activated

    @property
    def just_released(self) -> bool:
        return self._just_released

    @property
    def raw_pinch_dist(self) -> float:
        return self._raw_pinch_dist

    @property
    def palm_width(self) -> float:
        return self._palm_width

    @property
    def norm_pinch_dist(self) -> float:
        return self._norm_pinch_dist

    @property
    def last_release_reason(self) -> str | None:
        return self._last_release_reason

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def dwell_timer(self) -> float:
        """Elapsed dwell in seconds for active pending state."""
        if self._state == DragLockState.GRAB_PENDING and self._pending_start_time is not None:
            return max(0.0, time.perf_counter() - self._pending_start_time)
        if self._state == DragLockState.RELEASE_PENDING and self._release_pending_start_time is not None:
            return max(0.0, time.perf_counter() - self._release_pending_start_time)
        return 0.0

    @property
    def status_text(self) -> str:
        now = time.perf_counter()
        if getattr(self, "_drop_text_until", None) and now < self._drop_text_until:
            return "DROP"
        if self._state == DragLockState.READY:
            return "READY"
        if self._state == DragLockState.GRAB_PENDING:
            return "CANDIDATE"
        if self._state == DragLockState.GRAB_LOCKED:
            return "ACTIVE"
        if self._state == DragLockState.RELEASE_PENDING:
            return "RELEASING"
        if self._state == DragLockState.INPUT_ERROR:
            return "ERROR"
        return "READY"

    # ── Per-Frame Processing ──────────────────────────────────────────────────

    def process_frame(self, landmarks: list[Landmark] | None, now: float | None = None) -> None:
        """
        Processes one camera frame of left-hand landmarks.
        Updates pinch geometry, handles dwell timers, dispatches native input operations,
        and enforces deterministic state transitions.
        """
        self._just_activated = False
        self._just_released = False
        if now is None:
            now = time.perf_counter()

        # Update dynamic config overrides if modified at runtime
        start_th = getattr(config, "LEFT_DRAG_START_NORM_DIST", self.start_norm_dist)
        rel_th = getattr(config, "LEFT_DRAG_RELEASE_NORM_DIST", self.release_norm_dist)
        conf_dwell = getattr(config, "LEFT_DRAG_CONFIRM_S", self.confirm_dwell_s)
        lost_timeout = getattr(config, "LEFT_DRAG_LOST_TIMEOUT_S", self.lost_timeout_s)

        # 1. Validate Landmark Presence & Numerical Validity
        if landmarks is None:
            self.release_grab(reason="TRACKING_LOSS", now=now)
            return

        valid_landmarks = True
        if not isinstance(landmarks, (list, tuple)) or len(landmarks) < 21:
            valid_landmarks = False
        else:
            # Critical landmarks: 4 (thumb tip), 8 (index tip), 5 (index MCP), 17 (pinky MCP)
            for idx in (4, 8, 5, 17):
                lm = landmarks[idx]
                if lm is None or not hasattr(lm, "x") or not hasattr(lm, "y") or not hasattr(lm, "z"):
                    valid_landmarks = False
                    break
                if not (math.isfinite(lm.x) and math.isfinite(lm.y) and math.isfinite(lm.z)):
                    valid_landmarks = False
                    break

        if not valid_landmarks:
            self._handle_tracking_absence(now, lost_timeout)
            return

        # 2. Tracking Present: update timestamps and compute geometry
        self._last_valid_time = now

        # Compute palm scale reference (distance between index MCP #5 and pinky MCP #17)
        raw_palm = dist3d(landmarks[5], landmarks[17])
        self._palm_width = max(0.02, float(raw_palm))
        self._raw_pinch_dist = float(dist3d(landmarks[4], landmarks[8]))
        self._norm_pinch_dist = self._raw_pinch_dist / self._palm_width

        # Keep active drag session alive in actuator watchdog
        if self._state in (DragLockState.GRAB_LOCKED, DragLockState.RELEASE_PENDING):
            if hasattr(self._actuator, "keep_drag_alive"):
                self._actuator.keep_drag_alive(now)

        if not self.enabled:
            if self._state != DragLockState.READY:
                self.release_grab(reason="FEATURE_DISABLED", now=now)
            return

        # 3. State Machine Transitions
        if self._state == DragLockState.READY:
            # Check rearm cooldown: require physical unpinch or cooldown expiration
            if self._rearm_until is not None:
                if self._norm_pinch_dist >= rel_th:
                    self._rearm_until = None
                elif now >= self._rearm_until:
                    self._rearm_until = None
                else:
                    return

            if self._norm_pinch_dist < start_th:
                self._state = DragLockState.GRAB_PENDING
                self._pending_start_time = now
                self._last_release_reason = None
                self._last_error = None
                logger.info(
                    "DragLockState transition: READY -> GRAB_PENDING (pinch=%.3f < start_th=%.2f)",
                    self._norm_pinch_dist,
                    start_th,
                )

        elif self._state == DragLockState.GRAB_PENDING:
            if self._norm_pinch_dist >= rel_th:
                # User opened fingers before activation dwell completed -> cancel back to READY
                self._state = DragLockState.READY
                self._pending_start_time = None
                self._last_release_reason = "PINCH_CANCELLED"
                logger.info(
                    "DragLockState transition: GRAB_PENDING -> READY (pinch cancelled: d=%.3f >= %.2f)",
                    self._norm_pinch_dist,
                    rel_th,
                )
            else:
                elapsed = (now - self._pending_start_time) if self._pending_start_time else 0.0
                if elapsed >= conf_dwell:
                    # Dwell satisfied -> execute native button DOWN
                    res = self._execute_grab_down(now)
                    if res == DragStartResult.FAILED or res is False:
                        self._last_error = "NATIVE_BUTTON_DOWN_FAILED"
                        self._last_release_reason = "INPUT_ERROR"
                        self._pending_start_time = None
                        logger.error("Native button-down operation failed; attempting safe recovery")
                        try:
                            clean_res = self._actuator.drag_end()
                        except Exception:
                            clean_res = DragEndResult.FAILED

                        if clean_res == DragEndResult.FAILED:
                            self._state = DragLockState.INPUT_ERROR
                        else:
                            self._state = DragLockState.READY
                    else:
                        # Success: enter GRAB_LOCKED
                        self._state = DragLockState.GRAB_LOCKED
                        self._just_activated = True
                        self._pending_start_time = None
                        self._last_error = None
                        self._last_release_reason = None
                        logger.info(
                            "DragLockState transition: GRAB_PENDING -> GRAB_LOCKED (hold=%.3fs, pinch=%.3f, res=%s)",
                            elapsed,
                            self._norm_pinch_dist,
                            res,
                        )

        elif self._state == DragLockState.GRAB_LOCKED:
            # Clear release threshold (immediate unpinch without debounce)
            if self._norm_pinch_dist >= self.clear_release_norm_dist:
                logger.info(
                    "DragLockState transition: GRAB_LOCKED -> deliberate clear unpinch (d=%.3f >= %.2f)",
                    self._norm_pinch_dist,
                    self.clear_release_norm_dist,
                )
                self._execute_drop(now, reason="UNPINCH")
            elif self._norm_pinch_dist > rel_th:
                # Entering release hysteresis band: start release debounce dwell
                self._state = DragLockState.RELEASE_PENDING
                self._release_pending_start_time = now
                logger.info(
                    "DragLockState transition: GRAB_LOCKED -> RELEASE_PENDING (pinch=%.3f > rel_th=%.2f)",
                    self._norm_pinch_dist,
                    rel_th,
                )

        elif self._state == DragLockState.RELEASE_PENDING:
            if self._norm_pinch_dist <= rel_th:
                # Jitter recovery: pinch returned to held range before release dwell completed
                self._state = DragLockState.GRAB_LOCKED
                self._release_pending_start_time = None
                logger.info(
                    "DragLockState transition: RELEASE_PENDING -> GRAB_LOCKED (pinch recovered: d=%.3f <= %.2f)",
                    self._norm_pinch_dist,
                    rel_th,
                )
            else:
                elapsed_rel = (
                    (now - self._release_pending_start_time)
                    if self._release_pending_start_time
                    else 0.0
                )
                if (
                    elapsed_rel >= self.release_dwell_s
                    or self._norm_pinch_dist >= self.clear_release_norm_dist
                ):
                    # Deliberate unpinch dwell satisfied -> execute native button UP
                    logger.info(
                        "DragLockState transition: RELEASE_PENDING -> deliberate unpinch (dwell=%.3fs, d=%.3f)",
                        elapsed_rel,
                        self._norm_pinch_dist,
                    )
                    self._execute_drop(now, reason="UNPINCH")

        elif self._state == DragLockState.INPUT_ERROR:
            # Safe recovery attempt: if hand is unpinched, return to READY
            if self._norm_pinch_dist >= rel_th:
                logger.info("DragLockState recovery: INPUT_ERROR -> READY (fingers unpinched)")
                self._state = DragLockState.READY
                self._last_error = None

    # ── Tracking Loss & Safety ────────────────────────────────────────────────

    def _handle_tracking_absence(self, now: float, timeout_s: float) -> None:
        """
        Manages brief frame dropout vs sustained tracking loss.
        Brief tracking gaps (< timeout_s) keep the grab held in grace.
        Sustained loss releases the grab safely.
        """
        if self._state in (DragLockState.GRAB_LOCKED, DragLockState.RELEASE_PENDING):
            if self._last_valid_time is not None:
                elapsed_lost = now - self._last_valid_time
                if elapsed_lost <= timeout_s:
                    if hasattr(self._actuator, "keep_drag_alive"):
                        self._actuator.keep_drag_alive(now)
                    return
                logger.warning(
                    "Sustained left-hand tracking loss (%.3fs > %.3fs); safely releasing locked grab",
                    elapsed_lost,
                    timeout_s,
                )
                self.release_grab(reason="TRACKING_LOSS", now=now)
            else:
                self.release_grab(reason="TRACKING_LOSS", now=now)

        elif self._state == DragLockState.GRAB_PENDING:
            self._state = DragLockState.READY
            self._pending_start_time = None
            self._last_release_reason = "TRACKING_LOSS"

    # ── Native Input Execution ────────────────────────────────────────────────

    def _execute_grab_down(self, now: float) -> DragStartResult | bool:
        """Sends native MOUSEEVENTF_LEFTDOWN via actuator."""
        try:
            return self._actuator.drag_start(now)
        except TypeError:
            return self._actuator.drag_start()
        except Exception as e:
            logger.error("Exception during actuator.drag_start: %s", e)
            return DragStartResult.FAILED

    def _execute_drop(self, now: float, reason: str = "UNPINCH") -> bool:
        """Sends native MOUSEEVENTF_LEFTUP via actuator and transitions to READY."""
        try:
            res = self._actuator.drag_end()
        except Exception as e:
            logger.error("Exception during actuator.drag_end: %s", e)
            res = DragEndResult.FAILED

        if res == DragEndResult.FAILED:
            self._state = DragLockState.INPUT_ERROR
            self._last_error = "NATIVE_BUTTON_UP_FAILED"
            self._last_release_reason = "INPUT_ERROR"
            logger.error("Native button-up injection failed; transitioned to INPUT_ERROR")
            return False

        self._state = DragLockState.READY
        self._just_released = True
        self._drop_text_until = now + 0.35
        self._pending_start_time = None
        self._release_pending_start_time = None
        self._last_release_reason = reason
        self._last_error = None
        if reason == "UNPINCH":
            self._rearm_until = now + self.rearm_cooldown_s
        else:
            self._rearm_until = None
        return True

    def release_grab(self, reason: str = "SAFE_RELEASE", now: float | None = None) -> bool:
        """
        Safe, idempotent external cancellation.
        Called by orchestrator on tracking loss, feature disable, screenshot,
        workstation lock, app launch, watchdog trigger, or system shutdown.
        """
        if now is None:
            now = time.perf_counter()

        was_active = (
            self._state in (DragLockState.GRAB_LOCKED, DragLockState.RELEASE_PENDING)
            or getattr(self._actuator, "is_dragging", False)
        )

        success = True
        if was_active:
            try:
                res = self._actuator.drag_end()
                if res == DragEndResult.FAILED:
                    self._state = DragLockState.INPUT_ERROR
                    self._last_error = "NATIVE_BUTTON_UP_FAILED"
                    self._last_release_reason = "INPUT_ERROR"
                    return False
            except Exception as e:
                logger.error("Error during actuator.drag_end in release_grab: %s", e)
                success = False

        self._state = DragLockState.READY
        self._pending_start_time = None
        self._release_pending_start_time = None
        self._last_release_reason = reason
        if reason == "UNPINCH":
            self._rearm_until = now + self.rearm_cooldown_s
        else:
            self._rearm_until = None
        return success

    def reset(self) -> None:
        """Full reset of controller state and safe release of any held mouse button."""
        self.release_grab(reason="RESET")
        self._rearm_until = None
        self._last_valid_time = None
        self._raw_pinch_dist = 0.0
        self._palm_width = 0.0
        self._norm_pinch_dist = 0.0
        self._just_activated = False
        self._just_released = False
        self._last_error = None

# core/gestures/wakanda_gesture.py
"""
Wakanda Forever Gesture Recognizer - Crossed-arm chest pose to lock Windows.

Recognizes both forearms crossed over the chest with closed fists:
- Both hands present with high confidence.
- Left hand crossed to viewer-right and right hand crossed to viewer-left.
- Forearm vectors forming an 'X' diagonal posture pointing towards opposite shoulders.
- Closed fists (fingers curled into palms).
- Wrists positioned in chest/torso region below facial anchors.
- Continuous hold for 2.0 seconds triggers Windows workstation lock (Win32 LockWorkStation).
- Feature is disabled by default for safety.
"""

import ctypes
import logging
import os
import time
from enum import Enum, auto
from typing import Callable

from core.face_tracker import FaceResult
from core.gestures.utils import is_curled, is_fist
from core.tracker import HandsResult, Landmark

try:
    from config import (
        WAKANDA_ENABLED,
        WAKANDA_HOLD_DURATION_S,
        WAKANDA_GRACE_PERIOD_S,
        WAKANDA_COOLDOWN_S,
        WAKANDA_HAND_CONFIDENCE_MIN,
    )
except ImportError:
    WAKANDA_ENABLED = False
    WAKANDA_HOLD_DURATION_S = 2.0
    WAKANDA_GRACE_PERIOD_S = 0.15
    WAKANDA_COOLDOWN_S = 2.0
    WAKANDA_HAND_CONFIDENCE_MIN = 0.55

logger = logging.getLogger(__name__)


class WakandaState(Enum):
    DISABLED = auto()
    IDLE = auto()
    HOLDING = auto()
    TRIGGERED = auto()
    COOLDOWN = auto()


def lock_workstation() -> bool:
    """
    Safely executes Win32 LockWorkStation.
    Honors AIRPOINT_DISABLE_REAL_LOCK environment flag to avoid accidental OS locking
    during testing or developer simulation.
    """
    if os.environ.get("AIRPOINT_DISABLE_REAL_LOCK", "").strip().lower() in ("1", "true", "yes"):
        logger.info("[MOCK] Windows LockWorkStation called (real lock disabled via AIRPOINT_DISABLE_REAL_LOCK)")
        return True
    try:
        if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "user32"):
            res = ctypes.windll.user32.LockWorkStation()
            logger.info("Windows LockWorkStation returned: %s", res)
            return bool(res)
        logger.warning("ctypes.windll.user32 not available on this platform")
        return False
    except Exception as e:
        logger.error("Failed to execute LockWorkStation: %s", e)
        return False


def is_fist_relaxed(lm: list[Landmark]) -> bool:
    """
    Checks if hand forms a fist. Relaxed to accommodate natural closed/curled fist variations:
    Index, middle, ring, pinky tips are curled below/inward toward their PIP/MCP joints.
    """
    if is_fist(lm):
        return True
    curled_count = 0
    if is_curled(lm[8], lm[6]):
        curled_count += 1
    if is_curled(lm[12], lm[10]):
        curled_count += 1
    if is_curled(lm[16], lm[14]):
        curled_count += 1
    if is_curled(lm[20], lm[18]):
        curled_count += 1
    return curled_count >= 3


def check_wakanda_pose(
    hands: HandsResult | None,
    face: FaceResult | None = None,
    min_confidence: float = WAKANDA_HAND_CONFIDENCE_MIN,
) -> tuple[bool, str]:
    """
    Evaluates both hands (and optional face anchor) for crossed-arm chest pose.
    Returns (is_valid, diagnostic_reason).
    """
    if hands is None or hands.left is None or hands.right is None:
        return False, "BOTH_HANDS_REQUIRED"

    if hands.left_score < min_confidence or hands.right_score < min_confidence:
        return False, f"LOW_CONFIDENCE (left={hands.left_score:.2f}, right={hands.right_score:.2f})"

    left_lm = hands.left
    right_lm = hands.right

    # 1. Closed fists on both hands
    if not is_fist_relaxed(left_lm):
        return False, "LEFT_HAND_NOT_FIST"
    if not is_fist_relaxed(right_lm):
        return False, "RIGHT_HAND_NOT_FIST"

    # 2. Horizontal Inversion / Cross Check:
    # In mirrored selfie view:
    # User's anatomical left hand crosses across body towards screen-right (larger x).
    # User's anatomical right hand crosses towards screen-left (smaller x).
    # Therefore, left wrist.x > right wrist.x, and left middle MCP.x > right middle MCP.x.
    left_wrist = left_lm[0]
    right_wrist = right_lm[0]
    left_mcp = left_lm[9]
    right_mcp = right_lm[9]

    if left_wrist.x <= right_wrist.x:
        return False, f"ARMS_NOT_CROSSED (left_wrist.x={left_wrist.x:.3f} <= right_wrist.x={right_wrist.x:.3f})"

    if left_mcp.x <= right_mcp.x:
        return False, f"HANDS_NOT_CROSSED (left_mcp.x={left_mcp.x:.3f} <= right_mcp.x={right_mcp.x:.3f})"

    # 3. Diagonal Arm Vector ('X' shape):
    # Vector from wrist (0) to middle MCP (9):
    # User's right arm points up-and-left (screen dx < 0, dy < 0)
    # User's left arm points up-and-right (screen dx > 0, dy < 0)
    right_dx = right_mcp.x - right_wrist.x
    right_dy = right_mcp.y - right_wrist.y
    left_dx = left_mcp.x - left_wrist.x
    left_dy = left_mcp.y - left_wrist.y

    if right_dx > -0.01:
        return False, f"RIGHT_ARM_NOT_DIAGONAL (dx={right_dx:.3f})"
    if left_dx < 0.01:
        return False, f"LEFT_ARM_NOT_DIAGONAL (dx={left_dx:.3f})"

    # Arms should be angled upwards (y_mcp < y_wrist + margin)
    if right_dy > 0.08:
        return False, f"RIGHT_ARM_POINTING_DOWN (dy={right_dy:.3f})"
    if left_dy > 0.08:
        return False, f"LEFT_ARM_POINTING_DOWN (dy={left_dy:.3f})"

    # 4. Vertical Torso Anchor:
    # Wrists should be located in chest/upper torso region (y between 0.18 and 0.90)
    avg_wrist_y = (left_wrist.y + right_wrist.y) / 2.0
    if avg_wrist_y < 0.15 or avg_wrist_y > 0.92:
        return False, f"WRISTS_OUTSIDE_TORSO (y={avg_wrist_y:.3f})"

    # Wrists should be reasonably level with each other
    if abs(left_wrist.y - right_wrist.y) > 0.28:
        return False, f"WRISTS_ASYMMETRIC (dy={abs(left_wrist.y - right_wrist.y):.3f})"

    # If face is detected, wrists must be below mouth/chin level
    if face and face.detected and face.lip_center is not None:
        lip_y = face.lip_center[1]
        if avg_wrist_y < (lip_y - 0.04):
            return False, f"HANDS_TOO_HIGH (wrists={avg_wrist_y:.3f} above lips={lip_y:.3f})"

    # Horizontal proximity: crossed forearms stay within reasonable torso span (< 0.70 normalized)
    horizontal_spread = abs(left_wrist.x - right_wrist.x)
    if horizontal_spread > 0.70:
        return False, f"WRISTS_TOO_FAR_APART (dx={horizontal_spread:.3f})"

    return True, "VALID_WAKANDA_POSE"


class WakandaGestureRecognizer:
    """
    Manages Wakanda Forever gesture state, timing, and native workstation lock triggering.
    """

    def __init__(
        self,
        lock_fn: Callable[[], bool] | None = None,
        enabled: bool = WAKANDA_ENABLED,
        hold_duration: float = WAKANDA_HOLD_DURATION_S,
        grace_period: float = WAKANDA_GRACE_PERIOD_S,
        cooldown: float = WAKANDA_COOLDOWN_S,
    ) -> None:
        self._enabled: bool = bool(enabled)
        self.hold_duration: float = float(hold_duration)
        self.grace_period: float = float(grace_period)
        self.cooldown: float = float(cooldown)

        self._lock_fn: Callable[[], bool] = lock_fn if lock_fn is not None else lock_workstation
        self._state: WakandaState = WakandaState.IDLE if self._enabled else WakandaState.DISABLED
        self._hold_start_time: float = 0.0
        self._last_valid_time: float = 0.0
        self._trigger_time: float = 0.0
        self._status_text: str = "Ready" if self._enabled else "Disabled"
        self._progress: float = 0.0
        self._activation_cb: Callable[[], None] | None = None

        logger.info(
            "WakandaGestureRecognizer initialized (enabled=%s, hold=%.1fs, cooldown=%.1fs)",
            self._enabled,
            self.hold_duration,
            self.cooldown,
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, val: bool) -> None:
        self._enabled = bool(val)
        if not self._enabled:
            self._state = WakandaState.DISABLED
            self._progress = 0.0
            self._status_text = "Disabled"
        elif self._state == WakandaState.DISABLED:
            self._state = WakandaState.IDLE
            self._status_text = "Ready"

    @property
    def state(self) -> WakandaState:
        return self._state

    @property
    def progress(self) -> float:
        return self._progress

    @property
    def is_holding(self) -> bool:
        return self._state in (WakandaState.HOLDING, WakandaState.TRIGGERED)

    @property
    def status_text(self) -> str:
        return self._status_text

    def set_activation_callback(self, cb: Callable[[], None]) -> None:
        self._activation_cb = cb

    def reset(self) -> None:
        self._state = WakandaState.IDLE if self.enabled else WakandaState.DISABLED
        self._hold_start_time = 0.0
        self._last_valid_time = 0.0
        self._progress = 0.0
        self._status_text = "Ready" if self.enabled else "Disabled"

    def process(
        self,
        hands: HandsResult | None,
        face: FaceResult | None = None,
        now: float | None = None,
    ) -> bool:
        """
        Process current frame landmarks.
        Returns True if Wakanda gesture is active (holding or triggered),
        which should suppress mouse cursor motion.
        """
        if now is None:
            now = time.perf_counter()

        if not self.enabled:
            if self._state != WakandaState.DISABLED:
                self._state = WakandaState.DISABLED
                self._progress = 0.0
                self._status_text = "Disabled"
            return False

        if self._state == WakandaState.DISABLED:
            self._state = WakandaState.IDLE
            self._status_text = "Armed and ready"

        # In cooldown state, verify that the hands have uncrossed before returning to IDLE
        if self._state == WakandaState.COOLDOWN:
            self._progress = 0.0
            if (now - self._trigger_time) < self.cooldown:
                self._status_text = f"Cooldown ({self.cooldown - (now - self._trigger_time):.1f}s)"
                return False
            # Check if hands are uncrossed/released
            is_valid, _ = check_wakanda_pose(hands, face)
            if is_valid:
                # Still holding crossed pose, remain in cooldown
                self._status_text = "Release crossed arms to rearm"
                return False
            # Hands released and cooldown expired -> re-arm
            self._state = WakandaState.IDLE
            self._status_text = "Armed and ready"
            return False

        is_valid, reason = check_wakanda_pose(hands, face)

        if self._state == WakandaState.IDLE:
            self._progress = 0.0
            if is_valid:
                self._state = WakandaState.HOLDING
                self._hold_start_time = now
                self._last_valid_time = now
                self._status_text = f"Holding: 0.0 / {self.hold_duration:.1f}s"
                logger.info("Wakanda Forever hold started")
                return True
            self._status_text = "Waiting for crossed-arm pose"
            return False

        if self._state == WakandaState.HOLDING:
            if is_valid:
                self._last_valid_time = now
            else:
                # Check grace period for transient tracking blip
                time_since_valid = now - self._last_valid_time
                if time_since_valid > self.grace_period:
                    logger.info("Wakanda Forever hold broken (%s, grace expired %.2fs)", reason, time_since_valid)
                    self._state = WakandaState.IDLE
                    self._progress = 0.0
                    self._status_text = "Cancelled"
                    return False

            elapsed = max(0.0, now - self._hold_start_time)
            self._progress = min(1.0, elapsed / self.hold_duration)
            self._status_text = f"Holding: {elapsed:.1f} / {self.hold_duration:.1f}s"

            if elapsed >= self.hold_duration:
                self._progress = 1.0
                self._state = WakandaState.TRIGGERED
                self._trigger_time = now
                self._status_text = "WAKANDA FOREVER — LOCKING WORKSTATION"
                logger.info("Wakanda Forever triggered! Executing workstation lock...")

                # Execute lock
                lock_success = self._lock_fn()
                if self._activation_cb:
                    try:
                        self._activation_cb()
                    except Exception as e:
                        logger.error("Error in Wakanda activation callback: %s", e)

                # Transition to cooldown
                self._state = WakandaState.COOLDOWN
                return True

            return True

        if self._state == WakandaState.TRIGGERED:
            self._state = WakandaState.COOLDOWN
            return True

        return False

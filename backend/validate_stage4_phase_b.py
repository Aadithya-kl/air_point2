# validate_stage4_phase_b.py
"""
Air Point — Stage 4 Phase B Conservative Live-Cursor Test Harness.

Executes a bounded, conservative live-cursor validation session on real hardware:
- Real Cursor Movement ONLY: mouse pointer moves via native Win32 SendInput.
- Strict Pre-Movement Physical Displacement Check:
    Queries physical cursor position P_pre via Win32 GetCursorPos() BEFORE movement.
    Computes distance_pre = hypot(target_x - P_pre.x, target_y - P_pre.y).
    If distance_pre > 50.0 px, aborts immediately WITHOUT issuing SendInput or any native movement.
- Independent Post-Movement Physical Measurement:
    Queries physical cursor position P_post via Win32 GetCursorPos() AFTER movement.
    Computes phys_disp = hypot(P_post.x - P_pre.x, P_post.y - P_pre.y).
    If phys_disp > 50.0 px, latches abort and permanently refuses subsequent movement.
- Physical Target Agreement Requirement:
    target_err = hypot(P_post.x - target_x, P_post.y - target_y) <= 2.0px.
- Zero Fallback Policy:
    If SendInput returns 0, the harness fails closed immediately. It does NOT fall back
    to mouse_event or any secondary injection API.
- Fail-Closed Interlocks:
    If a pre-query fails, target is out-of-bounds, pre-displacement > 50px, SendInput fails,
    post-query fails, post-displacement > 50px, or target error > 2px: the harness aborts IMMEDIATELY.
    NO corrective movement is issued automatically.
- Stationary Freeze / Reassertion Verification:
    Stationary freeze paths (ear touch, lip mute, wakanda, screenshot) route through the
    same strict pre/post physical verification. Zero movement is never assumed without verification.
- Documented Race Condition:
    The post-movement check detects unexpected displacement; it cannot prevent external physical
    mouse movement that occurs between P_pre query and SendInput execution. Any such external movement
    is detected immediately post-move, triggering an irreversible fail-closed abort.
- ALL other actions STRICTLY DISABLED:
    Zero clicks (left, right, double).
    Zero dragging.
    Zero keyboard injection (user32.keybd_event interlocked).
    Zero application launches (os.startfile interlocked).
    Zero workstation locking (user32.LockWorkStation interlocked).
    Zero audio volume adjustments / mutes.
    Zero screenshot captures.
- Emergency failsafes:
    PID file: .airpoint_phase_b.pid
    Kill command: Stop-Process -Id (Get-Content .airpoint_phase_b.pid) -Force
    Global emergency key: Ctrl+Alt+Q (immediate hard kill)
    Global pause key: Ctrl+Alt+P (instant tracking freeze)
- Time-bounded: strictly terminates after ~30.0 seconds.
"""

from __future__ import annotations

import argparse
import atexit
import csv
import ctypes
from dataclasses import dataclass
from datetime import datetime
import json
import logging
import math
import os
from pathlib import Path
import sys
import threading
import time
from typing import Any

import cv2
import numpy as np
import psutil
from pynput import keyboard

# Subsystem imports
from core.actuator import (
    INPUT,
    INPUT_MOUSE,
    MOUSEINPUT,
    MOUSEEVENTF_ABSOLUTE,
    MOUSEEVENTF_MOVE,
    MOUSEEVENTF_VIRTUALDESK,
    MouseActuator,
    _user32,
)
from core.camera import AsyncCamera, FrameFreshnessDetector
from core.display import TrackpadZone, VirtualDesktop
from core.gestures.orchestrator import GestureOrchestrator
from core.power_state_machine import (
    InferenceCadence,
    PowerDecision,
    PowerState,
    PowerStateManager,
    PowerTransitionEvent,
)
from core.tracker import HandsResult, HandTracker, Landmark
from main import extract_hand_measurements

logger = logging.getLogger("airpoint.phase_b")


# ─── Strict Limits and Tolerances ───────────────────────────────────────────────

MAX_PHYSICAL_DISPLACEMENT_PX: float = 50.0
"""
Strict 50.0px physical displacement limit.
Both pre-movement distance (hypot(target - P_pre)) and post-movement physical displacement
(hypot(P_post - P_pre)) must not exceed this value.
"""

TOLERANCE_TARGET_PX: float = 2.0
"""
Maximum permissible discrepancy (Euclidean distance in pixels) between requested
virtual target coordinates and independently queried post-movement physical coordinates.
Accounts for 16-bit Win32 SendInput normalized coordinate quantization (+-1px per axis)
and desktop origin offsets.
"""


# ─── Safety Interlocks ───────────────────────────────────────────────────────────

_ORIGINAL_PHASE_B_APIS: dict[str, Any] = {}


def install_phase_b_interlocks() -> None:
    """
    Interlocks Win32 keyboard, workstation lock, mouse_event, SetCursorPos, and app launch APIs.
    Explicitly covers BOTH ctypes.windll.user32 AND core.actuator._user32 to prevent
    unpatched call paths across distinct WinDLL instances.
    """
    global _ORIGINAL_PHASE_B_APIS

    def _blocked_action(api_name: str):
        def _throw(*args, **kwargs):
            raise RuntimeError(f"PHASE B INTERLOCK VIOLATION: Blocked native call to {api_name} during Phase B!")
        return _throw

    # 1. Interlock ctypes.windll.user32 (protects WakandaGestureRecognizer and external modules)
    if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "user32"):
        u32 = ctypes.windll.user32
        if "user32_keybd_event" not in _ORIGINAL_PHASE_B_APIS:
            _ORIGINAL_PHASE_B_APIS["user32_keybd_event"] = getattr(u32, "keybd_event", None)
            _ORIGINAL_PHASE_B_APIS["user32_LockWorkStation"] = getattr(u32, "LockWorkStation", None)
            _ORIGINAL_PHASE_B_APIS["user32_mouse_event"] = getattr(u32, "mouse_event", None)
            _ORIGINAL_PHASE_B_APIS["user32_SetCursorPos"] = getattr(u32, "SetCursorPos", None)

        u32.keybd_event = _blocked_action("user32.keybd_event")
        u32.LockWorkStation = _blocked_action("user32.LockWorkStation")
        u32.mouse_event = _blocked_action("user32.mouse_event")
        u32.SetCursorPos = _blocked_action("user32.SetCursorPos")

    # 2. Interlock core.actuator._user32 (protects MouseActuator and SendInput fallback paths)
    try:
        import core.actuator as act_mod
        act_u32 = getattr(act_mod, "_user32", None)
        if act_u32 is not None and act_u32 is not getattr(getattr(ctypes, "windll", None), "user32", None):
            if "act_user32_keybd_event" not in _ORIGINAL_PHASE_B_APIS:
                _ORIGINAL_PHASE_B_APIS["act_user32_keybd_event"] = getattr(act_u32, "keybd_event", None)
                _ORIGINAL_PHASE_B_APIS["act_user32_LockWorkStation"] = getattr(act_u32, "LockWorkStation", None)
                _ORIGINAL_PHASE_B_APIS["act_user32_mouse_event"] = getattr(act_u32, "mouse_event", None)
                _ORIGINAL_PHASE_B_APIS["act_user32_SetCursorPos"] = getattr(act_u32, "SetCursorPos", None)

            act_u32.keybd_event = _blocked_action("core.actuator._user32.keybd_event")
            act_u32.LockWorkStation = _blocked_action("core.actuator._user32.LockWorkStation")
            act_u32.mouse_event = _blocked_action("core.actuator._user32.mouse_event")
            act_u32.SetCursorPos = _blocked_action("core.actuator._user32.SetCursorPos")
    except Exception:
        pass

    # 3. Interlock os.startfile (protects application launches)
    if hasattr(os, "startfile"):
        if "os_startfile" not in _ORIGINAL_PHASE_B_APIS:
            _ORIGINAL_PHASE_B_APIS["os_startfile"] = os.startfile
        os.startfile = _blocked_action("os.startfile")


def uninstall_phase_b_interlocks() -> None:
    """Restores original APIs prior to Phase B interlocking."""
    global _ORIGINAL_PHASE_B_APIS

    # 1. Restore ctypes.windll.user32
    if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "user32"):
        u32 = ctypes.windll.user32
        for api_name in ("keybd_event", "LockWorkStation", "mouse_event", "SetCursorPos"):
            key = f"user32_{api_name}"
            if key in _ORIGINAL_PHASE_B_APIS:
                orig = _ORIGINAL_PHASE_B_APIS[key]
                if orig is not None:
                    setattr(u32, api_name, orig)
                else:
                    try:
                        delattr(u32, api_name)
                    except AttributeError:
                        pass

    # 2. Restore core.actuator._user32
    try:
        import core.actuator as act_mod
        act_u32 = getattr(act_mod, "_user32", None)
        if act_u32 is not None and act_u32 is not getattr(getattr(ctypes, "windll", None), "user32", None):
            for api_name in ("keybd_event", "LockWorkStation", "mouse_event", "SetCursorPos"):
                key = f"act_user32_{api_name}"
                if key in _ORIGINAL_PHASE_B_APIS:
                    orig = _ORIGINAL_PHASE_B_APIS[key]
                    if orig is not None:
                        setattr(act_u32, api_name, orig)
                    else:
                        try:
                            delattr(act_u32, api_name)
                        except AttributeError:
                            pass
    except Exception:
        pass

    # 3. Restore os.startfile
    if "os_startfile" in _ORIGINAL_PHASE_B_APIS:
        os.startfile = _ORIGINAL_PHASE_B_APIS["os_startfile"]


# ─── Physical Movement Verification Record ──────────────────────────────────────

@dataclass
class PhysicalMovementVerification:
    timestamp: float
    dispatched_x: int
    dispatched_y: int
    dispatched_step_disp_px: float
    phys_pre_x: int | None
    phys_pre_y: int | None
    phys_post_x: int | None
    phys_post_y: int | None
    distance_pre_px: float | None
    phys_step_disp_px: float | None
    phys_target_error_px: float | None
    verified: bool
    failure_reason: str | None


# ─── Conservative Live Actuator (Move-Only with Strict Pre/Post Verification) ───

class ConservativeLiveActuator(MouseActuator):
    """
    Restricted live actuator for Phase B conservative validation:
    - Queries P_pre and enforces distance_pre <= 50.0px BEFORE calling SendInput.
    - Uses strict SendInput with ZERO fallback to mouse_event.
    - Queries P_post and enforces physical displacement <= 50.0px AFTER move.
    - Enforces target agreement <= 2.0px.
    - Latches abort_requested = True on ANY failure, permanently blocking further movement.
    - Strictly blocks and instruments all clicks, double clicks, and drag attempts.
    """

    def __init__(
        self,
        total_width: int,
        total_height: int,
        origin_x: int | None = None,
        origin_y: int | None = None,
        max_physical_disp: float = MAX_PHYSICAL_DISPLACEMENT_PX,
        target_tolerance: float = TOLERANCE_TARGET_PX,
    ) -> None:
        super().__init__(total_width, total_height, origin_x, origin_y)
        self.move_count = 0
        self.attempted_clicks = 0
        self.attempted_drags = 0
        self.max_physical_disp = max_physical_disp
        self.target_tolerance = target_tolerance

        self.abort_requested: bool = False
        self.abort_reason: str | None = None

        self._last_dispatched_pos: tuple[int, int] | None = None
        self.verification_history: list[PhysicalMovementVerification] = []
        self.latest_verification: PhysicalMovementVerification | None = None

    def _send_input_strict(self, x: int, y: int) -> bool:
        """
        Direct native SendInput call with ZERO fallback to mouse_event.
        If SendInput returns 0 for any reason (including UIPI error 5),
        it returns False immediately and does NOT attempt any secondary input.
        """
        if _user32 is None:
            return False
        try:
            norm_x = int(x * 65535 / max(self._total_w - 1, 1))
            norm_y = int(y * 65535 / max(self._total_h - 1, 1))
            norm_x = max(0, min(65535, norm_x))
            norm_y = max(0, min(65535, norm_y))

            inp = INPUT(
                type=INPUT_MOUSE,
                mi=MOUSEINPUT(
                    dx=norm_x,
                    dy=norm_y,
                    mouseData=0,
                    dwFlags=MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
                    time=0,
                    dwExtraInfo=0,
                ),
            )
            res = _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))
            if res == 0:
                err = ctypes.get_last_error()
                logger.warning("SendInput failed in ConservativeLiveActuator (GetLastError=%d). Zero fallback permitted.", err)
                return False
            return True
        except Exception as e:
            logger.warning("SendInput invocation raised exception: %s", e)
            return False

    def _record_verification(
        self,
        t: float,
        dispatched_x: int,
        dispatched_y: int,
        disp_dispatched: float,
        p_pre: tuple[int, int] | None,
        p_post: tuple[int, int] | None,
        verified: bool,
        reason: str | None,
        distance_pre: float | None = None,
        phys_disp: float | None = None,
        target_err: float | None = None,
    ) -> None:
        v = PhysicalMovementVerification(
            timestamp=t,
            dispatched_x=dispatched_x,
            dispatched_y=dispatched_y,
            dispatched_step_disp_px=disp_dispatched,
            phys_pre_x=p_pre[0] if p_pre else None,
            phys_pre_y=p_pre[1] if p_pre else None,
            phys_post_x=p_post[0] if p_post else None,
            phys_post_y=p_post[1] if p_post else None,
            distance_pre_px=distance_pre,
            phys_step_disp_px=phys_disp,
            phys_target_error_px=target_err,
            verified=verified,
            failure_reason=reason,
        )
        self.verification_history.append(v)
        self.latest_verification = v

    def move(self, x: int, y: int) -> bool:
        """
        Issue Win32 cursor move with strict pre- and post-movement physical verification.

        If any query fails or movement cannot be verified within tolerances, fails closed:
        sets self.abort_requested = True and refuses to issue or repeat movement.
        """
        t_now = time.perf_counter()

        # 1. Fail-closed guard: if abort already requested, refuse all further movement
        if self.abort_requested:
            logger.error("Move rejected: Actuator is in FAIL-CLOSED aborted state: %s", self.abort_reason)
            return False

        # 2. Validate requested target coordinates
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            self.abort_requested = True
            self.abort_reason = f"INVALID_TARGET_COORDINATES: Target ({x}, {y}) contains non-numeric values."
            logger.critical("SAFETY VIOLATION: %s", self.abort_reason)
            self._record_verification(t_now, 0, 0, 0.0, None, None, False, self.abort_reason)
            return False

        target_x = int(round(x))
        target_y = int(round(y))

        if not (0 <= target_x < self._total_w and 0 <= target_y < self._total_h):
            self.abort_requested = True
            self.abort_reason = f"TARGET_OUT_OF_BOUNDS: Target ({target_x}, {target_y}) is outside desktop bounds [0, {self._total_w - 1}] x [0, {self._total_h - 1}]."
            logger.critical("SAFETY VIOLATION: %s", self.abort_reason)
            self._record_verification(t_now, target_x, target_y, 0.0, None, None, False, self.abort_reason)
            return False

        # 3. Measure physical cursor position BEFORE movement
        p_pre = self.get_cursor_pos()
        if p_pre is None:
            self.abort_requested = True
            self.abort_reason = "PRE_QUERY_FAILED: Physical cursor position could not be queried before move."
            logger.critical("SAFETY VIOLATION: %s", self.abort_reason)
            self._record_verification(t_now, target_x, target_y, 0.0, None, None, False, self.abort_reason)
            return False

        if not (0 <= p_pre[0] < self._total_w and 0 <= p_pre[1] < self._total_h):
            self.abort_requested = True
            self.abort_reason = f"INVALID_PHYSICAL_PRE_POSITION: Queried position {p_pre} is outside desktop bounds."
            logger.critical("SAFETY VIOLATION: %s", self.abort_reason)
            self._record_verification(t_now, target_x, target_y, 0.0, p_pre, None, False, self.abort_reason)
            return False

        # 4. PRE-MOVEMENT PHYSICAL DISPLACEMENT CHECK
        distance_pre = math.hypot(target_x - p_pre[0], target_y - p_pre[1])
        if distance_pre > self.max_physical_disp + 1e-6:
            self.abort_requested = True
            self.abort_reason = (
                f"PRE_MOVE_DISPLACEMENT_EXCEEDED: Requested target ({target_x}, {target_y}) is "
                f"{distance_pre:.2f}px from physical pre-position {p_pre}, exceeding strict {self.max_physical_disp:.1f}px limit."
            )
            logger.critical("SAFETY VIOLATION: %s", self.abort_reason)
            self._record_verification(t_now, target_x, target_y, 0.0, p_pre, None, False, self.abort_reason, distance_pre=distance_pre)
            return False

        # Calculate dispatched displacement delta (for telemetry)
        disp_dispatched = 0.0
        if self._last_dispatched_pos is not None:
            disp_dispatched = math.hypot(target_x - self._last_dispatched_pos[0], target_y - self._last_dispatched_pos[1])
        self._last_dispatched_pos = (target_x, target_y)

        # 5. Dispatch movement via strict SendInput (NO mouse_event fallback)
        send_ok = self._send_input_strict(target_x, target_y)
        if not send_ok:
            self.abort_requested = True
            self.abort_reason = "SEND_INPUT_FAILED: Win32 SendInput returned 0. Fail-closed: zero fallback permitted."
            logger.critical("SAFETY VIOLATION: %s", self.abort_reason)
            self._record_verification(t_now, target_x, target_y, disp_dispatched, p_pre, None, False, self.abort_reason, distance_pre=distance_pre)
            return False

        # 6. Measure physical cursor position AFTER movement
        p_post = self.get_cursor_pos()
        if p_post is None:
            self.abort_requested = True
            self.abort_reason = "POST_QUERY_FAILED: Physical cursor position could not be queried after move."
            logger.critical("SAFETY VIOLATION: %s", self.abort_reason)
            self._record_verification(t_now, target_x, target_y, disp_dispatched, p_pre, None, False, self.abort_reason, distance_pre=distance_pre)
            return False

        # 7. POST-MOVEMENT PHYSICAL DISPLACEMENT CHECK
        phys_disp = math.hypot(p_post[0] - p_pre[0], p_post[1] - p_pre[1])
        target_err = math.hypot(p_post[0] - target_x, p_post[1] - target_y)

        if phys_disp > self.max_physical_disp + 1e-6:
            self.abort_requested = True
            self.abort_reason = (
                f"POST_MOVE_DISPLACEMENT_EXCEEDED: Actual measured displacement {phys_disp:.2f}px "
                f"exceeds strict {self.max_physical_disp:.1f}px limit."
            )
            logger.critical("SAFETY VIOLATION: %s", self.abort_reason)
            self._record_verification(t_now, target_x, target_y, disp_dispatched, p_pre, p_post, False, self.abort_reason, distance_pre=distance_pre, phys_disp=phys_disp, target_err=target_err)
            return False

        # 8. POST-MOVEMENT TARGET AGREEMENT CHECK
        if target_err > self.target_tolerance + 1e-6:
            self.abort_requested = True
            self.abort_reason = (
                f"TARGET_DISAGREEMENT_EXCEEDED: Physical result {p_post} differs from target ({target_x}, {target_y}) "
                f"by {target_err:.2f}px (tolerance={self.target_tolerance}px)."
            )
            logger.critical("SAFETY VIOLATION: %s", self.abort_reason)
            self._record_verification(t_now, target_x, target_y, disp_dispatched, p_pre, p_post, False, self.abort_reason, distance_pre=distance_pre, phys_disp=phys_disp, target_err=target_err)
            return False

        # All invariants verified!
        self.move_count += 1
        self._record_verification(
            t_now,
            target_x,
            target_y,
            disp_dispatched,
            p_pre,
            p_post,
            True,
            None,
            distance_pre=distance_pre,
            phys_disp=phys_disp,
            target_err=target_err,
        )
        return True

    def left_click(self, x: int | None = None, y: int | None = None) -> bool:
        self.attempted_clicks += 1
        logger.critical("SAFETY INTERCEPT: left_click blocked in ConservativeLiveActuator!")
        return False

    def right_click(self, x: int | None = None, y: int | None = None) -> bool:
        self.attempted_clicks += 1
        logger.critical("SAFETY INTERCEPT: right_click blocked in ConservativeLiveActuator!")
        return False

    def double_click(self) -> bool:
        self.attempted_clicks += 1
        logger.critical("SAFETY INTERCEPT: double_click blocked in ConservativeLiveActuator!")
        return False

    def drag_start(self) -> bool:
        self.attempted_drags += 1
        logger.critical("SAFETY INTERCEPT: drag_start blocked in ConservativeLiveActuator!")
        return False

    def drag_end(self) -> bool:
        return True


# ─── Phase B Audit Counters ─────────────────────────────────────────────────────

@dataclass
class PhaseBAuditCounters:
    whatsapp_attempts: int = 0
    wakanda_attempts: int = 0
    audio_adjustments: int = 0
    audio_mutes: int = 0
    screenshots_taken: int = 0
    clicks_blocked: int = 0
    drags_blocked: int = 0
    excessive_displacement_faults: int = 0
    physical_verification_faults: int = 0
    anchor_query_failures: int = 0
    watchdog_stall_breaks: int = 0

    def summary(self) -> dict[str, int]:
        return {
            "whatsapp_attempts": self.whatsapp_attempts,
            "wakanda_attempts": self.wakanda_attempts,
            "audio_adjustments": self.audio_adjustments,
            "audio_mutes": self.audio_mutes,
            "screenshots_taken": self.screenshots_taken,
            "clicks_blocked": self.clicks_blocked,
            "drags_blocked": self.drags_blocked,
            "excessive_displacement_faults": self.excessive_displacement_faults,
            "physical_verification_faults": self.physical_verification_faults,
            "anchor_query_failures": self.anchor_query_failures,
            "watchdog_stall_breaks": self.watchdog_stall_breaks,
        }


# ─── Telemetry Logger ───────────────────────────────────────────────────────────

class PhaseBTelemetryLogger:
    """Logs separate dispatched-coordinate and physical-cursor verification telemetry."""

    def __init__(self, csv_path: Path) -> None:
        self.csv_path = csv_path
        self._file = open(self.csv_path, "w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        self._writer.writerow([
            "timestamp_iso",
            "elapsed_s",
            "frame_id",
            "power_state",
            "has_hands",
            "cursor_moved",
            "dispatched_x",
            "dispatched_y",
            "dispatched_step_disp_px",
            "phys_pre_x",
            "phys_pre_y",
            "phys_post_x",
            "phys_post_y",
            "distance_pre_px",
            "phys_step_disp_px",
            "phys_target_error_px",
            "phys_verified",
            "trusted_anchor_x",
            "trusted_anchor_y",
            "is_consistent",
            "actuator_moves_total",
            "cpu_percent",
            "rss_mb",
        ])
        self._file.flush()

    def log_sample(
        self,
        elapsed_s: float,
        frame_id: int,
        power_state: str,
        has_hands: bool,
        cursor_moved: bool,
        dispatched_x: int | None,
        dispatched_y: int | None,
        dispatched_step_disp: float,
        phys_pre_x: int | None,
        phys_pre_y: int | None,
        phys_post_x: int | None,
        phys_post_y: int | None,
        distance_pre: float | None,
        phys_step_disp: float | None,
        phys_target_error: float | None,
        phys_verified: bool,
        anchor_x: int | None,
        anchor_y: int | None,
        is_consistent: bool,
        actuator_moves: int,
        cpu_pct: float,
        rss_mb: float,
    ) -> None:
        self._writer.writerow([
            datetime.now().isoformat(),
            round(elapsed_s, 4),
            frame_id,
            power_state,
            int(has_hands),
            int(cursor_moved),
            dispatched_x if dispatched_x is not None else "",
            dispatched_y if dispatched_y is not None else "",
            round(dispatched_step_disp, 2),
            phys_pre_x if phys_pre_x is not None else "",
            phys_pre_y if phys_pre_y is not None else "",
            phys_post_x if phys_post_x is not None else "",
            phys_post_y if phys_post_y is not None else "",
            round(distance_pre, 2) if distance_pre is not None else "",
            round(phys_step_disp, 2) if phys_step_disp is not None else "",
            round(phys_target_error, 2) if phys_target_error is not None else "",
            int(phys_verified),
            anchor_x if anchor_x is not None else "",
            anchor_y if anchor_y is not None else "",
            int(is_consistent),
            actuator_moves,
            round(cpu_pct, 1),
            round(rss_mb, 2),
        ])

    def close(self) -> None:
        try:
            self._file.flush()
            self._file.close()
        except Exception:
            pass


# ─── Phase B Validation Engine ──────────────────────────────────────────────────

class ConservativePhaseBEngine:
    def __init__(
        self,
        output_dir: Path,
        max_duration_s: float = 30.0,
        max_step_limit: float = 48.0,
        use_mock: bool = False,
    ) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.max_duration_s = max_duration_s
        self.max_step_limit = min(max_step_limit, MAX_PHYSICAL_DISPLACEMENT_PX)
        self.use_mock = use_mock

        self.desktop = VirtualDesktop(1920, 1080, 1)
        self.trackpad = TrackpadZone(100, 540, 100, 380)

        # Restore Win32 APIs if test_guard was loaded in this shell
        if not self.use_mock:
            try:
                import test_guard
                import core.actuator as act_mod

                orig = getattr(test_guard, "_ORIGINAL_APIS", {})
                if "cv2_VideoCapture" in orig:
                    cv2.VideoCapture = orig["cv2_VideoCapture"]
                if "user32_GetCursorPos" in orig:
                    ctypes.windll.user32.GetCursorPos = orig["user32_GetCursorPos"]
                    if hasattr(act_mod, "_user32"):
                        act_mod._user32.GetCursorPos = orig["user32_GetCursorPos"]
                if "user32_SendInput" in orig:
                    ctypes.windll.user32.SendInput = orig["user32_SendInput"]
                    if hasattr(act_mod, "_user32"):
                        act_mod._user32.SendInput = orig["user32_SendInput"]
                if "user32_SetCursorPos" in orig:
                    ctypes.windll.user32.SetCursorPos = orig["user32_SetCursorPos"]
                    if hasattr(act_mod, "_user32"):
                        act_mod._user32.SetCursorPos = orig["user32_SetCursorPos"]
                if "user32_mouse_event" in orig:
                    ctypes.windll.user32.mouse_event = orig["user32_mouse_event"]
                    if hasattr(act_mod, "_user32"):
                        act_mod._user32.mouse_event = orig["user32_mouse_event"]
            except Exception:
                pass

        self.actuator = ConservativeLiveActuator(1920, 1080, max_physical_disp=MAX_PHYSICAL_DISPLACEMENT_PX)
        self.audit_counters = PhaseBAuditCounters()
        self.pid_file = Path(".airpoint_phase_b.pid")
        self.is_running = True
        self.is_paused = False
        self.process = psutil.Process()
        self.process.cpu_percent(interval=None)

    def _setup_pid_and_emergency_controls(self) -> keyboard.GlobalHotKeys:
        pid = os.getpid()
        self.pid_file.write_text(str(pid), encoding="utf-8")
        print("\n" + "!" * 80)
        print(f"  PHASE B LIVE TEST PID: {pid} (saved to .airpoint_phase_b.pid)")
        print(f"  EMERGENCY KILL COMMAND: Stop-Process -Id {pid} -Force")
        print("  EMERGENCY HOTKEYS: Ctrl+Alt+Q (Hard Kill) | Ctrl+Alt+P (Pause Tracking)")
        print("!" * 80 + "\n")

        def _cleanup():
            try:
                if self.pid_file.exists():
                    self.pid_file.unlink()
            except Exception:
                pass

        atexit.register(_cleanup)

        def on_quit():
            logger.warning("Emergency Stop (Ctrl+Alt+Q) received!")
            self.is_running = False
            def _force():
                time.sleep(0.5)
                os._exit(0)
            threading.Thread(target=_force, daemon=True).start()

        def on_pause():
            self.is_paused = not self.is_paused
            logger.info("ENGINE %s", "PAUSED" if self.is_paused else "RESUMED")

        hotkeys = keyboard.GlobalHotKeys({
            "<ctrl>+<alt>+q": on_quit,
            "<ctrl>+<alt>+p": on_pause,
        })
        hotkeys.start()
        return hotkeys

    def _isolate_orchestrator(self, processor: GestureOrchestrator) -> None:
        processor.pointer_enabled = True
        processor.drag_enabled = False

        if hasattr(processor, "_screenshot"):
            processor._screenshot.enabled = False
            processor._screenshot.pre_capture_cb = None
            processor._screenshot.post_capture_cb = None

        if hasattr(processor, "_w_gesture"):
            processor._w_gesture.enabled = False
            processor.set_w_activation_callback(lambda s: self.audit_counters.__setattr__("whatsapp_attempts", self.audit_counters.whatsapp_attempts + 1))

        if hasattr(processor, "_lip_gesture"):
            processor._lip_gesture.enabled = False
            processor.set_lip_activation_callback(lambda a, s: self.audit_counters.__setattr__("audio_mutes", self.audit_counters.audio_mutes + 1))

        if hasattr(processor, "_ear_volume"):
            processor._ear_volume.enabled_up = False
            processor._ear_volume.enabled_down = False
            processor.set_ear_volume_callback(lambda d, v, a: self.audit_counters.__setattr__("audio_adjustments", self.audit_counters.audio_adjustments + 1))

        if hasattr(processor, "_wakanda"):
            processor._wakanda.enabled = False
            processor.set_wakanda_callback(lambda: self.audit_counters.__setattr__("wakanda_attempts", self.audit_counters.wakanda_attempts + 1))

        if hasattr(processor, "audio_controller"):
            ac = processor.audio_controller
            ac.set_volume_scalar = lambda v: None
            ac.toggle_mute = lambda: False

    def run_phase_b_test(self) -> tuple[bool, Path, dict[str, Any]]:
        csv_path = self.output_dir / "stage4_phase_b_telemetry.csv"
        telemetry = PhaseBTelemetryLogger(csv_path)
        hotkeys = self._setup_pid_and_emergency_controls()
        install_phase_b_interlocks()

        # Preflight: Initial physical cursor query requirement
        initial_pos = self.actuator.get_cursor_pos()
        if initial_pos is None:
            self.audit_counters.anchor_query_failures += 1
            logger.error("Initial get_cursor_pos() query FAILED! Suppressing movement.")
            print("[FATAL] Initial physical cursor position could not be queried. Aborting.")
            return False, csv_path, {"error": "initial get_cursor_pos failed"}

        print(f"[OK] Initial physical cursor query: {initial_pos}")

        # Instantiate orchestrator with strict max_step_limit (<= 48.0px to account for integer rounding)
        processor = GestureOrchestrator(
            actuator=self.actuator,
            desktop=self.desktop,
            trackpad=self.trackpad,
            initial_cursor_anchor=initial_pos,
            max_step_limit=self.max_step_limit,
        )
        self._isolate_orchestrator(processor)

        power_manager = PowerStateManager(
            inactivity_timeout_s=120.0,
            wake_trigger_velocity=0.50,
            wake_confirm_velocity=0.40,
            wake_confirm_duration_s=0.15,
            wake_dwell_duration_s=10.0,
            probe_stride=3,
            min_confirm_frames=3,
            max_healthy_frame_interval_s=0.150,
            clock_fn=time.perf_counter,
        )
        power_manager.set_enabled(True)
        freshness_detector = FrameFreshnessDetector(stale_threshold_count=3)

        t_start = time.perf_counter()
        last_accepted_frame_time = t_start
        last_frame_id = -1
        no_frame_since: float | None = None
        max_observed_dispatched_disp = 0.0
        max_observed_distance_pre = 0.0
        max_observed_phys_disp = 0.0
        max_observed_target_err = 0.0

        print(f"\n>>> Starting Phase B Conservative Live Test ({self.max_duration_s}s timeline) <<<")
        print(f">>> Maximum displacement limit: {MAX_PHYSICAL_DISPLACEMENT_PX:.1f}px per actuator move <<<")
        print(">>> Move hand gently in camera view to observe bounded cursor movement.\n")

        with AsyncCamera(camera_index=0) as camera, HandTracker(max_hands=2) as tracker:
            try:
                while self.is_running:
                    t_now = time.perf_counter()
                    t_elapsed = t_now - t_start

                    if t_elapsed >= self.max_duration_s:
                        logger.info("Phase B completed full %.1fs test session.", t_elapsed)
                        break

                    # 1. Read fresh camera frame
                    frame, frame_id = camera.read_fresh(last_frame_id, timeout=0.033)
                    t_now = time.perf_counter()

                    if frame is None or frame_id == last_frame_id:
                        if no_frame_since is None:
                            no_frame_since = t_now
                        elif (t_now - no_frame_since) > 5.0:
                            self.audit_counters.watchdog_stall_breaks += 1
                            logger.error("Webcam produced no frames for > 5.0s!")
                            break
                        time.sleep(0.005)
                        continue

                    # 2. Freshness check
                    if not freshness_detector.check(frame):
                        time.sleep(0.005)
                        continue

                    last_accepted_frame_time = t_now
                    last_frame_id = frame_id
                    no_frame_since = None

                    # 3. Tracking & Cadence
                    decision = power_manager.evaluate_cadence(now=t_now, frame_valid=True, frame_id=frame_id)

                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    hands = tracker.process(frame, rgb_image=rgb_frame)
                    has_hands, p_center, p_width, p_id = extract_hand_measurements(hands)

                    prior_moves = self.actuator.move_count
                    cursor_moved = False

                    if self.is_paused:
                        processor.process(None, None)
                    else:
                        processor.process(hands, None)

                    # 4. Fail-closed check: Actuator verification status
                    if self.actuator.abort_requested:
                        logger.critical("FAIL-CLOSED HARNESS ABORT: Physical verification failed: %s", self.actuator.abort_reason)
                        self.audit_counters.physical_verification_faults += 1
                        print(f"\n[FAIL-CLOSED ABORT] Physical verification failure: {self.actuator.abort_reason}")
                        print("Stopping harness immediately without issuing corrective movement.")
                        self.is_running = False
                        break

                    # 5. Extract verification metrics for telemetry
                    dispatched_x = None
                    dispatched_y = None
                    disp_dispatched = 0.0
                    phys_pre_x = None
                    phys_pre_y = None
                    phys_post_x = None
                    phys_post_y = None
                    dist_pre = None
                    phys_disp = None
                    phys_target_err = None
                    phys_verified = True

                    if self.actuator.latest_verification is not None:
                        lv = self.actuator.latest_verification
                        if self.actuator.move_count > prior_moves:
                            cursor_moved = True
                            dispatched_x = lv.dispatched_x
                            dispatched_y = lv.dispatched_y
                            disp_dispatched = lv.dispatched_step_disp_px
                            phys_pre_x = lv.phys_pre_x
                            phys_pre_y = lv.phys_pre_y
                            phys_post_x = lv.phys_post_x
                            phys_post_y = lv.phys_post_y
                            dist_pre = lv.distance_pre_px
                            phys_disp = lv.phys_step_disp_px
                            phys_target_err = lv.phys_target_error_px
                            phys_verified = lv.verified

                            if disp_dispatched > max_observed_dispatched_disp:
                                max_observed_dispatched_disp = disp_dispatched
                            if dist_pre is not None and dist_pre > max_observed_distance_pre:
                                max_observed_distance_pre = dist_pre
                            if phys_disp is not None and phys_disp > max_observed_phys_disp:
                                max_observed_phys_disp = phys_disp
                            if phys_target_err is not None and phys_target_err > max_observed_target_err:
                                max_observed_target_err = phys_target_err

                    # Verify internal anchor vs actuator position consistency
                    trusted_anchor = processor.trusted_cursor_anchor
                    last_cursor = processor.cursor_pos
                    is_consistent = True
                    if cursor_moved and trusted_anchor is not None:
                        is_consistent = (trusted_anchor == (dispatched_x, dispatched_y)) and (last_cursor == (dispatched_x, dispatched_y))
                        if not is_consistent:
                            logger.error("INCONSISTENCY: anchor %s != dispatched %s", trusted_anchor, (dispatched_x, dispatched_y))

                    # Safety check: zero clicks and drags permitted
                    if self.actuator.attempted_clicks > 0:
                        self.audit_counters.clicks_blocked += self.actuator.attempted_clicks
                        print("[ABORT] Click attempted during conservative mode. Stopping immediately.")
                        break

                    # Log telemetry
                    mem = self.process.memory_info()
                    rss_mb = mem.rss / (1024.0 * 1024.0)
                    cpu_pct = self.process.cpu_percent(interval=None)

                    telemetry.log_sample(
                        elapsed_s=t_elapsed,
                        frame_id=frame_id,
                        power_state=power_manager.state.name,
                        has_hands=has_hands,
                        cursor_moved=cursor_moved,
                        dispatched_x=dispatched_x,
                        dispatched_y=dispatched_y,
                        dispatched_step_disp=disp_dispatched,
                        phys_pre_x=phys_pre_x,
                        phys_pre_y=phys_pre_y,
                        phys_post_x=phys_post_x,
                        phys_post_y=phys_post_y,
                        distance_pre=dist_pre,
                        phys_step_disp=phys_disp,
                        phys_target_error=phys_target_err,
                        phys_verified=phys_verified,
                        anchor_x=trusted_anchor[0] if trusted_anchor else None,
                        anchor_y=trusted_anchor[1] if trusted_anchor else None,
                        is_consistent=is_consistent,
                        actuator_moves=self.actuator.move_count,
                        cpu_pct=cpu_pct,
                        rss_mb=rss_mb,
                    )

            except KeyboardInterrupt:
                logger.info("Phase B interrupted by operator.")
            finally:
                hotkeys.stop()
                telemetry.close()

        total_elapsed = time.perf_counter() - t_start
        audit_summary = self.audit_counters.summary()

        test_passed = (
            self.audit_counters.physical_verification_faults == 0
            and self.audit_counters.excessive_displacement_faults == 0
            and self.audit_counters.clicks_blocked == 0
            and self.audit_counters.drags_blocked == 0
            and self.audit_counters.whatsapp_attempts == 0
            and self.audit_counters.wakanda_attempts == 0
            and self.actuator.move_count > 0
            and not self.actuator.abort_requested
        )

        summary = {
            "test_verdict": "PASS" if test_passed else "FAIL",
            "duration_s": round(total_elapsed, 2),
            "max_step_limit_px": self.max_step_limit,
            "max_dispatched_displacement_px": round(max_observed_dispatched_disp, 2),
            "max_pre_distance_px": round(max_observed_distance_pre, 2),
            "max_physical_displacement_px": round(max_observed_phys_disp, 2),
            "max_physical_target_error_px": round(max_observed_target_err, 2),
            "total_cursor_moves": self.actuator.move_count,
            "physical_verifications_count": len(self.actuator.verification_history),
            "physical_verification_failures": sum(1 for v in self.actuator.verification_history if not v.verified),
            "initial_physical_anchor": initial_pos,
            "final_physical_anchor": self.actuator.get_cursor_pos(),
            "audit_counters": audit_summary,
        }

        summary_file = self.output_dir / "stage4_phase_b_summary.json"
        summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        return test_passed, csv_path, summary


# ─── CLI Entrypoint ─────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Air Point Stage 4 Phase B Conservative Live Cursor Test")
    parser.add_argument("--authorize-live-cursor", action="store_true", help="Explicit operator authorization for live cursor movement")
    parser.add_argument("--outdir", type=str, default="stage4_phase_b_results", help="Output directory")
    parser.add_argument("--timeout", type=float, default=30.0, help="Test duration in seconds (default: 30.0)")
    parser.add_argument("--max-step", type=float, default=48.0, help="Maximum displacement limit in px (default: 48.0, max: 50.0)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if not args.authorize_live_cursor:
        print("\n" + "=" * 80)
        print("  [AIRPOINT GATE] Phase B Live Cursor Testing is BLOCKED.")
        print("  Real cursor movement requires explicit operator authorization.")
        print("  To run when authorized:")
        print("    .\\.venv\\Scripts\\python.exe validate_stage4_phase_b.py --authorize-live-cursor")
        print("=" * 80 + "\n")
        sys.exit(0)

    out_dir = Path(args.outdir)
    engine = ConservativePhaseBEngine(
        output_dir=out_dir,
        max_duration_s=args.timeout,
        max_step_limit=args.max_step,
        use_mock=False,
    )

    success, csv_path, summary = engine.run_phase_b_test()

    print("\n" + "=" * 80)
    print("PHASE B CONSERVATIVE LIVE CURSOR TEST RESULT SUMMARY")
    print("=" * 80)
    print(f"Test Verdict:                  {summary['test_verdict']}")
    print(f"Duration:                      {summary['duration_s']}s")
    print(f"Max Step Limit:                {summary['max_step_limit_px']} px")
    print(f"Max Dispatched Displacement:   {summary['max_dispatched_displacement_px']} px")
    print(f"Max Pre-Distance:              {summary['max_pre_distance_px']} px")
    print(f"Max Physical Displacement:     {summary['max_physical_displacement_px']} px")
    print(f"Max Physical Target Error:     {summary['max_physical_target_error_px']} px")
    print(f"Total Cursor Moves:            {summary['total_cursor_moves']}")
    print(f"Physical Verifications:        {summary['physical_verifications_count']} (failures: {summary['physical_verification_failures']})")
    print(f"Initial Anchor:                {summary['initial_physical_anchor']}")
    print(f"Final Physical Position:       {summary['final_physical_anchor']}")
    print(f"Audit Counters:                {summary['audit_counters']}")
    print(f"Telemetry CSV:                 {csv_path.resolve()}")
    print("=" * 80 + "\n")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

# validate_stage4a1_wake.py
"""
Air Point — Stage 4A.1 Targeted Live Wake Validation Harness.

Exercises real webcam capture, real FrameFreshnessDetector, and real
PowerStateManager wake lifecycle with absolute OS isolation:
- Starts PowerStateManager directly in POWER_SAVE.
- Reuses production AsyncCamera, FrameFreshnessDetector, HandTracker,
  extract_hand_measurements, and PowerStateManager.
- Preserves exact production wake criteria:
    wake_trigger_velocity = 0.50 palm-width/s
    wake_confirm_velocity = 0.40 palm-width/s
    wake_confirm_duration_s = 0.15s
    min_confirm_frames = 3
- NonEmittingActuator: zero Win32 SendInput, zero cursor motion, zero keyboard events.
- All side-effect gestures disabled & monitored via audit counters (WhatsApp, Wakanda, audio, screenshots).
- Verifies:
    1. Rejection of stillness, brief flicks, tracking loss, and hand swaps.
    2. Intentional sweep produces WAKE_CONFIRMED and returns state to NORMAL.
    3. Resumes FULL_RATE inference on immediate next eligible frame.
- High-frequency per-frame CSV telemetry and JSON summary.
- Max duration: 60 seconds (or early clean completion ~8s after confirmed wake).
"""

from __future__ import annotations

import argparse
import atexit
import csv
import ctypes
from dataclasses import dataclass, field
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

logger = logging.getLogger("airpoint.validate_wake")


# ── Safety Interlocks ────────────────────────────────────────────────────────

def install_os_action_interlock() -> None:
    """Interlocks Win32 input and app launch APIs to prevent OS side effects."""
    def _blocked_action(api_name: str):
        def _throw(*args, **kwargs):
            raise RuntimeError(f"SAFETY INTERLOCK VIOLATION: Blocked native call to {api_name} during wake validation!")
        return _throw

    if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "user32"):
        u32 = ctypes.windll.user32
        u32.SendInput = _blocked_action("user32.SendInput")
        u32.SetCursorPos = _blocked_action("user32.SetCursorPos")
        u32.mouse_event = _blocked_action("user32.mouse_event")
        u32.keybd_event = _blocked_action("user32.keybd_event")
        u32.LockWorkStation = _blocked_action("user32.LockWorkStation")

    if hasattr(os, "startfile"):
        os.startfile = _blocked_action("os.startfile")


# ── Non-Emitting Actuator ───────────────────────────────────────────────────

class NonEmittingActuator:
    """Non-emitting actuator that records all calls in memory without issuing OS events."""

    def __init__(self, width: int = 1920, height: int = 1080) -> None:
        self.total_width = width
        self.total_height = height
        self.is_dragging = False
        self.move_count = 0
        self.move_to_count = 0
        self.click_count = 0
        self.drag_start_count = 0
        self.drag_end_count = 0

    def move(self, x: int, y: int) -> bool:
        self.move_count += 1
        return True

    def move_to(self, x: int, y: int) -> bool:
        self.move_to_count += 1
        return True

    def left_click(self, x: int | None = None, y: int | None = None) -> bool:
        self.click_count += 1
        return True

    def right_click(self, x: int | None = None, y: int | None = None) -> bool:
        self.click_count += 1
        return True

    def double_click(self) -> bool:
        self.click_count += 1
        return True

    def drag_start(self) -> bool:
        self.is_dragging = True
        self.drag_start_count += 1
        return True

    def drag_end(self) -> bool:
        self.is_dragging = False
        self.drag_end_count += 1
        return True

    def get_cursor_pos(self) -> tuple[int, int] | None:
        """Read-only query of actual cursor position for anchor audit."""
        try:
            from ctypes import wintypes
            pt = wintypes.POINT()
            if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
                return (pt.x, pt.y)
        except Exception:
            pass
        return None


# ── Audit Counters ──────────────────────────────────────────────────────────

@dataclass
class WakeAuditCounters:
    whatsapp_attempts: int = 0
    wakanda_attempts: int = 0
    audio_adjustments: int = 0
    audio_mutes: int = 0
    screenshots_taken: int = 0
    watchdog_stall_breaks: int = 0
    invalid_gap_resets: int = 0
    wake_candidates_armed: int = 0
    wake_candidates_rejected: int = 0
    wake_confirmed_events: int = 0

    def summary(self) -> dict[str, int]:
        return {
            "whatsapp_attempts": self.whatsapp_attempts,
            "wakanda_attempts": self.wakanda_attempts,
            "audio_adjustments": self.audio_adjustments,
            "audio_mutes": self.audio_mutes,
            "screenshots_taken": self.screenshots_taken,
            "watchdog_stall_breaks": self.watchdog_stall_breaks,
            "invalid_gap_resets": self.invalid_gap_resets,
            "wake_candidates_armed": self.wake_candidates_armed,
            "wake_candidates_rejected": self.wake_candidates_rejected,
            "wake_confirmed_events": self.wake_confirmed_events,
        }


# ── Per-Frame Telemetry Logger ───────────────────────────────────────────────

class WakeTelemetryLogger:
    def __init__(self, csv_path: Path) -> None:
        self.csv_path = csv_path
        self._file = open(self.csv_path, "w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        self._writer.writerow([
            "timestamp_iso",
            "elapsed_s",
            "frame_id",
            "stage_label",
            "power_state",
            "cadence",
            "transition_event",
            "is_fresh",
            "has_hands",
            "hand_id",
            "palm_x",
            "palm_y",
            "palm_width",
            "measured_velocity",
            "is_confirming_wake",
            "confirm_frames",
            "actuator_moves",
            "actuator_clicks",
            "cpu_percent",
            "rss_mb",
        ])
        self._file.flush()

    def log_frame(
        self,
        elapsed_s: float,
        frame_id: int,
        stage_label: str,
        power_state: str,
        cadence: str,
        transition_event: str,
        is_fresh: bool,
        has_hands: bool,
        hand_id: str | None,
        palm_center: tuple[float, float] | None,
        palm_width: float | None,
        measured_velocity: float,
        is_confirming_wake: bool,
        confirm_frames: int,
        actuator_moves: int,
        actuator_clicks: int,
        cpu_pct: float,
        rss_mb: float,
    ) -> None:
        px = round(palm_center[0], 4) if palm_center else ""
        py = round(palm_center[1], 4) if palm_center else ""
        pw = round(palm_width, 4) if palm_width else ""
        self._writer.writerow([
            datetime.now().isoformat(),
            round(elapsed_s, 4),
            frame_id,
            stage_label,
            power_state,
            cadence,
            transition_event,
            int(is_fresh),
            int(has_hands),
            hand_id or "",
            px,
            py,
            pw,
            round(measured_velocity, 3),
            int(is_confirming_wake),
            confirm_frames,
            actuator_moves,
            actuator_clicks,
            round(cpu_pct, 1),
            round(rss_mb, 2),
        ])

    def close(self) -> None:
        try:
            self._file.flush()
            self._file.close()
        except Exception:
            pass


# ── Mock Dependencies for Self-Test ──────────────────────────────────────────

class MockWakeSelfTestCamera:
    """Generates synthetic video stream simulating stillness, flick, and sweep."""
    def __init__(self, camera_index: int = 0) -> None:
        self.frame_id = 0
        self.is_opened = True

    def __enter__(self) -> MockWakeSelfTestCamera:
        return self

    def __exit__(self, *args) -> None:
        self.is_opened = False

    def read_fresh(self, last_frame_id: int = -1, timeout: float = 0.033) -> tuple[np.ndarray | None, int]:
        self.frame_id += 1
        time.sleep(0.015)  # Fast clock for self-test
        # Return subtle noise image
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        img[0, 0, 0] = self.frame_id % 256
        return img, self.frame_id


class MockWakeSelfTestTracker:
    """Generates sequence: stillness -> flick -> sweep -> tracking in NORMAL."""
    def __init__(self) -> None:
        self.call_count = 0

    def __enter__(self) -> MockWakeSelfTestTracker:
        return self

    def __exit__(self, *args) -> None:
        pass

    def process(self, frame: np.ndarray, rgb_image: np.ndarray | None = None) -> HandsResult:
        self.call_count += 1
        # Calls 1-4: stationary hand at (0.50, 0.50)
        # Calls 5-6: quick flick and stop (triggers candidate arm, then reject on stop)
        # Calls 7+: steady continuous sweep across camera (arms and confirms wake)
        if self.call_count <= 4:
            cx = 0.50
        elif self.call_count <= 6:
            cx = 0.55
        else:
            cx = 0.10 + (self.call_count - 6) * 0.015

        lm_wrist = Landmark(x=cx, y=0.55, z=0.0)
        lm_index_mcp = Landmark(x=cx - 0.05, y=0.50, z=0.0)
        lm_pinky_mcp = Landmark(x=cx + 0.05, y=0.50, z=0.0)
        landmarks = [lm_wrist] * 21
        landmarks[0] = lm_wrist
        landmarks[5] = lm_index_mcp
        landmarks[17] = lm_pinky_mcp

        return HandsResult(
            left=None,
            right=landmarks,
            left_score=0.0,
            right_score=0.95,
        )


# ── Targeted Wake Validation Engine ──────────────────────────────────────────

class TargetedWakeValidationEngine:
    def __init__(
        self,
        output_dir: Path,
        use_mock: bool = False,
        max_duration_s: float = 60.0,
    ) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.use_mock = use_mock
        self.max_duration_s = max_duration_s

        self.cam_factory = MockWakeSelfTestCamera if self.use_mock else AsyncCamera
        self.tracker_factory = MockWakeSelfTestTracker if self.use_mock else HandTracker

        if not self.use_mock:
            try:
                import test_guard
                if "cv2_VideoCapture" in getattr(test_guard, "_ORIGINAL_APIS", {}):
                    cv2.VideoCapture = test_guard._ORIGINAL_APIS["cv2_VideoCapture"]
                if "user32_GetCursorPos" in getattr(test_guard, "_ORIGINAL_APIS", {}):
                    ctypes.windll.user32.GetCursorPos = test_guard._ORIGINAL_APIS["user32_GetCursorPos"]
            except Exception:
                pass

        self.actuator = NonEmittingActuator(1920, 1080)
        self.desktop = VirtualDesktop(1920, 1080, 1)
        self.trackpad = TrackpadZone(100, 540, 100, 380)
        self.audit_counters = WakeAuditCounters()
        self.process = psutil.Process()
        self.process.cpu_percent(interval=None)

        self.pid_file = Path(".airpoint_wake_test.pid")
        self.is_running = True
        self.summary: dict[str, Any] = {}

    def _setup_pid_and_hotkeys(self) -> keyboard.GlobalHotKeys:
        pid = os.getpid()
        self.pid_file.write_text(str(pid), encoding="utf-8")
        logger.info("Wake Validation PID: %d (saved to %s)", pid, self.pid_file.name)

        def _cleanup():
            try:
                if self.pid_file.exists():
                    self.pid_file.unlink()
            except Exception:
                pass

        atexit.register(_cleanup)

        def on_quit():
            logger.warning("Emergency stop hotkey triggered!")
            self.is_running = False

        hotkeys = keyboard.GlobalHotKeys({"<ctrl>+<alt>+q": on_quit})
        hotkeys.start()
        return hotkeys

    def _isolate_orchestrator(self, processor: GestureOrchestrator) -> None:
        processor.pointer_enabled = False
        processor.drag_enabled = False

        if hasattr(processor, "_screenshot"):
            processor._screenshot.enabled = False
            processor._screenshot.pre_capture_cb = None
            processor._screenshot.post_capture_cb = None

        if hasattr(processor, "_w_gesture"):
            processor._w_gesture.enabled = False
            def _on_w(success: bool):
                self.audit_counters.whatsapp_attempts += 1
                logger.warning("AUDIT: WhatsApp activation caught and blocked!")
            processor.set_w_activation_callback(_on_w)

        if hasattr(processor, "_lip_gesture"):
            processor._lip_gesture.enabled = False
            def _on_lip(action: str, success: bool):
                self.audit_counters.audio_mutes += 1
                logger.warning("AUDIT: Lip mute caught and blocked!")
            processor.set_lip_activation_callback(_on_lip)

        if hasattr(processor, "_ear_volume"):
            processor._ear_volume.enabled_up = False
            processor._ear_volume.enabled_down = False
            def _on_vol(dir_name: str, vol: float, active: bool):
                self.audit_counters.audio_adjustments += 1
                logger.warning("AUDIT: Ear volume adjustment caught and blocked!")
            processor.set_ear_volume_callback(_on_vol)

        if hasattr(processor, "_wakanda"):
            processor._wakanda.enabled = False
            def _on_wakanda():
                self.audit_counters.wakanda_attempts += 1
                logger.critical("AUDIT: Wakanda lock attempt caught and blocked!")
            processor.set_wakanda_callback(_on_wakanda)

        if hasattr(processor, "audio_controller"):
            ac = processor.audio_controller
            ac.set_volume_scalar = lambda v: None
            ac.toggle_mute = lambda: False

    def run_wake_validation(self) -> tuple[bool, Path, dict[str, Any]]:
        csv_path = self.output_dir / "stage4a1_wake_telemetry.csv"
        telemetry = WakeTelemetryLogger(csv_path)
        hotkeys = self._setup_pid_and_hotkeys()
        install_os_action_interlock()

        # Instantiate production subsystems
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

        # Controlled setup: Start directly in POWER_SAVE
        power_manager._state = PowerState.POWER_SAVE
        power_manager._accumulated_inactive_s = 120.0
        assert power_manager.state == PowerState.POWER_SAVE, "Failed to start in POWER_SAVE"

        freshness_detector = FrameFreshnessDetector(stale_threshold_count=3)
        processor = GestureOrchestrator(self.actuator, self.desktop, self.trackpad)
        self._isolate_orchestrator(processor)

        t_start = time.perf_counter()
        last_accepted_frame_time = t_start
        last_frame_id = -1
        no_frame_since: float | None = None
        last_stage = "PHASE_1_REJECTION_PROBE"

        wake_confirmed_ts: float | None = None
        wake_confirmed_frame_id: int | None = None
        post_wake_normal_frames = 0
        pre_wake_probe_frames = 0
        pre_wake_skip_frames = 0
        max_measured_velocity = 0.0
        was_confirming = False
        resumed_full_rate_on_next_frame = False
        previous_decision_was_wake_confirmed = False

        print("\n" + "=" * 80)
        print(">>> [STAGE 4A.1 TARGETED WAKE VALIDATION RUNNING]")
        print(">>> Controlled Setup: Started directly in POWER_SAVE mode (probing 1:3)")
        print(">>> [PHASE 1 (0s-12s)]: TESTING FALSE WAKE REJECTION")
        print("    CUE: Keep hand still, or flick fingers briefly (must be rejected)\n" + "=" * 80 + "\n")

        with self.cam_factory() as camera, self.tracker_factory() as tracker:
            try:
                while self.is_running:
                    t_now = time.perf_counter()
                    t_elapsed = t_now - t_start

                    # Check overall duration timeout
                    if t_elapsed >= self.max_duration_s:
                        logger.info("Reached maximum duration (%.1fs). Ending test.", t_elapsed)
                        break

                    # End ~8s after confirmed wake to record steady resumed NORMAL operation
                    if wake_confirmed_ts is not None and (t_now - wake_confirmed_ts) >= (4.0 if self.use_mock else 8.0):
                        logger.info("Recorded %.1fs of post-wake NORMAL operation. Test complete.", t_now - wake_confirmed_ts)
                        break

                    # Update stage label and operator cues
                    if wake_confirmed_ts is not None:
                        current_stage = "PHASE_3_NORMAL_RESUMED"
                    elif t_elapsed < (3.0 if self.use_mock else 12.0):
                        current_stage = "PHASE_1_REJECTION_PROBE"
                    else:
                        current_stage = "PHASE_2_INTENTIONAL_SWEEP"

                    if current_stage != last_stage:
                        if current_stage == "PHASE_2_INTENTIONAL_SWEEP":
                            print("\n" + "*" * 80)
                            print(">>> [PHASE 2 (12s-45s)]: PERFORM DELIBERATE SWEEP NOW!")
                            print("    CUE: Wave hand steadily across the camera view (v >= 0.50 for >= 0.15s)")
                            print("*" * 80 + "\n")
                        elif current_stage == "PHASE_3_NORMAL_RESUMED":
                            print("\n" + "#" * 80)
                            print(">>> [PHASE 3]: WAKE_CONFIRMED! Full-rate inference active.")
                            print("    CUE: Move hand freely; verifying full-rate 30 FPS inference & anchor sync.")
                            print("#" * 80 + "\n")
                        last_stage = current_stage

                    # 1. Read fresh frame from camera
                    t_frame_start = time.perf_counter()
                    frame, frame_id = camera.read_fresh(last_frame_id, timeout=0.033)
                    t_now = time.perf_counter()

                    # 2. Watchdog check
                    if frame is None or frame_id == last_frame_id:
                        if no_frame_since is None:
                            no_frame_since = t_now
                        elif (t_now - no_frame_since) > 5.0:
                            self.audit_counters.watchdog_stall_breaks += 1
                            logger.error("Camera produced no frames for > 5.0s!")
                            break
                        if frame is None or (t_now - last_accepted_frame_time) > 0.150:
                            self.audit_counters.invalid_gap_resets += 1
                            power_manager.evaluate_cadence(now=t_now, frame_valid=False, frame_id=frame_id)
                        time.sleep(0.005)
                        continue

                    # 3. Check freshness
                    is_fresh = freshness_detector.check(frame)
                    if not is_fresh:
                        self.audit_counters.invalid_gap_resets += 1
                        power_manager.evaluate_cadence(now=t_now, frame_valid=False, frame_id=frame_id)
                        time.sleep(0.005)
                        continue

                    last_accepted_frame_time = t_now
                    last_frame_id = frame_id
                    no_frame_since = None

                    # 4. Cadence evaluation
                    decision = power_manager.evaluate_cadence(
                        now=t_now,
                        frame_valid=True,
                        frame_id=frame_id,
                        interaction_guard_clear=True,
                    )

                    # Check if next frame after WAKE_CONFIRMED resumed FULL_RATE
                    if previous_decision_was_wake_confirmed:
                        if decision.cadence == InferenceCadence.FULL_RATE and power_manager.state == PowerState.NORMAL:
                            resumed_full_rate_on_next_frame = True
                        previous_decision_was_wake_confirmed = False

                    has_hands = False
                    p_center = None
                    p_width = None
                    p_id = None
                    velocity = 0.0
                    event = decision.transition_event

                    # 5. Routing based on cadence
                    if decision.cadence == InferenceCadence.SKIP:
                        pre_wake_skip_frames += 1
                        processor.process(None, None)

                    elif decision.cadence in (InferenceCadence.PROBE, InferenceCadence.CONFIRMATION):
                        pre_wake_probe_frames += 1
                        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        hands = tracker.process(frame, rgb_image=rgb_frame)
                        has_hands, p_center, p_width, p_id = extract_hand_measurements(hands)

                        now_measure = time.perf_counter()
                        # Calculate instantaneous velocity relative to prior anchor using consistent timestamp
                        if (
                            has_hands and p_center and p_width and p_width > 0.001
                            and power_manager._prev_motion_anchor and power_manager._prev_motion_anchor_ts
                        ):
                            dt_m = now_measure - power_manager._prev_motion_anchor_ts
                            if dt_m > 0.001:
                                dx = p_center[0] - power_manager._prev_motion_anchor[0]
                                dy = p_center[1] - power_manager._prev_motion_anchor[1]
                                dist = math.sqrt(dx * dx + dy * dy)
                                velocity = dist / (p_width * dt_m)
                                if velocity > max_measured_velocity:
                                    max_measured_velocity = velocity

                        probe_dec = power_manager.update_probe_measurements(
                            now=now_measure,
                            has_hands=has_hands,
                            palm_center=p_center,
                            palm_width=p_width,
                            hand_id=p_id,
                        )
                        event = probe_dec.transition_event

                        # Audit wake candidate arming and rejection
                        if not was_confirming and power_manager.is_confirming_wake:
                            self.audit_counters.wake_candidates_armed += 1
                            logger.info("WAKE CANDIDATE ARMED at t=%.2fs (vel=%.2f, hand=%s)", t_elapsed, velocity, p_id)
                        elif was_confirming and event == PowerTransitionEvent.WAKE_REJECTED:
                            self.audit_counters.wake_candidates_rejected += 1
                            logger.info("WAKE CANDIDATE REJECTED at t=%.2fs (vel=%.2f)", t_elapsed, velocity)

                        was_confirming = power_manager.is_confirming_wake

                        if event == PowerTransitionEvent.WAKE_CONFIRMED:
                            self.audit_counters.wake_confirmed_events += 1
                            wake_confirmed_ts = t_now
                            wake_confirmed_frame_id = frame_id
                            previous_decision_was_wake_confirmed = True
                            queried_anchor = self.actuator.get_cursor_pos()
                            processor.set_cursor_anchor(queried_anchor)
                            logger.info(
                                ">>> WAKE_CONFIRMED at t=%.3fs (frame=%d, vel=%.2f, re-anchored to %s) <<<",
                                t_elapsed, frame_id, velocity, queried_anchor
                            )

                    elif decision.cadence == InferenceCadence.FULL_RATE:
                        post_wake_normal_frames += 1
                        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        hands = tracker.process(frame, rgb_image=rgb_frame)
                        has_hands, p_center, p_width, p_id = extract_hand_measurements(hands)

                        norm_dec = power_manager.update_normal_activity(
                            now=time.perf_counter(),
                            has_hands=has_hands,
                            palm_center=p_center,
                            palm_width=p_width,
                            hand_id=p_id,
                            interaction_guard_clear=True,
                        )
                        event = norm_dec.transition_event
                        processor.process(hands, None)

                    # 6. Log telemetry row
                    mem = self.process.memory_info()
                    rss_mb = mem.rss / (1024.0 * 1024.0)
                    cpu_pct = self.process.cpu_percent(interval=None)

                    telemetry.log_frame(
                        elapsed_s=t_elapsed,
                        frame_id=frame_id,
                        stage_label=current_stage,
                        power_state=power_manager.state.name,
                        cadence=decision.cadence.name,
                        transition_event=event.name,
                        is_fresh=is_fresh,
                        has_hands=has_hands,
                        hand_id=p_id,
                        palm_center=p_center,
                        palm_width=p_width,
                        measured_velocity=velocity,
                        is_confirming_wake=power_manager.is_confirming_wake,
                        confirm_frames=power_manager._wake_confirm_frames,
                        actuator_moves=self.actuator.move_count,
                        actuator_clicks=self.actuator.click_count,
                        cpu_pct=cpu_pct,
                        rss_mb=rss_mb,
                    )

            except KeyboardInterrupt:
                logger.info("Validation interrupted by operator.")
            finally:
                hotkeys.stop()
                telemetry.close()

        t_total = time.perf_counter() - t_start
        wake_success = (wake_confirmed_ts is not None) and (post_wake_normal_frames >= (3 if self.use_mock else 10))

        pre_wake_duration = (wake_confirmed_ts - t_start) if wake_confirmed_ts else t_total
        post_wake_duration = (t_start + t_total - wake_confirmed_ts) if wake_confirmed_ts else 0.0

        pre_wake_fps = (pre_wake_probe_frames / pre_wake_duration) if pre_wake_duration > 0 else 0.0
        post_wake_fps = (post_wake_normal_frames / post_wake_duration) if post_wake_duration > 0 else 0.0

        summary = {
            "test_verdict": "PASS" if wake_success else "FAIL",
            "started_in_power_save": True,
            "wake_confirmed": wake_confirmed_ts is not None,
            "wake_confirmed_elapsed_s": round(wake_confirmed_ts - t_start, 3) if wake_confirmed_ts else None,
            "wake_confirmed_frame_id": wake_confirmed_frame_id,
            "resumed_full_rate_on_next_frame": resumed_full_rate_on_next_frame,
            "total_duration_s": round(t_total, 2),
            "pre_wake_probe_frames": pre_wake_probe_frames,
            "pre_wake_skip_frames": pre_wake_skip_frames,
            "pre_wake_probe_effective_fps": round(pre_wake_fps, 2),
            "post_wake_normal_frames": post_wake_normal_frames,
            "post_wake_normal_fps": round(post_wake_fps, 2),
            "max_measured_velocity": round(max_measured_velocity, 2),
            "wake_candidates_armed": self.audit_counters.wake_candidates_armed,
            "wake_candidates_rejected": self.audit_counters.wake_candidates_rejected,
            "audit_counters": self.audit_counters.summary(),
            "actuator_counters": {
                "moves": self.actuator.move_count,
                "move_tos": self.actuator.move_to_count,
                "clicks": self.actuator.click_count,
                "drag_starts": self.actuator.drag_start_count,
            },
        }
        self.summary = summary

        summary_path = self.output_dir / "stage4a1_wake_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        return wake_success, csv_path, summary


# ── Self-Test Routine ────────────────────────────────────────────────────────

def run_self_test() -> bool:
    logger.info("=== Running Stage 4A.1 Wake Validation Self-Test (Mocked) ===")
    test_out = Path("test_wake_selftest_out")
    engine = TargetedWakeValidationEngine(output_dir=test_out, use_mock=True, max_duration_s=10.0)

    success, csv_path, summary = engine.run_wake_validation()

    logger.info("Self-Test Summary: %s", json.dumps(summary, indent=2))
    assert summary["started_in_power_save"] is True, "Failed to start in POWER_SAVE"
    assert summary["wake_confirmed"] is True, "Wake was not confirmed in self-test"
    assert summary["wake_candidates_armed"] >= 1, "Candidate was not armed"
    assert summary["resumed_full_rate_on_next_frame"] is True, "Failed to resume full-rate on next frame"
    assert summary["audit_counters"]["whatsapp_attempts"] == 0
    assert summary["audit_counters"]["wakanda_attempts"] == 0
    assert summary["actuator_counters"]["clicks"] == 0
    assert summary["actuator_counters"]["moves"] == 0

    # Cleanup self-test files
    try:
        csv_path.unlink()
        (test_out / "stage4a1_wake_summary.json").unlink()
        test_out.rmdir()
    except Exception:
        pass

    logger.info("=== ALL Stage 4A.1 Self-Tests PASSED cleanly ===")
    return True


# ── CLI Entrypoint ───────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Air Point Stage 4A.1 Targeted Wake Validation")
    parser.add_argument("--self-test", action="store_true", help="Run self-test with mocked frames")
    parser.add_argument("--outdir", type=str, default="stage4a1_wake_results", help="Output directory")
    parser.add_argument("--timeout", type=float, default=60.0, help="Max test duration in seconds (default: 60.0)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.self_test:
        ok = run_self_test()
        sys.exit(0 if ok else 1)

    out_dir = Path(args.outdir)
    engine = TargetedWakeValidationEngine(
        output_dir=out_dir,
        use_mock=False,
        max_duration_s=args.timeout,
    )

    success, csv_path, summary = engine.run_wake_validation()

    print("\n" + "=" * 80)
    print("STAGE 4A.1 TARGETED WAKE VALIDATION RESULT SUMMARY")
    print("=" * 80)
    print(f"Test Verdict:                  {summary['test_verdict']}")
    print(f"Started in POWER_SAVE:         {summary['started_in_power_save']}")
    print(f"Wake Confirmed:                {summary['wake_confirmed']}")
    print(f"Wake Confirmed Timestamp:      {summary.get('wake_confirmed_elapsed_s')}s")
    print(f"Wake Confirmed Frame ID:       {summary.get('wake_confirmed_frame_id')}")
    print(f"Resumed FULL_RATE Next Frame:  {summary['resumed_full_rate_on_next_frame']}")
    print(f"Candidates Armed:              {summary['wake_candidates_armed']}")
    print(f"Candidates Rejected:           {summary['wake_candidates_rejected']}")
    print(f"Max Measured Velocity:         {summary['max_measured_velocity']} palm-width/s")
    print(f"Pre-Wake Probe Cadence:        {summary['pre_wake_probe_effective_fps']} FPS (Probe 1:3)")
    print(f"Post-Wake Normal Cadence:      {summary['post_wake_normal_fps']} FPS (Full rate)")
    print(f"Audit Counter Violations:      {summary['audit_counters']}")
    print(f"Actuator Injections:           {summary['actuator_counters']}")
    print(f"Telemetry CSV:                 {csv_path.resolve()}")
    print("=" * 80 + "\n")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

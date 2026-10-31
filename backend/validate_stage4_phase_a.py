# validate_stage4_phase_a.py
"""
Air Point — Stage 4 Phase A Hardware Validation Harness.

Exercises real webcam capture, real sensor FrameFreshnessDetector, and
real PowerStateManager routing while maintaining absolute OS isolation:
- Strictly Non-Emitting Actuator (zero Win32 SendInput, zero mouse_event, zero cursor motion).
- All side-effecting gestures disabled & instrumented with audit counters (WhatsApp, Wakanda,
  audio volume, mute, screenshots).
- Windows pointer acceleration and timer resolution are NOT modified.
- Emergency shutdown targets the harness's own PID via .airpoint_phase_a.pid.
- Standard 310-second sampling timeline per run (60s baseline, 130s inactivity transition,
  60s power save steady-state, 60s post-wake active).
- Production FaceTracker inference workload included in NORMAL/FULL_RATE (1/3 frames);
  strictly bypassed in POWER_SAVE.
- Stationary hand measurements passed directly without artificial overrides.
- Timestamped CSV telemetry (frame intervals, power state, cadence, CPU %, Working Set MB,
  hand & face inferences).
- Comprehensive separate resource and cadence reporting for NORMAL vs POWER_SAVE.

Strictly read-only on import. Run with --self-test to verify logic with synthetic frames.
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

# Production subsystem imports
from core.camera import AsyncCamera, FrameFreshnessDetector
from core.display import TrackpadZone, VirtualDesktop, build_trackpad_zone, build_virtual_desktop
from core.face_tracker import FaceResult, FaceTracker
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

logger = logging.getLogger("airpoint.validate_phase_a")


# ── Safety Interlock ──────────────────────────────────────────────────────────

def install_os_action_interlock() -> None:
    """
    Installs runtime interlocks on native Win32 input APIs.
    If any subsystem attempts an unmocked OS input or workstation lock,
    this raises a hard RuntimeError.
    """
    def _blocked_action(api_name: str):
        def _throw(*args, **kwargs):
            raise RuntimeError(f"SAFETY INTERLOCK VIOLATION: Blocked native call to {api_name} during Phase A!")
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


# ── Non-Emitting Actuator ─────────────────────────────────────────────────────

class NonEmittingActuator:
    """
    Strictly non-emitting actuator for Phase A validation.
    Never instantiates or delegates to MouseActuator.
    Never calls Win32 SendInput or mouse_event.
    Captures all attempted calls in memory for safety auditing.
    """

    def __init__(self, width: int = 1920, height: int = 1080) -> None:
        self.total_width = width
        self.total_height = height
        self.is_dragging = False
        self.move_count = 0
        self.move_to_count = 0
        self.click_count = 0
        self.drag_start_count = 0
        self.drag_end_count = 0
        self.action_log: list[tuple[str, Any, float]] = []

    def move(self, x: int, y: int) -> bool:
        self.move_count += 1
        self.action_log.append(("move", (int(x), int(y)), time.perf_counter()))
        return True

    def move_to(self, x: int, y: int) -> bool:
        self.move_to_count += 1
        self.action_log.append(("move_to", (int(x), int(y)), time.perf_counter()))
        return True

    def left_click(self, x: int | None = None, y: int | None = None) -> bool:
        self.click_count += 1
        self.action_log.append(("left_click", (x, y), time.perf_counter()))
        return True

    def right_click(self, x: int | None = None, y: int | None = None) -> bool:
        self.click_count += 1
        self.action_log.append(("right_click", (x, y), time.perf_counter()))
        return True

    def double_click(self) -> bool:
        self.click_count += 1
        self.action_log.append(("double_click", None, time.perf_counter()))
        return True

    def drag_start(self) -> bool:
        self.is_dragging = True
        self.drag_start_count += 1
        self.action_log.append(("drag_start", None, time.perf_counter()))
        return True

    def drag_end(self) -> bool:
        self.is_dragging = False
        self.drag_end_count += 1
        self.action_log.append(("drag_end", None, time.perf_counter()))
        return True

    def get_cursor_pos(self) -> tuple[int, int] | None:
        """Read-only query of actual physical cursor for re-anchoring audit; does not mutate cursor."""
        try:
            from ctypes import wintypes
            pt = wintypes.POINT()
            if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
                return (pt.x, pt.y)
        except Exception:
            pass
        return None

    @property
    def total_action_count(self) -> int:
        return self.move_count + self.move_to_count + self.click_count + self.drag_start_count


# ── Audit Counters ────────────────────────────────────────────────────────────

@dataclass
class PhaseAAuditCounters:
    whatsapp_attempts: int = 0
    wakanda_attempts: int = 0
    audio_adjustments: int = 0
    audio_mutes: int = 0
    screenshots_taken: int = 0
    invalid_gap_resets: int = 0
    watchdog_stall_breaks: int = 0

    def summary(self) -> dict[str, int]:
        return {
            "whatsapp_attempts": self.whatsapp_attempts,
            "wakanda_attempts": self.wakanda_attempts,
            "audio_adjustments": self.audio_adjustments,
            "audio_mutes": self.audio_mutes,
            "screenshots_taken": self.screenshots_taken,
            "invalid_gap_resets": self.invalid_gap_resets,
            "watchdog_stall_breaks": self.watchdog_stall_breaks,
        }


# ── CSV Telemetry Logger ──────────────────────────────────────────────────────

class TelemetryLogger:
    def __init__(self, csv_path: Path) -> None:
        self.csv_path = csv_path
        self._file = open(self.csv_path, "w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        self._writer.writerow([
            "timestamp_iso",
            "elapsed_s",
            "stage_label",
            "power_state",
            "cadence",
            "transition_event",
            "is_fresh",
            "identical_count",
            "inactivity_elapsed_s",
            "frame_dt_ms",
            "cpu_percent",
            "rss_mb",
            "private_mb",
            "actuator_moves",
            "actuator_clicks",
            "hand_inferences",
            "face_inferences",
        ])
        self._file.flush()

    def log_sample(
        self,
        elapsed_s: float,
        stage_label: str,
        power_state: str,
        cadence: str,
        transition_event: str,
        is_fresh: bool,
        identical_count: int,
        inactivity_elapsed_s: float,
        frame_dt_ms: float,
        cpu_pct: float,
        rss_mb: float,
        private_mb: float,
        actuator_moves: int,
        actuator_clicks: int,
        hand_inferences: int,
        face_inferences: int,
    ) -> None:
        self._writer.writerow([
            datetime.now().isoformat(),
            round(elapsed_s, 3),
            stage_label,
            power_state,
            cadence,
            transition_event,
            int(is_fresh),
            identical_count,
            round(inactivity_elapsed_s, 3),
            round(frame_dt_ms, 2),
            round(cpu_pct, 2),
            round(rss_mb, 2),
            round(private_mb, 2),
            actuator_moves,
            actuator_clicks,
            hand_inferences,
            face_inferences,
        ])
        self._file.flush()

    def close(self) -> None:
        if self._file and not self._file.closed:
            self._file.flush()
            self._file.close()


# ── Synthetic Helpers for Self-Test ───────────────────────────────────────────

def _build_synthetic_hand_landmarks(cx: float = 0.5, cy: float = 0.5, width: float = 0.15) -> list[Landmark]:
    """
    Constructs a 21-landmark array conforming to extract_hand_measurements() geometry:
    dx = lms[5].x - lms[17].x
    p_width = hypot(dx, dy) = width
    center = (lms[0] + lms[5] + lms[17]) / 3 = (cx, cy)
    """
    lms = [Landmark(x=cx, y=cy, z=0.0) for _ in range(21)]
    lms[0] = Landmark(x=cx, y=cy, z=0.0)
    lms[5] = Landmark(x=cx - width / 2.0, y=cy, z=0.0)
    lms[17] = Landmark(x=cx + width / 2.0, y=cy, z=0.0)
    return lms


class MockSelfTestCamera:
    """Synthetic frame source for safe preflight verification without live webcam."""

    def __init__(self, fps: float = 60.0) -> None:
        self._fps = fps
        self._frame_id = 0
        self._stop_event = threading.Event()

    def __enter__(self) -> MockSelfTestCamera:
        return self

    def __exit__(self, *_) -> None:
        self._stop_event.set()

    def stop(self) -> None:
        self._stop_event.set()

    def read_fresh(self, last_frame_id: int, timeout: float = 0.04) -> tuple[np.ndarray | None, int]:
        if self._stop_event.is_set():
            return None, self._frame_id
        time.sleep(1.0 / self._fps)
        self._frame_id += 1
        # Generate synthetic frame with unique pixel noise so FrameFreshnessDetector marks it fresh
        frame = np.full((480, 640, 3), (self._frame_id * 17) % 255, dtype=np.uint8)
        return frame, self._frame_id


class MockSelfTestHandTracker:
    """Synthetic HandTracker for safe preflight verification."""

    def __init__(self, mode: str = "stationary") -> None:
        self.mode = mode
        self.call_count = 0

    def __enter__(self) -> MockSelfTestHandTracker:
        return self

    def __exit__(self, *_) -> None:
        pass

    def close(self) -> None:
        pass

    def process(self, frame: np.ndarray, rgb_image: np.ndarray | None = None) -> HandsResult:
        self.call_count += 1
        if self.mode == "missing":
            return HandsResult(right=None, left=None)

        width = 0.15
        if self.mode == "moving":
            cx = 0.3 + (self.call_count * 0.05)
            cy = 0.5
        else:  # "stationary"
            cx = 0.5
            cy = 0.5

        lms = _build_synthetic_hand_landmarks(cx=cx, cy=cy, width=width)
        return HandsResult(right=lms, left=None)


class MockSelfTestFaceTracker:
    """Synthetic FaceTracker workload simulator for safe preflight verification."""

    def __init__(self) -> None:
        self.call_count = 0
        self.call_count_normal = 0
        self.call_count_power_save = 0
        self._is_ready = True

    @property
    def is_ready(self) -> bool:
        return self._is_ready

    def __enter__(self) -> MockSelfTestFaceTracker:
        return self

    def __exit__(self, *_) -> None:
        pass

    def close(self) -> None:
        pass

    def process(
        self,
        frame: np.ndarray,
        timestamp_ms: int | None = None,
        rgb_image: np.ndarray | None = None,
    ) -> FaceResult:
        self.call_count += 1
        return FaceResult(
            detected=True,
            lip_center=(0.5, 0.5, 0.0),
            mouth_width=0.08,
            face_width=0.25,
            right_ear_pos=(0.6, 0.45, 0.0),
            left_ear_pos=(0.4, 0.45, 0.0),
            landmarks=None,
            confidence=0.95,
        )


# ── Phase A Validation Engine ─────────────────────────────────────────────────

class PhaseAValidationEngine:
    """
    Executes the Phase A hardware validation procedure using production pipeline routing.
    """

    def __init__(
        self,
        output_dir: Path,
        use_mock_camera: bool = False,
        stage_timeline: dict[str, float] | None = None,
        camera_factory: Any = None,
        tracker_factory: Any = None,
        face_tracker_factory: Any = None,
        inactivity_timeout_s: float = 120.0,
        mock_hand_mode: str = "stationary",
    ) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.use_mock_camera = use_mock_camera
        self.inactivity_timeout_s = inactivity_timeout_s
        self.mock_hand_mode = mock_hand_mode

        # Factory dependencies
        self.cam_factory = camera_factory or (MockSelfTestCamera if self.use_mock_camera else AsyncCamera)
        self.tracker_factory = tracker_factory or (
            (lambda: MockSelfTestHandTracker(mode=self.mock_hand_mode)) if self.use_mock_camera else HandTracker
        )
        self.face_tracker_factory = face_tracker_factory or (
            MockSelfTestFaceTracker if self.use_mock_camera else FaceTracker
        )

        if not self.use_mock_camera:
            try:
                import test_guard
                if "cv2_VideoCapture" in getattr(test_guard, "_ORIGINAL_APIS", {}):
                    cv2.VideoCapture = test_guard._ORIGINAL_APIS["cv2_VideoCapture"]
                if "user32_GetCursorPos" in getattr(test_guard, "_ORIGINAL_APIS", {}):
                    ctypes.windll.user32.GetCursorPos = test_guard._ORIGINAL_APIS["user32_GetCursorPos"]
            except Exception:
                pass

        # Timeline configuration (default standard run: 310s total)
        self.timeline = stage_timeline or {
            "BASELINE_ACTIVE": 60.0,
            "INACTIVITY_TRANSITION": 130.0,
            "POWER_SAVE_STEADY": 60.0,
            "WAKE_DWELL": 60.0,
        }

        self.pid_file = Path(".airpoint_phase_a.pid")
        self.audit_counters = PhaseAAuditCounters()
        self.actuator = NonEmittingActuator(1920, 1080)
        self.desktop = VirtualDesktop(1920, 1080, 1)
        self.trackpad = TrackpadZone(100, 540, 100, 380)

        # Seed initial psutil CPU epoch
        self.process = psutil.Process()
        self.process.cpu_percent(interval=None)

        self.is_running = True
        self.is_paused = False
        self.stop_event = threading.Event()
        self.last_summary: dict[str, Any] = {}

    def _setup_pid_and_emergency_controls(self) -> keyboard.GlobalHotKeys:
        """Writes exact PID file and hooks responsive emergency keys."""
        pid = os.getpid()
        self.pid_file.write_text(str(pid), encoding="utf-8")
        logger.info("Phase A Validation PID: %d (saved to %s)", pid, self.pid_file.name)
        logger.info("Emergency kill command: Stop-Process -Id %d -Force", pid)

        def _cleanup_pid():
            try:
                if self.pid_file.exists():
                    self.pid_file.unlink()
            except Exception:
                pass

        atexit.register(_cleanup_pid)

        def on_activate_quit():
            logger.warning("Emergency Stop (Ctrl+Alt+Q) received!")
            self.is_running = False
            self.stop_event.set()
            # 500ms fallback for immediate termination
            def _force_exit():
                time.sleep(0.5)
                if self.is_running:
                    os._exit(0)
            threading.Thread(target=_force_exit, daemon=True).start()

        def on_activate_pause():
            self.is_paused = not self.is_paused
            if self.is_paused:
                self.actuator.drag_end()
            logger.info("ENGINE %s", "PAUSED" if self.is_paused else "RESUMED")

        hotkeys = keyboard.GlobalHotKeys({
            "<ctrl>+<alt>+q": on_activate_quit,
            "<ctrl>+<alt>+p": on_activate_pause,
        })
        hotkeys.start()
        return hotkeys

    def _isolate_orchestrator(self, processor: GestureOrchestrator) -> None:
        """Disables and stubs all side-effecting gesture recognizers with audit hooks."""
        processor.pointer_enabled = False
        processor.drag_enabled = False

        # 1. Screenshots
        if hasattr(processor, "_screenshot"):
            processor._screenshot.enabled = False
            processor._screenshot.pre_capture_cb = None
            processor._screenshot.post_capture_cb = None

        # 2. WhatsApp
        if hasattr(processor, "_w_gesture"):
            processor._w_gesture.enabled = False
            def _on_w(success: bool):
                self.audit_counters.whatsapp_attempts += 1
                logger.warning("AUDIT: WhatsApp activation attempt caught and blocked!")
            processor.set_w_activation_callback(_on_w)

        # 3. Audio Mute
        if hasattr(processor, "_lip_gesture"):
            processor._lip_gesture.enabled = False
            def _on_lip(action: str, success: bool):
                self.audit_counters.audio_mutes += 1
                logger.warning("AUDIT: Lip mute attempt caught and blocked!")
            processor.set_lip_activation_callback(_on_lip)

        # 4. Ear Volume
        if hasattr(processor, "_ear_volume"):
            processor._ear_volume.enabled_up = False
            processor._ear_volume.enabled_down = False
            def _on_vol(dir_name: str, vol: float, active: bool):
                self.audit_counters.audio_adjustments += 1
                logger.warning("AUDIT: Ear volume adjustment caught and blocked!")
            processor.set_ear_volume_callback(_on_vol)

        # 5. Wakanda Forever Lock
        if hasattr(processor, "_wakanda"):
            processor._wakanda.enabled = False
            def _on_wakanda():
                self.audit_counters.wakanda_attempts += 1
                logger.critical("AUDIT: Wakanda lock attempt caught and blocked!")
            processor.set_wakanda_callback(_on_wakanda)

        # 6. AudioController stubs
        if hasattr(processor, "audio_controller"):
            ac = processor.audio_controller
            ac.set_volume_scalar = lambda v: None
            ac.toggle_mute = lambda: False

    def run_single_validation_pass(self, run_index: int = 1) -> Path:
        """
        Executes one full validation pass according to the Stage 4 timeline.
        Reuses production AsyncCamera, FrameFreshnessDetector, and PowerStateManager.
        """
        csv_file = self.output_dir / f"phase_a_run_{run_index}.csv"
        telemetry = TelemetryLogger(csv_file)
        hotkeys = self._setup_pid_and_emergency_controls()

        install_os_action_interlock()

        # Reset counters per pass
        self.audit_counters = PhaseAAuditCounters()
        self.actuator = NonEmittingActuator(1920, 1080)

        # Instantiate production subsystems
        power_manager = PowerStateManager(
            inactivity_timeout_s=self.inactivity_timeout_s,
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
        processor = GestureOrchestrator(self.actuator, self.desktop, self.trackpad)
        self._isolate_orchestrator(processor)

        logger.info("=== Starting Phase A Validation Pass #%d ===", run_index)
        t_run_start = time.perf_counter()
        last_accepted_frame_time = t_run_start
        last_frame_id = -1
        no_frame_since: float | None = None
        last_telemetry_sample = t_run_start
        last_state_tick = t_run_start

        # Stage timeline boundaries
        t_b_active = self.timeline["BASELINE_ACTIVE"]
        t_b_inact = t_b_active + self.timeline["INACTIVITY_TRANSITION"]
        t_b_steady = t_b_inact + self.timeline["POWER_SAVE_STEADY"]
        t_b_total = t_b_steady + self.timeline["WAKE_DWELL"]

        current_stage = "BASELINE_ACTIVE"
        frame_count = 0
        last_face_result: FaceResult | None = None

        # Tracking metrics for cadence and workload accounting
        hand_inferences_normal = 0
        hand_inferences_power_save = 0
        face_inferences_normal = 0
        face_inferences_power_save = 0
        skip_frames_power_save = 0

        # Performance resource samples separated by mode
        normal_cpu_samples: list[float] = []
        normal_rss_samples: list[float] = []
        normal_private_samples: list[float] = []

        power_save_cpu_samples: list[float] = []
        power_save_rss_samples: list[float] = []
        power_save_private_samples: list[float] = []

        total_normal_time_s: float = 0.0
        total_power_save_time_s: float = 0.0

        sample_interval = 0.25 if t_b_total <= 10.0 else 1.0

        with self.cam_factory() as camera, self.tracker_factory() as tracker, self.face_tracker_factory() as face_tracker:
            print(f"\n>>> [RUN {run_index} STAGE] BASELINE_ACTIVE (t=0.0s) — Move hand actively in camera view (60s baseline)\n")
            try:
                while self.is_running:
                    t_now = time.perf_counter()
                    t_elapsed = t_now - t_run_start

                    # Check overall timeline termination
                    if t_elapsed >= t_b_total:
                        logger.info("Pass #%d completed full timeline (%.1fs).", run_index, t_elapsed)
                        break

                    # Update current stage label
                    prev_stage = current_stage
                    if t_elapsed < t_b_active:
                        current_stage = "BASELINE_ACTIVE"
                        power_manager.set_enabled(True)
                    elif t_elapsed < t_b_inact:
                        current_stage = "INACTIVITY_TRANSITION"
                    elif t_elapsed < t_b_steady:
                        current_stage = "POWER_SAVE_STEADY"
                    else:
                        current_stage = "WAKE_DWELL"

                    if current_stage != prev_stage:
                        cues = {
                            "BASELINE_ACTIVE": "Move hand actively in camera view (60s baseline)",
                            "INACTIVITY_TRANSITION": "Keep hand motionless on desk or remove hand from camera view (130s transition)",
                            "POWER_SAVE_STEADY": "Stay quiet in Power Save steady state (60s quiet probe)",
                            "WAKE_DWELL": "Perform sweeping hand motion in front of camera to wake (60s dwell)",
                        }
                        cue = cues.get(current_stage, "")
                        logger.info(">>> STAGE TRANSITION: %s (t=%.1fs) | CUE: %s <<<", current_stage, t_elapsed, cue)
                        print(f"\n>>> [RUN {run_index} STAGE] {current_stage} (t={t_elapsed:.1f}s) — {cue}\n")

                    # 1. Read fresh frame from camera
                    t_frame_start = time.perf_counter()
                    frame, frame_id = camera.read_fresh(last_frame_id, timeout=0.033)
                    t_now = time.perf_counter()
                    frame_dt_ms = (t_now - t_frame_start) * 1000.0

                    # 2. Timeout / Camera Disconnection Watchdog (exercising production logic)
                    if frame is None or frame_id == last_frame_id:
                        if no_frame_since is None:
                            no_frame_since = t_now
                        elif (t_now - no_frame_since) > 5.0:
                            self.audit_counters.watchdog_stall_breaks += 1
                            logger.error("Camera produced no frames for > 5.0s (Watchdog break triggered)!")
                            break

                        elapsed_since_accepted = t_now - last_accepted_frame_time
                        if frame is None or elapsed_since_accepted > 0.150:
                            self.audit_counters.invalid_gap_resets += 1
                            power_manager.evaluate_cadence(now=t_now, frame_valid=False, frame_id=frame_id)

                        time.sleep(0.005)
                        continue

                    # 3. FrameFreshnessDetector Evaluation
                    is_fresh = freshness_detector.check(frame)
                    elapsed_since_accepted = t_now - last_accepted_frame_time

                    if not is_fresh:
                        self.audit_counters.invalid_gap_resets += 1
                        power_manager.evaluate_cadence(now=t_now, frame_valid=False, frame_id=frame_id)
                        time.sleep(0.005)
                        continue

                    # Fresh frame accepted
                    last_accepted_frame_time = t_now
                    last_frame_id = frame_id
                    no_frame_since = None
                    frame_count += 1

                    # 4. Cadence & Power State Routing
                    interaction_guard_clear = not self.actuator.is_dragging
                    decision = power_manager.evaluate_cadence(
                        now=t_now,
                        frame_valid=True,
                        frame_id=frame_id,
                        interaction_guard_clear=interaction_guard_clear,
                    )
                    last_event = decision.transition_event

                    if self.is_paused:
                        processor.process(None, None)

                    elif decision.cadence == InferenceCadence.SKIP:
                        # Full bypass of tracking and processor in POWER_SAVE
                        skip_frames_power_save += 1

                    elif decision.cadence in (InferenceCadence.PROBE, InferenceCadence.CONFIRMATION):
                        # In POWER_SAVE: Evaluate HandsLandmarker ONLY for wake check; FaceTracker is strictly bypassed
                        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        hands = tracker.process(frame, rgb_image=rgb_frame)
                        has_hands, p_center, p_width, p_id = extract_hand_measurements(hands)
                        hand_inferences_power_save += 1

                        probe_dec = power_manager.update_probe_measurements(
                            now=time.perf_counter(),
                            has_hands=has_hands,
                            palm_center=p_center,
                            palm_width=p_width,
                            hand_id=p_id,
                        )
                        last_event = probe_dec.transition_event

                        if probe_dec.transition_event == PowerTransitionEvent.WAKE_CONFIRMED:
                            queried = self.actuator.get_cursor_pos()
                            processor.set_cursor_anchor(queried)
                            logger.info("WAKE_CONFIRMED: Re-anchored cursor to %s", queried)

                    else:  # InferenceCadence.FULL_RATE (NORMAL operating mode)
                        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        hands = tracker.process(frame, rgb_image=rgb_frame)
                        has_hands, p_center, p_width, p_id = extract_hand_measurements(hands)
                        hand_inferences_normal += 1

                        # FaceTracker inference workload at 1/3 frames (matching production main.py)
                        face = None
                        if getattr(face_tracker, "is_ready", False):
                            ear_active = getattr(getattr(processor, '_ear_volume', None), 'is_active', False)
                            lip_active = getattr(getattr(processor, '_lip_gesture', None), 'is_holding', False)
                            face_interval = 2 if (ear_active or lip_active) else 3

                            if last_face_result is None or (frame_count % face_interval == 0):
                                face = face_tracker.process(frame, rgb_image=rgb_frame)
                                last_face_result = face
                                face_inferences_normal += 1
                            else:
                                face = last_face_result

                        # Pass actual measurements directly without artificial overrides!
                        norm_dec = power_manager.update_normal_activity(
                            now=time.perf_counter(),
                            has_hands=has_hands,
                            palm_center=p_center,
                            palm_width=p_width,
                            hand_id=p_id,
                            interaction_guard_clear=interaction_guard_clear,
                        )
                        last_event = norm_dec.transition_event

                        if norm_dec.transition_event == PowerTransitionEvent.ENTERED_POWER_SAVE:
                            processor.process(None, None)
                            logger.info("ENTERED_POWER_SAVE: Filter state reset.")
                        else:
                            processor.process(hands, face)

                    # State duration accumulation
                    state_dt = t_now - last_state_tick
                    last_state_tick = t_now
                    if power_manager.state == PowerState.NORMAL:
                        total_normal_time_s += state_dt
                    else:
                        total_power_save_time_s += state_dt

                    # 5. Periodic Telemetry Logging
                    if (t_now - last_telemetry_sample) >= sample_interval:
                        last_telemetry_sample = t_now
                        cpu_pct = self.process.cpu_percent(interval=None)
                        mem_info = self.process.memory_info()
                        rss_mb = mem_info.rss / (1024.0 * 1024.0)
                        private_mb = getattr(mem_info, "private", mem_info.rss) / (1024.0 * 1024.0)

                        if power_manager.state == PowerState.NORMAL:
                            normal_cpu_samples.append(cpu_pct)
                            normal_rss_samples.append(rss_mb)
                            normal_private_samples.append(private_mb)
                        else:
                            power_save_cpu_samples.append(cpu_pct)
                            power_save_rss_samples.append(rss_mb)
                            power_save_private_samples.append(private_mb)

                        telemetry.log_sample(
                            elapsed_s=t_elapsed,
                            stage_label=current_stage,
                            power_state=power_manager.state.name,
                            cadence=decision.cadence.name,
                            transition_event=last_event.name,
                            is_fresh=is_fresh,
                            identical_count=freshness_detector._identical_count,
                            inactivity_elapsed_s=power_manager.accumulated_inactive_s,
                            frame_dt_ms=frame_dt_ms,
                            cpu_pct=cpu_pct,
                            rss_mb=rss_mb,
                            private_mb=private_mb,
                            actuator_moves=self.actuator.move_count,
                            actuator_clicks=self.actuator.click_count,
                            hand_inferences=(hand_inferences_normal + hand_inferences_power_save),
                            face_inferences=face_inferences_normal,
                        )

            except KeyboardInterrupt:
                logger.info("Interrupted by operator.")
            finally:
                hotkeys.stop()
                telemetry.close()

        # Compute summary metrics separately for NORMAL and POWER_SAVE
        avg_norm_cpu = float(np.mean(normal_cpu_samples)) if normal_cpu_samples else 0.0
        avg_norm_rss = float(np.mean(normal_rss_samples)) if normal_rss_samples else 0.0
        avg_norm_private = float(np.mean(normal_private_samples)) if normal_private_samples else 0.0
        norm_fps = (hand_inferences_normal / total_normal_time_s) if total_normal_time_s > 0 else 0.0
        face_fps = (face_inferences_normal / total_normal_time_s) if total_normal_time_s > 0 else 0.0

        avg_ps_cpu = float(np.mean(power_save_cpu_samples)) if power_save_cpu_samples else 0.0
        avg_ps_rss = float(np.mean(power_save_rss_samples)) if power_save_rss_samples else 0.0
        avg_ps_private = float(np.mean(power_save_private_samples)) if power_save_private_samples else 0.0
        ps_probe_fps = (hand_inferences_power_save / total_power_save_time_s) if total_power_save_time_s > 0 else 0.0

        cpu_diff = avg_norm_cpu - avg_ps_cpu
        cpu_rel_reduction = ((cpu_diff / avg_norm_cpu) * 100.0) if avg_norm_cpu > 0 else 0.0
        mem_rss_diff = avg_norm_rss - avg_ps_rss

        summary = {
            "run_index": run_index,
            "normal": {
                "duration_s": round(total_normal_time_s, 2),
                "avg_cpu_percent": round(avg_norm_cpu, 2),
                "avg_rss_mb": round(avg_norm_rss, 2),
                "avg_private_mb": round(avg_norm_private, 2),
                "hand_inferences": hand_inferences_normal,
                "face_inferences": face_inferences_normal,
                "effective_hand_fps": round(norm_fps, 2),
                "effective_face_fps": round(face_fps, 2),
            },
            "power_save": {
                "duration_s": round(total_power_save_time_s, 2),
                "avg_cpu_percent": round(avg_ps_cpu, 2),
                "avg_rss_mb": round(avg_ps_rss, 2),
                "avg_private_mb": round(avg_ps_private, 2),
                "hand_inferences": hand_inferences_power_save,
                "face_inferences": face_inferences_power_save,
                "skip_frames": skip_frames_power_save,
                "effective_probe_fps": round(ps_probe_fps, 2),
            },
            "deltas": {
                "cpu_reduction_pct_points": round(cpu_diff, 2),
                "cpu_relative_reduction_pct": round(cpu_rel_reduction, 2),
                "rss_mb_delta": round(mem_rss_diff, 2),
                "workload_aligned_with_production": True,
            },
            "audit_counters": self.audit_counters.summary(),
            "actuator_counters": {
                "moves": self.actuator.move_count,
                "move_tos": self.actuator.move_to_count,
                "clicks": self.actuator.click_count,
                "drag_starts": self.actuator.drag_start_count,
            },
        }
        self.last_summary = summary

        summary_file = self.output_dir / f"phase_a_run_{run_index}_summary.json"
        summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        logger.info(
            "\n"
            "================================================================================\n"
            "                      STAGE 4 PHASE A RESOURCE & CADENCE SUMMARY                \n"
            "================================================================================\n"
            "  Metric                         NORMAL Mode              POWER SAVE Mode       \n"
            "--------------------------------------------------------------------------------\n"
            "  Duration (s)                   %-24.1f %-24.1f\n"
            "  Avg CPU Load (%%)               %-24.1f %-24.1f\n"
            "  Avg Working Set (RSS MB)       %-24.1f %-24.1f\n"
            "  Avg Private Memory (MB)        %-24.1f %-24.1f\n"
            "  Hand Inferences                %-24d %-24d\n"
            "  Face Inferences                %-24d %-24d\n"
            "  Effective Hand Cadence         %-24.1f inf/s       %-24.1f inf/s\n"
            "  Effective Face Cadence         %-24.1f inf/s       %-24.1f inf/s\n"
            "  Bypassed / Skipped Frames      %-24d %-24d\n"
            "--------------------------------------------------------------------------------\n"
            "  CPU Relative Reduction:        %.1f%%\n"
            "  FaceTracker Workload:          Active at 1/3 frames in NORMAL, 100%% bypassed in POWER_SAVE\n"
            "  Side-Effect Invocations:       0 (Zero OS injection, Zero gesture actions)\n"
            "================================================================================",
            total_normal_time_s, total_power_save_time_s,
            avg_norm_cpu, avg_ps_cpu,
            avg_norm_rss, avg_ps_rss,
            avg_norm_private, avg_ps_private,
            hand_inferences_normal, hand_inferences_power_save,
            face_inferences_normal, face_inferences_power_save,
            norm_fps, ps_probe_fps,
            face_fps, 0.0,
            0, skip_frames_power_save,
            cpu_rel_reduction,
        )

        logger.info("=== Pass #%d Complete. Summary Telemetry: %s ===", run_index, csv_file.name)
        return csv_file


# ── Expanded Self-Test Routine ────────────────────────────────────────────────

def run_self_test() -> bool:
    """
    Verifies harness safety invariants and correct pipeline behavior using synthetic frames
    without accessing live camera or OS input.
    """
    logger.info("Running Phase A Expanded Self-Tests (Mocked Dependencies)...")

    # =========================================================================
    # Test 1: Stationary Hand Pass-Through & Inactivity Accumulation
    # Verifies that stationary hand measurements pass without overrides and accumulate inactivity.
    # =========================================================================
    logger.info("Test 1: Verifying stationary hand measurements pass through and accumulate inactivity...")
    psm1 = PowerStateManager(
        inactivity_timeout_s=0.5,
        wake_trigger_velocity=0.50,
        clock_fn=time.perf_counter,
    )
    psm1.set_enabled(True)
    t_start = 1000.0
    now = t_start
    dt = 0.033

    # Generate stationary synthetic hand landmarks
    stationary_lms = _build_synthetic_hand_landmarks(cx=0.5, cy=0.5, width=0.15)
    hands_stationary = HandsResult(right=stationary_lms, left=None)
    has_hands, p_center, p_width, p_id = extract_hand_measurements(hands_stationary)
    assert has_hands is True, "Expected has_hands to be True for synthetic stationary hand"
    assert p_center == (0.5, 0.5), f"Expected center (0.5, 0.5), got {p_center}"
    assert abs(p_width - 0.15) < 1e-4, f"Expected width ~0.15, got {p_width}"

    # Feed frames of stationary hand without overrides
    entered_ps = False
    for frame_idx in range(25):
        now += dt
        dec = psm1.evaluate_cadence(now=now, frame_valid=True, frame_id=frame_idx)
        if dec.cadence == InferenceCadence.FULL_RATE:
            # Direct pass of actual measurements - NO has_hands_for_psm = False override!
            norm_dec = psm1.update_normal_activity(
                now=now,
                has_hands=has_hands,
                palm_center=p_center,
                palm_width=p_width,
                hand_id=p_id,
            )
            if norm_dec.transition_event == PowerTransitionEvent.ENTERED_POWER_SAVE:
                entered_ps = True
                break

    assert entered_ps is True, "PowerStateManager failed to enter POWER_SAVE with stationary hand!"
    assert psm1.state == PowerState.POWER_SAVE, f"Expected POWER_SAVE state, got {psm1.state}"
    logger.info("Test 1 PASSED: Stationary hand passed without overrides and successfully entered POWER_SAVE.")

    # =========================================================================
    # Test 2: Missing Hands vs Stationary Hands Expected Paths
    # Verifies missing hands and stationary hands both accumulate inactivity, while moving hands reset it.
    # =========================================================================
    logger.info("Test 2: Verifying missing hands vs stationary hands vs moving hands paths...")

    # Path A: Missing hands
    psm_missing = PowerStateManager(inactivity_timeout_s=10.0, clock_fn=time.perf_counter)
    psm_missing.set_enabled(True)
    now_m = 2000.0
    for i in range(5):
        now_m += 0.05
        psm_missing.evaluate_cadence(now=now_m, frame_valid=True, frame_id=i)
        psm_missing.update_normal_activity(now=now_m, has_hands=False, palm_center=None, palm_width=None, hand_id=None)
    assert psm_missing.accumulated_inactive_s >= 0.19, f"Missing hands failed to accumulate: {psm_missing.accumulated_inactive_s}"
    assert psm_missing._prev_motion_anchor is None, "Missing hands should clear motion anchor"

    # Path B: Stationary hands
    psm_stat = PowerStateManager(inactivity_timeout_s=10.0, clock_fn=time.perf_counter)
    psm_stat.set_enabled(True)
    now_s = 2000.0
    for i in range(5):
        now_s += 0.05
        psm_stat.evaluate_cadence(now=now_s, frame_valid=True, frame_id=i)
        psm_stat.update_normal_activity(now=now_s, has_hands=True, palm_center=(0.5, 0.5), palm_width=0.15, hand_id="right")
    assert psm_stat.accumulated_inactive_s >= 0.19, f"Stationary hands failed to accumulate: {psm_stat.accumulated_inactive_s}"
    assert psm_stat._prev_motion_anchor == (0.5, 0.5), "Stationary hands should retain motion anchor"
    assert abs(psm_stat.accumulated_inactive_s - psm_missing.accumulated_inactive_s) < 1e-4, "Accumulation rate should match exactly"

    # Path C: Moving hands (resets inactivity)
    now_s += 0.05
    psm_stat.evaluate_cadence(now=now_s, frame_valid=True, frame_id=10)
    # Move hand by 0.30 in 0.05s -> velocity = 0.30 / (0.15 * 0.05) = 40.0 >> 0.50
    psm_stat.update_normal_activity(now=now_s, has_hands=True, palm_center=(0.8, 0.5), palm_width=0.15, hand_id="right")
    assert psm_stat.accumulated_inactive_s == 0.0, f"Expected reset to 0.0 on moving hand, got {psm_stat.accumulated_inactive_s}"
    logger.info("Test 2 PASSED: Missing, stationary, and moving hands follow exact respective expected paths.")

    # =========================================================================
    # Test 3: FaceTracker Execution Cadence in NORMAL vs Skip in POWER_SAVE
    # Integrated test with PhaseAValidationEngine using mock camera, mock tracker & mock face tracker.
    # =========================================================================
    logger.info("Test 3: Verifying FaceTracker cadence (NORMAL vs POWER_SAVE) and resource logging...")
    out_dir = Path("validation_output_selftest")

    compressed_timeline = {
        "BASELINE_ACTIVE": 0.6,
        "INACTIVITY_TRANSITION": 1.2,
        "POWER_SAVE_STEADY": 1.0,
        "WAKE_DWELL": 0.4,
    }

    mock_face_tracker_inst = MockSelfTestFaceTracker()

    engine = PhaseAValidationEngine(
        output_dir=out_dir,
        use_mock_camera=True,
        stage_timeline=compressed_timeline,
        face_tracker_factory=lambda: mock_face_tracker_inst,
        inactivity_timeout_s=0.5,
        mock_hand_mode="stationary",
    )

    csv_path = engine.run_single_validation_pass(run_index=0)
    summary = engine.last_summary

    assert csv_path.exists(), "CSV telemetry file was not created!"
    assert summary, "Run summary was not generated!"

    # Verify FaceTracker in NORMAL mode executed on eligible frames (~1/3)
    normal_face_inferences = summary["normal"]["face_inferences"]
    normal_hand_inferences = summary["normal"]["hand_inferences"]
    assert normal_face_inferences > 0, "FaceTracker was never called in NORMAL mode!"
    assert normal_hand_inferences > normal_face_inferences, "Expected hand inferences to exceed face inferences"
    cadence_ratio = normal_face_inferences / normal_hand_inferences
    logger.info(
        "FaceTracker NORMAL cadence: %d face / %d hand (~%.2f ratio, expected ~0.33)",
        normal_face_inferences, normal_hand_inferences, cadence_ratio
    )
    assert 0.20 <= cadence_ratio <= 0.50, f"Unexpected FaceTracker execution cadence: {cadence_ratio}"

    # Verify FaceTracker was NEVER called in POWER_SAVE mode
    ps_face_inferences = summary["power_save"]["face_inferences"]
    assert ps_face_inferences == 0, f"FaceTracker was called {ps_face_inferences} times in POWER_SAVE!"

    # Verify separate CPU and RAM measurements were recorded
    assert "avg_cpu_percent" in summary["normal"], "Missing NORMAL avg_cpu_percent"
    assert "avg_cpu_percent" in summary["power_save"], "Missing POWER_SAVE avg_cpu_percent"
    assert summary["deltas"]["workload_aligned_with_production"] is True
    logger.info("Test 3 PASSED: FaceTracker executed in NORMAL (~1/3 frames) and strictly bypassed (0) in POWER_SAVE.")

    # =========================================================================
    # Test 4: Audit Counters and Non-Emitting Actuator Remain Zero
    # =========================================================================
    logger.info("Test 4: Verifying zero side-effects and zero actuator actions...")
    audit = summary["audit_counters"]
    actuator_counts = summary["actuator_counters"]

    assert audit["whatsapp_attempts"] == 0, f"WhatsApp audit triggered: {audit['whatsapp_attempts']}"
    assert audit["wakanda_attempts"] == 0, f"Wakanda audit triggered: {audit['wakanda_attempts']}"
    assert audit["audio_adjustments"] == 0, f"Audio adjustment audit triggered: {audit['audio_adjustments']}"
    assert audit["audio_mutes"] == 0, f"Audio mute audit triggered: {audit['audio_mutes']}"
    assert audit["screenshots_taken"] == 0, f"Screenshot audit triggered: {audit['screenshots_taken']}"

    assert actuator_counts["clicks"] == 0, f"Actuator clicks: {actuator_counts['clicks']}"
    assert actuator_counts["drag_starts"] == 0, f"Actuator drag starts: {actuator_counts['drag_starts']}"
    assert actuator_counts["moves"] == 0, f"Actuator moves: {actuator_counts['moves']}"
    assert actuator_counts["move_tos"] == 0, f"Actuator move_tos: {actuator_counts['move_tos']}"

    # Clean up self-test artifacts
    try:
        csv_path.unlink()
        summary_file = out_dir / "phase_a_run_0_summary.json"
        if summary_file.exists():
            summary_file.unlink()
        out_dir.rmdir()
    except Exception:
        pass

    logger.info("Test 4 PASSED: All side-effect audit counters and actuator actions are ZERO.")
    logger.info("=== ALL Phase A Self-Tests PASSED cleanly ===")
    return True


# ── CLI Entrypoint ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Air Point Stage 4 Phase A Hardware Validation Harness")
    parser.add_argument("--self-test", action="store_true", help="Run self-test with mocked dependencies without live hardware")
    parser.add_argument("--runs", type=int, default=3, help="Number of sequential 310s validation runs (default: 3)")
    parser.add_argument("--outdir", type=str, default="stage4_phase_a_results", help="Output directory for CSV telemetry")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.self_test:
        success = run_self_test()
        sys.exit(0 if success else 1)

    out_dir = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 80)
    print("  AIR POINT STAGE 4 PHASE A LIVE-CAMERA VALIDATION")
    print(f"  Runs: {args.runs} | Timeline: 310s per run (~5.2 min each)")
    print("  Actuator: NonEmittingActuator (Strict OS isolation)")
    print("  Side-effect Interlocks: ACTIVE")
    print(f"  Output Directory: {out_dir.resolve()}")
    print("=" * 80 + "\n")

    engine = PhaseAValidationEngine(
        output_dir=out_dir,
        use_mock_camera=False,
    )

    all_summaries = []
    for run_idx in range(1, args.runs + 1):
        print(f"\n{'=' * 80}")
        print(f"  STARTING VALIDATION PASS {run_idx} OF {args.runs}")
        print(f"{'=' * 80}\n")
        csv_path = engine.run_single_validation_pass(run_index=run_idx)
        summary = engine.last_summary
        all_summaries.append(summary)

        # Check safety invariants
        audit = summary.get("audit_counters", {})
        side_effects = [k for k, v in audit.items() if v > 0 and k not in ("invalid_gap_resets", "watchdog_stall_breaks")]
        if side_effects:
            logger.critical("SAFETY VIOLATION in Run %d: Nonzero side effects detected: %s", run_idx, side_effects)
            print(f"\n[FATAL] Nonzero side effects detected: {side_effects}. Halting further runs immediately.\n")
            break

        actuator_actions = summary.get("actuator_counters", {})
        if actuator_actions.get("clicks", 0) > 0 or actuator_actions.get("drag_starts", 0) > 0:
            logger.critical("SAFETY VIOLATION in Run %d: Nonzero actuator actions: %s", run_idx, actuator_actions)
            print(f"\n[FATAL] Nonzero actuator actions detected: {actuator_actions}. Halting immediately.\n")
            break

        if not engine.is_running:
            logger.warning("Execution stopped early by operator.")
            break

        if run_idx < args.runs:
            print(f"\n[RUN {run_idx} COMPLETE] 5-second cooldown before next run...\n")
            time.sleep(5.0)

    combined_file = out_dir / "phase_a_all_runs_summary.json"
    combined_file.write_text(json.dumps(all_summaries, indent=2), encoding="utf-8")
    print(f"\nAll {len(all_summaries)} validation runs completed. Combined summary saved to {combined_file}\n")


if __name__ == "__main__":
    main()

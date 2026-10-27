# core/power_state_machine.py
"""
Air Point — Pure Power State Machine.

Maintains two runtime states: NORMAL and POWER_SAVE.
Strictly decoupled from camera acquisition, MediaPipe inference, gesture
processing, actuator calls, networking, and OS input.

All time progression is driven by an injected monotonic clock.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class PowerState(Enum):
    NORMAL = "NORMAL"
    POWER_SAVE = "POWER_SAVE"


class InferenceCadence(Enum):
    FULL_RATE = "FULL_RATE"        # NORMAL mode: run hands + face + gesture/actuator dispatch
    PROBE = "PROBE"                # POWER_SAVE mode: evaluate hands ONLY for motion check
    CONFIRMATION = "CONFIRMATION"  # POWER_SAVE mode: full-rate hands ONLY across confirmation window
    SKIP = "SKIP"                  # POWER_SAVE mode: bypass cvtColor, hands, face, and gesture dispatch


class PowerTransitionEvent(Enum):
    NONE = "NONE"
    ENTERED_POWER_SAVE = "ENTERED_POWER_SAVE"  # NORMAL -> POWER_SAVE transition
    WAKE_CONFIRMED = "WAKE_CONFIRMED"          # POWER_SAVE -> NORMAL confirmed wake
    WAKE_REJECTED = "WAKE_REJECTED"            # Candidate dropped; resumes probe cadence
    FEATURE_DISABLED = "FEATURE_DISABLED"      # User toggled OFF; immediate return to NORMAL


@dataclass(frozen=True)
class PowerDecision:
    state: PowerState
    cadence: InferenceCadence
    transition_event: PowerTransitionEvent
    inactivity_elapsed_s: float
    is_confirming_wake: bool


class PowerStateManager:
    """
    Pure state manager governing the two-state Power Optimization runtime lifecycle.
    """

    def __init__(
        self,
        inactivity_timeout_s: float = 120.0,
        wake_trigger_velocity: float = 0.50,
        wake_confirm_velocity: float = 0.40,
        wake_confirm_duration_s: float = 0.15,
        wake_dwell_duration_s: float = 10.0,
        probe_stride: int = 3,
        min_confirm_frames: int = 3,
        max_healthy_frame_interval_s: float = 0.150,
        clock_fn: Callable[[], float] | None = None,
    ) -> None:
        self._inactivity_timeout_s = float(inactivity_timeout_s)
        self._wake_trigger_velocity = float(wake_trigger_velocity)
        self._wake_confirm_velocity = float(wake_confirm_velocity)
        self._wake_confirm_duration_s = float(wake_confirm_duration_s)
        self._wake_dwell_duration_s = float(wake_dwell_duration_s)
        self._probe_stride = max(1, int(probe_stride))
        self._min_confirm_frames = max(1, int(min_confirm_frames))
        self._max_healthy_frame_interval_s = float(max_healthy_frame_interval_s)
        self._clock_fn = clock_fn if clock_fn is not None else (lambda: 0.0)

        # Operational state
        self._state = PowerState.NORMAL
        self._enabled = False  # Defaults OFF (opt-in)
        self._probe_counter = 0

        # Inactivity accounting
        self._accumulated_inactive_s = 0.0
        self._last_healthy_frame_ts: float | None = None
        self._last_frame_id: int | None = None
        self._had_camera_gap = False
        self._last_frame_dt = 0.0

        # Motion anchors & Wake detection
        self._prev_motion_anchor: tuple[float, float] | None = None
        self._prev_motion_anchor_ts: float | None = None
        self._prev_motion_hand_id: str | None = None
        self._wake_candidate_start_ts: float | None = None
        self._wake_confirm_frames = 0
        self._wake_dwell_until_ts = 0.0

    # ── Configuration & State Queries ────────────────────────────────────────

    @property
    def state(self) -> PowerState:
        return self._state

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def accumulated_inactive_s(self) -> float:
        return self._accumulated_inactive_s

    @property
    def is_confirming_wake(self) -> bool:
        return self._wake_candidate_start_ts is not None

    def set_enabled(self, enabled: bool) -> PowerTransitionEvent:
        """
        Update the feature toggle. If toggled OFF while in POWER_SAVE,
        synchronously forces return to NORMAL.
        """
        new_val = bool(enabled)
        if self._enabled == new_val:
            return PowerTransitionEvent.NONE

        self._enabled = new_val
        if not self._enabled and self._state == PowerState.POWER_SAVE:
            self._state = PowerState.NORMAL
            self._wake_candidate_start_ts = None
            self._wake_confirm_frames = 0
            self._probe_counter = 0
            self._prev_motion_anchor = None
            self._prev_motion_anchor_ts = None
            self._prev_motion_hand_id = None
            return PowerTransitionEvent.FEATURE_DISABLED

        return PowerTransitionEvent.NONE

    def get_telemetry(self) -> dict[str, Any]:
        return {
            "power_state": self._state.value,
            "power_optimization_enabled": self._enabled,
            "accumulated_inactive_s": round(self._accumulated_inactive_s, 2),
            "is_confirming_wake": self.is_confirming_wake,
            "had_camera_gap": self._had_camera_gap,
        }

    # ── Phase 1: Pre-Inference Cadence Evaluation ────────────────────────────

    def evaluate_cadence(
        self,
        now: float | None = None,
        frame_valid: bool = True,
        frame_id: int = 0,
        interaction_guard_clear: bool = True,
    ) -> PowerDecision:
        """
        Evaluates frame delivery health, checks gap and stall status, and returns
        the required inference cadence for the current loop iteration.
        """
        current_now = self._clock_fn() if now is None else float(now)

        # 1. Camera Frame Failure / Explicit Gap / Suspected Freeze
        if not frame_valid:
            self._had_camera_gap = True
            self._accumulated_inactive_s = 0.0  # Immediate reset: breaks continuity
            self._prev_motion_anchor = None
            self._prev_motion_anchor_ts = None
            self._prev_motion_hand_id = None
            self._last_frame_dt = 0.0

            trans_event = PowerTransitionEvent.NONE
            if self._wake_candidate_start_ts is not None:
                self._wake_candidate_start_ts = None
                self._wake_confirm_frames = 0
                trans_event = PowerTransitionEvent.WAKE_REJECTED

            return PowerDecision(
                state=self._state,
                cadence=InferenceCadence.SKIP,
                transition_event=trans_event,
                inactivity_elapsed_s=0.0,
                is_confirming_wake=False,
            )

        # 2. Duplicate Consumer Frame ID (re-read or consumer timeout)
        if frame_id != 0 and self._last_frame_id is not None and frame_id == self._last_frame_id:
            self._last_frame_dt = 0.0
            return PowerDecision(
                state=self._state,
                cadence=InferenceCadence.SKIP,
                transition_event=PowerTransitionEvent.NONE,
                inactivity_elapsed_s=self._accumulated_inactive_s,
                is_confirming_wake=self.is_confirming_wake,
            )

        # 3. Healthy Recovery Frame Following Gap
        if self._had_camera_gap:
            self._had_camera_gap = False
            self._accumulated_inactive_s = 0.0
            self._last_healthy_frame_ts = current_now
            self._last_frame_id = frame_id
            self._prev_motion_anchor = None
            self._prev_motion_anchor_ts = None
            self._prev_motion_hand_id = None
            self._last_frame_dt = 0.0

            cadence = InferenceCadence.FULL_RATE if self._state == PowerState.NORMAL else InferenceCadence.SKIP
            return PowerDecision(
                state=self._state,
                cadence=cadence,
                transition_event=PowerTransitionEvent.NONE,
                inactivity_elapsed_s=0.0,
                is_confirming_wake=self.is_confirming_wake,
            )

        # 4. Inter-Frame Stall Check (gap exceeding 150ms continuity threshold)
        if self._last_healthy_frame_ts is not None:
            raw_dt = current_now - self._last_healthy_frame_ts
            if raw_dt > self._max_healthy_frame_interval_s:
                # Stall detected: continuity broken
                self._accumulated_inactive_s = 0.0
                self._last_healthy_frame_ts = current_now
                self._last_frame_id = frame_id
                self._prev_motion_anchor = None
                self._prev_motion_anchor_ts = None
                self._prev_motion_hand_id = None
                self._last_frame_dt = 0.0

                trans_event = PowerTransitionEvent.NONE
                if self._wake_candidate_start_ts is not None:
                    self._wake_candidate_start_ts = None
                    self._wake_confirm_frames = 0
                    trans_event = PowerTransitionEvent.WAKE_REJECTED

                cadence = InferenceCadence.FULL_RATE if self._state == PowerState.NORMAL else InferenceCadence.SKIP
                return PowerDecision(
                    state=self._state,
                    cadence=cadence,
                    transition_event=trans_event,
                    inactivity_elapsed_s=0.0,
                    is_confirming_wake=False,
                )

        # 5. Consecutive Healthy Frame Timing (clamped to max 50ms per frame)
        if self._last_healthy_frame_ts is not None:
            self._last_frame_dt = min(max(0.0, current_now - self._last_healthy_frame_ts), 0.050)
        else:
            self._last_frame_dt = 0.0
        self._last_healthy_frame_ts = current_now
        self._last_frame_id = frame_id

        # 6. Determine Cadence Based on Operating State
        if self._state == PowerState.NORMAL:
            return PowerDecision(
                state=self._state,
                cadence=InferenceCadence.FULL_RATE,
                transition_event=PowerTransitionEvent.NONE,
                inactivity_elapsed_s=self._accumulated_inactive_s,
                is_confirming_wake=False,
            )

        # In POWER_SAVE:
        if self._wake_candidate_start_ts is not None:
            return PowerDecision(
                state=self._state,
                cadence=InferenceCadence.CONFIRMATION,
                transition_event=PowerTransitionEvent.NONE,
                inactivity_elapsed_s=self._accumulated_inactive_s,
                is_confirming_wake=True,
            )

        # Probing schedule in POWER_SAVE
        self._probe_counter += 1
        if self._probe_counter % self._probe_stride == 0:
            cadence = InferenceCadence.PROBE
        else:
            cadence = InferenceCadence.SKIP

        return PowerDecision(
            state=self._state,
            cadence=cadence,
            transition_event=PowerTransitionEvent.NONE,
            inactivity_elapsed_s=self._accumulated_inactive_s,
            is_confirming_wake=False,
        )

    # ── Phase 2: Post-Inference Measurement Updates ──────────────────────────

    def update_normal_activity(
        self,
        now: float | None = None,
        has_hands: bool = False,
        palm_center: tuple[float, float] | None = None,
        palm_width: float | None = None,
        hand_id: str | None = None,
        interaction_guard_clear: bool = True,
    ) -> PowerDecision:
        """
        Invoked in NORMAL mode after full-rate inference to update inactivity
        accumulation and evaluate entry into POWER_SAVE.
        """
        current_now = self._clock_fn() if now is None else float(now)

        if self._state != PowerState.NORMAL:
            self._last_frame_dt = 0.0
            return PowerDecision(
                state=self._state,
                cadence=InferenceCadence.SKIP,
                transition_event=PowerTransitionEvent.NONE,
                inactivity_elapsed_s=self._accumulated_inactive_s,
                is_confirming_wake=False,
            )

        # 1. Motion Velocity Calculation & Hand Identity Continuity
        is_meaningful_motion = False
        if has_hands and palm_center is not None and palm_width and palm_width > 0.001:
            if (
                hand_id is not None
                and self._prev_motion_hand_id is not None
                and hand_id != self._prev_motion_hand_id
            ):
                # Hand swapped: re-baseline without calculating cross-hand jump
                is_meaningful_motion = False
            elif self._prev_motion_anchor is not None and self._prev_motion_anchor_ts is not None:
                dt_motion = current_now - self._prev_motion_anchor_ts
                if dt_motion > 0.0001:
                    dx = palm_center[0] - self._prev_motion_anchor[0]
                    dy = palm_center[1] - self._prev_motion_anchor[1]
                    dist = math.sqrt(dx * dx + dy * dy)
                    velocity = dist / (palm_width * dt_motion)
                    if velocity >= self._wake_trigger_velocity:
                        is_meaningful_motion = True

            self._prev_motion_anchor = palm_center
            self._prev_motion_anchor_ts = current_now
            self._prev_motion_hand_id = hand_id
        else:
            # Absence of hand clears anchor
            self._prev_motion_anchor = None
            self._prev_motion_anchor_ts = None
            self._prev_motion_hand_id = None

        # 2. Inactivity Accounting with Single Consumption Lock
        if not interaction_guard_clear or is_meaningful_motion:
            self._accumulated_inactive_s = 0.0
        else:
            self._accumulated_inactive_s += self._last_frame_dt

        # Consume the incremental dt so it cannot be added twice
        self._last_frame_dt = 0.0

        # 3. Evaluate Entry Into POWER_SAVE
        trans_event = PowerTransitionEvent.NONE
        is_dwell_active = current_now < self._wake_dwell_until_ts

        if (
            self._enabled
            and not is_dwell_active
            and self._accumulated_inactive_s >= (self._inactivity_timeout_s - 1e-4)
            and interaction_guard_clear
        ):
            self._state = PowerState.POWER_SAVE
            self._probe_counter = 0
            self._wake_candidate_start_ts = None
            self._wake_confirm_frames = 0
            self._prev_motion_anchor = None
            self._prev_motion_anchor_ts = None
            self._prev_motion_hand_id = None
            trans_event = PowerTransitionEvent.ENTERED_POWER_SAVE

        return PowerDecision(
            state=self._state,
            cadence=InferenceCadence.FULL_RATE if self._state == PowerState.NORMAL else InferenceCadence.PROBE,
            transition_event=trans_event,
            inactivity_elapsed_s=self._accumulated_inactive_s,
            is_confirming_wake=False,
        )

    def update_probe_measurements(
        self,
        now: float | None = None,
        has_hands: bool = False,
        palm_center: tuple[float, float] | None = None,
        palm_width: float | None = None,
        hand_id: str | None = None,
    ) -> PowerDecision:
        """
        Invoked in POWER_SAVE mode after probe/confirmation inference to evaluate
        wake candidate arming, confirmation persistence, or candidate rejection.
        """
        current_now = self._clock_fn() if now is None else float(now)

        if self._state != PowerState.POWER_SAVE:
            return PowerDecision(
                state=self._state,
                cadence=InferenceCadence.FULL_RATE,
                transition_event=PowerTransitionEvent.NONE,
                inactivity_elapsed_s=self._accumulated_inactive_s,
                is_confirming_wake=False,
            )

        trans_event = PowerTransitionEvent.NONE

        # 1. No Hands Detected
        if not has_hands or palm_center is None or palm_width is None or palm_width <= 0.001:
            self._prev_motion_anchor = None
            self._prev_motion_anchor_ts = None
            self._prev_motion_hand_id = None
            if self._wake_candidate_start_ts is not None:
                self._wake_candidate_start_ts = None
                self._wake_confirm_frames = 0
                trans_event = PowerTransitionEvent.WAKE_REJECTED

            return PowerDecision(
                state=self._state,
                cadence=InferenceCadence.SKIP,
                transition_event=trans_event,
                inactivity_elapsed_s=self._accumulated_inactive_s,
                is_confirming_wake=False,
            )

        # 2. Hand Identity Swap Check
        if (
            hand_id is not None
            and self._prev_motion_hand_id is not None
            and hand_id != self._prev_motion_hand_id
        ):
            self._prev_motion_anchor = palm_center
            self._prev_motion_anchor_ts = current_now
            self._prev_motion_hand_id = hand_id
            if self._wake_candidate_start_ts is not None:
                self._wake_candidate_start_ts = None
                self._wake_confirm_frames = 0
                trans_event = PowerTransitionEvent.WAKE_REJECTED
            return PowerDecision(
                state=self._state,
                cadence=InferenceCadence.SKIP,
                transition_event=trans_event,
                inactivity_elapsed_s=self._accumulated_inactive_s,
                is_confirming_wake=False,
            )

        # 3. Hand Detected — Motion Calculation
        velocity = 0.0
        if self._prev_motion_anchor is not None and self._prev_motion_anchor_ts is not None:
            dt_motion = current_now - self._prev_motion_anchor_ts
            if dt_motion > 0.0001:
                dx = palm_center[0] - self._prev_motion_anchor[0]
                dy = palm_center[1] - self._prev_motion_anchor[1]
                dist = math.sqrt(dx * dx + dy * dy)
                velocity = dist / (palm_width * dt_motion)

        # Update anchor coordinates
        self._prev_motion_anchor = palm_center
        self._prev_motion_anchor_ts = current_now
        self._prev_motion_hand_id = hand_id

        # 4. Wake Candidate & Confirmation Lifecycle
        if self._wake_candidate_start_ts is None:
            # Candidate Arming Phase
            if velocity >= self._wake_trigger_velocity:
                self._wake_candidate_start_ts = current_now
                self._wake_confirm_frames = 1
                cadence = InferenceCadence.CONFIRMATION
            else:
                cadence = InferenceCadence.SKIP
        else:
            # Candidate Confirmation Phase
            if velocity < self._wake_confirm_velocity:
                # Failed persistence check -> reject with zero lockout
                self._wake_candidate_start_ts = None
                self._wake_confirm_frames = 0
                trans_event = PowerTransitionEvent.WAKE_REJECTED
                cadence = InferenceCadence.SKIP
            else:
                self._wake_confirm_frames += 1
                elapsed_confirm = current_now - self._wake_candidate_start_ts
                if (
                    elapsed_confirm >= (self._wake_confirm_duration_s - 1e-4)
                    and self._wake_confirm_frames >= self._min_confirm_frames
                ):
                    # Wake Confirmed!
                    self._state = PowerState.NORMAL
                    self._wake_candidate_start_ts = None
                    self._wake_confirm_frames = 0
                    self._accumulated_inactive_s = 0.0
                    self._wake_dwell_until_ts = current_now + self._wake_dwell_duration_s
                    trans_event = PowerTransitionEvent.WAKE_CONFIRMED
                    cadence = InferenceCadence.FULL_RATE
                else:
                    # Still within confirmation window
                    cadence = InferenceCadence.CONFIRMATION

        return PowerDecision(
            state=self._state,
            cadence=cadence,
            transition_event=trans_event,
            inactivity_elapsed_s=self._accumulated_inactive_s,
            is_confirming_wake=(self._wake_candidate_start_ts is not None),
        )

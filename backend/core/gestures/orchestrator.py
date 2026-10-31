"""
GestureOrchestrator - routes HandsResult to per-hand processors and manages Pointer Ownership.
"""

import logging
import math
import time
from enum import Enum, auto

from core.tracker import HandsResult
from core.display import VirtualDesktop, TrackpadZone
from core.actuator import MouseActuator
from core.gestures.right_hand import RightHandProcessor
from core.gestures.left_hand import LeftHandProcessor
from core.gestures.two_hand import TwoHandProcessor
from core.gestures.screenshot import ScreenshotController
from core.gestures.w_gesture import WGestureRecognizer, WState
from core.app_launcher import AppLauncher
from core.gestures.lip_mute_gesture import LipMuteGestureRecognizer, LipMuteState
from core.gestures.ear_volume_gesture import EarVolumeGestureRecognizer, EarVolumeDirection
from core.audio_controller import AudioController
from core.face_tracker import FaceResult
from core.gestures.wakanda_gesture import WakandaGestureRecognizer, WakandaState

logger = logging.getLogger(__name__)

class PointerOwner(Enum):
    NONE = auto()
    RIGHT = auto()
    LEFT = auto()

def _is_valid_coord(pos: object) -> bool:
    """Validate that pos is a concrete 2-tuple or list of numeric pixel coordinates."""
    if not isinstance(pos, (tuple, list)) or len(pos) != 2:
        return False
    x, y = pos[0], pos[1]
    if isinstance(x, bool) or isinstance(y, bool):
        return False
    return isinstance(x, (int, float)) and isinstance(y, (int, float))

class GestureOrchestrator:
    def __init__(
        self,
        actuator: MouseActuator,
        desktop: VirtualDesktop,
        trackpad: TrackpadZone,
        initial_cursor_anchor: tuple[int, int] | None = None,
        max_step_limit: float | None = None,
    ) -> None:
        self._max_step_limit: float | None = float(max_step_limit) if (max_step_limit is not None and max_step_limit > 0) else None
        self._right = RightHandProcessor(actuator, desktop, trackpad)
        self._left = LeftHandProcessor(actuator, desktop, trackpad)
        self._two = TwoHandProcessor(actuator)
        self._screenshot = ScreenshotController(actuator)
        self._app_launcher = AppLauncher()
        self._w_gesture = WGestureRecognizer(self._app_launcher)
        self._audio_controller = AudioController()
        self._lip_gesture = LipMuteGestureRecognizer(self._audio_controller)
        self._ear_volume = EarVolumeGestureRecognizer(self._audio_controller)
        self._wakanda = WakandaGestureRecognizer()
        self._actuator = actuator

        # Initialize trusted cursor anchor:
        # 1. If explicit initial_cursor_anchor is provided, preserve it.
        # 2. Otherwise, attempt to query the actual current desktop cursor position from actuator.
        # 3. If query fails or returns None, initialize to None (fail closed: suppress movement until anchor established).
        if _is_valid_coord(initial_cursor_anchor):
            self._trusted_cursor_anchor: tuple[int, int] | None = (int(initial_cursor_anchor[0]), int(initial_cursor_anchor[1]))
        elif hasattr(actuator, "get_cursor_pos"):
            try:
                queried = actuator.get_cursor_pos()
                if _is_valid_coord(queried):
                    self._trusted_cursor_anchor = (int(queried[0]), int(queried[1]))
                else:
                    self._trusted_cursor_anchor = None
            except Exception as e:
                logger.warning("Failed to query initial cursor position: %s", e)
                self._trusted_cursor_anchor = None
        else:
            self._trusted_cursor_anchor = None

        self._last_cursor_pos: tuple[int, int] | None = self._trusted_cursor_anchor
        self._last_move_time: float = 0.0
        self._consecutive_jumps: int = 0
        self._was_right_locked: bool = False
        self._was_ear_active: bool = False
        
        self._pointer_owner = PointerOwner.NONE
        self._owner_switch_time: float | None = None
        self._drag_pointer_owner: PointerOwner | None = None
        self._cursor_source_name: str = "NONE"
        self._is_cursor_moving: bool = False
        self.pointer_enabled: bool = True
        self._drag_enabled: bool = True
        self._right_dropout_frames: int = 0
        self._right_last_valid_time: float | None = None
        self._left_dropout_frames: int = 0
        self._left_last_valid_time: float | None = None
        
        self._GRACE_INTERVAL_S = 0.2
        
        logger.info("GestureOrchestrator ready (dual-hand mode)")

    def set_sensitivity(self, sensitivity: float) -> None:
        """Forward sensitivity to hand processors."""
        if hasattr(self._right, "set_sensitivity"):
            self._right.set_sensitivity(sensitivity)
        if hasattr(self._left, "set_sensitivity"):
            self._left.set_sensitivity(sensitivity)

    @property
    def drag_enabled(self) -> bool:
        return getattr(self, '_drag_enabled', True)

    @drag_enabled.setter
    def drag_enabled(self, enabled: bool) -> None:
        was_enabled = getattr(self, '_drag_enabled', True)
        new_val = bool(enabled)
        self._drag_enabled = new_val
        if was_enabled and not new_val:
            logger.info("Drag & drop disabled; safely releasing active drag")
            if hasattr(self._left, "release_drag"):
                self._left.release_drag(reason="FEATURE_DISABLED")
            elif hasattr(self._actuator, "drag_end"):
                self._actuator.drag_end()
            self._drag_pointer_owner = None
        elif new_val:
            if hasattr(self._left, "_rearm_time"):
                self._left._rearm_time = None

    @property

    @property
    def max_step_limit(self) -> float | None:
        return self._max_step_limit

    @max_step_limit.setter
    def max_step_limit(self, limit: float | None) -> None:
        self._max_step_limit = float(limit) if (limit is not None and limit > 0) else None

    def set_smoothing(self, smoothing: int | float) -> None:
        """Forward smoothing to hand processors."""
        if hasattr(self._right, "set_smoothing"):
            self._right.set_smoothing(smoothing)
        if hasattr(self._left, "set_smoothing"):
            self._left.set_smoothing(smoothing)

    def process(self, hands: HandsResult | None, face: FaceResult | None = None) -> None:
        from config import POINTER_ONLY_MODE, PINCH_CLICK_ENABLED
        now = time.perf_counter()
        self._cursor_source_name = "NONE"
        self._is_cursor_moving = False

        if hands is None:
            hands = HandsResult()

        if getattr(self._actuator, 'is_dragging', False):
            if hasattr(self._actuator, 'check_drag_watchdog') and (self._actuator.check_drag_watchdog(now, timeout_s=0.25) is True):
                if hasattr(self._left, 'release_drag'):
                    self._left.release_drag(reason="WATCHDOG_TIMEOUT")

        screenshot_active = self._screenshot.process(hands, now)
        
        if screenshot_active:
            if hasattr(self._left, 'release_drag'):
                self._left.release_drag(reason="SCREENSHOT")
            if self._last_cursor_pos is not None:
                self._actuator.move(self._last_cursor_pos[0], self._last_cursor_pos[1])
            self._right.process(None)
            self._left.process(None, now)
            self._pointer_owner = PointerOwner.NONE
            return

        # Phase 8: Wakanda Forever crossed-arm lock gesture
        wakanda_active = self._wakanda.process(hands, face, now)
        if wakanda_active:
            if hasattr(self._left, 'release_drag'):
                self._left.release_drag(reason="WORKSTATION_LOCK")
            if self._last_cursor_pos is not None:
                self._actuator.move(self._last_cursor_pos[0], self._last_cursor_pos[1])
            self._right.process(None)
            self._left.process(None, now)
            self._pointer_owner = PointerOwner.NONE
            return

        # Phase 4: Two-hand W gesture to open WhatsApp Desktop
        self._w_gesture.process(hands, now)
        if self._w_gesture.state in (WState.CANDIDATE, WState.CONFIRMED):
            if hasattr(self._left, 'release_drag'):
                self._left.release_drag(reason="APP_LAUNCH")
            if self._last_cursor_pos is not None:
                self._actuator.move(self._last_cursor_pos[0], self._last_cursor_pos[1])
            self._right.process(None)
            self._left.process(None, now)
            self._pointer_owner = PointerOwner.NONE
            return

        # Check if an active mouse drag is in progress
        is_active_drag = (
            (getattr(self._actuator, 'is_dragging', False) is True)
            or (
                hasattr(self._left, "drag_controller")
                and self._left.drag_controller.is_active_or_pending
            )
            or getattr(self._left, 'left_drag_state', '') in ('DRAGGING', 'GRAB_LOCKED', 'GRAB_CANDIDATE', 'GRAB_PENDING')
        )

        # Phase 5: Lip-touch audio mute / restore (protected: never interrupts active drag)
        if not is_active_drag:
            self._lip_gesture.process(hands, face, now)
            if self._lip_gesture.is_holding:
                if self._last_cursor_pos is not None:
                    self._actuator.move(self._last_cursor_pos[0], self._last_cursor_pos[1])
                self._right.process(None)
                self._left.process(None)
                self._pointer_owner = PointerOwner.NONE
                return
        else:
            if self._lip_gesture.state != LipMuteState.IDLE:
                self._lip_gesture.reset()

        # Phase 6: Ear-touch continuous volume adjustment
        self._ear_volume.process(hands, face, now)
        ear_active = self._ear_volume.is_active
        ear_touching_hand = self._ear_volume.touching_hand if ear_active else None

        if ear_active:
            # Only suppress the hand that is actively touching an ear
            # Candidate proximity NEVER locks or pauses cursor
            if ear_touching_hand == "RIGHT":
                self._right.process(None)
                if hands.left is not None and self.drag_enabled:
                    self._left.process(hands.left, now)
                else:
                    self._left.process(None, now)
            elif ear_touching_hand == "LEFT":
                self._left.process(None, now)
                if hands.right is not None and self.pointer_enabled:
                    self._right.process(hands.right)
                else:
                    self._right.process(None)
            else:
                self._right.process(None)
                self._left.process(None, now)

            # Check if the non-touching hand can control cursor
            left_can_point = (ear_touching_hand == "RIGHT" and hands.left is not None and getattr(self._left, "is_pointing", False))
            right_can_point = (ear_touching_hand == "LEFT" and hands.right is not None and getattr(self._right, "_cursor_pos", None) is not None)

            if not (left_can_point or right_can_point):
                if self._last_cursor_pos is not None:
                    self._actuator.move(self._last_cursor_pos[0], self._last_cursor_pos[1])
                self._pointer_owner = PointerOwner.NONE
                self._was_ear_active = True
                return
        else:
            if hands.left is not None and self.drag_enabled:
                self._left_dropout_frames = 0
                self._left_last_valid_time = now
                self._left._is_in_dropout_grace = False
                self._left.process(hands.left, now)
            else:
                is_dragging = (
                    (
                        hasattr(self._left, "drag_controller")
                        and self._left.drag_controller.is_grab_locked
                    )
                    or getattr(self._left, 'left_drag_state', '') in ('DRAGGING', 'GRAB_LOCKED')
                    or (getattr(self._actuator, 'is_dragging', False) is True)
                )
                from config import LEFT_DRAG_LOST_TIMEOUT_S
                configured_lost_s = getattr(self._left, 'drag_lost_timeout_s', float(LEFT_DRAG_LOST_TIMEOUT_S))
                grace_timeout = configured_lost_s if is_dragging else 0.120
                if (
                    self._left_last_valid_time is not None
                    and (now - self._left_last_valid_time) <= grace_timeout
                ):
                    self._left_dropout_frames += 1
                    self._left._is_in_dropout_grace = True
                    if is_dragging and hasattr(self._actuator, 'keep_drag_alive'):
                        self._actuator.keep_drag_alive(now)
                else:
                    self._left_dropout_frames = 0
                    self._left_last_valid_time = None
                    self._left._is_in_dropout_grace = False
                    self._left.process(None, now)

            if getattr(self._left, 'just_started_drag', False):
                if hasattr(self._right, 'resolve_pending_click'):
                    self._right.resolve_pending_click()

            if hands.right is not None and self.pointer_enabled:
                self._right_dropout_frames = 0
                self._right_last_valid_time = now
                self._right._is_in_dropout_grace = False
                self._right.process(hands.right)
            else:
                if (
                    self.pointer_enabled
                    and self._right_last_valid_time is not None
                    and self._right_dropout_frames < 3
                    and (now - self._right_last_valid_time) <= 0.120
                ):
                    self._right_dropout_frames += 1
                    self._right._is_in_dropout_grace = True
                else:
                    self._right_dropout_frames = 0
                    self._right_last_valid_time = None
                    self._right._is_in_dropout_grace = False
                    self._right.process(None)

        if hands.left is not None and hands.right is not None:
            self._two.process(hands.left, hands.right)

        # POINTER OWNERSHIP LOGIC
        # Priority:
        # If left hand is actively dragging, retain left pointer ownership
        # Otherwise:
        # 1. Right hand (if valid pointer and not touching ear)
        # 2. Left hand (if valid pointer and no right hand)
        
        is_left_actively_dragging = (
            self.drag_enabled
            and (
                (
                    hasattr(self._left, "drag_controller")
                    and self._left.drag_controller.is_grab_locked
                )
                or getattr(self._left, 'left_drag_state', '') in ('DRAGGING', 'GRAB_LOCKED')
                or (getattr(self._actuator, 'is_dragging', False) is True)
            )
        )

        right_in_grace = getattr(self._right, 'is_in_dropout_grace', False) and (is_left_actively_dragging or hands.left is None)
        right_wants_pointer = (
            (hands.right is not None or right_in_grace)
            and ear_touching_hand != "RIGHT"
            and getattr(self._right, '_cursor_pos', None) is not None
        )
        left_wants_pointer = (
            (hands.left is not None or getattr(self._left, 'is_in_dropout_grace', False))
            and ear_touching_hand != "LEFT"
            and getattr(self._left, 'is_pointing', False)
            and getattr(self._left, 'cursor_pos', None) is not None
        )

        new_owner = PointerOwner.NONE
        
        # Determine candidate owner
        if is_left_actively_dragging:
            # Lock ownership for the entire duration of the active drag session
            # 1. Preserve an existing valid RIGHT pointer owner
            # 2. If no usable owner exists and the right hand can control the cursor, prefer RIGHT
            # 3. Use LEFT as the pointer only when RIGHT is not a usable pointer source
            if self._drag_pointer_owner is None:
                if self._pointer_owner == PointerOwner.RIGHT and right_wants_pointer:
                    self._drag_pointer_owner = PointerOwner.RIGHT
                elif right_wants_pointer:
                    self._drag_pointer_owner = PointerOwner.RIGHT
                elif left_wants_pointer:
                    self._drag_pointer_owner = PointerOwner.LEFT
                else:
                    self._drag_pointer_owner = self._pointer_owner if self._pointer_owner != PointerOwner.NONE else PointerOwner.RIGHT
            new_owner = self._drag_pointer_owner
        else:
            self._drag_pointer_owner = None
            if self._pointer_owner == PointerOwner.RIGHT and right_wants_pointer:
                new_owner = PointerOwner.RIGHT
            elif right_wants_pointer:
                new_owner = PointerOwner.RIGHT
            elif left_wants_pointer:
                new_owner = PointerOwner.LEFT
            else:
                new_owner = PointerOwner.NONE
        old_owner = self._pointer_owner
        # Pointer switching: Right hand and active drag have instant priority; Left hand takes over smoothly when right hand is absent
        if new_owner != self._pointer_owner:
            if new_owner == PointerOwner.RIGHT or self._pointer_owner == PointerOwner.NONE or is_left_actively_dragging or (new_owner == PointerOwner.LEFT and hands.right is None) or new_owner == PointerOwner.NONE:
                self._pointer_owner = new_owner
                self._owner_switch_time = None
            elif self._owner_switch_time is None:
                self._owner_switch_time = now
            elif (now - self._owner_switch_time) >= 0.08:
                self._pointer_owner = new_owner
                self._owner_switch_time = None

            # Hand identity switch handling: rebaseline anchor safely to prevent cross-screen teleportation
            if old_owner != PointerOwner.NONE and self._pointer_owner != PointerOwner.NONE and old_owner != self._pointer_owner:
                logger.info("Pointer ownership transferred from %s to %s — rebaselining anchor safely", old_owner.name, self._pointer_owner.name)
                if _is_valid_coord(self._last_cursor_pos):
                    self._trusted_cursor_anchor = (int(self._last_cursor_pos[0]), int(self._last_cursor_pos[1]))
                elif hasattr(self._actuator, "get_cursor_pos"):
                    fresh = self._actuator.get_cursor_pos()
                    if _is_valid_coord(fresh):
                        self._trusted_cursor_anchor = (int(fresh[0]), int(fresh[1]))
                self._consecutive_jumps = 0
        else:
            self._owner_switch_time = None

        # Execute pointer movement
        right_locked = getattr(self._right, 'is_cursor_locked', False)
        
        target_pos: tuple[int, int] | None = None
        if self._pointer_owner == PointerOwner.RIGHT:
            target_pos = getattr(self._right, '_cursor_pos', None)
            # Uncertain tracking check: suppress movement if landmark score is below minimum confidence
            min_score = 0.20 if is_left_actively_dragging else 0.40
            if hands.right is not None and getattr(hands, 'right_score', 1.0) < min_score:
                logger.debug("Uncertain right hand tracking (score=%.2f < %.2f); suppressing cursor movement", getattr(hands, 'right_score', 1.0), min_score)
                target_pos = None
        elif self._pointer_owner == PointerOwner.LEFT:
            target_pos = getattr(self._left, 'cursor_pos', None)
            min_score = 0.20 if is_left_actively_dragging else 0.40
            if hands.left is not None and getattr(hands, 'left_score', 1.0) < min_score:
                logger.debug("Uncertain left hand tracking (score=%.2f < %.2f); suppressing cursor movement", getattr(hands, 'left_score', 1.0), min_score)
                target_pos = None

        if target_pos is not None:
            target_x, target_y = target_pos

            # Reacquisition / startup anchor synchronization:
            # If tracking was inactive (_last_cursor_pos is None), attempt to refresh anchor
            # from actual physical cursor position to capture any external mouse movement.
            if self._last_cursor_pos is None and hasattr(self._actuator, "get_cursor_pos"):
                try:
                    fresh_pos = self._actuator.get_cursor_pos()
                    if _is_valid_coord(fresh_pos):
                        self._trusted_cursor_anchor = (int(fresh_pos[0]), int(fresh_pos[1]))
                except Exception as e:
                    logger.debug("Failed to refresh cursor pos: %s", e)

            # Backward compatibility with callers/tests that manually set _last_cursor_pos
            if not _is_valid_coord(self._trusted_cursor_anchor) and _is_valid_coord(self._last_cursor_pos):
                self._trusted_cursor_anchor = (int(self._last_cursor_pos[0]), int(self._last_cursor_pos[1]))

            # If anchor remains unknown (query failed and no prior anchor known):
            # Fail closed: suppress movement until a valid trusted anchor is established.
            if not _is_valid_coord(self._trusted_cursor_anchor):
                logger.warning("Desktop cursor anchor unknown; suppressing movement for safety")
                self._last_cursor_pos = None
                return

            anchor_x, anchor_y = self._trusted_cursor_anchor

            # Effective elapsed time clamped to [0.001s, 0.040s]
            if self._last_move_time > 0.0:
                dt_raw = max(0.001, now - self._last_move_time)
                dt_effective = min(dt_raw, 0.040)
            else:
                dt_effective = 1.0 / 30.0

            # Dynamic step limit: 380px floor, 24000 px/s slope, ceiling capped at 960px
            max_step = max(380.0, 24000.0 * dt_effective)
            if max_step > 960.0:
                max_step = 960.0

            # Stricter opt-in step limit (e.g. 50px for conservative Phase B live validation)
            if self._max_step_limit is not None and self._max_step_limit > 0.0:
                max_step = min(max_step, float(self._max_step_limit))

            dx = float(target_x - anchor_x)
            dy = float(target_y - anchor_y)
            jump_dist = math.hypot(dx, dy)

            if jump_dist > max_step:
                self._consecutive_jumps += 1
                if self._consecutive_jumps == 1:
                    logger.warning(
                        "CURSOR JUMP DETECTED: %.1fpx (limit: %.0fpx, dt_eff=%.1fms) | "
                        "Owner: %s | Bounding step to maintain stability",
                        jump_dist, max_step, dt_effective * 1000.0,
                        self._pointer_owner.name
                    )

                # Bounded step along vector
                scale = max_step / jump_dist
                cand_x = int(round(anchor_x + dx * scale))
                cand_y = int(round(anchor_y + dy * scale))

                # Conservative integer rounding adjustment: guarantee Euclidean displacement <= max_step
                while math.hypot(cand_x - anchor_x, cand_y - anchor_y) > max_step + 1e-6:
                    step_x = cand_x - anchor_x
                    step_y = cand_y - anchor_y
                    if abs(step_x) >= abs(step_y) and step_x != 0:
                        cand_x -= 1 if step_x > 0 else -1
                    elif step_y != 0:
                        cand_y -= 1 if step_y > 0 else -1
                    else:
                        break

                screen_x, screen_y = cand_x, cand_y
            else:
                self._consecutive_jumps = 0
                screen_x, screen_y = target_x, target_y

            self._actuator.move(screen_x, screen_y)
            self._trusted_cursor_anchor = (screen_x, screen_y)
            self._last_cursor_pos = (screen_x, screen_y)
            self._last_move_time = now
            self._was_ear_active = False
            self._cursor_source_name = self._pointer_owner.name
            self._is_cursor_moving = True
        else:
            if self._pointer_owner == PointerOwner.NONE:
                # Hand tracking absent: clear per-stream tracking position and jump counters,
                # but preserve _trusted_cursor_anchor so post-absence reacquisition remains bounded.
                self._last_cursor_pos = None
                self._consecutive_jumps = 0

        self._was_right_locked = right_locked

    @property
    def right_state(self) -> str:
        return getattr(self._right, '_state').name

    @property
    def cursor_pos(self) -> tuple[int, int] | None:
        return self._last_cursor_pos

    @property
    def trusted_cursor_anchor(self) -> tuple[int, int] | None:
        return self._trusted_cursor_anchor

    def set_cursor_anchor(self, anchor: tuple[int, int] | None) -> None:
        """Explicitly define trusted cursor anchor (for testing or wake reanchoring)."""
        if _is_valid_coord(anchor):
            self._trusted_cursor_anchor = (int(anchor[0]), int(anchor[1]))
            self._last_cursor_pos = self._trusted_cursor_anchor
        else:
            self._trusted_cursor_anchor = None
            self._last_cursor_pos = None

        self._consecutive_jumps = 0
        self._last_move_time = 0.0


    @property
    def right_visual_tips(self) -> dict[int, tuple[float, float, float]]:
        return getattr(self._right, 'visual_tips', {})
        
    @property
    def left_visual_tips(self) -> dict[int, tuple[float, float, float]]:
        return getattr(self._left, 'visual_tips', {})

    @property
    def click_state_text(self) -> str:
        return getattr(self._right, '_click_state_text', "DISABLED")

    @property
    def last_pinch_norm(self) -> float:
        return getattr(self._right, 'last_pinch_norm', 0.0)

    @property
    def is_cursor_locked(self) -> bool:
        return getattr(self._right, 'is_cursor_locked', False)
        
    @property
    def pointer_owner(self) -> str:
        return self._pointer_owner.name

    @property
    def cursor_source_name(self) -> str:
        return self._cursor_source_name

    @property
    def is_cursor_moving(self) -> bool:
        return self._is_cursor_moving

    @property
    def w_gesture(self) -> WGestureRecognizer:
        return self._w_gesture

    @property
    def w_state(self) -> str:
        return self._w_gesture.state.name

    @property
    def w_status_text(self) -> str:
        return self._w_gesture.status_text

    def set_w_activation_callback(self, cb) -> None:
        self._w_gesture.set_activation_callback(cb)

    @property
    def lip_gesture(self) -> LipMuteGestureRecognizer:
        return self._lip_gesture

    @property
    def lip_state(self) -> str:
        return self._lip_gesture.state.name

    @property
    def lip_status_text(self) -> str:
        return self._lip_gesture.status_text

    @property
    def audio_controller(self) -> AudioController:
        return self._audio_controller

    def set_lip_activation_callback(self, cb) -> None:
        self._lip_gesture.set_activation_callback(cb)

    @property
    def ear_volume_gesture(self) -> EarVolumeGestureRecognizer:
        return self._ear_volume

    @property
    def ear_volume_direction(self) -> str:
        return self._ear_volume.direction.name

    @property
    def ear_volume_status_text(self) -> str:
        return self._ear_volume.status_text

    def set_ear_volume_callback(self, cb) -> None:
        self._ear_volume.set_callback(cb)

    @property
    def wakanda_gesture(self) -> WakandaGestureRecognizer:
        return self._wakanda

    @property
    def wakanda_state(self) -> str:
        return self._wakanda.state.name

    @property
    def wakanda_progress(self) -> float:
        return self._wakanda.progress

    @property
    def wakanda_status_text(self) -> str:
        return self._wakanda.status_text

    def set_wakanda_callback(self, cb) -> None:
        self._wakanda.set_activation_callback(cb)

    def reset(self) -> None:
        """Reset all sub-processors and safely release any held mouse buttons or gestures."""
        if hasattr(self._left, 'reset'):
            self._left.reset()
        elif hasattr(self._actuator, 'drag_end'):
            self._actuator.drag_end()
        if hasattr(self._right, 'resolve_pending_click'):
            self._right.resolve_pending_click()
        if hasattr(self._lip_gesture, 'reset'):
            self._lip_gesture.reset()
        if hasattr(self._wakanda, 'reset'):
            self._wakanda.reset()
        if hasattr(self._ear_volume, '_stop_adjustment'):
            self._ear_volume._stop_adjustment(time.perf_counter())
        self._pointer_owner = PointerOwner.NONE
        self._drag_pointer_owner = None
        self._cursor_source_name = "NONE"
        self._is_cursor_moving = False
        self._last_cursor_pos = None
        self._consecutive_jumps = 0
        self._last_move_time = 0.0
        self._was_ear_active = False
        self._right_dropout_frames = 0
        self._right_last_valid_time = None
        self._left_dropout_frames = 0
        self._left_last_valid_time = None
        self._right._is_in_dropout_grace = False
        self._left._is_in_dropout_grace = False

        # Attempt to re-query the current desktop cursor position.
        # If query fails, preserve existing trusted anchor so we do not lose our baseline.
        fresh_anchor = None
        if hasattr(self._actuator, "get_cursor_pos"):
            try:
                queried = self._actuator.get_cursor_pos()
                if _is_valid_coord(queried):
                    fresh_anchor = (int(queried[0]), int(queried[1]))
            except Exception as e:
                logger.debug("Failed to re-query cursor position on reset: %s", e)
                fresh_anchor = None

        if fresh_anchor is not None:
            self._trusted_cursor_anchor = fresh_anchor
        # If fresh_anchor is None, preserve self._trusted_cursor_anchor


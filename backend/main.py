# main.py
"""
AI Air Mouse — Entry point.

Startup sequence (ORDER MATTERS):
  1. Configure logging
  2. Set Windows timer resolution to 1ms
  3. Elevate process to HIGH_PRIORITY_CLASS
  4. Register main thread with MMCSS ("Games" profile)
  5. Build virtual desktop + trackpad zone (DPI awareness already set at display.py import)
  6. Disable Windows pointer acceleration (restore on exit)
  7. Start async camera
  8. Start MediaPipe hand tracker
  9. Instantiate gesture processor + actuator
  10. Run inference loop
  11. On exit: restore timer resolution, restore pointer precision, release all resources

Exit handling:
  - Ctrl+C (KeyboardInterrupt) -> clean shutdown
  - Any unhandled exception -> log traceback, then clean shutdown
  - atexit handler as final safety net to ensure pointer precision is restored
"""

import atexit
import ctypes
import logging
import os
import sys
import time
import traceback

import psutil

import cv2
from pynput import keyboard

from config import PROCESS_PRIORITY, TIMER_RESOLUTION_MS, DEBUG_GESTURES
import math
from typing import Any
from queue import Queue, Empty

from core.camera import AsyncCamera, FrameFreshnessDetector
from core.power_state_machine import PowerStateManager, InferenceCadence, PowerTransitionEvent, PowerState
from core.tracker import HandTracker, HandsResult
from core.face_tracker import FaceTracker
from core.gestures import GestureOrchestrator
from core.actuator import MouseActuator
from core.display import build_virtual_desktop, build_trackpad_zone
from core.control_server import ControlServer
from config import SCREENSHOT_OVERLAY_ENABLED, SCREENSHOT_OVERLAY_POSITION

if SCREENSHOT_OVERLAY_ENABLED:
    from core.overlay import ScreenshotOverlay
else:
    ScreenshotOverlay = None

if DEBUG_GESTURES:
    from core.debug_overlay import draw_debug_frame

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("airmouse.main")


# ── Windows OS Setup ──────────────────────────────────────────────────────────

def _apply_windows_performance() -> dict:
    """
    Apply all Windows OS performance settings.
    Returns a dict of original values so they can be restored on exit.
    """
    original = {}

    # 1. Timer resolution: set to 1ms floor (default is 15.6ms)
    try:
        winmm = ctypes.windll.winmm
        winmm.timeBeginPeriod(TIMER_RESOLUTION_MS)
        original["timer_period"] = TIMER_RESOLUTION_MS
        logger.info("Windows timer resolution set to %dms", TIMER_RESOLUTION_MS)
    except Exception as e:
        logger.warning("Failed to set timer resolution: %s", e)

    # 2. Process priority: HIGH_PRIORITY_CLASS
    try:
        proc = psutil.Process(os.getpid())
        proc.nice(PROCESS_PRIORITY)
        logger.info("Process priority set to HIGH_PRIORITY_CLASS (0x%X)", PROCESS_PRIORITY)
    except psutil.AccessDenied:
        logger.warning("Could not elevate process priority — run as administrator for best performance")

    # 3. MMCSS: register main thread as "Games" workload class
    # This tells the Windows scheduler to give us CPU time more aggressively
    # and deprioritize background tasks (Defender, Windows Update, etc.) relative to us.
    try:
        avrt = ctypes.windll.avrt
        task_index = ctypes.c_ulong(0)
        avrt.AvSetMmThreadCharacteristicsW.restype = ctypes.c_void_p
        handle = avrt.AvSetMmThreadCharacteristicsW("Games", ctypes.byref(task_index))
        if handle:
            original["mmcss_handle"] = handle
            logger.info("MMCSS thread registered as 'Games' (handle=%d)", handle)
        else:
            logger.warning("MMCSS registration returned NULL handle")
    except Exception as e:
        logger.warning("MMCSS registration failed: %s", e)

    # 4. Disable "Enhance Pointer Precision" (Windows mouse acceleration)
    # This ballistic curve applied by Windows corrupts the 1€ Filter output.
    # SPI_GETMOUSE = 3, SPI_SETMOUSE = 4
    # The parameter is [threshold1, threshold2, acceleration]
    # acceleration=0 disables enhance pointer precision
    original_mouse_params = (ctypes.c_int * 3)(0, 0, 0)
    get_result = ctypes.windll.user32.SystemParametersInfoW(3, 0, original_mouse_params, 0)
    if not get_result:
        logger.warning("SystemParametersInfoW(SPI_GETMOUSE) failed — cannot save/restore mouse settings")
    else:
        original["mouse_params"] = list(original_mouse_params)
        no_accel = (ctypes.c_int * 3)(0, 0, 0)
        set_result = ctypes.windll.user32.SystemParametersInfoW(4, 0, no_accel, 2)
        if not set_result:
            logger.warning("SystemParametersInfoW(SPI_SETMOUSE) failed — pointer acceleration may not be disabled")
        else:
            logger.info("Windows pointer acceleration disabled")

    return original


def _restore_windows_settings(original: dict) -> None:
    """Restore all Windows settings mutated during startup."""

    # Restore timer resolution
    if "timer_period" in original:
        ctypes.windll.winmm.timeEndPeriod(original["timer_period"])
        logger.info("Windows timer resolution restored")

    # Unregister MMCSS
    if "mmcss_handle" in original:
        try:
            ctypes.windll.avrt.AvRevertMmThreadCharacteristics(original["mmcss_handle"])
            logger.info("MMCSS thread unregistered")
        except Exception as e:
            logger.warning("MMCSS revert failed: %s", e)

    # Restore pointer precision
    if "mouse_params" in original:
        restored = (ctypes.c_int * 3)(*original["mouse_params"])
        ctypes.windll.user32.SystemParametersInfoW(4, 0, restored, 2)
        logger.info("Windows pointer acceleration restored")


def extract_hand_measurements(
    hands_res: Any,
) -> tuple[bool, tuple[float, float] | None, float | None, str | None]:
    if not hands_res:
        return False, None, None, None
    if getattr(hands_res, 'right', None) is not None and len(hands_res.right) >= 18:
        lms = hands_res.right
        h_id = "right"
    elif getattr(hands_res, 'left', None) is not None and len(hands_res.left) >= 18:
        lms = hands_res.left
        h_id = "left"
    else:
        return False, None, None, None

    dx = lms[5].x - lms[17].x
    dy = lms[5].y - lms[17].y
    p_width = math.hypot(dx, dy)
    if p_width < 0.001 or math.isnan(p_width) or math.isinf(p_width):
        return False, None, None, None

    cx = (lms[0].x + lms[5].x + lms[17].x) / 3.0
    cy = (lms[0].y + lms[5].y + lms[17].y) / 3.0
    if math.isnan(cx) or math.isnan(cy) or math.isinf(cx) or math.isinf(cy):
        return False, None, None, None

    return True, (cx, cy), p_width, h_id


# ── Main Loop ─────────────────────────────────────────────────────────────────

def run() -> None:
    original_settings: dict = {}

    def _emergency_restore():
        """atexit safety net — runs even on unhandled exceptions."""
        if original_settings:
            _restore_windows_settings(original_settings)

    atexit.register(_emergency_restore)

    logger.info("=== AI Air Mouse starting ===")

    # Apply OS settings before anything else
    original_settings.update(_apply_windows_performance())

    # Build display geometry
    desktop = build_virtual_desktop()
    trackpad = build_trackpad_zone()

    # Instantiate subsystems
    actuator = MouseActuator(desktop.total_width, desktop.total_height)

    frame_count = 0
    fps_clock = time.perf_counter()
    none_count = 0
    
    # State for pause/resume
    is_paused = False
    is_running = True
    
    is_tracking_active = False
    has_tracked_once = False
    hand_missing_since = None
    hand_present_since = None

    def on_activate_pause():
        nonlocal is_paused, is_tracking_active, hand_missing_since, hand_present_since
        is_paused = not is_paused
        if is_paused and getattr(actuator, 'is_dragging', False):
            actuator.drag_end()
        logger.info("SYSTEM PAUSED" if is_paused else "SYSTEM RESUMED")
        if overlay:
            overlay.show_pause_toast(is_paused)
        hand_missing_since = None
        hand_present_since = None
        
    def on_activate_quit():
        nonlocal is_running
        is_running = False
        logger.info("Emergency Stop triggered")

    def on_activate_status():
        if overlay and processor:
            r_h = getattr(hands, 'right', None) if 'hands' in locals() and hands else None
            l_h = getattr(hands, 'left', None) if 'hands' in locals() and hands else None
            trk = "Both Hands" if (r_h and l_h) else ("Right Hand" if r_h else ("Left Hand" if l_h else "No Hands"))
            overlay.show_runtime_status({
                "fps": current_fps,
                "owner": processor.pointer_owner,
                "tracking": trk,
                "paused": is_paused,
            })

    debug_window_active = bool(DEBUG_GESTURES) or ("--debug" in sys.argv)
    debug_window_created = False

    def on_activate_debug():
        nonlocal debug_window_active, debug_window_created
        debug_window_active = not debug_window_active
        logger.info("Debug overlay: %s", "ENABLED" if debug_window_active else "DISABLED")
        if not debug_window_active:
            try:
                cv2.destroyWindow("VIRTUAL POINTER")
            except Exception:
                pass
            debug_window_created = False

    hotkey_listener = keyboard.GlobalHotKeys({
        '<ctrl>+<alt>+p': on_activate_pause,
        '<ctrl>+<alt>+q': on_activate_quit,
        '<ctrl>+<alt>+s': on_activate_status,
        '<ctrl>+<alt>+d': on_activate_debug,
    })
    hotkey_listener.start()

    with AsyncCamera() as camera, HandTracker() as tracker, FaceTracker() as face_tracker:
        processor = GestureOrchestrator(actuator, desktop, trackpad)

        # Start background Control Server for Control Center UI
        control_server = ControlServer(host="127.0.0.1", port=8765)
        control_server.start()

        def stop_tracking_from_ui() -> bool:
            nonlocal is_paused
            if not is_paused:
                on_activate_pause()
            return False

        def start_tracking_from_ui() -> bool:
            nonlocal is_paused
            if is_paused:
                on_activate_pause()
            return True

        def toggle_pause_from_ui() -> bool:
            nonlocal is_paused
            on_activate_pause()
            return not is_paused

        control_server.state.set_lifecycle_callbacks(
            stop_cb=stop_tracking_from_ui,
            start_cb=start_tracking_from_ui,
        )
        control_server.state.set_pause_toggle_cb(toggle_pause_from_ui)

        settings_queue: Queue[dict[str, Any]] = Queue()

        power_manager = PowerStateManager(clock_fn=time.perf_counter)
        freshness_detector = FrameFreshnessDetector(stale_threshold_count=3)
        last_accepted_frame_time = time.perf_counter()

        overlay = None
        if ScreenshotOverlay:
            overlay = ScreenshotOverlay(SCREENSHOT_OVERLAY_POSITION)
            overlay.set_audio_controller(processor.audio_controller)
            processor._screenshot.pre_capture_cb = overlay.hide

            def on_screenshot_post():
                if overlay:
                    overlay.show()
                control_server.state.add_event("Screenshot saved", "screenshot")

            processor._screenshot.post_capture_cb = on_screenshot_post

            def on_w_act(success: bool):
                overlay.show_app_toast("WhatsApp", success)
                if success:
                    control_server.state.add_event("Opening WhatsApp", "whatsapp")

            processor.set_w_activation_callback(on_w_act)

            def on_lip_act(action: str, success: bool):
                overlay.show_audio_toast(action, success)
                if success:
                    evt = "muted" if "MUTE" in action else "unmuted"
                    control_server.state.add_event(f"System audio {action.lower()}", evt)

            processor.set_lip_activation_callback(on_lip_act)

            def on_ear_vol(dir_name: str, vol: float, active: bool):
                overlay.show_ear_volume(
                    dir_name, vol, active, is_muted=processor.audio_controller.is_muted
                )
                if active:
                    is_up = dir_name in ("VOLUME_UP", "UP")
                    evt = "volume-up" if is_up else "volume-down"
                    control_server.state.add_event(f"Volume {'up' if is_up else 'down'}: {int(vol * 100)}%", evt)

            processor.set_ear_volume_callback(on_ear_vol)

            def on_wakanda_act():
                if overlay:
                    overlay.show_wakanda_complete()
                control_server.state.add_event("Workstation locked via Wakanda Forever", "wakanda-forever")

            processor.set_wakanda_callback(on_wakanda_act)
            control_server.state.set_test_countdown_cb(lambda d: overlay.start_test_countdown(d) if overlay else None)

        def apply_ui_settings(new_settings: dict) -> None:
            settings_queue.put(new_settings)

        def drain_settings_queue() -> None:
            while not settings_queue.empty():
                try:
                    new_settings = settings_queue.get_nowait()
                except Empty:
                    break
                if "hold" in new_settings:
                    processor._screenshot.hold_duration = new_settings["hold"]
                if "sensitivity" in new_settings:
                    processor.set_sensitivity(new_settings["sensitivity"])
                if "smoothing" in new_settings:
                    processor.set_smoothing(new_settings["smoothing"])
                if "enabled" in new_settings:
                    en = new_settings["enabled"]
                    processor._screenshot.enabled = en.get("screenshot", True)
                    processor._w_gesture.enabled = en.get("whatsapp", True)
                    processor._lip_gesture.enabled = en.get("mute", True)
                    processor._ear_volume.enabled_up = en.get("volume-up", True)
                    processor._ear_volume.enabled_down = en.get("volume-down", True)
                    processor._wakanda.enabled = en.get("wakanda-forever", False)
                    processor.pointer_enabled = en.get("pointer", True)
                    processor.drag_enabled = en.get("drag", True)
                if "power_save" in new_settings:
                    was_enabled = power_manager.is_enabled
                    new_val = bool(new_settings["power_save"])
                    evt = power_manager.set_enabled(new_val)
                    if evt == PowerTransitionEvent.FEATURE_DISABLED:
                        queried = actuator.get_cursor_pos() if hasattr(actuator, "get_cursor_pos") else None
                        processor.set_cursor_anchor(queried)
                        if overlay:
                            overlay.show_power_saver_disabled()
                    elif new_val and not was_enabled:
                        if overlay:
                            overlay.show_power_saver_enabled_waiting()

                if overlay:
                    overlay.configure(
                        island_enabled=new_settings.get("island_enabled"),
                        notifications_enabled=new_settings.get("island_notifications_enabled"),
                        timer_enabled=new_settings.get("island_timer_enabled"),
                        autohide_enabled=new_settings.get("island_autohide_enabled"),
                        hud_duration_s=new_settings.get("island_hud_duration_s"),
                        completion_duration_s=new_settings.get("island_completion_duration_s"),
                    )

        control_server.state.set_settings_change_cb(apply_ui_settings)
        apply_ui_settings(control_server.state.get_snapshot()["settings"])
        drain_settings_queue()

        logger.info("Running. Press Ctrl+Alt+Q to exit, Ctrl+Alt+P to pause, Ctrl+Alt+S for status.")
        
        current_fps = 0.0
        last_frame_time = time.perf_counter()

        last_raw_frame = None
        last_processed_frame = None
        control_server.state.set_frame_provider(lambda: last_processed_frame)
            
        last_face_result = None
        tot_cam_ms = 0.0
        tot_hand_ms = 0.0
        tot_face_ms = 0.0
        tot_gest_ms = 0.0
        tot_ovl_ms = 0.0
        last_frame_id = -1
        no_frame_since = None
        try:
            while is_running:
                drain_settings_queue()

                t_now = time.perf_counter()
                t_cam_start = t_now
                frame, frame_id = camera.read_fresh(last_frame_id, timeout=0.033)
                cam_ms = (time.perf_counter() - t_cam_start) * 1000.0
                t_now = time.perf_counter()

                # 1. Handle consumer timeout or explicit capture failure
                if frame is None or frame_id == last_frame_id:
                    if no_frame_since is None:
                        no_frame_since = t_now
                    elif (t_now - no_frame_since) > 5.0:
                        logger.error("Camera produced no frames for ~5 seconds — camera may be disconnected")
                        break

                    elapsed_since_accepted = t_now - last_accepted_frame_time
                    if frame is None or elapsed_since_accepted > 0.150:
                        power_manager.evaluate_cadence(now=t_now, frame_valid=False, frame_id=frame_id)

                    time.sleep(0.005)
                    continue

                # 2. Check frame freshness (detect repeated buffer freeze)
                is_fresh = freshness_detector.check(frame)
                elapsed_since_accepted = t_now - last_accepted_frame_time

                if not is_fresh:
                    power_manager.evaluate_cadence(now=t_now, frame_valid=False, frame_id=frame_id)
                    time.sleep(0.005)
                    continue

                # Fresh frame accepted!
                last_accepted_frame_time = t_now
                no_frame_since = None
                none_count = 0
                last_frame_id = frame_id
                frame = cv2.flip(frame, 1)
                last_processed_frame = frame

                ovl_ms = 0.0
                if overlay:
                    t_ovl_start = time.perf_counter()
                    overlay.update_state(processor._screenshot, is_paused, wakanda_gesture=processor._wakanda)
                    ovl_ms = (time.perf_counter() - t_ovl_start) * 1000.0
                
                if not is_paused:
                    t_start = time.perf_counter()
                    t1 = t_start

                    # Interaction guard check
                    interaction_guard_clear = (
                        not getattr(actuator, 'is_dragging', False)
                        and not getattr(processor._right, 'is_cursor_locked', False)
                        and not getattr(processor.audio_controller, 'is_active', False)
                        and not getattr(getattr(processor, '_ear_volume', None), 'is_active', False)
                        and not getattr(getattr(processor, '_screenshot', None), 'is_holding', False)
                        and not getattr(getattr(processor, '_wakanda', None), 'is_holding', False)
                        and getattr(processor, 'w_state', 'IDLE') == 'IDLE'
                        and getattr(processor, 'lip_state', 'IDLE') == 'IDLE'
                    )

                    decision = power_manager.evaluate_cadence(
                        now=t_start,
                        frame_valid=True,
                        frame_id=frame_id,
                        interaction_guard_clear=interaction_guard_clear,
                    )

                    if decision.cadence == InferenceCadence.SKIP:
                        hands = HandsResult()
                        face = None
                        inference_time_ms = 0.0
                        hand_ms = 0.0
                        face_ms = 0.0
                        gest_ms = 0.0

                    elif decision.cadence in (InferenceCadence.PROBE, InferenceCadence.CONFIRMATION):
                        # In POWER_SAVE: Evaluate HandsLandmarker ONLY for wake check; face is bypassed
                        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        t_hand_start = time.perf_counter()
                        hands = tracker.process(frame, rgb_image=rgb_frame)
                        hand_ms = (time.perf_counter() - t_hand_start) * 1000.0
                        face = None
                        face_ms = 0.0
                        inference_time_ms = hand_ms

                        has_hands_m, p_center, p_width, p_hand_id = extract_hand_measurements(hands)
                        probe_dec = power_manager.update_probe_measurements(
                            now=time.perf_counter(),
                            has_hands=has_hands_m,
                            palm_center=p_center,
                            palm_width=p_width,
                            hand_id=p_hand_id,
                        )

                        if probe_dec.transition_event == PowerTransitionEvent.WAKE_CONFIRMED:
                            # Confirmed wake: synchronize cursor anchor on main thread
                            queried = actuator.get_cursor_pos() if hasattr(actuator, "get_cursor_pos") else None
                            processor.set_cursor_anchor(queried)
                            control_server.state.add_event("Waking from Power Save", "wake")
                            if overlay:
                                overlay.show_wake_confirmed()

                        gest_ms = 0.0
                        # Zero actuator calls during probe / confirmation!

                    else: # InferenceCadence.FULL_RATE (NORMAL operating mode)
                        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                        t_hand_start = time.perf_counter()
                        hands = tracker.process(frame, rgb_image=rgb_frame)
                        hand_ms = (time.perf_counter() - t_hand_start) * 1000.0

                        # Hand tracking state transition detection
                        has_hands = (hands is not None) and (hands.right is not None or hands.left is not None)
                        now_ts = time.perf_counter()
                        if has_hands:
                            hand_missing_since = None
                            if not is_tracking_active:
                                if hand_present_since is None:
                                    hand_present_since = now_ts
                                elif (now_ts - hand_present_since) >= 0.15:
                                    is_tracking_active = True
                                    if has_tracked_once and overlay:
                                        overlay.show_tracking_toast("REACQUIRED")
                                    if has_tracked_once:
                                        control_server.state.add_event("Hand reacquired", "reacquired")
                                    has_tracked_once = True
                        else:
                            hand_present_since = None
                            if is_tracking_active and has_tracked_once:
                                if hand_missing_since is None:
                                    hand_missing_since = now_ts
                                elif (now_ts - hand_missing_since) >= 0.35:
                                    is_tracking_active = False
                                    if overlay:
                                        overlay.show_tracking_toast("LOST")
                                    control_server.state.add_event("Hand lost", "lost")

                        face_ms = 0.0
                        if face_tracker.is_ready:
                            t_face_start = time.perf_counter()
                            ear_active = getattr(getattr(processor, '_ear_volume', None), 'is_active', False)
                            lip_active = getattr(getattr(processor, '_lip_gesture', None), 'is_holding', False)
                            face_interval = 2 if (ear_active or lip_active) else 3

                            if last_face_result is None or (frame_count % face_interval == 0):
                                face = face_tracker.process(frame, rgb_image=rgb_frame)
                                last_face_result = face
                            else:
                                face = last_face_result
                            face_ms = (time.perf_counter() - t_face_start) * 1000.0
                        else:
                            face = None

                        t2 = time.perf_counter()
                        inference_time_ms = (t2 - t1) * 1000.0

                        # Update normal activity for PowerStateManager
                        has_hands_m, p_center, p_width, p_hand_id = extract_hand_measurements(hands)
                        norm_dec = power_manager.update_normal_activity(
                            now=t2,
                            has_hands=has_hands_m,
                            palm_center=p_center,
                            palm_width=p_width,
                            hand_id=p_hand_id,
                            interaction_guard_clear=interaction_guard_clear,
                        )

                        if norm_dec.transition_event == PowerTransitionEvent.ENTERED_POWER_SAVE:
                            control_server.state.add_event("Entering Power Save", "power_save")
                            if overlay:
                                overlay.start_power_save_countdown()
                            processor.process(None, None)
                            gest_ms = 0.0
                        else:
                            t_gest_start = time.perf_counter()
                            processor.process(hands, face)
                            gest_ms = (time.perf_counter() - t_gest_start) * 1000.0
                else:
                    t_start = time.perf_counter()
                    hands = HandsResult()
                    inference_time_ms = 0.0
                    hand_ms = 0.0
                    face_ms = 0.0
                    t_gest_start = time.perf_counter()
                    processor.process(None, None) # reset filter and state
                    gest_ms = (time.perf_counter() - t_gest_start) * 1000.0

                tot_cam_ms += cam_ms
                tot_hand_ms += hand_ms
                tot_face_ms += face_ms
                tot_gest_ms += gest_ms
                tot_ovl_ms += ovl_ms

                now = time.perf_counter()
                dt = now - last_frame_time
                last_frame_time = now
                total_time_ms = (now - t_start) * 1000.0
                
                if dt > 0:
                    inst_fps = 1.0 / dt
                    current_fps = 0.9 * current_fps + 0.1 * inst_fps if current_fps > 0 else inst_fps

                if debug_window_active:
                    if not debug_window_created:
                        cv2.namedWindow("VIRTUAL POINTER", cv2.WINDOW_AUTOSIZE)
                        debug_window_created = True
                    annotated = draw_debug_frame(
                        frame, 
                        hands, 
                        "PAUSED" if is_paused else processor.right_state, 
                        processor.cursor_pos,
                        processor.right_visual_tips,
                        processor.left_visual_tips,
                        inference_time_ms,
                        total_time_ms,
                        current_fps,
                        camera.fps,
                        processor.click_state_text,
                        processor.last_pinch_norm,
                        processor.is_cursor_locked,
                        processor
                    )
                    cv2.imshow("VIRTUAL POINTER", annotated)
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord('q'):
                        break
                    elif key in (ord('d'), ord('D')):
                        on_activate_debug()
                    elif key in (ord('p'), ord('P')):
                        on_activate_pause()
                    elif key in (ord('s'), ord('S')):
                        on_activate_status()
                else:
                    if debug_window_created:
                        try:
                            cv2.destroyWindow("VIRTUAL POINTER")
                        except Exception:
                            pass
                        debug_window_created = False

                # Update Control Server telemetry (~10 times per second)
                if frame_count % 3 == 0:
                    active_gest = "idle"
                    ss_st = getattr(processor._screenshot, 'state', getattr(processor._screenshot, '_state', None))
                    if ss_st is not None and getattr(ss_st, 'name', '') == "HOLDING":
                        active_gest = "screenshot"
                    elif getattr(processor._wakanda, 'is_holding', False):
                        active_gest = "wakanda-forever"
                    elif getattr(processor, 'w_state', '') in ("CANDIDATE", "CONFIRMED"):
                        active_gest = "whatsapp"
                    elif getattr(processor, 'lip_state', 'IDLE') not in ("IDLE",):
                        active_gest = "mute"
                    elif getattr(processor.ear_volume_gesture, 'is_active', False):
                        is_vol_up = getattr(processor, 'ear_volume_direction', '') in ("VOLUME_UP", "UP")
                        active_gest = "volume-up" if is_vol_up else "volume-down"
                    elif getattr(actuator, 'is_dragging', False):
                        active_gest = "drag"
                    elif getattr(processor, 'pointer_owner', 'NONE') != "NONE":
                        active_gest = "pointer"

                    r_h = getattr(hands, 'right', None) if 'hands' in locals() and hands else None
                    l_h = getattr(hands, 'left', None) if 'hands' in locals() and hands else None
                    trk = "Both Hands" if (r_h and l_h) else ("Right Hand" if r_h else ("Left Hand" if l_h else "No Hands"))
                    vol_pct = int(processor.audio_controller.get_volume_scalar() * 100.0)
                    control_server.state.update_telemetry(
                        running=not is_paused,
                        tracking=trk,
                        fps=current_fps,
                        owner=processor.pointer_owner,
                        volume=vol_pct,
                        muted=processor.audio_controller.is_muted,
                        active_gesture=active_gest,
                        power_state=power_manager.state.name,
                    )

                # Update live spatial landmarks on every frame for immediate, low-latency overlay tracking
                def _ser_hand(h_lms):
                    if not h_lms:
                        return None
                    return [{"x": round(lm.x, 4), "y": round(lm.y, 4), "z": round(lm.z, 4)} for lm in h_lms]

                f_data = None
                if 'face' in locals() and face and getattr(face, 'detected', False):
                    lip_pts = None
                    if getattr(face, 'landmarks', None) and len(face.landmarks) > 291:
                        # Upper & lower outer lip contour landmarks from MediaPipe FaceMesh
                        lip_indices = [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291, 375, 321, 405, 314, 17, 84, 181, 91, 146]
                        try:
                            lip_pts = [[round(face.landmarks[idx].x, 4), round(face.landmarks[idx].y, 4)] for idx in lip_indices]
                        except (IndexError, AttributeError):
                            lip_pts = None

                    f_data = {
                        "detected": True,
                        "lip_center": [round(c, 4) for c in face.lip_center] if getattr(face, 'lip_center', None) else None,
                        "right_ear": [round(c, 4) for c in face.right_ear_pos] if getattr(face, 'right_ear_pos', None) else None,
                        "left_ear": [round(c, 4) for c in face.left_ear_pos] if getattr(face, 'left_ear_pos', None) else None,
                        "mouth_width": round(face.mouth_width, 4) if getattr(face, 'mouth_width', None) else None,
                        "lip_contour": lip_pts,
                    }

                r_h = getattr(hands, 'right', None) if 'hands' in locals() and hands else None
                l_h = getattr(hands, 'left', None) if 'hands' in locals() and hands else None

                control_server.state.update_landmarks(
                    hands_data={"right": _ser_hand(r_h), "left": _ser_hand(l_h)},
                    face_data=f_data,
                    is_locked=getattr(processor._right, 'is_cursor_locked', False),
                    click_state=getattr(processor, 'click_state_text', 'DISABLED'),
                    last_pinch_norm=getattr(processor, 'last_pinch_norm', 0.0),
                )

                # FPS telemetry — log once per 5 seconds
                frame_count += 1
                now = time.perf_counter()
                if now - fps_clock >= 5.0:
                    fps = frame_count / (now - fps_clock)
                    n_f = max(1, frame_count)
                    logger.info(
                        "FPS: %.1f | Cam: %.1fms | Hand: %.1fms | Face: %.1fms | Gest: %.1fms | Overlay: %.1fms",
                        fps, tot_cam_ms / n_f, tot_hand_ms / n_f, tot_face_ms / n_f, tot_gest_ms / n_f, tot_ovl_ms / n_f
                    )
                    tot_cam_ms = tot_hand_ms = tot_face_ms = tot_gest_ms = tot_ovl_ms = 0.0
                    frame_count = 0
                    fps_clock = now

        except KeyboardInterrupt:
            logger.info("Ctrl+C received — shutting down cleanly")
        except Exception:
            logger.error("Unhandled exception:\n%s", traceback.format_exc())
        finally:
            control_server.stop()
            if overlay:
                overlay.close()
            try:
                cv2.destroyAllWindows()
            except Exception:
                pass
            # Ensure drag is never left pressed on exit
            if getattr(actuator, 'is_dragging', False):
                actuator.drag_end()
            _restore_windows_settings(original_settings)
            original_settings.clear()  # prevent atexit double-restore
            logger.info("=== AI Air Mouse stopped ===")


if __name__ == "__main__":
    run()

# AIRPOINT — SYSTEM ARCHITECTURE (AS IMPLEMENTED)

**Document date:** 2026-11-02
**Repository:** `C:\Users\loges\Documents\air_point2_audit` (remote `https://github.com/Aadithya-kl/air_point2.git`)
**Branch:** `fix/p0-native-input-safety` at HEAD `4672829`
**Working tree:** 6 modified tracked files + 6 untracked files = the uncommitted P0 native-input-safety work (see §1.2). Nothing is staged.
**Backup of the P0 working tree:** `C:\Users\loges\Documents\air_point2_audit_backups\p0_worktree_backup_20261102_190141\` (patches, full copies, HEAD versions, SHA-256 manifest; checksums verified identical).

This document describes what the code actually does today. Every component entry gives the file, its responsibility, its dependencies, the data that flows through it, and the limitations found by reading and executing the code. It does not describe intended or future behaviour; that lives in `AIRPOINT_ENGINEERING_ROADMAP.md`.

---

## 1. Environment and baseline facts

### 1.1 Toolchain

| Item | Value |
|---|---|
| Python | 3.14.3 (`C:\Python314\python.exe`) |
| Backend virtualenv | `backend\.venv` (created 2026-11-02 from `backend\requirements.txt`; gitignored). Resolved versions: mediapipe 1.2.0, opencv-python 5.0.0.93, numpy 2.5.4, pynput 1.8.2, screeninfo 0.8.1, pycaw 20260927, comtypes 1.4.17, pillow 13.0.0, psutil 7.2.2 |
| Node / npm | v24.14.0 / 11.9.0; `frontend\node_modules` installed with `npm ci` from `package-lock.json` |
| Frontend stack | React 19, TanStack Start 1.168 / Router 1.170, Vite 8, Tailwind 4, Vitest 4, Radix UI, framer-motion, lucide-react |

`requirements.txt` pins no versions. The P0.3 validation report was produced with the interpreter of the *other* checkout (`...\antigravity\AirPoint\backend\.venv`). That interpreter carries `Lib\site-packages\airpoint_dev.pth`, which puts `C:\Users\loges\Documents\antigravity\AirPoint\backend` on `sys.path`. With that interpreter, guarded discovery of the canonical tree fails before any test runs ("`test_guard` module incorrectly imported from ...antigravity..."), because `sitecustomize.py` is resolved from the older checkout during interpreter start-up. Do not use that interpreter for this repository.

### 1.2 Uncommitted P0 work (preserved, not modified in Phase 0)

| File | State | Content |
|---|---|---|
| `backend/core/actuator.py` | modified | `SendInputResult` enum (CONFIRMED / UNCONFIRMED / FAILED); `_send_input()` no longer calls `mouse_event()`; `drag_start()` only marks a drag on CONFIRMED; `drag_end()` retries once and retains `is_dragging=True` on failure; `GetAsyncKeyState` telemetry |
| `backend/core/gestures/drag_controller.py` | modified | Removal of the immediate drop at `clear_release_norm_dist`; release always goes through `RELEASE_PENDING` + 80 ms dwell; DEBUG telemetry line |
| `backend/config.py` | modified | `LEFT_DRAG_LOST_TIMEOUT_S` 0.075 → 0.150 |
| `backend/core/debug_overlay.py` | modified | SEND HUD field understands the enum (OK / FAIL / UNCERTAIN / N/A) |
| `backend/test_drag_and_drop_pipeline.py` | modified | test 05 expects RELEASE_PENDING then one UP after dwell |
| `backend/test_phase2_left_hand.py` | modified | tests 10, 11, 14 satisfy the 80 ms dwell |
| `backend/test_native_input_safety.py` | untracked | 21 tests for the contract above |
| `backend/test_debug_overlay_send.py` | untracked | 9 tests for the HUD mapping |
| `AIRPOINT_PHASE_P0_IMPLEMENTATION_REPORT.md`, `AIRPOINT_P0_CODE_REVIEW.md`, `AIRPOINT_P0_3_REGRESSION_VALIDATION_REPORT.md`, `AIRPOINT_INDEPENDENT_ARCHITECTURE_REVIEW.md` | untracked | Reports from the previous phase |

### 1.3 Baseline test results (this session, canonical venv)

| Suite | Command | Result |
|---|---|---|
| Backend, guarded | `AIRPOINT_SETTINGS_PATH=:memory: AIRPOINT_ENABLE_TEST_GUARD=1 AIRPOINT_DISABLE_REAL_LOCK=1 .venv\Scripts\python -m unittest discover -s . -p "test_*.py"` (in `backend`) | 400 run, 395 pass, 5 fail, 0 errors, 21.9 s |
| Backend, unguarded (documented command) | `AIRPOINT_SETTINGS_PATH=:memory: .venv\Scripts\python -m unittest discover -s . -p "test_*.py"` | 400 run, 395 pass, same 5 failures |
| Frontend typecheck | `npx tsc --noEmit` | clean |
| Frontend unit | `npx vitest run` | 14 files, 135 tests, all pass (React `act()` warnings on stderr) |
| Frontend build | `npm run build` | succeeds (Nitro/Cloudflare target); regenerates `src/routeTree.gen.ts` with LF endings, restored afterwards |
| Backend after Phase 1 (guarded and unguarded) | same commands | 420 run, 420 pass (20 new tests in `test_phase1_drag_reliability.py`); a reversed-order subset also passes |
| Backend after the unified migration (guarded) | same command | 471 run, 471 pass (28 new tests in `test_dyne_events.py`; 443 before) |
| Frontend after the unified migration | `npx tsc --noEmit`, `npx vitest run`, `npm run build` | clean; 15 files, 144 tests, all pass (`maxWorkers: 4`); build succeeds, `routeTree.gen.ts` restored afterwards |
| Launcher after the unified migration | `.\scripts\start_airpoint.ps1 -Mode full -DryRun`; `-Mode frontend-only` start + `stop_airpoint.ps1` | dry run passes every check and starts nothing; the frontend-only cycle reached readiness in a few seconds, recorded PID + 4 node children, stopped only those, freed the port, left no process (engine modes were not started: the camera is never opened by the agent) |

The five baseline failures and their root causes are in §11.3. None was a production defect (two obsolete expectations, three test-isolation defects); all were resolved in Phase 1 without weakening production code.

---

## 2. System topology

```
┌────────────────────────────── Windows desktop ───────────────────────────────┐
│                                                                              │
│  Python process  (backend/main.py)                                           │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │ CameraCapture thread ──► latest-frame slot ──► MAIN THREAD loop       │    │
│  │   (core/camera.py)                             ├─ HandTracker (MP)   │    │
│  │                                                ├─ FaceTracker (MP)   │    │
│  │ pynput GlobalHotKeys thread ─► pause/quit/     ├─ PowerStateManager  │    │
│  │   (Ctrl+Alt+P/Q/S/D)            status/debug   ├─ GestureOrchestrator│    │
│  │                                                │    ├─ Right/Left/2H  │    │
│  │ AirPointControlServer thread                   │    ├─ Drag controller│    │
│  │   ThreadingHTTPServer 127.0.0.1:8765           │    └─ MouseActuator ─┼──► SendInput / pynput
│  │   ├─ GET  /api/status /api/events(SSE)         ├─ Tk "Dynamic Island"│    │   (Win32 cursor, buttons,
│  │   │       /api/landmarks /api/camera/*          │   overlay (main thr) │    │    keys, LockWorkStation)
│  │   └─ POST /api/settings /start /stop /control  └─ OpenCV debug window│    │
│  │        ──► settings_queue ──► drained each frame                      │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│             ▲ HTTP + SSE (loopback, token for mutations)                     │
│  Browser: React Control Center (frontend, Vite dev server :8080 or build)    │
│    AirPointEngineProvider ─ polls /api/status 1.5 s, SSE /api/events,        │
│    LiveTrackingCanvas polls /api/landmarks 50 ms + MJPEG /api/camera/stream  │
└──────────────────────────────────────────────────────────────────────────────┘
```

Three user-visible surfaces exist: the Windows cursor and system actions (native), the Tk overlay capsule drawn by the Python process, and the browser Control Center. The browser never draws a desktop overlay.

---

## 3. Process and thread model (backend)

| Thread | Created by | Work | Shared state |
|---|---|---|---|
| Main | `main.run()` | Frame acquisition, MediaPipe inference, gesture processing, all `SendInput` calls, Tk overlay drawing (`overlay.update_state` once per frame, rate-limited to ~30 Hz), OpenCV debug window | owns everything below |
| `CameraCapture` (daemon) | `AsyncCamera.start()` | `cv2.VideoCapture.read()` loop (DirectShow, 640×480, requested 30 fps, buffer 1), writes the latest frame + incrementing `frame_id` under a `Condition` | `_frame`, `_frame_id`, `_current_fps` |
| `AirPointControlServer` (daemon) + one thread per request | `ControlServer.start()` | HTTP/SSE; SSE handler threads block on a per-client `queue.Queue(maxsize=100)` | `RuntimeState` (lock), `settings_queue` → main loop, overlay `_dispatch_queue` → main loop |
| pynput hotkey listener | `keyboard.GlobalHotKeys` | Pause/resume, quit, status toast, debug window toggle | closures over `is_paused`, `is_running`; overlay calls go through `_dispatch_to_main` |

Cross-thread rules that the code relies on: HTTP settings changes are not applied directly; `RuntimeState.apply_settings` invokes `apply_ui_settings`, which only enqueues; `drain_settings_queue()` applies them on the main thread at the top of every loop iteration. Overlay methods called from non-main threads (`configure`, `start_test_countdown`, `show_pause_toast`, `show_runtime_status`, `show_app_toast`, `show_audio_toast`, `show_tracking_toast`, `show_wakanda_complete`, power-save toasts) queue a closure that `update_state` executes on the main thread. `show_ear_volume`, `show_success_toast`, `show_error_toast` and `hide/show` are called only from the main thread and execute immediately.

---

## 4. Backend component map

### 4.1 Entry point — `backend/main.py` (775 lines)

- **Responsibility:** process start-up and teardown, the inference loop, wiring of callbacks between gesture recognisers, the Tk overlay and the control server, telemetry publication.
- **Start-up order:** logging → `_apply_windows_performance()` (timeBeginPeriod 1 ms, HIGH_PRIORITY_CLASS via psutil, MMCSS "Games", SPI_SETMOUSE acceleration off, originals saved) → `build_virtual_desktop()` / `build_trackpad_zone()` → `MouseActuator` → hotkeys → `with AsyncCamera, HandTracker, FaceTracker:` → `GestureOrchestrator` → `ControlServer(host="127.0.0.1", port=8765).start()` → `PowerStateManager`, `FrameFreshnessDetector(3)` → `ScreenshotOverlay` and callback wiring → initial settings applied from `control_server.state.get_snapshot()["settings"]`.
- **Loop (per iteration):** drain settings → `camera.read_fresh(last_id, timeout=0.033)` → if no new frame: power-manager `evaluate_cadence(frame_valid=False)`, sleep 5 ms, abort after 5 s without frames → `FrameFreshnessDetector.check` (3 identical buffers = stale, skip) → `cv2.flip(frame, 1)` (selfie mirror; all later coordinates are mirrored) → `overlay.update_state(...)` → if not paused: interaction guard + `power_manager.evaluate_cadence` → FULL_RATE: hand inference, hand-presence transitions (0.15 s present → "reacquired", 0.35 s absent → "lost"), face inference every 3rd frame (every 2nd while ear/lip gestures are active), `power_manager.update_normal_activity`, `processor.process(hands, face)`; PROBE/CONFIRMATION: hands only, no actuation; SKIP: nothing → if paused: `processor.process(None, None)` → debug window (optional) → every 3rd frame `control_server.state.update_telemetry(...)` → every frame `update_landmarks(...)` for the browser canvas → FPS log every 5 s.
- **Shutdown (`finally`, Phase 1 order):** `processor._left.release_drag("SHUTDOWN")` → `actuator.force_release_drag(context="SHUTDOWN")` (bounded: 3 attempts, each a LEFTUP plus one retry; one CRITICAL line and `is_dragging` retained if still unconfirmed) → `control_server.stop()` → `overlay.close()` → `cv2.destroyAllWindows()` → `_restore_windows_settings`. The `atexit` hook also force-releases a held drag (`ATEXIT`) before restoring Windows settings if `finally` never ran. The hotkey listener is never stopped explicitly.
- **Pause (Phase 1):** `on_activate_pause` (called from the hotkey thread, HTTP handler threads or the debug window) only sets `pause_release_pending`; the main loop consumes the flag at the top of the next iteration via `release_drag_on_pause()`: controller release with reason `PAUSE`, then `force_release_drag(context="PAUSE")`, and a `drag-fault` SSE event if the release stays unconfirmed. No native input is issued from non-main threads any more.
- **Debug HUD switches:** `config.DEBUG_GESTURES`, the `--debug` argument (plain `sys.argv` check, no argparse) and Ctrl+Alt+D / the `d` key. The renderer `core.debug_overlay.draw_debug_frame` is imported unconditionally inside a guard; if that import ever fails, `DEBUG_HUD_IMPORT_ERROR` holds the reason and `debug_hud_available()` refuses the request with an ERROR log instead of crashing (F-26).
- **Limitations found:** `ControlServer.start()` runs outside the `try` block, so a port collision raises `RuntimeError` and the process exits during start-up (clean, but with no UI feedback). F-07 (release ordering and ignored result) is resolved in code; physical confirmation is pending (tests T7/T8 of the physical plan).

### 4.2 Configuration — `backend/config.py`

All tunables, imported by value at module import time (so tests that mutate `config.X` after import only affect code that re-reads `config` dynamically; `drag_controller.process_frame` does, `right_hand.process` does for pinch constants, `left_hand.__init__` does not). Relevant values: camera 640×480@30, trackpad margin 100, One Euro mincutoff 0.40 / beta 0.035 (overridden at runtime, see §5), pinch click start 0.50 / release 0.58 / confirm 0.10 s, left drag start 0.55 / release 0.75 / confirm 0.10 s / lost timeout 0.150 s, screenshot hold 3.0 s, W gesture hold 0.7 s, lip mute hold 0.6 s, ear volume 30 %/s, HUD durations, Wakanda disabled by default. `MP_MAX_HANDS = 1` is unused (tracker hard-codes `num_hands=2`).

### 4.3 Camera — `backend/core/camera.py`

- `AsyncCamera`: DirectShow capture thread; `read_fresh()` blocks up to `timeout` for a new `frame_id`; `fps` property updated once per second. No reconnection: a failed `read()` just loops with a 10 ms wait; `main.py` aborts after 5 s without frames.
- `FrameFreshnessDetector`: flags a frame as stale after N byte-identical consecutive buffers (N = 3 in `main.py`). Each check copies the frame (`np.ascontiguousarray(...).copy()` and `np.array_equal`), i.e. a 921 KB compare and copy per frame.

### 4.4 Hand tracking — `backend/core/tracker.py`

- `HandTracker`: MediaPipe Tasks `HandLandmarker`, `RunningMode.VIDEO`, `num_hands=2`, detection 0.55, presence/tracking 0.5, timestamps from `perf_counter` forced monotonic. Returns `HandsResult(left, right, left_score, right_score)`; each hand is 21 `Landmark(x, y, z, visibility)` in normalised frame coordinates (`y` down).
- Handedness: because the frame is mirrored before inference, MediaPipe's "Left" label is mapped to the user's anatomical **right** hand and vice versa. A single-hand label flip within 150 ms with score < 0.65 is suppressed (hysteresis).
- Any exception in inference is logged at WARNING and yields an empty `HandsResult` (silent tracking dropout).

### 4.5 Face tracking — `backend/core/face_tracker.py`

MediaPipe `FaceLandmarker` (VIDEO, 1 face). Produces lip centre (landmarks 13/14), mouth width (61↔291), face width (234↔454), ear anchors (the cheek landmarks, assigned by x order on the mirrored frame), and the full 478-point list. Missing model file disables face gestures with a warning.

### 4.6 Display geometry — `backend/core/display.py`

Sets per-monitor-v2 DPI awareness at import. `build_virtual_desktop()` uses `screeninfo` to compute the bounding box of all monitors; `VirtualDesktop(total_width, total_height, monitor_count)` is origin-relative. `map_to_desktop(nx, ny, trackpad, desktop)`: normalised → camera pixels → clamp to the trackpad zone → `np.interp` to `[0, W-1] × [0, H-1]` → clamp. No mirroring here (already mirrored). Coordinates are consistent with `MouseActuator.move()` (VIRTUALDESK absolute) and `get_cursor_pos()` (subtracts `SM_XVIRTUALSCREEN/SM_YVIRTUALSCREEN`), as the independent review's Errata E-04 concluded. Multi-monitor behaviour has not been physically verified.

### 4.7 Filtering — `backend/core/filter.py`

`OneEuroFilter(freq, mincutoff, beta, dcutoff, speed_scale=120)`, one instance per axis. Uses real elapsed time between samples (`freq` only sets the initial alpha and guards non-positive dt); resets the derivative when the gap exceeds 150 ms; the derivative is computed from raw samples (Casiez eq. 1); cutoff = `mincutoff + beta * speed_scale * |edx|`. `set_mincutoff/set_beta` are called from `set_smoothing()`.

### 4.8 Gesture orchestrator — `backend/core/gestures/orchestrator.py` (681 lines)

- **Responsibility:** per-frame routing of `HandsResult`/`FaceResult` to recognisers, priority arbitration between gestures, pointer ownership, cursor-jump limiting, the only call site of `actuator.move()` for pointer motion.
- **Order inside `process()`:** (1) drag watchdog `check_drag_watchdog(now, 0.25)` → on trigger `left.release_drag("WATCHDOG_TIMEOUT")`; (2) screenshot (`ScreenshotController`) — while active, releases any drag, re-asserts the last cursor position, feeds `None` to both hand processors, owner NONE, returns; (3) Wakanda (same suppression while holding; since the Wakanda fix it is not evaluated at all while a left drag is active or pending, and a stale hold is reset); (4) W gesture (CANDIDATE/CONFIRMED suppress the same way); (5) lip mute, only when no drag is active or pending; (6) ear volume — suppresses only the touching hand; (7) left hand with dropout grace; (8) right hand with dropout grace (≤3 frames and ≤120 ms); (9) two-hand processor when both hands present; (10) pointer ownership; (11) bounded movement.
- **Left dropout grace:** when `hands.left is None`, the orchestrator withholds `left.process(None)` for `grace_timeout` = the controller's `lost_timeout_s` (0.150 s) while a drag is locked or the actuator reports dragging, else 0.120 s; during grace it calls `actuator.keep_drag_alive(now)` itself. After the grace it calls `left.process(None, now)`, which releases immediately. Tracking-loss handling therefore has two owners (F-21).
- **Pointer ownership:** `is_left_actively_dragging` (controller `is_grab_locked` or legacy state names or `actuator.is_dragging`) locks `_drag_pointer_owner` for the drag's duration: existing RIGHT owner is kept, otherwise RIGHT if it has a cursor, else LEFT if pointing, else previous owner or RIGHT. Outside a drag: RIGHT has priority whenever it has a cursor; LEFT takes over only when RIGHT is absent; a RIGHT→LEFT handover while the right hand is still visible waits 80 ms. On any owner change the anchor is re-baselined to the last emitted position.
- **Movement:** target = owner's `cursor_pos`, suppressed when the hand's MediaPipe score is below 0.40 (0.20 during a drag). The first move after absence re-reads the physical cursor (`get_cursor_pos`) as the trusted anchor; with no anchor the move is suppressed (fail closed). The step from the anchor is limited to `max_step = clamp(24000 px/s × dt_eff, 380, 960)` with `dt_eff ∈ [1 ms, 40 ms]`; an opt-in `max_step_limit` tightens it. Then `actuator.move(x, y)`; the anchor becomes the emitted point.
- **Limitations found:** `max_step_limit` getter raised `TypeError` until Phase 1 (duplicate `@property`, F-04, fixed). During a drag the owner is locked to RIGHT even after the right hand is lost for > 120 ms, so the cursor freezes and the left hand cannot steer until the drag ends (F-22, documented by `test_owner_stays_right_and_cursor_freezes_when_right_lost_during_drag`; product decision pending). `reset()` is only called by tests; `main.py` never calls it.

### 4.9 Right hand — `backend/core/gestures/right_hand.py` (649 lines)

- Produces `_cursor_pos` from the One-Euro-filtered index tip (landmark 8) mapped through the trackpad; the position is frozen at `_locked_cursor_pos` during `PINCH_LOCKED`, `CLICK_PENDING` and `ZOOM_ACTIVE`.
- Pinch click state machine on `dist(4,8)/palm_width`: IDLE → PINCH_CANDIDATE (< 0.50) → confirmed after 0.10 s → "instant" mode fires `left_click(x, y)` (sets the cursor with `SetCursorPos` and sends absolute DOWN/UP) or a `double_click` when a second pinch lands within 750 ms and 100 px; "comfortable" mode buffers the first click. `PINCH_LOCKED` holds until the ratio exceeds 0.58; holding a pinch 350 ms fires a double-click once. Zoom: peace sign held 0.3 s → `ZOOM_ACTIVE`; index–middle spread ±0.15 sends Ctrl+= / Ctrl+-.
- Fist → `LOCKED` state, intended to stop cursor and gestures; the cursor position is assigned *before* that early return, so the orchestrator keeps moving the cursor with a fist (F-09).
- `_State.LEFT_PINCH_PENDING_DRAG` and `_State.DRAGGING` are never entered; the module docstring describing right-hand drag is stale (F-24). `drag_end()` calls inside this file are unreachable.
- Uses the global `click_tracer` (`core/click_diagnostics.py`), which logs every click transition at INFO and queries the real `GetCursorPos`.

### 4.10 Left hand — `backend/core/gestures/left_hand.py` (297 lines)

Owns a `LeftDragController` and the left pointer (`cursor_pos`, `is_pointing`): the index tip is filtered and mapped like the right hand; a fist disables left pointing unless a pinch/drag is active. All drag semantics are delegated. Constructor passes `lost_timeout_s` from `config` at construction time (0.150 with the P0 change), but `process_frame` re-reads `config.LEFT_DRAG_LOST_TIMEOUT_S` each frame anyway.

### 4.11 Drag controller — `backend/core/gestures/drag_controller.py` (525 lines)

Single owner of `actuator.drag_start()` / `drag_end()` for the product (confirmed by search: no other production caller of `drag_start`).

| State | Enter when | Leave to |
|---|---|---|
| READY | start, after any release | GRAB_PENDING when `norm_pinch < 0.55` (and the 150 ms rearm cooldown after an UNPINCH release has expired or the hand opened past 0.75) |
| GRAB_PENDING | pinch below start threshold | READY if `norm_pinch ≥ 0.75` before 100 ms; GRAB_LOCKED when the 100 ms confirm dwell passes **and** `drag_start()` returns STARTED; READY/INPUT_ERROR on FAILED (see below) |
| GRAB_LOCKED | native LEFTDOWN confirmed | RELEASE_PENDING when `norm_pinch ≥ 0.75` |
| RELEASE_PENDING | pinch opened | GRAB_LOCKED if `norm_pinch ≤ 0.75` before 80 ms (jitter recovery); READY via `_execute_drop` after 80 ms sustained; INPUT_ERROR if LEFTUP fails |
| INPUT_ERROR | LEFTDOWN failed and the cleanup `drag_end()` also failed, or LEFTUP failed | READY when the hand is open (`≥ 0.75`); the actuator button state is left to the watchdog |

Other release paths (all through `release_grab(reason)` → `actuator.drag_end()`): `TRACKING_LOSS` (landmarks `None`, immediately; or invalid landmark list after `lost_timeout`), `FEATURE_DISABLED`, `SCREENSHOT`, `WORKSTATION_LOCK`, `APP_LAUNCH`, `WATCHDOG_TIMEOUT`, `RESET`. The per-frame `keep_drag_alive` feeds the actuator watchdog while GRAB_LOCKED or RELEASE_PENDING (not while INPUT_ERROR, which is what lets the actuator watchdog retry a failed LEFTUP; since Phase 1 the watchdog re-arms after each unconfirmed attempt, so retries are spaced by 250 ms instead of running every frame — F-08 resolved).

Failed LEFTDOWN: the controller calls `drag_end()` "for safe recovery" (a no-op `NOT_DRAGGING` when nothing is held), returns to READY while the pinch is still closed, and will re-attempt after another 100 ms dwell. Failed LEFTUP: INPUT_ERROR; the controller never retries by itself.

`clear_release_norm_dist` (0.85) is still stored but no longer used for any decision (P0 change). Backward-compatibility aliases (`IDLE`, `DRAGGING`, `GRAB_CANDIDATE`, `RELEASING`) make `DragLockState` compare equal to legacy strings; `RELEASING` maps to READY, not RELEASE_PENDING.

### 4.12 Native input — `backend/core/actuator.py` (666 lines)

- `_send_input(INPUT) -> SendInputResult`: `SendInput(1, ...)` returned 1 → CONFIRMED; returned 0 → UNCONFIRMED (GetLastError logged; **no** `mouse_event` fallback any more); exception or missing user32 → FAILED. "CONFIRMED" means Windows accepted the record into the input stream, nothing more.
- `move(x, y)`: absolute 16-bit normalised coordinates with `MOUSEEVENTF_VIRTUALDESK`; returns `True` only on CONFIRMED (the orchestrator ignores the return value).
- `left_click(x, y)`: `SetCursorPos` + absolute DOWN, 5 ms, absolute UP; `double_click` = two clicks 50 ms apart; `right_click` logs when unconfirmed.
- `drag_start(now)`: ALREADY_ACTIVE if held; LEFTDOWN → CONFIRMED sets `_dragging=True`, records `_last_drag_time`, logs `GetAsyncKeyState(VK_LBUTTON)` as telemetry only; otherwise FAILED with `_last_drag_error="SENDINPUT_LEFTDOWN_FAILED"`.
- `drag_end()`: NOT_DRAGGING if idle; LEFTUP CONFIRMED clears state → RELEASED; otherwise one retry after 5 ms; still unconfirmed → FAILED with `is_dragging` retained and a CRITICAL log (the retry log tolerates non-enum results since Phase 1, F-06 fixed).
- `check_drag_watchdog(now, timeout_s=0.25)`: releases when no keep-alive for 0.25 s; after an unconfirmed release it re-arms (`_last_drag_time = now`) so retries are spaced by `timeout_s`.
- `force_release_drag(max_attempts=3, retry_delay_s=0.02, context)` (Phase 1): bounded release used by pause, shutdown and `atexit`; returns `NOT_DRAGGING`, `RELEASED` or `FAILED`; on failure sets `_last_drag_error = "DRAG_RELEASE_UNCONFIRMED_AT_<context>"`, keeps `is_dragging=True` and logs exactly one CRITICAL summary line.
- `get_native_left_button_state()`: `GetAsyncKeyState(0x01)` → DOWN/UP/UNKNOWN; diagnostic only.
- Keyboard shortcuts, scroll and zoom go through pynput controllers (no result reporting). `take_screenshot()` uses `PIL.ImageGrab.grab(all_screens=True)`; the post-capture callback is invoked before the file is saved and again in the failure path (F-12).
- `is_dragging` checks both `_dragging` and a legacy `_is_dragging` attribute (tests set the latter).
- `SendInputResult`, `DragStartResult`, `DragEndResult` define `__eq__` (bool-compatible) and, since Phase 1, `__hash__` (F-05 fixed).

### 4.13 Other gesture recognisers

| File | Gesture | Trigger → action | Notes |
|---|---|---|---|
| `core/gestures/screenshot.py` | both open palms facing camera, hold 3 s (1–10 s settable) | `actuator.take_screenshot(SCREENSHOT_DIR)` → `backend/screenshots/` | Blocks all other gestures while holding; rearm requires both hands out of pose for 0.5 s |
| `core/gestures/w_gesture.py` | two-hand "W" pose held 0.7 s | `AppLauncher.open_whatsapp()` (`os.startfile("whatsapp:")`, AUMID fallback) | Suppresses pointer while CANDIDATE/CONFIRMED |
| `core/gestures/lip_mute_gesture.py` | index tip at lip centre 0.6 s | `AudioController.toggle_mute()` (pycaw) | Disabled while a drag is active or pending |
| `core/gestures/ear_volume_gesture.py` | index tip at right/left ear, 0.2 s arm | continuous ±30 %/s via `AudioController.adjust_volume`, rate-limited 50 ms | Suppresses only the touching hand |
| `core/gestures/wakanda_gesture.py` | crossed fists on chest 2.0 s (0.15 s grace), then 2.0 s cooldown and release before rearm | one `LockWorkStation()` request per confirmed hold; the API return value decides `LOCK REQUEST ACCEPTED` / `FAILED` (`AIRPOINT_DISABLE_REAL_LOCK=1` mocks it; a real call is refused under a test runner) | Enabled by default since the Wakanda fix (was disabled at two layers and never ran, F-27); not evaluated while a left drag is active or pending; `hud_text` exposes DISABLED / SEARCHING (reason) / POSE DETECTED / HOLDING / CONFIRMED / LOCK REQUEST ACCEPTED / LOCK REQUEST FAILED / COOLDOWN |
| `core/gestures/two_hand.py` | both fists 1 s → Win+L; open left palm + right fist flick → Win+Left/Right | pynput keys | Runs whenever both hands are visible; no HUD/SSE events; `_THUMB_INDEX_DIST` pinch zoom branch is dead |

Supporting services: `core/app_launcher.py`, `core/audio_controller.py` (pycaw endpoint, saves/restores the volume scalar around mute), `core/click_diagnostics.py`.

### 4.14 Power state machine — `backend/core/power_state_machine.py`

Pure, clock-injected two-state manager (NORMAL / POWER_SAVE). Enters power save after 120 s of inactivity (palm velocity below 0.5 palm-widths/s and interaction guard clear); in power save, hands are evaluated every 3rd frame (PROBE) and a wake needs velocity ≥ 0.5 then ≥ 0.4 sustained 150 ms over ≥ 3 frames; a 10 s dwell prevents immediate re-entry. Disabled by default; toggled through the `power_save` setting.

### 4.15 Tk overlay ("Dynamic Island") — `backend/core/overlay.py` (1296 lines)

- Borderless, topmost, click-through (`WS_EX_LAYERED | WS_EX_TRANSPARENT`), transparent-colour Tk window at the top centre of the primary screen, 220×44 at rest.
- Internal state: `_island_state ∈ {IDLE, DROPPING, HOLDING, SUCCESS, ERROR, STATUS, RETRACTING}`, `_island_mode ∈ {"", VOLUME, WAKANDA, SCREENSHOT_HOLD, POWER_SAVE, POWER_SAVE_COMPLETE}`, priority levels CRITICAL 40 / VOLUME 30 / TRACKING 20 / STATUS 10, duplicate suppression of the same text within 0.8 s, slide animation factor 0.35.
- Driven two ways: `update_state(screenshot_controller, is_paused, wakanda)` each frame (screenshot hold countdown, Wakanda progress, power-save countdown, retraction) and explicit `show_*` calls from `main.py` callbacks.
- Settings consumed via `configure()`: `island_enabled` (hide/unhide), `notifications_enabled`, `timer_enabled` (countdown badge), `autohide_enabled`, `hud_duration_s` (power-save countdown length), `completion_duration_s`. `notifications_enabled` and `island_enabled` are checked only by the power-save family of toasts (`show_normal_mode`, `show_power_saver_*`, `start_power_save_countdown`, `show_wake_confirmed`); every gesture toast calls `root.deiconify()` unconditionally, so a disabled island can be re-shown by a gesture (F-15).
- Appearance (colours, fonts, geometry) is hard-coded; nothing from Dyne Studio reaches this file.

### 4.16 Debug window — `backend/core/debug_overlay.py`

OpenCV window "VIRTUAL POINTER" (toggle Ctrl+Alt+D or `--debug`): skeletons, fingertip rings, HUD lines including DRAG STATE / DRAG CFG (`LOG` = actuator flag, `BTN` = `GetAsyncKeyState`, `SEND` = last `SendInputResult`) and DRAG CURSOR (owner, source, moving).

### 4.17 Control server — `backend/core/control_server.py` (1010 lines)

- `RuntimeState`: lock-protected telemetry snapshot, settings (loaded from and persisted to `backend/settings.json`; `AIRPOINT_SETTINGS_PATH` overrides, `:memory:` disables), a 5-entry `recent_events` ring, SSE listener list, lifecycle callbacks into `main.py`.
- `ControlServer`: `ThreadingHTTPServer` with `SO_EXCLUSIVEADDRUSE`, bound to `127.0.0.1:8765`; on collision raises `RuntimeError` unless `allow_port_fallback` or `AIRPOINT_PORT_FALLBACK=1`, in which case it binds an ephemeral port. Writes `backend/bridge_info.json` (host, port, pid, token, started_at) and `backend/.bridge_token` on start and deletes them on stop (both gitignored). Token: 32-byte hex, also returned in every `/api/status` response.
- Request policy: `Host` must be `127.0.0.1`/`localhost`; `Origin`, when present, must be in `{localhost,127.0.0.1} × {8080, 5173, 8765}` plus `AIRPOINT_ALLOWED_ORIGINS` plus the server's own origin; mutations need a valid `X-AirPoint-Token`, or an allowed Origin, or (origin-less) a local Host; bodies ≤ 16 KB.

| Endpoint | Method | Payload / behaviour |
|---|---|---|
| `/api/status` | GET | `{running, tracking, fps, owner, volume, muted, active_gesture, power_state, drag{state, logical_held, native_button, last_error}, settings{...}, events[≤5], token}` (the `drag` block is Phase 1: controller state, logical flag, `GetAsyncKeyState` reading and last native error, published separately on purpose) |
| `/api/events` | GET | SSE: first `data: {"event":"connected","status":"ok"}`, then `data: {"event": <type>, "action": <text>, "time": "HH:MM:SS"}` per `add_event`; `: ping` keep-alive every 10 s; per-client queue of 100, overflow dropped silently |
| `/api/landmarks` | GET | latest hands (21×{x,y,z} each), face anchors (lip centre, ears, mouth width, 20-point lip contour), tracking/owner/active gesture, right-hand lock and click state, last pinch norm |
| `/api/camera/frame` | GET | one JPEG (q70, ≤480 px wide) of the mirrored processed frame |
| `/api/camera/stream` | GET | MJPEG multipart at ≤15 fps |
| `/api/settings` | POST | partial update of `{hold, sensitivity, smoothing, enabled{...}, power_save, island_*}`; clamped; persisted; applied on the main thread next frame; returns the full settings snapshot |
| `/api/stop`, `/api/start`, `/api/toggle` | POST | pause / resume via `main.py` callbacks |
| `/api/control` | POST | `{action: stop|shutdown|pause|start|resume|toggle|test_countdown, duration}` |
| `/api/overlay/test`, `/api/overlay/test_countdown` | POST | overlay test countdown |
| `/`, `/static/*` | GET | placeholder page, or `backend/ui_dist` if a build is placed there (no build is placed there today) |

Note that "stop" means *pause tracking*, not process exit; there is no endpoint that terminates the engine.

### 4.18 Test guard — `backend/test_guard.py`, `backend/sitecustomize.py`

`install_test_guard()` replaces `user32.SendInput/SetCursorPos/mouse_event/keybd_event/LockWorkStation` with raising stubs, substitutes a deterministic `GetCursorPos` (default (960, 540)), blocks `os.startfile`, `subprocess.Popen` (except `ver`), integer-index `cv2.VideoCapture`, and pynput controllers; since Phase 1 it imports `pynput.mouse` and `pynput.keyboard` explicitly before patching, so the protection no longer depends on import order (F-02 fixed). `sitecustomize.py` installs it at interpreter start when `AIRPOINT_ENABLE_TEST_GUARD=1`; `core/actuator.py` installs it on import under the same variable. `scripts/run_checks.ps1` sets `AIRPOINT_ENABLE_TEST_GUARD=1` and `AIRPOINT_DISABLE_REAL_LOCK=1` since Phase 1 (F-18 fixed).

---

## 5. Pointer pipeline (camera → Windows cursor), as executed

1. `CameraCapture` thread stores the newest 640×480 BGR frame; the main loop waits ≤ 33 ms for a new `frame_id`.
2. Freshness check (byte-identical ×3 → skipped), `cv2.flip(…, 1)`.
3. `HandTracker.process()` (BGR→RGB conversion done once in `main.py` and reused for the face tracker) → up to two hands with scores; handedness inverted for the mirror.
4. Orchestrator gating (screenshot / Wakanda / W / lip / ear) decides whether the right hand is processed at all.
5. `RightHandProcessor.process`: `OneEuroFilter` per axis on landmark 8, timestamp = `perf_counter()` taken inside `process` (not the camera timestamp). Runtime parameters come from the smoothing slider: `set_smoothing(s)` maps `s ∈ [10, 100]` to `mincutoff ∈ [1.0, 0.12]` and `beta ∈ [0.04, 0.008]`; the default persisted value 65 gives mincutoff ≈ 0.46, beta ≈ 0.020, so the `ONE_EURO_*` constants in `config.py` are overridden at every start-up (F-20).
6. `map_to_desktop`: the trackpad zone is rebuilt by `set_sensitivity(s)`: span = (640−2×100)/s horizontally and (480−2×100)/s vertically, clamped to ≥80×60 and ≤(608×448), centred, with a 16 px border; the default 0.85 yields x ∈ [61, 579], y ∈ [75, 405]. Positions outside the zone are clamped (edge dead zone), then linearly interpolated to the virtual desktop.
7. Orchestrator ownership and jump limiting (§4.8), then `MouseActuator.move()` → `SendInput` absolute move.
8. Every 3rd frame the owner/fps/tracking telemetry is published; every frame the landmarks are published for the browser canvas.

Measured timing: none is recorded per frame; only the 5-second average log line (`FPS | Cam | Hand | Face | Gest | Overlay` ms). Historical audits report ≈15 fps processed versus the 30 fps camera target; this session did not run the camera. The One Euro filter uses `perf_counter()` at processing time rather than the capture timestamp, so capture jitter and processing jitter are indistinguishable to the filter.

---

## 6. Native input contract (what is and is not established)

| Statement | Status |
|---|---|
| `SendInput` returned 1 ⇒ Windows accepted the input record | established by API semantics; this is what CONFIRMED means |
| CONFIRMED ⇒ the target window received the button event | **not established**; UIPI, elevated foreground windows and secure desktop can accept the record and still not deliver |
| `GetAsyncKeyState(VK_LBUTTON)` reports DOWN after an injected LEFTDOWN | logged as telemetry, never gated on; semantics under injection not measured |
| A drag "succeeded" (object moved/dropped) | never observed programmatically; no test or harness checks application-visible outcome |
| Failed LEFTDOWN never produces a logical drag | established by code and 21 mock tests |
| Failed LEFTUP keeps `is_dragging=True` and is retried by the watchdog | established by code and mock tests; physical behaviour not observed |

The debug HUD shows three independent observations (`LOG` logical flag, `BTN` async key state, `SEND` last result) precisely so that they are not conflated.

---

## 7. Notification and event pipeline (one Dyne event system)

The unified migration (Stage E, 2026-11-02) replaced the three disconnected surfaces with one dispatcher owned by `RuntimeState` (`backend/core/events.py`):

```
gesture / engine code ──► RuntimeState.publish_event(type, message, source=, metadata=)
                             │  EventDispatcher: monotonic id per process, random session token, ring of 50
                             ├─► RuntimeState._on_dyne_event ─► /api/status (10 newest), /api/events/history (ring),
                             │                                   SSE fan-out with `id:` lines (Last-Event-ID replay)
                             │        └─► React AirPointEngineProvider: parseDyneEvent / mergeEvents (dedupe by
                             │            `${session}:${id}`, newest first, ≤ 50) ─► DyneLiveIsland in DesktopShell
                             └─► ScreenshotOverlay.handle_event ─► Tk capsule toasts (gated by the Dyne switches)
```

### 7.1 Schema (`DyneEvent.to_dict()`)

`id`, `session`, `type` (dotted, catalogued in `EVENT_CATALOGUE`), `timestamp` (epoch), `time` (local `HH:MM:SS`), `source`, `title`, `message`, `priority` (`low|normal|high|critical`), `duration_s`, `metadata`, plus the legacy keys `event` (short kind) and `action` (= message). Bridge payloads expose the legacy kind as `type` and the dotted type as `event_type` so pre-migration consumers keep working. Every type has catalogue defaults (title, priority, duration, legacy kind); producers may override message and metadata.

### 7.2 Producers (each publishes after the real outcome is known)

| Event type | Producer | Desktop capsule |
|---|---|---|
| `engine.started` / `engine.stopping` | `main.py` after settings are applied / in `finally` after the drag release and before the bridge stops | none (Control Center only) |
| `engine.paused` / `engine.resumed` | `on_activate_pause` (hotkey, Control Center, debug-window key) | pause / resume toast |
| `tracking.acquired` / `tracking.lost` / `tracking.recovered` | main loop hand presence (0.15 s present / 0.35 s absent) | lost / reacquired toasts (no toast for the first acquisition) |
| `screenshot.captured` / `screenshot.failed` | `ScreenshotController.capture_result_cb(success, path)`, called after `take_screenshot` returned (F-12 fixed; `post_capture_cb` is overlay re-show only) | rendered from the controller state in `update_state` |
| `app.launched` / `app.launch_failed` | W-gesture callback | app toast |
| `audio.muted` / `audio.unmuted` / `audio.failed` | lip-gesture callback | audio toast |
| `audio.volume` | `VolumeEventCoalescer`: at most one event per 250 ms while the gesture is active plus one final event (F-13 fixed); the live bars still receive every 50 ms tick directly | live volume visualizer (direct call, HUD state) |
| `drag.started` / `drag.completed` / `drag.released` / `drag.failed` | `DragEventTracker.observe(drag_state_name, release_reason, drag_controller.last_error)` once per frame in `main.py` (read-only observation of the controller; it never touches the controller or the actuator) and `release_drag_on_pause` for an unconfirmed pause release | `drag.failed` → error notice "Drag fault: release the left mouse button"; the others are Control Center only |
| `wakanda.confirmed` then `lock.accepted` / `lock.failed` | Wakanda callback with the `LockWorkStation` result | Wakanda capsule / failed toast |
| `power.save_entered` / `power.wake` | power manager transitions | countdown capsule / wake toast |

Ctrl+Alt+S runtime status and the power-saver toggle toasts remain direct overlay calls (they are user actions, not engine events). Nothing publishes `screenshot.captured` before the file is written and nothing publishes `lock.accepted` without a non-zero API result.

### 7.3 Transport and consumers

- `GET /api/events`: `: connected` + hello `{"event": "connected", "session", "last_event_id"}`, then `id: N` / `data: {...}` blocks; a `Last-Event-ID` header (sent automatically by `EventSource` on reconnect) or `?after=N` replays the missed ring entries before live events, without duplicates; 10 s keep-alive ping.
- `GET /api/events/history?after=N&limit=50`: the ring in ascending id order with `session` and `last_event_id`.
- `GET /api/status`: `events` (10 newest), `event_session`, `last_event_id`.
- Frontend (`engine.tsx`): status and SSE events are merged (`mergeEvents`) instead of replaced (F-11 fixed); `eventStream` (`connecting|open|reconnecting|unsupported`) is shown on Overview and About; a different `session` in the SSE hello (engine restart) rebuilds the feed from `/api/events/history`.
- Live island (`components/air-point/dyne-live-island.tsx`, mounted by `DesktopShell`, F-14 fixed): shows an event only when its sequence is newer than everything seen in the current engine session after first contact (history present at connect never raises it), ignores `low` priority, honours `island_enabled`, `island_notifications_enabled` and `island_autohide_enabled`, uses `duration_s`, the persisted Dyne appearance and position, and carries `data-live="true"` plus a LIVE tag. Dyne Studio capsules and `DynamicIslandPreview` keep their "PREVIEW"/"DEMO" copy.
- Tk overlay (`handle_event` + per-toast gating): discrete toasts require `island_enabled and notifications_enabled`; progress capsules (screenshot hold, Wakanda hold, power countdown, live volume) require only `island_enabled`; `update_state` draws nothing while the HUD is disabled, and `show()` no longer re-enables a disabled HUD after a screenshot (F-15 fixed).

---

## 8. Backend ↔ frontend integration

| Concern | Implementation | Gap |
|---|---|---|
| Base URL | `BRIDGE_BASE_URL = resolveBridgeBaseUrl(import.meta.env.VITE_AIRPOINT_BRIDGE_URL)` (`frontend/src/lib/air-point-model.ts`): the launcher reads `backend/bridge_info.json` after the engine bound its port and passes the origin to the dev server; only `http://127.0.0.1|localhost[:port]` is accepted, anything else falls back to `http://127.0.0.1:8765`. Status pills and About derive their host text from the resolved URL (F-10 fixed for launcher-started runs) | a dev server started by hand still uses the default port unless `VITE_AIRPOINT_BRIDGE_URL` is set |
| Port collision | backend raises and exits; the launcher refuses a busy port (reporting the owner) unless `-AllowPortFallback`, which sets `AIRPOINT_PORT_FALLBACK=1` and discovers the chosen port through `bridge_info.json` | — |
| Authentication | token from `GET /api/status` → `X-AirPoint-Token` on mutations; dev-server origins whitelisted; the stop script reads `backend/.bridge_token` to authenticate the exit request | fine for loopback; `.bridge_token` is a plain file |
| Liveness | status poll every 1.5 s with 2 s abort; `connected` flips on any failure; SSE `EventSource` auto-reconnects with `Last-Event-ID`, the bridge replays missed events; `eventStream` state is displayed | no poll backoff |
| Settings sync | POST `/api/settings` with optimistic local update, snapshot re-applied from the response; status poll re-applies settings every cycle; `island_position` and `island_appearance` are part of the snapshot | a stale poll can briefly overwrite an in-flight slider value (Dyne Studio guards this with local state + version counter; the cursor page does not) |
| Lifecycle | `/api/stop` and `/api/start` pause/resume; `/api/control {"action": "exit"}` (token) raises an exit flag consumed by the engine main loop, which then runs the normal shutdown (drag release first); `lifecycleLockRef` + sequence number guard against stale polls | "Shutdown" in the UI only pauses tracking; "exit" is used by the stop script, not exposed in the UI |
| Startup | `scripts/start_airpoint.ps1` (see §8.1) starts, verifies and records both services; `stop_airpoint.ps1` asks the engine to exit through the bridge, then stops only verified own processes | the frontend dev server is required at runtime; `backend/ui_dist` static hosting exists but is unused |

### 8.1 Unified launcher (`scripts/start_airpoint.ps1`, `scripts/stop_airpoint.ps1`)

- Root, python (`backend\.venv\Scripts\python.exe`, required) and frontend directory are resolved from the script location; the legacy checkout is never referenced.
- Prerequisites: canonical layout markers, Python version and engine imports (`cv2, mediapipe, pynput, psutil, screeninfo, numpy`), both model bundles, Node, npm, `frontend\node_modules`.
- Ports: listeners on the backend and frontend ports are reported with PID, name and whether their command line references this repository.
- Duplicate protection: `.airpoint\airpoint_pids.json` (version 2: root, mode, bridge URL, backend/frontend PIDs, node child PIDs, log paths); live recorded processes block a second start, stale records are removed.
- Backend: `Start-Process` of `main.py` (or `core\control_server.py`), stdout/stderr to `logs\backend_<stamp>.log|.err.log` (hidden window) unless `-ShowConsoles`. `backend\.venv\Scripts\python.exe` is the venv launcher stub: `Start-Process` returns the stub's PID and the real interpreter (the engine, `os.getpid()` in `bridge_info.json`) is its child. Health (`Wait-BridgeHealthy` in `scripts/airpoint_launcher_lib.ps1`) therefore resolves the engine from the started process tree: engine child alive → `bridge_info.json` written by a PID of that tree (a file from another tree is "foreign", a file older than the launch is "stale") → `GET /api/status` 200 with a status payload, within `-BackendTimeoutSec` (60 s). The PID record stores the engine child (`pid`), the stub (`launcherPid`) and the descendants. Failure reports distinguish process-exited / no-bridge-info / bridge-foreign-pid / bridge-not-answering / bridge-bad-response. (Corrected after the 2026-11-02 launch, which compared the stub PID with the engine PID and never probed a bridge that had been healthy for 58 s.)
- Self-test: `scripts/launcher_selftest.ps1` runs the same library functions against `backend/launcher_bridge_probe.py` (a real `ControlServer` with the exit callback, no camera, no input) and checks stub-versus-child resolution, foreign-tree rejection, the `/api/status` probe, the graceful exit of the whole tree and the removal of the discovery files.
- Frontend: `cmd /d /c npm run dev -- --port <p> --host 127.0.0.1 --strictPort` with `VITE_AIRPOINT_BRIDGE_URL` from the discovered bridge; readiness = HTTP 200 on `http://127.0.0.1:<p>/` within `-FrontendTimeoutSec` (90 s); node children recorded after readiness.
- Partial failure: whatever was already started is stopped (verified tree) and the PID file removed; exit codes 2 prerequisites, 3 port, 4 duplicate, 5 backend, 6 frontend, 7 unexpected.
- `-DryRun` performs every check and prints the exact commands without starting or writing anything; `-DebugHud` passes `--debug` to `main.py`.
- Stop: graceful `exit` through the authenticated bridge (waits `-GracefulTimeoutSec`, default 10 s) before any `Stop-Process`, accepted when `bridge_info.json` belongs to any process of the recorded tree (stub, engine child, recorded children); then waits for the whole tree to end; forced stop goes deepest-first through the live descendants; every process is verified by command line, by being a live descendant of the recorded root, or by being a recorded child created within two minutes of the service start; `-IncludeOrphans` extends the search to processes whose command line references this repository; never kills every `python.exe`/`node.exe`; bridge files are removed only when no engine remains.

---

## 9. Frontend architecture

- **Routing:** TanStack Start file routes: `/` (Overview: live canvas, telemetry cards, 8 gesture toggles, recent activity), `/gestures` (library + inspector, screenshot hold slider, Wakanda deck), `/cursor` (sensitivity/smoothing sliders, presets, browser-only playground), `/island` (Dyne Studio), `/appearance` (theme/accent/density/reduced motion), `/about` (diagnostics manifest). `__root.tsx` wraps everything in `QueryClientProvider` → `AirPointEngineProvider` → `DesktopShell`.
- **State:** a single React context (`components/air-point/engine.tsx`) holds bridge telemetry, engine settings, mutation feedback, the merged Dyne event feed (`events`, `eventStream`, `liveNotification`), the persisted Dyne position and appearance (`islandPosition`, `islandAppearance` with setters), the Studio-only island preview state, and UI preferences. No TanStack Query usage beyond the provider.
- **Live island:** `components/air-point/dyne-live-island.tsx` is mounted by `DesktopShell` and renders `engine.liveNotification` (real events only) with the persisted appearance/position; see §7.3.
- **Live tracking:** `live-tracking-canvas.tsx` polls `/api/landmarks` every 50 ms when connected and overlays skeletons on the MJPEG stream.
- **Dyne Studio** (`components/air-point/dyne-studio/*`): a capsule carousel of the 17 `DynamicIslandState` names with per-capsule appearance (`accent, texture, font, fontSize, weight, intensity, matteIntensity, translucentIntensity, roundness, style, customRgb`) as previews; Notifications and Behaviour & Timing write the six `island_*` settings through `DyneHostAdapter` → `commitDesktopSettings` → `engine.setIslandSettings` (filtered by `CapabilityMap`, validated by `isValidAirPointSettingValue`); the new Position category writes `island_position`; "Apply this look" writes the current capsule's appearance as `island_appearance` (`hostAdapter.setIslandAppearance`) and "Load live look" copies the applied look back into the preview; the status pill under the stage says `PREVIEW · NOT APPLIED` or `THIS LOOK IS LIVE`; "Test countdown" posts `/api/control {action: test_countdown}`.
- **Persistence:** `localStorage["air-point.ui-preferences.v1"]` for theme/accent/density/reducedMotion/feedbackDuration; the inline anti-flash script in `__root.tsx` now reads the same key (F-16 fixed). Dyne position and the applied appearance are persisted by the engine in `backend/settings.json` and used by both the Tk overlay (position, accent colour) and the live React island (position, full look).
- **Build:** `@lovable.dev/vite-tanstack-config`, Nitro server bundle with a Cloudflare worker target; `src/server.ts` wraps SSR errors. The app is not packaged for the desktop; it is a dev-server web app.
- **Tests:** 15 Vitest files / 144 tests covering routing, engine lifecycle controls, Dyne Studio navigation and host-boundary filtering, live tracking parsing, power saver, tutorials, and (`src/test/dyne-live-events.test.tsx`) bridge URL validation, event parsing/merging, the live island driven by status-poll and SSE fixtures, the notifications switch, the preview/live distinction and the Studio apply-look flow. Fetch and `EventSource` are mocked in tests; no test exercises a real bridge. `vitest.config.ts` caps `maxWorkers` at 4 because one jsdom fork per logical CPU crashed workers on the development machine (16 CPUs, 15.7 GB).
- **Copy:** `/about` now states "HTTP status poll + Server-Sent Events (<bridge url>)" and shows the event-stream state (F-17 fixed); the README launcher section describes the unified launcher.

---

## 10. Settings and persistence matrix

| Setting | Where set | Where stored | Consumed by | Live effect |
|---|---|---|---|---|
| gesture enabled ×8 | Overview / Gestures | `backend/settings.json` | `drain_settings_queue` → recognisers' `enabled` flags, `pointer_enabled`, `drag_enabled` (disabling drag releases an active drag) | next frame |
| sensitivity 0.2–4.0 | Cursor page | `settings.json` | `set_sensitivity` on both hand processors (trackpad zone) | next frame |
| smoothing 10–100 | Cursor page | `settings.json` | `set_smoothing` (One Euro mincutoff/beta) | next frame |
| hold 1–10 s (UI 1–5) | Gestures page | `settings.json` | `ScreenshotController.hold_duration` | next frame |
| power_save | Overview / shell | `settings.json` | `PowerStateManager.set_enabled` + overlay toasts | next frame |
| island_enabled, island_notifications_enabled, island_timer_enabled, island_autohide_enabled, island_hud_duration_s (10–1800), island_completion_duration_s (1–5) | Dyne Studio | `settings.json` | `overlay.configure(...)` (toasts gated by both switches, progress capsules by the HUD switch; F-15 fixed) and the live React island (`enabled`, `notificationsEnabled`, `autohideEnabled`) | next frame |
| island_position (`top-center`, `top-left`, `top-right`, `bottom-center`) | Dyne Studio → Position | `settings.json` | `overlay.configure(position=)` → `_apply_position` (x, y_visible, y_hidden); live island CSS placement | next frame |
| island_appearance (accent, texture, font, fontSize 18–28, weight 300–800, intensity/matteIntensity/translucentIntensity 0–100, roundness 28–56, style, customRgb) | Dyne Studio → Apply this look | `settings.json` (validated by `sanitize_island_appearance`) | `overlay.configure(appearance=)` → accent colour of bars/tracks/badge; live island look | next frame |
| theme, accent, density, reducedMotion, feedbackDuration | Appearance | browser localStorage | frontend only | immediate |
| Dyne capsule previews (11 fields × 17 capsules) | Dyne Studio | memory only | previews only, until "Apply this look" copies the active one into island_appearance | lost on reload (the applied look is not) |
| All `config.py` thresholds | code | — | import-time constants | restart |

---

## 11. Test infrastructure

### 11.1 Inventory

- Backend: 44 files match `test_*.py` (unittest suites including the Phase 1 `test_phase1_drag_reliability.py`, `test_debug_hud_startup.py`, `test_wakanda_lock_fix.py` and the migration's `test_dyne_events.py`; `test_guard.py` helper; `test_startup.py` manual smoke script with no TestCase); 3 `validate_stage4_*.py` live harnesses that are not collected; `preflight_physical_test.py` (Phase 1) is a hardware-free start-up check for the physical plan, also not collected. 471 tests collected.
- Frontend: 15 Vitest files, 144 tests, `jsdom`, `src/test/setup.ts` stubs `matchMedia`, `ResizeObserver`, media playback; `maxWorkers: 4`.
- Launcher: parse check with `[System.Management.Automation.Language.Parser]::ParseFile`, `start_airpoint.ps1 -DryRun`, and a `-Mode frontend-only` start/stop cycle (node only; the agent never starts the engine).

### 11.2 How to run safely

```
cd backend
set AIRPOINT_SETTINGS_PATH=:memory:
set AIRPOINT_ENABLE_TEST_GUARD=1
set AIRPOINT_DISABLE_REAL_LOCK=1
.venv\Scripts\python.exe -m unittest discover -s . -p "test_*.py"
```

```
cd frontend
npx tsc --noEmit
npx vitest run
npm run build
```

`scripts/run_checks.ps1` runs the same four gates with the guard variables set (Phase 1).

### 11.3 Baseline failures (5) and root causes — all resolved in Phase 1

| Test | Root cause | Classification |
|---|---|---|
| `test_test_guard.test_pynput_mouse_controller_blocked`, `..._keyboard_controller_blocked` | `test_native_input_safety.py` assigns `sys.modules["pynput"] = MagicMock()` (and `pynput.mouse`, `pynput.keyboard`, `mediapipe*`, `screeninfo`, `PIL`) at import time and never restores them; after that module is imported, `sys.modules["pynput"]` stays a MagicMock for the rest of the process (reproduced). Which `pynput` object the guard patched then depends on import order: the two guard assertions pass when run alone or in the pair `[test_native_input_safety, test_test_guard]`, and fail only in the full-discovery order. Order-dependent failures of this kind are the signature of process-wide module stubbing. | test-isolation defect (F-01) |
| `test_tracker_handedness.test_handedness_mapping` | Same stubs: `sys.modules["mediapipe.tasks.python"]` becomes an empty module. Reproduced with the pair `[test_native_input_safety, test_tracker_handedness]`: `AttributeError: module 'mediapipe.tasks.python' has no attribute 'BaseOptions'` when `core.tracker` is first imported after the stub; under full discovery (tracker imported earlier) the symptom is an empty `HandsResult`. Passes alone. | test-isolation defect (F-01) |
| `test_phase6_drag.test_left_drag_release_drops` | asserts a drop after one unpinched frame; P0 requires 80 ms in RELEASE_PENDING | obsolete expectation (F-03) |
| `test_left_hand_drag_reliability.test_intentional_open_palm_drops_file_immediately` | same obsolete expectation | obsolete expectation (F-03) |

The previous P0.3 report attributed the handedness failure to "live webcam/display hardware"; that attribution is wrong.

**Phase 1 resolution.** The `sys.modules` stubs were removed from `test_native_input_safety.py` (the real packages are installed); `install_test_guard()` imports the pynput submodules explicitly; the two obsolete tests were aligned to the 80 ms release dwell. A fourth hidden dependency surfaced once isolation was fixed: `test_phase6_drag.test_missing_left_cancels_drag` expected a release after 100 ms of tracking loss and had only passed because the `tearDown` methods of `test_drag_safety.py` and `test_phase2_left_hand.py` left the pre-P0 value `0.075` in `config.LEFT_DRAG_LOST_TIMEOUT_S` for every later module (F-25). Those tearDowns now restore the original value and the test expects the 150 ms grace. Result: 420/420 in guarded and unguarded discovery and in a reversed subset order.

---

## 12. Verified findings (consolidated register)

Status codes: **E** = reproduced by execution in this session, **R** = established by reading the code (not executed).

| ID | Area | Finding | File(s) | Status |
|---|---|---|---|---|
| F-01 | tests | Top-level `sys.modules` stubs in the P0 safety test contaminate later modules | `backend/test_native_input_safety.py` | E → fixed (Phase 1) |
| F-02 | tests | Test guard patches pynput controllers only if submodules were already imported | `backend/test_guard.py` | R (consequence E) → fixed (Phase 1) |
| F-03 | tests | Two legacy tests assert pre-P0 immediate drop | `backend/test_phase6_drag.py`, `backend/test_left_hand_drag_reliability.py` | E → fixed (Phase 1) |
| F-04 | pointer | `GestureOrchestrator.max_step_limit` getter raises `TypeError` (double `@property`) | `backend/core/gestures/orchestrator.py` | E → fixed (Phase 1) |
| F-05 | actuator | `SendInputResult`/`DragStartResult`/`DragEndResult` members are unhashable | `backend/core/actuator.py` | E → fixed (Phase 1) |
| F-06 | actuator | `drag_end()` retry log uses `res.value` unconditionally | `backend/core/actuator.py` | R → fixed (Phase 1) |
| F-07 | shutdown | Drag released after server/overlay teardown; `drag_end()` result ignored; no retry; same on pause | `backend/main.py` | R → fixed in code (Phase 1); physical confirmation pending |
| F-08 | drag | Persistent LEFTUP failure → watchdog calls `drag_end()` every frame (2 attempts + CRITICAL log per frame) | `backend/core/actuator.py` | R → fixed (Phase 1, retry every 250 ms) |
| F-09 | pointer | Right-hand fist `LOCKED` state does not stop cursor movement | `backend/core/gestures/right_hand.py:286-297` | R |
| F-10 | bridge | Port 8765 hard-coded on both sides; collision aborts start-up; fallback port undiscoverable; `bridge_info.json` unread | `backend/main.py`, `control_server.py`, `frontend/src/lib/air-point-model.ts` | R → fixed (unified migration): the launcher reads `bridge_info.json` and passes `VITE_AIRPOINT_BRIDGE_URL` (loopback-only, validated by `resolveBridgeBaseUrl`); `-AllowPortFallback` covers collisions; a hand-started dev server still needs the variable |
| F-11 | events | Status poll replaces the frontend event list with the backend's 5-entry ring every 1.5 s; no event ids | `frontend/src/components/air-point/engine.tsx` | R → fixed (ids `${session}:${id}`, `mergeEvents`, ring of 50, SSE `id:` lines with Last-Event-ID replay, `/api/events/history`) |
| F-12 | events | "Screenshot saved" emitted before save and on failure | `backend/core/gestures/screenshot.py`, `main.py` | R → fixed (`capture_result_cb` after `take_screenshot` returned; `screenshot.failed` on error; `test_dyne_events.py` §8) |
| F-13 | events | Ear-volume SSE event per 50 ms tick | `backend/main.py`, `core/events.py` | R → fixed (`VolumeEventCoalescer`: ≤ 4 events/s + one final; the overlay visualizer still gets every tick) |
| F-14 | Dyne | React island preview unmounted; SSE never drives it; appearance settings memory-only | `frontend/src/components/air-point/dyne-live-island.tsx`, `shell.tsx`, `engine.tsx`, `dyne-studio.tsx` | R → fixed (live island mounted in the shell and driven by real events; position and applied appearance persisted in `settings.json`; previews stay labelled) |
| F-15 | overlay | `island_enabled`/`notifications_enabled` ignored by gesture toasts (unconditional `deiconify`) | `backend/core/overlay.py` | R → fixed (`_notifications_allowed()` on every toast, `update_state` early return and `show()` guard when the HUD is disabled; `test_dyne_events.py` §7) |
| F-16 | frontend | localStorage key mismatch (`ui.preferences` vs `ui-preferences`) → theme flash | `frontend/src/routes/__root.tsx` | R → fixed (same key in the anti-flash script) |
| F-17 | docs/UI | About page claims WebSocket; README test counts and `bridge_info.json` claim stale | `frontend/src/routes/about.tsx`, `README.md` | R → fixed (About shows "HTTP status poll + Server-Sent Events" and the stream state; README launcher section rewritten) |
| F-18 | tests | `run_checks.ps1` runs backend tests unguarded | `scripts/run_checks.ps1` | R → fixed (Phase 1) |
| F-19 | env | Prior validation interpreter leaks the older checkout onto `sys.path` (`airpoint_dev.pth`) | `...\antigravity\...\.venv\Lib\site-packages\airpoint_dev.pth` | E |
| F-20 | config | `MP_MAX_HANDS` unused; `ONE_EURO_*` overridden at start-up by `set_smoothing(65)` | `backend/config.py:19,33-35`, `main.py:403` | R |
| F-21 | drag | Tracking-loss grace split between orchestrator (withholds `process(None)`) and controller (immediate release) | `orchestrator.py:257-286`, `drag_controller.py:246-248` | R |
| F-22 | drag | Pointer owner locked to RIGHT for the whole drag; cursor freezes if the right hand is lost > 120 ms | `orchestrator.py:350-364, 404-410` | R |
| F-23 | perf | No per-frame latency instrumentation; filter timestamps taken at processing time | `backend/main.py:740-752`, `right_hand.py:218` | R |
| F-24 | pointer | Dead `LEFT_PINCH_PENDING_DRAG`/`DRAGGING` states and stale docstring in right hand | `backend/core/gestures/right_hand.py:5-25, 68-69, 222-223, 299-301` | R |
| F-25 | tests | `tearDown` methods pinned the pre-P0 `LEFT_DRAG_LOST_TIMEOUT_S = 0.075` for every later test module, masking an obsolete 100 ms expectation in `test_phase6_drag` | `backend/test_drag_safety.py`, `backend/test_phase2_left_hand.py`, `backend/test_phase6_drag.py` | E → fixed (Phase 1) |
| F-26 | startup | `draw_debug_frame` was imported only when `config.DEBUG_GESTURES` was True, but the debug window is also enabled by `--debug` and Ctrl+Alt+D; with the shipped default the first debug frame raised `NameError` and the engine shut down (found by the user on the first physical start-up attempt) | `backend/main.py` | E (user) → fixed (unconditional guarded import, HUD disabled with a diagnostic if the import fails; `test_debug_hud_startup.py`) |
| F-27 | Wakanda | The lock gesture never ran: `config.WAKANDA_ENABLED = False` built the recognizer in `DISABLED`, and the control server's default `enabled["wakanda-forever"] = False` re-applied that at every start-up unless a persisted `settings.json` said otherwise (reported by the user as "not working") | `backend/config.py`, `backend/core/control_server.py`, `backend/main.py` | R (user) → fixed (enabled by default; config, persisted setting and Control Center toggle still disable it) |
| F-28 | Wakanda | `LockWorkStation` result was discarded: the callback, overlay capsule and SSE event reported "Workstation locked" even when the API returned 0 or raised | `backend/core/gestures/wakanda_gesture.py`, `backend/main.py`, `backend/core/overlay.py` | R → fixed (result checked, logged with GetLastError, propagated to the callback; distinct accepted/failed overlay and bridge events; `test_wakanda_lock_fix.py`) |
| F-29 | Wakanda/drag | The crossed-fist check ran while a drag was active; a pinching hand with three curled fingers passes the relaxed fist test, so one matching frame could release a held object | `backend/core/gestures/orchestrator.py` | R → fixed (recognizer skipped and reset while a drag is active or pending) |
| F-30 | drag | The actuator watchdog was evaluated at the top of `GestureOrchestrator.process()` against the heartbeat written during the previous frame, so its 250 ms budget was spent on the inter-frame gap: at the 5-7 FPS of the first full-mode launch every slow frame released a healthy GRAB_LOCKED drag and the still-pinched hand re-grabbed 100 ms later (repeated LEFTDOWN/LEFTUP pairs, `logs/backend_20261102_225058.err.log`) | `backend/core/gestures/orchestrator.py` | E (user log + `test_watchdog_frame_gap.py` reproduction) → fixed (watchdog evaluated after the controller processed the frame, on every path; timeout, actuator and controller unchanged) |
| F-31 | launcher | `backend\.venv\Scripts\python.exe` is a venv launcher stub whose child is the real interpreter; the launcher compared `bridge_info.json`'s pid (the child) with the `Start-Process` PID (the stub), never probed a bridge that had bound 2 s after start, reported "did not answer within 60 s" and force-stopped the tree | `scripts/start_airpoint.ps1`, `scripts/stop_airpoint.ps1` | E (probe: stub PID ≠ child PID; leftover `bridge_info.json` pid 67948 vs stub 48912) → fixed (`scripts/airpoint_launcher_lib.ps1`: process-tree resolution, foreign/stale classification, graceful exit of the tree; `launcher_selftest.ps1`) |

---

## 13. Historical claims checked against the current tree

| Claim (from the brief / earlier reports) | Current status |
|---|---|
| `test_debug_overlay_send.py` mocks NumPy in `sys.modules` | No longer true (fixed in P0.3); the same pattern now lives in `test_native_input_safety.py` (F-01) |
| `test_phase2_left_hand.py` tests 10/11/14 expect immediate release | Already aligned to the 80 ms dwell in the working tree; they pass |
| Isolated suites pass while full discovery fails | True, and now explained by F-01 (order-dependent `sys.modules` stubs) |
| Frontend hard-codes port 8765 | True |
| Backend allocates a dynamic port | Only with `AIRPOINT_PORT_FALLBACK=1`; by default it refuses to start |
| `bridge_info.json` is not consumed | True |
| The Tk overlay receives only selected callbacks | It receives every notification state that exists; drag, clicks and zoom have no notification at all |
| React SSE events update history but not the island | True; additionally the island preview is not mounted anywhere |
| Right hand is a competing drag starter | False (dead states only), consistent with Errata E-01 |
| Multi-monitor coordinate spaces are inconsistent | Not supported by the code (consistent VIRTUALDESK + origin handling); unverified physically |

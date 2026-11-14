# AIRPOINT — FEATURE PARITY MATRIX (STAGE B)

**Date:** 2026-11-02
**Scope:** every capability found in either workspace, with the decision for the unified product. Because both checkouts are at commit `4672829`, "Canonical" and "Legacy" describe the working trees: the canonical tree carries the uncommitted P0, Phase 1, debug-start-up and Wakanda work; the legacy tree carries only the items listed in the inventory §3.

**Column key**
- Canonical / Legacy: `yes` = implemented in that working tree; `yes+` = implemented with the canonical uncommitted improvements.
- Quality: which version is more complete.
- Tests: automated coverage in the canonical tree (file names abbreviated).
- Integration: whether the feature is connected end to end today.
- Physical: `user-reported` = the user observed it working on the desktop on 2026-11-02 (engine, tracking, pointer, drag, HUD); `pending` = not yet observed; `n/a` = not a desktop behaviour.
- Decision: PRESERVE (canonical as is), MERGE (combine), MIGRATE (bring from legacy), REDESIGN (rework during integration), RETIRE.
- Class: CANONICAL ONLY, LEGACY ONLY, IDENTICAL, DIVERGENT, NEEDS MERGE, INCOMPLETE, OBSOLETE.

## A. Core pointer functionality

| Feature | Canonical | Legacy | Quality | Dependencies | Tests | Integration | Physical | Decision | Class |
|---|---|---|---|---|---|---|---|---|---|
| Right-hand virtual pointer (index tip 8 → cursor) | yes | yes | equal | `right_hand.py`, `display.py`, `filter.py`, `orchestrator.py` | phase4_3, phase6_3, jump_protection, fast_movement | yes | user-reported | PRESERVE | IDENTICAL |
| Index-finger tracking and 5-tip visual filters | yes | yes | equal | `right_hand.py` | phase4_5 | yes (debug HUD) | user-reported | PRESERVE | IDENTICAL |
| Coordinate normalisation and trackpad zone mapping | yes | yes | equal | `display.map_to_desktop`, `set_sensitivity` | coordinate_mapping, phase4_2 | yes | user-reported | PRESERVE | IDENTICAL |
| Mirrored webcam handling (`cv2.flip` + handedness inversion) | yes | yes | equal | `main.py`, `tracker.py` | tracker_handedness | yes | user-reported | PRESERVE | IDENTICAL |
| Pinch click (instant / comfortable modes) | yes | yes | equal | `right_hand.py`, `actuator.left_click` | pinch_click, phase4_3 | yes | pending (clicks not formally recorded) | PRESERVE | IDENTICAL |
| Double-click (second pinch within 750 ms / 100 px; pinch-hold 350 ms) | yes | yes | equal | same | pinch_click | yes | pending | PRESERVE | IDENTICAL |
| Pointer smoothing (One Euro, slider 10–100) | yes | yes | equal | `filter.py`, `set_smoothing` | phase4_2_stability, phase6_3 | yes | user-reported (feel not measured) | PRESERVE, measure in Stage C/E of the roadmap Phase 2 | IDENTICAL |
| Cursor sensitivity (0.2–4.0 rebuilds the zone) | yes | yes | equal | `set_sensitivity` | phase4_4 | yes | user-reported | PRESERVE | IDENTICAL |
| Cursor freeze (pinch-locked / zoom-active / fist) | yes | yes | equal; fist freeze ineffective (F-09) | `right_hand.py` | phase4_5 | partial | pending | PRESERVE; F-09 decision pending | IDENTICAL |
| Pointer ownership (RIGHT priority, LEFT fallback, drag lock) | yes | yes | equal | `orchestrator.py` | phase1_drag_reliability, phase2_left_hand, left_hand_drag_reliability | yes | user-reported | PRESERVE | IDENTICAL |
| Cursor edge handling (trackpad clamp, desktop clamp, 16-bit absolute) | yes | yes | equal | `display.py`, `actuator.move` | coordinate_mapping | yes | pending | PRESERVE | IDENTICAL |
| Cursor jump limiter / trusted anchor / reacquisition | yes+ (F-04 getter fixed) | yes (getter broken) | canonical | `orchestrator.py` | jump_protection, fast_movement, phase1 | yes | pending | PRESERVE | DIVERGENT |
| Calibration presets (Precision / Balanced / Fast) | yes | yes | equal | frontend `cursor.tsx`, `/api/settings` | frontend lifecycle tests | yes | n/a | PRESERVE | IDENTICAL |
| Drag-time cursor movement (right hand steers during left hold) | yes+ | yes | canonical (tested with scripted native results) | `orchestrator.py` | phase1 `test_right_cursor_moves_while_left_drag_held`, phase2 test_17 | yes | user-reported (drag system operational) | PRESERVE | DIVERGENT |
| Zoom gesture (peace sign, Ctrl+= / Ctrl+-) | yes | yes | equal | `right_hand.py`, pynput | phase3 | yes | pending | PRESERVE | IDENTICAL |

## B. Two-hand drag-and-drop

| Feature | Canonical | Legacy | Quality | Dependencies | Tests | Integration | Physical | Decision | Class |
|---|---|---|---|---|---|---|---|---|---|
| Left-hand pinch recognition (thumb–index / palm width) | yes | yes | equal | `drag_controller.py` | native_input_safety, phase2 | yes | user-reported | PRESERVE | IDENTICAL |
| Grab pending (100 ms confirm dwell) | yes | yes | equal | same | drag_and_drop_pipeline | yes | user-reported | PRESERVE | IDENTICAL |
| Grab lock | yes | yes | equal | same | same | yes | user-reported | PRESERVE | IDENTICAL |
| Native LEFTDOWN only on CONFIRMED `SendInput` | yes+ (P0) | no (pre-P0: `mouse_event` false success) | canonical | `actuator.py` | native_input_safety (21) | yes | pending (BTN reading T2) | PRESERVE | CANONICAL ONLY |
| Release pending + 80 ms release dwell (no single-frame drop) | yes+ (P0) | no (immediate drop at 0.85) | canonical | `drag_controller.py` | native_input_safety, phase1, phase6_drag | yes | pending (T4/T5) | PRESERVE | CANONICAL ONLY |
| Native LEFTUP with retry; failed LEFTUP retains state | yes+ (P0) | no | canonical | `actuator.py` | native_input_safety, phase1 | yes | pending | PRESERVE | CANONICAL ONLY |
| Tracking-loss recovery (150 ms grace, controller + orchestrator) | yes+ (150 ms) | yes (75 ms) | canonical | `config.py`, `orchestrator.py` | phase1, drag_safety | yes | pending (T6) | PRESERVE | DIVERGENT |
| Hand reacquisition during a hold | yes | yes | equal | `orchestrator.py` | phase1 `dropout_within_grace…` | yes | pending | PRESERVE | IDENTICAL |
| Actuator watchdog (250 ms; rate-limited retry after failure) | yes+ (Phase 1) | yes (retry storm) | canonical | `actuator.py` | phase1 | yes | pending | PRESERVE | DIVERGENT |
| Pause during an active drag (main-thread bounded release) | yes+ (Phase 1) | yes (cross-thread `drag_end`, result ignored) | canonical | `main.py`, `actuator.force_release_drag` | phase1 | yes | pending (T7) | PRESERVE | DIVERGENT |
| Shutdown during an active drag (release first, bounded, atexit) | yes+ (Phase 1) | yes (release last, result ignored) | canonical | `main.py` | phase1 | yes | pending (T8) | PRESERVE | DIVERGENT |
| Failed native input handling surfaced in `/api/status` → `drag` | yes+ (Phase 1) | no | canonical | `control_server.py` | control_server | yes | n/a | PRESERVE | CANONICAL ONLY |
| Drag events to Dyne (started / completed / released / failed) | yes (Stage E: `DragEventTracker`, read-only observation of the controller) | no | canonical | `core/events.py`, `main.py` | test_dyne_events §2 | yes | pending | INTEGRATED | CANONICAL ONLY |

## C. Gesture applications and system controls

| Feature | Canonical | Legacy | Quality | Dependencies | Tests | Integration | Physical | Decision | Class |
|---|---|---|---|---|---|---|---|---|---|
| Wakanda Forever crossed-fist pose (geometry) | yes | yes | equal | `wakanda_gesture.check_wakanda_pose` | wakanda_gesture, wakanda_lock_fix | yes | pending (user to perform) | PRESERVE | IDENTICAL |
| Wakanda enabled in normal runtime | yes+ | no (disabled at config and control-server layers) | canonical | `config.py`, `control_server.py` | wakanda_lock_fix | yes | pending | PRESERVE | CANONICAL ONLY |
| Windows workstation lock with API result reporting | yes+ | no (result discarded) | canonical | `wakanda_gesture.lock_workstation` | wakanda_lock_fix (stubbed API) | yes | pending | PRESERVE | CANONICAL ONLY |
| Wakanda skipped during drags | yes+ | no | canonical | `orchestrator.py` | wakanda_lock_fix test 12 | yes | pending | PRESERVE | CANONICAL ONLY |
| Screenshot gesture (two open palms, 1–10 s hold) | yes | yes | equal | `screenshot.py`, `actuator.take_screenshot` (PIL) | phase3_screenshot_timer, phase4_1 | yes | pending | PRESERVE | IDENTICAL |
| Screenshot countdown and overlay capsule | yes | yes | equal | `overlay.py` | phase7_hud | yes | pending | PRESERVE | IDENTICAL |
| "Screenshot captured" event only on real success | yes (Stage E: `capture_result_cb` after the file is written; `screenshot.failed` otherwise) | no (F-12) | canonical | `screenshot.py`, `main.py` | test_dyne_events §8 | yes | pending | INTEGRATED | CANONICAL ONLY |
| WhatsApp W gesture and app launch (protocol URI, AUMID fallback) | yes | yes | equal | `w_gesture.py`, `app_launcher.py` | phase4_w_gesture | yes | pending | PRESERVE | IDENTICAL |
| Lip-touch mute / restore (pycaw) | yes | yes | equal | `lip_mute_gesture.py`, `audio_controller.py`, face tracker | phase5_lip_mute | yes | pending | PRESERVE | IDENTICAL |
| Ear-touch continuous volume | yes+ (events coalesced to ≤ 4/s + final, F-13 fixed; visualizer unchanged) | yes (event flood) | canonical | `ear_volume_gesture.py`, `core/events.py` | phase6_ear_volume, phase7_1, test_dyne_events §3 | yes | pending | PRESERVE | DIVERGENT |
| Two-hand shortcuts (both fists → Win+L, palm + fist flick → Win+Left/Right) | yes | yes | equal; no HUD, no events, no tests | `two_hand.py`, pynput keyboard | none | partial | pending | PRESERVE (document as untested); events in Stage E are optional | IDENTICAL |
| Right-hand fist lock / docstring drag states | yes | yes | both stale (F-09, F-24) | `right_hand.py` | — | partial | pending | REDESIGN later (roadmap Phase 2) | IDENTICAL |

## D. Computer vision

| Feature | Canonical | Legacy | Quality | Dependencies | Tests | Integration | Physical | Decision | Class |
|---|---|---|---|---|---|---|---|---|---|
| MediaPipe hand tracking (Tasks API, VIDEO, 2 hands) | yes | yes | equal; canonical venv runs mediapipe 1.2.0 | `tracker.py`, `models/hand_landmarker.task` | tracker_handedness, preflight | yes | user-reported | PRESERVE | IDENTICAL |
| Face tracking (lips, ears, 478 points) | yes | yes | equal | `face_tracker.py`, `models/face_landmarker.task` | phase5/phase6 via mocks, preflight | yes | pending | PRESERVE | IDENTICAL |
| Landmark extraction and `HandsResult`/`FaceResult` | yes | yes | equal | `tracker.py` | gestures_unit | yes | user-reported | PRESERVE | IDENTICAL |
| Handedness hysteresis (150 ms, score < 0.65) | yes | yes | equal | `tracker.py` | tracker_handedness | yes | pending | PRESERVE | IDENTICAL |
| Tracking confidence gating (0.40 / 0.20 during drag) | yes | yes | equal | `orchestrator.py` | jump_protection | yes | pending | PRESERVE | IDENTICAL |
| Tracking loss / reacquisition toasts and events (0.35 s / 0.15 s) | yes | yes | equal | `main.py` | none direct | yes | pending | PRESERVE | IDENTICAL |
| Camera management (DirectShow, buffer 1, async thread) | yes | yes | equal | `camera.py` | frame_freshness (detector only) | yes | user-reported | PRESERVE | IDENTICAL |
| Camera FPS / processing FPS telemetry | yes (5 s average log, HUD) | yes | equal; no per-frame metrics (F-23) | `main.py` | none | partial | user-reported | PRESERVE; instrument in roadmap Phase 2 | IDENTICAL |
| Frame freshness (3 identical buffers) | yes | yes | equal | `camera.py` | frame_freshness | yes | pending | PRESERVE | IDENTICAL |
| Power state machine (probe cadence, wake) | yes | yes | equal | `power_state_machine.py` | power_state_machine, power_runtime_integration | yes | pending | PRESERVE | IDENTICAL |
| Additional vision models | none | none | — | — | — | — | — | — | — |

## E. Dynamic Island and notification system

| Feature | Canonical | Legacy | Quality | Dependencies | Tests | Integration | Physical | Decision | Class |
|---|---|---|---|---|---|---|---|---|---|
| Python Tk overlay (capsule states, priorities, 0.8 s dedupe) | yes+ (`show_wakanda_failed`; Stage E: `handle_event` subscriber, `show_notice`, position, accent) | yes | canonical | `overlay.py` | phase7_hud, phase7_1, dynamic_island_power_notifications, test_dyne_events §7 | yes (dispatcher subscriber + direct HUD state) | user-reported HUD; overlay pending | PRESERVE | DIVERGENT |
| Overlay honours `island_enabled` / `notifications_enabled` for gesture toasts | yes (Stage E, F-15 fixed) | no | canonical | `overlay.py` | test_dyne_events §7 | yes | pending | INTEGRATED | CANONICAL ONLY |
| React notification island component | live island `dyne-live-island.tsx` mounted in `DesktopShell`, driven by real events (F-14 fixed); `dynamic-island.tsx` stays a preview | component only, unmounted | canonical | frontend | dyne-live-events.test, wakanda-forever.test | yes | n/a | INTEGRATED | CANONICAL ONLY |
| Dyne Studio (capsule carousel, Colour/Text/Material/Shape preview, Notifications and Behaviour & Timing host controls) | yes+ (Position category, Apply this look / Load live look, applied-look status pill) | yes | canonical | `dyne-studio/*` | dyne-studio-integration, dyne-studio-audit-verification, dynamic-island-tab, dyne-live-events.test | host controls yes; previews labelled; applied look persisted | n/a | PRESERVE | DIVERGENT |
| Notification categories (per-type enable) | no (one global notifications switch) | no | — | — | — | missing | n/a | open (roadmap 3.5) | INCOMPLETE |
| Notification settings (6 `island_*` keys + `island_position` + `island_appearance`) | yes+ | yes (6 keys) | canonical | `control_server.py`, `overlay.configure` | control_server, dynamic-island-tab, test_dyne_events §5 | yes | pending | PRESERVE | DIVERGENT |
| Notification preview distinguished from real events | previews keep "PREVIEW"/"DEMO"; the live island carries `data-live` + LIVE tag; Studio shows `PREVIEW · NOT APPLIED` / `THIS LOOK IS LIVE` | preview only | canonical | frontend | dyne-live-events.test | yes | n/a | INTEGRATED | CANONICAL ONLY |
| Event history | ring of 50 with ids and session; `/api/status` 10 newest; `/api/events/history`; frontend merges instead of replacing (F-11 fixed) | ring of 5, overwritten by poll | canonical | `core/events.py`, `control_server.py`, `engine.tsx` | test_dyne_events §1/§5/§6, dyne-live-events.test | yes | n/a | INTEGRATED | CANONICAL ONLY |
| Event priorities | schema `priority` (low/normal/high/critical) + Tk overlay priorities | Tk overlay only | canonical | `core/events.py`, `overlay.py` | test_dyne_events §1 | yes | n/a | INTEGRATED | DIVERGENT |
| Event deduplication | ids `${session}:${id}`, SSE replay filter, frontend merge; Tk 0.8 s text dedupe kept | Tk only | canonical | `core/events.py`, `engine.tsx` | test_dyne_events §6, dyne-live-events.test | yes | n/a | INTEGRATED | DIVERGENT |
| Animation settings | Tk: fixed `HUD_ANIMATION_SPEED`; React: reduced-motion preference | same | equal | `config.py`, frontend prefs | ui-polish tests | partial | n/a | PRESERVE | IDENTICAL |
| Notification position | `island_position` (top-center / top-left / top-right / bottom-center) honoured by the Tk overlay geometry and the live island | top centre fixed | canonical | `overlay.py`, `dyne-live-island.tsx` | test_dyne_events §7, dyne-live-events.test | yes | pending | INTEGRATED | CANONICAL ONLY |
| Sound settings | none | none | — | — | — | — | — | not planned (no audio asset or requirement in either tree) | — |
| Persistence of Dyne settings | 6 keys + position + applied appearance in `settings.json`, validated server-side | 6 keys | canonical | `control_server.py`, `core/events.py` | test_dyne_events §5 | yes | n/a | INTEGRATED | DIVERGENT |

## F. Frontend Control Center

| Feature | Canonical | Legacy | Quality | Dependencies | Tests | Integration | Physical | Decision | Class |
|---|---|---|---|---|---|---|---|---|---|
| Overview dashboard (live canvas, telemetry cards, gesture tiles, recent activity) | yes | yes | equal | `routes/index.tsx`, `live-tracking-canvas.tsx` | live-tracking, mute-tutorial, redesign-regression | yes | n/a | PRESERVE | IDENTICAL |
| Application status (bridge pill, sidebar card, start/stop) | yes | yes | equal | `shell.tsx`, `engine.tsx` | lifecycle-controls | yes | n/a | PRESERVE | IDENTICAL |
| Gesture controls (8 toggles, inspector, videos, Wakanda deck) | yes+ (Wakanda default on) | yes | canonical | `routes/gestures.tsx` | gesture-videos, wakanda-forever | yes | n/a | PRESERVE | DIVERGENT |
| Settings: cursor sensitivity/smoothing/presets, screenshot hold, power save | yes | yes | equal | `routes/cursor.tsx`, `routes/gestures.tsx` | lifecycle-controls, power-saver | yes | n/a | PRESERVE | IDENTICAL |
| Dyne Studio route | yes | yes | equal | `routes/island.tsx` | dynamic-island-tab | yes | n/a | PRESERVE | IDENTICAL |
| Event history UI | yes+ (5 most recent grouped by type, title + message + source, stream state) | yes (3, overwritten by poll) | canonical | `routes/index.tsx` | mute-tutorial, dyne-live-events.test | yes | n/a | INTEGRATED | DIVERGENT |
| Device / camera status (MJPEG stream, landmarks at 20 Hz) | yes | yes | equal | `live-tracking-canvas.tsx` | live-tracking | yes | n/a | PRESERVE | IDENTICAL |
| Debug information (diagnostics manifest on About) | yes+ (protocol copy fixed, event-stream state, bridge host from the resolved URL; F-17 fixed) | claims WebSocket | canonical | `routes/about.tsx` | redesign-regression, ui-polish-corrections | yes | n/a | PRESERVE | DIVERGENT |
| Appearance (theme, accent, density, reduced motion) | yes+ (anti-flash key fixed, F-16) | key mismatch | canonical | `routes/appearance.tsx`, `__root.tsx` | ui-polish-corrections | yes | n/a | PRESERVE | DIVERGENT |
| Backend connectivity (status poll 1.5 s, SSE with ids, token) | yes+ (`BRIDGE_BASE_URL` from `VITE_AIRPOINT_BRIDGE_URL`, loopback-only; F-10) | port fixed | canonical | `engine.tsx`, `air-point-model.ts` | lifecycle-controls, dyne-live-events.test | yes | n/a | INTEGRATED | DIVERGENT |
| Configuration management | settings via `/api/settings`; UI prefs in localStorage | same | equal | — | — | yes | n/a | PRESERVE | IDENTICAL |

## G. Runtime and infrastructure

| Feature | Canonical | Legacy | Quality | Dependencies | Tests | Integration | Physical | Decision | Class |
|---|---|---|---|---|---|---|---|---|---|
| PowerShell launcher `start_airpoint.ps1` (modes full / control-server / backend-only / frontend-only) | yes+ (Stage F: canonical root, venv python required, prerequisite + model checks, port owner report, duplicate protection, bridge health via `bridge_info.json` + `/api/status`, frontend HTTP readiness, `VITE_AIRPOINT_BRIDGE_URL`, PID record with node children, logs, partial-failure cleanup, `-DryRun`, `-DebugHud`, `-AllowPortFallback`) | yes (PID file + port pre-check only) | canonical | `backend/.venv`, npm | parse check, dry run, frontend-only start/stop cycle | yes | user to run `-Mode full` | INTEGRATED | DIVERGENT |
| Shutdown script `stop_airpoint.ps1` | yes+ (Stage F: graceful `exit` through the authenticated bridge, ownership verified by command line / descendant / recorded child, `-IncludeOrphans`, bridge files removed only when no engine remains, never kills unrelated python/node) | yes (kills any python/node on the ports) | canonical | `/api/control exit` | parse check, frontend-only cycle (no leftover processes) | yes | user to run after an engine session | INTEGRATED | DIVERGENT |
| `run_checks.ps1` four gates | yes+ (guard variables) | yes | canonical | — | parse-checked | yes | n/a | PRESERVE | DIVERGENT |
| Control server (HTTP + SSE, token, origin/host checks, settings persistence) | yes+ (`drag` block) | yes | canonical | `control_server.py` | control_server, phase4_1_control_server | yes | n/a | PRESERVE; extend events (Stage E) | DIVERGENT |
| HTTP routes (`/api/status`, `/api/events`, `/api/landmarks`, `/api/camera/*`, `/api/settings`, `/api/start|stop|toggle|control`, `/api/overlay/test`) | yes | yes | equal | same | control_server | yes | n/a | PRESERVE | IDENTICAL |
| SSE implementation (per-client queue 100, 10 s ping, `id:` lines, Last-Event-ID / `?after` replay, session hello) | yes+ | yes (no ids) | canonical | same | control_server, test_dyne_events §6 | yes | n/a | INTEGRATED | DIVERGENT |
| Local bridge security (loopback bind, host/origin allow-list, token; `exit` action token-authenticated) | yes+ | yes | canonical | same | control_server, test_dyne_events §6 | yes | n/a | PRESERVE | DIVERGENT |
| Runtime port selection (fixed 8765, optional `AIRPOINT_PORT_FALLBACK`, `bridge_info.json` read by the launcher) | yes+ | yes (undiscoverable) | canonical | `control_server.py`, launcher, `air-point-model.ts` | control_server, dyne-live-events.test (`resolveBridgeBaseUrl`) | yes for launcher runs | n/a | INTEGRATED | DIVERGENT |
| Configuration files (`config.py`, `settings.json`, localStorage prefs) | yes | yes | equal | — | — | yes | n/a | PRESERVE; one source per setting documented (Stage F) | IDENTICAL |
| Environment variables (`AIRPOINT_SETTINGS_PATH`, `AIRPOINT_ENABLE_TEST_GUARD`, `AIRPOINT_DISABLE_REAL_LOCK`, `AIRPOINT_ALLOWED_ORIGINS`, `AIRPOINT_PORT_FALLBACK`) | yes | yes | equal | — | test_guard, control_server, wakanda_lock_fix | yes | n/a | PRESERVE; document | IDENTICAL |
| Python dependencies (`requirements.txt`, unpinned) | yes | yes | equal | — | preflight | yes | n/a | PRESERVE; pin later (roadmap) | IDENTICAL |
| Node dependencies (`package.json`, lockfile) | yes | yes | equal | — | vitest/build | yes | n/a | PRESERVE | IDENTICAL |
| Logging and diagnostics (INFO console log, debug HUD with measured panel width, preflight, launcher logs) | yes+ | yes (HUD truncated at 44 chars) | canonical | — | debug_hud_startup, debug_overlay_send | yes | user-reported | PRESERVE | DIVERGENT |
| Physical test sandbox tooling (create / reset / verify) | yes (`tools/physical_sandbox/`, paths resolved from this repository) | yes (`tools/p0_2`, hard-coded legacy paths) | canonical | PowerShell | parse check | standalone | pending | MIGRATED (Stage C) | DIVERGENT |
| Hardware-free preflight | yes | no | canonical | `preflight_physical_test.py` | — | standalone | run | PRESERVE | CANONICAL ONLY |

## Summary (updated after Stages C–G)

- No capability existed only in the legacy tree except the physical sandbox tooling (migrated to `tools/physical_sandbox/`) and historical reports (copied to `docs/legacy_p0_2/`).
- Every capability in the canonical tree is preserved; none was retired.
- Rows marked INTEGRATED were completed by the migration on canonical files: the unified Dyne event system, the live React island, event history/dedup/priorities, Dyne position and applied-appearance persistence, drag and screenshot event truth, volume event coalescing, overlay switch gating, bridge discovery for launcher runs, the launcher and stop scripts, the About/appearance fixes.
- Still INCOMPLETE: per-event-type notification enable (one global switch today), events for clicks/zoom/two-hand shortcuts (no HUD feedback exists for them either), F-09/F-24 (pointer), per-frame performance instrumentation (roadmap Phase 2).
- Physical validation status is unchanged by this matrix: the user has observed the engine, tracking, pointer, drag and HUD running; the formal results (T1–T12), the Wakanda lock, the desktop capsule position/accent and the full-mode launcher are still to be observed by the user.

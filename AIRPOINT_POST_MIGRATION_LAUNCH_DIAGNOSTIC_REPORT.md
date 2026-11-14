# AIRPOINT — POST-MIGRATION FULL LAUNCH DIAGNOSTIC REPORT

**Date:** 2026-11-02
**Launch under investigation:** `.\scripts\start_airpoint.ps1 -Mode full -DebugHud` from `C:\Users\loges\Documents\air_point2_audit`, 22:50:58–22:52:01 (logs `logs/backend_20261102_225058.err.log`, stdout log empty as expected: the engine logs to stderr).
**Outcome:** both problems have a proven root cause, a minimal correction and regression tests. Nothing was committed or pushed. No native input, camera, drag or workstation lock was used by the investigation (the launcher self-test runs a real `ControlServer` without an engine; the drag tests run a scripted actuator).

---

## 1. Backend health-check failure: root cause

**The bridge was healthy; the launcher's probe was wrong.** The engine log shows the bridge bound 2 s after start:

```
22:51:02 [INFO] airmouse.main: === AI Air Mouse starting ===
22:51:04 [INFO] core.control_server: Air Point Control Bridge bound to http://127.0.0.1:8765
22:51:04 [INFO] airmouse.main: Running. Press Ctrl+Alt+Q to exit, ...
```

and the engine kept processing frames until the launcher force-stopped it at 22:52:01. The launcher never sent a single HTTP request: its health loop only probed `GET /api/status` after it had accepted `bridge_info.json`, and it accepted that file only when the `pid` inside equalled the PID returned by `Start-Process`. Those are two different processes:

- `backend\.venv\Scripts\python.exe` (255 KB) is the Python 3.14 **venv launcher stub**; `C:\Python314\python.exe` (106 KB) is the interpreter. The stub stays alive and runs the interpreter as a **child process**. Proven by a probe started exactly like the engine (`Start-Process ... -PassThru`): Start-Process returned PID 60532 (the stub, command line `.venv\Scripts\python.exe <script>`), while the script's own `os.getpid()` was **27024**, a child of 60532 (`os.getppid() == 60532`). The self-test in §10 reproduces this every time (stub 75232, engine 41444).
- The engine writes `bridge_info.json` with `os.getpid()`, i.e. the child. The file the failed launch left behind (the engine was killed with `TerminateProcess`, so its cleanup never ran) reads `"pid": 67948` and `"port": 8765`, while the launcher had recorded stub PID 48912. `67948 != 48912` → the launcher waited 60 s, reported "did not answer on its bridge", and cleaned up.

Against the brief's checklist: the server **did** bind; the launcher **never queried** any endpoint; no endpoint rejected anything; no port collision or fallback occurred (port 8765, no `AIRPOINT_PORT_FALLBACK`); the engine startup did not block the bridge (bound at +2 s, ~58 s before the timeout); **the PID returned by Start-Process was not the application process**. The health-check timeout was not changed.

## 2. Actual bound bridge port

`127.0.0.1:8765` (log line above and `bridge_info.json` of that run). No fallback was involved.

## 3. Correct health endpoint

`GET http://127.0.0.1:<port>/api/status` (no token required for reads; `Host` must be loopback, which PowerShell's `Invoke-WebRequest` satisfies). A healthy answer is HTTP 200 with the status JSON (`running`, `tracking`, `fps`, `drag{state,...}`, `last_event_id`, ...). The launcher used the right endpoint; it simply never reached the probe. The corrected library validates the payload (`running` must be present) so another service on the port is reported as "bridge-bad-response" instead of "healthy".

## 4. PID tracking discrepancy

| Process | Failed launch | Role |
|---|---|---|
| 48912 | returned by `Start-Process` | venv launcher stub (`.venv\Scripts\python.exe main.py`) |
| 67948 | `bridge_info.json` `pid` | the real engine (interpreter child of 48912) |
| 10048 | killed in cleanup | `conhost.exe` child of the stub |

The cleanup killed the descendants of 48912 (67948, 10048), which is why "different" PIDs appeared: they were the stub's children, i.e. the engine. The stop script had the same blind spot: its graceful-exit path compared `bridge_info.pid` with the recorded PID and would have fallen back to `Stop-Process` on the stub, leaving the engine child alive.

## 5. Watchdog heartbeat sequence (answers to the ten questions)

1. **What refreshes the watchdog?** `MouseActuator._last_drag_time`, written by `drag_start()` (on CONFIRMED LEFTDOWN) and by `keep_drag_alive(now)`; `drag_end()` resets it to 0; `check_drag_watchdog(now, 0.25)` compares `now - _last_drag_time`.
2. **Which path calls the refresh?** `LeftDragController.process_frame()` at its line 288: `keep_drag_alive(now)` whenever the state is `GRAB_LOCKED` or `RELEASE_PENDING` and the landmarks are valid; `_handle_tracking_absence()` during the 150 ms grace; `GestureOrchestrator` line 287 during its own dropout grace while dragging.
3. **Is it called on every valid active-drag frame?** Yes: the orchestrator calls `self._left.process(hands.left, now)` on every frame in which the left hand is present and drag is enabled, regardless of pointer ownership, and the controller refreshes before its state machine runs.
4. **Does the left hand maintain the drag while the right hand moves the cursor?** Yes. The heartbeat lives in the controller path; `move()` does not touch it. `test_watchdog_frame_gap.test_slow_frames_never_release_a_healthy_drag` steers with the right hand during the slow frames and the grab holds.
5. **Does a pointer-owner change stop heartbeat updates?** No. Ownership (`_pointer_owner`, `_drag_pointer_owner`) only selects which hand's position is sent to `move()`.
6. **Tracking loss versus movement?** Loss: the orchestrator withholds `process(None)` for ≤150 ms (keep-alive), then the controller's `release_grab("TRACKING_LOSS")` sends exactly one LEFTUP (`test_tracking_loss_releases_once_through_grace_not_the_watchdog`). Movement never interacts with the watchdog.
7. **Why did it trigger after ~250 ms with the state GRAB_LOCKED?** Because of *where* it was evaluated: `GestureOrchestrator.process()` called `check_drag_watchdog(now)` **at the top of the frame**, before `self._left.process(...)`. `now` is the new frame's timestamp and `_last_drag_time` is the previous frame's, so the comparison equals the inter-frame gap. The log's "held for 0.257–0.378 s" values are single frame periods. The engine ran at 5–7 FPS (log: `FPS: 5.4 … 7.4`; hand inference 15–41 ms, face 3–5 ms, camera 2–8 ms; the remaining ~100 ms per frame is not instrumented, see §9) so gaps above 250 ms were routine. Each firing injected a LEFTUP, `release_drag("WATCHDOG_TIMEOUT")` reset the controller to READY, the still-pinched hand entered GRAB_PENDING, and 100 ms later a new LEFTDOWN followed: the repeated cycle in the log (≈25 LEFTDOWN/LEFTUP pairs in 40 s, each a real native event on the desktop).
8. **Do retries race the controller's release path?** Before the fix, no double LEFTUP occurred (the watchdog's `drag_end` cleared `is_dragging`, so the controller's subsequent `release_grab` was a no-op), but the watchdog and the controller released on alternate frames. After the fix the watchdog runs only after the controller, so on a frame where the controller just released or just refreshed it is a no-op; the Phase 1 INPUT_ERROR retry (every 250 ms) is unchanged (`test_failed_leftup_retry_remains_rate_limited`).
9. **Why was the pointer owner LEFT in the jump log?** `right_wants_pointer` requires a tracked right hand; only the left hand was in view, so `left_wants_pointer` (hand present, pointing, not a fist unless pinching) made LEFT the owner (orchestrator lines 342–381). The 1168 px jump at `dt_eff=40 ms` is the first frame after the left hand appeared far from the trusted anchor (or re-labelled handedness); the limiter bounded the step to 960 px and logged it once.
10. **Is that expected?** Yes for a one-handed session: LEFT is the documented fallback owner, and during the pinch the left index steers the cursor. It is unrelated to the watchdog releases (which happen for any owner), and the log does not prove a user-intended grab or a successful Windows drag: it only proves confirmed `SendInput` records.

## 6. Root cause of the repeated watchdog releases

Evaluation order, not heartbeat generation: the watchdog check preceded the controller's refresh within the same frame, so the 250 ms budget was consumed by the camera/processing gap instead of by "the controller stopped refreshing". The reproduction `backend/test_watchdog_frame_gap.py` fails on the pre-fix code exactly like the log (first slow frame → GRAB_PENDING again, LEFTUP injected) and passes after the correction.

The low frame rate is a second, independent observation: the measured stages sum to ≈50 ms per frame while the loop ran at 140–200 ms; the un-instrumented remainder is the debug window (`draw_debug_frame`, `cv2.imshow`, `cv2.waitKey(1)`), the Tk overlay update and the per-frame telemetry, or a webcam delivering fewer than 30 frames per second in low light. This is roadmap Phase 2 instrumentation work; it does not change the diagnosis, because the watchdog must tolerate any frame period as long as the controller refreshes.

## 7. Pointer-owner explanation

See §5 items 9–10. Ownership policy (unchanged): RIGHT has priority; LEFT is used only when no usable right pointer exists; during a drag the owner is frozen for the whole grab (`_drag_pointer_owner`), with RIGHT preferred when the right hand is usable. The jump limiter (`max_step` 380–960 px by `dt_eff`) is the reason the first left-hand frame was bounded rather than teleporting the cursor.

## 8. Exact affected files

| File | Change |
|---|---|
| `backend/core/gestures/orchestrator.py` | watchdog block moved out of the top of `process()` into `_run_drag_watchdog(now)`, called after the hand processing (normal path and the ear-touch early return) and on the four other early-return paths (screenshot, Wakanda, W gesture, lip) so the INPUT_ERROR retry keeps running there; nothing else changed |
| `backend/test_watchdog_frame_gap.py` (new) | 5 regression tests (slow frames, heartbeat equals frame time, watchdog still fires on desynchronisation, tracking loss releases once, failed-LEFTUP retry rate limit) |
| `scripts/airpoint_launcher_lib.ps1` (new) | shared functions: process tree resolution (`Resolve-EngineProcess`), two-step health (`Wait-BridgeHealthy`), `/api/status` validation, graceful exit of a tree, ownership-checked stops |
| `scripts/start_airpoint.ps1` | uses the library; records engine child + stub + descendants; failure categories; cleanup tries the graceful exit first |
| `scripts/stop_airpoint.ps1` | uses the library; graceful exit accepted for any PID of the recorded tree; forced stop deepest-first; version 2 and 3 PID records |
| `scripts/launcher_selftest.ps1` (new) + `backend/launcher_bridge_probe.py` (new) | backend-branch test without a camera |
| `CLAUDE.md`, `AIRPOINT_SYSTEM_ARCHITECTURE.md` (§8.1, §12 F-30/F-31) | documentation |

**Not changed:** `backend/core/actuator.py`, `backend/core/gestures/drag_controller.py`, `backend/config.py`, pinch thresholds, release dwell, the 250 ms watchdog timeout, LEFTDOWN/LEFTUP semantics, the pointer-ownership policy.

## 9. Minimal correction (implemented)

**Issue B.** `GestureOrchestrator._run_drag_watchdog(now)` evaluates `check_drag_watchdog(now, 0.25)` after the left-hand controller processed the frame. A healthy active frame therefore ends with `_last_drag_time == now` and can never fire the watchdog, however long the gap before it was; the watchdog still fires when the button is held and nothing refreshed it for 250 ms across frames (controller desynchronised or disabled, or a LEFTUP Windows did not confirm). Timeout, actuator and controller are untouched.

**Issue A.** The launcher resolves the engine from the process tree below the PID it started: `bridge_info.json` is accepted when its `pid` is the stub or one of its descendants (`owned`), ignored when older than the launch (`stale`), and reported as a conflict when written by an unrelated process (`foreign`); only then is `GET /api/status` probed and validated. The PID record stores the engine child, the stub and the descendants; the stop script sends the graceful exit to any PID of that tree and waits for the whole tree. Timeouts are unchanged (60 s backend, 90 s frontend).

Proposed but **not** implemented (speculative, out of scope): changing the watchdog timeout, adding a second heartbeat from `main.py`, or instrumenting the frame loop.

## 10. Regression results

| Suite / check | Result |
|---|---|
| `test_watchdog_frame_gap.py` before the fix | 2 failures (slow frame released the drag; heartbeat 0.0 after release) — reproduces the log |
| `test_watchdog_frame_gap.py` after the fix | 5/5 |
| Drag safety, Phase 1 orchestrator, native input safety, pipeline, phase 2/6 left hand, jump protection, fast movement, Wakanda, Dyne events, control server | 202/202 |
| Full guarded backend discovery | **476/476** (471 before + 5 new) |
| Launcher parse (`Parser::ParseFile`) | lib, start, stop, self-test, run_checks: no errors |
| `scripts/launcher_selftest.ps1` (real `ControlServer`, no camera) | PASS 9/9: bridge healthy; engine PID == `bridge_info` pid (41444) ≠ stub (75232); bound port; `/api/status` payload with `drag.state`; foreign tree rejected; graceful exit of the whole tree; no leftover process; discovery files removed |
| `start_airpoint.ps1 -Mode full -DryRun` | passes every check, starts nothing |
| `-Mode frontend-only` start + `stop_airpoint.ps1` (refactored scripts) | ready in seconds; all recorded PIDs stopped; port freed; the stale `bridge_info.json`/`.bridge_token` of the failed launch removed |
| `git diff --check` | clean |

The `-Mode full` launch itself (camera, native input) was **not** run by the agent; it is the user's next physical step.

## 11. P0/P1 safety invariants

- Only `LeftDragController` starts or ends a native drag: unchanged; the orchestrator still only *calls* the controller and the actuator watchdog, in a different order.
- One LEFTDOWN per grab, one LEFTUP per release: restored for slow frames (the defect produced one extra pair per slow frame); the reproduction asserts `up_attempts == 0` across four 300 ms frames and exactly one LEFTUP on tracking loss.
- `CONFIRMED` is never proof of an application-level drag; UNCONFIRMED/FAILED never success; no `mouse_event` fallback: unchanged (actuator untouched).
- Failed LEFTUP keeps `is_dragging=True` and the watchdog retries every 250 ms: verified at the new call site (`test_failed_leftup_retry_remains_rate_limited`) and by the Phase 1 suite.
- Pause/shutdown release on the engine thread; the stop script now reaches the real engine process, so the graceful exit (drag release first) actually runs instead of a `TerminateProcess` on the stub.
- 80 ms release dwell, 150 ms grace, 250 ms watchdog, Wakanda safeguards, `settings_queue`, `_dispatch_to_main`: unchanged.

**Next physical step (user):** `.\scripts\start_airpoint.ps1 -Mode full -DebugHud`; expect "Engine PID <child> (stub <pid>); bridge healthy at http://127.0.0.1:8765" within a few seconds, then hold a left pinch for several seconds: the HUD `DRAG STATE` must stay `GRAB_LOCKED` with no watchdog warning in `logs\backend_*.err.log`, and `.\scripts\stop_airpoint.ps1` must log "Engine exited gracefully".

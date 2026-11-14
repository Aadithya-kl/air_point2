# CLAUDE.md — AirPoint engineering rules

AirPoint is a webcam, hand-gesture Windows interaction system: a Python computer-vision engine (`backend/`) that injects native input, a Tk desktop overlay ("Dynamic Island") owned by that engine, and a React Control Center (`frontend/`) talking to the engine over loopback HTTP + SSE. One Dyne event system (`backend/core/events.py`) feeds the overlay, the bridge and the live React island. Read `AIRPOINT_SYSTEM_ARCHITECTURE.md` before changing anything; `AIRPOINT_ENGINEERING_ROADMAP.md` holds the phase plan and the finding register (F-xx); `AIRPOINT_UNIFIED_MIGRATION_REPORT.md` records how the legacy checkout was folded into this one.

## Repository rules

- Canonical checkout: `C:\Users\loges\Documents\air_point2_audit`, branch `fix/p0-native-input-safety`, base commit `4672829`. The checkout at `C:\Users\loges\Documents\antigravity\AirPoint` (same HEAD) is the legacy workspace: read-only historical reference, never used for code, tests or its virtualenv (its `.pth` file leaks that tree onto `sys.path`). Everything useful from it was migrated (`tools/physical_sandbox/`, `docs/legacy_p0_2/`); nothing in this repository may reference its path.
- Do not switch branches, merge, cherry-pick, commit or push without explicit authorisation from the user. Report `git status` and the diff instead.
- The uncommitted P0 native-input-safety work (6 modified + 6 untracked files, listed in the architecture document §1.2) must be preserved. A verified backup exists at `C:\Users\loges\Documents\air_point2_audit_backups\p0_worktree_backup_20261102_190141\`.
- Generated file: `frontend/src/routeTree.gen.ts` is rewritten by Vite/Vitest with LF endings; restore it with `git checkout -- frontend/src/routeTree.gen.ts` after running frontend tooling unless routes changed.

## Environment

- Backend: `backend\.venv` (Python 3.14.3; mediapipe 1.2.0, opencv 5.0, pynput, screeninfo, pycaw installed from `requirements.txt`). Create with `C:\Python314\python.exe -m venv backend\.venv && backend\.venv\Scripts\python -m pip install -r backend\requirements.txt` if missing.
- Frontend: `cd frontend && npm ci` (Node 24, npm 11).
- Runtime files the engine writes (gitignored): `backend/settings.json`, `backend/bridge_info.json`, `backend/.bridge_token`, `backend/screenshots/`. The launcher writes `.airpoint/airpoint_pids.json` and `logs/*.log` (gitignored).
- Bridge discovery: the launcher passes `VITE_AIRPOINT_BRIDGE_URL` (loopback http only) to the dev server; without it the Control Center uses `http://127.0.0.1:8765`.

## Commands

Backend tests (always with the guard; it blocks real SendInput, SetCursorPos, keyboard, LockWorkStation, app launch and camera opens):

```
cd backend
set AIRPOINT_SETTINGS_PATH=:memory:
set AIRPOINT_ENABLE_TEST_GUARD=1
set AIRPOINT_DISABLE_REAL_LOCK=1
.venv\Scripts\python.exe -m unittest discover -s . -p "test_*.py"
```

Frontend gates: `npx tsc --noEmit`, `npx vitest run`, `npm run build` (in `frontend`).

Running the product (physical testing is done by the user, not by the agent): `.\scripts\start_airpoint.ps1 -Mode full` (add `-DebugHud` for the OpenCV HUD, `-DryRun` to check without starting) and `.\scripts\stop_airpoint.ps1` (graceful engine exit through the bridge, own processes only); hotkeys Ctrl+Alt+P pause, Ctrl+Alt+Q quit, Ctrl+Alt+S status, Ctrl+Alt+D debug window. Before a physical session run `backend\.venv\Scripts\python.exe backend\preflight_physical_test.py` (hardware-free: never opens the camera or injects input). The agent may run the preflight, the launcher's `-DryRun`, `-Mode frontend-only` (node only) and `.\scripts\launcher_selftest.ps1` (the backend branch against `backend\launcher_bridge_probe.py`, a real ControlServer without camera or input); it never starts `main.py` or `backend-only`/`full` mode, because those open the camera and inject input. Physical sandbox folders for drag tests come from `tools/physical_sandbox/`.
- Process identity: `backend\.venv\Scripts\python.exe` is a venv launcher stub; the engine is its child process (the PID in `bridge_info.json`). Launcher code must reason about the process tree (`scripts/airpoint_launcher_lib.ps1`), never compare a single PID.

## Invariants that must not be broken

- Only `LeftDragController` (`backend/core/gestures/drag_controller.py`) starts or ends a native drag. Exactly one LEFTDOWN per grab, one LEFTUP per release.
- `SendInputResult.CONFIRMED` means Windows accepted the input record. It is never evidence that an application processed a drag. Never treat UNCONFIRMED or FAILED as success; never reintroduce the `mouse_event` fallback.
- A failed LEFTUP keeps `is_dragging=True` so the watchdog can retry (every 250 ms). Faults are logged and surfaced, not hidden; `GET /api/status` → `drag` publishes controller state, logical flag, native button state and last error separately.
- Pause, shutdown and `atexit` release a held drag on the engine main thread through `LeftDragController.release_grab` followed by `MouseActuator.force_release_drag` (bounded retries, one CRITICAL line, never reported as success when unconfirmed). Never inject native input from the hotkey or HTTP threads.
- Release always passes through `RELEASE_PENDING` with the 80 ms dwell; tracking loss grace is 150 ms (`LEFT_DRAG_LOST_TIMEOUT_S`); the actuator watchdog is 250 ms.
- The watchdog is evaluated by `GestureOrchestrator._run_drag_watchdog()` **after** the left-hand controller processed the frame (and on every early-return path), never before it: the controller refreshes the heartbeat on each active frame, so a slow frame must never release a healthy drag (2026-11-02 launch diagnostic; `test_watchdog_frame_gap.py`). Do not move the check back to the top of `process()`.
- Settings from the HTTP thread are applied only on the engine main thread via `settings_queue`; Tk overlay calls from other threads go through `_dispatch_to_main`.
- Wakanda Forever (crossed fists, 2.0 s hold, 2.0 s cooldown, release to rearm) sends exactly one `LockWorkStation` request per confirmed hold and reports the API result as accepted or failed, never as "locked". It is enabled by default; it is never evaluated while a left drag is active or pending. Tests inject `lock_fn` or run with `AIRPOINT_DISABLE_REAL_LOCK=1`; `lock_workstation()` also refuses a real call when the process is a test runner. Never remove those safeguards.
- Dyne events are published only after the real outcome is known (`screenshot.captured` after the file is written, `lock.accepted` only on a non-zero API result, `drag.*` from observed controller transitions, `drag.failed` for any unconfirmed release). Never fabricate a success event, never add a second notification path beside `RuntimeState.publish_event`, and keep `DragEventTracker` read-only (it must never call the controller or the actuator). Previews in the Control Center must stay labelled as previews; the live island renders real events only.
- The stop script asks the engine to exit through `/api/control {"action": "exit"}` so the shutdown path (drag release first) runs on the engine thread; it force-stops only after the graceful wait and only processes verified as its own.

## Testing rules

- Never assign into `sys.modules` in a test. Use subclass mocks of `MouseActuator` (see `SafeTestActuator`, `MockInputActuator`) and `unittest.mock.patch` scoped to the test.
- Drive state machines with explicit timestamps (`now=`) rather than `time.sleep`.
- Never weaken production code to make an obsolete test pass; never delete a failing test to go green. Align the test to the current contract and say why in the test docstring.
- Run full discovery after any change, not only the touched module; order-dependent failures are defects.
- Mocked tests are never reported as physical validation. Physical procedures live in `AIRPOINT_PHASE_<n>_PHYSICAL_TEST_PLAN.md` and are executed by the user.

## Stop and explain before

Replacing the architecture, changing gesture semantics or thresholds without measurements, adding major dependencies, changing Windows privilege requirements, deleting features, irreversible operations, or anything that could weaken the native-input safety contract.

## Documentation to maintain

`CLAUDE.md`, `AIRPOINT_SYSTEM_ARCHITECTURE.md`, `AIRPOINT_ENGINEERING_ROADMAP.md`, `AIRPOINT_FEATURE_PARITY_MATRIX.md`, and one report per phase (`AIRPOINT_PHASE_<n>_IMPLEMENTATION_REPORT.md`; the unified migration is `AIRPOINT_UNIFIED_MIGRATION_REPORT.md` with its inventory `AIRPOINT_UNIFIED_MIGRATION_INVENTORY.md`). Update the architecture document whenever behaviour or structure changes; add new event types to `EVENT_CATALOGUE` and to architecture §7.2.

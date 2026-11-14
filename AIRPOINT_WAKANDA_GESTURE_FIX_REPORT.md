# AIRPOINT — WAKANDA FOREVER GESTURE: WINDOWS LOCK SCREEN FIX REPORT

**Date:** 2026-11-02
**Repository / branch:** `C:\Users\loges\Documents\air_point2_audit`, `fix/p0-native-input-safety` (HEAD `4672829`; nothing committed or pushed)
**Findings:** F-27 (feature never ran), F-28 (lock result never checked), F-29 (recognizer could run during a drag) in the architecture register.
**Physical status:** not validated. No Wakanda gesture has been performed on the real desktop; nothing in this report claims that Windows locked.

---

## 1. Workflow trace and where it stopped

```
Camera frame
  → HandTracker (both hands with scores)                                     working (user-confirmed physically)
  → GestureOrchestrator.process(): screenshot → Wakanda → W → lip → ear …    Wakanda evaluated every frame unless the screenshot gesture is active
  → WakandaGestureRecognizer.process(hands, face, now)                        STOPPED HERE: state DISABLED, returned False on every frame
  → check_wakanda_pose(): fists, crossing, diagonal, torso, face checks       never reached
  → 2.0 s hold (0.15 s grace) → TRIGGERED                                     never reached
  → lock_fn() = lock_workstation() → user32.LockWorkStation()                 never reached; and its result was discarded when reached
  → activation callback → Tk overlay capsule + SSE event                      reported "Workstation locked" regardless of the API result
  → COOLDOWN 2.0 s, then release required before rearm                        correct, unchanged
```

### 1.1 Exact root cause (F-27): disabled at two layers

1. `backend/config.py` had `WAKANDA_ENABLED = False` ("Disabled by default for security"). `WakandaGestureRecognizer.__init__` used it as the default for `enabled`, so the orchestrator's instance started in `WakandaState.DISABLED`. The log line `WakandaGestureRecognizer initialized (enabled=False, hold=2.0s, cooldown=2.0s)` is exactly this.
2. `backend/core/control_server.py` initialised `enabled_gestures["wakanda-forever"] = False` (every other gesture True). At start-up `main.py` applies the control-server settings snapshot to the recognisers (`processor._wakanda.enabled = en.get("wakanda-forever", False)`), so even a config change would have been overridden unless a persisted `backend/settings.json` contained `"wakanda-forever": true`. No such file existed on this machine.

The only way the feature could ever run was to open the React Control Center, toggle "Lock Screen" on (which persists `settings.json`), and keep the frontend running. There is no environment variable that enables it; `AIRPOINT_DISABLE_REAL_LOCK` only mocks the lock call.

### 1.2 Second defect (F-28): false success

`lock_workstation()` returned the API result, but the recognizer assigned it to a local variable and never used it. The callback had no argument, so `main.py` always showed the "WAKANDA FOREVER" capsule and sent the SSE event "Workstation locked via Wakanda Forever", even if `LockWorkStation` returned 0 or raised. `LockWorkStation` also returns when the request is *queued*, not when the desktop is locked, so even a non-zero return only means "request accepted".

### 1.3 Third defect (F-29): interference with a held drag

The crossed-fist check ran on every frame including during a left-hand drag. `is_fist_relaxed()` accepts any hand with three of four fingers curled, which a pinching hand satisfies; a single frame that also passed the crossing and torso checks would have released the held object through `release_drag("WORKSTATION_LOCK")`.

## 2. Gesture definition (preserved, unchanged)

`check_wakanda_pose(hands, face)` in `backend/core/gestures/wakanda_gesture.py`, evaluated on the mirrored frame:

| Requirement | Rule |
|---|---|
| Hands | both present, each MediaPipe score ≥ 0.55 (`WAKANDA_HAND_CONFIDENCE_MIN`) |
| Fingers | each hand a relaxed fist: `is_fist()` or at least 3 of index/middle/ring/pinky with tip below PIP (thumb free) |
| Crossing | user's left wrist and middle MCP to the right of the right hand's (`left.x > right.x` for landmarks 0 and 9) |
| Orientation | wrist→middle-MCP vector: right hand dx ≤ −0.01, left hand dx ≥ +0.01 (an "X"), both dy ≤ 0.08 (pointing up) |
| Torso | mean wrist y in [0.15, 0.92]; wrist y difference ≤ 0.28; wrist x spread ≤ 0.70; with a face, wrists not above lip height − 0.04 |
| Hold | 2.0 s continuous (`WAKANDA_HOLD_DURATION_S`), 0.15 s grace for tracking blips (`WAKANDA_GRACE_PERIOD_S`) |
| After firing | 2.0 s cooldown (`WAKANDA_COOLDOWN_S`), then the arms must uncross before the recognizer rearms |
| Cadence | evaluated every processed frame by the orchestrator, except while the screenshot gesture is active and (new) while a left drag is active or pending |

No threshold was altered.

## 3. Files modified

| File | Change |
|---|---|
| `backend/config.py` | `WAKANDA_ENABLED = True` with the disable paths documented |
| `backend/core/control_server.py` | every gesture, including `wakanda-forever`, defaults to enabled; a persisted `settings.json` or a Control Center toggle still disables it |
| `backend/core/gestures/wakanda_gesture.py` | `lock_workstation()` checks the return value, logs ACCEPTED / REJECTED (with `GetLastError`) / unavailable / raised, keeps the `AIRPOINT_DISABLE_REAL_LOCK` mock, and refuses a real call under a test runner (`_running_under_test_runner()`); `enabled` resolves from the live `config` module at construction; the recognizer records `last_lock_accepted`, `last_reject_reason`, exposes `hud_text`, logs the documented states, and calls the activation callback with the lock result (`cb(accepted)`) |
| `backend/core/gestures/orchestrator.py` | `is_active_drag` computed before the Wakanda step; recognizer skipped and reset while a drag is active or pending (lip-mute protection reused; the duplicated computation lower down removed) |
| `backend/main.py` | `on_wakanda_act(accepted)`: accepted → existing capsule + event "Workstation lock requested via Wakanda Forever"; failed → error toast + event "Wakanda Forever: Windows rejected the lock request"; settings default for the toggle is True |
| `backend/core/overlay.py` | `show_wakanda_failed()` (standard error toast "Lock request failed"); the success capsule is unchanged |
| `backend/core/debug_overlay.py` | one HUD line `WAKANDA   : <state>`; cyan like the other gesture lines, red when it reads `LOCK REQUEST FAILED` |
| `frontend/src/lib/air-point-model.ts` | default for `wakanda-forever` is `true` (the UI syncs from the engine anyway) and the inspector copy no longer says "disabled by default" |
| `backend/test_wakanda_gesture.py`, `backend/test_control_server.py` | the two tests that encoded "disabled by default" now encode "enabled by default, disable explicitly", with docstrings saying why |
| `backend/test_wakanda_lock_fix.py` | new, 21 tests (see §6) |
| `AIRPOINT_SYSTEM_ARCHITECTURE.md`, `AIRPOINT_ENGINEERING_ROADMAP.md`, `CLAUDE.md` | register entries F-27..F-29, component/producer rows, invariant |

Not modified: `backend/core/actuator.py`, `backend/core/gestures/drag_controller.py`, left-hand thresholds, release dwell, watchdog timing, pointer filtering, cursor ownership. The P0 and Phase 1 working tree is intact.

## 4. Windows lock API implementation

`lock_workstation()` (`backend/core/gestures/wakanda_gesture.py`):

1. `AIRPOINT_DISABLE_REAL_LOCK` set → log `[MOCK] ... request accepted` and return True (no native call).
2. Process started by a test runner (`__main__` is `unittest`/`pytest`, or a `test_*.py` script) → log an ERROR and return False without calling user32. Product entry points (`main.py`, `run_airpoint.bat`, the PowerShell launcher, the `validate_*` harnesses) never match.
3. `ctypes.windll.user32.LockWorkStation` missing → ERROR "unavailable", return False.
4. Call it: non-zero → INFO `LockWorkStation request ACCEPTED (return=…)`, return True; zero → ERROR `REJECTED (return=0, GetLastError=…)`, return False; exception (including the test guard's `BlockedOSActionError`) → ERROR, return False.

The recognizer stores the boolean as `last_lock_accepted`, sets the HUD to `LOCK REQUEST ACCEPTED` (suffixed `(MOCK)` when the flag is set) or `LOCK REQUEST FAILED`, logs the same words, and passes the boolean to the activation callback. Success is never inferred from the absence of an exception, and a non-zero return is described as an accepted request, not as a locked desktop.

## 5. Safety protections

| Requirement | Mechanism |
|---|---|
| Never lock during automated tests | tests inject `lock_fn`; `AIRPOINT_DISABLE_REAL_LOCK=1` mocks the call (documented command, `run_checks.ps1`, `test_wakanda_gesture.py` sets it at import); the test guard replaces `user32.LockWorkStation` with a raising stub; `lock_workstation()` refuses a real call when the process is a test runner even with none of the above |
| Never lock at start-up | nothing calls the lock at start-up; a lock needs a 2.0 s continuous pose after the engine is running |
| No single-frame trigger | 2.0 s hold; a pose that disappears for more than 0.15 s cancels the hold |
| No repeat while held | one request per confirmed hold; COOLDOWN for 2.0 s; rearm requires the arms to uncross |
| No interference with the left-hand drag | recognizer not evaluated while a drag is active or pending; a stale hold is reset |
| No interference with right-hand pointing | unchanged: pointer suppression applies only while the pose is actually being held |
| No partial/ambiguous pose | unchanged geometry; every rejection reason is now visible on the HUD (`SEARCHING (LEFT_HAND_NOT_FIST)` and so on) |

## 6. Regression tests

`backend/test_wakanda_lock_fix.py` (21 tests, every lock mocked or stubbed):

1. enabled in normal runtime (`config.WAKANDA_ENABLED` True, recognizer IDLE, HUD `SEARCHING`)
2. disabled where configured: `config.WAKANDA_ENABLED = False` at construction, `enabled=False`, and the runtime toggle round trip
3. correct pose recognised
4. incorrect and partial poses rejected (uncrossed, one hand, low confidence, open left hand) with the reason on the HUD
5. / 6. hold respected; 1.9 s then release never fires; a single frame never fires
7. one sustained 10 s gesture → exactly one lock request, callback called once with True, COOLDOWN then `COOLDOWN (release arms to rearm)`
8. / 9. cooldown blocks a second request; result shown for 1 s then the countdown; release rearms; a second deliberate hold fires exactly once more
10. failed lock request reported: HUD `LOCK REQUEST FAILED`, `last_lock_accepted` False, callback called with False, ERROR logged, cooldown still applies; a raising lock function is also reported as failure
    `lock_workstation()` with a stubbed API: return 0 → False with `GetLastError` logged; return 1 → True; API missing → False
11. tests cannot lock: the mock flag never touches user32; the test guard stub is reported as failure; the test-runner detector is True inside the suite and refuses the real call before user32; `main.py` as `__main__` is not mistaken for a runner; mock acceptance is labelled `(MOCK)`
12. drag non-interference at orchestrator level: with a recognizer that claims a valid pose on every frame, it is never evaluated while the grab is pending or locked, a stale hold is reset, no LEFTUP is sent, and it is evaluated again after the deliberate release
+ the debug HUD renders the `WAKANDA` line without error

Existing suites updated: `test_wakanda_gesture.py` (enabled-by-default semantics; the hold/cancel/cooldown/pointer-suppression tests unchanged) and `test_control_server.py` (two default assertions).

### Results (canonical venv, 2026-11-02)

| Run | Result |
|---|---|
| `py_compile` of every edited module and test | clean |
| `test_wakanda_lock_fix` + `test_wakanda_gesture` | 27/27 |
| `test_control_server`, `test_drag_safety`, `test_drag_and_drop_pipeline`, `test_phase1_drag_reliability`, `test_debug_overlay_send`, `test_debug_hud_startup` | 73/73 |
| Full guarded discovery (`AIRPOINT_ENABLE_TEST_GUARD=1`, `AIRPOINT_DISABLE_REAL_LOCK=1`) | 443/443, no `ACCEPTED (return=` or runner-refusal line in the log, i.e. no real lock attempt |
| Frontend `npx tsc --noEmit` / `npx vitest run` | clean / 135/135 (`routeTree.gen.ts` restored afterwards) |
| `git diff --check` | clean |

A worst-case run (full discovery with neither the guard nor the mock flag) was attempted as additional evidence; the session's permission system declined that command. The structural refusal it would have exercised is covered inside the suite by test 11d, which runs in the same kind of process (`python -m unittest`).

## 7. How to enable and test Wakanda on the actual desktop

No enabling step is needed any more. If `backend\settings.json` exists from an earlier session with `"wakanda-forever": false`, either delete that key, or switch "Lock Screen" on in the Control Center (Gestures → Lock Screen → toggle), which rewrites the file.

Procedure (you perform it; save your work first, the desktop will lock if it works):

1. `cd C:\Users\loges\Documents\air_point2_audit\backend` and run `.\.venv\Scripts\python.exe main.py --debug 2>&1 | Tee-Object -FilePath ..\wakanda_physical_run.log`.
2. In the debug window confirm the HUD line reads `WAKANDA   : SEARCHING (...)`. With no hands it shows `SEARCHING (BOTH_HANDS_REQUIRED)`; with hands in view the reason tells you which rule rejects the pose, for example `SEARCHING (LEFT_HAND_NOT_FIST)` or `SEARCHING (ARMS_NOT_CROSSED)`.
3. Stand so that your face and both forearms are in frame. Cross both forearms over your chest with closed fists, each fist near the opposite shoulder, fists below your mouth.
4. Expect `POSE DETECTED` within a frame, then `HOLDING x.x/2.0s` counting up, then in the log `WAKANDA: CONFIRMED after 2.0xs hold; sending one workstation lock request` and `LockWorkStation request ACCEPTED (return=1)` followed by `WAKANDA: LOCK REQUEST ACCEPTED`.
5. Windows should lock. Unlock, and record: the HUD text before the lock, the two log lines above, and whether the desktop locked. After unlocking the HUD must show `COOLDOWN (...)` and then `SEARCHING` once you uncross; a second deliberate hold must fire again exactly once.
6. Negative checks: hold for about one second and uncross (no lock; HUD returns to `SEARCHING`); keep the arms crossed after a lock (no second request; `COOLDOWN (release arms to rearm)`); start a left-hand drag and cross a fist over it (the drag must not be released; the HUD stays on the drag lines).
7. If the log shows `LockWorkStation request REJECTED (return=0, GetLastError=…)`, report the error code; the HUD will read `LOCK REQUEST FAILED` and the overlay will show "Lock request failed".

Only after you have performed step 4 and seen the desktop lock does this feature count as physically validated.

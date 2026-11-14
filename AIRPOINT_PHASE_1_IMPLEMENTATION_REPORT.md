# AIRPOINT — PHASE 1 IMPLEMENTATION REPORT (DRAG AND DROP RELIABILITY)

**Date:** 2026-11-02
**Repository / branch:** `C:\Users\loges\Documents\air_point2_audit`, `fix/p0-native-input-safety` (HEAD `4672829`, nothing committed in this phase)
**Scope:** roadmap §1 tasks 1.1–1.7. The P0 native-input-safety changes were preserved unchanged except for the three small defects listed under 1.3; the P0 contract itself (no false success, retained drag on failed LEFTUP, 80 ms release dwell, 150 ms tracking grace) is untouched.
**What this report does not claim:** any physical result. No camera, cursor, button or overlay was exercised. The procedure for that is `AIRPOINT_PHASE_1_PHYSICAL_TEST_PLAN.md`.

---

## 1. Findings addressed and root causes

| Finding | Root cause | Resolution |
|---|---|---|
| F-01 test contamination | `test_native_input_safety.py` replaced `pynput`, `pynput.mouse`, `pynput.keyboard`, `mediapipe`, `mediapipe.tasks*`, `screeninfo`, `PIL` in `sys.modules` at import time (written for an environment without those packages) and never restored them | Stubs deleted; the real packages are in the canonical virtualenv; tests rely on `SafeTestActuator` and the OS-action guard instead |
| F-02 guard import-order gap | `install_test_guard()` patched `pynput.mouse.Controller` only if `pynput.mouse` happened to be imported already | Guard imports both submodules explicitly (`importlib.import_module`) before patching |
| F-03 obsolete expectations | `test_phase6_drag.test_left_drag_release_drops` and `test_left_hand_drag_reliability.test_intentional_open_palm_drops_file_immediately` asserted the pre-P0 single-frame drop | Rewritten to expect RELEASE_PENDING on the first open frame and exactly one UP after the 80 ms dwell; docstrings say why |
| F-25 hidden timeout coupling (new) | `tearDown` in `test_drag_safety.py` and `test_phase2_left_hand.py` set `config.LEFT_DRAG_LOST_TIMEOUT_S = 0.075` (the pre-P0 value) for the rest of the process; `test_phase6_drag.test_missing_left_cancels_drag` only passed because of it | tearDowns restore the value they found; the test now expects the 150 ms grace (held at 100 ms, released after 150 ms) |
| F-04 broken property | A stray `@property` line wrapped the real property, so reading `GestureOrchestrator.max_step_limit` raised `TypeError` | Stray decorator removed; round-trip test added |
| F-05 unhashable enums | `__eq__` overrides removed `__hash__` from `SendInputResult`, `DragStartResult`, `DragEndResult` | `__hash__` restored on all three; test added |
| F-06 fragile logging | `drag_end()` retry log read `res.value` unconditionally | `getattr(res, "value", res)`; test with a bool-returning mock added |
| F-07 unverified release at shutdown/pause | `finally` released the drag after tearing down the server and overlay and ignored the result; pause called `actuator.drag_end()` from the hotkey/HTTP thread | See §2 |
| F-08 retry storm | After a failed LEFTUP the watchdog called `drag_end()` on every frame (two attempts and a CRITICAL line per frame) | Watchdog re-arms its timer after an unconfirmed release; retries are spaced by 250 ms |
| F-18 unguarded gate | `scripts/run_checks.ps1` ran the backend suite without the guard | Script exports `AIRPOINT_ENABLE_TEST_GUARD=1` and `AIRPOINT_DISABLE_REAL_LOCK=1`; stale test-count labels removed |

## 2. Behaviour changes in production code

| File | Change |
|---|---|
| `backend/core/actuator.py` | `__hash__` on the three result enums; tolerant retry log; `check_drag_watchdog` re-arms after an unconfirmed release; new `force_release_drag(max_attempts=3, retry_delay_s=0.02, context)` — bounded release that returns `NOT_DRAGGING` / `RELEASED` / `FAILED`, keeps `is_dragging=True` on failure, sets `_last_drag_error = "DRAG_RELEASE_UNCONFIRMED_AT_<context>"` and logs one CRITICAL summary line |
| `backend/main.py` | Shutdown order is now: controller `release_drag("SHUTDOWN")` → `actuator.force_release_drag("SHUTDOWN")` → server stop → overlay close → windows → restore OS settings. The `atexit` hook force-releases (`ATEXIT`) before restoring settings. Pause no longer injects input from the calling thread: it sets `pause_release_pending`; the main loop consumes it (`release_drag_on_pause()`: controller release with reason `PAUSE`, then `force_release_drag`, then a `drag-fault` SSE event if still unconfirmed). Telemetry now publishes the drag controller state, logical flag, last native error and `GetAsyncKeyState` reading every 3rd frame |
| `backend/core/control_server.py` | `RuntimeState.update_telemetry` accepts `drag_state`, `drag_logical`, `drag_error`, `native_button`; `GET /api/status` includes `drag: {state, logical_held, native_button, last_error}` |
| `backend/core/gestures/orchestrator.py` | Removed the stray `@property` |
| `backend/test_guard.py` | Explicit pynput submodule import before patching |
| `scripts/run_checks.ps1` | Guard variables; accurate labels |
| `README.md` | Test counts, guarded test command, accurate port and drag-safety statements |

No gesture threshold, dwell, timeout, filter or Windows privilege was changed. No dependency was added. The frontend was not changed; it ignores the new `drag` field.

## 3. Tests

New file `backend/test_phase1_drag_reliability.py` (20 tests, deterministic timestamps, scripted `SendInputResult` actuator, orchestrator-level):

- failed LEFTDOWN through the orchestrator → no logical drag, `INPUT_ERROR` reason, recovery on the next confirmed attempt
- failed LEFTUP → `INPUT_ERROR`, `is_dragging` retained, pointer owner stays locked, watchdog recovers after 250 ms with reason `WATCHDOG_TIMEOUT`
- persistent LEFTUP failure → watchdog retries bounded (4–12 native attempts per second instead of ~60)
- brief pinch opening (one frame at 0.90) → `RELEASE_PENDING` then recovery, no UP
- sustained unpinch → exactly one UP, no duplicates afterwards
- re-pinch inside the 80 ms dwell → back to `GRAB_LOCKED`, no UP
- stale frames (identical landmarks, then identical timestamps) → no release
- dropout inside the 150 ms grace, then reacquisition → drag continues, no second DOWN
- sustained dropout → one release at 150 ms + ≤ 2 frames, reason `TRACKING_LOSS`
- right-hand cursor keeps moving (monotonic x) while the left drag is held; owner `RIGHT`
- owner switching without a drag (LEFT → RIGHT when the right hand appears); left steering when the right hand is absent during a drag
- current F-22 behaviour documented: owner stays `RIGHT` and the cursor stops when the right hand is lost mid-drag
- `force_release_drag` success, bounded failure (6 native attempts, one CRITICAL summary, flag retained), the shutdown sequence (controller then actuator) and the pause sequence (failed controller release → force-release recovers → `READY` on the next frame)
- F-04 / F-05 / F-06 regression tests

Results (canonical venv, Python 3.14.3):

| Run | Result |
|---|---|
| Guarded full discovery | 420 tests, OK, 19.2 s |
| Unguarded full discovery | 420 tests, OK, 19.4 s |
| Reversed-order subset (`test_tracker_handedness test_test_guard test_native_input_safety test_phase6_drag test_drag_safety test_phase2_left_hand`) | 68 tests, OK |
| New matrix alone | 20 tests, OK |

Frontend gates were not re-run (no frontend change); Phase 0 results stand (tsc clean, 135/135, build OK).

## 4. Git state

```
 M backend/config.py                          (P0)
 M backend/core/actuator.py                   (P0 + Phase 1)
 M backend/core/control_server.py             (Phase 1)
 M backend/core/debug_overlay.py              (P0)
 M backend/core/gestures/drag_controller.py   (P0)
 M backend/core/gestures/orchestrator.py      (Phase 1)
 M backend/main.py                            (Phase 1)
 M backend/test_drag_and_drop_pipeline.py     (P0)
 M backend/test_drag_safety.py                (Phase 1)
 M backend/test_guard.py                      (Phase 1)
 M backend/test_left_hand_drag_reliability.py (Phase 1)
 M backend/test_phase2_left_hand.py           (P0 + Phase 1)
 M backend/test_phase6_drag.py                (Phase 1)
 M scripts/run_checks.ps1                     (Phase 1)
 M README.md                                  (Phase 1)
?? backend/test_native_input_safety.py        (P0, stubs removed in Phase 1)
?? backend/test_debug_overlay_send.py         (P0)
?? backend/test_phase1_drag_reliability.py    (Phase 1)
?? AIRPOINT_SYSTEM_ARCHITECTURE.md, AIRPOINT_ENGINEERING_ROADMAP.md, CLAUDE.md,
   AIRPOINT_PHASE_1_PHYSICAL_TEST_PLAN.md, AIRPOINT_PHASE_1_IMPLEMENTATION_REPORT.md (Phase 0/1 docs)
?? AIRPOINT_PHASE_P0_IMPLEMENTATION_REPORT.md, AIRPOINT_P0_CODE_REVIEW.md,
   AIRPOINT_P0_3_REGRESSION_VALIDATION_REPORT.md, AIRPOINT_INDEPENDENT_ARCHITECTURE_REVIEW.md (prior)
```

Nothing staged, committed or pushed. The P0 backup at `C:\Users\loges\Documents\air_point2_audit_backups\p0_worktree_backup_20261102_190141\` is untouched. A Phase 1-only patch (P0 excluded) was reviewed line by line before this report.

## 5. What still requires physical validation

Pre-flight (hardware-free, run 2026-11-02 with the canonical venv): `backend/preflight_physical_test.py` reports READY, 11/11 checks — interpreter and `sys.path` clean, all packages import, both MediaPipe models load under mediapipe 1.2.0 and run on a blank frame (hand 192 ms load / 28 ms inference, face 23 ms / 2.5 ms), 1920×1080 single monitor, port 8765 free, screenshot directory writable, audio endpoint readable, native APIs present. Results go into `AIRPOINT_PHASE_1_PHYSICAL_RESULTS.md`.

Everything in `AIRPOINT_PHASE_1_PHYSICAL_TEST_PLAN.md`, in particular:

1. T2: whether `GetAsyncKeyState(VK_LBUTTON)` reads DOWN after an injected LEFTDOWN on this machine (decides whether it can ever become a gate).
2. T3/T4: whether a real Explorer object follows the cursor and drops on the dwell release.
3. T7/T8: the new pause and shutdown release paths on a real desktop (no stuck button after `Ctrl+Alt+P` / `Ctrl+Alt+Q` while holding).
4. T9: UIPI behaviour against an elevated window (expected: `SEND:OK`, no effect).
5. Reliability counts (ten repetitions of T2–T5).

## 6. Decisions needed from the product owner (stop-and-ask)

1. **F-22 — right hand lost during a drag.** Today the pointer owner stays locked to the right hand and the cursor freezes until the drag ends; the left hand cannot take over steering. Options: keep (predictable, no cross-hand jump), or allow a one-way handover to the left hand after the right-hand grace expires (more capable, but the object jumps to the left index position). This changes gesture semantics, so it is not implemented.
2. **F-09 — right-hand fist "lock".** The documented intent is "no cursor, no gestures while a fist is held", but the cursor keeps moving. Restoring the freeze is a one-line change in the right-hand processor; it was left for Phase 2 because it changes pointer behaviour and should be decided with the pointer profile work.

## 6a. Addendum — first physical start-up attempt (F-26)

The user's first `python main.py --debug` start initialised the camera, models, actuator and control server, then crashed on the first debug frame with `NameError: name 'draw_debug_frame' is not defined` (`main.py`, debug branch). Root cause: the renderer import was conditional on `config.DEBUG_GESTURES` (default False) although the window is also enabled by `--debug` and by Ctrl+Alt+D, so the name was never bound on those paths; the exception escaped the loop and the engine shut down. The same latent crash applied to Ctrl+Alt+D in normal mode.

Fix (only `backend/main.py`): unconditional guarded import of `draw_debug_frame`; `DEBUG_HUD_IMPORT_ERROR` records any import failure; `debug_hud_available()` refuses `--debug`, `DEBUG_GESTURES` and the hotkey with one ERROR line when the renderer is missing instead of crashing. `core.debug_overlay` depends only on cv2, numpy, config and `core.tracker`, which `main.py` imports anyway, so normal mode has no added cost and there is no circular import. Regression tests: `backend/test_debug_hud_startup.py` (renderer bound with the shipped default and with either flag value; the exact debug-branch call renders a synthetic frame without a camera). No P0 native-input file, threshold, dwell or watchdog value was touched.

## 7. Deferred (by design) to later phases

F-10 port discovery, F-11/F-12/F-13 event semantics, F-14/F-15 Dyne wiring and overlay settings (Phase 3); F-16/F-17 (About page) UI copy (Phase 4); F-20/F-21/F-23/F-24 pointer-pipeline clean-ups and instrumentation (Phase 2).

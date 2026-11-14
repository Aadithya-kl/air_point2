# AIRPOINT — ENGINEERING ROADMAP

**Document date:** 2026-11-02 (Phase 0 complete)
**Companion documents:** `AIRPOINT_SYSTEM_ARCHITECTURE.md` (what exists), `CLAUDE.md` (how to work in this repository), phase reports (`AIRPOINT_PHASE_<n>_*.md`).
**Finding IDs (F-xx)** refer to §12 of the architecture document.

---

## 0. Phase 0 engineering assessment

### 0.1 What already works (verified in software this session)

- The P0 native-input safety contract is in the working tree and behaves as specified: `SendInput` returning 0 is reported as UNCONFIRMED, never as success; a drag is only marked active on CONFIRMED LEFTDOWN; a failed LEFTUP retains `is_dragging=True` and is retried by the watchdog; the release path always goes through an 80 ms dwell (21 contract tests + 17 pipeline tests + 9 HUD tests pass).
- The left-hand drag state machine (READY → GRAB_PENDING → GRAB_LOCKED → RELEASE_PENDING → READY, with INPUT_ERROR) has a single owner and exactly one native DOWN / one native UP per session in every mock scenario tested.
- Right-hand pointer movement continues during a left-hand drag in the orchestrator model (pointer owner locks to RIGHT; `test_17` and `test_14`).
- Backend suite: 400 tests collected, 395 pass under the canonical virtualenv, guarded and unguarded. Frontend: typecheck clean, 135/135 tests, production build succeeds.
- Control bridge: loopback HTTP + SSE with token-checked mutations, settings persistence to `settings.json`, settings applied on the engine's main thread; the React Control Center reads status, landmarks, camera stream and writes gesture toggles, sensitivity, smoothing, hold time, power save and the six HUD settings.
- The Tk "Dynamic Island" overlay receives direct callbacks for screenshot, WhatsApp, mute/unmute, ear volume, Wakanda, hand lost/reacquired, pause/resume, power-save states (code-verified; rendering not observed by this session).
- Pointer coordinate spaces are consistent for multi-monitor virtual desktops (VIRTUALDESK absolute moves, origin-corrected cursor queries), as a reading of the code shows.

### 0.2 What is incomplete

- Dyne notifications: the React island preview component is not mounted on any route; SSE events only populate a 5-entry history list; Dyne Studio appearance settings are memory-only and never reach the Python overlay; the event schema has no id, severity, duration or metadata (F-11, F-14).
- Missing event producers: drag started / completed / failed, pause / resume, engine started, clicks, zoom, two-hand shortcuts (§7.1 of the architecture document).
- Bridge discovery: both sides hard-code `127.0.0.1:8765`; a collision aborts the engine; the fallback port cannot be discovered by the browser (F-10).
- Observability: no per-frame latency measurement, no replay harness, no record of actual camera versus processing frame rate beyond a 5-second average log (F-23).
- Test infrastructure: the OS-action guard is not part of the documented test command, and its pynput protection is import-order dependent (F-02, F-18).
- Packaging: the Control Center is a Vite dev-server app; `backend/ui_dist` static hosting exists but nothing builds into it.

### 0.3 What is broken (verified)

| ID | Defect | Impact |
|---|---|---|
| F-01 | `test_native_input_safety.py` replaces `pynput`, `mediapipe.*`, `screeninfo`, `PIL` in `sys.modules` at import | 3 unrelated tests fail under full discovery; the guard's pynput protection is silently defeated in the same run |
| F-03 | Two legacy drag tests assert the pre-P0 immediate drop | 2 failures; they contradict the P0 behaviour and must be aligned, not deleted |
| F-04 | `GestureOrchestrator.max_step_limit` getter raises `TypeError` | any reader of the public property crashes (tests only use the setter) |
| F-05 | result enums unhashable | cannot be used in sets/dict keys; latent |
| F-06 | `drag_end()` logs `res.value` on the retry path | `AttributeError` with bool-returning actuator mocks |
| F-07 | shutdown releases the drag last and ignores the result; pause ignores the result | a failed LEFTUP at exit or pause leaves the button down with no retry and no visible fault |
| F-08 | persistent LEFTUP failure → `drag_end()` twice per frame with CRITICAL logs | log flood; retry cadence undefined |
| F-09 | right-hand fist "lock" no longer freezes the cursor | behaviour diverges from documented intent |
| F-12 | "Screenshot saved" event fires before save and on failure | false notification |
| F-13 | ear volume emits an SSE event every 50 ms | event flood |
| F-15 | gesture toasts ignore `island_enabled` / `notifications_enabled` | user setting not honoured |
| F-16 | localStorage key mismatch in the anti-flash script | theme flash on load |
| F-17 | About page / README state wrong protocol, test counts and discovery claims | misleads operators |
| F-19 | prior validation interpreter leaks the older checkout onto `sys.path` | prior regression numbers were produced in a contaminated environment |

### 0.4 What has only been tested with mocks

Everything involving native input and the OS: `SendInput` delivery, `GetAsyncKeyState` semantics after injection, drag-and-drop of real Explorer objects, UIPI/elevated-window behaviour, multi-monitor mapping, screenshot capture, audio endpoint control, WhatsApp launch, workstation lock, the Tk overlay rendering, camera capture and MediaPipe inference timing. `test_startup.py` is a manual smoke script, not collected. The `validate_stage4_*` harnesses perform bounded live cursor moves but were not run.

### 0.5 What has never been physically validated (by this session)

No physical test of any kind was performed in Phase 0: no camera was opened, no cursor was moved, no button was injected, no overlay was shown. All statements about runtime behaviour are from code reading and mocked execution.

### 0.6 Highest-risk defects (ranked)

1. **Physical drag/hold/drop is unproven.** CONFIRMED means "accepted into the input stream", not "the target application performed the drag". Risk: shipping a flagship feature whose success criterion has never been observed.
2. **Unverified release on shutdown and pause (F-07).** A stuck left button after exit is the worst user-visible failure the product can produce.
3. **Test-isolation contamination (F-01/F-02/F-18).** The suite can report green while the OS-action guard is disabled, and it reports red for reasons unrelated to the code under test. This blocks trustworthy regression testing for every later phase.
4. **Bridge port rigidity (F-10).** A single stray process on 8765 prevents the product from starting, or silently disconnects the UI.
5. **Dyne is not a notification system yet (F-11, F-14).** The React side cannot show a real gesture event; the Python overlay cannot be styled.
6. **Pointer quality is unmeasured (F-23).** Historical ≈15 fps processing with 30 fps capture means every smoothing decision so far was made without data.

### 0.7 Recommended first implementation tasks (Phase 1, in order)

1. Remove the `sys.modules` stubs from `test_native_input_safety.py` (dependencies are installed); make `test_guard.install_test_guard()` import and patch `pynput.mouse`/`pynput.keyboard` explicitly; make `scripts/run_checks.ps1` set the guard variables. Re-run full discovery: expected 398/400 before the next step.
2. Align the two obsolete tests (`test_phase6_drag`, `test_left_hand_drag_reliability`) to the 80 ms release dwell without weakening production code. Expected 400/400.
3. Fix the small verified production defects: F-04 (duplicate `@property`), F-05 (`__hash__` on result enums), F-06 (robust logging). Add tests for each.
4. Harden shutdown and pause: release the drag before tearing down the server and overlay, bound the retry (e.g. 3 attempts × 20 ms), log a single explicit `DRAG_RELEASE_UNCONFIRMED_AT_EXIT` fault, expose `last_drag_error` and native button state in `/api/status`, and rate-limit the watchdog retry (F-07, F-08).
5. Add the missing drag tests from the brief (failed LEFTDOWN / LEFTUP through the orchestrator, repeated LEFTUP retry, brief pinch opening, sustained unpinch, re-pinch during RELEASE_PENDING, right cursor during drag with stale frames, tracking dropout and reacquisition, pointer owner switching, shutdown during an active drag).
6. Write the physical Windows drag test procedure (`AIRPOINT_PHASE_1_PHYSICAL_TEST_PLAN.md`) for the user to execute.

Deferred to later phases on purpose: F-09 (pointer behaviour, Phase 2), F-10/F-11/F-12/F-13/F-14/F-15 (Phase 3), F-16/F-17 (Phase 4), F-22 (needs a product decision, Phase 1 report will ask).

---

## 1. Phase 1 — Drag and drop reliability

**Goal:** every drag outcome is either confirmed or reported as a fault; the test suite is trustworthy; a human can execute a repeatable physical validation.

| # | Task | Files | Acceptance criteria |
|---|---|---|---|
| 1.1 | Test isolation (F-01, F-02, F-18) | `backend/test_native_input_safety.py`, `backend/test_guard.py`, `scripts/run_checks.ps1` | No `sys.modules` assignment in any test; `test_test_guard` passes in full discovery; guard patches pynput regardless of import order; `run_checks.ps1` exports `AIRPOINT_ENABLE_TEST_GUARD=1`, `AIRPOINT_DISABLE_REAL_LOCK=1` |
| 1.2 | Obsolete dwell expectations (F-03) | `backend/test_phase6_drag.py`, `backend/test_left_hand_drag_reliability.py` | Tests express "RELEASE_PENDING on first open frame, one UP after ≥ 80 ms"; production untouched |
| 1.3 | Small production defects (F-04, F-05, F-06) | `orchestrator.py`, `actuator.py` | Getter returns the limit; enums hashable; `drag_end()` logs any result type; regression tests added |
| 1.4 | Shutdown / pause release hardening (F-07, F-08) | `main.py`, `actuator.py`, `drag_controller.py`, `control_server.py` | Drag released first in `finally`; bounded retries; one CRITICAL fault line per failure; `last_drag_error` + native button state visible in `/api/status` and the debug HUD; watchdog retry interval ≥ 100 ms; tests for exit-with-held-button and exit-with-failed-LEFTUP |
| 1.5 | Drag test matrix | new `backend/test_drag_reliability_phase1.py` | All scenarios listed in §0.7 item 5 pass; each test drives the orchestrator with explicit timestamps (no `time.sleep`) |
| 1.6 | Observability | `drag_controller.py`, `main.py` | State transitions logged once at INFO with reason, elapsed dwell and native result; per-frame values at DEBUG only |
| 1.7 | Physical test plan | `AIRPOINT_PHASE_1_PHYSICAL_TEST_PLAN.md` | Step-by-step procedure with expected log lines, HUD fields and pass/fail criteria for grab, hold, right-hand steering, drop, noisy release, tracking loss, pause, exit, UIPI target |

Stop-and-ask items surfaced for Phase 1: pointer-owner policy when the right hand is lost mid-drag (F-22); whether the right-hand fist lock should freeze the cursor again (F-09).

**Phase 1 status (2026-11-02):** tasks 1.1–1.7 implemented; see `AIRPOINT_PHASE_1_IMPLEMENTATION_REPORT.md`. Backend 420/420 (guarded and unguarded). Not done in software: nothing. Not done at all: the physical procedure in `AIRPOINT_PHASE_1_PHYSICAL_TEST_PLAN.md` (user-executed) and the two product decisions above. Finding F-25 (test tearDowns pinning the pre-P0 timeout) was discovered and fixed during 1.1. Finding F-26 (`--debug` start-up `NameError`, found by the user on the first physical attempt) was fixed in `main.py` with a regression test before the physical run resumed; physical results are still pending. The user then confirmed the engine, tracking, pointer, drag and HUD run physically and asked for the Wakanda Forever lock gesture, which had never run (F-27) and reported false success (F-28); see `AIRPOINT_WAKANDA_GESTURE_FIX_REPORT.md`. The deliberate Wakanda gesture on the real desktop is still to be performed by the user.

## 2. Phase 2 — Pointer smoothness and precision

| # | Task | Acceptance criteria |
|---|---|---|
| 2.1 | Instrumentation: per-frame capture timestamp, inference time, filter input/output, dispatch time; ring buffer exported through `/api/metrics` and a CSV dump command | Camera fps, processing fps, frame-time mean/variance, landmark jitter at rest, cursor jitter at rest, response delay (step input) reported from real runs |
| 2.2 | Replay harness: record landmark streams with timestamps; replay through the orchestrator offline | A recorded session reproduces identical cursor output bit-for-bit |
| 2.3 | Use capture timestamps in the One Euro filter instead of processing time | Filter dt equals camera dt in replay |
| 2.4 | Evaluate filter settings, dead zones, edge handling, sensitivity curve, separate profiles for pointing / fine pointing / drag | Before/after measurements documented; no stacked filters without a latency budget |
| 2.5 | Resolve F-09 and F-24 | Fist lock behaviour decided and tested; dead states removed |

## 3. Phase 3 — Dyne: a real notification system (delivered by the unified migration, 2026-11-02)

| # | Task | Acceptance criteria | Status |
|---|---|---|---|
| 3.1 | Event schema `{id, session, type, timestamp, source, title, message, priority, duration_s, metadata}` produced by one backend dispatcher; SSE carries ids; `/api/status` carries a bounded history with the same ids | No duplicates on reconnect; ordering preserved; history bounded | **Done** (`backend/core/events.py`, `/api/events` with `id:` lines + Last-Event-ID replay, `/api/events/history`, ring of 50; `test_dyne_events.py`) |
| 3.2 | Producers for every existing feature (drag start/complete/fail, pause/resume, start/stop, tracking, screenshot, app, audio, Wakanda/lock, power); fix F-12, F-13 | Each real gesture produces exactly one event with correct outcome | **Done** for the listed features; clicks, zoom and the two-hand shortcuts still produce no event (they are not surfaced anywhere today; add producers when those gestures get HUD feedback) |
| 3.3 | Bridge discovery (F-10) | UI connects after a port fallback; clear offline banner otherwise | **Done for launcher-started runs** (`VITE_AIRPOINT_BRIDGE_URL` from `bridge_info.json`, loopback-only validation; `-AllowPortFallback`); a hand-started dev server still needs the variable; the backend does not serve the built UI |
| 3.4 | React island driven by events, mounted in the shell; reconnection; preview versus live | A real gesture activates the island; previews are labelled | **Done** (`dyne-live-island.tsx` in `DesktopShell`, `eventStream` state, `data-live` + LIVE tag; previews keep PREVIEW/DEMO copy); reconnection relies on `EventSource` retry + bridge replay, no custom backoff |
| 3.5 | Persisted Dyne preferences consumed by both the Python overlay and the React island (F-14, F-15) | Settings survive restart; running overlay honours changes immediately | **Partly done**: the six switches/timings, `island_position` and the applied `island_appearance` are persisted and honoured by both surfaces; **per-category (per-event-type) enable and scale are not implemented** (one global notifications switch) |

## 4. Phase 4 — Product polish

Information architecture pass on the Control Center, remove dead controls (browser-only cursor playground labelled or removed, fake sparkline), consistent design tokens, empty/error states, reduced-motion compliance, Dyne as a coherent companion. F-16/F-17 and the README launcher section were fixed by the unified migration; the rest is open.

## 5. Phase 5 — System validation

Full backend and frontend regression (done after every change so far), integration tests against a live `ControlServer` without a camera (done for the event bridge in `test_dyne_events.py`), start/stop scripts verified (dry run and a frontend-only cycle done; the engine modes are verified only by the user), performance report from Phase 2 instrumentation (open), physical checklist results from the user (open: `AIRPOINT_PHASE_1_PHYSICAL_RESULTS.md` is still all NOT RUN), known-limitations report (`AIRPOINT_UNIFIED_MIGRATION_REPORT.md` §14).

---

## 6. Working rules (summary; full text in `CLAUDE.md`)

- Canonical checkout only; never the `antigravity` tree or its virtualenv.
- No branch switch, merge, cherry-pick, commit or push without explicit authorisation.
- Never weaken production code to satisfy an obsolete test; never delete a failing test to go green.
- Mock-based results are never reported as physical validation; physical tests are executed by the user from a written procedure.
- Stop and explain before changing gesture semantics, Windows privileges, dependencies, or the native-input safety contract.

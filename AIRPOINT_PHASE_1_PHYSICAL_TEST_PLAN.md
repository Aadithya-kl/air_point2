# AIRPOINT — PHASE 1 PHYSICAL WINDOWS TEST PLAN (DRAG AND DROP)

**Purpose.** Establish, on a real Windows desktop with a real webcam, what the mocked test suite cannot: whether an injected left-button hold actually drags objects, whether `GetAsyncKeyState` reflects injected input, whether release paths (deliberate, noisy, tracking loss, pause, exit) leave the physical button in the expected state, and how elevated windows behave. This plan is executed by a human. Nothing in the automated suite is a substitute for it.

**Terminology.** Three observations are always recorded separately and never merged into one "it worked":
- `LOG` — the engine's logical drag flag (`actuator.is_dragging`).
- `BTN` — `GetAsyncKeyState(VK_LBUTTON)` as reported by the engine (DOWN / UP / UNKNOWN).
- `OS` — what Windows visibly did (object moved, dropped, selection rectangle, nothing).

A test passes only when all three agree with the expected column.

---

## 0. Safety and abort

- Keep the physical mouse within reach. Moving it overrides the injected cursor position; clicking it clears any stuck button state.
- `Ctrl+Alt+P` pauses tracking (releases a held drag on the main loop). `Ctrl+Alt+Q` exits (releases first, then tears down).
- If the left button appears stuck after any step (a selection rectangle follows the cursor, or windows "drag" when you move): press and release the physical left mouse button once. Record it as a FAIL for that step.
- Do not run the Wakanda lock tests here; `AIRPOINT_DISABLE_REAL_LOCK` is irrelevant for drag.
- Test on a scratch folder on the desktop containing a few disposable files, so a mis-drop cannot move anything important.

## 1. Preconditions

1. Canonical checkout `C:\Users\loges\Documents\air_point2_audit`, branch `fix/p0-native-input-safety`, with the Phase 1 working tree.
2. Run the hardware-free preflight and require `READY`:

```
cd C:\Users\loges\Documents\air_point2_audit\backend
.\.venv\Scripts\python.exe preflight_physical_test.py
```

   It checks the interpreter, packages, both MediaPipe models (loaded and run on a blank frame), display geometry, port 8765, the screenshot directory, the audio endpoint and the native APIs. It never opens the camera or sends input.
3. Webcam connected; nothing else using it.
4. No other process on port 8765 (`Get-NetTCPConnection -LocalPort 8765 -State Listen` returns nothing).
5. Start the engine with the debug window and a log file, from PowerShell:

```
cd C:\Users\loges\Documents\air_point2_audit\backend
.\.venv\Scripts\python.exe main.py --debug 2>&1 | Tee-Object -FilePath ..\phase1_physical_run.log
```

6. Confirm the "VIRTUAL POINTER" window shows `SENSOR_R`/`SENSOR_L` tracking and the HUD lines `DRAG STATE`, `DRAG CFG`, `DRAG CURSOR`.
7. Optional: open `http://127.0.0.1:8765/api/status` in a browser; the `drag` object there must match the HUD (`state`, `logical_held`, `native_button`, `last_error`).

Record in the header of your results: Windows build, DPI scaling, monitor layout, webcam model, measured processing FPS from the HUD (`FPS: CAM x | PROC y`).

## 2. Test matrix

For every test record: HUD `DRAG STATE`, `LOG`, `BTN`, `SEND`, `OWNER`, the log lines quoted below, and the OS outcome.

### T1 — Pointer baseline (no drag)

Steps: raise the right hand, move it across the frame for 10 s.
Expect: cursor follows; HUD `SEND:OK`; no "unconfirmed" or "UNCERTAIN" anywhere; `OWNER:RIGHT`, `MOVING:YES`.
Fail if: `SEND:UNCERTAIN` or `SEND:FAIL` ever appears while moving on the normal desktop (this would mean `SendInput` is being rejected in your session; stop and report).

### T2 — Grab confirmation and native button state

Steps: right hand points at a disposable file; left hand pinches thumb + index and holds still.
Expect within ~0.1 s: log `DragLockState transition: GRAB_PENDING -> GRAB_LOCKED (...res=DragStartResult.STARTED)` and `Drag started successfully (native MOUSEEVENTF_LEFTDOWN CONFIRMED)`; HUD `DRAG STATE: GRAB_LOCKED`, `LOG:YES`, `SEND:OK`.
Record `BTN` **exactly**. The expected value is DOWN. If it reads UP while `LOG:YES` and the OS shows the file highlighted/grabbed, record "BTN does not reflect injected input"; this is the open question about `GetAsyncKeyState` semantics and must be reported either way. Also record whether the log printed `Native button state not DOWN after LEFTDOWN injection`.
OS: the file becomes selected/pressed.

### T3 — Hold and steer with the right hand

Steps: keep the left pinch; move the right hand slowly across the frame for 5 s, then quickly for 2 s.
Expect: the file follows the cursor continuously; HUD `OWNER:RIGHT`, `MOVING:YES`, `LOG:YES`; no `RELEASE_PENDING` transitions in the log while the left hand is steady.
Fail if: the file is dropped, the cursor stops while the right hand moves, or `OWNER` changes.

### T4 — Deliberate drop

Steps: with the file held over an empty desktop area, open the left hand fully and keep it open.
Expect: log `GRAB_LOCKED -> RELEASE_PENDING`, then `RELEASE_PENDING -> deliberate unpinch (dwell=0.08…)` and `Drag ended successfully (native MOUSEEVENTF_LEFTUP CONFIRMED)`; HUD `DRAG STATE: READY`, `LOG:NO`, `BTN:UP`; status `DROP` text briefly.
OS: the file is dropped at the cursor position (Explorer moves the icon there).
Fail if: more than one `Drag ended` line per drop, the file snaps back, or `BTN` stays DOWN.

### T5 — Noisy release must not drop

Steps: hold a file; make a quick, small finger flick (open and close within ~50 ms) while keeping the pinch overall; repeat 5 times.
Expect: at most `GRAB_LOCKED -> RELEASE_PENDING` followed by `RELEASE_PENDING -> GRAB_LOCKED (pinch recovered…)`; no `Drag ended` line; the file stays attached.
Record: how many flicks produced a `RELEASE_PENDING` entry and how many produced a drop (expected 0 drops).

### T6 — Tracking loss during a hold

Steps: hold a file; move the left hand out of the frame (or cover the camera half) for ~1 s while the right hand stays visible.
Expect: log `Sustained left-hand tracking loss (0.1xx s > 0.150 s); safely releasing locked grab` (or the orchestrator's equivalent after its grace), `Drag ended successfully`; HUD `READY`, `LOG:NO`, `BTN:UP`; `[REL: TRACKING_LOSS]` on the DRAG STATE line.
OS: the file is dropped where the cursor was when tracking was lost.
Also run the short version: hide the left hand for ~0.1 s and bring it back. Expect no release and the file still attached (grace window).

### T7 — Pause during a hold

Steps: hold a file; press `Ctrl+Alt+P`.
Expect: log `SYSTEM PAUSED`, then `PAUSE: native left button released (attempt 1/3)` (or the controller's `Drag ended successfully` line first); HUD shows `PAUSED`; `BTN:UP`.
OS: the file is dropped; moving the physical mouse afterwards drags nothing.
Press `Ctrl+Alt+P` again to resume; T2 must work again afterwards (re-arm).

### T8 — Exit during a hold

Steps: hold a file; press `Ctrl+Alt+Q`.
Expect in the log (in this order): `SHUTDOWN: native left button released (attempt 1/3)` or `Drag ended successfully`, then `Air Point Control Bridge stopped`, then `=== AI Air Mouse stopped ===`.
OS after exit: move the physical mouse: no selection rectangle, no window drag; a single physical click selects normally.
Fail if the log shows `SHUTDOWN: native left button release UNCONFIRMED` (report the `native_button` value printed with it) or the OS shows a stuck button.

### T9 — Elevated target (UIPI behaviour)

Steps: open an elevated application window (for example Task Manager started with "Run as administrator", or `regedit`). With the engine running (not elevated), use the right hand to move the cursor over that window and perform a pinch click on one of its buttons; then try to drag the elevated window by its title bar with the left-hand pinch.
Expect: HUD `SEND:OK` (Windows accepted the records) but the elevated window does not react (UIPI blocks lower-integrity input). Record exactly what happened; this test documents that `CONFIRMED` is not delivery.
Then click and drag on a normal (non-elevated) window to confirm input is still working.

### T10 — Bridge view of the fault state

Steps: during T2 and T4, fetch `http://127.0.0.1:8765/api/status` and read the `drag` object.
Expect: `state` and `logical_held` match the HUD at that moment, `native_button` matches `BTN`, `last_error` is `null` after a successful drop.

### T11 — Multi-monitor (only if more than one monitor is attached)

Steps: repeat T2–T4 dragging a file from the primary monitor to a secondary monitor and back.
Expect: the cursor and the file cross the boundary without jumps; drop lands where the cursor is shown.

### T12 — Long hold stability

Steps: hold a file for 60 s with the left hand steady and the right hand moving slowly.
Expect: exactly one `Drag started` line and no `Drag ended` line for the whole minute; no watchdog warnings (`Drag safety watchdog triggered`).

## 3. Results

Record everything in `AIRPOINT_PHASE_1_PHYSICAL_RESULTS.md` (pre-filled with one row per test, a session header and repetition counts) and attach `phase1_physical_run.log`.

## 4. What these results do and do not establish

- A pass on T2–T4 establishes that, on this machine and for Explorer, the injected hold produces a real drag and the dwell-based release produces a real drop.
- T2's `BTN` reading decides whether `GetAsyncKeyState` can ever be promoted from telemetry to a gate. Do not promote it without this measurement.
- T9 establishes the UIPI limitation that must be documented to users.
- A single pass does not establish reliability. Repeat T2–T5 ten times each and report counts; reliability claims in later phases must cite these counts.

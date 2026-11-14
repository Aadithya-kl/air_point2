# AIRPOINT P0.2 — PHYSICAL WINDOWS VALIDATION REPORT
**Pre-Validation Test Rig Preparation & Execution Template**

**Document Version:** 1.1.0  
**Repository Branch:** `main`  
**Execution Status:** **READY FOR PHYSICAL VALIDATION (ALL PHYSICAL TESTS: NOT RUN)**  
**Target Platform:** Windows 11 Desktop (x64)  
**Human Operator:** User  
**Automated Verification Suite:** `tools/p0_2/Verify-AirPointP02Sandbox.ps1`

---

## 1. Executive Summary & Verification Preconditions

Milestones P0 and P0.1 completed the structural overhaul of AirPoint's drag-and-drop state machine (`LeftDragController`), the native input abstraction layer (`MouseActuator`), and the real-time debug diagnostics HUD (`DebugOverlay`).

**Milestone P0.2** establishes the physical testing rig and protocol for live human-operated validation. In accordance with strict validation guidelines:
- **No physical tests are simulated or fabricated.** Every physical test entry in this report is initialized to `NOT RUN`.
- The human tester will personally execute the physical gesture procedures outlined in `AIRPOINT_P0_2_PHYSICAL_TEST_GUIDE.md`.
- **A visual drag animation or floating cursor ghost alone is NOT proof of success.** File movement and data integrity must be verified deterministically via SHA-256 manifests using `tools/p0_2/Verify-AirPointP02Sandbox.ps1`.

### Pre-Validation Regression Baseline

| Test Suite / Scope | Test Files Included | Tests Run | Result | Duration |
| :--- | :--- | :--- | :--- | :--- |
| **Core Drag & Safety** | `test_drag_and_drop_pipeline.py`<br>`test_drag_safety.py`<br>`test_power_state_machine.py`<br>`test_test_guard.py`<br>`test_frame_freshness.py`<br>`test_phase2_left_hand.py` | 82 | **PASS (82/82)** | 3.00s |
| **Jump Protection & Reacquisition** | `test_jump_protection_and_reacquisition.py` | 26 | **PASS (26/26)** | 0.11s |
| **Debug Overlay SendInput Diagnostics** | `test_debug_overlay_send.py` | 8 | **PASS (8/8)** | 0.04s |
| **Focused Pre-Flight Test Total** | All 8 focused suites above | 116 | **PASS (116/116)** | 3.13s |
| **Full Repository Regression** | All 38 discovery test suites (`backend/test_*.py`) | 378 | **PASS (378/378)** | 18.77s |
| **Whitespace / Diff Check** | `git diff --check` | N/A | **CLEAN (0 errors)** | <0.1s |

---

## 2. Test Rig & Environmental Configuration

Confirmed pre-flight environment settings:

| Parameter | Recommended Specification | Actual Test Rig Value | Status |
| :--- | :--- | :--- | :--- |
| **Operating System** | Windows 11 Build 22621+ (x64) | Windows 11 (Standard User) | Ready |
| **Elevation State** | Standard User (Non-Elevated) | Non-Elevated (`standard`) | Confirmed |
| **Monitor Resolution** | 1920 × 1080 (Primary Monitor) | `1920x1080` | Confirmed |
| **Windows DPI Scaling** | 100% or 125% (No custom scaling) | Confirmed via Win32 API | Ready |
| **Webcam Hardware** | 720p or 1080p @ 30 FPS minimum | Standard USB / Built-in Cam | Ready |
| **Camera Placement** | Centered top of primary monitor | ~50–75 cm from user | Ready |
| **Lighting Setup** | Diffuse frontal lighting, no harsh backlights | Standard indoor room lighting | Ready |
| **File Explorer Setup** | Dual-window layout: Left = Source, Right = Destination | Windows Explorer list view | Ready |
| **Sandbox Path** | `C:\Users\loges\AirPoint-Sandbox` | `C:\Users\loges\AirPoint-Sandbox` | Verified (31 assets intact) |

---

## 3. Real-Time Diagnostics & Telemetry Assessment

AirPoint v2.0 features real-time diagnostics rendered on the camera HUD (`--debug` mode) and logged via stderr/stdout:

| Metric | Source Indicator | Expected Normal Value | Meaning / Verification Rule |
| :--- | :--- | :--- | :--- |
| **Cam / Proc FPS** | `CAM xx.x \| PROC xx.x` | `CAM >= 28 \| PROC >= 28` | Ensures frame processing keeps pace with 33.3ms video intervals. |
| **Right Hand Tracking** | `SENSOR_R: TRACKING` | `TRACKING (ACTIVE)` | HandLandmarker confidence >= 0.5; controls Windows cursor. |
| **Left Hand Tracking** | `SENSOR_L: TRACKING` | `TRACKING` or `GRACE` | Pinch hand detected; `GRACE` indicates dropout tolerance active. |
| **Desktop Coordinates** | `CURSOR WIN: XXXX, YYYY` | Valid desktop coordinates | Tracks calculated virtual cursor position on desktop. |
| **Drag State Machine** | `DRAG STATE: <STATE>` | `READY`, `GRAB_PENDING`, `GRAB_LOCKED`, `DROP` | Reflects `LeftDragController` state transitions. |
| **Pinch Telemetry** | `(d=X.XX/th=X.XX)` | `d < 0.55` (Grab) / `d > 0.75` (Drop) | Normalized Euclidean distance between thumb and index tips. |
| **Tracking Presence** | `DET: YES \| NO \| GRACE` | `YES` during interaction | `NO` = hand absent; `GRACE` = hand absent within 75ms tolerance. |
| **Actuator Drag Flag** | `LOG: YES \| NO` | `YES` only when dragging | Internal boolean flag indicating drag session active. |
| **Hardware Button State**| `BTN: DOWN \| UP` | `DOWN` during hold, `UP` when idle | Polled natively via Win32 `GetAsyncKeyState(VK_LBUTTON)`. |
| **SendInput Result** | `SEND: OK \| FAIL \| UNCERTAIN \| N/A` | `OK` on injection | Low-level result: `OK` (confirmed), `FAIL` (error), `UNCERTAIN` (unconfirmed/retry fail), `N/A` (idle). |
| **Pointer Ownership** | `OWNER: RIGHT \| LEFT` | `RIGHT` | Designates which hand drives the Windows desktop cursor. |
| **Cursor Stream** | `SRC: RIGHT \| LEFT` | `RIGHT` | Coordinate stream actively delivering mouse move events. |
| **Cursor Movement** | `MOVING: YES \| NO` | `YES` when hand is in motion | Confirms cursor updates are actively streaming to OS. |

---

## 4. Physical Test Execution Matrix

*Status Legend: `NOT RUN` (Pending human execution) | `PASS` | `FAIL` | `BLOCKED` | `INCONCLUSIVE`*

| Test ID | Procedure / Description | Target Asset | Precondition | Expected State & Telemetry | Actual Result | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **TEST-A** | **Basic Pointer Movement**<br>Move right index finger across all 4 screen quadrants without left hand. | Cursor Only | AirPoint running in debug mode | Smooth cursor movement across screen; no jumps; `OWNER: RIGHT`, `MOVING: YES`. | *(To be recorded by user)* | `NOT RUN` |
| **TEST-B** | **Native Left-Button Grab**<br>Hover over asset, pinch left thumb-index, confirm selection, release. | `drag-test-01.txt` | Cursor positioned over file | `DRAG STATE`: `READY` → `PENDING` → `LOCKED`<br>`BTN: DOWN`, `SEND: OK`. Release: `DROP` → `READY`, `BTN: UP`. | *(To be recorded by user)* | `NOT RUN` |
| **TEST-C.1** | **Sustained Hold — 2 Seconds**<br>Grab file, circle right hand continuously for 2.0s, drop into Destination. | `hold-2s.txt` | Left hand pinched for >= 2.0s | Continuous `BTN: DOWN`; no premature drop during circular motion; drop on open. | *(To be recorded by user)* | `NOT RUN` |
| **TEST-C.2** | **Sustained Hold — 5 Seconds**<br>Grab file, circle right hand continuously for 5.0s, drop into Destination. | `hold-5s.txt` | Left hand pinched for >= 5.0s | Continuous `BTN: DOWN`; ghost icon follows cursor without release until deliberate unpinch. | *(To be recorded by user)* | `NOT RUN` |
| **TEST-C.3** | **Sustained Hold — 10 Seconds**<br>Grab file, circle right hand continuously for 10.0s, drop into Destination. | `hold-10s.txt` | Left hand pinched for >= 10.0s | No watchdog timeout (< 250ms lost hand); button holds until intentional left unpinch. | *(To be recorded by user)* | `NOT RUN` |
| **TEST-D.1** | **Real File Movement (Single File)**<br>Drag file from Source to Destination window; verify move with SHA-256. | `drag-test-02.txt` | Source and Destination Explorer open side-by-side | File disappears from Source, appears in Destination; `Verify-AirPointP02Sandbox.ps1` returns `MOVED_VERIFIED`. | *(To be recorded by user)* | `NOT RUN` |
| **TEST-D.2** | **Real Folder Movement**<br>Drag entire directory structure from Source to Destination. | `TestFolder/` | Folder containing `inside.txt` | Entire folder moves to Destination; inner file contents and hashes preserved. | *(To be recorded by user)* | `NOT RUN` |
| **TEST-E** | **Repeated Drag Cycles (20 Iterations)**<br>Perform 20 consecutive drag-and-drop operations on separate files. | `cycle-01.txt` .. `cycle-20.txt` | 20 individual synthetic text files in Source | 20/20 clean grabs and drops; zero stuck buttons; zero premature drops; logged in CSV. | *(To be recorded by user)* | `NOT RUN` |
| **TEST-F** | **Nested Folder Hierarchy Movement**<br>Drag multi-file folder to Destination and verify child file hashes. | `FolderCycle/` | Contains `file-01.txt` & `file-02.txt` | `FolderCycle/` moved; SHA-256 hashes of both inner files match manifest exactly. | *(To be recorded by user)* | `NOT RUN` |
| **TEST-G.1** | **Jitter Tolerance (Hysteresis)**<br>During drag, partially relax left pinch (`d ≈ 0.65`) without opening (`th = 0.75`). | `drag-test-01.txt` | In active `GRAB_LOCKED` | State remains `GRAB_LOCKED`; `BTN: DOWN` maintained; no accidental drop occurs. | *(To be recorded by user)* | `NOT RUN` |
| **TEST-G.2** | **Tracking Dropout Grace Period**<br>During drag, occlude or drop left hand for ~50ms (< 75ms grace) and restore. | `drag-test-01.txt` | In active `GRAB_LOCKED` | State enters `DET: GRACE`; does NOT drop; restores to `DET: YES` when hand reappears. | *(To be recorded by user)* | `NOT RUN` |
| **TEST-G.3** | **Sustained Hand Loss Safety Release**<br>During active drag, completely withdraw left hand from camera view (> 75ms). | `drag-test-01.txt` | In active `GRAB_LOCKED` | Grace expires; state transitions to `READY` with `REL: TRACKING_LOSS`; button safely released. | *(To be recorded by user)* | `NOT RUN` |
| **TEST-H.1** | **Multi-Monitor Boundary Crossing** *(Optional)*<br>Drag asset across virtual desktop monitor boundary. | Multi-monitor rig | Secondary display attached | Cursor smoothly crosses monitor boundary while maintaining `BTN: DOWN`. | *(To be recorded by user)* | `NOT RUN` |
| **TEST-H.2** | **UIPI Privilege Boundary Isolation** *(Optional)*<br>Attempt to drag asset into an elevated (Administrator) window. | Admin Window | Elevated prompt / Task Manager | Windows UIPI security blocks drop into elevated window; button releases safely on unpinch. | *(To be recorded by user)* | `NOT RUN` |

---

## 5. Detailed Test E Log Sheet (20-Cycle Verification)

Use this table (and `P0_2_TEST_LOG.csv`) to record individual cycle metrics during physical execution:

| Cycle # | Asset Name | Grab Time | Drop Time | Pinch `d` | FPS | BTN State | Move Verified (Y/N) | Operator Notes |
| :---: | :--- | :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| 1 | `cycle-01.txt` | — | — | — | — | — | — | Pending test |
| 2 | `cycle-02.txt` | — | — | — | — | — | — | Pending test |
| 3 | `cycle-03.txt` | — | — | — | — | — | — | Pending test |
| 4 | `cycle-04.txt` | — | — | — | — | — | — | Pending test |
| 5 | `cycle-05.txt` | — | — | — | — | — | — | Pending test |
| 6 | `cycle-06.txt` | — | — | — | — | — | — | Pending test |
| 7 | `cycle-07.txt` | — | — | — | — | — | — | Pending test |
| 8 | `cycle-08.txt` | — | — | — | — | — | — | Pending test |
| 9 | `cycle-09.txt` | — | — | — | — | — | — | Pending test |
| 10 | `cycle-10.txt` | — | — | — | — | — | — | Pending test |
| 11 | `cycle-11.txt` | — | — | — | — | — | — | Pending test |
| 12 | `cycle-12.txt` | — | — | — | — | — | — | Pending test |
| 13 | `cycle-13.txt` | — | — | — | — | — | — | Pending test |
| 14 | `cycle-14.txt` | — | — | — | — | — | — | Pending test |
| 15 | `cycle-15.txt` | — | — | — | — | — | — | Pending test |
| 16 | `cycle-16.txt` | — | — | — | — | — | — | Pending test |
| 17 | `cycle-17.txt` | — | — | — | — | — | — | Pending test |
| 18 | `cycle-18.txt` | — | — | — | — | — | — | Pending test |
| 19 | `cycle-19.txt` | — | — | — | — | — | — | Pending test |
| 20 | `cycle-20.txt` | — | — | — | — | — | — | Pending test |

---

## 6. Safe Shutdown & Emergency Recovery Verification

Prior to live physical testing, the emergency mechanisms were audited directly in source code:

1. **Global Hotkey Emergency Exit (`Ctrl+Alt+Q`):**
   - Implemented via `pynput.keyboard.GlobalHotKeys` in `main.py`.
   - Triggers `on_activate_quit()`, cleanly breaking the main execution loop.
   - Executes `finally:` cleanup block: calls `actuator.drag_end()` (with 5ms retry), restores multimedia timer resolution (15.6ms), and restores pointer precision settings.
   - *Architecture Note:* The software attempts native release up to 4 times across normal and shutdown execution paths, but **cannot guarantee OS-level release** if Windows UIPI or kernel-level security blocks `SendInput`.
2. **Pause / Resume Hotkey (`Ctrl+Alt+P`):**
   - Instantly toggles pause state: calls `actuator.drag_end()`, clears pointer ownership, and freezes tracking.
3. **Hardware Mouse Physical Override (Status: UNVERIFIED):**
   - Single click on a physical mouse generates a hardware interrupt and native Windows button-up event at the OS driver level. However, interaction with synthetic queues under all Windows 11 contexts remains **UNVERIFIED**.
4. **Guaranteed Windows NT Kernel Reset (Secure Desktop):**
   - Pressing **`Ctrl+Alt+Del`** unconditionally resets all user-mode logical mouse and keyboard capture states at the Windows NT kernel level. Pressing **`Esc`** returns to desktop with clean state.
5. **Drag Watchdog Timer (250ms):**
   - Active in `MouseActuator` *only* while the main inference loop runs. If left-hand tracking is completely lost while dragging for > 250ms, native release is dispatched automatically. The watchdog does **NOT** run after process termination.
6. **Targeted Process Termination (Safe Procedure):**
   - Never run generic `Stop-Process -Name python -Force`. Instead, identify the exact AirPoint PID via `Get-CimInstance Win32_Process` matching `AirPoint\backend\main.py`, verify its command line, and terminate only that specific PID.

---

## 7. Known Limitations & Environmental Constraints

1. **Windows UIPI (User Interface Privilege Isolation):**
   - Running AirPoint as a standard non-elevated user prevents injecting mouse clicks or drag events into elevated windows (e.g., Task Manager or Administrator Command Prompts). This is an enforced Windows NT security boundary.
2. **Backlight & Contrast Sensitivity:**
   - MediaPipe HandLandmarker confidence drops when hands are backlit by bright windows. Tester must ensure uniform front lighting.
3. **Camera Field of View Boundaries:**
   - When moving items across wide screen distances, moving the right hand outside the camera frame will pause cursor movement. User should utilize comfortable wrist movements rather than reaching outside camera boundaries.

---

## 8. Verification Sign-Off Template (To be completed post physical testing)

```text
Physical Testing Executed By: ___________________________
Date & Time Started:          ___________________________
Date & Time Completed:        ___________________________
Overall Physical Result:      [ ] PASS   [ ] FAIL   [ ] CONDITIONAL PASS
Total Validated Moves:        ___ / 31 assets verified
Premature Drops Encountered:  ___
Stuck Buttons Observed:       ___
Comments / Observations:
_______________________________________________________________________________
_______________________________________________________________________________
```

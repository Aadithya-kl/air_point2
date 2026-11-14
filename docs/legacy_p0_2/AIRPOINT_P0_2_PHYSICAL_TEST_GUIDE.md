# AIRPOINT P0.2 — PHYSICAL WINDOWS VALIDATION GUIDE
**Interactive Desktop Drag-and-Drop Verification Manual**

---

## 1. Overview & Verification Objective

AirPoint P0 and P0.1 rebuilt the core drag-and-drop state machine (`LeftDragController`), input adapter safety (`MouseActuator`), and the real-time debug overlay HUD (`DebugOverlay`). All automated regression suites (378/378 tests) pass.

**Milestone P0.2 is the physical proof:** You will physically operate AirPoint with your hands in front of your webcam, grab real synthetic files in Windows File Explorer, and verify that Windows Explorer physically moves them from `Source\` to `Destination\`.

> [!IMPORTANT]
> **A visual drag animation or ghost cursor outline alone is NOT a successful test.**
> Windows File Explorer may show a floating file icon even if the drop event never committed to the filesystem. A test is considered **PASS** only when `Verify-AirPointP02Sandbox.ps1` confirms:
> 1. The asset physically exists in `Destination\`.
> 2. The asset is absent from `Source\`.
> 3. The SHA-256 cryptographic hash matches the original manifest.
> 
> Every test in this guide must be physically performed by you. All tests in the test report start as `NOT RUN`.

---

## 2. Camera Positioning & Lighting Setup

### Camera Setup & Positioning
- **Placement:** Mount your webcam securely centered on top of your primary monitor, pointing slightly downward toward your chest and desk area.
- **Distance:** Sit **50 cm to 75 cm** (comfortable arm's length) from the camera lens.
- **Field of View:** Ensure that both hands, when raised in front of you at chest/shoulder level, remain entirely within the camera's visual frame. Avoid positioning your hands near the extreme left or right edges of the frame where landmark detection confidence drops.

### Lighting Setup
- **Lighting Direction:** Diffuse, frontal lighting is essential. Light should fall directly on your palms and face.
- **Avoid Backlighting:** Do NOT sit directly in front of a bright window or intense lamp. Backlighting casts hands into dark silhouette, causing MediaPipe HandLandmarker confidence to drop below the tracking threshold (0.50).
- **Background:** Maintain a relatively clean, uncluttered background without other moving persons.

### Windows File Explorer Layout
Before launching AirPoint, position two Windows Explorer windows side by side on your primary screen:
1. **Left Half of Display:** Open `Source\`:
   `C:\Users\loges\AirPoint-Sandbox\Source`
   - Set view mode to **List** or **Details** so each item has a distinct, clickable row target.
2. **Right Half of Display:** Open `Destination\`:
   `C:\Users\loges\AirPoint-Sandbox\Destination`
   - Should be initially empty.

---

## 3. How to Start AirPoint

Open a non-elevated PowerShell terminal (do not run as Administrator, as standard desktop windows use standard user privilege):

```powershell
cd C:\Users\loges\Documents\antigravity\AirPoint\backend
.\.venv\Scripts\python.exe main.py --debug
```

*(The `--debug` flag opens the OpenCV camera preview window with the real-time diagnostic telemetry HUD).*

---

## 4. How to Locate & Read the Debug HUD

The OpenCV debug window titled **`VIRTUAL POINTER`** appears on your desktop. The upper-left corner displays the real-time telemetry panel:

```text
┌──────────────────────────────────────────────────────────┐
│ VIRTUAL POINTER OS v2.0                                  │
├──────────────────────────────────────────────────────────┤
│ FPS       : CAM 30.0 | PROC 29.8                         │
│ SENSOR_R  : TRACKING (ACTIVE) CONF: 0.94                 │
│ SENSOR_L  : TRACKING CONF: 0.91                          │
│ CURSOR WIN: 0960, 0540                                   │
│ DRAG STATE: GRAB_LOCKED (d=0.34/th=0.75) CAND:NO         │
│ DRAG CFG  : EN:YES | DET:YES | LOG:YES | BTN:DOWN | SEND:OK
│ DRAG CURSOR: OWNER:RIGHT | SRC:RIGHT | MOVING:YES        │
└──────────────────────────────────────────────────────────┘
```

### Telemetry Line Definitions

| Field | Meaning | Expected Normal Behavior |
| :--- | :--- | :--- |
| **`FPS`** | Camera capture FPS and inference processing FPS | Both should stay between 28.0 and 32.0. |
| **`SENSOR_R`** | Right-hand detection and landmark tracking confidence | Shows `TRACKING (ACTIVE)` when right hand is in view. |
| **`SENSOR_L`** | Left-hand detection and landmark tracking confidence | Shows `TRACKING` when left hand is in view; `GRACE` during brief dropout. |
| **`CURSOR WIN`** | Desktop pixel coordinates `(X, Y)` mapped from right hand | Follows right index fingertip smoothly. |
| **`DRAG STATE`** | Finite state machine of `LeftDragController` | `READY` → `GRAB_PENDING` → `GRAB_LOCKED` → `RELEASE_PENDING` → `DROP`. |
| **`d=` / `th=`** | Normalized pinch Euclidean distance vs. active threshold | Start threshold `th=0.55`; release threshold `th=0.75`. |
| **`DET`** | Physical presence of left hand | `YES` = visible; `GRACE` = absent < 75ms; `NO` = absent > 75ms. |
| **`LOG`** | Logical actuator drag state in `MouseActuator` | `YES` when mouse button is logically held; `NO` when released. |
| **`BTN`** | Native OS physical button state via `GetAsyncKeyState` | `DOWN` when left button is held; `UP` when idle. |
| **`SEND`** | Return code of the underlying Win32 `SendInput` call | **`OK`** (Confirmed); **`FAIL`** (Error); **`UNCERTAIN`** (Unconfirmed); **`N/A`** (Idle). |
| **`OWNER`** | Pointer owner controlling desktop movement | `RIGHT` (default) or `LEFT` (fallback). |
| **`SRC`** | Active cursor stream coordinate source | Usually `RIGHT`. |
| **`MOVING`** | Real-time motion detection | `YES` when right hand is actively translating. |

---

## 5. Touchless Interaction Procedures

### Step 1: Right-Hand Cursor Movement
- Raise your **Right Hand** with the index finger extended (like pointing at the screen). Keep other fingers relaxed.
- Move your right hand in the air. The Windows mouse cursor will smoothly follow your index fingertip.
- Position the cursor directly over the target file in the `Source` window (e.g. `drag-test-01.txt`).

### Step 2: Left-Hand Grab
- Bring your **Left Hand** into view at chest level.
- **Pinch** your left thumb and index fingertips firmly together.
- Observe the Debug HUD:
  - `DRAG STATE` enters `GRAB_PENDING`, dwells for ~100ms, and locks into `GRAB_LOCKED`.
  - `BTN` transitions from `UP` to `DOWN`.
  - `SEND` displays `OK`.
  - Windows Explorer displays the item selection box / drag ghost.

### Step 3: Move While Holding the Grab
- **Keep your left thumb and index fingertips pinched together.**
- Move your **Right Hand** across the screen toward the `Destination` window.
- The item/ghost follows your cursor smoothly across the desktop.
- The HUD continues to report:
  - `DRAG STATE: GRAB_LOCKED`
  - `BTN: DOWN`
  - `OWNER: RIGHT`
  - `MOVING: YES`

### Step 4: Deliberate Release & Drop
- Once the cursor is positioned over the `Destination` folder window, **deliberately open your left hand** (separate thumb and index finger).
- Observe the Debug HUD:
  - `DRAG STATE` transitions to `DROP`, then returns to `READY`.
  - `BTN` transitions from `DOWN` to `UP`.
  - `SEND` displays `OK`.
  - Windows File Explorer completes the file drop.

---

## 6. How to Verify Actual File Movement

After executing any drag gesture, verify the actual filesystem outcome by opening a second terminal and running:

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\loges\Documents\antigravity\AirPoint\tools\p0_2\Verify-AirPointP02Sandbox.ps1 -SandboxPath "C:\Users\loges\AirPoint-Sandbox"
```

The verification utility will output a table:
- **`MOVED_VERIFIED`**: File arrived in `Destination\`, disappeared from `Source\`, and SHA-256 matches.
- **`STILL_IN_SOURCE`**: Drag was not registered or item was not moved.
- **`COPIED_NOT_MOVED`**: File exists in both folders (Windows copy instead of move).
- **`CORRUPT_HASH_MISMATCH`**: File was truncated or corrupted during move.

To verify a specific single file (e.g. `drag-test-01.txt`):
```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\loges\Documents\antigravity\AirPoint\tools\p0_2\Verify-AirPointP02Sandbox.ps1 -SandboxPath "C:\Users\loges\AirPoint-Sandbox" -TargetAsset "drag-test-01.txt"
```

---

## 7. How to Reset Assets Between Test Runs

When you wish to return moved files from `Destination\` back to `Source\` for another round of testing:

- **Preview Planned Moves (Dry Run):**
  ```powershell
  powershell -ExecutionPolicy Bypass -File C:\Users\loges\Documents\antigravity\AirPoint\tools\p0_2\Reset-AirPointP02Sandbox.ps1 -SandboxPath "C:\Users\loges\AirPoint-Sandbox"
  ```
- **Execute Guaranteed Reset:**
  ```powershell
  powershell -ExecutionPolicy Bypass -File C:\Users\loges\Documents\antigravity\AirPoint\tools\p0_2\Reset-AirPointP02Sandbox.ps1 -SandboxPath "C:\Users\loges\AirPoint-Sandbox" -ConfirmReset
  ```
*This utility moves files back to `Source\`. It checks for file collisions, preserves timestamps, and never deletes files.*

---

## 8. Physical Test Catalog (Tests A through H)

| Test ID | Name | Target Asset | Description & Expected Result |
| :--- | :--- | :--- | :--- |
| **TEST-A** | **Basic Pointer Movement** | Cursor Only | Move right index finger across all 4 screen quadrants without left hand. Cursor moves smoothly; no jumps; `OWNER: RIGHT`. |
| **TEST-B** | **Native Left-Button Grab** | `drag-test-01.txt` | Hover over file, pinch left hand, confirm `BTN: DOWN` and `SEND: OK`. Open pinch; confirm `BTN: UP`. |
| **TEST-C.1** | **Sustained Hold (2s)** | `hold-2s.txt` | Grab file, make continuous right-hand circles for 2.0s, drop into Destination. `BTN: DOWN` sustained throughout. |
| **TEST-C.2** | **Sustained Hold (5s)** | `hold-5s.txt` | Grab file, make continuous right-hand circles for 5.0s, drop into Destination. Ghost follows cursor without release. |
| **TEST-C.3** | **Sustained Hold (10s)** | `hold-10s.txt` | Grab file, circle for 10.0s, drop into Destination. Watchdog does not fire as long as left hand is visible. |
| **TEST-D.1** | **Single File Move** | `drag-test-02.txt` | Drag file from `Source` to `Destination`. Run `Verify-AirPointP02Sandbox.ps1` to confirm `MOVED_VERIFIED`. |
| **TEST-D.2** | **Single Folder Move** | `TestFolder/` | Drag folder from `Source` to `Destination`. Verify folder and inner `test-subfile.txt` arrive intact. |
| **TEST-E** | **20-Cycle Repeated Drag** | `cycle-01.txt` .. `cycle-20.txt` | Sequentially drag 20 individual files from `Source` to `Destination`. Log each iteration in `P0_2_TEST_LOG.csv`. |
| **TEST-F** | **Nested Folder Hierarchy** | `FolderCycle/` | Drag folder containing `file-01.txt` and `file-02.txt`. Confirm full hierarchy and hashes match. |
| **TEST-G.1** | **Hysteresis Jitter Recovery** | `drag-test-01.txt` | During active drag, relax pinch slightly (`d ≈ 0.65`, below `th=0.75`). Verify drag stays locked. |
| **TEST-G.2** | **Tracking Dropout Grace** | `drag-test-01.txt` | During active drag, drop left hand below camera for ~50ms (< 75ms grace). Drag remains locked. |
| **TEST-G.3** | **Sustained Loss Failsafe** | `drag-test-01.txt` | During active drag, completely withdraw left hand (> 75ms). Drag safely releases (`REL: TRACKING_LOSS`). |
| **TEST-H.1** | **Multi-Monitor Boundary** | Desktop item | *(Optional)* Drag asset across virtual desktop monitor boundary. Cursor crosses smoothly while holding button. |
| **TEST-H.2** | **UIPI Privilege Boundary** | Desktop item | *(Optional)* Drag asset into an Administrator window. Windows UIPI security blocks drop; button releases cleanly. |

---

## 9. Emergency Shutdown & Safe Recovery Procedures

If AirPoint behaves unexpectedly or a mouse button remains held:

1. **Normal Graceful Stop:**
   - Press **`Ctrl+Alt+Q`** anywhere in Windows, OR press **`Q`** with the OpenCV debug window focused.
   - The main loop exits, entering the `finally:` block in `main.py`, which calls `actuator.drag_end()` (with retry), restores Windows timer resolution (15.6ms), and restores pointer acceleration.
   - *Technical Limitation:* Software attempts release up to 4 times across normal and shutdown execution paths, but **cannot guarantee release** if Windows UIPI or kernel-level security blocks `SendInput`.

2. **Instant Pause / Freeze:**
   - Press **`Ctrl+Alt+P`** anywhere in Windows.
   - Tracking pauses immediately and `actuator.drag_end()` is called. Press `Ctrl+Alt+P` again to resume.

3. **In-Flight Watchdog (250ms):**
   - Active *only* while the main inference loop is running. If left-hand tracking is lost while in `GRAB_LOCKED`, the 250ms watchdog dispatches native `MOUSEEVENTF_LEFTUP`.
   - *Crucial note:* The watchdog terminates with the Python process and does **NOT** run after shutdown.

4. **Physical Hardware Mouse Click (Status: UNVERIFIED):**
   - Click the left button on your physical hardware mouse. While Windows HID drivers typically dispatch a hardware `WM_LBUTTONUP` on button release, whether this unconditionally overrides an arbitrary synthetic `MOUSEEVENTF_LEFTDOWN` state across all Windows 11 desktop contexts remains **UNVERIFIED**.

5. **Guaranteed Windows NT Kernel Reset (Secure Desktop):**
   - Press **`Ctrl+Alt+Del`** on your physical keyboard.
   - The Windows NT kernel immediately switches display contexts to the Winlogon Secure Desktop (Session 0 isolation), which unconditionally clears all user-mode logical mouse and keyboard capture states. Press **`Esc`** to return to your desktop with a guaranteed clean button state.

6. **Targeted AirPoint Process Termination (Safe Operator Procedure):**
   - If the application ever becomes unresponsive, **NEVER** run `Stop-Process -Name python -Force` as it terminates unrelated Python processes across your machine.
   - Instead, use this verified PID-targeted procedure:
     ```powershell
     # Step A: Identify and verify the exact AirPoint PID and command line
     $airPoint = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | 
         Where-Object { $_.CommandLine -like "*AirPoint\backend\main.py*" }
     $airPoint | Select-Object ProcessId, ExecutablePath, CommandLine | Format-List

     # Step B: Gracefully stop only that verified PID
     if ($airPoint) {
         Stop-Process -Id $airPoint.ProcessId
         Write-Host "Dispatched termination to AirPoint PID $($airPoint.ProcessId)" -ForegroundColor Green
     } else {
         Write-Warning "AirPoint backend process not found."
     }

     # Step C: Forced termination ONLY as a last resort if graceful exit fails
     # Stop-Process -Id $airPoint.ProcessId -Force
     ```

---

## 10. How to Record Failures & Observations

Record every test execution result in:
1. **`AIRPOINT_P0_2_TEST_REPORT.md`**: Fill in the `Actual Result` and `Status` (`PASS` / `FAIL` / `INCONCLUSIVE`).
2. **`C:\Users\loges\AirPoint-Sandbox\P0_2_TEST_LOG.csv`**: Record the following columns for each test:
   - `PinchDist`: The distance reported on HUD `(d=...)`.
   - `FPS`: The frame rate reported on HUD.
   - `BtnState`: `DOWN` or `UP`.
   - `SendResult`: `OK`, `FAIL`, or `UNCERTAIN`.
   - `FileMoved`: `YES` (verified by script) or `NO`.
   - `Notes`: Any premature drops, stuck buttons, or tracking dropout observations.

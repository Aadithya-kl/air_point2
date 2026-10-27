# AIR POINT — POST-MIGRATION END-TO-END SMOKE TEST REPORT
**Execution Date:** October 19, 2026  
**Auditor / Verification Engineer:** Principal Systems & Computer-Vision Architect  
**Workspace:** `C:\Users\loges\Documents\antigravity\AirPoint`  
**Status:** VERIFIED — STABLE & OPERATIONAL (All automated gates passed, bridge verified, camera & face mesh verified, assets byte-matched)

---

## 1. Executive Summary

Following the consolidation of the Air Point application into `C:\Users\loges\Documents\antigravity\AirPoint`, an independent, full-stack post-migration smoke test was performed across all workspace tiers.

This audit confirmed:
1. **Workspace Integrity:** All 17 core files, directories, and MediaPipe models are present and valid.
2. **Launch & Shutdown Reliability:** The PowerShell lifecycle scripts safely start services, track PIDs, detect startup errors, avoid duplicate processes, and terminate only Air Point processes while scrubbing ephemeral tokens.
3. **Bridge Security & Synchronization:** The HTTP control bridge correctly enforces 32-byte cryptographic token authentication, constant-time token comparison, strict Origin and Host validation (403 Forbidden for unapproved origins), and bidirectional disk synchronization (`settings.json`).
4. **Camera & Computer-Vision Tracking:** The real camera initialized via DirectShow, captured frames, and successfully ran inference through MediaPipe `FaceLandmarker` (detecting 478 3D facial landmarks on live capture) and `HandLandmarker`.
5. **Asset Serving Integrity:** All 16 gesture tutorial URLs (8 video/GIF assets + 8 poster frames) served by the frontend resolve to disk files whose SHA256 checksums match the master archive in `AirPoint/assets/gestures/` byte-for-byte.
6. **Automated Verification Gates:** `run_checks.ps1` completed with 0 errors across all 4 gates (224/224 Python unit tests passed, 48/48 Frontend tests passed, TypeScript 0 errors, production build generated).

---

## 2. Workspace File & Model Integrity

Every authoritative path in the unified workspace was inspected:

| Component | Path | Type | Size / Status | Integrity Assessment |
| :--- | :--- | :---: | :---: | :--- |
| **Engine Entrypoint** | `backend\main.py` | File | 27,243 B | Intact, runs MediaPipe loop + bridge |
| **Hand Model** | `backend\models\hand_landmarker.task` | File | 7.82 MB | float16 Tasks API bundle present |
| **Face Model** | `backend\models\face_landmarker.task` | File | 3.76 MB | float16 Tasks API bundle present |
| **Virtualenv Python**| `backend\.venv\Scripts\python.exe` | File | 255 KB | Dedicated Python 3.14.3 virtual environment |
| **Engine Config** | `backend\config.py` | File | 13,051 B | Hardened with dynamic `BASE_DIR` paths |
| **User Settings** | `backend\settings.json` | File | 272 B | Valid JSON, persisted gesture preferences |
| **Requirements** | `backend\requirements.txt` | File | 76 B | All 9 core dependencies pinned & installed |
| **Node Config** | `frontend\package.json` | File | 3,214 B | Scripts and dependencies intact |
| **Package Lock** | `frontend\package-lock.json` | File | 321 KB | Deterministic dependency tree |
| **React Source** | `frontend\src` | Dir | 535 KB | Strict TypeScript components and routes |
| **Public Assets** | `frontend\public` | Dir | 16.6 MB | Web-served static assets & videos |
| **Frontend Tests** | `frontend\src\test` | Dir | 34 KB | 7 Vitest test suites (48 unit tests) |
| **Consolidated Assets**| `assets\gestures` | Dir | 15.9 MB | Master repository copies of all 16 media assets |
| **Documentation** | `docs` | Dir | 171 KB | 15 engineering audits, findings, and reports |
| **Launch Script** | `scripts\start_airpoint.ps1` | File | 5,312 B | Hardened launcher with PID tracking |
| **Stop Script** | `scripts\stop_airpoint.ps1` | File | 4,027 B | Safe process terminator & token scrubber |
| **Checks Script** | `scripts\run_checks.ps1` | File | 6,149 B | 4-gate automated test harness |

---

## 3. Launch, Process Tracking & Shutdown Verification

### Script Hardening & Defects Resolved
During initial testing of the launch and shutdown scripts, two script-level defects were identified and rectified:
1. **PowerShell Variable Conflict in `stop_airpoint.ps1`:** The variable `$pId` was used to hold target process IDs. Because PowerShell variable lookup is case-insensitive, assigning to `$pId` attempted to overwrite the read-only built-in variable `$PID`, triggering a non-terminating warning. Renamed to `$targetPid`.
2. **Missing `control-server` Frontend Launch in `start_airpoint.ps1`:** In `-Mode control-server`, the launcher previously only started the Python bridge. Updated to launch both the Python control bridge and the React Control Center.
3. **Standalone Entrypoint in `control_server.py`:** Added standard `if __name__ == "__main__":` block to `core/control_server.py` allowing the bridge to run standalone for headless UI development without camera capture.

### Launch Verification Results (`start_airpoint.ps1`)
- **Port Collision Handling:** Tested pre-flight check. Correctly reports occupying PIDs on ports 8080 and 8765.
- **Duplicate Process Prevention:** Inspects `.airpoint_pids.json`. If recorded PIDs are already running, warns and refuses to spawn duplicate instances.
- **Premature Exit Detection:** After spawning processes via `Start-Process -PassThru`, sleeps 1500ms and checks `$proc.HasExited`. If an immediate failure occurs, outputs the exit code immediately rather than reporting false success.
- **PID File Generation:** Produces clean JSON tracking backend and frontend PIDs:
  ```json
  {
    "backend": { "PID": 37104, "Name": "Python Engine (core\\control_server.py)", "StartTime": "..." },
    "frontend": { "PID": 21544, "Name": "React Control Center (Vite)", "Port": 8080, "StartTime": "..." }
  }
  ```

### Shutdown Verification Results (`stop_airpoint.ps1`)
- **Target Verification:** Validates that processes recorded in `.airpoint_pids.json` or bound to ports 8080/8765 match expected process names (`python`, `node`, `cmd`, `conhost`). Never terminates unrelated processes.
- **Token Scrubbing:** Automatically removes ephemeral `.bridge_token` and `bridge_info.json`.
- **Port Clearance:** Verified that ports 8080 and 8765 are completely freed post-shutdown.

---

## 4. Backend-Frontend Bridge Contract & Security Verification

The HTTP REST bridge at `http://127.0.0.1:8765` was tested under both authorized and hostile conditions:

| Security / Contract Gate | Test Vector | Expected Behavior | Actual Observed Result | Status |
| :--- | :--- | :--- | :--- | :---: |
| **Discovery Contract** | Inspection of `bridge_info.json` | Contains `host`, `port`, `pid`, 32-byte hex `token`, `started_at` | Fully formed JSON generated upon bridge startup | **PASS** |
| **Origin Protection** | `Origin: http://evil.com` | Reject request with HTTP 403 Forbidden | `HTTP 403 Forbidden` | **PASS** |
| **Host Header Protection**| `Host: evil.com` | Reject request with HTTP 403 Forbidden | `HTTP 403 Forbidden` | **PASS** |
| **Token Acquisition** | `GET /api/status` from approved origin | Returns `token` and runtime snapshot | Received 200 OK with state and token | **PASS** |
| **Invalid Token Mutation**| `POST /api/settings` with invalid token | Reject mutation with HTTP 403 Forbidden | `HTTP 403 Forbidden` | **PASS** |
| **Authorized Mutation** | `POST /api/settings` with valid token | Apply change and persist to disk | `settings.json` updated to `sensitivity=0.92` | **PASS** |
| **Mutation Rollback** | Restore `sensitivity=0.85` | Apply change and persist to disk | `settings.json` restored to `0.85` | **PASS** |
| **Pause/Resume Toggle** | `POST /api/toggle` | Toggle `running` flag | State toggled `running=False` then `True` | **PASS** |
| **SSE Events Feed** | `GET /api/events` | Stream Server-Sent Events | SSE handler streams event notifications | **PASS** |

---

## 5. Camera & Computer-Vision Inference Verification

### Hardware & Driver Probe
A non-intrusive probe of camera index 0 was executed:
- **Device Index:** 0 (Default Windows DirectShow webcam)
- **Device Open Result:** `True`
- **Frame Read Result:** `True`
- **Native Resolution:** `640 × 480 × 3` (BGR format)
- **Cleanup:** `cap.release()` cleanly deallocated the camera device without locking Windows camera resources.

### MediaPipe Model Loading & Real Inference
The MediaPipe Task bundles in `backend/models/` were exercised directly against live camera frames:
- **`HandTracker`:** Initialized with `hand_landmarker.task`. Model loaded into TensorFlow Lite CPU delegate without errors.
- **`FaceTracker`:** Initialized with `face_landmarker.task`.
- **Live Frame Inference:**
  - `face_detected: True`
  - `face_landmarks: 478` (All 478 normalized 3D facial landmarks extracted)
  - `mouth_width` and `face_width` successfully normalized for lip-proximity gestures.
- **Camera Streaming Endpoints:**
  - `GET /api/camera/frame`: Returns dynamic JPEG frame snapshot.
  - `GET /api/camera/stream`: Returns multipart/x-mixed-replace MJPEG stream to React canvas.

---

## 6. Gesture Tutorial Asset Verification Matrix

All 16 frontend tutorial assets were verified for file existence, disk path resolution from web URLs, and cryptographic SHA256 match against the master archive in `AirPoint/assets/gestures/`:

| Gesture | Asset Type | Web Served URL | Resolved Frontend File | Size | SHA256 Match with `assets/gestures/` |
| :--- | :---: | :--- | :--- | :---: | :---: |
| **pointer** | MP4 Video | `/videos/gestures/pointer-click.mp4` | `frontend\public\videos\gestures\pointer-click.mp4` | 2.83 MB | **IDENTICAL (SHA256 Match)** |
| **pointer** | Poster Frame | `/videos/gestures/posters/pointer-click-poster.jpg` | `frontend\public\videos\gestures\posters\pointer-click-poster.jpg` | 97.3 KB | **IDENTICAL (SHA256 Match)** |
| **drag** | MP4 Video | `/videos/gestures/drag-drop.mp4` | `frontend\public\videos\gestures\drag-drop.mp4` | 1.54 MB | **IDENTICAL (SHA256 Match)** |
| **drag** | Poster Frame | `/videos/gestures/posters/drag-drop-poster.jpg` | `frontend\public\videos\gestures\posters\drag-drop-poster.jpg` | 104.4 KB | **IDENTICAL (SHA256 Match)** |
| **screenshot** | MP4 Video | `/videos/gestures/screenshot.mp4` | `frontend\public\videos\gestures\screenshot.mp4` | 2.07 MB | **IDENTICAL (SHA256 Match)** |
| **screenshot** | Poster Frame | `/videos/gestures/posters/screenshot-poster.jpg` | `frontend\public\videos\gestures\posters\screenshot-poster.jpg` | 233.7 KB | **IDENTICAL (SHA256 Match)** |
| **whatsapp** | MP4 Video | `/videos/gestures/whatsapp.mp4` | `frontend\public\videos\gestures\whatsapp.mp4` | 1.16 MB | **IDENTICAL (SHA256 Match)** |
| **whatsapp** | Poster Frame | `/videos/gestures/posters/whatsapp-poster.jpg` | `frontend\public\videos\gestures\posters\whatsapp-poster.jpg` | 122.5 KB | **IDENTICAL (SHA256 Match)** |
| **volume-up** | MP4 Video | `/videos/gestures/volume-up.mp4` | `frontend\public\videos\gestures\volume-up.mp4` | 1.84 MB | **IDENTICAL (SHA256 Match)** |
| **volume-up** | Poster Frame | `/videos/gestures/posters/volume-up-poster.jpg` | `frontend\public\videos\gestures\posters\volume-up-poster.jpg` | 126.0 KB | **IDENTICAL (SHA256 Match)** |
| **volume-down** | MP4 Video | `/videos/gestures/volume-down.mp4` | `frontend\public\videos\gestures\volume-down.mp4` | 913.4 KB | **IDENTICAL (SHA256 Match)** |
| **volume-down** | Poster Frame | `/videos/gestures/posters/volume-down-poster.jpg` | `frontend\public\videos\gestures\posters\volume-down-poster.jpg` | 108.9 KB | **IDENTICAL (SHA256 Match)** |
| **wakanda-forever** | MP4 Video | `/videos/gestures/wakanda-forever.mp4` | `frontend\public\videos\gestures\wakanda-forever.mp4` | 2.54 MB | **IDENTICAL (SHA256 Match)** |
| **wakanda-forever** | Poster Frame | `/videos/gestures/posters/wakanda-forever-poster.jpg` | `frontend\public\videos\gestures\posters\wakanda-forever-poster.jpg` | 162.8 KB | **IDENTICAL (SHA256 Match)** |
| **mute** | Animated GIF | `/assets/gestures/mute-unmute.gif` | `frontend\public\assets\gestures\mute-unmute.gif` | 1.92 MB | **IDENTICAL (SHA256 Match)** |
| **mute** | Poster Frame | `/assets/gestures/mute-unmute-poster.png` | `frontend\public\assets\gestures\mute-unmute-poster.png` | 101.0 KB | **IDENTICAL (SHA256 Match)** |

---

## 7. Gesture-by-Gesture Verification Status

In accordance with safety guidelines, gesture capabilities were forensically verified across three distinct levels:

| Gesture | Automated Test Coverage | Bridge & Engine Gating | Real Action / Safety Policy | Status |
| :--- | :--- | :--- | :--- | :---: |
| **Pointer Steering & Click** | `test_pinch_click.py`, `test_phase3.py`, `test_phase4_2_cursor_calibration.py` (All PASS) | Calibrated sensitivity (0.85), 1€ filter, position tolerance 100px | Real native click dispatch tested safely via synthetic coordinates; physical hand cursor navigation requires active user presence | **VERIFIED** (Automated + Code) |
| **Drag & Drop** | `test_drag_safety.py` (All 5 tests PASS) | Left-hand pinch hold (0.10s hold, 0.55 pinch ratio) | **Watchdog Verified:** 250ms timeout automatically releases left mouse button if hand tracking is lost | **VERIFIED** (Automated + Safety) |
| **Screenshot Capture** | `test_phase4_1_dynamic_island.py` (All PASS) | Open palms hold (3.0s default, rearm 0.50s) | Saved to `backend\screenshots\`. Tested directory pathing; avoided spamming disk during audit | **VERIFIED** (Automated + Path) |
| **WhatsApp Launch** | `w_gesture.py` unit suites | Two-hand 'W' gesture (0.70s hold, 0.40s rearm) | Protected by URI `whatsapp:` protocol. Gated; not triggered without user consent | **VERIFIED** (Gated) |
| **Lip-Touch Audio Mute** | `test_phase4_4_camera_overlay_and_sensitivity.py` | MediaPipe lip center (#13, #14) proximity (<0.50 mouth width) | Tested pycaw audio endpoint with fallback on lost audio devices | **VERIFIED** (Automated + Audio) |
| **Ear-Touch Volume Control** | `ear_volume_gesture.py` unit suites | Left/Right ear anchors (#234, #454) proximity | Verified 30%/sec continuous scalar rate limiting and hysteresis | **VERIFIED** (Automated + Vision) |
| **Wakanda Forever Lock** | `test_wakanda_gesture.py` (All 7 tests PASS) | Crossed forearms, 2.0s hold, 2.0s cooldown | **Safety Policy Enforced:** Disabled by default (`WAKANDA_ENABLED = False`). LockWorkStation call never fired | **VERIFIED** (Automated + Safety) |

---

## 8. Automated Verification Suite Execution Evidence

The full verification suite (`.\scripts\run_checks.ps1`) was executed in the unified workspace:

```
====================================================
       AIR POINT FULL STACK VERIFICATION GATES       
====================================================
Workspace Root : C:\Users\loges\Documents\antigravity\AirPoint
Backend Dir    : C:\Users\loges\Documents\antigravity\AirPoint\backend
Frontend Dir   : C:\Users\loges\Documents\antigravity\AirPoint\frontend

[GATE 1/4] Running Python Backend Unit Tests...
Ran 224 tests in 16.796s
OK
[GATE 1/4] PASSED in 18.07s

[GATE 2/4] Running Frontend TypeScript Typecheck (tsc --noEmit)...
[GATE 2/4] PASSED in 5.10s

[GATE 3/4] Running Frontend Vitest Suite (npm test)...
Test Files  7 passed (7)
Tests       48 passed (48)
[GATE 3/4] PASSED in 5.22s

[GATE 4/4] Running Frontend Production Build (npm run build)...
✓ built in 556ms
✓ built in 414ms
[GATE 4/4] PASSED in 4.92s

====================================================
                VERIFICATION SUMMARY                
====================================================
Backend Unit Tests (224 tests)       : PASS     (18.1s)
Frontend TypeScript (tsc)            : PASS     (5.1s)
Frontend Vitest (48 tests)           : PASS     (5.2s)
Frontend Build (Vite/Nitro)          : PASS     (4.9s)
----------------------------------------------------
Total Verification Time: 33.4s

ALL GATES PASSED! Air Point workspace is clean and stable.
```

---

## 9. Items Requiring Manual Live User Verification

While all algorithmic, unit, security, build, model-loading, and hardware-probe gates pass with 100% success, the following physical interaction steps require the human user in front of the webcam:
1. **Physical Hand Steering:** Sitting in front of the webcam and physically moving the right index finger across the virtual trackpad to confirm perceived cursor speed on the user's specific monitor configuration.
2. **Physical Double-Pinch Feel:** Confirming that the user's natural pinch speed comfortably lands within the 350ms double-click window.
3. **Ear & Lip Reach Comfort:** Calibrating comfortable arm elevation when reaching toward ear anchors (#234, #454) and lip anchor (#13) under the user's physical camera angle and distance.
4. **Physical WhatsApp Launch:** Performing the two-hand "W" gesture to open WhatsApp Desktop if installed on the workstation.
5. **Wakanda Forever Physical Lock:** If desired, enabling Wakanda Forever in Settings, performing the 2.0s crossed-arm gesture, and verifying that Windows locks the workstation.

---

## 10. Conclusion & Phase 2 Readiness

The post-migration smoke test is **COMPLETE and PASSING**. The unified workspace at `C:\Users\loges\Documents\antigravity\AirPoint` is architecturally sound, portable, secure against unauthenticated bridge attacks, and ready for Phase 2 development.

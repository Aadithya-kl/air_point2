# Air Point — Unified Workspace

An AI-driven, touchless desktop interaction engine for Windows. Air Point tracks hand and face landmarks via MediaPipe to deliver cursor tracking, gesture-based OS controls (pinch-click, drag, double-tap, continuous ear-touch volume, lip-touch mute, screenshot, WhatsApp launch, and crossed-arm screen lock), paired with a Nothing OS × macOS translucent React Control Center.

---

## 1. Workspace Layout

The Air Point project is organized as a self-contained, portable multi-tier workspace:

```
AirPoint/
├── backend/                       # Python Computer-Vision Engine & Control Server
│   ├── core/                      # Core modules (tracking, actuator, filter, gestures, bridge)
│   │   ├── gestures/              # Gesture recognizers (ear_volume, lip_mute, wakanda, etc.)
│   │   ├── actuator.py            # Windows input synthesis (mouse, keyboard, volume, lock)
│   │   ├── camera.py              # DirectShow high-FPS camera capture
│   │   ├── control_server.py      # HTTP control bridge with token authentication
│   │   ├── debug_overlay.py       # High-contrast visual feedback HUD
│   │   ├── face_tracker.py        # MediaPipe Face Landmarker (lip & ear gestures)
│   │   ├── filter.py              # Adaptive 1€ filter for jitter reduction
│   │   ├── overlay.py             # Transparent Windows feedback overlays
│   │   └── tracker.py             # MediaPipe Hand Landmarker integration
│   ├── models/                    # MediaPipe Task Bundles (.task)
│   │   ├── hand_landmarker.task   # Hand tracking model
│   │   └── face_landmarker.task   # Face tracking model
│   ├── test_*.py                  # Complete Python test suite (420 unit & regression tests)
│   ├── config.py                  # Authoritative system configuration & thresholds
│   ├── main.py                    # Gesture engine entrypoint
│   ├── settings.json              # User settings & gesture toggles
│   └── requirements.txt           # Python dependencies
│
├── frontend/                      # React Control Center UI
│   ├── src/                       # TypeScript / React application source
│   │   ├── components/            # UI components (Nothing Glass cards, video players, HUD)
│   │   ├── routes/                # TanStack Start file-based routing
│   │   └── test/                  # Vitest suite (135 tests across 14 test files)
│   ├── public/                    # Static assets & web-accessible gesture tutorials
│   │   ├── assets/gestures/       # Mute tutorial GIF & poster
│   │   └── videos/gestures/       # 7 gesture tutorial MP4 videos & posters
│   ├── package.json               # Node dependencies & test scripts
│   └── vite.config.ts             # Vite / Nitro build configuration
│
├── assets/                        # Consolidated Centralized Assets
│   └── gestures/                  # Master copies of all 8 gesture tutorials & posters
│       ├── mute-unmute.gif / .png
│       ├── pointer-click.mp4 / .png
│       ├── drag-drop.mp4 / .png
│       ├── screenshot.mp4 / .png
│       ├── whatsapp.mp4 / .png
│       ├── volume-up.mp4 / .png
│       ├── volume-down.mp4 / .png
│       └── wakanda-forever.mp4 / .png
│
├── docs/                          # Architecture & Audit Documentation
│   ├── AIR_POINT_MASTER_ENGINEERING_AUDIT.md
│   ├── AIR_POINT_AUDIT_FINDINGS.json
│   ├── AIR_POINT_PHASE1_REMEDIATION_REPORT.md
│   └── AIR_POINT_WORKSPACE_MIGRATION_REPORT.md
│
├── scripts/                       # PowerShell Automation Scripts
│   ├── start_airpoint.ps1         # Unified launcher: prerequisites, ports, health, PID record, logs
│   ├── stop_airpoint.ps1          # Graceful engine exit via the bridge; stops own processes only
│   └── run_checks.ps1             # Full-stack verification test runner (4 gates)
├── tools/physical_sandbox/        # Disposable Explorer sandbox for physical drag tests (manifest + verify + reset)
├── docs/legacy_p0_2/              # Historical P0.2 reports migrated from the legacy checkout
│
├── .gitignore                     # Workspace-level Git ignore rules
└── README.md                      # This documentation
```

---

## 2. Prerequisites & Environment Setup

### System Requirements
- **OS:** Windows 10 / Windows 11 (64-bit)
- **Webcam:** 720p or 1080p webcam (60 FPS recommended; 30 FPS minimum)
- **Python:** Python 3.10 – 3.14 (tested on Python 3.14.3)
- **Node.js:** Node.js 18+ (tested on Node.js v24.14.0, npm 11.9.0)

### Backend Setup (Python)
1. Navigate to the backend directory:
   ```powershell
   cd AirPoint\backend
   ```
2. Create and activate a virtual environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
3. Install required Python packages:
   ```powershell
   pip install -r requirements.txt
   ```

### Frontend Setup (React / Node)
1. Navigate to the frontend directory:
   ```powershell
   cd AirPoint\frontend
   ```
2. Install dependencies (if not pre-installed):
   ```powershell
   npm install
   ```

---

## 3. Running Air Point

### Option A: Using the Unified PowerShell Launcher (Recommended)
From the repository root:
```powershell
# Start the Python engine and the React Control Center, verify both, record their PIDs
.\scripts\start_airpoint.ps1 -Mode full

# Same, with the OpenCV debug HUD (drag diagnostics) enabled
.\scripts\start_airpoint.ps1 -Mode full -DebugHud

# Check prerequisites, ports and the exact commands without starting anything
.\scripts\start_airpoint.ps1 -Mode full -DryRun

# Other modes
.\scripts\start_airpoint.ps1 -Mode control-server   # bridge only + Control Center
.\scripts\start_airpoint.ps1 -Mode frontend-only
.\scripts\start_airpoint.ps1 -Mode backend-only
```
The launcher resolves the repository root from its own location, requires `backend\.venv`, checks Python imports, model bundles, Node, npm and `node_modules`, refuses busy ports (reporting the owner) and a second instance, waits for the bridge (`backend\bridge_info.json` + `GET /api/status`) and for the dev server (HTTP 200), passes the discovered bridge URL to the Control Center (`VITE_AIRPOINT_BRIDGE_URL`), and writes `.airpoint\airpoint_pids.json` plus `logs\backend_*.log` / `logs\frontend_*.log`. If one service fails, whatever was already started is stopped again. Once started, open **`http://localhost:8080`**.

To stop Air Point (graceful engine exit through the authenticated bridge, then only the processes the launcher started):
```powershell
.\scripts\stop_airpoint.ps1
# add -IncludeOrphans to also stop AirPoint processes started by hand from this repository
```
The stop script never terminates unrelated `python.exe` or `node.exe` processes.

### Option B: Manual Execution

**1. Launch the Backend:**
```powershell
cd AirPoint\backend
.\.venv\Scripts\python.exe main.py
# Or run just the HTTP control server bridge:
# .\.venv\Scripts\python.exe core\control_server.py
```

**2. Launch the Frontend:**
```powershell
cd AirPoint\frontend
npm run dev -- --port 8080
```

---

## 4. Verification & Testing

To run the complete full-stack verification suite in one command:
```powershell
.\scripts\run_checks.ps1
```

This executes 4 automated gates:
1. **Python Unit Tests:** 471 unit tests covering gesture detection, filters, actuators, drag reliability, audio controls, the Dyne event system and the HTTP bridge. They run with the OS-action guard enabled (`AIRPOINT_ENABLE_TEST_GUARD=1`), which blocks real mouse/keyboard injection, workstation lock, application launches and camera opens.
2. **Frontend TypeScript Check:** `npx tsc --noEmit` verifies strict types across all routes and components.
3. **Frontend Vitest Suite:** 144 unit tests verifying gesture video players, recent activity feeds, theme providers, Dyne Studio, the live Dyne island and engine context.
4. **Frontend Production Build:** `npm run build` compiles client and server Nitro bundles.

### Running Gates Individually:
- **Python Tests:**
  ```powershell
  cd AirPoint\backend
  $env:AIRPOINT_SETTINGS_PATH = ":memory:"
  $env:AIRPOINT_ENABLE_TEST_GUARD = "1"
  $env:AIRPOINT_DISABLE_REAL_LOCK = "1"
  .\.venv\Scripts\python.exe -m unittest discover -s . -p "test_*.py"
  ```
- **TypeScript Typecheck:**
  ```powershell
  cd AirPoint\frontend
  npx tsc --noEmit
  ```
- **Frontend Vitest:**
  ```powershell
  cd AirPoint\frontend
  npm test
  ```
- **Frontend Build:**
  ```powershell
  cd AirPoint\frontend
  npm run build
  ```

---

## 5. Security & Bridge Architecture

The React Control Center communicates with the Python engine over a local HTTP REST bridge with strict security protections:
- **Ephemeral Token Authentication:** The Python server generates a cryptographic 32-byte hex token upon startup, persisted to `backend/.bridge_token` and `backend/bridge_info.json`. Mutating requests require the matching `X-AirPoint-Token` header.
- **Constant-Time Comparison:** All token comparisons use `secrets.compare_digest` to prevent timing attacks.
- **Origin & Host Protection:** The server rejects any HTTP request whose `Host` or `Origin` header points outside `localhost` or `127.0.0.1`.
- **Port Handling:** The engine binds `127.0.0.1:8765` and refuses to start if the port is taken (set `AIRPOINT_PORT_FALLBACK=1`, or pass `-AllowPortFallback` to the launcher, to bind a free loopback port instead; the assigned port is written to `bridge_info.json`). The launcher reads that file and passes the bridge origin to the Control Center as `VITE_AIRPOINT_BRIDGE_URL`; only loopback `http://` origins are accepted, anything else falls back to `http://127.0.0.1:8765`. A dev server started by hand without the variable uses the default port.
- **Events:** every notification is one Dyne event (`backend/core/events.py`) with an id, a session token, a type, a priority and a duration; `GET /api/events` streams them with `id:` lines (reconnecting clients send `Last-Event-ID` and missed events are replayed), `GET /api/events/history` returns the bounded ring, and the same events drive the desktop capsule and the Control Center's live island.
- **Drag Safety:** A held left button is released when the left hand is lost for more than 0.15 s, and by the gesture loop's watchdog if the drag controller stops refreshing it for 0.25 s. Native input results are reported as CONFIRMED / UNCONFIRMED / FAILED; a release that cannot be confirmed is retried (bounded) on pause and shutdown and surfaced in `GET /api/status` under `drag`, never reported as success.

---

## 6. Troubleshooting

- **Port 8080 or 8765 Already in Use:**
  The launcher names the owning process. If it is an AirPoint process from this repository run `.\scripts\stop_airpoint.ps1 -IncludeOrphans`; otherwise free the port or pass `-FrontendPort` / `-BackendPort`. You can also inspect occupying PIDs with:
  ```powershell
  Get-NetTCPConnection -LocalPort 8080, 8765 -State Listen
  ```
- **Launcher says the backend did not answer:** read the newest `logs\backend_*.err.log`; the usual causes are a missing camera, a missing model bundle, or a port collision (the launcher checks the port first, but another process may have taken it in between).
- **MediaPipe Model Not Found:**
  In `AirPoint\backend\config.py`, all model paths resolve dynamically using `Path(__file__).resolve().parent`. Ensure `backend\models\hand_landmarker.task` and `backend\models\face_landmarker.task` are present.
- **Audio Gesture Warnings (pycaw):**
  If testing in a headless environment without an active audio endpoint, pycaw may report `Device lost` or `No audio endpoint found`. This is normal and handled safely by the engine without crashing.
- **Webcam Access Denied:**
  Ensure Windows Settings > Privacy & Security > Camera allows desktop apps to access the camera.

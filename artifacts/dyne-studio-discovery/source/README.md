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
│   ├── test_*.py                  # Complete Python test suite (224 unit & regression tests)
│   ├── config.py                  # Authoritative system configuration & thresholds
│   ├── main.py                    # Gesture engine entrypoint
│   ├── settings.json              # User settings & gesture toggles
│   └── requirements.txt           # Python dependencies
│
├── frontend/                      # React Control Center UI
│   ├── src/                       # TypeScript / React application source
│   │   ├── components/            # UI components (Nothing Glass cards, video players, HUD)
│   │   ├── routes/                # TanStack Start file-based routing
│   │   └── test/                  # Vitest suite (48 tests across 7 test files)
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
│   ├── start_airpoint.ps1         # Launches backend + frontend with PID tracking
│   ├── stop_airpoint.ps1          # Gracefully terminates all services & cleans tokens
│   └── run_checks.ps1             # Full-stack verification test runner (4 gates)
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

### Option A: Using the Automated PowerShell Launcher (Recommended)
From the `AirPoint` root directory:
```powershell
# Start both Python backend and React frontend
.\scripts\start_airpoint.ps1

# Start in control-server-only mode (lightweight bridge + frontend)
.\scripts\start_airpoint.ps1 -Mode control-server

# Start only the frontend or only the backend
.\scripts\start_airpoint.ps1 -Mode frontend-only
.\scripts\start_airpoint.ps1 -Mode backend-only
```
Once started, open your browser at **`http://localhost:8080`**.

To cleanly stop all Air Point services and clean up bridge tokens:
```powershell
.\scripts\stop_airpoint.ps1
```

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
1. **Python Unit Tests:** 224 unit tests covering gesture detection, filters, actuators, audio controls, and the HTTP bridge.
2. **Frontend TypeScript Check:** `npx tsc --noEmit` verifies strict types across all routes and components.
3. **Frontend Vitest Suite:** 48 unit tests verifying gesture video players, recent activity feeds, theme providers, and engine context.
4. **Frontend Production Build:** `npm run build` compiles client and server Nitro bundles.

### Running Gates Individually:
- **Python Tests:**
  ```powershell
  cd AirPoint\backend
  .\.venv\Scripts\python.exe -m unittest discover -p "test_*.py"
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
- **Dynamic Port Negotiation:** If the default port (8765) is bound, the server dynamically binds to a free loopback port and writes the assigned port to `bridge_info.json`. The React frontend reads this file to connect seamlessly.
- **Drag Safety Watchdog:** A background safety thread monitors active mouse drag operations and automatically releases the left mouse button if hand tracking is lost for >0.25 seconds, preventing cursor lockup.

---

## 6. Troubleshooting

- **Port 8080 or 8765 Already in Use:**
  Run `.\scripts\stop_airpoint.ps1` to terminate lingering processes. You can also inspect occupying PIDs with:
  ```powershell
  Get-NetTCPConnection -LocalPort 8080, 8765 -State Listen
  ```
- **MediaPipe Model Not Found:**
  In `AirPoint\backend\config.py`, all model paths resolve dynamically using `Path(__file__).resolve().parent`. Ensure `backend\models\hand_landmarker.task` and `backend\models\face_landmarker.task` are present.
- **Audio Gesture Warnings (pycaw):**
  If testing in a headless environment without an active audio endpoint, pycaw may report `Device lost` or `No audio endpoint found`. This is normal and handled safely by the engine without crashing.
- **Webcam Access Denied:**
  Ensure Windows Settings > Privacy & Security > Camera allows desktop apps to access the camera.

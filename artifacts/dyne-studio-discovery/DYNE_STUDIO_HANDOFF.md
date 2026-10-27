# AIRPOINT / DYNE STUDIO — ENGINEERING HANDOFF & ARCHITECTURAL DISCOVERY

> **Status:** Discovery & Read-Only Audit Complete  
> **Target Feature:** Dyne Studio (Layered Mechanical Fin HUD Editor for AirPoint Desktop HUD "Dyne")  
> **Workspace Root:** `C:\Users\loges\Documents\antigravity\AirPoint`  
> **Document Purpose:** Definitive technical reference and implementation roadmap for engineering Dyne Studio without guessing or breaking existing functionality.

---

## 1. REPOSITORY IDENTITY & WORKING ENVIRONMENT

### 1.1 Repository Structure & Git Identity
- **Active Workspace Directory:** `C:\Users\loges\Documents\antigravity\AirPoint`
- **Related Git Repositories:**
  - `C:\Users\loges\Documents\antigravity\air_point_clean`: Branch `main`, HEAD commit `1297bf2f61aefa2709cb4cb4277e75df64d41c7d` (`feat: implement Phase 7 Dynamic Island HUD and Phase 7.1 volume visualizer`).
  - `C:\Users\loges\Documents\antigravity\keen-carson`: Branch `master`, HEAD commit `e12d3aadeaffc32f75e6bf005a06c4a36b535be8`.
  - Primary working directory `C:\Users\loges\Documents\antigravity\AirPoint` contains the unified monorepo-style structure combining `frontend/`, `backend/`, `assets/`, `docs/`, and `scripts/`.
- **Framework & Package Stack:**
  - **Frontend:**
    - React 19.2.0 (`frontend/package.json#L61`)
    - TanStack Start 1.168.60 (`frontend/package.json#L52`)
    - TanStack Router 1.170.41 (`frontend/package.json#L51`)
    - Vite 8.1.5 (`frontend/package.json#L95`)
    - Tailwind CSS v4.2.1 (`frontend/package.json#L69`, `@tailwindcss/vite: ^4.2.1`)
    - Radix UI Primitives (`@radix-ui/react-switch`, `@radix-ui/react-slider`, etc.)
    - Lucide React 0.575.0 (`frontend/package.json#L60`)
    - Vitest 4.1.10 (`frontend/package.json#L96`) + Testing Library React 16.0.0
  - **Backend:**
    - Python 3.12 (virtual environment at `backend/.venv/Scripts/python.exe`)
    - MediaPipe 0.10.14 hand/face tracking
    - Zero-dependency built-in `http.server` & SSE server (`backend/core/control_server.py`)
    - Native Win32 desktop overlay HUD using Tkinter + `ctypes.windll.user32` (`backend/core/overlay.py`)
    - Inactivity & power state machine (`backend/core/power_state_machine.py`)
    - Persisted configuration store (`backend/settings.json`)

---

## 2. EXISTING HUD ROUTE & COMPONENT TREE

### 2.1 Current Route Hierarchy
- **Route Definition:** `frontend/src/routes/island.tsx` mounted at path `/island`.
- **Navigation Shell:** `frontend/src/components/air-point/shell.tsx#L162-L168` exposes the "Dynamic Island" navigation tab with Lucide `<Sparkles>` icon.
- **Root Layout:** `frontend/src/routes/__root.tsx` wraps routes in `AirPointEngineProvider` and `DesktopShell`.

### 2.2 Component Hierarchy of Current HUD Page
```text
frontend/src/routes/island.tsx (DynamicIslandPage)
├── Header & Mode Badges (Lines 178-191)
├── Main Preview Grid (Lines 194-465)
│   ├── Left Column (Col-Span 2):
│   │   ├── Section A: Futuristic 3D Interactive Capsule Stage (Lines 215-234)
│   │   │   └── CapsuleStage (frontend/src/components/air-point/capsule/CapsuleStage.tsx)
│   │   │       ├── Volumetric Lighting Rigs (Left Cyan & Right Violet blurs)
│   │   │       ├── 3D Perspective Viewport (perspective: 1200px, preserve-3d)
│   │   │       ├── MechanicalFin (left, orientation="left") (MechanicalFin.tsx)
│   │   │       ├── CapsuleBody (state, accent, label, sublabel, badge) (CapsuleBody.tsx)
│   │   │       ├── MechanicalFin (right, orientation="right") (MechanicalFin.tsx)
│   │   │       └── Stage Projection Layer (children)
│   │   ├── Section B: Classic 2D Desktop HUD Pill (Lines 236-265)
│   │   │   └── DynamicIslandPreview (frontend/src/components/air-point/dynamic-island.tsx)
│   │   ├── Simulation State Buttons (Lines 267-356)
│   │   │   ├── Normal Mode
│   │   │   ├── Waiting for Inactivity
│   │   │   ├── Power Saver Mode
│   │   │   ├── Countdown Complete
│   │   │   ├── Hand Detected / Wake
│   │   │   └── Full Lifecycle Demo (Automated sequence)
│   │   └── Real Desktop Overlay Test Trigger (Lines 358-380)
│   │       └── button[data-testid="test-countdown-btn"] -> testDesktopCountdown(5.0)
│   └── Right Column (Col-Span 1): Real Desktop Overlay Status (Lines 384-464)
│       ├── HUD Overlay: ACTIVE (Win32) / DISABLED
│       ├── Bridge: ONLINE (8765) / OFFLINE
│       ├── Engine State: NORMAL / POWER SAVE
│       └── Power Saver: ENABLED / OFF
└── Section C: Dynamic Island Settings Grid (Lines 467-697)
    ├── Reset Defaults Button (Lines 478-496)
    ├── 4 Switches Grid (Lines 498-592):
    │   ├── Show HUD (id="toggle-island-enabled")
    │   ├── Notifications (id="toggle-island-notifications")
    │   ├── Countdown (id="toggle-island-timer")
    │   └── Auto-hide (id="toggle-island-autohide")
    ├── HUD Duration Slider & Presets (Lines 594-666):
    │   ├── Slider: 10s to 1800s (Default: 120s / 2 min)
    │   └── Preset buttons: 30s, 1m, 2m, 5m, 10m
    └── Completion Message Duration Buttons (Lines 668-696):
        └── 1.0s, 1.5s, 2.0s (Default), 3.0s, 5.0s
```

---

## 3. REAL SETTINGS INVENTORY & DATA FLOW

Every HUD setting is defined across frontend models, engine synchronization, backend server models, and native overlay rendering.

### 3.1 Settings Matrix

| Setting Identifier | UI Label & Default | Frontend Type & Limit | Backend Key & Storage | Host Endpoint | Native Win32 Reflection | Read/Write Status | Relevant Tests |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **HUD Enabled** | `Show HUD` (`true`) | `boolean` (`air-point-model.ts#L110`) | `island_enabled` (`backend/settings.json#L16`) | `POST /api/settings` (`{ island_enabled: bool }`) | Direct: Calls `overlay.configure(island_enabled=...)`. If `false`, hides window (`overlay.py#L1066-L1074`). | Read-Write | `dynamic-island-tab.test.tsx#L101-L125`, `test_control_server.py` |
| **Notifications** | `Notifications` (`true`) | `boolean` (`air-point-model.ts#L111`) | `island_notifications_enabled` (`backend/settings.json#L17`) | `POST /api/settings` (`{ island_notifications_enabled: bool }`) | Direct: Guards `show_normal_mode`, `show_power_saver_enabled_waiting`, `start_power_save_countdown`, `show_wake_confirmed` (`overlay.py#L1101, L1129, L1159`). | Read-Write | `dynamic-island-tab.test.tsx#L127-L148`, `test_control_server.py` |
| **Countdown On/Off**| `Countdown` (`true`) | `boolean` (`air-point-model.ts#L112`) | `island_timer_enabled` (`backend/settings.json#L18`) | `POST /api/settings` (`{ island_timer_enabled: bool }`) | Direct: When `false`, suppresses `MM:SS` badge pill on overlay, leaving clean bar or minimal pill (`overlay.py#L665-L672, L1182`). | Read-Write | `dynamic-island-tab.test.tsx#L150-L170`, `test_phase4_1_dynamic_island.py` |
| **Auto-hide** | `Auto-hide` (`true`) | `boolean` (`air-point-model.ts#L113`) | `island_autohide_enabled` (`backend/settings.json#L19`) | `POST /api/settings` (`{ island_autohide_enabled: bool }`) | Direct: When `true`, retracts toast after `_toast_until` deadline expires (`overlay.py#L657-L661`). If `false`, stays pinned. | Read-Write | `dynamic-island-tab.test.tsx#L172-L195`, `test_control_server.py` |
| **HUD Duration** | `HUD duration` (`120s` / 2 min) | `number` (Min: 10s, Max: 1800s, Step: 10s) (`air-point-model.ts#L127-L132`) | `island_hud_duration_s` (`backend/settings.json#L20`) | `POST /api/settings` (`{ island_hud_duration_s: float }`) | Direct: Sets inactivity countdown span `_ps_duration` and deadline in `start_power_save_countdown` (`overlay.py#L1081, L1161-L1169`). | Read-Write | `dynamic-island-tab.test.tsx#L197-L230`, `test_phase4_1_dynamic_island.py` |
| **Completion Duration**| `Completion message duration` (`2.0s`) | `number` (Min: 1.0s, Max: 5.0s, Step: 0.5s) (`air-point-model.ts#L133-L137`) | `island_completion_duration_s` (`backend/settings.json#L21`) | `POST /api/settings` (`{ island_completion_duration_s: float }`) | Direct: Duration for which `"POWER SAVER · HIDING"` toast remains visible before retracting (`overlay.py#L685, L1083`). | Read-Write | `dynamic-island-tab.test.tsx#L232-L260`, `test_control_server.py` |
| **Test Countdown** | `Real Desktop Overlay Test` | None (Action trigger) | Ephemeral runtime only | `POST /api/control` (`{ action: "test_countdown", duration: 5.0 }`) | Direct: Invokes `overlay.start_test_countdown(5.0)` without altering `PowerStateManager` (`overlay.py#L1190-L1224`). | Write-Only Action | `dynamic-island-tab.test.tsx#L262-L290`, `test_control_server.py` |

---

## 4. LIFECYCLE & RUNTIME CONTRACT

### 4.1 State Distribution: Engine vs. HUD Overlay
A critical architectural boundary exists between **Engine Power State** and **HUD Overlay Presentation**:
- **Engine State (`backend/core/power_state_machine.py`):**
  - Only two pure states: `NORMAL` (30-60 FPS camera, full inference) and `POWER_SAVE` (2 Hz probe cadence, tracking suspended).
  - Transition events: `ENTERED_POWER_SAVE`, `WAKE_CONFIRMED`, `WAKE_REJECTED`, `FEATURE_DISABLED`.
- **HUD Presentation State (`backend/core/overlay.py`):**
  - Manages presentation states: `IDLE`, `DROPPING`, `HOLDING`, `SUCCESS`, `ERROR`, `STATUS`, `RETRACTING`.
  - Specific presentation modes:
    1. **Normal:** `"AIR POINT · NORMAL"` toast displayed on user interaction or wake.
    2. **Waiting:** `"POWER SAVER · WAITING"` toast displayed when Power Saver is toggled ON but inactivity timeout has not elapsed.
    3. **Countdown:** `"POWER SAVER"` capsule with active `MM:SS` countdown badge and progress bar.
    4. **Hiding / Completion:** `"POWER SAVER · HIDING"` completion toast displayed for `completion_duration_s` before retracting.
    5. **Retracted / Hidden:** Win32 overlay hidden with `y = -h - 10` while the Python engine remains in `POWER_SAVE` 2 Hz probe mode.
    6. **Wake:** `"HAND DETECTED · NORMAL"` displayed when a hand re-enters the camera view.
    7. **Offline:** Control Center displays `ONLINE (8765)` or `OFFLINE` based on `/api/status` polling heartbeat failure.

### 4.2 Network & Communication Protocol
- **Transport:** HTTP REST + Server-Sent Events (SSE) on `http://127.0.0.1:8765`.
- **Authentication:** Token-based header `X-AirPoint-Token` generated at launch in `backend/.bridge_token` (`control_server.py#L529-L539`).
- **Telemetry Polling:** `GET /api/status` polled every 1500ms (`engine.tsx#L368-L372`).
- **Event Streaming:** `GET /api/events` provides real-time SSE stream (`engine.tsx#L374-L409`).
- **Settings Mutation:** `POST /api/settings` accepts JSON dictionary and returns updated settings (`control_server.py#L713-L725`).
- **Runtime Control:** `POST /api/control` handles `stop`, `start`, `toggle`, and `test_countdown` (`control_server.py#L746-L777`).

---

## 5. DESIGN TOKENS & VISUAL SPECIFICATION

### 5.1 Design Tokens (`frontend/src/styles.css`)
- **Theme Palette:** Nothing Glass V2 (`styles.css#L17-L150`)
  - Obsidian (Dark default): `--bg-page: #0f1013`, `--window-bg: rgba(20, 22, 28, 0.74)`
  - Titanium (Light porcelain): `--bg-page: #E8E7E3`, `--window-bg: rgba(255, 255, 255, 0.62)`
- **Capsule 3D Custom Properties (`styles.css#L2431-L2488`):**
  - `--capsule-chassis-bg: #090a0f`
  - `--capsule-chassis-surface: #11131a`
  - `--capsule-chassis-elevated: #181b26`
  - `--capsule-titanium-rim: rgba(255, 255, 255, 0.16)`
  - `--capsule-titanium-bevel: rgba(255, 255, 255, 0.28)`
  - `--capsule-accent-cyan: #22d3ee` (Glow: `rgba(34, 211, 238, 0.38)`)
  - `--capsule-accent-violet: #a876ff` (Glow: `rgba(168, 118, 255, 0.38)`)
  - `--capsule-accent-amber: #fbbf24` (Glow: `rgba(251, 191, 36, 0.38)`)
  - `--capsule-accent-emerald: #34d399` (Glow: `rgba(52, 211, 153, 0.38)`)
  - `--capsule-perspective: 1200px`
  - `--capsule-duration: 400ms`
  - `--capsule-ease-spring: cubic-bezier(0.16, 1, 0.3, 1)`
- **Mechanical Fin Kinematics (`styles.css#L2555-L2612`):**
  - Class `.mechanical-fin-root`: `transform-style: preserve-3d; will-change: transform;`
  - Transition: `transform 400ms cubic-bezier(0.16, 1, 0.3, 1)`
  - Wake Overshoot: `@keyframes fin-wake-overshoot-left / right` (600ms)
  - Accessibility: Full `@media (prefers-reduced-motion: reduce)` and `html[data-reduced-motion="true"]` overrides.

---

## 6. DYNE STUDIO: INTERACTION MODEL & 8-FIN ARCHITECTURE

### 6.1 The Intended Interaction Concept
Based on the design reference and user specification:
1. **Initial Rest State:**
   - A clean, unadorned Dyne capsule rests on a dedicated desktop preview stage plinth.
   - Shows live preview posture (Normal, Eco, or Armed).
2. **Layer 1 Unfold (Double-Click Gesture):**
   - Double-clicking the central capsule chassis unfolds **8 primary mechanical fins** radially around the capsule.
   - These 8 fins serve as the **primary category navigation surface**, replacing flat settings cards.
   - Proposed Category Fins (derived from existing settings + extensibility):
     1. **`HUD / Visibility`** (Controls Show HUD, Auto-hide, persistent display)
     2. **`Notifications`** (Mode toasts, status badges, volume visualizer)
     3. **`Time / Timer`** (Countdown toggle, HUD duration slider, completion time)
     4. **`Colour / Accent`** (Obsidian, Cyan, Violet, Dual, Eco Amber)
     5. **`Motion / Dynamics`** (Spring tension, deployment angles, reduced motion)
     6. **`Presets / Modes`** (Desktop Native mode vs Concept Studio mode)
     7. **`Position / Notch`** (Top Center, screen margins, offset)
     8. **`Diagnostics / Test`** (Trigger 5s desktop countdown, test toasts)
3. **Layer 2 Expansion (Fin Selection):**
   - Clicking any of the 8 primary fins expands a secondary ring/layer of option petals or adjustment controls around the selected fin.
   - The primary fins remain visible in a dimmed/recessed state to provide visual context and easy switching.
4. **Layer 3 Deeper Customization (Sub-options):**
   - For complex categories (e.g., `Time`), clicking an option (e.g., `HUD Duration`) reveals granular presets (`30s`, `1m`, `2m`, `5m`) or an arc-slider.
5. **Instant Live Preview:**
   - Every selection instantly updates the preview stage capsule and mechanical fins.
   - Selected options display a distinct cyan/violet illumination state.
6. **Smooth Dismissal & Reversal:**
   - Clicking the active fin again, clicking outside the capsule in the viewport, or pressing **Escape** smoothly folds layers back in reverse order (Layer 3 -> Layer 2 -> Layer 1 -> Folded).
7. **Dual Operating Modes:**
   - **Desktop Mode:** Exclusively reflects settings and visual behaviors supported by the real Win32 Tkinter overlay (`overlay.py`). Changes synchronize live to the Python engine.
   - **Concept Mode:** Unlocks extended visual experimentation (custom fin geometries, particle lighting, extreme angles) without sending invalid configs to the host.

### 6.2 Radial Fin Geometry & Mathematical Layout
For an 8-fin radial layout around a central rounded capsule of dimensions $W \times H$ (approx $360\text{px} \times 64\text{px}$):
- Let index $k \in \{0, 1, \dots, 7\}$ denote the 8 fin positions:
  - Fin 0: Top-Left North-West ($\theta_0 \approx -135^\circ$)
  - Fin 1: Top-Center North ($\theta_1 \approx -90^\circ$)
  - Fin 2: Top-Right North-East ($\theta_2 \approx -45^\circ$)
  - Fin 3: Right Lateral East ($\theta_3 \approx 0^\circ$)
  - Fin 4: Bottom-Right South-East ($\theta_4 \approx 45^\circ$)
  - Fin 5: Bottom-Center South ($\theta_5 \approx 90^\circ$)
  - Fin 6: Bottom-Left South-West ($\theta_6 \approx 135^\circ$)
  - Fin 7: Left Lateral West ($\theta_7 \approx 180^\circ$)
- Each fin calculates its anchor point along the capsule rim using an elliptical perimeter projection:
  $$x_k = \frac{W}{2} + \left(\frac{W}{2} - R\right) \cos(\theta_k), \quad y_k = \frac{H}{2} + R \sin(\theta_k)$$
  where $R = H / 2 \approx 32\text{px}$.
- Folded state: Fins parked flush or retracted behind the chassis ($r_{\text{deploy}} = 0\text{px}$, scale = 0.8, opacity = 0).
- Unfolded Layer 1: Fins extend radially outward by $\Delta r \approx 60\text{px}$ with spring animation.
- Layer 2: Selected fin advances by $\Delta r \approx 90\text{px}$ and rotates its option cluster outward.

---

## 7. PROPOSED COMPONENT BOUNDARIES FOR DYNE STUDIO

To preserve the existing application and avoid regression, Dyne Studio should be modularized under `frontend/src/components/air-point/dyne-studio/`:

```text
frontend/src/components/air-point/dyne-studio/
├── index.ts                     # Public barrel export
├── DyneStudioStage.tsx          # 3D viewport, plinth, wallpaper backdrop, click-outside dismissal
├── DyneCapsuleHub.tsx           # Central capsule with double-click detector & mode indicators
├── DyneRadialFinRing.tsx        # Mathematical 8-fin radial manager & layer orchestration
├── DyneFinArm.tsx               # Individual articulated mechanical fin with vector armor & LED rail
├── DyneOptionLayer.tsx          # Layer 2 & Layer 3 expanded options, dials, and preset chips
├── DyneModeToggle.tsx           # Segmented pill for "Desktop Mode" vs "Concept Mode"
├── dyne-studio-store.ts         # Studio state machine (unfold layer, selected fin, concept overrides)
└── dyne-fin-geometry.ts         # Pure trigonometric layout functions & angle mappings
```

### 7.1 State Machine Schema (`dyne-studio-store.ts`)
```typescript
export type DyneLayer = "IDLE" | "PRIMARY_FINS" | "CATEGORY_OPTIONS" | "SUB_OPTIONS";
export type DyneEditorMode = "desktop" | "concept";

export interface DyneStudioState {
  layer: DyneLayer;
  mode: DyneEditorMode;
  activeFinId: string | null;
  activeOptionId: string | null;
  conceptOverrides: Record<string, unknown>;
  unfoldProgress: number; // 0.0 to 1.0
}
```

---

## 8. INTEGRATION RISKS, UNCERTAINTIES & MITIGATION

1. **Host Synchronization Guard:**
   - *Risk:* Selecting an experimental concept option could attempt to write an unsupported key to `backend/settings.json`, causing backend validation failures.
   - *Mitigation:* Strict dual-mode separation. In `desktop` mode, mutations dispatch directly through `engine.setIslandSettings()`. In `concept` mode, mutations are captured exclusively in local React state.
2. **Double-Click Detection on Web & Touch:**
   - *Risk:* Double clicking can trigger unwanted text selection or conflict with single clicks.
   - *Mitigation:* Use CSS `select-none`, track `e.detail === 2` or a dedicated 300ms timing window, and prevent default browser text highlighting.
3. **Performance of 8 Articulated Vector Fins in 3D:**
   - *Risk:* Complex SVG filters (`drop-shadow`, `blur`) on 8 simultaneously animated 3D elements could impact framerate on lower-end GPUs.
   - *Mitigation:* Use `will-change: transform`, GPU-accelerated CSS `transform: translate3d(...) rotateZ(...)`, and toggle heavy glow filters off during rapid movement.
4. **Keyboard Accessibility & Reduced Motion:**
   - *Risk:* Radial interfaces can be difficult to navigate via keyboard or screen reader.
   - *Mitigation:* Implement full `ArrowKey` cycling around the 8 fins, `Enter`/`Space` to select, `Escape` to unwind layers, and disable spring transitions when `prefers-reduced-motion` is active.

---

## 9. RECOMMENDED ORDERED IMPLEMENTATION ROADMAP

For the next engineering assistant/session implementing Dyne Studio:

- [ ] **Step 1: Scaffold Types & Geometry Math (`dyne-fin-geometry.ts`)**
  - Define 8 fin definitions, radial polar-to-cartesian conversions, and deployment postures.
  - Implement pure unit tests verifying angle calculations and boundary conditions.
- [ ] **Step 2: Create Dyne Studio State Store (`dyne-studio-store.ts`)**
  - Implement layer progression (`IDLE` -> `PRIMARY_FINS` -> `CATEGORY_OPTIONS` -> `SUB_OPTIONS`).
  - Wire Escape key listener, outside-click detection, and rewind animation triggers.
- [ ] **Step 3: Build Articulated 8-Fin Radial Ring (`DyneRadialFinRing.tsx` & `DyneFinArm.tsx`)**
  - Adapt the multi-layer titanium vector artwork from `MechanicalFin.tsx` into a scalable, angle-agnostic fin arm.
  - Mount the 8 fins around `CapsuleBody` inside `CapsuleStage`.
- [ ] **Step 4: Implement Double-Click Chassis Trigger (`DyneCapsuleHub.tsx`)**
  - Wire double-click handler on the capsule to expand Layer 1 with smooth spring kinematics.
- [ ] **Step 5: Implement Layer 2 & Layer 3 Category Expansion (`DyneOptionLayer.tsx`)**
  - Connect real settings (Show HUD, Auto-hide, Countdown, Durations) into the respective fin options.
  - Wire `useAirPointEngine()` for live two-way synchronization in Desktop Mode.
- [ ] **Step 6: Add Mode Switch & Studio Controls (`DyneModeToggle.tsx`)**
  - Add Desktop Mode vs Concept Mode switcher with visual distinction.
- [ ] **Step 7: Route Integration & Vitest Verification**
  - Integrate Dyne Studio into `/island` route with backward-compatible toggle to classic view.
  - Run full Vitest suite (110+ tests) and backend unittest suite (337 tests) to verify zero regressions.

# AIRPOINT × DYNE STUDIO — PRE-INTEGRATION DISCOVERY AUDIT REPORT

> **Audit Type:** Technical Discovery & Pre-Integration Analysis (Strictly Read-Only)  
> **Destination Project:** AirPoint (`C:\Users\loges\Documents\antigravity\AirPoint`)  
> **Source Project:** Dyne Studio Standalone (`C:\Users\loges\Documents\antigravity\elegant-bell`)  
> **Audit Date:** 2026-10-26  
> **Status:** Discovery Complete — Ready for Integration Planning  
> **Authoritative Candidate Branch:** `feat/capsule-switcher` at commit `cb382da4c625787baf71f3f2ca9c4e927a626bf4`  

---

## 1. EXECUTIVE SUMMARY

An exhaustive, read-only technical discovery audit was performed across both the **AirPoint** destination project and the standalone **Dyne Studio** source project (`elegant-bell`).

### Key Findings
1. **Source Version Authority:** The implementation in `C:\Users\loges\Documents\antigravity\elegant-bell\dyne-studio-application` on Git branch `feat/capsule-switcher` (commit `cb382da`) is the **authoritative, latest implementation** of Dyne Studio. It includes the approved central capsule, segmented capsule shell, fine-adjustment dial, custom RGB 3-loop mixer, two-ring 18-colour extended palette, and the interactive capsule switcher (Power Saver, Focus, Performance, Media).
2. **Single Real Capsule Reality:** The underlying AirPoint desktop application, Python engine, and Win32 Tkinter overlay (`overlay.py`) support **only ONE single real capsule**: the **Power Saver** desktop HUD. The 4 capsule profiles in Dyne Studio (`Power Saver`, `Focus`, `Performance`, `Media`) are explicitly marked `isPreviewOnly: true` in `lib/capsules.ts` and reside strictly in local React UI state. No native multi-profile registry or host switching API exists.
3. **Integration Point:** In AirPoint, the Dynamic Island and capsule customization experience is exclusively owned by `frontend/src/routes/island.tsx` (`DynamicIslandPage`), mounted at `/island`. Dyne Studio should be integrated here as a dedicated, modular component tree (`frontend/src/components/air-point/dyne-studio/`), keeping native settings synchronized without breaking existing desktop overlay controls.
4. **Compatibility & Dependencies:** Both projects run **React 19** (`19.2.0` in AirPoint, `^19` in Dyne Studio) and **Tailwind CSS v4**. Dyne Studio requires `framer-motion` (`^14.6.0`), which is not yet present in AirPoint's `frontend/package.json`. Adding `framer-motion` to AirPoint frontend will be required during integration.
5. **Zero Baseline Regressions:** Before any changes, baseline checks confirm 100% health:
   - AirPoint Frontend: 110/110 tests pass across 12 Vitest suites (`npx vitest run`); production build succeeds cleanly (`npm run build`).
   - AirPoint Backend: 337/337 unit tests pass (`python -m unittest discover` with `AIRPOINT_ENABLE_TEST_GUARD=1`).
   - Dyne Studio Standalone: Zero TypeScript errors (`tsc --noEmit`); Next.js production build succeeds; 22/22 dial geometry checks pass.

---

## 2. GIT AND WORKSPACE RELATIONSHIPS

```
                                  [Git Repository Checkouts]
                                              │
              ┌───────────────────────────────┴───────────────────────────────┐
              ▼                                                               ▼
   C:\Users\loges\Documents\                                      C:\Users\loges\Documents\
   antigravity\air_point_clean                                    antigravity\elegant-bell
   - Git: main (commit 1297bf2)                                   - Git: feat/capsule-switcher (commit cb382da)
   - Origin: backend & earlier tests                              - Standalone Dyne Studio Next.js App
              │ (Source base consolidated into)                               │ (Authoritative UI source)
              ▼                                                               │
   C:\Users\loges\Documents\                                                  │
   antigravity\AirPoint                                                       │
   - Primary Workspace (No .git in root)                                      │
   - frontend/ (TanStack Start, Vite, React 19)                               │
   - backend/ (Python MediaPipe, ControlServer, Overlay)                      │
   - artifacts/dyne-studio-discovery/                                         │
              ▲                                                               │
              └──────────────────── [Pending Integration Merge] ──────────────┘
```

### Detailed Workspace Status
- **`AirPoint` (`C:\Users\loges\Documents\antigravity\AirPoint`):**
  - Git Root: Not a direct Git repository (consolidated monorepo-style working folder).
  - Contains: `frontend/`, `backend/`, `assets/`, `docs/`, `scripts/`, `artifacts/`.
  - Working Tree: Active development tree. Must be preserved without destructive operations.
- **`air_point_clean` (`C:\Users\loges\Documents\antigravity\air_point_clean`):**
  - Git Root: `C:\Users\loges\Documents\antigravity\air_point_clean\.git`
  - Current Branch: `main`
  - Current HEAD Commit: `1297bf2f61aefa2709cb4cb4277e75df64d41c7d` (`feat: implement Phase 7 Dynamic Island HUD and Phase 7.1 volume visualizer`)
  - Status: Behind `origin/main` by 1 commit. Has 19 unstaged modifications and 27 untracked files (audit reports and backup files). Untouched during this audit.
- **`elegant-bell` (`C:\Users\loges\Documents\antigravity\elegant-bell`):**
  - Git Root: `C:\Users\loges\Documents\antigravity\elegant-bell\.git`
  - Current Branch: `feat/capsule-switcher`
  - Current HEAD Commit: `cb382da4c625787baf71f3f2ca9c4e927a626bf4` (`feat(capsule-switcher): implement capsule switcher with arrows, keyboard, swipe, and per-capsule settings`, committed Mon Oct 26 20:08:45 2026)
  - Other Local Branches: `feat/audit-implementation`, `feat/rgb-drag-labels-alignment`, `feat/transitions-alignment-clarity`, `master`.
  - Uncommitted Changes: 12 modified files (verification screenshots, tsbuildinfo) and 6 untracked patch files in `dyne-studio-application/`.
  - Untouched during this audit.

---

## 3. AUTHORITATIVE SOURCE IDENTIFICATION

A comparison between the existing discovery artifacts and the actual workspaces confirms:

| Location | Contents | Status & Role |
| :--- | :--- | :--- |
| `elegant-bell\dyne-studio-application\` (branch `feat/capsule-switcher`, commit `cb382da`) | Complete, approved Dyne Studio UI (central capsule, segmented shell, adjustment dial, RGB mixer, two-ring palette, capsule switcher, mountain wallpaper, tests). | **Authoritative Source.** This is the definitive codebase representing the approved visual and interaction design. |
| `AirPoint\artifacts\dyne-studio-discovery\source\` | Snapshot of AirPoint foundation files (`island.tsx`, `CapsuleStage.tsx`, `MechanicalFin.tsx`, `control_server.py`, `overlay.py`). | **Historical Discovery Bundle.** Captures destination foundation as of Phase 3, but does NOT contain the Dyne Studio editor. |
| `AirPoint\artifacts\dyne-studio-discovery\DYNE_STUDIO_HANDOFF.md` | Initial architectural mapping and discovery documentation. | **Reference Guide.** Accurate for host contracts and settings matrix. |

---

## 4. AIRPOINT FRONTEND ARCHITECTURE

### 4.1 Framework & Core Tooling
- **Application Framework:** TanStack Start v1.168.60 with Nitro SSR (`frontend/package.json#L52`, `#L91`).
- **Routing Engine:** TanStack Router v1.170.41 (`frontend/package.json#L51`) with automatic route tree generation in `src/routeTree.gen.ts`.
- **UI Library:** React 19.2.0 (`frontend/package.json#L61`), React DOM 19.2.0.
- **Bundler:** Vite 8.1.5 (`frontend/package.json#L95`).
- **Styling:** Tailwind CSS v4.2.1 (`@tailwindcss/vite`) + Nothing Glass v2 design system (`frontend/src/styles.css`).
- **Component Primitives:** Radix UI (`@radix-ui/react-switch`, `@radix-ui/react-slider`, `@radix-ui/react-dialog`, etc.).
- **Iconography:** `lucide-react` v0.575.0 (`frontend/package.json#L60`).
- **Testing:** Vitest v4.1.10 (`frontend/package.json#L96`) + Testing Library React v16.0.0, jsdom environment.

### 4.2 Entry Points & Routing Map
1. **Root Route (`frontend/src/routes/__root.tsx`):**
   - Mounts `AirPointEngineProvider` (`src/components/air-point/engine.tsx`).
   - Wraps content in `DesktopShell` (`src/components/air-point/shell.tsx`).
2. **Page Routes (`frontend/src/routes/`):**
   - `/`: `index.tsx` (Overview: live camera stream, tracking diagnostics, quick power saver toggle).
   - `/gestures`: `gestures.tsx` (Gesture tutorials, video previews, enable/disable switches).
   - `/cursor`: `cursor.tsx` (Cursor calibration, 1 Euro filter smoothing, sensitivity sliders).
   - `/island`: `island.tsx` (**Dynamic Island Page: The sole owner of HUD customization**).
   - `/appearance`: `appearance.tsx` (App-wide themes: Obsidian, Titanium, OLED, Slate; accents; density).
   - `/about`: `about.tsx` (Diagnostics, system info, versioning).

### 4.3 Component Ownership of the Dynamic Island
`frontend/src/routes/island.tsx` (`DynamicIslandPage`) is the **exclusive owner** of the Dynamic Island experience:
- Lines 197–234: Futuristic 3D Capsule Viewport (`CapsuleStage` in `src/components/air-point/capsule/CapsuleStage.tsx`), hosting `CapsuleBody` and lateral `MechanicalFin` components.
- Lines 236–265: Classic 2D Desktop HUD Pill (`DynamicIslandPreview` in `src/components/air-point/dynamic-island.tsx`).
- Lines 280–356: Interactive preview simulation triggers (Normal, Waiting, Countdown, Complete, Wake, Full Lifecycle Demo).
- Lines 358–380: Real Desktop Overlay Test trigger button (`testDesktopCountdown(5.0)`).
- Lines 384–464: Real Desktop Overlay Status card (Active Win32, Bridge 8765, Engine State, Power Saver).
- Lines 468–697: Dynamic Island settings grid (Show HUD, Notifications, Countdown, Auto-hide switches, duration slider, completion duration buttons).

### 4.4 Recommended Integration Placement
Dyne Studio should be integrated into **`frontend/src/routes/island.tsx`** as a dedicated modular subsystem under `frontend/src/components/air-point/dyne-studio/`:
- **Stage Replacement/Upgrade:** Replace or augment the current static `CapsuleStage` with `DyneStudio`, establishing the interactive stadium shell, radial categories, adjustment dials, and colour palettes.
- **Preserved Real Settings:** Maintain two-way binding to `useAirPointEngine()` so real desktop settings (`island_enabled`, `island_notifications_enabled`, `island_timer_enabled`, `island_autohide_enabled`, `island_hud_duration_s`, `island_completion_duration_s`) remain functional and synchronize live to the native Win32 overlay.

---

## 5. REAL CAPSULE IDENTITY AND DATA MODEL

### 5.1 Capsule Identity Origin
In AirPoint, the capsule identity is **NOT** a user-created profile or database entity. It is an operational presentation mode derived from the computer-vision tracking engine and power state machine:

| Property | Frontend Representation | Host / Backend Source | Native Win32 Overlay Output |
| :--- | :--- | :--- | :--- |
| **Display Name** | Hardcoded in `CapsuleBody.tsx#L26-L81` based on `CapsuleState` (`"AirPoint Core"`, `"Armed & Ready"`, `"Countdown Sequence"`, `"AirPoint Active"`, `"Power Saver"`, `"Waking System"`). | Ephemeral runtime status in `RuntimeState` (`control_server.py#L133`). | Hardcoded in `overlay.py`: `"AIR POINT · NORMAL"`, `"POWER SAVER · WAITING"`, `"POWER SAVER"`, `"POWER SAVER · HIDING"`, `"HAND DETECTED · NORMAL"`. |
| **Icon / Symbol** | Lucide icons in `CapsuleBody.tsx` (`<Cpu>`, `<Sparkles>`, `<Clock>`, `<Activity>`, `<Leaf>`, `<Zap>`). | None stored. | Vector line art drawn on Tkinter canvas in `overlay.py#L300-L345` (`PLAY`, `POWER_WAIT`, `POWER_SAVE`, `HAND_FOUND`, etc.). |
| **Accent Colour** | `CapsuleAccent` (`"cyan"`, `"violet"`, `"dual"`, `"amber"`, `"emerald"`) in `types.ts#L27`. | None stored. | Fixed palette constants in `overlay.py#L40-L56` (`#8aa89b` Sage, `#d49b56` Amber, `#b983ff` Wakanda). |
| **Power Saver State**| `engine.powerState` (`"NORMAL"` \| `"POWER_SAVE"`) in `engine.tsx#L65`. | `PowerStateManager.state` (`power_state_machine.py#L77`). | Directly governs overlay presentation mode (`POWER_SAVE`, `POWER_WAIT`, `NORMAL`). |
| **HUD Duration** | `islandSettings.hudDurationS` (10s–1800s, default 120s) in `air-point-model.ts#L123`. | `island_hud_duration_s` in `backend/settings.json#L20`. | Sets `_ps_duration` and countdown badge in `overlay.py#L1161-L1169`. |
| **Completion Duration**| `islandSettings.completionDurationS` (1s–5s, default 2.0s) in `air-point-model.ts#L124`. | `island_completion_duration_s` in `backend/settings.json#L21`. | Sets toast visibility deadline for `"POWER SAVER · HIDING"` in `overlay.py#L685`. |
| **Countdown On/Off**| `islandSettings.timerEnabled` (`bool`) in `air-point-model.ts#L112`. | `island_timer_enabled` in `backend/settings.json#L18`. | Toggles `MM:SS` badge pill visibility on overlay in `overlay.py#L665`. |
| **Show HUD** | `islandSettings.enabled` (`bool`) in `air-point-model.ts#L110`. | `island_enabled` in `backend/settings.json#L16`. | Shows/hides Win32 overlay window in `overlay.py#L1066`. |
| **Auto-hide** | `islandSettings.autohideEnabled` (`bool`) in `air-point-model.ts#L113`. | `island_autohide_enabled` in `backend/settings.json#L19`. | Controls whether toast retracts after deadline in `overlay.py#L657`. |

### 5.2 Capability Breakdown
1. **Values read from real desktop application:** `running`, `fps`, `pointerOwner`, `trackingStatus`, `powerState`, `islandSettings` (`enabled`, `notificationsEnabled`, `timerEnabled`, `autohideEnabled`, `hudDurationS`, `completionDurationS`).
2. **Values that can be written to real application:** All 6 `islandSettings` via `POST /api/settings`, and 5s test countdown via `POST /api/control`.
3. **Values that affect ONLY the frontend preview:** Custom RGB mixing, font family (`System`, `Mono`, `Humanist`), font size, font boldness, texture/material (`Glass`, `Matte`, `Translucent`), shape roundness (`28px`–`56px`), style (`Balanced`, `Quiet`, `Luminous`), and preview profiles (`Focus`, `Performance`, `Media`).
4. **Unsupported native capabilities:** Native desktop Tkinter overlay does NOT support custom fonts, arbitrary RGB tints via API, textured materials, or shape roundness adjustments.

---

## 6. MULTIPLE REAL CAPSULES INQUIRY

### Mandatory Finding: AirPoint Exposes Only ONE Real Capsule
- **Source Inspection:** A thorough search across `backend/settings.json`, `backend/core/control_server.py`, `backend/core/overlay.py`, and `backend/core/power_state_machine.py` confirms that **no multiple capsule profile model exists in the host**.
- **Data Source in Dyne Studio:** In `elegant-bell\dyne-studio-application\lib\capsules.ts#L13-L21`, the author explicitly documented this fact:
  ```typescript
  /**
   * PREVIEW-ONLY CAPSULE LIST
   * 
   * Host Inspection Note:
   * The underlying Dyne host/native bridge currently defines only a single capsule profile ("Power Saver").
   * Per the switcher brief, we do NOT fake extra native profiles. This switcher operates over a 
   * clearly labelled preview-only profile list that stays strictly in local UI state and is never 
   * sent to a native writer.
   */
  ```
- **Preview Profiles:** `PREVIEW_CAPSULES` contains:
  1. `power-saver` (Power Saver, icon: `Activity`, Gold accent, 2s time, 56px roundness)
  2. `focus` (Focus, icon: `Moon`, Cyan accent, 5s time, 28px roundness)
  3. `performance` (Performance, icon: `Zap`, Red accent, 10s time, 56px roundness)
  4. `media` (Media, icon: `Music`, Purple accent, 4s time, 42px roundness)
- **Integration Rule:** All profile switching must remain **strictly in local React UI state** (`capsulesSettings: Record<string, Settings>`). Selecting a non-Power Saver profile must **never** send an invalid profile ID to `POST /api/settings`.

---

## 7. DESKTOP INTEGRATION DATA FLOW & HOST CONTRACTS

```
                                  DATA-FLOW ARCHITECTURE
                                  
  ┌────────────────────────────────────────────────────────────────────────┐
  │                           REACT FRONTEND                               │
  │  frontend/src/routes/island.tsx (DynamicIslandPage / DyneStudio)       │
  │  - Manages local preview state & calls useAirPointEngine()             │
  └──────────────────┬───────────────────────────────────▲─────────────────┘
                     │ Mutations                         │ Telemetry & Events
                     │ (JSON HTTP POST)                  │ (Polling & SSE)
                     ▼                                   │
  ┌──────────────────────────────────────────────────────┴─────────────────┐
  │                 AIRPOINT ENGINE PROVIDER (engine.tsx)                  │
  │  - Polling heartbeat: GET http://127.0.0.1:8765/api/status (every 1.5s)│
  │  - Event stream: GET http://127.0.0.1:8765/api/events (SSE)            │
  │  - Mutator: postSettingsMutation() -> POST /api/settings               │
  │  - Controller: testDesktopCountdown() -> POST /api/control             │
  │  - Auth: Injects X-AirPoint-Token header from .bridge_token            │
  └──────────────────┬───────────────────────────────────▲─────────────────┘
                     │ HTTP REST                         │ HTTP Responses
                     ▼                                   │
  ┌──────────────────────────────────────────────────────┴─────────────────┐
  │              PYTHON CONTROL SERVER (core/control_server.py)             │
  │  - Validates Origin & Host headers (127.0.0.1:8765 / localhost)        │
  │  - Validates X-AirPoint-Token header against backend/.bridge_token     │
  │  - Enforces bounds clamping on all numeric parameters                  │
  │  - Updates RuntimeState in memory & persists to backend/settings.json  │
  │  - Dispatches actions to DynamicIslandOverlay via thread-safe queue    │
  └──────────────────┬─────────────────────────────────────────────────────┘
                     │ Thread-Safe Queue Dispatch
                     ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │             WIN32 DESKTOP OVERLAY HUD (core/overlay.py)                 │
  │  - Tkinter topmost click-through window (ctypes.windll.user32)         │
  │  - Coordinates: x = (sw - w) // 2, y_hidden = -h - 10, y_visible = 16  │
  │  - Renders vector capsule, progress bar, audio soundbars, countdown    │
  │  - Animates smooth drop/retract transitions at 30 FPS                  │
  └────────────────────────────────────────────────────────────────────────┘
```

### Supported API Operations Reference

| Operation | Caller | Endpoint | Payload / Request Shape | Response Shape | Capability / Rules |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Status Poll** | `engine.tsx#L287` | `GET /api/status` | None | `{ running, fps, tracking, owner, power_state, token, settings: {...} }` | Read-only. Polled every 1500ms with 2000ms timeout abort controller. |
| **Event Stream** | `engine.tsx#L374` | `GET /api/events` | None | Server-Sent Events stream: `data: { event, action, time }` | Read-only SSE stream. Keeps live event activity log. |
| **Update Settings**| `engine.tsx#L412` | `POST /api/settings` | `{ island_enabled?, island_notifications_enabled?, island_timer_enabled?, island_autohide_enabled?, island_hud_duration_s?, island_completion_duration_s?, ... }` | `{ status: "ok", settings: {...} }` | Read-Write. Requires valid `X-AirPoint-Token`. Clamps values: duration 10–1800s, completion 1–5s. |
| **Test Countdown** | `engine.tsx#L673` | `POST /api/control` | `{ action: "test_countdown", duration: 5.0 }` | `{ status: "ok", action: "test_countdown", triggered: true, duration: 5.0 }` | Action trigger. Runs safe 5s test countdown on overlay without modifying `PowerStateManager`. |
| **Lifecycle Control**| `engine.tsx#L458` | `POST /api/stop`, `POST /api/start`, `POST /api/toggle` | Empty | `{ status: "ok", running: bool, action: "..." }` | Action trigger. Pauses, resumes, or stops vision tracking. |

---

## 8. DYNE STUDIO SOURCE FILE INVENTORY

All files located in `C:\Users\loges\Documents\antigravity\elegant-bell\dyne-studio-application`:

| File Path | Exported Symbols | Purpose & Architecture | Reuse Strategy |
| :--- | :--- | :--- | :--- |
| `components/dyne-studio.tsx` | `DyneStudio` | Main container component: manages view state (`rest`, `main`, `category`, `adjust`, `fonts`, `customColour`, `extendedColours`), heading transitions, switcher navigation, pointer gestures, and keyboard handlers. | **Direct Reuse** with minor path adjustments to local AirPoint imports. |
| `components/central-capsule.tsx` | `CentralCapsule` | The central metallic capsule: renders icon, name, timeout tag, status LED, dynamic accent colour, sheen gradient, and pulse feedback. | **Direct Reuse**. Pure React component. |
| `components/segmented-capsule-shell.tsx`| `SegmentedCapsuleShell`, `ShellOption` | SVG stadium ring displaying 3, 6, 10, or 18 articulated category options around the central capsule with calculated centroids and entrance/exit animations. | **Direct Reuse**. Pure SVG component. |
| `components/capsule-adjustment-track.tsx`| `CapsuleAdjustmentTrack` | Open stadium dial track with draggable tactile handle, numeric ticks, detent haptics, and live readout. Used for Time (0–10s) and intensity dials. | **Direct Reuse**. Pure SVG component. |
| `components/colour-explorations.tsx` | `CustomColourView` | Custom RGB colour mixer with 3 concentric stadium loops (R, G, B), live hex readout, anti-wrap drag clamping, and numeric stepper inputs. | **Direct Reuse**. Pure SVG/React component. |
| `components/two-ring-colour-palette.tsx` | `TwoRingColourPalette` | Two-ring extended colour palette rendering 18 stadium segments (8 inner, 10 outer) with centered labels and selection indicators. | **Direct Reuse**. Pure SVG component. |
| `lib/capsules.ts` | `PREVIEW_CAPSULES`, `CapsuleDefinition` | Definitions for 4 preview profiles (`Power Saver`, `Focus`, `Performance`, `Media`) with default settings and explicit `isPreviewOnly: true` flags. | **Direct Reuse**. Pure TypeScript model. |
| `lib/studio.ts` | `stadiumPoint`, `perimeterPath`, `stadiumTrackFrame`, `stadiumTrackPath`, `stadiumTrackProject`, `stadiumLoopFrame`, `stadiumLoopProject`, `colours`, `extendedColours`, `initialSettings`, types (`View`, `Category`, `Adjustment`, `Settings`) | Mathematical geometry engine: pure trigonometric functions computing continuous stadium paths and radial projections. | **Direct Reuse**. Pure mathematical utility. |
| `lib/utils.ts` | `cn` | Standard `clsx` + `tailwind-merge` utility function. | Already exists in AirPoint at `frontend/src/lib/utils.ts`. |
| `app/globals.css` | CSS classes (`.studio`, `.capsule-stage`, `.capsule-assembly`, `.central-capsule`, `.shell-svg`, `.adjustment-track-svg`, etc.) | Custom CSS classes for Dyne Studio layout, textures, stadium geometry, and animations. | **Extract & Scope** into `frontend/src/styles/dyne-studio.css`. |
| `public/airpoint-mountain-wallpaper.jpg` | Asset file | Mountain landscape backdrop image used for local texture/material transparency simulation. | Copy to `AirPoint/frontend/public/`. |

---

## 9. INTEGRATION COMPATIBILITY ANALYSIS

### 9.1 Compatibility Matrix

| Aspect | AirPoint (`AirPoint/frontend`) | Dyne Studio (`elegant-bell`) | Compatibility Assessment & Required Resolution |
| :--- | :--- | :--- | :--- |
| **React Version** | `19.2.0` | `^19` | **Full Compatibility.** Both use React 19. No version mismatch. |
| **Router / SSR** | TanStack Start (Nitro) + TanStack Router | Next.js 16.4.3 (App Router) | **Compatible via Component Extraction.** Dyne Studio components are client components (`'use client'`) with zero Next.js server dependencies. They mount cleanly in TanStack Router. |
| **Package Manager** | `npm` (`package-lock.json`) | `pnpm` (`pnpm-lock.yaml`) | **Resolution:** Use `npm` in AirPoint. Do not copy pnpm lockfile. |
| **Animation Engine** | CSS transitions & `@keyframes` in `styles.css` | `framer-motion` v14.6.0 | **Action Required:** Install `framer-motion` into `AirPoint/frontend/package.json`. |
| **Tailwind CSS** | Tailwind CSS v4.2.1 (`@tailwindcss/vite`) | Tailwind CSS v4.3.3 (`@tailwindcss/postcss`) | **Full Compatibility.** Both use Tailwind CSS v4 theme inline syntax. |
| **CSS Namespace** | Nothing Glass v2 design system (`styles.css`) | Custom studio classes in `globals.css` | **Resolution:** Place Dyne Studio styles in an isolated, scoped stylesheet (`dyne-studio.css`) imported into `styles.css` without altering AirPoint's root theme variables. |
| **Icons** | `lucide-react` v0.575.0 | `lucide-react` v1.16.0 | **Full Compatibility.** All icons used in Dyne Studio (`Palette`, `Type`, `SlidersHorizontal`, `Clock3`, `Hexagon`, `Layers`, `Droplet`, `Circle`, `Sun`, `Minus`, `Grid3X3`, `ChevronLeft`, `ChevronRight`) exist in AirPoint's Lucide version. |
| **Wallpaper Asset** | Not currently in `frontend/public/` | `public/airpoint-mountain-wallpaper.jpg` | **Action Required:** Copy `airpoint-mountain-wallpaper.jpg` into `AirPoint/frontend/public/` so CSS `url('/airpoint-mountain-wallpaper.jpg')` resolves. |
| **Keyboard Navigation**| Tab, Space, Escape handled per page | Escape (back one level), Left/Right (switch capsule) | **Compatible.** Dyne Studio's Escape handler unwinds one level at a time and stops propagation when active. |
| **Accessibility** | ARIA live regions, semantic buttons | `aria-roledescription="carousel"`, `role="tablist"`, `role="slider"` | **Compatible.** Dyne Studio includes screen reader announcements and `useReducedMotion()`. |

---

## 10. STATE OWNERSHIP AND PERSISTENCE PLAN

To prevent regressions and ensure host safety, every state field is assigned an unambiguous owner:

| State Field | Storage Type | Read Source | Write Destination | Host Impact |
| :--- | :--- | :--- | :--- | :--- |
| **Active Capsule Profile** | Local React State | Default index `0` (`power-saver`) | `setActiveCapsuleIndex(idx)` | **None (Preview Only).** Never sent to backend. |
| **Per-Capsule Settings** | Local React State | `capsulesSettings: Record<string, Settings>` | `setCapsulesSettings(prev => ...)` | **None (Preview Only).** Preserved across capsule switches in memory. |
| **Navigation Layer (`View`)**| Local React State | Initial: `{ kind: 'rest' }` | `navigate(targetView)` / `back()` | **None (UI Only).** |
| **Custom RGB Values** | Local React State | `settings.customRgb: { r, g, b }` | `change('customRgb', rgb)` | **None (Preview Only).** |
| **Texture / Material** | Local React State | `settings.texture` (`Glass`, `Matte`, `Translucent`) | `change('texture', val)` | **None (Preview Only).** |
| **Font Family & Size** | Local React State | `settings.font`, `settings.fontSize`, `settings.weight` | `change('font', val)`, etc. | **None (Preview Only).** |
| **Shape Roundness** | Local React State | `settings.roundness` (`28px`–`56px`) | `change('roundness', val)` | **None (Preview Only).** |
| **Preview Timeout (`time`)** | Local React State | `settings.time` (`0s`–`10s`) | `change('time', val)` | **Local Preview.** Does not alter native 120s timer unless user explicitly applies to desktop HUD. |
| **Show HUD** | Real Engine State | `engine.islandSettings.enabled` | `engine.setIslandSettings({ enabled: bool })` | **Real Win32.** Calls `POST /api/settings`, toggles native overlay window. |
| **Notifications Toggle** | Real Engine State | `engine.islandSettings.notificationsEnabled` | `engine.setIslandSettings({ notificationsEnabled: bool })` | **Real Win32.** Calls `POST /api/settings`, suppresses mode toasts. |
| **Countdown Badge** | Real Engine State | `engine.islandSettings.timerEnabled` | `engine.setIslandSettings({ timerEnabled: bool })` | **Real Win32.** Calls `POST /api/settings`, toggles MM:SS badge pill. |
| **Auto-hide Toggle** | Real Engine State | `engine.islandSettings.autohideEnabled` | `engine.setIslandSettings({ autohideEnabled: bool })` | **Real Win32.** Calls `POST /api/settings`, toggles retraction timeout. |
| **HUD Duration (Real)** | Real Engine State | `engine.islandSettings.hudDurationS` (10–1800s) | `engine.setIslandSettings({ hudDurationS: val })` | **Real Win32.** Calls `POST /api/settings`, updates `_ps_duration`. |
| **Completion Duration** | Real Engine State | `engine.islandSettings.completionDurationS` (1–5s) | `engine.setIslandSettings({ completionDurationS: val })` | **Real Win32.** Calls `POST /api/settings`, updates toast deadline. |
| **Test 5s Countdown** | Real Host Action | Action trigger | `engine.testDesktopCountdown(5.0)` | **Real Win32.** Calls `POST /api/control`, runs test without altering engine state. |

---

## 11. REGRESSION RISKS & MITIGATION MATRIX

| Risk Description | Evidence from Code | Severity | Affected Files | Safest Mitigation | Required Regression Test |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Accidental Native Multi-Profile Mutation** | Dyne Studio has 4 capsule profiles (`Power Saver`, `Focus`, `Performance`, `Media`). Backend `settings.json` supports only one flat config. | **High** | `engine.tsx`, `control_server.py`, `settings.json` | Explicitly enforce `isPreviewOnly: true`. Do not connect profile switching to `postSettingsMutation()`. | Run backend `test_control_server.py` and verify `settings.json` schema remains unchanged. |
| **Missing `framer-motion` Dependency** | Dyne Studio uses `MotionConfig`, `AnimatePresence`, `motion.*` extensively. `AirPoint/frontend` lacks `framer-motion`. | **High** | `frontend/package.json` | Install `framer-motion` (`^12` or `^14`) using `npm install framer-motion`. | Run `npm run build` to verify clean Vite and SSR Nitro bundling. |
| **CSS Class Collisions** | Dyne Studio uses global classes like `.studio`, `.capsule-stage`, `.capsule-assembly`, `body`. | **Medium** | `styles.css`, `app/globals.css` | Isolate studio styles into `src/styles/dyne-studio.css`. Scope root body background rules to `.dyne-studio-root` container instead of global `body`. | Verify `/`, `/gestures`, `/appearance` pages render without visual distortion. |
| **Wallpaper 404 in Vite Bundler** | Dyne Studio references `/airpoint-mountain-wallpaper.jpg`. | **Low** | `public/`, `styles/dyne-studio.css` | Copy `airpoint-mountain-wallpaper.jpg` into `AirPoint/frontend/public/`. | Verify backdrop loads cleanly with HTTP 200 in browser. |
| **Double-Click vs Single-Click Conflict** | Earlier specification considered double-click for Layer 1. Approved Dyne Studio uses single click to open and single click to go back. | **Medium** | `central-capsule.tsx`, `dyne-studio.tsx` | Strictly honor the approved `elegant-bell` implementation: single click on resting capsule opens Layer 1 (`main`); single click when open backs out one level. | Run `dynamic-island-tab.test.tsx` and verify click-to-open and ESC-to-back. |
| **Escape Key Hijacking Global Shortcuts** | `DyneStudio` attaches a `keydown` listener for `Escape` to call `back()`. | **Low** | `dyne-studio.tsx` | Listener is active only while the Dyne Studio component is mounted, and gracefully unwinds views before unmounting. | Test navigating to other tabs (`/gestures`, `/cursor`) and verify Escape behavior. |

---

## 12. PROPOSED FILE-LEVEL INTEGRATION CHANGE LIST

When integration begins in a subsequent task, the following file operations are planned:

### A. New Files to Create in `AirPoint/frontend`
1. `src/components/air-point/dyne-studio/index.ts` (Public export barrel)
2. `src/components/air-point/dyne-studio/dyne-studio.tsx` (Adapted from `elegant-bell/dyne-studio-application/components/dyne-studio.tsx`)
3. `src/components/air-point/dyne-studio/central-capsule.tsx` (Adapted from `elegant-bell/.../central-capsule.tsx`)
4. `src/components/air-point/dyne-studio/segmented-capsule-shell.tsx` (Adapted from `elegant-bell/.../segmented-capsule-shell.tsx`)
5. `src/components/air-point/dyne-studio/capsule-adjustment-track.tsx` (Adapted from `elegant-bell/.../capsule-adjustment-track.tsx`)
6. `src/components/air-point/dyne-studio/colour-explorations.tsx` (Adapted from `elegant-bell/.../colour-explorations.tsx`)
7. `src/components/air-point/dyne-studio/two-ring-colour-palette.tsx` (Adapted from `elegant-bell/.../two-ring-colour-palette.tsx`)
8. `src/components/air-point/dyne-studio/lib/capsules.ts` (Adapted from `elegant-bell/.../lib/capsules.ts`)
9. `src/components/air-point/dyne-studio/lib/studio.ts` (Adapted from `elegant-bell/.../lib/studio.ts`)
10. `src/styles/dyne-studio.css` (Scoped studio styles extracted from `elegant-bell/.../app/globals.css`)
11. `public/airpoint-mountain-wallpaper.jpg` (Copied from `elegant-bell/.../public/airpoint-mountain-wallpaper.jpg`)
12. `src/test/dyne-studio.test.tsx` (Integration test suite verifying layer navigation, capsule switching, and slider detents)

### B. Existing Files to Modify in `AirPoint/frontend`
1. `package.json`: Add dependency `"framer-motion": "^12.0.0"` (or `^14.0.0`).
2. `src/styles.css`: Import `@import "./styles/dyne-studio.css";`.
3. `src/routes/island.tsx`: Mount `DyneStudio` inside `DynamicIslandPage`, replacing the static stage while retaining the Real Desktop Status card, test countdown trigger, and native settings synchronization.

### C. Files that MUST NOT Be Touched
- `backend/core/control_server.py` (Must remain untouched)
- `backend/core/overlay.py` (Must remain untouched)
- `backend/core/power_state_machine.py` (Must remain untouched)
- `backend/settings.json` (Must remain untouched)
- `frontend/src/components/air-point/engine.tsx` (Supported contracts already sufficient)
- `frontend/src/routes/appearance.tsx`, `index.tsx`, `gestures.tsx`, `cursor.tsx`, `about.tsx` (Must remain untouched)

---

## 13. BASELINE VERIFICATION LOG

All baseline verification commands were executed directly during this audit. No code was modified.

| Environment / Target | Command Executed | Exit Code | Result / Output Summary |
| :--- | :--- | :---: | :--- |
| **AirPoint Frontend Tests** | `cd AirPoint/frontend; npx vitest run` | `0` | **12 test files passed, 110/110 tests passed (100%)** in 5.09s. |
| **AirPoint Frontend Build** | `cd AirPoint/frontend; npm run build` | `0` | Vite client bundle (1,935 modules) + Nitro SSR server (1,975 modules) compiled cleanly into `.output/`. |
| **AirPoint Backend Tests** | `$env:AIRPOINT_ENABLE_TEST_GUARD="1"; python -m unittest discover` | `0` | **337/337 tests passed OK** in 17.306s with zero failures and zero native mouse/keyboard dispatch. |
| **Dyne Studio Typecheck** | `cd elegant-bell/dyne-studio-application; npx tsc --noEmit` | `0` | Zero TypeScript errors across all 12 source files. |
| **Dyne Studio Build** | `cd elegant-bell/dyne-studio-application; npx next build` | `0` | Next.js production build compiled and prerendered static pages cleanly in 1.4s. |
| **Dyne Studio Dials QA** | `node verification/dyne-dial-check.cjs` | `0` | **22/22 geometry/source checks passed.** |
| **Dyne Studio Transpile QA**| `node verification/transpile-check.cjs` | `0` | **PASS: syntax-transpiled 12 TypeScript/TSX files.** |

---

## 14. UNKNOWNS, LIMITATIONS & CONCLUSION

1. **Unknowns:** None. The architecture, file locations, component boundaries, and contracts across both repositories have been completely established and verified.
2. **Blockers:** None.
3. **Conclusion:** Both codebases are in a clean, passing state. The approved Dyne Studio UI is modular, self-contained, and ready to be merged into `AirPoint/frontend/src/components/air-point/dyne-studio/` and mounted in `frontend/src/routes/island.tsx` as soon as the integration plan is reviewed.

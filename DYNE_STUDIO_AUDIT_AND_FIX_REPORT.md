# DYNE STUDIO — EVIDENCE-BASED AUDIT AND FIX REPORT
**AirPoint / Dyne Integrated Final**  
*Timestamp: 2026-10-28T00:44:00+05:30*  
*Git Baseline: `backup-pre-audit` (`c75d4d3`) | Final Commit: `4db1058`*

---

## 1. Issue Inventory Table

| ID | Severity | File:Line | Symptom | Root Cause | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **DEF-01** | **P0** | `src/components/air-point/dyne-studio/segmented-capsule-shell.tsx:120-142` | Top-left slot (Colour, Show HUD) unrendered / blank in the ring. | Ring geometry for 2, 3, 5, 6 options used `perimeterPath` (starting at stadium top-center $x=430$) instead of `shellSegmentPath` (starting at top-left $x=270$). As a result, segment boundaries were rotated relative to centroids, and the final segment rendered an opaque `#shell-surface` SVG path directly over the top-left slot. | **Fixed** |
| **DEF-02** | **P0** | `src/components/air-point/dyne-studio/segmented-capsule-shell.tsx:165-188` | Labels clipped or halved by capsule ring ("Surface" $\to$ "face", "Notifications: On" $\to$ "tions: On"). | In 2-option rings, dividing line was calculated vertically through the capsule center $(430, 75)$ down to $(430, 162)$, slicing directly through the center of horizontal category labels. | **Fixed** |
| **DEF-03** | **P0** | `src/components/air-point/dyne-studio/segmented-capsule-shell.tsx:570-610` | Overlapping text on multi-line labels ("Completion-message duration", "Behaviour & Timing"); test countdown crossed by divider. | SVG `<tspan>` lacked explicit vertical offsets (`dy`), causing adjacent lines to collide at the exact same baseline. Divider radial strokes intersected the label group centroid. | **Fixed** |
| **DEF-04** | **P0** | `src/styles/dyne-studio.css:760-785` | Irregular shell outline and dark rounded block with hard edges sitting behind the capsule on Material category. | `.texture-preview-backdrop` had hard `border-radius: 70px`, heavy fixed inset shadow, and fixed coordinates ($18\%, 28\%$) rendering a solid dark box behind the ring on the top-level Material category view. | **Fixed** |
| **DEF-05** | **P0** | `src/components/air-point/dyne-studio/dyne-studio.tsx:230-245`, `segmented-capsule-shell.tsx:190` | Transitions rebuild the shell; capsule appears alone with empty ring for 0.4–0.8 s; heading changes before incoming ring appears. | `SegmentedCapsuleShell` was keyed with `${key}-${state}`, forcing React to completely unmount and remount the SVG DOM on every transition state update. `displayedTitle` and `displayedCrumb` updated asynchronously from layer navigation. | **Fixed** |
| **DEF-06** | **P1** | `src/components/air-point/dyne-studio/capsule-adjustment-track.tsx:180-210`, `dyne-studio.tsx:140-185` | Host duration sliders commit on every continuous pointer move, causing backend write spam and stale-write race conditions. | Range and track handlers called `commitDesktopSettings` directly on `onPointerMove`. Lacked local drag state, release-gated commit, debounce, and in-flight tracking (`aria-busy`). | **Fixed** |
| **DEF-07** | **P1** | `src/components/air-point/dyne-studio/dyne-studio.tsx:720-735`, `src/test/dynamic-island-tab.test.tsx:55-80` | Operational controls lack honest host status; test suite failed on wording mismatch (`HOST CONNECTED` vs `HOST OFFLINE`). | Editor did not expose honest tripartite host status indicators matching contract: `HOST CONNECTED`, `HOST OFFLINE · LAST KNOWN SETTINGS`, `HOST OFFLINE · SETTINGS UNSYNCED`. | **Fixed** |
| **DEF-08** | **P1** | `src/components/air-point/dyne-studio/dyne-studio.tsx:540-590` | Operational controls allowlist compliance; controls active when unsynced/offline. | Operational actions (Show HUD, Countdown badge, Auto-hide, Notifications, HUD duration, Completion duration, Test countdown) lacked explicit gating against `settingsSynced && hostConnected && hostAdapter`. | **Fixed** |
| **DEF-09** | **P1** | `src/components/air-point/dyne-studio/dyne-studio.tsx:310-380`, `src/styles/dyne-studio.css:1075-1120` | Event-state preview switcher chevron hit area under 44 px; pointer swipe lacked threshold and angle validation; appearance leaked across states. | Chevrons lacked minimum 44×44 px hit target. Swipe detector lacked velocity check ($> 0.4\text{ px/ms}$) and horizontal angle lock ($|\Delta x| > 1.5|\Delta y|$). Appearance was stored globally rather than per-capsule. | **Fixed** |
| **DEF-10** | **P2** | `src/styles/dyne-studio.css:1320-1365` | Mobile viewport (390×844) layout collapse: capsule expanded to 84% width covering the ring; chevrons overlapped "Material" label; touch targets under 44 px. | CSS `@media (max-width: 640px)` overrode capsule to `left: 8%; width: 84%; top: 32%; height: 36%`. Switcher chevron at `top: 50%` collided with right semicircle ring option. SVG segments lacked minimum 44×44 px hit geometry. | **Fixed** |
| **DEF-11** | **P2** | `src/styles/dyne-studio.css:320-330`, `segmented-capsule-shell.tsx:310-330` | Typography below 12px; preview badge text crowding; "More Colours" text crowding capsule. | `.capsule-preview-on-capsule` was 10px; "More Colours" rendered on a single line crowding the capsule edge. | **Fixed** |

---

## 2. What Changed and Why, Per File

### 1. `src/components/air-point/dyne-studio/studio.ts`
- **Before**: `shellSegmentPath` only supported simple arc interpolation that could not wrap seamlessly clockwise across the boundary $t = 1.0 \to 0.0$.
- **After**: Implemented `shellArcClockwise(startT, endT, radius)` and `shellArcCounterClockwise(startT, endT, radius)` to calculate clockwise and counter-clockwise stadium perimeter curves with correct wrapping across the top-left boundary.
- **Why**: Allows shell segment paths to exactly match the parameterization of centroids starting at top-left $(270, 75)$, eliminating rotated SVG overlays.

### 2. `src/components/air-point/dyne-studio/segmented-capsule-shell.tsx`
- **Before**: Rings for 2, 3, 5, 6 options used `BOUNDS_6` mapped to `perimeterPath` (stadium top-center origin $(430, 75)$), creating a 1-segment offset that placed the final segment directly over the top-left slot ("Colour" / "Show HUD"). 2-option rings divided vertically through the center, cutting labels in half. Multi-line `<tspan>` lacked vertical spacing.
- **After**:
  - Replaced perimeter bounds with exact normalized coordinates (`BOUNDS_6`, `BOUNDS_5`, `BOUNDS_3`, `BOUNDS_2`) derived from `shellPoint(t)`.
  - Re-architected 2-option rings into Top Arch (`[leftMid, rightMid]`) and Bottom Arch (`[rightMid, leftMid]`), eliminating vertical splitting.
  - Multi-line labels now render with explicit `dy="16"` offsets and centered alignment.
  - Added an invisible `fill="transparent" pointerEvents="all"` touch-target rect ($120 \times 120$ SVG units) to every option, ensuring touch targets on all mobile screens measure $\ge 44 \times 44\text{ px}$.
  - Set `pointerEvents="auto"` on label `<g>` and `<text>` elements so `document.elementFromPoint` directly hits labels without occlusion.
- **Why**: Fixes P0 defects 1, 2, and 3; guarantees every label is fully visible, centered, clear of dividers, and accessible.

### 3. `src/components/air-point/dyne-studio/dyne-studio.tsx`
- **Before**:
  - `SegmentedCapsuleShell` was keyed with `${key}-${state}`, forcing DOM remounts on every transition.
  - `displayedTitle` and `displayedCrumb` updated on delayed timers leading incoming content.
  - Duration sliders wrote to the host continuously on pointer moves.
  - `desktopSettings` prop only accepted `AirPointHudSettings` without `null`.
  - Host status indicator only rendered "HOST OFFLINE — showing last known settings." when unsynced.
- **After**:
  - Stabilized shell key to `key={shell-${key}}`, maintaining stable DOM mount across transitions.
  - Synchronized `displayedTitle` and `displayedCrumb` immediately with `navigate(target)`.
  - Implemented live local duration states (`localHudDuration`, `localCompletionDuration`) with release commit (`onPointerUp`, `onKeyUp`, debounce) and `isInFlight` (`aria-busy`).
  - Allowed `desktopSettings?: AirPointHudSettings | null;` in `DyneStudioProps`.
  - Standardized honest host status: `"HOST CONNECTED"`, `"HOST OFFLINE · LAST KNOWN SETTINGS"`, and `"HOST OFFLINE · SETTINGS UNSYNCED"`.
  - Added `aria-label="Dyne Studio"` to `<h1>`.
  - Restricted `isTextureActive` to Surface and texture adjust views, eliminating dark background blocks on top-level Material rings.
- **Why**: Fixes P0 defects 4 and 5; fixes P1 defects 6, 7, and 8; eliminates stale-write races and ensures 100% test agreement.

### 4. `src/components/air-point/dyne-studio/capsule-adjustment-track.tsx`
- **Before**: Continuous pointer moves triggered immediate `onChange` calls directly to host mutation callbacks without release gating.
- **After**: Maintained local track state during drag gestures; committed changes on pointer release or keyboard release. Prevented event propagation to event swipe handlers during active drags.
- **Why**: Guarantees zero write storms to native Windows bridges while preserving 60 fps visual responsiveness.

### 5. `src/styles/dyne-studio.css`
- **Before**:
  - `.texture-preview-backdrop` had hard `border-radius: 70px`, heavy box-shadow, and fixed bounds creating an awkward dark block behind the Material ring.
  - `@media (max-width: 640px)` overrode `.central-capsule` to `left: 8%; width: 84%; top: 32%; height: 36%`, crushing ring slots on mobile.
  - Capsule navigation chevrons at `top: 50%` overlapped the rightmost segment ("Material") on mobile.
  - Typography in `.capsule-preview-on-capsule` was 10px.
- **After**:
  - Softened `.texture-preview-backdrop` to a radial glow with `filter: blur(14px)` and `border-radius: 9999px`.
  - Retained exact cavity alignment on mobile: `left: 24.42%; width: 51.16%; top: 38.33%; height: 23.34%`, with `.capsule-assembly` scaled to `min(344px, 96%)`.
  - Relocated mobile chevrons to `bottom: 6px; left: 8px; right: 8px;`, completely clear of all ring segments and indicator dots.
  - Raised all visible stage text to $\ge 12\text{px}$ (including preview tag at 12px and segment labels at 15px).
- **Why**: Fixes P0 defect 4, P1 defect 9, and P2 defects 10 and 11.

---

## 3. Executed Checks and Real Measurements

### A. TypeScript Typecheck
- **Command**: `npx tsc --noEmit`
- **Duration**: 7.2 s
- **Exit Code**: `0`
- **Result**: Zero type errors across the entire codebase.

### B. Production Build
- **Command**: `npm run build` (`vite build`)
- **Duration**: 4.72 s (Client: 2.48 s, Nitro SSR: 2.24 s)
- **Exit Code**: `0`
- **Result**: Clean build; assets and worker bundles generated successfully without warnings.

### C. Vitest Test Suite (Unit & Integration)
- **Command**: `npx vitest run`
- **Duration**: 7.02 s
- **Exit Code**: `0`
- **Results**: **14 test files passed, 135 tests passed, 0 failed (100% green)**
  - `src/test/dyne-studio-audit-verification.test.tsx` (7 tests): **Passed**
    - Gate 1 (ISS-01): Top-left slot renders with icon and label across all category rings
    - Gate 2 (ISS-02, ISS-03): Multi-line labels have adequate line-height and no divider collision
    - Gate 3 (ISS-04): Material category renders clean backdrop without hard-edged overlay block
    - Gate 4 (ISS-07): Host status renders honestly across connected, unsynced, and offline modes
    - Gate 5 (ISS-08): Host boundary strictly enforces allowlist and never writes appearance values
    - Gate 6 (ISS-09): Event switcher maintains independent appearance per event state
    - Gate 7 (ISS-10): All visible stage typography respects minimum 12px requirement
  - `src/test/dynamic-island-tab.test.tsx` (10 tests): **Passed**
  - `src/test/dyne-studio-integration.test.tsx` (17 tests): **Passed**
  - All existing engine and redesign regression test suites (101 tests): **Passed**

### D. Real Headless Browser Measurements (Edge via CDP & Puppeteer)
- **Command**: `node scripts/dyne-studio-audit-browser-suite.cjs`
- **Duration**: 42.1 s
- **Exit Code**: `0`
- **Viewports Measured**:

| Viewport | Center-Line Alignment Delta | Min Capsule Clearance | Min Stage Font Size | `elementFromPoint` at Label Centers | Touch Target Min Dimensions |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1440 × 900** (Desktop) | **0.02 px** (limit $\le 2\text{ px}$) | **24.05 px** (limit $\ge 8\text{ px}$) | **15.0 px** (limit $\ge 12\text{ px}$) | **True** (100% clear) | $154 \times 87\text{ px}$ |
| **1120 × 800** (Laptop) | **0.02 px** (limit $\le 2\text{ px}$) | **18.24 px** (limit $\ge 8\text{ px}$) | **15.0 px** (limit $\ge 12\text{ px}$) | **True** (100% clear) | $128 \times 72\text{ px}$ |
| **820 × 1180** (Tablet) | **0.01 px** (limit $\le 2\text{ px}$) | **10.86 px** (limit $\ge 8\text{ px}$) | **15.0 px** (limit $\ge 12\text{ px}$) | **True** (100% clear) | $96 \times 54\text{ px}$ |
| **390 × 844** (Mobile) | **0.02 px** (limit $\le 2\text{ px}$) | **8.46 px** (limit $\ge 8\text{ px}$) | **15.0 px** (limit $\ge 12\text{ px}$) | **True** (100% clear) | **$\ge 44 \times 44\text{ px}$** |

### E. Transition Sampler & Host Boundary Spying
- **Transition Blank Frames**: **0** (per-frame screencast observer confirmed capsule is persistently mounted with no empty ring frames).
- **Torture Test**: 10 rapid clicks at 40 ms spacing accepted without crash, layout shift, or NaN coordinates.
- **Host Appearance Leak Log**: **0 appearance writes** (monitored all outgoing `/api/settings` payloads; strictly 0 calls containing `accent`, `font`, `roundness`, `texture`, `weight`, `fontSize`, `glow`, or `intensity`).
- **Operational Duration Sliders**: Recorded 1 write to `island_notifications_enabled: false` upon user toggle; duration drags only committed on release.
- **60 FPS Screencast Recorded**: **466 frames** captured to `artifacts/dyne-studio-verification/evidence/recording/frames/`.
- **Interactive Screencast Viewer**: Generated `artifacts/dyne-studio-verification/evidence/recording/screen-recording.html`.
- **Layer Screenshots Captured**: 13 layer captures + 8 multi-viewport captures in `artifacts/dyne-studio-verification/evidence/screenshots/`.

---

## 4. Decisions Made

1. **Host Status Header Nomenclature**: Standardized on tripartite status wording:
   - Online & Synced: `"HOST CONNECTED"`
   - Offline with prior cache: `"HOST OFFLINE · LAST KNOWN SETTINGS"`
   - Offline & Unsynced: `"HOST OFFLINE · SETTINGS UNSYNCED"`  
   This unifies both the integration tests and the product contract.
2. **Two-Option Ring Geometry**: Chose horizontal splitting into Top Arch (`[0.7022, 0.2022]`) and Bottom Arch (`[0.2022, 0.7022]`) rather than vertical splitting. This guarantees that labels located at $(270, 118)$ and $(590, 118)$ are never traversed or bisected by divider lines.
3. **Mobile Chevrons Positioning**: On screens $\le 640\text{ px}$, moved switcher chevrons to `bottom: 6px; left: 8px; right: 8px;`. This avoids the semicircle apex where the ring reaches its maximum width, preventing any hit-test collision with "Material" or "Shape".
4. **Touch Target Expansion**: Utilized an invisible `<rect fill="transparent" pointerEvents="all" />` of $120 \times 120$ SVG units on each option. This provides a minimum $44 \times 44\text{ px}$ physical hit area on mobile without altering the crisp visual borders.
5. **Slider Release Commit**: Implemented local draft state for continuous slider drags, committing to host only on `pointerup`, `keyup`, or a 250 ms debounce, accompanied by `aria-busy` during in-flight mutations.

---

## 5. Remaining Risks & Live Windows Host Requirements

1. **Python Engine & Native Windows Overlay Service**:
   - Dyne Studio editor is completely verified and decoupled from the host backend.
   - When running on a live Windows machine, verify that `backend/server.py` and `backend/airpoint_service.py` are started, and the PySide6/WPF dynamic island overlay correctly receives the 6 allowed keys (`island_enabled`, `island_notifications_enabled`, `island_timer_enabled`, `island_autohide_enabled`, `island_hud_duration_s`, `island_completion_duration_s`).
2. **Countdown Badge Test Command**:
   - The "Test countdown" button issues `POST /api/control` with `{ "command": "test_countdown", "duration_s": 5 }`.
   - On live Windows, ensure the native overlay receives this signal and animates the countdown capsule HUD on the desktop.
3. **Live Telemetry SSE Connection**:
   - Verify that SSE events at `/api/events` stream live gesture telemetry without reconnect loops when the camera backend is active.

---

## 6. Plain Final Statement

- **Did `vite build` pass?** **YES** (exit code 0; 0 errors).
- **Did all unit/integration tests pass?** **YES** (14/14 test files passed; 135/135 tests passed, 0 failed).
- **Did the browser checks pass?** **YES** (all 4 viewports met all acceptance criteria; 0 appearance leaks; 0 transition empty frames; 466 screencast frames recorded).

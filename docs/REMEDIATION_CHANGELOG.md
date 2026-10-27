# AIR POINT — REMEDIATION CHANGELOG
**Target:** `C:\Users\loges\Downloads\air-point-control-center-redesign-verified`  
**Date:** 2026-10-15  
**Version:** 1.1.0-remediated  

All changes documented below were performed strictly within `air-point-control-center-redesign-verified`.

---

### Added
- **`src/test/live-tracking.test.tsx`:**
  - Restored full unit and regression test suite previously missing from candidate redesign.
  - Added test case for Python dictionary hand payload `{right: [...], left: null}`.
  - Added test case for array hand payload compatibility.
  - Added test cases for coordinate tuple parsing (`[x, y]` & `[x, y, z]`) and invalid coordinate rejection.
  - Added test cases for facial anchor normalization (`lip_center`, `lip_contour`, ears).
  - Preserved concentric target ring tests at landmark 8 with `.index-target-ring`.
- **`REMEDIATION_REPORT.md`:** Comprehensive engineering report documenting root causes, fixes, test metrics, and integration readiness.
- **`REMEDIATION_CHANGELOG.md`:** Chronological record of file modifications.

---

### Changed
- **`src/components/air-point/live-tracking-canvas.tsx`:**
  - Implemented `normalizeHandPayload(...)` dual-schema adapter supporting both Python dictionary and array representations safely.
  - Implemented `parseCoordinatePair(...)` and `normalizeFacePayload(...)` preventing `NaN` coordinate emissions on tuple/array facial anchors.
  - Corrected SVG coordinate mapping to native `640 × 480` (`viewBox="0 0 640 480"` and `aspect-[4/3]`) to prevent spatial distortion over camera feed.
  - Restored `.index-target-ring` concentric halos and 4 cardinal ticks at landmark 8 when `is_locked` is active.
  - Added support for both `paused` and `running` boolean props for backward compatibility.
- **`src/components/air-point/engine.tsx`:**
  - Converted index-signature property accesses (`settings["sensitivity"]`, `settings["smoothing"]`, `settings["hold"]`, `settings["enabled"]`, `ev["time"]`, `ev["action"]`, `ev["event"]`) to bracket notation to satisfy strict `noPropertyAccessFromIndexSignature`.
- **`src/lib/air-point-model.ts`:**
  - Updated `sanitizeUIPreferences` to use safe bracket access on parsed `Record<string, unknown>` for `theme`, `accent`, `density`, `reducedMotion`, and `feedbackDuration`.
- **`src/routes/gestures.tsx`:**
  - Imported `type GestureSpec`.
  - Added explicit typed fallback `FALLBACK_GESTURE: GestureSpec`.
  - Typed `selectedGesture: GestureSpec` strictly, resolving 13 potential undefined errors under `noUncheckedIndexedAccess`.
- **`src/routes/index.tsx`:**
  - Forwarded `trackingStatus` and `pointerOwner` props to `LiveTrackingCanvas`.

---

### Verification
- `npx vitest run`: **24 / 24 Tests Passed (100%)**
- `npx tsc --noEmit`: **0 Compiler Errors (Strict Mode Pass)**
- `npm run build`: **Production Bundle Success (Vite + Nitro SSR)**
- Protected repositories (`air_point_clean`, `Air_Point_Control_Center_Refined`, `keen-carson`): **Untouched**

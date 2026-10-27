# DYNE STUDIO — CONTEXT BUNDLE FILE MANIFEST

This manifest provides a comprehensive catalog of every file included in the curated context bundle for **Dyne Studio** under `artifacts/dyne-studio-discovery/source/` and the archive `dyne-studio-context-bundle.zip`.

---

## 1. MANIFEST TABLE

| # | Repository-Relative Path | Category | Purpose / Relevance to Dyne Studio | Included Scope |
| :- | :--- | :--- | :--- | :--- |
| 1 | `frontend/src/routes/island.tsx` | Frontend Logic / Route | Current Dynamic Island page containing preview simulations, 3D capsule stage, and HUD settings controls. | Full |
| 2 | `frontend/src/routes/__root.tsx` | Frontend Logic / Layout | Root TanStack Router layout wrapping all routes with `AirPointEngineProvider` and `DesktopShell`. | Full |
| 3 | `frontend/src/routes/index.tsx` | Frontend Logic / Route | Overview route showing live camera, tracking status, and primary status indicators. | Full |
| 4 | `frontend/src/components/air-point/dynamic-island.tsx` | Frontend UI Component | Classic 2D desktop HUD pill preview component showing volume, mute, and countdown badges. | Full |
| 5 | `frontend/src/components/air-point/capsule/types.ts` | Shared Types | Defines `CapsuleState`, `CapsuleAccent`, `FIN_DEPLOYMENT_ANGLES`, `FinPosture`, and component props. | Full |
| 6 | `frontend/src/components/air-point/capsule/CapsuleBody.tsx` | Frontend UI Component | Central metallic chassis component with titanium bevels, docking collars, and status aperture. | Full |
| 7 | `frontend/src/components/air-point/capsule/CapsuleStage.tsx` | Frontend UI Component | 3D perspective viewport container with 1200px depth, volumetric lighting rigs, and plinth. | Full |
| 8 | `frontend/src/components/air-point/capsule/MechanicalFin.tsx` | Frontend UI Component | Articulated metallic wing assembly with 6 structural/vector layers, hinge knuckle, and LED conduit. | Full |
| 9 | `frontend/src/components/air-point/capsule/index.ts` | Frontend Module / Barrel | Public export barrel for all capsule foundation components, kinematics helpers, and types. | Full |
| 10 | `frontend/src/components/air-point/engine.tsx` | Frontend State / Bridge | Central React context provider, SSE stream listener, status polling (1500ms), and settings mutator. | Full |
| 11 | `frontend/src/components/air-point/shell.tsx` | Frontend UI Shell | Windows desktop application shell with titlebar, sidebar navigation tabs, and system status badges. | Full |
| 12 | `frontend/src/styles.css` | Styling / Design Tokens | Tailwind CSS v4 setup, Nothing Glass theme tokens, 3D capsule viewport rules, and fin keyframes. | Full |
| 13 | `frontend/src/lib/air-point-model.ts` | Shared Data Models / Types | TypeScript definitions for `DynamicIslandSettings`, `DynamicIslandState`, duration limits, and presets. | Full |
| 14 | `frontend/src/test/capsule.test.tsx` | Frontend Tests | Vitest suite for `CapsuleBody`, `CapsuleStage`, and `MechanicalFin` kinematics across states. | Full |
| 15 | `frontend/src/test/dynamic-island-tab.test.tsx` | Frontend Tests | Vitest suite verifying Dynamic Island route matching, settings mutations, and countdown tests. | Full |
| 16 | `frontend/package.json` | Configuration / Deps | Project package definitions, npm scripts, and dependencies (React 19, TanStack Start, Vite, Tailwind v4). | Full |
| 17 | `frontend/vite.config.ts` | Configuration / Build | Vite bundler configuration including TanStack Router and Tailwind CSS plugins. | Full |
| 18 | `frontend/vitest.config.ts` | Configuration / Test | Vitest configuration with jsdom environment, test timeout (10000ms), and path aliases. | Full |
| 19 | `frontend/tsconfig.json` | Configuration / TypeScript | TypeScript compiler options, JSX configuration, and path mapping aliases (`@/*`). | Full |
| 20 | `backend/core/control_server.py` | Host Contract / Server | Zero-dependency local HTTP/SSE bridge (port 8765), token authentication, `/api/settings`, `/api/control`. | Full |
| 21 | `backend/core/overlay.py` | Native Host / Renderer | Win32 desktop overlay HUD using Tkinter + `ctypes.windll.user32`, rendering Dynamic Island capsules. | Full |
| 22 | `backend/core/power_state_machine.py` | Host Logic / State Machine | Pure two-state PowerStateManager (`NORMAL` vs `POWER_SAVE`) with 120s inactivity timer. | Full |
| 23 | `backend/config.py` | Host Configuration | Global Python configuration constants, HUD defaults, animation speeds, and threshold limits. | Full |
| 24 | `backend/settings.json` | Host Configuration / Data | Real persisted configuration file storing user settings, gesture toggles, and HUD parameters. | Full |
| 25 | `scripts/start_airpoint.ps1` | Automation / Script | PowerShell launcher for AirPoint engine and Control Center frontend with environment setup. | Full |
| 26 | `scripts/stop_airpoint.ps1` | Automation / Script | PowerShell script to safely stop running Python and Node background processes. | Full |
| 27 | `scripts/run_checks.ps1` | Automation / Verification | Automated validation script running test guards, frontend lint/build, and test suites. | Full |
| 28 | `README.md` | Documentation | Repository overview, architecture diagrams, installation instructions, and feature guide. | Full |

---

## 2. EXCLUSION POLICY

The following directories and artifacts are deliberately excluded from this curated context bundle to keep the payload clean, secure, and focused:
- `frontend/node_modules/`: Package binaries and cached modules (reproducible via `npm install`).
- `frontend/.output/` & `frontend/dist/`: Ephemeral build outputs.
- `backend/.venv/`: Python virtual environment binaries (reproducible via `requirements.txt`).
- `backend/__pycache__/` & `.pytest_cache/`: Python compilation bytecode and test cache.
- Local secrets, private keys, `.bridge_token`, or personal user environment files.

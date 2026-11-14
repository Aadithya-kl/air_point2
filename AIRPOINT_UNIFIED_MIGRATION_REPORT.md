# AIRPOINT — UNIFIED MIGRATION REPORT

**Date:** 2026-11-02
**Canonical repository:** `C:\Users\loges\Documents\air_point2_audit` (branch `fix/p0-native-input-safety`, HEAD `4672829`, nothing committed by this work)
**Legacy repository:** `C:\Users\loges\Documents\antigravity\AirPoint` (same HEAD; read-only; untouched)
**Result:** one AirPoint in the canonical repository: one Python engine, one React Control Center, one Dyne event system feeding the desktop capsule and the Control Center island, one launcher. Every automated gate passes. Physical behaviour is **not** validated by this report; see §15.

---

## 1. Source repositories and their initial states

| | Canonical (A) | Legacy (B) |
|---|---|---|
| Path | `C:\Users\loges\Documents\air_point2_audit` | `C:\Users\loges\Documents\antigravity\AirPoint` |
| Branch / HEAD | `fix/p0-native-input-safety` / `4672829` | `main` / `4672829` (identical commit and history) |
| Working tree at start | 20 modified + 17 untracked files (P0 native-input safety, Phase 1 drag reliability, debug start-up fix, Wakanda lock fix, documents) | 2 modified (`backend/core/debug_overlay.py`, `backend/main.py`) + 6 untracked (four P0.2 reports, an older `test_debug_overlay_send.py`, `tools/p0_2/` sandbox scripts) |
| Runtime-only state | canonical venv (Python 3.14.3, mediapipe 1.2.0) | venv with `airpoint_dev.pth` leak, `backend/settings.json` (`island_enabled: false`), screenshots, `backup_phase3_frozen/` |
| Baseline tests | backend 443/443 guarded, Vitest 135/135, tsc clean, build OK | not run (venv unusable for this repository) |

Because both trees share the same commit, the "legacy full product" (frontend, Dyne Studio, scripts, assets) was already in the canonical repository byte for byte. Details: `AIRPOINT_UNIFIED_MIGRATION_INVENTORY.md`.

## 2. Backup verification

| Backup | Location | Verification |
|---|---|---|
| P0 working-tree backup (existing) | `C:\Users\loges\Documents\air_point2_audit_backups\p0_worktree_backup_20261102_190141\` | 12/12 files match their SHA-256 manifest (re-checked at Stage A) |
| Migration checkpoint (new, Stage A) | `C:\Users\loges\Documents\air_point2_audit_backups\migration_checkpoint_20261102_214947\` | `repo_a/`: 20 modified + 17 untracked files, HEAD versions, `unstaged.patch`, status/log, 37/37 hashes match; `repo_b/`: 2 modified + 6 untracked files, 10/10 hashes match, plus B's `settings.json` |
| Post-migration checkpoint (new, Stage H) | `C:\Users\loges\Documents\air_point2_audit_backups\migration_result_<stamp>\` | full copies of every modified and untracked file of the canonical tree with a SHA-256 manifest (created at the end of this work; path printed in the hand-off message) |

No destructive git operation was used at any point (`reset --hard`, `clean`, `checkout -- .`, branch switch, merge, rebase, commit, push: none). The only `git checkout --` was the single-file restore of the generated `frontend/src/routeTree.gen.ts` after frontend tooling, as `CLAUDE.md` prescribes.

## 3. Features preserved from the canonical repository

Everything. In particular, untouched by rule: `backend/core/actuator.py`, `backend/core/gestures/drag_controller.py`, `backend/core/gestures/orchestrator.py`, `backend/config.py`, every gesture threshold, the release dwell (80 ms), tracking grace (150 ms), watchdog (250 ms), the pause/shutdown release path, the Wakanda safeguards, the test guard. The P0/P1/debug/Wakanda work (20 modified + 17 untracked files) is intact and still passes its suites (443 of the 471 backend tests are the pre-migration ones). Full capability list: `AIRPOINT_FEATURE_PARITY_MATRIX.md`.

## 4. Features migrated from the legacy repository

| Legacy item | Destination | Change |
|---|---|---|
| `tools/p0_2/{New,Reset,Verify}-AirPointP02Sandbox.ps1` | `tools/physical_sandbox/{New,Reset,Verify}-AirPointSandbox.ps1` + `README.md` | the generated sandbox README now resolves the repository, backend and script paths from the script location (`$RepoRoot`, `$BackendDir`, `$ToolsDir`); P0.2 naming generalised (`PHYSICAL_TEST_LOG.csv`); behaviour otherwise unchanged; parse-checked |
| Four `AIRPOINT_P0_2_*.md` reports | `docs/legacy_p0_2/` + index `README.md` | copied unchanged (hash verified) as historical reference; they record no physical result |
| Wider debug-HUD lines (legacy raised the truncation from 44 to 65 characters without widening the panel) | `backend/core/debug_overlay.py` | re-implemented properly: the panel width is measured from the longest line (`cv2.getTextSize`), capped at the frame width, the font shrinks to 0.34 only when needed, truncation uses measured widths |

## 5. Features merged from both

None required a line-by-line merge: the legacy `main.py` try/except import and its `test_debug_overlay_send.py` are superseded by the canonical F-26 fix and the canonical P0.3 test; the legacy SEND-mapping variant is covered by the canonical mapping. The HUD width is the only idea taken from the legacy edit (above).

## 6. Conflicts and decisions

| Conflict | Decision |
|---|---|
| Two `debug_overlay.py` edits | keep canonical mapping; adopt the width idea with a measured panel |
| Two debug-import fixes in `main.py` | keep canonical (diagnostic + tests) |
| Two `test_debug_overlay_send.py` | keep canonical (newer, isolated) |
| Legacy `settings.json` with `island_enabled: false` | not imported (it would hide the desktop capsule); a copy sits in the checkpoint; the Control Center toggle sets it in seconds |
| Launcher requirements versus the identical old script | rewritten in place (canonical path); the legacy workspace is never referenced |
| Frontend test workers crash under the default fork pool once the 15th test file exists | `vitest.config.ts` caps `maxWorkers` at 4 (documented; no test changed) |

## 7. Files created

`backend/core/events.py`, `backend/test_dyne_events.py`, `frontend/src/components/air-point/dyne-live-island.tsx`, `frontend/src/test/dyne-live-events.test.tsx`, `tools/physical_sandbox/` (3 scripts + README), `docs/legacy_p0_2/` (4 reports + README), `AIRPOINT_FEATURE_PARITY_MATRIX.md`, `AIRPOINT_UNIFIED_MIGRATION_INVENTORY.md`, this report.

## 8. Files modified

Backend: `core/control_server.py`, `core/overlay.py`, `main.py`, `core/gestures/screenshot.py`, `core/debug_overlay.py`.
Frontend: `src/lib/air-point-model.ts`, `src/components/air-point/engine.tsx`, `src/components/air-point/shell.tsx`, `src/routes/__root.tsx`, `src/routes/about.tsx`, `src/routes/index.tsx`, `src/routes/island.tsx`, `src/components/air-point/dyne-studio/dyne-studio.tsx`, `src/components/air-point/dyne-studio/studio.ts`, `src/components/air-point/dyne-studio/layered/host-adapter.ts`, `vitest.config.ts`.
Scripts and docs: `scripts/start_airpoint.ps1`, `scripts/stop_airpoint.ps1`, `.gitignore`, `CLAUDE.md`, `README.md`, `AIRPOINT_SYSTEM_ARCHITECTURE.md` (§1.3, §7, §8, §9, §10, §11, §12), `AIRPOINT_ENGINEERING_ROADMAP.md` (Phases 3–5).

### What changed, by stage

- **Stage C (backend):** sandbox tooling and reports migrated; HUD width measured; `ScreenshotController.capture_result_cb` (the only truthful place for a "captured" event).
- **Stage E (Dyne, backend):** `core/events.py` — `DyneEvent` schema, `EVENT_CATALOGUE` (24 types), `EventDispatcher` (monotonic ids, session token, ring of 50, thread-safe fan-out), `DragEventTracker` (read-only transition observer), `VolumeEventCoalescer`, Dyne position/appearance sanitisers. `RuntimeState` owns the dispatcher: `publish_event`, legacy `add_event` shim, status `events` (10) + `event_session` + `last_event_id`, `GET /api/events/history`, SSE `id:` lines with `Last-Event-ID` / `?after` replay, token-authenticated `/api/control {"action": "exit"}`, persisted `island_position` and `island_appearance`. `main.py` publishes engine start/pause/resume/stop, tracking, screenshot, app, audio (coalesced volume), drag, Wakanda/lock and power events after the real outcome; the Tk overlay subscribes (`handle_event`) and gates every toast by the Dyne switches (F-15), honours position and accent, and draws nothing while the HUD is off.
- **Stage D/E (frontend):** `BRIDGE_BASE_URL` from `VITE_AIRPOINT_BRIDGE_URL` (loopback-only); `parseDyneEvent` / `mergeEvents`; provider keeps a merged, deduplicated feed of 50, exposes `eventStream`, `liveNotification`, `islandPosition`, `islandAppearance`; `DyneLiveIsland` mounted in the shell shows real events only (newer than the history present at connect, not `low` priority, honouring the host switches and duration); Dyne Studio gained Position, "Apply this look", "Load live look" and the applied-look status pill; About/shell derive host text from the resolved bridge URL and show the stream state; the anti-flash localStorage key matches; Overview activity shows title, message, source and grouping.
- **Stage F (launcher):** `start_airpoint.ps1` and `stop_airpoint.ps1` rewritten (§12).

## 9. Files intentionally not migrated

`backend/main.py` and `backend/core/debug_overlay.py` legacy edits (superseded), legacy `backend/test_debug_overlay_send.py` (older), `backend/settings.json` (user data; copy in the checkpoint), `backend/screenshots/`, `backend/backup_phase3_frozen/`, the legacy virtual environment.

## 10. Backend test results

| Run | Command | Result |
|---|---|---|
| Full guarded discovery | `AIRPOINT_SETTINGS_PATH=:memory: AIRPOINT_ENABLE_TEST_GUARD=1 AIRPOINT_DISABLE_REAL_LOCK=1 .venv\Scripts\python -m unittest discover -s . -p "test_*.py"` | **471 run, 471 pass** (20.1 s); 443 pre-migration + 28 in `test_dyne_events.py` |
| Targeted modules after each edit | debug HUD, screenshot, control server, overlay, power notifications | all pass |
| Hardware-free preflight | `backend\.venv\Scripts\python.exe backend\preflight_physical_test.py` | 11 ok, 0 warnings, 0 failed: READY |

`test_dyne_events.py` covers: dispatcher schema/ids/history/fan-out/thread safety; drag transitions (started, completed, released on tracking loss/pause, failed on LEFTDOWN/LEFTUP errors, silent cancels and jitter recovery); volume coalescing (≤ 5 events per second of 50 ms ticks + one final); position/appearance validation; `RuntimeState` publish + legacy shim, snapshot fields, persistence round trip, exit callback; HTTP history endpoint, SSE `id:` lines and Last-Event-ID replay without duplicates, `exit` action; Tk overlay geometry per position, accent, Dyne switch gating, `handle_event` mapping, dispatcher subscription; screenshot result truth (success path / failure path, result after the overlay re-show). The mocked workstation lock and the test guard remain in force; no native input, camera or lock is used.

## 11. Frontend test results

| Gate | Result |
|---|---|
| `npx tsc --noEmit` | clean |
| `npx vitest run` | **15 files, 144 tests, all pass** (135 pre-migration + 9 in `dyne-live-events.test.tsx`); with the default one-fork-per-CPU pool the 15-file suite crashed workers on this 16-CPU / 15.7 GB machine, so `vitest.config.ts` now sets `maxWorkers: 4` (also verified with `--pool=threads` and `--no-file-parallelism`) |
| `npm run build` | succeeds (Nitro / Cloudflare target); `src/routeTree.gen.ts` restored afterwards |

`dyne-live-events.test.tsx` covers: `resolveBridgeBaseUrl` (loopback only), `parseDyneEvent` (unified and legacy payloads), `mergeEvents` (dedupe, order, bound), appearance validation, the live island raised only by events newer than the history present at connect and dismissible, silence when the host notifications switch is off (event still recorded), Server-Sent Events delivered to the feed and island with duplicate suppression and `eventStream` state, preview-versus-live labelling, and the Studio apply/load look flow with no implicit host writes.

## 12. Launcher verification

| Check | Result |
|---|---|
| PowerShell parse (`Parser::ParseFile`) of `start_airpoint.ps1`, `stop_airpoint.ps1`, `run_checks.ps1` and the three sandbox scripts | no errors |
| `.\scripts\start_airpoint.ps1 -Mode full -DryRun` | canonical root confirmed; Python 3.14.3 from `backend\.venv`; engine imports and both model bundles present; Node v24.14.0, npm 11.9.0, `node_modules` present; no recorded instance; ports 8765 and 8080 free; exact commands printed; exit 0; nothing started or written |
| `.\scripts\start_airpoint.ps1 -Mode frontend-only` (twice, ports 8080 and 8081) | dev server reached HTTP 200 in a few seconds; PID record written with the cmd/npm PID and four node children; logs captured (`logs\frontend_*.log`) |
| `.\scripts\stop_airpoint.ps1` | first cycle revealed that npm's own node process carries no repository path in its command line and was left running (it exited by itself); the ownership rule was extended (live descendants of the recorded root, and recorded children created within two minutes of the service start, are ours); second cycle stopped every recorded process, left no process, freed the port, removed the PID file |
| `-Mode full` / `backend-only` / `control-server` | **not run by the agent** (they open the camera and inject input). The user's first full-mode launch (22:50) failed its health check and exposed repeated watchdog releases; both root causes and corrections are in `AIRPOINT_POST_MIGRATION_LAUNCH_DIAGNOSTIC_REPORT.md` (venv launcher stub versus engine child; watchdog evaluated before the controller's refresh). The backend branch is now covered by `scripts/launcher_selftest.ps1` against a real `ControlServer` |

Launcher requirements 1–16 from the brief map to: root resolution and marker check (1, 3), required venv python (2), prerequisite checks (4), port owner report (5), backend/frontend start (6, 7), PID record with node children (8), bridge health through `bridge_info.json` + `/api/status` (9), HTTP readiness (10), status table (11), duplicate refusal (12), ownership-verified stop (13), no blanket kills (14), cleanup on partial failure (15), log capture (16).

## 13. Integration verification

| Brief item | How it was verified | Boundary |
|---|---|---|
| Backend health appears in the Control Center | status pill/About derive their host text from the resolved bridge URL; `/api/status` consumed by the provider (Vitest, mocked fetch); launcher health check against a live bridge is exercised only in dry run/backend branch unexecuted | no live engine run by the agent |
| A real backend event reaches the React subscriber | backend: live `ControlServer` + SSE replay test (`test_dyne_events.py` §6); frontend: SSE fixture in the unified schema reaches the feed and the island (`dyne-live-events.test.tsx`) | the two halves are joined by the documented schema, not by a browser against a live engine |
| The Dyne notification island reacts | `DyneLiveIsland` renders the fixture event with `data-live="true"` | fixture, not a webcam gesture |
| Settings synchronise and persist | `island_position` / `island_appearance` round trip through `settings.json` and reload (`test_dyne_events.py` §5); provider applies them from the status payload (Vitest) | — |
| Bridge disconnects and reconnects | `EventSource` resends `Last-Event-ID`; the bridge replays the missed ring without duplicates (backend test); `eventStream` reports `reconnecting`; a changed session rebuilds the feed from history | browser reconnection timing not measured |
| Shutdown cleans up its own services | frontend-only cycle (§12); engine graceful exit via `/api/control exit` tested on a live `ControlServer` with a stub callback | engine process exit not observed by the agent |

## 14. Known limitations

- Physical behaviour (cursor, clicks, drags, Wakanda lock, desktop capsule position/accent, the full-mode launcher with the camera) is unverified by this work; see §15.
- Per-event-type notification preferences are not implemented (one global `island_notifications_enabled`); no "scale" or sound settings.
- Clicks, zoom and the two-hand shortcuts publish no events (they have no HUD feedback today either).
- The Tk overlay honours position and accent colour of the applied look; shape, font and material apply to the React island only.
- Bridge discovery works for launcher-started runs; a dev server started by hand needs `VITE_AIRPOINT_BRIDGE_URL`; the backend does not serve the built UI.
- Vite's `--host 127.0.0.1 --strictPort` flags were validated once in frontend-only mode; the lovable plugin printed only a deprecation notice about `vite-tsconfig-paths`.
- `maxWorkers: 4` in `vitest.config.ts` is a machine-driven cap, not a test fix.
- A hidden backend console (log files instead) is the launcher default; use `-ShowConsoles` to see the engine log live.
- Roadmap Phase 2 (pointer instrumentation, F-09, F-24) and the Phase 4 information-architecture pass remain open.
- `scripts/dyne-studio-audit-browser-suite.cjs` (tracked at HEAD, from the earlier Dyne Studio audit) still hard-codes a puppeteer install and an output folder under the legacy `antigravity` tree. It is not part of the runtime, the launcher or any verification gate; it was left as a historical audit artefact and should be deleted or re-pointed in the Phase 4 clean-up. The remaining `antigravity` mentions are documents and the preflight's deliberate `sys.path` leak check.

## 15. Physical testing requirements (user)

1. Run `backend\.venv\Scripts\python.exe backend\preflight_physical_test.py` (READY today).
2. Create the sandbox: `powershell -ExecutionPolicy Bypass -File .\tools\physical_sandbox\New-AirPointSandbox.ps1`.
3. Start the product: `.\scripts\start_airpoint.ps1 -Mode full -DebugHud` and open `http://localhost:8080`.
4. Observe: Overview shows BRIDGE ONLINE with the discovered host; the Recent Activity feed shows `AirPoint started`; moving a hand into view raises the live island (`Hand acquired`) and the desktop capsule stays quiet for the first acquisition; covering the camera for 0.35 s raises `Hand lost` on both surfaces.
5. Perform the drag procedures T1–T12 of `AIRPOINT_PHASE_1_PHYSICAL_TEST_PLAN.md` and record them in `AIRPOINT_PHASE_1_PHYSICAL_RESULTS.md` (still all NOT RUN); the live island should show `Drag started` / `Drag completed` and a `Drag failed` notice only on an unconfirmed release.
6. Perform one deliberate Wakanda Forever hold and record whether the desktop locked; the island shows `Lock request accepted/failed` (API result, never "locked").
7. In Dyne Studio, change Position to bottom centre and apply a look; confirm the desktop capsule moves and takes the accent colour, and that both survive `stop_airpoint.ps1` + restart.
8. Stop with `.\scripts\stop_airpoint.ps1` and confirm the engine exited gracefully (log line `Graceful exit requested via the control bridge`) and no process remained.

## 16. Remaining engineering roadmap

Phase 2 (pointer instrumentation and tuning, F-09, F-24), Phase 3 remainder (per-event-type preferences, events for clicks/zoom/shortcuts, backend-served UI for port-independent discovery), Phase 4 (information architecture and dead-control removal), Phase 5 (physical results, performance report). See `AIRPOINT_ENGINEERING_ROADMAP.md`.

---

**Rollback point:** the migration checkpoint in §2 restores the pre-migration working tree file by file; the post-migration checkpoint restores this result. Git history is unchanged (`4672829`); nothing was committed or pushed.

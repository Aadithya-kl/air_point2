# AIRPOINT — UNIFIED MIGRATION INVENTORY (STAGE A)

**Date:** 2026-11-02
**Purpose:** record the actual state of both AirPoint workspaces before any integration change, verify the protection of uncommitted work, and define the file migration plan and the conflict decisions. Every statement below was produced by running `git` and file commands against both trees; nothing is assumed from earlier reports.

---

## 1. Repository comparison

| Item | Repository A (canonical) | Repository B (legacy) |
|---|---|---|
| Path | `C:\Users\loges\Documents\air_point2_audit` | `C:\Users\loges\Documents\antigravity\AirPoint` |
| Remote | `https://github.com/Aadithya-kl/air_point2.git` | same remote |
| Branch | `fix/p0-native-input-safety` (local; `main` also present) | `main` (also local branch `backup-pre-audit`) |
| HEAD | `4672829` docs: add AIRPOINT2_BACKEND_PUBLICATION_REPORT.md | `4672829` (identical commit) |
| Common history | identical: `4672829 ← 75547fe ← 2a458bd ← 4db1058 ← 9ce81fe` | identical |
| Staged changes | none | none |
| Modified tracked files | 20 (P0 + Phase 1 + debug + Wakanda work; listed in §2) | 2: `backend/core/debug_overlay.py`, `backend/main.py` |
| Untracked files | 17 (new tests, documents, preflight) | 6: four P0.2 reports, `backend/test_debug_overlay_send.py`, `tools/p0_2/` (3 scripts) |
| Ignored state that matters | `backend/.venv` (Python 3.14.3, mediapipe 1.2.0), `frontend/node_modules` | `backend/.venv` (carries `airpoint_dev.pth` pointing at B), `backend/settings.json` (user preferences), `backend/screenshots/` (10 captures from 2026-10-10), `backend/backup_phase3_frozen/` (17-file older engine snapshot) |
| Other worktrees | `C:\Users\loges\.local\share\kilo\worktree-pool\air-point2-audit-5eba18e6fa28\granite-hat` (detached at `4672829`, clean; tool-managed, untouched) | none |
| Stash | none | none |
| Frontend | 148 tracked files, 1 modified (`src/lib/air-point-model.ts`, Wakanda default) | 148 tracked files, unmodified |
| Scripts | `run_checks.ps1` modified (guard variables); launcher/stop scripts unmodified | all unmodified (user ran `start_airpoint.ps1 -Mode full` from here) |

**Conclusion:** the two workspaces are the same commit. Everything the brief attributes to the "legacy full-product workspace" (frontend, Dyne Studio, scripts, assets, docs) is already tracked in the canonical repository byte for byte. The legacy tree's unique content is small and listed in §3.

## 2. Canonical working tree (repository A) at the start of migration

Modified (20): `README.md`, `backend/config.py`, `backend/core/actuator.py`, `backend/core/control_server.py`, `backend/core/debug_overlay.py`, `backend/core/gestures/drag_controller.py`, `backend/core/gestures/orchestrator.py`, `backend/core/gestures/wakanda_gesture.py`, `backend/core/overlay.py`, `backend/main.py`, `backend/test_control_server.py`, `backend/test_drag_and_drop_pipeline.py`, `backend/test_drag_safety.py`, `backend/test_guard.py`, `backend/test_left_hand_drag_reliability.py`, `backend/test_phase2_left_hand.py`, `backend/test_phase6_drag.py`, `backend/test_wakanda_gesture.py`, `frontend/src/lib/air-point-model.ts`, `scripts/run_checks.ps1`.

Untracked (17): `AIRPOINT_ENGINEERING_ROADMAP.md`, `AIRPOINT_INDEPENDENT_ARCHITECTURE_REVIEW.md`, `AIRPOINT_P0_3_REGRESSION_VALIDATION_REPORT.md`, `AIRPOINT_P0_CODE_REVIEW.md`, `AIRPOINT_PHASE_1_IMPLEMENTATION_REPORT.md`, `AIRPOINT_PHASE_1_PHYSICAL_RESULTS.md`, `AIRPOINT_PHASE_1_PHYSICAL_TEST_PLAN.md`, `AIRPOINT_PHASE_P0_IMPLEMENTATION_REPORT.md`, `AIRPOINT_SYSTEM_ARCHITECTURE.md`, `AIRPOINT_WAKANDA_GESTURE_FIX_REPORT.md`, `CLAUDE.md`, `backend/preflight_physical_test.py`, `backend/test_debug_hud_startup.py`, `backend/test_debug_overlay_send.py`, `backend/test_native_input_safety.py`, `backend/test_phase1_drag_reliability.py`, `backend/test_wakanda_lock_fix.py`.

Baseline test state at the start of migration: backend 443/443 (guarded discovery), frontend typecheck clean, Vitest 135/135, production build passing.

## 3. Legacy working tree (repository B): unique content

| Item | What it is | Assessment |
|---|---|---|
| `backend/core/debug_overlay.py` (modified) | SEND field mapping that also accepts enum `.name`/strings and treats `_last_drag_error == "SENDINPUT_LEFTUP_FAILED"` as `UNCERTAIN`; HUD line truncation widened from 44 to 65 characters without widening the 420 px panel | DIVERGENT. The canonical P0 mapping already covers every `SendInputResult` value; the extra error condition is redundant because a failed LEFTUP leaves `_last_send_input_result` as UNCONFIRMED. The wider lines are useful (the canonical `WAKANDA` line is truncated at 44) but need a wider panel. **Decision: merge the width idea with a matching panel width; do not copy the mapping.** |
| `backend/main.py` (modified) | `try: from core.debug_overlay import draw_debug_frame / except ImportError: None` | OBSOLETE. The canonical F-26 fix does the same with a diagnostic and a runtime refusal path, plus tests. |
| `backend/test_debug_overlay_send.py` (untracked, 8 tests) | Earlier version of the SEND-mapping test; its mock orchestrator exposes `_left_proc`, a name the overlay never reads | OBSOLETE. The canonical P0.3 version (9 tests, no `sys.modules` use) stays. |
| `tools/p0_2/New-AirPointP02Sandbox.ps1`, `Reset-…`, `Verify-…` | Create a disposable `C:\AirPoint-Sandbox` with synthetic files/folders and a SHA-256 manifest, reset moved assets without deleting, verify moves by hash. The generated README hard-codes the legacy repository path | LEGACY ONLY, valuable for the physical drag plan. **Decision: migrate to `tools/physical_sandbox/` with the path references resolved from the canonical tree.** |
| `AIRPOINT_P0_2_2_REPOSITORY_RECONCILIATION_REPORT.md`, `AIRPOINT_P0_2_PHYSICAL_TEST_GUIDE.md`, `AIRPOINT_P0_2_PREFLIGHT_REPORT.md`, `AIRPOINT_P0_2_TEST_REPORT.md` | Reports from the P0.2 work: how the two checkouts desynchronised (the P0 work was never committed), a physical test guide, a preflight audit, and a test-report template whose physical rows are all `NOT RUN` | Historical reference; no physical result recorded. **Decision: copy to `docs/legacy_p0_2/` unchanged.** |
| `backend/settings.json` (ignored) | User preferences saved by the legacy engine on 2026-11-02 13:36: all gestures on including `wakanda-forever`, `island_enabled: false`, `island_timer_enabled: false`, `island_hud_duration_s: 150`, defaults otherwise | User data, not code. **Decision: not copied automatically** (it would hide the desktop overlay, which may or may not be intended); a copy is in the checkpoint and §6 explains how to adopt it. |
| `backend/screenshots/*.png` (ignored) | Ten screenshot-gesture captures from 2026-10-10 | User artefacts; not migrated. |
| `backend/backup_phase3_frozen/` (ignored) | 17-file snapshot of an older engine (phase 3) | Superseded by the canonical history and backups; not migrated. |
| `backend/.venv` | Python 3.14.3 with mediapipe 1.1.1 and the `airpoint_dev.pth` leak | Not used; the canonical venv exists. |

Nothing in the legacy frontend, scripts, assets or docs differs from the canonical tree.

## 4. P0/P1 protection verification

| Check | Result |
|---|---|
| Existing P0 backup `p0_worktree_backup_20261102_190141` | intact: 12/12 files match their saved SHA-256 manifest (recomputed 2026-11-02 21:49) |
| New migration checkpoint | `C:\Users\loges\Documents\air_point2_audit_backups\migration_checkpoint_20261102_214947\` |
| Checkpoint contents | `repo_a/`: HEAD, branch, remotes, `git status`, `git log`, `unstaged.patch`, `staged.patch` (empty), full copies of the 20 modified + 17 untracked files, HEAD versions of the modified files, `SHA256_source.txt` / `SHA256_checkpoint.txt` (37/37 match). `repo_b/`: the same for its 2 modified + 6 untracked files (10/10 match), plus `runtime_state/backend/settings.json` |
| Destructive git operations used | none (`reset --hard`, `clean`, `checkout -- .`, branch switches, merges, commits, pushes: none) |
| Legacy repository | read only; no file in it was modified |

Roll-back point: the checkpoint above plus the P0 backup. Restoring the canonical working tree means copying files back from `repo_a/modified_files` and `repo_a/untracked_files`.

## 5. File migration plan

| Order | Source (B) | Destination (A) | Action | Stage |
|---|---|---|---|---|
| 1 | `tools/p0_2/*.ps1` | `tools/physical_sandbox/*.ps1` | copy, replace the hard-coded legacy paths in the generated README with the canonical repository resolved from the script location; parse-check | C |
| 2 | four `AIRPOINT_P0_2_*.md` | `docs/legacy_p0_2/` | copy unchanged, add a one-paragraph index | C |
| 3 | `backend/core/debug_overlay.py` (truncation width) | canonical `debug_overlay.py` | widen the HUD panel and the truncation together (not a copy) | C |
| — | `backend/main.py` try/except import | — | not migrated (superseded by F-26) | — |
| — | `backend/test_debug_overlay_send.py` | — | not migrated (canonical version is newer and isolated) | — |
| — | `backend/settings.json` | — | not migrated automatically; see §6 | — |
| — | `backend/backup_phase3_frozen/`, `screenshots/`, `.venv` | — | not migrated | — |

Everything else the brief lists for migration (frontend, Dyne Studio, launcher scripts, assets, control server) already exists in the canonical repository; those stages (D, E, F) are integration and improvement work on the canonical files, not file migration.

## 6. Conflict report and decisions

| Conflict | Decision | Reason |
|---|---|---|
| Two `debug_overlay.py` SEND mappings | keep the canonical P0 mapping | it is tested (`test_debug_overlay_send.py`, 9 tests) and the legacy extra condition is redundant |
| Two `main.py` fixes for the debug import | keep the canonical F-26 fix | it adds a diagnostic path and three regression tests |
| Two `test_debug_overlay_send.py` versions | keep the canonical | the legacy one asserts against an attribute the overlay does not read |
| Legacy `settings.json` (`island_enabled: false`) versus canonical defaults (overlay on) | do not import silently | the setting hides the desktop overlay; if that was deliberate, copy `migration_checkpoint_…\repo_b\runtime_state\backend\settings.json` to `backend\settings.json` before launching, or set it in the Control Center |
| Legacy launcher (`-Mode full` works for the user) versus the launcher requirements in the brief | upgrade the canonical copy of the same script in place | the scripts are identical; the gaps (prerequisite checks, health and readiness verification, log capture, cleanup on partial failure, ownership checks before killing) are improvements, not conflicts |
| Legacy venv with mediapipe 1.1.1 versus canonical venv with 1.2.0 | canonical venv | the canonical preflight loads both models and runs them; the legacy venv leaks its tree onto `sys.path` |
| Branch names (`main` in B, `fix/p0-native-input-safety` in A) | unchanged | no branch operation is authorised; both point at `4672829` |

No conflict puts user work at risk: every file that would be changed by the migration exists in the checkpoint with its hash.

## 7. Files created and modified by the migration (Stages C–H, 2026-11-02)

Created: `backend/core/events.py`, `backend/test_dyne_events.py`, `frontend/src/components/air-point/dyne-live-island.tsx`, `frontend/src/test/dyne-live-events.test.tsx`, `tools/physical_sandbox/{New,Reset,Verify}-AirPointSandbox.ps1`, `tools/physical_sandbox/README.md`, `docs/legacy_p0_2/` (four P0.2 reports, unchanged, plus `README.md`), `AIRPOINT_FEATURE_PARITY_MATRIX.md`, `AIRPOINT_UNIFIED_MIGRATION_INVENTORY.md`, `AIRPOINT_UNIFIED_MIGRATION_REPORT.md`.

Modified: `backend/core/control_server.py` (dispatcher, SSE ids/replay, history endpoint, `exit` action, `island_position`/`island_appearance`), `backend/core/overlay.py` (dispatcher subscriber, Dyne switch gating, position, accent, `show_notice`), `backend/main.py` (event producers, drag tracker, volume coalescer, exit flag, early `overlay`/`bridge_state` binding), `backend/core/gestures/screenshot.py` (`capture_result_cb`), `backend/core/debug_overlay.py` (measured HUD width), `frontend/src/lib/air-point-model.ts`, `frontend/src/components/air-point/{engine,shell}.tsx`, `frontend/src/routes/{__root,about,index,island}.tsx`, `frontend/src/components/air-point/dyne-studio/{dyne-studio.tsx,studio.ts,layered/host-adapter.ts}`, `frontend/vitest.config.ts` (`maxWorkers: 4`), `scripts/start_airpoint.ps1`, `scripts/stop_airpoint.ps1`, `.gitignore`, `CLAUDE.md`, `README.md`, `AIRPOINT_SYSTEM_ARCHITECTURE.md`, `AIRPOINT_ENGINEERING_ROADMAP.md`.

Not touched (by rule): `backend/core/actuator.py`, `backend/core/gestures/drag_controller.py`, `backend/core/gestures/orchestrator.py`, `backend/config.py`, every gesture threshold, `AIRPOINT_PHASE_1_PHYSICAL_RESULTS.md` (SHA-256 identical to the Stage A checkpoint copy), and the legacy checkout (its `git status` is unchanged: 2 modified, 6 untracked).

Residual legacy-path mentions in the canonical tree: documents only, the preflight's deliberate `sys.path` leak check, and the tracked historical audit script `scripts/dyne-studio-audit-browser-suite.cjs` (not used by any gate or runtime; see the report, §14).

Post-migration checkpoint: `C:\Users\loges\Documents\air_point2_audit_backups\migration_result_20261102_224800\` (67 files = every modified and untracked file, `SHA256_manifest.txt`, `unstaged.patch`, `git_status.txt`; 0 hash mismatches against the working tree).

# Legacy P0.2 reports (historical reference)

These four documents were the only untracked reports in the legacy checkout
(`C:\Users\loges\Documents\antigravity\AirPoint`, same HEAD `4672829`). They
were copied unchanged during the unified migration so that the history of the
P0.2 work stays available in the canonical repository. They are **not**
authoritative: the canonical engineering record is `AIRPOINT_SYSTEM_ARCHITECTURE.md`,
`AIRPOINT_ENGINEERING_ROADMAP.md` and the phase reports in the repository root.

| File | Content | Status today |
|---|---|---|
| `AIRPOINT_P0_2_2_REPOSITORY_RECONCILIATION_REPORT.md` | How the two checkouts desynchronised (the P0 work was never committed) | Resolved by the unified migration (`AIRPOINT_UNIFIED_MIGRATION_INVENTORY.md`) |
| `AIRPOINT_P0_2_PHYSICAL_TEST_GUIDE.md` | Physical drag test guide written for the legacy checkout | Superseded by `AIRPOINT_PHASE_1_PHYSICAL_TEST_PLAN.md` and `tools/physical_sandbox/` |
| `AIRPOINT_P0_2_PREFLIGHT_REPORT.md` | Hardware-free preflight audit of the legacy checkout | Superseded by `backend/preflight_physical_test.py` |
| `AIRPOINT_P0_2_TEST_REPORT.md` | Test-report template; every physical row is `NOT RUN` | No physical result was ever recorded in it |

The legacy `backend/core/debug_overlay.py` and `backend/main.py` working-tree
edits and the older `backend/test_debug_overlay_send.py` were not migrated; the
canonical P0/P1 versions cover them (see the migration inventory, section 3).

# AirPoint physical validation sandbox

Three PowerShell utilities that prepare and verify a disposable folder for the
physical drag-and-drop procedures in `AIRPOINT_PHASE_1_PHYSICAL_TEST_PLAN.md`.
They were migrated from the legacy checkout's `tools/p0_2` during the unified
migration; the only functional change is that every path is resolved from this
repository instead of being hard-coded.

| Script | What it does | Safety |
|---|---|---|
| `New-AirPointSandbox.ps1 [-SandboxPath C:\AirPoint-Sandbox]` | Creates `Source\` (synthetic text files, nested folders, 20 cycle files) and `Destination\`, writes a SHA-256 `manifest.json`, a `PHYSICAL_TEST_LOG.csv` template and a README with the exact launch and verification commands for this repository | Never overwrites existing files; refuses a non-empty folder without a manifest |
| `Verify-AirPointSandbox.ps1 [-SandboxPath ...] [-TargetAsset name]` | Reports, per manifest asset, whether it is still in `Source`, moved to `Destination` (hash verified), copied instead of moved, partially moved or missing | Read-only |
| `Reset-AirPointSandbox.ps1 [-SandboxPath ...] -ConfirmReset` | Moves manifest assets from `Destination` back to `Source` | Dry run without `-ConfirmReset`; never deletes; stops on a collision |

Typical session:

```powershell
cd C:\Users\loges\Documents\air_point2_audit
powershell -ExecutionPolicy Bypass -File .\tools\physical_sandbox\New-AirPointSandbox.ps1
.\scripts\start_airpoint.ps1 -Mode full -DebugHud
# ... perform the drag procedures with two Explorer windows (Source / Destination) ...
powershell -ExecutionPolicy Bypass -File .\tools\physical_sandbox\Verify-AirPointSandbox.ps1
powershell -ExecutionPolicy Bypass -File .\tools\physical_sandbox\Reset-AirPointSandbox.ps1 -ConfirmReset
```

The scripts never start the engine, never inject input and never touch files
outside the sandbox path. Physical results are recorded by the user in
`AIRPOINT_PHASE_1_PHYSICAL_RESULTS.md`; nothing here marks a test as passed.

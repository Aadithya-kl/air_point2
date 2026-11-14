<#
.SYNOPSIS
    AirPoint unified launcher: starts the Python gesture engine and the React Control Center
    from the canonical repository, verifies both, and records exactly what it started.

.DESCRIPTION
    Expected use:
        cd C:\Users\loges\Documents\air_point2_audit
        .\scripts\start_airpoint.ps1 -Mode full

    What it guarantees (unified migration, Stage F; corrected after the 2026-11-02 launch diagnostic):
      1.  Resolves the repository root from its own location (never a hard-coded path).
      2.  Uses the repository's virtual environment python (backend\.venv) and refuses a global one.
      3.  Uses the repository's frontend directory.
      4.  Checks Python, the engine's imports and models, Node, npm and node_modules before starting.
      5.  Checks the backend and frontend ports and reports who owns a busy one.
      6.  Starts the Python backend (main.py, or core\control_server.py in control-server mode).
      7.  Starts the React dev server bound to 127.0.0.1 with the bridge URL it discovered.
      8.  Records the exact process ids: the venv launcher stub Start-Process returned AND the real
          engine child it spawns (bridge_info.json's pid), plus the node children of npm.
      9.  Verifies backend health in two steps: engine process alive -> bridge_info.json written by a
          process of the started tree -> GET /api/status answers 200 with a status payload.
      10. Verifies frontend readiness with an HTTP request.
      11. Prints a status table (component, PID, port, URL, state, log file).
      12. Refuses to start a second instance recorded by this launcher.
      13. Stops only processes it started (stop_airpoint.ps1 verifies them by command line or tree).
      14. Never terminates every python.exe or node.exe.
      15. Stops what it already started (graceful exit first) when the other service fails.
      16. Captures stdout/stderr of both services under logs\ (unless -ShowConsoles).

    Physical gesture behaviour is not verified by this script; it only confirms the
    processes are up and the bridge answers.

.PARAMETER Mode
    full (engine + Control Center), control-server (bridge only + Control Center),
    backend-only (engine only), frontend-only (Control Center only).
.PARAMETER DebugHud
    Pass --debug to main.py (OpenCV debug window with the drag diagnostics HUD).
.PARAMETER DryRun
    Run every check and print the exact commands, but start nothing and write nothing.
.PARAMETER ShowConsoles
    Open visible console windows instead of redirecting output to log files.
.PARAMETER AllowPortFallback
    Let the engine bind a free loopback port when the backend port is busy (the frontend
    still discovers it through bridge_info.json).
#>
[CmdletBinding()]
param(
    [ValidateSet("full", "control-server", "backend-only", "frontend-only")]
    [string]$Mode = "full",
    [int]$FrontendPort = 8080,
    [int]$BackendPort = 8765,
    [switch]$DebugHud,
    [switch]$DryRun,
    [switch]$ShowConsoles,
    [switch]$AllowPortFallback,
    [switch]$OpenBrowser,
    [int]$BackendTimeoutSec = 60,
    [int]$FrontendTimeoutSec = 90
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Exit codes ────────────────────────────────────────────────────────────────
$EXIT_OK = 0
$EXIT_PREREQ = 2
$EXIT_PORT = 3
$EXIT_DUPLICATE = 4
$EXIT_BACKEND = 5
$EXIT_FRONTEND = 6
$EXIT_UNEXPECTED = 7

# ── 1. Canonical root resolved from this script's location ───────────────────
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "airpoint_launcher_lib.ps1")
$WorkspaceRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path.TrimEnd('\')
$BackendDir = Join-Path $WorkspaceRoot "backend"
$FrontendDir = Join-Path $WorkspaceRoot "frontend"
$RunDir = Join-Path $WorkspaceRoot ".airpoint"
$LogDir = Join-Path $WorkspaceRoot "logs"
$PidFile = Join-Path $RunDir "airpoint_pids.json"
$PythonExe = Join-Path $BackendDir ".venv\Scripts\python.exe"
$BridgeInfoFile = Join-Path $BackendDir "bridge_info.json"
$BridgeTokenFile = Join-Path $BackendDir ".bridge_token"
$Stamp = (Get-Date).ToString("yyyyMMdd_HHmmss")

$NeedBackend = $Mode -in @("full", "control-server", "backend-only")
$NeedFrontend = $Mode -in @("full", "control-server", "frontend-only")
$BackendScript = "main.py"
if ($Mode -eq "control-server") { $BackendScript = "core\control_server.py" }

function Write-Banner([string]$Text) { Write-Host "`n== $Text ==" -ForegroundColor Cyan }
function Write-Ok([string]$Text)     { Write-Host "  [OK]   $Text" -ForegroundColor Green }
function Write-Info([string]$Text)   { Write-Host "  [..]   $Text" -ForegroundColor Gray }
function Write-Warn2([string]$Text)  { Write-Host "  [WARN] $Text" -ForegroundColor Yellow }
function Write-Fail([string]$Text)   { Write-Host "  [FAIL] $Text" -ForegroundColor Red }

Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "        AIR POINT UNIFIED LAUNCHER (canonical)       " -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "Workspace root : $WorkspaceRoot"
Write-Host "Mode           : $Mode$(if ($DryRun) { '  (DRY RUN: nothing will start)' })"
Write-Host "Backend port   : $BackendPort"
Write-Host "Frontend port  : $FrontendPort"
Write-Host "PID file       : $PidFile"
Write-Host "Log directory  : $LogDir"

$Started = @{}   # label -> @{ Pid; Kind }

function Invoke-Cleanup([string]$Reason) {
    Write-Warn2 "Cleaning up after failure: $Reason"
    if ($Started.ContainsKey("backend")) {
        $rootPid = [int]$Started["backend"].Pid
        $tree = @($rootPid) + @(Get-ChildProcessIds -ParentId $rootPid)
        # Graceful first: the engine releases a held drag and restores Windows settings on its own thread.
        $g = Request-GracefulEngineExit -BridgeInfoPath $BridgeInfoFile -TokenPath $BridgeTokenFile -AllowedPids $tree -TimeoutSec 8
        if ($g.Exited) { Write-Info "Backend exited gracefully during cleanup" } else { Write-Info "Graceful exit not possible ($($g.Detail)); stopping the started process tree" }
        Stop-ProcessTree -RootPid $rootPid -Label "backend" -WorkspaceRoot $WorkspaceRoot | Out-Null
    }
    if ($Started.ContainsKey("frontend")) {
        Stop-ProcessTree -RootPid ([int]$Started["frontend"].Pid) -Label "frontend" -WorkspaceRoot $WorkspaceRoot | Out-Null
    }
    if (Test-Path $PidFile) { Remove-Item $PidFile -Force -ErrorAction SilentlyContinue }
}

# ── 2–4. Prerequisites ───────────────────────────────────────────────────────
Write-Banner "Prerequisites"
$prereqOk = $true

foreach ($marker in @("backend\main.py", "backend\core\control_server.py", "frontend\package.json", "scripts\stop_airpoint.ps1", "scripts\airpoint_launcher_lib.ps1")) {
    if (-not (Test-Path (Join-Path $WorkspaceRoot $marker))) {
        Write-Fail "Missing $marker under $WorkspaceRoot; this is not the canonical AirPoint repository layout"
        $prereqOk = $false
    }
}
if ($prereqOk) { Write-Ok "Canonical repository layout confirmed" }

if ($NeedBackend) {
    if (-not (Test-Path $PythonExe)) {
        Write-Fail "Virtual environment python not found: $PythonExe"
        Write-Host "         Create it with:" -ForegroundColor Yellow
        Write-Host "         C:\Python314\python.exe -m venv backend\.venv" -ForegroundColor Yellow
        Write-Host "         backend\.venv\Scripts\python -m pip install -r backend\requirements.txt" -ForegroundColor Yellow
        $prereqOk = $false
    } else {
        $pyVersion = Invoke-ToolVersion -Exe $PythonExe -Arguments @("-c", "import sys; print(sys.version.split()[0])")
        if ($null -eq $pyVersion) {
            Write-Fail "Could not run $PythonExe"
            $prereqOk = $false
        } else {
            Write-Ok "Python $pyVersion ($PythonExe; venv launcher stub + interpreter child)"
            $importCheck = Invoke-ToolVersion -Exe $PythonExe -Arguments @("-c", "import cv2, mediapipe, pynput, psutil, screeninfo, numpy; print('imports-ok')")
            if ($importCheck -ne "imports-ok") {
                Write-Fail "Engine dependencies are missing in the virtual environment (cv2 / mediapipe / pynput / psutil / screeninfo)"
                Write-Host "         backend\.venv\Scripts\python -m pip install -r backend\requirements.txt" -ForegroundColor Yellow
                $prereqOk = $false
            } else {
                Write-Ok "Engine imports resolve (cv2, mediapipe, pynput, psutil, screeninfo, numpy)"
            }
        }
        foreach ($model in @("models\hand_landmarker.task", "models\face_landmarker.task")) {
            if (-not (Test-Path (Join-Path $BackendDir $model))) {
                Write-Fail "Model bundle missing: backend\$model"
                $prereqOk = $false
            }
        }
    }
}

if ($NeedFrontend) {
    $nodeVersion = Invoke-ToolVersion -Exe "node" -Arguments @("-v")
    $npmVersion = Invoke-ToolVersion -Exe "npm.cmd" -Arguments @("-v")
    if ($null -eq $nodeVersion) { Write-Fail "node is not on PATH"; $prereqOk = $false } else { Write-Ok "Node $nodeVersion" }
    if ($null -eq $npmVersion) { Write-Fail "npm is not on PATH"; $prereqOk = $false } else { Write-Ok "npm $npmVersion" }
    if (-not (Test-Path (Join-Path $FrontendDir "node_modules\vite"))) {
        Write-Fail "frontend\node_modules is missing or incomplete; run: cd frontend; npm ci"
        $prereqOk = $false
    } else {
        Write-Ok "frontend\node_modules present"
    }
}

if (-not $prereqOk) {
    Write-Fail "Prerequisites not met; nothing was started."
    exit $EXIT_PREREQ
}

# ── 12. Duplicate instance protection ────────────────────────────────────────
Write-Banner "Duplicate instance check"
if (Test-Path $PidFile) {
    $alive = @()
    try {
        $recorded = Get-Content $PidFile -Raw | ConvertFrom-Json
        foreach ($label in @("backend", "frontend")) {
            $entry = $recorded.$label
            if ($null -eq $entry) { continue }
            $ids = @([int]$entry.pid)
            if ($null -ne $entry.PSObject.Properties["launcherPid"] -and $null -ne $entry.launcherPid) { $ids += [int]$entry.launcherPid }
            foreach ($id in $ids) {
                $info = Get-ProcessInfo -ProcessId $id
                if ($null -ne $info -and ((Test-OwnedByWorkspace $info $WorkspaceRoot) -or $info.Name -in @("python.exe", "node.exe", "cmd.exe"))) {
                    $alive += "$label PID $id ($($info.Name))"
                }
            }
        }
    } catch {
        Write-Warn2 "PID file unreadable ($($_.Exception.Message)); treating it as stale"
    }
    if ($alive.Count -gt 0) {
        Write-Fail "An AirPoint instance started by this launcher is still running:"
        foreach ($a in $alive) { Write-Host "         - $a" -ForegroundColor Yellow }
        Write-Host "         Stop it first: .\scripts\stop_airpoint.ps1" -ForegroundColor Yellow
        exit $EXIT_DUPLICATE
    }
    Write-Info "Stale PID file found (no recorded process alive)$(if ($DryRun) { '; would be removed' })"
    if (-not $DryRun) { Remove-Item $PidFile -Force -ErrorAction SilentlyContinue }
} else {
    Write-Ok "No instance recorded by this launcher"
}

# ── 5. Port checks ───────────────────────────────────────────────────────────
Write-Banner "Port checks"
$portOk = $true
if ($NeedBackend) {
    $be = Get-PortListener -Port $BackendPort -WorkspaceRoot $WorkspaceRoot
    if ($null -ne $be) {
        $who = "PID $($be.Pid) ($($be.Name))"
        if ($be.Owned) {
            Write-Fail "Backend port $BackendPort is held by an AirPoint process from this repository: $who. Run .\scripts\stop_airpoint.ps1 -IncludeOrphans"
            $portOk = $false
        } elseif ($AllowPortFallback) {
            Write-Warn2 "Backend port $BackendPort is busy ($who); the engine will bind a free loopback port (AIRPOINT_PORT_FALLBACK=1)"
        } else {
            Write-Fail "Backend port $BackendPort is busy: $who. Free it, pick -BackendPort, or pass -AllowPortFallback"
            $portOk = $false
        }
    } else {
        Write-Ok "Backend port $BackendPort is free"
    }
}
if ($NeedFrontend) {
    $fe = Get-PortListener -Port $FrontendPort -WorkspaceRoot $WorkspaceRoot
    if ($null -ne $fe) {
        $who = "PID $($fe.Pid) ($($fe.Name))"
        if ($fe.Owned) {
            Write-Fail "Frontend port $FrontendPort is held by an AirPoint process from this repository: $who. Run .\scripts\stop_airpoint.ps1 -IncludeOrphans"
        } else {
            Write-Fail "Frontend port $FrontendPort is busy: $who. Free it or pick -FrontendPort"
        }
        $portOk = $false
    } else {
        Write-Ok "Frontend port $FrontendPort is free"
    }
}
if (-not $portOk) {
    Write-Fail "Port check failed; nothing was started."
    exit $EXIT_PORT
}

# ── Plan ─────────────────────────────────────────────────────────────────────
$backendArgs = @($BackendScript)
if ($DebugHud -and $Mode -ne "control-server") { $backendArgs += "--debug" }
$backendOut = Join-Path $LogDir "backend_$Stamp.log"
$backendErr = Join-Path $LogDir "backend_$Stamp.err.log"
$frontendOut = Join-Path $LogDir "frontend_$Stamp.log"
$frontendErr = Join-Path $LogDir "frontend_$Stamp.err.log"
$frontendArgs = "/d /c npm run dev -- --port $FrontendPort --host 127.0.0.1 --strictPort"

Write-Banner "Plan"
if ($NeedBackend) {
    Write-Info "Backend : `"$PythonExe`" $($backendArgs -join ' ')   (cwd: $BackendDir)"
    if ($AllowPortFallback) { Write-Info "          env AIRPOINT_PORT_FALLBACK=1" }
    if (-not $ShowConsoles) { Write-Info "          stdout -> $backendOut ; stderr (engine log) -> $backendErr" }
    Write-Info "          health = engine child alive -> bridge_info.json from the started tree -> GET /api/status 200 (<= $BackendTimeoutSec s)"
}
if ($NeedFrontend) {
    Write-Info "Frontend: cmd.exe $frontendArgs   (cwd: $FrontendDir)"
    Write-Info "          env VITE_AIRPOINT_BRIDGE_URL=<discovered from backend\bridge_info.json, default http://127.0.0.1:$BackendPort>"
    if (-not $ShowConsoles) { Write-Info "          stdout -> $frontendOut ; stderr -> $frontendErr" }
}

if ($DryRun) {
    Write-Host "`nDRY RUN complete: prerequisites, duplicate check and ports verified; no process was started and no file was written." -ForegroundColor Green
    exit $EXIT_OK
}

New-Item -ItemType Directory -Force -Path $RunDir | Out-Null
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$record = [ordered]@{
    version = 3
    root = $WorkspaceRoot
    mode = $Mode
    startedAt = (Get-Date).ToString("o")
    launcherPid = $PID
    bridgeUrl = $null
    backend = $null
    frontend = $null
}

function Save-PidFile {
    ($record | ConvertTo-Json -Depth 6) | Set-Content -Path $PidFile -Encoding UTF8
}

$bridgeUrl = "http://127.0.0.1:$BackendPort"

try {
    # ── 6 + 9. Backend ────────────────────────────────────────────────────────
    if ($NeedBackend) {
        Write-Banner "Starting backend ($BackendScript)"
        # A discovery file left by a force-stopped engine would otherwise look like ours.
        foreach ($stale in @($BridgeInfoFile, $BridgeTokenFile)) {
            if (Test-Path $stale) {
                $staleInfo = Read-BridgeInfo -Path $BridgeInfoFile
                if ($null -ne $staleInfo -and $null -ne (Get-ProcessInfo -ProcessId ([int]$staleInfo.pid))) {
                    Write-Fail "bridge_info.json belongs to a live engine (PID $($staleInfo.pid)); stop it first (.\scripts\stop_airpoint.ps1 -IncludeOrphans)"
                    exit $EXIT_DUPLICATE
                }
                Remove-Item $stale -Force -ErrorAction SilentlyContinue
                Write-Info "Removed stale $(Split-Path $stale -Leaf) from an earlier run"
            }
        }
        if ($AllowPortFallback) { $env:AIRPOINT_PORT_FALLBACK = "1" } else { Remove-Item Env:\AIRPOINT_PORT_FALLBACK -ErrorAction SilentlyContinue }

        $launchedAt = Get-Date
        $startParams = @{
            FilePath = $PythonExe
            ArgumentList = $backendArgs
            WorkingDirectory = $BackendDir
            PassThru = $true
        }
        if (-not $ShowConsoles) {
            $startParams["RedirectStandardOutput"] = $backendOut
            $startParams["RedirectStandardError"] = $backendErr
            $startParams["WindowStyle"] = "Hidden"
        }
        $beProc = Start-Process @startParams
        $Started["backend"] = @{ Pid = $beProc.Id }
        $record.backend = [ordered]@{
            pid = $beProc.Id            # replaced by the real engine child once the bridge is up
            launcherPid = $beProc.Id    # venv launcher stub returned by Start-Process
            childPids = @()
            script = $BackendScript
            port = $BackendPort
            log = $(if ($ShowConsoles) { $null } else { $backendOut })
            errLog = $(if ($ShowConsoles) { $null } else { $backendErr })
            startedAt = $launchedAt.ToString("o")
        }
        Save-PidFile
        Write-Info "Launcher stub PID $($beProc.Id); waiting up to $BackendTimeoutSec s for the engine child and its bridge"

        $health = Wait-BridgeHealthy -LauncherPid $beProc.Id -BridgeInfoPath $BridgeInfoFile -TimeoutSec $BackendTimeoutSec -NotBefore $launchedAt -OnProgress { param($msg) Write-Info $msg }

        if (-not $health.Healthy) {
            switch ($health.Failure) {
                "process-exited"        { Write-Fail "Backend process exited (launcher stub exit code: $(if ($beProc.HasExited) { $beProc.ExitCode } else { 'n/a' })). $($health.Detail)" }
                "no-bridge-info"        { Write-Fail "Engine process is alive but the bridge never came up: $($health.Detail)" }
                "bridge-foreign-pid"    { Write-Fail "Bridge discovery conflict: $($health.Detail)" }
                "bridge-not-answering"  { Write-Fail "Bridge bound but not answering: $($health.Detail)" }
                "bridge-bad-response"   { Write-Fail "Something else answers on the bridge port: $($health.Detail)" }
                default                 { Write-Fail "Backend health check failed: $($health.Detail)" }
            }
            foreach ($line in (Get-LogTail -Path $backendErr)) { Write-Host "         | $line" -ForegroundColor DarkYellow }
            Invoke-Cleanup -Reason "backend health check failed ($($health.Failure))"
            exit $EXIT_BACKEND
        }
        $bridgeUrl = $health.BridgeUrl
        $status = $health.Status
        $record.backend.pid = [int]$health.EnginePid
        $record.backend.childPids = @($health.Descendants)
        $record.backend.port = [int]($bridgeUrl.Split(':')[-1])
        $record.bridgeUrl = $bridgeUrl
        Save-PidFile
        $dragState = "n/a"
        if ($null -ne $status -and $null -ne $status.PSObject.Properties["drag"] -and $null -ne $status.drag) { $dragState = $status.drag.state }
        Write-Ok "Engine PID $($health.EnginePid) (stub $($beProc.Id)); bridge healthy at $bridgeUrl (running=$($status.running), tracking=$($status.tracking), drag=$dragState)"
    } elseif ($NeedFrontend) {
        # frontend-only: reuse a live bridge if its process is still alive
        $info = Read-BridgeInfo -Path $BridgeInfoFile
        if ($null -ne $info -and $null -ne (Get-ProcessInfo -ProcessId ([int]$info.pid))) {
            $bridgeUrl = "http://$($info.host):$($info.port)"
            Write-Info "Reusing the running bridge at $bridgeUrl (engine PID $($info.pid))"
        }
    }

    # ── 7 + 10. Frontend ──────────────────────────────────────────────────────
    if ($NeedFrontend) {
        Write-Banner "Starting frontend (vite dev on 127.0.0.1:$FrontendPort)"
        $env:VITE_AIRPOINT_BRIDGE_URL = $bridgeUrl
        $feStartedAt = Get-Date
        $startParams = @{
            FilePath = "cmd.exe"
            ArgumentList = $frontendArgs
            WorkingDirectory = $FrontendDir
            PassThru = $true
        }
        if (-not $ShowConsoles) {
            $startParams["RedirectStandardOutput"] = $frontendOut
            $startParams["RedirectStandardError"] = $frontendErr
            $startParams["WindowStyle"] = "Hidden"
        }
        $feProc = Start-Process @startParams
        $Started["frontend"] = @{ Pid = $feProc.Id }
        $record.frontend = [ordered]@{
            pid = $feProc.Id
            childPids = @()
            port = $FrontendPort
            url = "http://localhost:$FrontendPort"
            bridgeUrl = $bridgeUrl
            log = $(if ($ShowConsoles) { $null } else { $frontendOut })
            errLog = $(if ($ShowConsoles) { $null } else { $frontendErr })
            startedAt = $feStartedAt.ToString("o")
        }
        Save-PidFile
        Write-Info "Frontend PID $($feProc.Id) (cmd/npm); waiting up to $FrontendTimeoutSec s for http://127.0.0.1:$FrontendPort/"

        $deadline = (Get-Date).AddSeconds($FrontendTimeoutSec)
        $ready = $false
        while ((Get-Date) -lt $deadline) {
            if ($feProc.HasExited) { break }
            try {
                $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$FrontendPort/" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
                if ($resp.StatusCode -eq 200) { $ready = $true; break }
            } catch { }
            Start-Sleep -Milliseconds 500
        }
        if (-not $ready) {
            if ($feProc.HasExited) {
                Write-Fail "Frontend exited early with code $($feProc.ExitCode)"
            } else {
                Write-Fail "Frontend did not answer on port $FrontendPort within $FrontendTimeoutSec s"
            }
            foreach ($line in (Get-LogTail -Path $frontendErr)) { Write-Host "         | $line" -ForegroundColor DarkYellow }
            foreach ($line in (Get-LogTail -Path $frontendOut -Lines 10)) { Write-Host "         | $line" -ForegroundColor DarkYellow }
            Invoke-Cleanup -Reason "frontend readiness check failed"
            exit $EXIT_FRONTEND
        }
        $record.frontend.childPids = @(Get-ChildProcessIds -ParentId $feProc.Id)
        Save-PidFile
        Write-Ok "Control Center ready at http://localhost:$FrontendPort (node children: $($record.frontend.childPids -join ', '))"
    }
} catch {
    Write-Fail "Unexpected launcher error: $($_.Exception.Message)"
    Invoke-Cleanup -Reason "unexpected error"
    exit $EXIT_UNEXPECTED
}

# ── 11. Status ────────────────────────────────────────────────────────────────
Write-Banner "Status"
$rows = @()
if ($null -ne $record.backend) {
    $rows += [PSCustomObject]@{ Component = "Python engine ($BackendScript)"; PID = $record.backend.pid; Stub = $record.backend.launcherPid; Port = $record.backend.port; URL = "$bridgeUrl/api/status"; State = "healthy"; Log = $(if ($record.backend.errLog) { $record.backend.errLog } else { "console" }) }
}
if ($null -ne $record.frontend) {
    $rows += [PSCustomObject]@{ Component = "React Control Center (vite)"; PID = $record.frontend.pid; Stub = ""; Port = $record.frontend.port; URL = $record.frontend.url; State = "ready"; Log = $(if ($record.frontend.log) { $record.frontend.log } else { "console" }) }
}
$rows | Format-Table -AutoSize | Out-String -Width 220 | Write-Host

Write-Host "Air Point is running from $WorkspaceRoot" -ForegroundColor Green
if ($NeedFrontend) { Write-Host "Control Center : http://localhost:$FrontendPort  (bridge $bridgeUrl)" -ForegroundColor Cyan }
if ($NeedBackend)  { Write-Host "Hotkeys        : Ctrl+Alt+P pause, Ctrl+Alt+Q quit, Ctrl+Alt+S status, Ctrl+Alt+D debug HUD" -ForegroundColor Cyan }
Write-Host "Stop           : .\scripts\stop_airpoint.ps1   (graceful engine exit, own processes only)" -ForegroundColor Yellow

if ($OpenBrowser -and $NeedFrontend) {
    try { Start-Process "http://localhost:$FrontendPort" } catch { }
}
exit $EXIT_OK

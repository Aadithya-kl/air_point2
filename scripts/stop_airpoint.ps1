<#
.SYNOPSIS
    AirPoint unified shutdown: stops only the processes start_airpoint.ps1 started
    (or, with -IncludeOrphans, AirPoint processes that provably belong to this repository).

.DESCRIPTION
    Order of operations:
      1. Reads .airpoint\airpoint_pids.json written by the launcher (version 2 or 3).
      2. Asks the engine to exit gracefully through the authenticated bridge
         (POST /api/control {"action":"exit"}) so a held drag is released on the
         engine thread and the Windows pointer settings are restored. The request
         is sent only when bridge_info.json belongs to a process of the recorded
         tree (the venv launcher stub, the engine child it spawned, recorded children).
         Only if processes are still alive after -GracefulTimeoutSec does it force-stop them.
      3. Stops the frontend's node children, then the npm/cmd parent.
      4. Every process is verified (command line references this repository, or it
         is a live descendant of a root this launcher started, or it was recorded as
         such a descendant at start-up) before Stop-Process; nothing else is ever
         terminated, and it never kills every python.exe or node.exe.
      5. Removes the ephemeral bridge files only when no engine remains.

.PARAMETER IncludeOrphans
    Also stop python/node/cmd processes whose command line references this
    repository's backend or frontend even when they are not in the PID file
    (for example an engine started by hand from backend\).
.PARAMETER GracefulTimeoutSec
    How long to wait for the engine to exit after the graceful request.
#>
[CmdletBinding()]
param(
    [switch]$IncludeOrphans,
    [int]$GracefulTimeoutSec = 10
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "airpoint_launcher_lib.ps1")
$WorkspaceRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path.TrimEnd('\')
$BackendDir = Join-Path $WorkspaceRoot "backend"
$FrontendDir = Join-Path $WorkspaceRoot "frontend"
$RunDir = Join-Path $WorkspaceRoot ".airpoint"
$PidFile = Join-Path $RunDir "airpoint_pids.json"
$BridgeToken = Join-Path $BackendDir ".bridge_token"
$BridgeInfo = Join-Path $BackendDir "bridge_info.json"

function Write-Ok([string]$Text)    { Write-Host "  [OK]   $Text" -ForegroundColor Green }
function Write-Info([string]$Text)  { Write-Host "  [..]   $Text" -ForegroundColor Gray }
function Write-Warn2([string]$Text) { Write-Host "  [WARN] $Text" -ForegroundColor Yellow }

Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "        AIR POINT UNIFIED SHUTDOWN (canonical)       " -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "Workspace root : $WorkspaceRoot"

$stoppedAny = $false
$engineStillRunning = $false

function Stop-RecordedBackend($Entry) {
    # Returns $true when the engine is gone afterwards.
    $enginePid = [int]$Entry.pid
    $launcherPid = $enginePid
    if ($null -ne $Entry.PSObject.Properties["launcherPid"] -and $null -ne $Entry.launcherPid) { $launcherPid = [int]$Entry.launcherPid }
    $startedAt = $null
    try { $startedAt = [datetime]$Entry.startedAt } catch { $startedAt = $null }
    $recordedChildren = @()
    if ($null -ne $Entry.PSObject.Properties["childPids"] -and $null -ne $Entry.childPids) { foreach ($c in @($Entry.childPids)) { $recordedChildren += [int]$c } }

    $liveTree = @()
    if ($null -ne (Get-ProcessInfo -ProcessId $launcherPid)) { $liveTree = @($launcherPid) + @(Get-ChildProcessIds -ParentId $launcherPid) }
    $candidates = @($liveTree) + @($enginePid) + @($recordedChildren) | Select-Object -Unique
    $aliveNow = @($candidates | Where-Object { $null -ne (Get-ProcessInfo -ProcessId $_) })
    if ($aliveNow.Count -eq 0) {
        Write-Info "Backend (engine PID $enginePid, stub PID $launcherPid) already stopped"
        return $true
    }

    Write-Host "`nStopping backend (engine PID $enginePid, stub PID $launcherPid, $($Entry.script))..." -ForegroundColor Yellow
    $g = Request-GracefulEngineExit -BridgeInfoPath $BridgeInfo -TokenPath $BridgeToken -AllowedPids $candidates -TimeoutSec $GracefulTimeoutSec
    if ($g.Exited) {
        Write-Ok "Engine exited gracefully (drag release and Windows settings restore ran on its own thread)"
        return $true
    }
    if ($g.Requested) { Write-Warn2 $g.Detail } else { Write-Info "Graceful exit not possible: $($g.Detail)" }
    Write-Warn2 "Forcing the engine to stop; if a drag was held, press and release the left mouse button once"
    $ok = Stop-ProcessTree -RootPid $launcherPid -Label "backend" -WorkspaceRoot $WorkspaceRoot -RecordedChildIds ($recordedChildren + @($enginePid)) -ServiceStartedAt $startedAt
    if ($enginePid -ne $launcherPid -and $null -ne (Get-ProcessInfo -ProcessId $enginePid)) {
        $engInfo = Get-ProcessInfo -ProcessId $enginePid
        $engOwned = (Test-OwnedByWorkspace $engInfo $WorkspaceRoot) -or (Test-RecordedChild $engInfo ($recordedChildren + @($enginePid)) $startedAt)
        if (-not (Stop-OwnedProcess -ProcessId $enginePid -Label "engine" -WorkspaceRoot $WorkspaceRoot -Descendant $engOwned)) { $ok = $false }
    }
    return $ok
}

function Stop-RecordedFrontend($Entry) {
    $fePid = [int]$Entry.pid
    $startedAt = $null
    try { $startedAt = [datetime]$Entry.startedAt } catch { $startedAt = $null }
    $recordedChildren = @()
    if ($null -ne $Entry.PSObject.Properties["childPids"] -and $null -ne $Entry.childPids) { foreach ($c in @($Entry.childPids)) { $recordedChildren += [int]$c } }
    $aliveNow = @((@($fePid) + $recordedChildren) | Where-Object { $null -ne (Get-ProcessInfo -ProcessId $_) })
    if ($aliveNow.Count -eq 0) {
        Write-Info "Frontend PID $fePid already stopped"
        return $true
    }
    Write-Host "`nStopping frontend (PID $fePid and its node children)..." -ForegroundColor Yellow
    return (Stop-ProcessTree -RootPid $fePid -Label "frontend" -WorkspaceRoot $WorkspaceRoot -RecordedChildIds $recordedChildren -ServiceStartedAt $startedAt)
}

# ── 1–3. Recorded processes ──────────────────────────────────────────────────
if (Test-Path $PidFile) {
    $record = $null
    try { $record = Get-Content $PidFile -Raw | ConvertFrom-Json } catch { Write-Warn2 "PID file unreadable: $($_.Exception.Message)" }

    if ($null -ne $record) {
        if ($null -ne $record.backend) {
            if (Stop-RecordedBackend -Entry $record.backend) { $stoppedAny = $true } else { $engineStillRunning = $true }
        }
        if ($null -ne $record.frontend) {
            if (Stop-RecordedFrontend -Entry $record.frontend) { $stoppedAny = $true }
        }
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
} else {
    Write-Info "No PID file at $PidFile (nothing recorded by the launcher)"
}

# ── 4. Orphans (opt-in, still verified by command line) ──────────────────────
if ($IncludeOrphans) {
    Write-Host "`nLooking for AirPoint processes from this repository not recorded in the PID file..." -ForegroundColor Yellow
    $candidates = @()
    try {
        $candidates = Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
            $_.Name -in @("python.exe", "pythonw.exe", "node.exe", "cmd.exe") -and
            -not [string]::IsNullOrEmpty($_.CommandLine) -and (
                $_.CommandLine.ToLowerInvariant().Contains($BackendDir.ToLowerInvariant()) -or
                $_.CommandLine.ToLowerInvariant().Contains($FrontendDir.ToLowerInvariant())
            )
        }
    } catch { Write-Warn2 "Process enumeration failed: $($_.Exception.Message)" }
    $pythonOrphans = @($candidates | Where-Object { $_.Name -like "python*" } | ForEach-Object { [int]$_.ProcessId })
    if ($pythonOrphans.Count -gt 0) {
        $g = Request-GracefulEngineExit -BridgeInfoPath $BridgeInfo -TokenPath $BridgeToken -AllowedPids $pythonOrphans -TimeoutSec $GracefulTimeoutSec
        if ($g.Exited) { Write-Ok "Orphan engine exited gracefully"; $stoppedAny = $true } elseif ($g.Requested) { Write-Warn2 $g.Detail }
    }
    foreach ($c in @($candidates)) {
        if ($null -eq $c) { continue }
        $cPid = [int]$c.ProcessId
        if ($cPid -eq $PID) { continue }
        if ($null -eq (Get-ProcessInfo -ProcessId $cPid)) { continue }
        if (Stop-OwnedProcess -ProcessId $cPid -Label "orphan $($c.Name)" -WorkspaceRoot $WorkspaceRoot) { $stoppedAny = $true } elseif ($c.Name -like "python*") { $engineStillRunning = $true }
    }
    if (@($candidates).Count -eq 0) { Write-Info "No orphaned AirPoint process found" }
}

# ── 5. Bridge files ──────────────────────────────────────────────────────────
$engineAlive = $false
$info = Read-BridgeInfo -Path $BridgeInfo
if ($null -ne $info) { $engineAlive = ($null -ne (Get-ProcessInfo -ProcessId ([int]$info.pid))) }
if (-not $engineAlive -and -not $engineStillRunning) {
    foreach ($f in @($BridgeToken, $BridgeInfo)) {
        if (Test-Path $f) { Remove-Item $f -Force -ErrorAction SilentlyContinue; Write-Info "Removed ephemeral $f" }
    }
} else {
    Write-Warn2 "An engine still owns the bridge files; leaving them in place"
}

if ($stoppedAny) {
    Write-Host "`nAir Point stopped (own processes only).`n" -ForegroundColor Green
} else {
    Write-Host "`nNothing to stop.`n" -ForegroundColor Green
}
exit 0

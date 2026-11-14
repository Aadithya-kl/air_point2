<#
.SYNOPSIS
    Launcher self-test: exercises the backend branch of start/stop_airpoint.ps1
    against a hardware-free stand-in engine (backend\launcher_bridge_probe.py).

.DESCRIPTION
    Proves, without a camera or native input, that the launcher library:
      1. starts the engine through the venv python stub and resolves the REAL engine
         child (the PID bridge_info.json records), which differs from the PID
         Start-Process returned (2026-11-02 launch failure root cause);
      2. accepts bridge_info.json only from the started process tree;
      3. probes GET /api/status on the actual bound port;
      4. exits the engine gracefully through POST /api/control {"action":"exit"} and
         waits for the whole tree (child and stub) to end;
      5. leaves no process and no bridge discovery file behind.
    Refuses to run while a real engine owns backend\bridge_info.json.

.PARAMETER Port
    Port for the probe bridge (default 18765; use a free one).
#>
[CmdletBinding()]
param(
    [int]$Port = 18765,
    [int]$TimeoutSec = 30
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "airpoint_launcher_lib.ps1")
$WorkspaceRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path.TrimEnd('\')
$BackendDir = Join-Path $WorkspaceRoot "backend"
$PythonExe = Join-Path $BackendDir ".venv\Scripts\python.exe"
$BridgeInfoFile = Join-Path $BackendDir "bridge_info.json"
$BridgeTokenFile = Join-Path $BackendDir ".bridge_token"
$ProbeScript = Join-Path $BackendDir "launcher_bridge_probe.py"

$results = @()
function Check([string]$Name, [bool]$Ok, [string]$Detail) {
    $script:results += [PSCustomObject]@{ Check = $Name; Result = $(if ($Ok) { "PASS" } else { "FAIL" }); Detail = $Detail }
    if ($Ok) { Write-Host "  [PASS] $Name - $Detail" -ForegroundColor Green } else { Write-Host "  [FAIL] $Name - $Detail" -ForegroundColor Red }
}

Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "        AIR POINT LAUNCHER SELF-TEST (no camera)     " -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "Workspace root : $WorkspaceRoot"
Write-Host "Probe port     : $Port"

if (-not (Test-Path $PythonExe)) { Write-Host "venv python missing: $PythonExe" -ForegroundColor Red; exit 2 }
$existing = Read-BridgeInfo -Path $BridgeInfoFile
if ($null -ne $existing -and $null -ne (Get-ProcessInfo -ProcessId ([int]$existing.pid))) {
    Write-Host "A live engine (PID $($existing.pid)) owns backend\bridge_info.json; refusing to run the self-test." -ForegroundColor Red
    exit 3
}
foreach ($stale in @($BridgeInfoFile, $BridgeTokenFile)) { if (Test-Path $stale) { Remove-Item $stale -Force -ErrorAction SilentlyContinue } }
$listener = Get-PortListener -Port $Port -WorkspaceRoot $WorkspaceRoot
if ($null -ne $listener) { Write-Host "Port $Port is busy (PID $($listener.Pid) $($listener.Name)); pick another -Port." -ForegroundColor Red; exit 3 }

$tmpSettings = Join-Path $env:TEMP ("airpoint_selftest_settings_" + [guid]::NewGuid().ToString("N") + ".json")
$logOut = Join-Path $env:TEMP "airpoint_selftest_probe.log"
$logErr = Join-Path $env:TEMP "airpoint_selftest_probe.err.log"
foreach ($f in @($logOut, $logErr)) { if (Test-Path $f) { Remove-Item $f -Force -ErrorAction SilentlyContinue } }
$env:AIRPOINT_SETTINGS_PATH = $tmpSettings   # bridge files are written only with a real settings path

$launchedAt = Get-Date
$proc = Start-Process -FilePath $PythonExe -ArgumentList @($ProbeScript, "--port", "$Port", "--max-seconds", "90") -WorkingDirectory $BackendDir -PassThru -RedirectStandardOutput $logOut -RedirectStandardError $logErr -WindowStyle Hidden
Write-Host "  [..]   Start-Process returned PID $($proc.Id)"
$overallOk = $true
try {
    $health = Wait-BridgeHealthy -LauncherPid $proc.Id -BridgeInfoPath $BridgeInfoFile -TimeoutSec $TimeoutSec -NotBefore $launchedAt -OnProgress { param($m) Write-Host "  [..]   $m" -ForegroundColor Gray }
    Check "bridge healthy" $health.Healthy "$($health.Detail)"
    if (-not $health.Healthy) { $overallOk = $false }
    $bridge = Read-BridgeInfo -Path $BridgeInfoFile
    $bridgePid = $(if ($null -ne $bridge) { [int]$bridge.pid } else { 0 })
    Check "engine PID resolved from the tree" ($health.EnginePid -eq $bridgePid -and $bridgePid -gt 0) "engine PID $($health.EnginePid) == bridge_info pid $bridgePid"
    Check "venv launcher stub differs from the engine child" ($health.EnginePid -ne $proc.Id) "stub $($proc.Id) vs engine $($health.EnginePid) (Start-Process PID is not the engine)"
    $portOk = ($null -ne $health.BridgeUrl -and $health.BridgeUrl.EndsWith(":$Port"))
    Check "actual bound port" $portOk "bridge url $($health.BridgeUrl)"
    $probe = Test-BridgeStatus -BridgeUrl $health.BridgeUrl
    Check "GET /api/status is the health endpoint" ($probe.Ok -and $null -ne $probe.Status.PSObject.Properties["drag"]) "running=$($probe.Status.running) drag.state=$($probe.Status.drag.state) last_event_id=$($probe.Status.last_event_id)"
    $foreign = Resolve-EngineProcess -LauncherPid 1 -BridgeInfoPath $BridgeInfoFile -NotBefore $launchedAt
    Check "foreign tree is rejected" ($foreign.BridgeState -eq "foreign") "resolving from an unrelated PID classifies the bridge as $($foreign.BridgeState)"
    if (-not ($health.EnginePid -eq $bridgePid -and $health.EnginePid -ne $proc.Id -and $portOk -and $probe.Ok -and $foreign.BridgeState -eq "foreign")) { $overallOk = $false }

    $tree = @($proc.Id) + @(Get-ChildProcessIds -ParentId $proc.Id)
    $g = Request-GracefulEngineExit -BridgeInfoPath $BridgeInfoFile -TokenPath $BridgeTokenFile -AllowedPids $tree -TimeoutSec 10
    Check "graceful exit accepted and whole tree exited" ($g.Accepted -and $g.Exited) $g.Detail
    if (-not ($g.Accepted -and $g.Exited)) { $overallOk = $false }
    Start-Sleep -Milliseconds 500
    $leftover = @($tree | Where-Object { $null -ne (Get-ProcessInfo -ProcessId $_) })
    Check "no process left behind" ($leftover.Count -eq 0) "leftover PIDs: $(if ($leftover.Count -eq 0) { 'none' } else { $leftover -join ', ' })"
    $filesGone = -not (Test-Path $BridgeInfoFile) -and -not (Test-Path $BridgeTokenFile)
    Check "bridge discovery files removed by the engine" $filesGone "bridge_info.json present=$(Test-Path $BridgeInfoFile), .bridge_token present=$(Test-Path $BridgeTokenFile)"
    if ($leftover.Count -ne 0 -or -not $filesGone) { $overallOk = $false }
} finally {
    # Never leave the probe running
    $tree = @($proc.Id) + @(Get-ChildProcessIds -ParentId $proc.Id)
    foreach ($id in $tree) { if ($null -ne (Get-ProcessInfo -ProcessId $id)) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue; Write-Host "  [WARN] force-stopped leftover PID $id" -ForegroundColor Yellow } }
    Remove-Item Env:\AIRPOINT_SETTINGS_PATH -ErrorAction SilentlyContinue
    if (Test-Path $tmpSettings) { Remove-Item $tmpSettings -Force -ErrorAction SilentlyContinue }
}

Write-Host ""
$results | Format-Table -AutoSize | Out-String -Width 200 | Write-Host
Write-Host "Probe log: $logErr" -ForegroundColor Gray
if ($overallOk) { Write-Host "LAUNCHER SELF-TEST: PASS" -ForegroundColor Green; exit 0 } else { Write-Host "LAUNCHER SELF-TEST: FAIL" -ForegroundColor Red; exit 1 }

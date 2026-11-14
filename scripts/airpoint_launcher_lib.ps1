<#
.SYNOPSIS
    Shared functions for start_airpoint.ps1, stop_airpoint.ps1 and launcher_selftest.ps1.
    Functions only: dot-sourcing this file runs nothing.

.DESCRIPTION
    Process identity on Windows with a virtual environment (proven 2026-11-02):
    backend\.venv\Scripts\python.exe is the venv *launcher* stub. Start-Process
    returns the stub's PID; the stub spawns the real interpreter as a CHILD
    process, and that child is the engine (its os.getpid() is what
    bridge_info.json records). Every function here therefore reasons about the
    process TREE below the PID the launcher started, never about one PID alone.
#>

Set-StrictMode -Version Latest

$script:LauncherHelperNames = @("python.exe", "pythonw.exe", "cmd.exe", "conhost.exe", "node.exe")

function Get-ProcessInfo([int]$ProcessId) {
    # @{ Id; Name; CommandLine; ParentId; Created } or $null when the process is gone.
    if ($ProcessId -le 0) { return $null }
    try { $p = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop } catch { return $null }
    if ($null -eq $p) { return $null }
    $created = $null
    try { $created = [datetime]$p.CreationDate } catch { $created = $null }
    return @{ Id = [int]$p.ProcessId; Name = [string]$p.Name; CommandLine = [string]$p.CommandLine; ParentId = [int]$p.ParentProcessId; Created = $created }
}

function Test-OwnedByWorkspace($Info, [string]$WorkspaceRoot) {
    # A process is "ours" by command line only when it references this repository.
    if ($null -eq $Info) { return $false }
    $cl = $Info.CommandLine
    if ([string]::IsNullOrEmpty($cl) -or [string]::IsNullOrEmpty($WorkspaceRoot)) { return $false }
    return $cl.ToLowerInvariant().Contains($WorkspaceRoot.ToLowerInvariant())
}

function Get-ChildProcessIds([int]$ParentId) {
    # Recursive descendants (depth first), live snapshot.
    $result = @()
    if ($ParentId -le 0) { return $result }
    try { $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $ParentId" -ErrorAction Stop } catch { return $result }
    foreach ($c in @($children)) {
        if ($null -eq $c) { continue }
        $result += [int]$c.ProcessId
        $result += Get-ChildProcessIds -ParentId ([int]$c.ProcessId)
    }
    return $result
}

function Get-PortListener([int]$Port, [string]$WorkspaceRoot) {
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $conn) { return $null }
    $info = Get-ProcessInfo -ProcessId ([int]$conn.OwningProcess)
    $name = "unknown"
    if ($null -ne $info) { $name = $info.Name }
    return @{ Pid = [int]$conn.OwningProcess; Name = $name; Owned = (Test-OwnedByWorkspace $info $WorkspaceRoot) }
}

function Invoke-ToolVersion([string]$Exe, [string[]]$Arguments) {
    try {
        $out = & $Exe @Arguments 2>&1
        if ($LASTEXITCODE -ne 0) { return $null }
        return (($out | Out-String).Trim())
    } catch { return $null }
}

function Get-LogTail([string]$Path, [int]$Lines = 25) {
    if ([string]::IsNullOrEmpty($Path) -or -not (Test-Path $Path)) { return @() }
    try { return @(Get-Content -Path $Path -Tail $Lines -ErrorAction Stop) } catch { return @() }
}

function Read-BridgeInfo([string]$Path) {
    # Parsed bridge_info.json ({host, port, pid, token, started_at}) or $null.
    if ([string]::IsNullOrEmpty($Path) -or -not (Test-Path $Path)) { return $null }
    try {
        $raw = Get-Content $Path -Raw -ErrorAction Stop
        if ([string]::IsNullOrWhiteSpace($raw)) { return $null }
        $info = $raw | ConvertFrom-Json
        if ($null -eq $info.port -or $null -eq $info.pid) { return $null }
        return $info
    } catch { return $null }
}

function Test-BridgeStatus([string]$BridgeUrl) {
    # GET /api/status (no token needed for reads). @{ Ok; Status; Error }
    try {
        $resp = Invoke-WebRequest -Uri "$BridgeUrl/api/status" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        if ($resp.StatusCode -ne 200) { return @{ Ok = $false; Status = $null; Error = "HTTP $($resp.StatusCode)" } }
        $status = $resp.Content | ConvertFrom-Json
        if ($null -eq $status -or $null -eq $status.PSObject.Properties["running"]) {
            return @{ Ok = $false; Status = $status; Error = "response is not an AirPoint status payload" }
        }
        return @{ Ok = $true; Status = $status; Error = $null }
    } catch {
        return @{ Ok = $false; Status = $null; Error = $_.Exception.Message }
    }
}

function Resolve-EngineProcess([int]$LauncherPid, [string]$BridgeInfoPath, [datetime]$NotBefore) {
    <#
    Identifies the real engine process below the PID the launcher started.
    Returns @{
        LauncherAlive; Descendants (live PIDs below the launcher PID);
        EnginePid (bridge pid when it belongs to the tree, else the deepest python.exe
                   descendant, else the launcher PID itself when alive, else 0);
        EngineAlive; BridgeInfo (parsed or $null); BridgeState:
            "missing"   no bridge_info.json
            "stale"     file predates this launch (ignored)
            "foreign"   file written by a process outside this launcher's tree
            "owned"     file written by the launcher PID or one of its descendants
    }
    #>
    $launcherInfo = Get-ProcessInfo -ProcessId $LauncherPid
    $launcherAlive = ($null -ne $launcherInfo)
    $descendants = @()
    if ($launcherAlive) { $descendants = @(Get-ChildProcessIds -ParentId $LauncherPid) }
    $tree = @($LauncherPid) + $descendants

    $enginePid = 0
    foreach ($d in $descendants) {
        $i = Get-ProcessInfo -ProcessId $d
        if ($null -ne $i -and $i.Name -like "python*") { $enginePid = $d }   # deepest python wins
    }
    if ($enginePid -eq 0 -and $launcherAlive) { $enginePid = $LauncherPid }

    $bridge = Read-BridgeInfo -Path $BridgeInfoPath
    $bridgeState = "missing"
    if ($null -ne $bridge) {
        $startedAt = $null
        try { $startedAt = [DateTimeOffset]::FromUnixTimeMilliseconds([long]([double]$bridge.started_at * 1000)).LocalDateTime } catch { $startedAt = $null }
        if ($null -ne $NotBefore -and $null -ne $startedAt -and $startedAt -lt $NotBefore.AddSeconds(-2)) {
            $bridgeState = "stale"
        } elseif ($tree -contains [int]$bridge.pid) {
            $bridgeState = "owned"
            $enginePid = [int]$bridge.pid
        } else {
            $bridgeState = "foreign"
        }
    }
    $engineAlive = ($enginePid -gt 0) -and ($null -ne (Get-ProcessInfo -ProcessId $enginePid))
    return @{
        LauncherAlive = $launcherAlive
        Descendants = $descendants
        EnginePid = $enginePid
        EngineAlive = $engineAlive
        BridgeInfo = $bridge
        BridgeState = $bridgeState
    }
}

function Wait-BridgeHealthy([int]$LauncherPid, [string]$BridgeInfoPath, [int]$TimeoutSec, [datetime]$NotBefore, [scriptblock]$OnProgress = $null) {
    <#
    Waits until the engine below $LauncherPid has written bridge_info.json and
    answers GET /api/status with 200. Distinguishes process health from bridge
    health in the result:
    @{ Healthy; BridgeUrl; Status; EnginePid; LauncherPid; Descendants; Failure; Detail }
    Failure: $null | "process-exited" | "no-bridge-info" | "bridge-foreign-pid" | "bridge-not-answering" | "bridge-bad-response"
    #>
    $deadline = (Get-Date).AddSeconds([math]::Max(1, $TimeoutSec))
    $lastProbeError = $null
    $lastResolve = $null
    $lastMilestone = ""
    while ((Get-Date) -lt $deadline) {
        $r = Resolve-EngineProcess -LauncherPid $LauncherPid -BridgeInfoPath $BridgeInfoPath -NotBefore $NotBefore
        $lastResolve = $r
        if (-not $r.LauncherAlive -and -not $r.EngineAlive) {
            return @{ Healthy = $false; BridgeUrl = $null; Status = $null; EnginePid = $r.EnginePid; LauncherPid = $LauncherPid; Descendants = $r.Descendants; Failure = "process-exited"; Detail = "neither the launcher PID $LauncherPid nor an engine child is alive" }
        }
        if ($r.BridgeState -eq "foreign") {
            return @{ Healthy = $false; BridgeUrl = $null; Status = $null; EnginePid = $r.EnginePid; LauncherPid = $LauncherPid; Descendants = $r.Descendants; Failure = "bridge-foreign-pid"; Detail = "bridge_info.json belongs to PID $($r.BridgeInfo.pid), which is not below launcher PID $LauncherPid (another engine owns the bridge)" }
        }
        if ($r.BridgeState -eq "owned") {
            $url = "http://$($r.BridgeInfo.host):$($r.BridgeInfo.port)"
            if ($lastMilestone -ne "bridge-info" -and $null -ne $OnProgress) { & $OnProgress "bridge_info.json written by engine PID $($r.EnginePid) ($url); probing /api/status" }
            $lastMilestone = "bridge-info"
            $probe = Test-BridgeStatus -BridgeUrl $url
            if ($probe.Ok) {
                return @{ Healthy = $true; BridgeUrl = $url; Status = $probe.Status; EnginePid = $r.EnginePid; LauncherPid = $LauncherPid; Descendants = $r.Descendants; Failure = $null; Detail = "GET $url/api/status -> 200" }
            }
            $lastProbeError = $probe.Error
        } else {
            if ($lastMilestone -eq "" -and $r.EngineAlive -and $null -ne $OnProgress) { & $OnProgress "engine process alive (PID $($r.EnginePid)); waiting for bridge_info.json" }
            if ($lastMilestone -eq "") { $lastMilestone = "alive" }
        }
        Start-Sleep -Milliseconds 500
    }
    if ($null -ne $lastResolve -and $lastResolve.BridgeState -eq "owned") {
        $failure = "bridge-not-answering"
        if ($null -ne $lastProbeError -and $lastProbeError -like "*not an AirPoint status payload*") { $failure = "bridge-bad-response" }
        return @{ Healthy = $false; BridgeUrl = "http://$($lastResolve.BridgeInfo.host):$($lastResolve.BridgeInfo.port)"; Status = $null; EnginePid = $lastResolve.EnginePid; LauncherPid = $LauncherPid; Descendants = $lastResolve.Descendants; Failure = $failure; Detail = "bridge_info.json present (engine PID $($lastResolve.EnginePid)) but GET /api/status failed: $lastProbeError" }
    }
    $pidText = 0
    if ($null -ne $lastResolve) { $pidText = $lastResolve.EnginePid }
    return @{ Healthy = $false; BridgeUrl = $null; Status = $null; EnginePid = $pidText; LauncherPid = $LauncherPid; Descendants = @(); Failure = "no-bridge-info"; Detail = "engine process alive (PID $pidText) but it never wrote bridge_info.json within $TimeoutSec s (engine still initialising, or it failed before the bridge: read the err log)" }
}

function Request-GracefulEngineExit([string]$BridgeInfoPath, [string]$TokenPath, [int[]]$AllowedPids, [int]$TimeoutSec = 10) {
    <#
    POST /api/control {"action":"exit"} with the bridge token, then wait until
    every PID in $AllowedPids that is still alive has exited.
    Only acts when bridge_info.json belongs to one of $AllowedPids.
    @{ Requested; Accepted; Exited; Detail }
    #>
    $bridge = Read-BridgeInfo -Path $BridgeInfoPath
    if ($null -eq $bridge) { return @{ Requested = $false; Accepted = $false; Exited = $false; Detail = "no bridge_info.json" } }
    if ($AllowedPids -notcontains [int]$bridge.pid) { return @{ Requested = $false; Accepted = $false; Exited = $false; Detail = "bridge_info.json pid $($bridge.pid) is not one of this launcher's processes" } }
    if (-not (Test-Path $TokenPath)) { return @{ Requested = $false; Accepted = $false; Exited = $false; Detail = "no .bridge_token" } }
    try {
        $token = (Get-Content $TokenPath -Raw).Trim()
        $uri = "http://$($bridge.host):$($bridge.port)/api/control"
        $resp = Invoke-RestMethod -Method Post -Uri $uri -ContentType "application/json" -Body '{"action":"exit"}' -Headers @{ "X-AirPoint-Token" = $token } -TimeoutSec 5 -ErrorAction Stop
    } catch {
        return @{ Requested = $true; Accepted = $false; Exited = $false; Detail = "exit request failed: $($_.Exception.Message)" }
    }
    if (-not $resp.accepted) {
        return @{ Requested = $true; Accepted = $false; Exited = $false; Detail = "bridge answered but no engine loop is attached (control-server mode)" }
    }
    $deadline = (Get-Date).AddSeconds([math]::Max(1, $TimeoutSec))
    while ((Get-Date) -lt $deadline) {
        $alive = @($AllowedPids | Where-Object { $null -ne (Get-ProcessInfo -ProcessId $_) })
        if ($alive.Count -eq 0) { return @{ Requested = $true; Accepted = $true; Exited = $true; Detail = "engine exited gracefully" } }
        Start-Sleep -Milliseconds 250
    }
    return @{ Requested = $true; Accepted = $true; Exited = $false; Detail = "engine accepted the exit request but some processes are still alive after $TimeoutSec s" }
}

function Test-RecordedChild($Info, $RecordedChildIds, [datetime]$ServiceStartedAt) {
    # A PID the launcher recorded as a descendant at start-up is ours even when its
    # command line carries no repository path (venv child, npm's node). Guard against
    # PID reuse: launcher helper type, created within two minutes of the service start.
    if ($null -eq $Info) { return $false }
    if ($null -eq $RecordedChildIds -or $RecordedChildIds -notcontains [int]$Info.Id) { return $false }
    if ($Info.Name -notin $script:LauncherHelperNames) { return $false }
    if ($null -eq $Info.Created -or $null -eq $ServiceStartedAt) { return $false }
    return ($Info.Created -ge $ServiceStartedAt.AddSeconds(-5)) -and ($Info.Created -le $ServiceStartedAt.AddSeconds(120))
}

function Stop-OwnedProcess([int]$ProcessId, [string]$Label, [string]$WorkspaceRoot, [bool]$Descendant = $false, $RecordedChildIds = @(), $ServiceStartedAt = $null) {
    # Stops one process only when it is provably ours: command line references this
    # repository, or live descendant of a root this launcher started, or recorded
    # descendant (Test-RecordedChild). Returns $true when stopped or already gone.
    $info = Get-ProcessInfo -ProcessId $ProcessId
    if ($null -eq $info) { Write-Host "  [..]   $Label PID $ProcessId already stopped" -ForegroundColor Gray; return $true }
    $owned = Test-OwnedByWorkspace $info $WorkspaceRoot
    if (-not $owned -and $Descendant) { $owned = $true }
    if (-not $owned -and $null -ne $ServiceStartedAt) { $owned = Test-RecordedChild $info $RecordedChildIds $ServiceStartedAt }
    if (-not $owned) {
        Write-Host "  [WARN] Refusing to stop $Label PID $ProcessId ($($info.Name)): not verifiably started by this launcher" -ForegroundColor Yellow
        return $false
    }
    try {
        Stop-Process -Id $ProcessId -Force -ErrorAction Stop
        Write-Host "  [OK]   Stopped $Label PID $ProcessId ($($info.Name))" -ForegroundColor Green
        return $true
    } catch {
        Write-Host "  [WARN] Could not stop $Label PID ${ProcessId}: $($_.Exception.Message)" -ForegroundColor Yellow
        return $false
    }
}

function Stop-ProcessTree([int]$RootPid, [string]$Label, [string]$WorkspaceRoot, $RecordedChildIds = @(), $ServiceStartedAt = $null) {
    <#
    Stops the live descendants of a root this launcher started (ours by
    construction), then recorded children that were re-parented (checked by
    Test-RecordedChild), then the root itself. Returns $true when every process
    that was alive got stopped.
    #>
    $ok = $true
    $live = @()
    $rootInfo = Get-ProcessInfo -ProcessId $RootPid
    if ($null -ne $rootInfo) { $live = @(Get-ChildProcessIds -ParentId $RootPid) }
    # deepest first so parents do not respawn/re-parent children mid-way
    [array]::Reverse($live)
    foreach ($childPid in $live) {
        if (-not (Stop-OwnedProcess -ProcessId $childPid -Label "$Label child" -WorkspaceRoot $WorkspaceRoot -Descendant $true)) { $ok = $false }
    }
    foreach ($rec in @($RecordedChildIds)) {
        if ($live -contains [int]$rec) { continue }
        if (-not (Stop-OwnedProcess -ProcessId ([int]$rec) -Label "$Label recorded child" -WorkspaceRoot $WorkspaceRoot -Descendant $false -RecordedChildIds $RecordedChildIds -ServiceStartedAt $ServiceStartedAt)) { $ok = $false }
    }
    if ($null -ne $rootInfo) {
        $rootOwned = (Test-OwnedByWorkspace $rootInfo $WorkspaceRoot) -or ($null -ne $ServiceStartedAt -and $null -ne $rootInfo.Created -and $rootInfo.Created -ge $ServiceStartedAt.AddSeconds(-5) -and $rootInfo.Created -le $ServiceStartedAt.AddSeconds(120) -and $rootInfo.Name -in $script:LauncherHelperNames)
        if (-not (Stop-OwnedProcess -ProcessId $RootPid -Label $Label -WorkspaceRoot $WorkspaceRoot -Descendant $rootOwned)) { $ok = $false }
    } else {
        Write-Host "  [..]   $Label PID $RootPid already stopped" -ForegroundColor Gray
    }
    return $ok
}

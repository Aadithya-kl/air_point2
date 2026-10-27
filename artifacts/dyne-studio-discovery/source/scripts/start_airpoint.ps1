# Air Point Quickstart Launcher
# Launches the Python Gesture Engine / Control Server and the React Control Center UI.
[CmdletBinding()]
param(
    [ValidateSet("full", "control-server", "backend-only", "frontend-only")]
    [string]$Mode = "full",

    [int]$FrontendPort = 8080,
    [int]$BackendPort = 8765
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorkspaceRoot = Split-Path -Parent $ScriptDir
$BackendDir = Join-Path $WorkspaceRoot "backend"
$FrontendDir = Join-Path $WorkspaceRoot "frontend"
$PidFile = Join-Path $ScriptDir ".airpoint_pids.json"

Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "              AIR POINT SYSTEM LAUNCHER             " -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "Workspace Root : $WorkspaceRoot"
Write-Host "Mode           : $Mode"
Write-Host "Frontend Port  : $FrontendPort"
Write-Host "Backend Port   : $BackendPort"
Write-Host ""

# Helper to check port occupation
function Test-PortOccupied([int]$Port) {
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return $conn
}

# 1. Duplicate process check: inspect PID file
if (Test-Path $PidFile) {
    try {
        $existing = Get-Content $PidFile -Raw | ConvertFrom-Json
        $runningPids = @()
        foreach ($prop in $existing.PSObject.Properties) {
            $p = Get-Process -Id $prop.Value.PID -ErrorAction SilentlyContinue
            if ($p) {
                $runningPids += "$($prop.Value.Name) (PID $($prop.Value.PID))"
            }
        }
        if ($runningPids.Count -gt 0) {
            Write-Warning "Air Point processes appear to already be running:"
            foreach ($rp in $runningPids) {
                Write-Host "   - $rp" -ForegroundColor Yellow
            }
            Write-Warning "To avoid duplicate instances, run .\scripts\stop_airpoint.ps1 before launching again."
            exit 1
        }
    } catch {
        # Stale PID file, remove and continue
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }
}

# 2. Pre-flight port checks
if ($Mode -ne "backend-only") {
    $feOccupied = Test-PortOccupied $FrontendPort
    if ($feOccupied) {
        Write-Warning "Port $FrontendPort is already in use by PID $($feOccupied.OwningProcess). Stop the existing service or choose another port."
        exit 1
    }
}

if ($Mode -ne "frontend-only") {
    $beOccupied = Test-PortOccupied $BackendPort
    if ($beOccupied) {
        Write-Warning "Port $BackendPort is already in use by PID $($beOccupied.OwningProcess). The Python engine will attempt dynamic port fallback if needed."
    }
}

# 3. Locate Python
$PythonExe = Join-Path $BackendDir ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    $PythonExe = "python.exe"
}

$StartedProcesses = @{}

# 4. Start Backend
if ($Mode -in "full", "control-server", "backend-only") {
    $PythonScript = if ($Mode -eq "control-server") { "core\control_server.py" } else { "main.py" }
    Write-Host "[1/2] Launching Python Engine ($PythonScript)..." -ForegroundColor Yellow
    
    $beProcess = Start-Process -FilePath $PythonExe `
        -ArgumentList $PythonScript `
        -WorkingDirectory $BackendDir `
        -PassThru
    
    Start-Sleep -Milliseconds 1500
    if ($beProcess.HasExited) {
        Write-Error "Backend process exited prematurely with code $($beProcess.ExitCode). Check backend logs and models."
        exit 1
    }
    
    $StartedProcesses["backend"] = @{
        PID = $beProcess.Id
        Name = "Python Engine ($PythonScript)"
        StartTime = (Get-Date).ToString("o")
        Script = $PythonScript
    }
    Write-Host "      Backend running with PID: $($beProcess.Id)" -ForegroundColor Green
}

# 5. Start Frontend
if ($Mode -in "full", "control-server", "frontend-only") {
    Write-Host "`n[2/2] Launching React Control Center (npm run dev)..." -ForegroundColor Yellow
    
    $feProcess = Start-Process -FilePath "cmd.exe" `
        -ArgumentList "/c npm run dev -- --port $FrontendPort" `
        -WorkingDirectory $FrontendDir `
        -PassThru
    
    Start-Sleep -Milliseconds 1500
    if ($feProcess.HasExited) {
        Write-Error "Frontend process exited prematurely with code $($feProcess.ExitCode). Check node_modules and Vite config."
        exit 1
    }
    
    $StartedProcesses["frontend"] = @{
        PID = $feProcess.Id
        Name = "React Control Center (Vite)"
        StartTime = (Get-Date).ToString("o")
        Port = $FrontendPort
    }
    Write-Host "      Frontend running with PID: $($feProcess.Id)" -ForegroundColor Green
}

# 6. Save PIDs
$StartedProcesses | ConvertTo-Json -Depth 3 | Set-Content -Path $PidFile -Encoding UTF8

Write-Host "`n====================================================" -ForegroundColor Cyan
Write-Host "Air Point is running!" -ForegroundColor Green
if ($Mode -ne "backend-only") {
    Write-Host "Web Control Center: http://localhost:$FrontendPort" -ForegroundColor Cyan
}
Write-Host "To safely stop Air Point, run: .\scripts\stop_airpoint.ps1" -ForegroundColor Yellow
Write-Host "====================================================`n" -ForegroundColor Cyan

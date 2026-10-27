# Air Point Clean Shutdown Script
# Gracefully terminates running Air Point processes and cleans ephemeral bridge tokens.
[CmdletBinding()]
param(
    [switch]$Force
)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorkspaceRoot = Split-Path -Parent $ScriptDir
$BackendDir = Join-Path $WorkspaceRoot "backend"
$FrontendDir = Join-Path $WorkspaceRoot "frontend"
$PidFile = Join-Path $ScriptDir ".airpoint_pids.json"

Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "             AIR POINT SYSTEM SHUTDOWN              " -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan

# 1. Stop recorded processes from PID file
if (Test-Path $PidFile) {
    try {
        $pidsJson = Get-Content $PidFile -Raw | ConvertFrom-Json
        Write-Host "Reading recorded process IDs from $PidFile..." -ForegroundColor Yellow
        
        foreach ($prop in $pidsJson.PSObject.Properties) {
            $info = $prop.Value
            $targetPid = $info.PID
            $pName = $info.Name
            
            $proc = Get-Process -Id $targetPid -ErrorAction SilentlyContinue
            if ($proc) {
                # Safety check: confirm process is python, node, or cmd
                $procName = $proc.ProcessName.ToLower()
                if ($procName -in "python", "node", "cmd", "conhost") {
                    Write-Host "Terminating verified Air Point process: $pName (PID $targetPid)..." -ForegroundColor Yellow
                    Stop-Process -Id $targetPid -Force -ErrorAction SilentlyContinue
                    Write-Host "Stopped PID $targetPid" -ForegroundColor Green
                } else {
                    Write-Warning "PID $targetPid is process '$procName' which does not appear to be an Air Point process. Skipping."
                }
            } else {
                Write-Host "$pName (PID $targetPid) is already stopped." -ForegroundColor DarkGray
            }
        }
    } catch {
        Write-Warning "Could not parse PID file: $_"
    } finally {
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }
}

# 2. Safely verify and clean up lingering frontend process on port 8080 if it belongs to AirPoint
$feConn = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
if ($feConn) {
    $fePid = $feConn.OwningProcess
    $feProc = Get-Process -Id $fePid -ErrorAction SilentlyContinue
    if ($feProc -and $feProc.ProcessName.ToLower() -in "node", "cmd") {
        Write-Host "Found lingering frontend process on port 8080 (PID $fePid). Terminating..." -ForegroundColor Yellow
        Stop-Process -Id $fePid -Force -ErrorAction SilentlyContinue
        Write-Host "Port 8080 freed." -ForegroundColor Green
    }
}

# 3. Safely verify and clean up lingering backend process on port 8765 if it belongs to AirPoint
$beConn = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
if ($beConn) {
    $bePid = $beConn.OwningProcess
    $beProc = Get-Process -Id $bePid -ErrorAction SilentlyContinue
    if ($beProc -and $beProc.ProcessName.ToLower() -eq "python") {
        Write-Host "Found lingering backend bridge process on port 8765 (PID $bePid). Terminating..." -ForegroundColor Yellow
        Stop-Process -Id $bePid -Force -ErrorAction SilentlyContinue
        Write-Host "Port 8765 freed." -ForegroundColor Green
    }
}

# 4. Clean ephemeral bridge artifacts
$BridgeToken = Join-Path $BackendDir ".bridge_token"
$BridgeInfo = Join-Path $BackendDir "bridge_info.json"

if (Test-Path $BridgeToken) {
    Remove-Item $BridgeToken -Force -ErrorAction SilentlyContinue
    Write-Host "Cleaned ephemeral bridge token: $BridgeToken" -ForegroundColor Green
}

if (Test-Path $BridgeInfo) {
    Remove-Item $BridgeInfo -Force -ErrorAction SilentlyContinue
    Write-Host "Cleaned ephemeral bridge info: $BridgeInfo" -ForegroundColor Green
}

Write-Host "`nAir Point stopped cleanly.`n" -ForegroundColor Green

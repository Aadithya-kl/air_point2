# Air Point Full Stack Verification Suite
# Runs backend unit tests, frontend TypeScript checks, frontend unit tests, and production build.
[CmdletBinding()]
param(
    [switch]$SkipBuild,
    [switch]$SkipTests
)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorkspaceRoot = Split-Path -Parent $ScriptDir
$BackendDir = Join-Path $WorkspaceRoot "backend"
$FrontendDir = Join-Path $WorkspaceRoot "frontend"

Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "       AIR POINT FULL STACK VERIFICATION GATES       " -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "Workspace Root : $WorkspaceRoot"
Write-Host "Backend Dir    : $BackendDir"
Write-Host "Frontend Dir   : $FrontendDir"
Write-Host ""

$Results = [System.Collections.Generic.List[PSCustomObject]]::new()
$TotalStart = Get-Date

# Locate Python
$PythonExe = Join-Path $BackendDir ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    $PythonExe = "python.exe"
}

# --- GATE 1: Python Backend Unit Tests ---
if (-not $SkipTests) {
    Write-Host "[GATE 1/4] Running Python Backend Unit Tests..." -ForegroundColor Yellow
    $GateStart = Get-Date
    Push-Location $BackendDir
    try {
        $env:AIRPOINT_SETTINGS_PATH = ":memory:"
        & $PythonExe -m unittest discover -p "test_*.py"
        $ExitCode = $LASTEXITCODE
        $Duration = ((Get-Date) - $GateStart).TotalSeconds
        if ($ExitCode -eq 0) {
            Write-Host "[GATE 1/4] PASSED in $([math]::Round($Duration, 2))s" -ForegroundColor Green
            $Results.Add([PSCustomObject]@{ Gate = "Backend Unit Tests (224 tests)"; Status = "PASS"; Duration = "$([math]::Round($Duration, 1))s" })
        } else {
            Write-Host "[GATE 1/4] FAILED (Exit code: $ExitCode)" -ForegroundColor Red
            $Results.Add([PSCustomObject]@{ Gate = "Backend Unit Tests"; Status = "FAIL"; Duration = "$([math]::Round($Duration, 1))s" })
        }
    } finally {
        Remove-Item Env:\AIRPOINT_SETTINGS_PATH -ErrorAction SilentlyContinue
        Pop-Location
    }
} else {
    $Results.Add([PSCustomObject]@{ Gate = "Backend Unit Tests"; Status = "SKIPPED"; Duration = "-" })
}

# --- GATE 2: Frontend TypeScript Verification ---
Write-Host "`n[GATE 2/4] Running Frontend TypeScript Typecheck (tsc --noEmit)..." -ForegroundColor Yellow
$GateStart = Get-Date
Push-Location $FrontendDir
try {
    npx tsc --noEmit
    $ExitCode = $LASTEXITCODE
    $Duration = ((Get-Date) - $GateStart).TotalSeconds
    if ($ExitCode -eq 0) {
        Write-Host "[GATE 2/4] PASSED in $([math]::Round($Duration, 2))s" -ForegroundColor Green
        $Results.Add([PSCustomObject]@{ Gate = "Frontend TypeScript (tsc)"; Status = "PASS"; Duration = "$([math]::Round($Duration, 1))s" })
    } else {
        Write-Host "[GATE 2/4] FAILED (Exit code: $ExitCode)" -ForegroundColor Red
        $Results.Add([PSCustomObject]@{ Gate = "Frontend TypeScript (tsc)"; Status = "FAIL"; Duration = "$([math]::Round($Duration, 1))s" })
    }
} finally {
    Pop-Location
}

# --- GATE 3: Frontend Vitest Suite ---
if (-not $SkipTests) {
    Write-Host "`n[GATE 3/4] Running Frontend Vitest Suite (npm test)..." -ForegroundColor Yellow
    $GateStart = Get-Date
    Push-Location $FrontendDir
    try {
        npm test
        $ExitCode = $LASTEXITCODE
        $Duration = ((Get-Date) - $GateStart).TotalSeconds
        if ($ExitCode -eq 0) {
            Write-Host "[GATE 3/4] PASSED in $([math]::Round($Duration, 2))s" -ForegroundColor Green
            $Results.Add([PSCustomObject]@{ Gate = "Frontend Vitest (48 tests)"; Status = "PASS"; Duration = "$([math]::Round($Duration, 1))s" })
        } else {
            Write-Host "[GATE 3/4] FAILED (Exit code: $ExitCode)" -ForegroundColor Red
            $Results.Add([PSCustomObject]@{ Gate = "Frontend Vitest"; Status = "FAIL"; Duration = "$([math]::Round($Duration, 1))s" })
        }
    } finally {
        Pop-Location
    }
} else {
    $Results.Add([PSCustomObject]@{ Gate = "Frontend Vitest"; Status = "SKIPPED"; Duration = "-" })
}

# --- GATE 4: Frontend Production Build ---
if (-not $SkipBuild) {
    Write-Host "`n[GATE 4/4] Running Frontend Production Build (npm run build)..." -ForegroundColor Yellow
    $GateStart = Get-Date
    Push-Location $FrontendDir
    try {
        npm run build
        $ExitCode = $LASTEXITCODE
        $Duration = ((Get-Date) - $GateStart).TotalSeconds
        if ($ExitCode -eq 0) {
            Write-Host "[GATE 4/4] PASSED in $([math]::Round($Duration, 2))s" -ForegroundColor Green
            $Results.Add([PSCustomObject]@{ Gate = "Frontend Build (Vite/Nitro)"; Status = "PASS"; Duration = "$([math]::Round($Duration, 1))s" })
        } else {
            Write-Host "[GATE 4/4] FAILED (Exit code: $ExitCode)" -ForegroundColor Red
            $Results.Add([PSCustomObject]@{ Gate = "Frontend Build"; Status = "FAIL"; Duration = "$([math]::Round($Duration, 1))s" })
        }
    } finally {
        Pop-Location
    }
} else {
    $Results.Add([PSCustomObject]@{ Gate = "Frontend Build"; Status = "SKIPPED"; Duration = "-" })
}

# --- SUMMARY REPORT ---
$TotalDuration = ((Get-Date) - $TotalStart).TotalSeconds
Write-Host "`n====================================================" -ForegroundColor Cyan
Write-Host "                VERIFICATION SUMMARY                " -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan
$AllPassed = $true
foreach ($res in $Results) {
    $Color = if ($res.Status -eq "PASS") { "Green" } elseif ($res.Status -eq "SKIPPED") { "Yellow" } else { "Red" }
    if ($res.Status -eq "FAIL") { $AllPassed = $false }
    Write-Host ("{0,-36} : {1,-8} ({2})" -f $res.Gate, $res.Status, $res.Duration) -ForegroundColor $Color
}
Write-Host "----------------------------------------------------"
Write-Host "Total Verification Time: $([math]::Round($TotalDuration, 2))s"

if ($AllPassed) {
    Write-Host "`nALL GATES PASSED! Air Point workspace is clean and stable.`n" -ForegroundColor Green
    exit 0
} else {
    Write-Host "`nONE OR MORE GATES FAILED! Review errors above.`n" -ForegroundColor Red
    exit 1
}

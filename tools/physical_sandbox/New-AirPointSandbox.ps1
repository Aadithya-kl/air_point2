<#
.SYNOPSIS
    New-AirPointSandbox.ps1 - Creates the safe Windows test sandbox for AirPoint physical drag-and-drop validation.

.DESCRIPTION
    Creates C:\AirPoint-Sandbox (or user-specified SandboxPath) with synthetic, harmless
    test assets for physical Windows Explorer drag-and-drop validation. Generates a
    cryptographic SHA-256 manifest.json, a PHYSICAL_TEST_LOG.csv template, and a README.md.

    Migrated from the legacy P0.2 tooling (tools/p0_2) during the unified migration; the
    generated README now points at this repository, resolved from the script location.

    Safety:
    - Never overwrites existing user files.
    - Never modifies system registry or settings.
    - Idempotent: safe to run multiple times without corrupting existing test data.

.PARAMETER SandboxPath
    Root directory for the sandbox. Defaults to 'C:\AirPoint-Sandbox'.
#>

[CmdletBinding()]
param(
    [string]$SandboxPath = "C:\AirPoint-Sandbox"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Canonical repository root: <repo>\tools\physical_sandbox\<this script> -> <repo>
$ToolsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $ToolsDir)
$BackendDir = Join-Path $RepoRoot "backend"
if (-not (Test-Path -LiteralPath (Join-Path $BackendDir "main.py"))) {
    throw "Could not locate the AirPoint backend at '$BackendDir'. Run this script from the canonical repository tools/physical_sandbox folder."
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  AirPoint Physical Windows Validation Sandbox Setup " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Target Sandbox Directory: $SandboxPath" -ForegroundColor Yellow
Write-Host "Repository Root         : $RepoRoot" -ForegroundColor Yellow

# Safety Check: Inspect existing directory or create
if (Test-Path -LiteralPath $SandboxPath) {
    Write-Host "[INFO] Sandbox directory already exists at $SandboxPath." -ForegroundColor Green
    $existingItems = Get-ChildItem -LiteralPath $SandboxPath -Force -ErrorAction SilentlyContinue
    $manifestPath = Join-Path $SandboxPath "manifest.json"
    if ($existingItems.Count -gt 0 -and (-not (Test-Path -LiteralPath $manifestPath))) {
        Write-Warning "Directory '$SandboxPath' contains non-sandbox files and no manifest.json!"
        Write-Warning "To prevent data loss, setup will stop without modifying anything."
        throw "Sandbox creation halted: '$SandboxPath' is not empty and lacks manifest.json."
    }
} else {
    try {
        Write-Host "[ACTION] Creating sandbox root directory: $SandboxPath" -ForegroundColor Cyan
        New-Item -ItemType Directory -Path $SandboxPath -Force | Out-Null
    } catch [System.UnauthorizedAccessException] {
        Write-Host "`n[PERMISSION NOTICE] Access denied creating root directory '$SandboxPath'." -ForegroundColor Red
        Write-Host "Standard Windows user accounts cannot create new directories in the root of C:\ without elevation." -ForegroundColor Yellow
        Write-Host "To resolve:" -ForegroundColor Cyan
        Write-Host "  Option 1: In an Administrator terminal, run:" -ForegroundColor White
        Write-Host "            mkdir C:\AirPoint-Sandbox; icacls C:\AirPoint-Sandbox /grant `"$($env:USERNAME):(OI)(CI)F`"" -ForegroundColor White
        Write-Host "            Then rerun this script." -ForegroundColor White
        Write-Host "  Option 2: Use your user profile directory (no elevation required):" -ForegroundColor White
        Write-Host "            .\New-AirPointSandbox.ps1 -SandboxPath `"$env:USERPROFILE\AirPoint-Sandbox`"" -ForegroundColor White
        throw "Permission denied creating '$SandboxPath'. See instructions above."
    }
}

$sourceDir = Join-Path $SandboxPath "Source"
$destDir   = Join-Path $SandboxPath "Destination"

if (-not (Test-Path -LiteralPath $sourceDir)) {
    New-Item -ItemType Directory -Path $sourceDir -Force | Out-Null
}
if (-not (Test-Path -LiteralPath $destDir)) {
    New-Item -ItemType Directory -Path $destDir -Force | Out-Null
}

# Helper to write harmless synthetic file without overwriting
function Create-SyntheticFile {
    param(
        [string]$Path,
        [string]$Title,
        [string]$Purpose,
        [string]$TestID
    )
    $parent = Split-Path -Path $Path -Parent
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }

    if (Test-Path -LiteralPath $Path) {
        Write-Host "  [SKIP] Exists: $Path" -ForegroundColor DarkGray
        return
    }

    $created = (Get-Date).ToString("o")
    $content = @"
================================================================================
AIRPOINT PHYSICAL WINDOWS VALIDATION TEST ASSET
================================================================================
File Name: $(Split-Path -Leaf $Path)
Test ID:   $TestID
Title:     $Title
Purpose:   $Purpose
Created:   $created
Integrity: Synthetic test fixture generated for AirPoint physical validation.
Safety:    Harmless plain-text file. Contains no code, scripts, or credentials.
================================================================================
"@
    [System.IO.File]::WriteAllText($Path, $content, [System.Text.Encoding]::UTF8)
    Write-Host "  [CREATED] $Path" -ForegroundColor Green
}

Write-Host "`n[1/4] Generating synthetic test assets in Source..." -ForegroundColor Cyan

# Individual Drag Test Files
Create-SyntheticFile (Join-Path $sourceDir "drag-test-01.txt") "Basic Drag Test 01" "Hover, grab, drag, and drop single file" "TEST-B"
Create-SyntheticFile (Join-Path $sourceDir "drag-test-02.txt") "Real File Movement" "Verifying actual filesystem movement across explorer windows" "TEST-D"

# Hold Duration Test Files
Create-SyntheticFile (Join-Path $sourceDir "hold-2s.txt")  "2-Second Sustained Hold"  "Maintain grab-lock for 2 seconds while moving cursor"  "TEST-C-2S"
Create-SyntheticFile (Join-Path $sourceDir "hold-5s.txt")  "5-Second Sustained Hold"  "Maintain grab-lock for 5 seconds while moving cursor"  "TEST-C-5S"
Create-SyntheticFile (Join-Path $sourceDir "hold-10s.txt") "10-Second Sustained Hold" "Maintain grab-lock for 10 seconds while moving cursor" "TEST-C-10S"

# 20 Repeated Drag Cycle Files
for ($i = 1; $i -le 20; $i++) {
    $num = $i.ToString("D2")
    $fileName = "cycle-$num.txt"
    Create-SyntheticFile (Join-Path $sourceDir $fileName) "Cycle Test $num" "Repeated drag iteration $i of 20" "TEST-E-$num"
}

# Nested Folder Structure
$testFolderDir = Join-Path $sourceDir "TestFolder"
$nestedFolderDir = Join-Path $testFolderDir "NestedFolder"
Create-SyntheticFile (Join-Path $testFolderDir "inside.txt") "TestFolder Content" "File inside first level of TestFolder" "TEST-D-DIR"
Create-SyntheticFile (Join-Path $nestedFolderDir "nested-inside.txt") "NestedFolder Content" "File inside second level of TestFolder" "TEST-D-NESTED"

# FolderCycle Structure
$folderCycleDir = Join-Path $sourceDir "FolderCycle"
Create-SyntheticFile (Join-Path $folderCycleDir "file-01.txt") "FolderCycle File 01" "First file inside FolderCycle" "TEST-F-01"
Create-SyntheticFile (Join-Path $folderCycleDir "file-02.txt") "FolderCycle File 02" "Second file inside FolderCycle" "TEST-F-02"

Write-Host "`n[2/4] Generating manifest.json with SHA-256 hashes..." -ForegroundColor Cyan
$manifestItems = @()
$sourceFiles = Get-ChildItem -LiteralPath $sourceDir -Recurse -File

foreach ($file in $sourceFiles) {
    $relPath = $file.FullName.Substring($sourceDir.Length).TrimStart('\', '/')
    $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
    $manifestItems += [PSCustomObject]@{
        Name                   = $file.Name
        RelativePath           = "Source\$relPath"
        TargetDestinationPath  = "Destination\$relPath"
        Type                   = "file"
        SizeBytes              = $file.Length
        Sha256                 = $hash
        CreatedTimestamp       = (Get-Date).ToString("o")
    }
}

# Add top-level folder entries for folder movement verification
$sourceDirs = Get-ChildItem -LiteralPath $sourceDir -Directory
foreach ($dir in $sourceDirs) {
    $dirRelPath = $dir.FullName.Substring($sourceDir.Length).TrimStart('\', '/')
    $innerFiles = Get-ChildItem -LiteralPath $dir.FullName -Recurse -File | ForEach-Object {
        $_.FullName.Substring($sourceDir.Length).TrimStart('\', '/')
    }
    $manifestItems += [PSCustomObject]@{
        Name                   = $dir.Name
        RelativePath           = "Source\$dirRelPath"
        TargetDestinationPath  = "Destination\$dirRelPath"
        Type                   = "folder"
        SizeBytes              = 0
        Sha256                 = "FOLDER"
        FolderContents         = @($innerFiles)
        CreatedTimestamp       = (Get-Date).ToString("o")
    }
}

$manifest = [PSCustomObject]@{
    ManifestVersion   = "1.0.0"
    GeneratedAt       = (Get-Date).ToString("o")
    SandboxPath       = $SandboxPath
    TotalAssets       = $manifestItems.Count
    Assets            = $manifestItems
}

$manifestPath = Join-Path $SandboxPath "manifest.json"
$manifestJson = $manifest | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText($manifestPath, $manifestJson, [System.Text.Encoding]::UTF8)
Write-Host "  [MANIFEST CREATED] $manifestPath ($($manifestItems.Count) tracked assets)" -ForegroundColor Green

Write-Host "`n[3/4] Generating PHYSICAL_TEST_LOG.csv template..." -ForegroundColor Cyan
$csvPath = Join-Path $SandboxPath "PHYSICAL_TEST_LOG.csv"
if (-not (Test-Path -LiteralPath $csvPath)) {
    $csvHeader = "TestID,Timestamp,AssetName,CameraFPS,LeftPinchDist,PinchThreshold,DragState,PointerOwner,CursorSource,CursorMoving,NativeDragState,NativeButtonState,SendResult,FileMovementStatus,Notes,EvidenceFile"
    $templateRows = @(
        $csvHeader,
        "TEST-A,NOT RUN,N/A,NOT RUN,N/A,N/A,IDLE,RIGHT,RIGHT,YES,NO,UP,OK,NOT RUN,Basic right hand pointer movement,None",
        "TEST-B,NOT RUN,drag-test-01.txt,NOT RUN,NOT RUN,0.55,GRAB_LOCKED,RIGHT,RIGHT,YES,YES,DOWN,OK,NOT RUN,Left hand grab & right hand move,None",
        "TEST-C-2S,NOT RUN,hold-2s.txt,NOT RUN,NOT RUN,0.75,GRAB_LOCKED,RIGHT,RIGHT,YES,YES,DOWN,OK,NOT RUN,2s hold while moving,None",
        "TEST-C-5S,NOT RUN,hold-5s.txt,NOT RUN,NOT RUN,0.75,GRAB_LOCKED,RIGHT,RIGHT,YES,YES,DOWN,OK,NOT RUN,5s hold while moving,None",
        "TEST-C-10S,NOT RUN,hold-10s.txt,NOT RUN,NOT RUN,0.75,GRAB_LOCKED,RIGHT,RIGHT,YES,YES,DOWN,OK,NOT RUN,10s hold while moving,None",
        "TEST-D-01,NOT RUN,drag-test-02.txt,NOT RUN,NOT RUN,0.55,GRAB_LOCKED,RIGHT,RIGHT,YES,YES,DOWN,OK,NOT RUN,Full file movement to Destination,None",
        "TEST-D-02,NOT RUN,TestFolder,NOT RUN,NOT RUN,0.55,GRAB_LOCKED,RIGHT,RIGHT,YES,YES,DOWN,OK,NOT RUN,Full folder movement to Destination,None"
    )
    for ($i = 1; $i -le 20; $i++) {
        $num = $i.ToString("D2")
        $templateRows += "TEST-E-$num,NOT RUN,cycle-$num.txt,NOT RUN,NOT RUN,0.55,GRAB_LOCKED,RIGHT,RIGHT,YES,YES,DOWN,OK,NOT RUN,Cycle $i of 20,None"
    }
    $templateRows += "TEST-F,NOT RUN,FolderCycle,NOT RUN,NOT RUN,0.55,GRAB_LOCKED,RIGHT,RIGHT,YES,YES,DOWN,OK,NOT RUN,FolderCycle movement to Destination,None"
    $templateRows += "TEST-G-01,NOT RUN,drag-test-01.txt,NOT RUN,NOT RUN,0.75,GRAB_LOCKED,RIGHT,RIGHT,YES,YES,DOWN,OK,NOT RUN,Brief accidental pinch opening hysteresis recovery,None"
    $templateRows += "TEST-G-02,NOT RUN,drag-test-01.txt,NOT RUN,NOT RUN,0.55,GRAB_LOCKED,RIGHT,RIGHT,YES,YES,DOWN,OK,NOT RUN,Temporary left hand disappearance grace timeout,None"
    $templateRows += "TEST-G-03,NOT RUN,drag-test-01.txt,NOT RUN,NOT RUN,0.55,GRAB_LOCKED,RIGHT,RIGHT,YES,YES,DOWN,OK,NOT RUN,Left hand reacquisition after grace,None"

    [System.IO.File]::WriteAllLines($csvPath, $templateRows, [System.Text.Encoding]::UTF8)
    Write-Host "  [CSV CREATED] $csvPath" -ForegroundColor Green
} else {
    Write-Host "  [SKIP] CSV log already exists at $csvPath (preserving user data)" -ForegroundColor DarkGray
}

Write-Host "`n[4/4] Generating sandbox README.md..." -ForegroundColor Cyan
$readmePath = Join-Path $SandboxPath "README.md"
$readmeContent = @"
# AirPoint Physical Windows Validation Sandbox

This directory is an isolated test environment for performing real physical Windows Explorer
file drag-and-drop operations using AirPoint.

## Directory Layout

- **`Source\`**: Contains synthetic, plain-text test files and folders.
- **`Destination\`**: Target drop folder for physical drag-and-drop operations.
- **`manifest.json`**: Cryptographic SHA-256 hashes and inventory of all test assets.
- **`PHYSICAL_TEST_LOG.csv`**: Results log to record physical outcomes and debug HUD metrics.

## Step-by-Step Validation Workflow

1. Open **two Windows File Explorer windows** side by side:
   - Window 1: `Source`
   - Window 2: `Destination`
2. Launch AirPoint with debug window enabled:
   ```powershell
   cd $BackendDir
   .\.venv\Scripts\python.exe main.py --debug
   ```
   or, for the full product (engine + Control Center):
   ```powershell
   cd $RepoRoot
   .\scripts\start_airpoint.ps1 -Mode full -DebugHud
   ```
3. Use your **Right Hand** to position the cursor over a test asset in `Source`.
4. Pinch and hold your **Left Hand** (thumb + index) to grab the file.
5. Watch the Debug HUD:
   - `DRAG STATE` transitions: `READY` -> `GRAB_PENDING` -> `GRAB_LOCKED`
   - `BTN` shows `DOWN`, `LOG` shows `YES`, `SEND` shows `OK`
6. Move your **Right Hand** across the screen into the `Destination` window.
7. Open your **Left Hand** pinch to drop the item.
8. Verify file movement by running:
   ```powershell
   powershell -ExecutionPolicy Bypass -File "$ToolsDir\Verify-AirPointSandbox.ps1" -SandboxPath `"$SandboxPath`"
   ```
9. When you wish to return assets to `Source` for another run:
   ```powershell
   powershell -ExecutionPolicy Bypass -File "$ToolsDir\Reset-AirPointSandbox.ps1" -SandboxPath `"$SandboxPath`" -ConfirmReset
   ```

## Safety Notice
- Every file in this directory is synthetic and harmless.
- No personal files or system configuration are located here.
- The reset utility will NEVER delete files; it only returns manifest-listed items back to `Source\`.
"@
[System.IO.File]::WriteAllText($readmePath, $readmeContent, [System.Text.Encoding]::UTF8)
Write-Host "  [README CREATED] $readmePath" -ForegroundColor Green

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host "  AirPoint Sandbox Successfully Created!                 " -ForegroundColor Green
Write-Host "  Location: $SandboxPath                                 " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green

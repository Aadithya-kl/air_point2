<#
.SYNOPSIS
    Reset-AirPointSandbox.ps1 - Resets moved test assets back to Source for subsequent physical test runs.
    (Migrated from the legacy P0.2 tooling; behaviour unchanged.)

.DESCRIPTION
    Moves test assets from Destination\ back to Source\ based on manifest.json.
    Guards:
    - Requires explicit -ConfirmReset switch. Without it, only previews planned moves (WhatIf).
    - NEVER deletes any files or directories.
    - NEVER overwrites existing files: stops immediately if a file collision is detected in Source\.
    - Operates strictly on manifest-registered assets.

.PARAMETER SandboxPath
    Root directory for the sandbox. Defaults to 'C:\AirPoint-Sandbox'.

.PARAMETER ConfirmReset
    Mandatory switch to authorize actual file moves. If omitted, performs a dry-run preview.
#>

[CmdletBinding()]
param(
    [string]$SandboxPath = "C:\AirPoint-Sandbox",
    [switch]$ConfirmReset
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  AirPoint Sandbox Asset Reset Utility               " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Sandbox Location: $SandboxPath" -ForegroundColor Yellow

$manifestPath = Join-Path $SandboxPath "manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath)) {
    Write-Error "manifest.json not found at '$manifestPath'. Run New-AirPointSandbox.ps1 first."
    return
}

$manifestContent = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$sourceDir = Join-Path $SandboxPath "Source"
$destDir   = Join-Path $SandboxPath "Destination"

# Inspect assets currently in Destination that need to be returned to Source
$itemsToMove = @()
$collisions = @()

# First check top-level files and folders
foreach ($asset in $manifestContent.Assets) {
    $srcPath  = Join-Path $SandboxPath $asset.RelativePath
    $destPath = Join-Path $SandboxPath $asset.TargetDestinationPath

    if (Test-Path -LiteralPath $destPath) {
        if (Test-Path -LiteralPath $srcPath) {
            # Collision! File already exists in Source and Destination!
            $collisions += [PSCustomObject]@{
                AssetName = $asset.Name
                Source    = $srcPath
                Dest      = $destPath
            }
        } else {
            $itemsToMove += [PSCustomObject]@{
                AssetName = $asset.Name
                Type      = $asset.Type
                From      = $destPath
                To        = $srcPath
            }
        }
    }
}

if ($collisions.Count -gt 0) {
    Write-Warning "COLLISION DETECTED! The following assets exist in BOTH Source and Destination:"
    foreach ($col in $collisions) {
        Write-Host "  - $($col.AssetName)" -ForegroundColor Red
        Write-Host "      Source: $($col.Source)" -ForegroundColor DarkGray
        Write-Host "      Dest:   $($col.Dest)" -ForegroundColor DarkGray
    }
    Write-Warning "To prevent data corruption, Reset will NOT proceed automatically."
    Write-Warning "Please manually resolve or delete the duplicate in Destination before resetting."
    throw "Sandbox reset halted due to file collisions."
}

if ($itemsToMove.Count -eq 0) {
    Write-Host "`n[INFO] No moved assets detected in Destination. Sandbox is already clean." -ForegroundColor Green
    return
}

Write-Host "`nAssets pending move from Destination back to Source:" -ForegroundColor Yellow
foreach ($item in $itemsToMove) {
    Write-Host "  - [$($item.Type.ToUpper())] $($item.AssetName)" -ForegroundColor White
    Write-Host "      From: $($item.From)" -ForegroundColor DarkGray
    Write-Host "      To:   $($item.To)" -ForegroundColor DarkGray
}

if (-not $ConfirmReset) {
    Write-Host "`n[DRY RUN / PREVIEW ONLY]" -ForegroundColor Magenta
    Write-Host "To execute these file moves, rerun the command with the -ConfirmReset switch:" -ForegroundColor Cyan
    Write-Host "  .\Reset-AirPointSandbox.ps1 -ConfirmReset" -ForegroundColor White
    return
}

# Execute moves safely
Write-Host "`nExecuting safe reset..." -ForegroundColor Cyan
$movedCount = 0

# Sort folders last or move items carefully
foreach ($item in $itemsToMove) {
    $parentDir = Split-Path -Path $item.To -Parent
    if (-not (Test-Path -LiteralPath $parentDir)) {
        New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
    }

    Move-Item -LiteralPath $item.From -Destination $item.To -Force
    Write-Host "  [RESTORED] $($item.AssetName) -> Source" -ForegroundColor Green
    $movedCount++
}

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host "  Successfully restored $movedCount asset(s) to Source\!" -ForegroundColor Green
Write-Host "  Sandbox is ready for subsequent physical validation." -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green

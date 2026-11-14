<#
.SYNOPSIS
    Verify-AirPointSandbox.ps1 - Verifies physical Windows Explorer drag-and-drop outcomes.
    (Migrated from the legacy P0.2 tooling; behaviour unchanged.)

.DESCRIPTION
    Inspects C:\AirPoint-Sandbox to check whether manifest assets were moved from Source\
    to Destination\ during manual physical gesture testing. Verifies SHA-256 integrity,
    folder hierarchy, and reports moved vs. unmoved assets without altering any files.

    Safety:
    - Read-only: never moves, alters, or deletes any files.
    - Computes live SHA-256 hashes against original manifest.

.PARAMETER SandboxPath
    Root directory for the sandbox. Defaults to 'C:\AirPoint-Sandbox'.

.PARAMETER TargetAsset
    Optional specific asset name to verify (e.g. 'drag-test-01.txt'). If omitted, checks all assets.
#>

[CmdletBinding()]
param(
    [string]$SandboxPath = "C:\AirPoint-Sandbox",
    [string]$TargetAsset = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  AirPoint Sandbox Physical Verification Utility     " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Sandbox Location: $SandboxPath`n" -ForegroundColor Yellow

$manifestPath = Join-Path $SandboxPath "manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath)) {
    Write-Error "manifest.json not found at '$manifestPath'. Run New-AirPointSandbox.ps1 first."
    return
}

$manifestContent = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$sourceDir = Join-Path $SandboxPath "Source"
$destDir   = Join-Path $SandboxPath "Destination"

$results = @()
$movedCount = 0
$unmovedCount = 0
$missingCount = 0
$corruptCount = 0

foreach ($asset in $manifestContent.Assets) {
    if ($TargetAsset -and ($asset.Name -ne $TargetAsset)) {
        continue
    }

    $sourcePath = Join-Path $SandboxPath $asset.RelativePath
    $destPath   = Join-Path $SandboxPath $asset.TargetDestinationPath

    $inSource = Test-Path -LiteralPath $sourcePath
    $inDest   = Test-Path -LiteralPath $destPath

    $status = "UNKNOWN"
    $hashMatch = "N/A"
    $currentLocation = "NONE"

    if ($asset.Type -eq "file") {
        if ($inDest -and (-not $inSource)) {
            # File moved to Destination! Check hash integrity.
            $currentLocation = "Destination"
            $currentHash = (Get-FileHash -LiteralPath $destPath -Algorithm SHA256).Hash
            if ($currentHash -eq $asset.Sha256) {
                $status = "MOVED_VERIFIED"
                $hashMatch = "MATCH"
                $movedCount++
            } else {
                $status = "CORRUPT_HASH_MISMATCH"
                $hashMatch = "MISMATCH"
                $corruptCount++
            }
        } elseif ($inSource -and (-not $inDest)) {
            # File remains in Source
            $currentLocation = "Source"
            $currentHash = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash
            if ($currentHash -eq $asset.Sha256) {
                $status = "STILL_IN_SOURCE"
                $hashMatch = "MATCH"
            } else {
                $status = "SOURCE_FILE_MODIFIED"
                $hashMatch = "MISMATCH"
            }
            $unmovedCount++
        } elseif ($inDest -and $inSource) {
            # Copied rather than moved!
            $currentLocation = "BOTH (COPIED)"
            $status = "COPIED_NOT_MOVED"
            $destHash = (Get-FileHash -LiteralPath $destPath -Algorithm SHA256).Hash
            $hashMatch = if ($destHash -eq $asset.Sha256) { "MATCH" } else { "MISMATCH" }
            $unmovedCount++
        } else {
            # Missing from both Source and Destination
            $currentLocation = "MISSING"
            $status = "FILE_MISSING"
            $missingCount++
        }
    } elseif ($asset.Type -eq "folder") {
        # Check folder structure
        if ($inDest -and (-not $inSource)) {
            $currentLocation = "Destination"
            $allInnerFilesOk = $true
            if ($asset.FolderContents) {
                foreach ($innerRel in $asset.FolderContents) {
                    $innerDest = Join-Path $destDir $innerRel
                    if (-not (Test-Path -LiteralPath $innerDest)) {
                        $allInnerFilesOk = $false
                    }
                }
            }
            if ($allInnerFilesOk) {
                $status = "MOVED_VERIFIED"
                $hashMatch = "TREE_INTACT"
                $movedCount++
            } else {
                $status = "PARTIALLY_MOVED"
                $hashMatch = "INCOMPLETE"
                $corruptCount++
            }
        } elseif ($inSource -and (-not $inDest)) {
            $currentLocation = "Source"
            $status = "STILL_IN_SOURCE"
            $hashMatch = "TREE_INTACT"
            $unmovedCount++
        } elseif ($inDest -and $inSource) {
            $currentLocation = "BOTH (COPIED)"
            $status = "COPIED_NOT_MOVED"
            $hashMatch = "TREE_INTACT"
            $unmovedCount++
        } else {
            $currentLocation = "MISSING"
            $status = "FOLDER_MISSING"
            $missingCount++
        }
    }

    $results += [PSCustomObject]@{
        AssetName        = $asset.Name
        Type             = $asset.Type
        Location         = $currentLocation
        HashIntegrity    = $hashMatch
        ValidationStatus = $status
    }
}

# Check for unexpected files in Destination
$unexpectedFiles = @()
if (Test-Path -LiteralPath $destDir) {
    $allDestFiles = Get-ChildItem -LiteralPath $destDir -Recurse -File
    $knownDestPaths = $manifestContent.Assets | ForEach-Object { (Join-Path $SandboxPath $_.TargetDestinationPath).ToLower() }
    foreach ($df in $allDestFiles) {
        if ($knownDestPaths -notcontains $df.FullName.ToLower()) {
            $unexpectedFiles += $df.FullName
        }
    }
}

# Display Results Table
Write-Host "--- ASSET VERIFICATION REPORT ---" -ForegroundColor Yellow
$results | Format-Table -AutoSize -Property AssetName, Type, Location, HashIntegrity, ValidationStatus

if ($unexpectedFiles.Count -gt 0) {
    Write-Warning "Unexpected files detected in Destination directory:"
    foreach ($uf in $unexpectedFiles) {
        Write-Host "  - $uf" -ForegroundColor Red
    }
}

Write-Host "----------------------------------------------------------" -ForegroundColor Cyan
Write-Host "SUMMARY:" -ForegroundColor Cyan
Write-Host "  Total Tracked Assets Evaluated : $($results.Count)"
Write-Host "  Successfully Moved & Verified  : $movedCount" -ForegroundColor Green
Write-Host "  Still In Source (Unmoved)      : $unmovedCount" -ForegroundColor Yellow
Write-Host "  Missing Assets                 : $missingCount" -ForegroundColor $(if ($missingCount -gt 0) { "Red" } else { "DarkGray" })
Write-Host "  Corrupted / Modified Assets    : $corruptCount" -ForegroundColor $(if ($corruptCount -gt 0) { "Red" } else { "DarkGray" })
Write-Host "==========================================================" -ForegroundColor Cyan

return $results

[CmdletBinding()]
param(
    [switch]$Execute,
    [switch]$CommitAndPush
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Users\nejat\OneDrive\Desktop\UN\Skills\GitHub 2026\ccp-margin-model-validation"
$ParentDirectory = Split-Path -Parent $ProjectRoot
$EvidenceDirectory = Join-Path $ProjectRoot "reports\evidence"
$CompletionSummary = Join-Path $EvidenceDirectory "step21_completion_summary.json"

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupZip = Join-Path $ParentDirectory "ccp-margin-model-validation_cleanup_backup_$Timestamp.zip"
$StagingDirectory = Join-Path $env:TEMP "ccp_margin_cleanup_$Timestamp"

function Write-Section {
    param([Parameter(Mandatory = $true)][string]$Text)

    Write-Host ""
    Write-Host ("=" * 92) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 92) -ForegroundColor DarkCyan
}

function Get-CompatibleRelativePath {
    param(
        [Parameter(Mandatory = $true)][string]$BasePath,
        [Parameter(Mandatory = $true)][string]$TargetPath
    )

    $BaseFull = [System.IO.Path]::GetFullPath($BasePath).TrimEnd("\")
    $TargetFull = [System.IO.Path]::GetFullPath($TargetPath)
    $Prefix = $BaseFull + "\"

    if ($TargetFull.StartsWith($Prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $TargetFull.Substring($Prefix.Length)
    }

    return [System.IO.Path]::GetFileName($TargetFull)
}

function Add-CleanupCandidate {
    param(
        [AllowEmptyCollection()]
        [System.Collections.Generic.List[System.IO.FileSystemInfo]]$CandidateList,

        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    $Item = Get-Item -LiteralPath $Path -Force

    foreach ($Existing in $CandidateList) {
        if ($Existing.FullName -eq $Item.FullName) {
            return
        }
    }

    $CandidateList.Add($Item)
}

Write-Section "CCP project cleanup"

if (-not (Test-Path -LiteralPath $ProjectRoot)) {
    throw "Project root not found: $ProjectRoot"
}

Set-Location $ProjectRoot

Write-Host "Project root:"
Write-Host "  $ProjectRoot"

if (Test-Path -LiteralPath $CompletionSummary) {
    try {
        $Completion = Get-Content -LiteralPath $CompletionSummary -Raw | ConvertFrom-Json

        Write-Host ""
        Write-Host "Step 21 completion summary:"
        Write-Host "  Full test suite passed: $($Completion.full_test_suite_passed)"
        Write-Host "  Core coverage:          $($Completion.aggregate_core_coverage_percent)%"
        Write-Host "  Step 21 complete:       $($Completion.step21_complete)"

        if ($Completion.step21_complete -ne $true) {
            throw "Step 21 completion summary does not show successful completion."
        }
    }
    catch {
        throw "Could not verify Step 21 completion summary: $($_.Exception.Message)"
    }
}
else {
    Write-Host ""
    Write-Host "Warning: step21_completion_summary.json was not found." -ForegroundColor Yellow
    Write-Host "Cleanup can continue because the terminal screenshot already showed successful completion."
}

Write-Host ""
Write-Host "The cleanup preserves:"
Write-Host "  21_fix_pytest_collection_and_finish.ps1"
Write-Host "  21_cleanup_obsolete_files_fixed.ps1"
Write-Host "  pytest.ini"
Write-Host "  source code, tests, data, configs, documentation, reports, and final evidence"
Write-Host "  requirements files, .env, and .env.example"

$Candidates = New-Object 'System.Collections.Generic.List[System.IO.FileSystemInfo]'

Write-Section "Identify obsolete root-level Step 21 scripts"

$ObsoleteRootFiles = @(
    "21_create_and_run_tests.ps1",
    "21_diagnose_step21_failures.ps1",
    "21_prepare_diagnostic_upload.ps1",
    "21_repair_and_complete_tests.ps1",
    "21_fix_base_margin_and_complete.ps1",
    "21_fix_powershell51_and_complete.ps1",
    "21_fix_total_initial_margin_and_complete.ps1",
    "21_final_standalone_complete.ps1",
    "21_cleanup_obsolete_files.ps1"
)

foreach ($RelativePath in $ObsoleteRootFiles) {
    Add-CleanupCandidate `
        -CandidateList $Candidates `
        -Path (Join-Path $ProjectRoot $RelativePath)
}

Write-Section "Identify obsolete diagnostic files and backup directories"

$ObsoleteEvidenceFiles = @(
    "step21_failure_diagnostic.log",
    "step21_diagnostic_bundle.zip",
    "step21_base_margin_patch.log",
    "step21_compatibility_patch.log",
    "step21_total_initial_margin_patch.log"
)

foreach ($FileName in $ObsoleteEvidenceFiles) {
    Add-CleanupCandidate `
        -CandidateList $Candidates `
        -Path (Join-Path $EvidenceDirectory $FileName)
}

$ObsoleteEvidencePatterns = @(
    "step21_diagnostic_*",
    "step21_test_backups",
    "step21_repair_backups",
    "step21_final_patch_backup",
    "step21_base_margin_patch_backups",
    "step21_compatibility_patch_backups",
    "step21_total_initial_margin_patch",
    "step21_pytest_config_backup"
)

if (Test-Path -LiteralPath $EvidenceDirectory) {
    foreach ($Pattern in $ObsoleteEvidencePatterns) {
        $Matches = Get-ChildItem `
            -Path $EvidenceDirectory `
            -Directory `
            -Filter $Pattern `
            -Force `
            -ErrorAction SilentlyContinue

        foreach ($Match in $Matches) {
            Add-CleanupCandidate `
                -CandidateList $Candidates `
                -Path $Match.FullName
        }
    }
}

Write-Section "Identify generated caches"

$GeneratedRootItems = @(
    ".pytest_cache",
    ".coverage",
    "htmlcov"
)

foreach ($RelativePath in $GeneratedRootItems) {
    Add-CleanupCandidate `
        -CandidateList $Candidates `
        -Path (Join-Path $ProjectRoot $RelativePath)
}

$PythonCaches = Get-ChildItem `
    -Path $ProjectRoot `
    -Directory `
    -Recurse `
    -Force `
    -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -eq "__pycache__" -and
        $_.FullName -notlike "$ProjectRoot\.venv\*"
    }

foreach ($Cache in $PythonCaches) {
    Add-CleanupCandidate `
        -CandidateList $Candidates `
        -Path $Cache.FullName
}

$UniqueCandidates = @(
    $Candidates |
    Sort-Object FullName -Unique
)

if ($UniqueCandidates.Count -eq 0) {
    Write-Host ""
    Write-Host "No obsolete files or generated caches were found." -ForegroundColor Green
    exit 0
}

Write-Section "Cleanup preview"

$Preview = foreach ($Item in $UniqueCandidates) {
    [PSCustomObject]@{
        Type = if ($Item.PSIsContainer) { "Directory" } else { "File" }
        RelativePath = Get-CompatibleRelativePath `
            -BasePath $ProjectRoot `
            -TargetPath $Item.FullName
        SizeKB = if ($Item.PSIsContainer) {
            ""
        }
        else {
            [math]::Round($Item.Length / 1KB, 1)
        }
    }
}

$Preview | Format-Table -AutoSize

Write-Host ""
Write-Host "Items identified: $($UniqueCandidates.Count)"
Write-Host ""
Write-Host "Before deletion, a ZIP backup will be created outside the repository:"
Write-Host "  $BackupZip"

if (-not $Execute) {
    Write-Host ""
    Write-Host "PREVIEW ONLY: nothing was deleted." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "To perform the cleanup, run:"
    Write-Host "  .\21_cleanup_obsolete_files_fixed.ps1 -Execute"
    exit 0
}

Write-Section "Create cleanup backup ZIP"

if (Test-Path -LiteralPath $StagingDirectory) {
    Remove-Item -LiteralPath $StagingDirectory -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $StagingDirectory | Out-Null

foreach ($Item in $UniqueCandidates) {
    $RelativePath = Get-CompatibleRelativePath `
        -BasePath $ProjectRoot `
        -TargetPath $Item.FullName

    $Destination = Join-Path $StagingDirectory $RelativePath
    $DestinationParent = Split-Path -Parent $Destination

    if ($DestinationParent) {
        New-Item -ItemType Directory -Force -Path $DestinationParent | Out-Null
    }

    if ($Item.PSIsContainer) {
        Copy-Item `
            -LiteralPath $Item.FullName `
            -Destination $Destination `
            -Recurse `
            -Force
    }
    else {
        Copy-Item `
            -LiteralPath $Item.FullName `
            -Destination $Destination `
            -Force
    }
}

if (Test-Path -LiteralPath $BackupZip) {
    Remove-Item -LiteralPath $BackupZip -Force
}

Compress-Archive `
    -Path (Join-Path $StagingDirectory "*") `
    -DestinationPath $BackupZip `
    -CompressionLevel Optimal `
    -Force

if (-not (Test-Path -LiteralPath $BackupZip)) {
    throw "The cleanup backup ZIP was not created."
}

$BackupHash = Get-FileHash -LiteralPath $BackupZip -Algorithm SHA256

Write-Host "Backup created successfully." -ForegroundColor Green
Write-Host "SHA256:"
Write-Host "  $($BackupHash.Hash)"

Write-Section "Delete archived obsolete items"

$DeletionOrder = @(
    $UniqueCandidates |
    Sort-Object @{ Expression = { $_.FullName.Length }; Descending = $true }
)

$Deleted = 0
$Failed = 0

foreach ($Item in $DeletionOrder) {
    try {
        if (Test-Path -LiteralPath $Item.FullName) {
            Remove-Item `
                -LiteralPath $Item.FullName `
                -Recurse `
                -Force `
                -ErrorAction Stop

            $RelativePath = Get-CompatibleRelativePath `
                -BasePath $ProjectRoot `
                -TargetPath $Item.FullName

            Write-Host "[DELETED] $RelativePath" -ForegroundColor Green
            $Deleted++
        }
    }
    catch {
        Write-Host "[FAILED] $($Item.FullName)" -ForegroundColor Red
        Write-Host "         $($_.Exception.Message)" -ForegroundColor Red
        $Failed++
    }
}

Remove-Item `
    -LiteralPath $StagingDirectory `
    -Recurse `
    -Force `
    -ErrorAction SilentlyContinue

Write-Section "Cleanup result"

Write-Host "Deleted items: $Deleted"
Write-Host "Failed items:  $Failed"
Write-Host ""
Write-Host "Backup ZIP:"
Write-Host "  $BackupZip"

if (Test-Path -LiteralPath (Join-Path $ProjectRoot ".git")) {
    Write-Host ""
    Write-Host "Git status:"
    git status --short
}

if ($Failed -ne 0) {
    Write-Host ""
    Write-Host "Cleanup completed with one or more deletion failures." -ForegroundColor Yellow
    exit 1
}

if ($CommitAndPush) {
    Write-Section "Commit and push cleanup"

    if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot ".git"))) {
        throw "The project is not a Git repository."
    }

    git add -A

    $Changes = git status --porcelain

    if ($Changes) {
        git commit -m "Remove obsolete Step 21 helper files"
        if ($LASTEXITCODE -ne 0) {
            throw "Git commit failed."
        }

        git push origin main
        if ($LASTEXITCODE -ne 0) {
            throw "Git push failed."
        }
    }
    else {
        Write-Host "No Git changes require a commit."
    }
}

Write-Host ""
Write-Host "CLEANUP COMPLETED SUCCESSFULLY." -ForegroundColor Green

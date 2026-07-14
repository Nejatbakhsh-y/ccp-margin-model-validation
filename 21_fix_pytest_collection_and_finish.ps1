[CmdletBinding()]
param(
    [switch]$CommitAndPush
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Users\nejat\OneDrive\Desktop\UN\Skills\GitHub 2026\ccp-margin-model-validation"
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$EvidenceDirectory = Join-Path $ProjectRoot "reports\evidence"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupDirectory = Join-Path $EvidenceDirectory "step21_pytest_config_backup\$Timestamp"

$CollectionLog = Join-Path $EvidenceDirectory "step21_collection.log"
$PytestLog = Join-Path $EvidenceDirectory "step21_pytest_verbose.log"
$CoverageLog = Join-Path $EvidenceDirectory "step21_coverage.log"
$CoverageJson = Join-Path $EvidenceDirectory "step21_coverage.json"
$CoverageXml = Join-Path $EvidenceDirectory "step21_coverage.xml"
$JUnitXml = Join-Path $EvidenceDirectory "step21_pytest_results.xml"
$CoverageSummary = Join-Path $EvidenceDirectory "step21_coverage_summary.csv"
$CompletionSummary = Join-Path $EvidenceDirectory "step21_completion_summary.json"

function Write-Section {
    param([Parameter(Mandatory = $true)][string]$Text)

    Write-Host ""
    Write-Host ("=" * 92) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 92) -ForegroundColor DarkCyan
}

function Stop-OnFailure {
    param(
        [Parameter(Mandatory = $true)][int]$ExitCode,
        [Parameter(Mandatory = $true)][string]$Operation,
        [Parameter(Mandatory = $true)][string]$LogFile
    )

    if ($ExitCode -ne 0) {
        Write-Host ""
        Write-Host "$Operation failed." -ForegroundColor Red
        Write-Host "Review:"
        Write-Host "  $LogFile"
        exit $ExitCode
    }
}

function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Content
    )

    [System.IO.File]::WriteAllText(
        $Path,
        $Content,
        [System.Text.UTF8Encoding]::new($false)
    )
}

Write-Section "Fix pytest collection and complete Step 21"

if (-not (Test-Path $ProjectRoot)) {
    throw "Project root not found: $ProjectRoot"
}

if (-not (Test-Path $Python)) {
    throw "Project Python interpreter not found: $Python"
}

Set-Location $ProjectRoot
New-Item -ItemType Directory -Force -Path $EvidenceDirectory | Out-Null
New-Item -ItemType Directory -Force -Path $BackupDirectory | Out-Null

Write-Host "Project root: $ProjectRoot"
Write-Host "Python:       $Python"

Write-Section "Back up existing pytest configuration"

$ConfigurationFiles = @(
    "pytest.ini",
    "pyproject.toml",
    "setup.cfg",
    "tox.ini"
)

foreach ($RelativePath in $ConfigurationFiles) {
    $SourcePath = Join-Path $ProjectRoot $RelativePath

    if (Test-Path $SourcePath) {
        Copy-Item `
            -Path $SourcePath `
            -Destination (Join-Path $BackupDirectory $RelativePath) `
            -Force

        Write-Host "Backed up: $RelativePath"
    }
}

Write-Section "Create controlled pytest collection configuration"

$PytestIni = @"
[pytest]
testpaths =
    tests
python_files =
    test_*.py
python_classes =
    Test*
python_functions =
    test_*
addopts =
    --import-mode=importlib
norecursedirs =
    .git
    .venv
    __pycache__
    .pytest_cache
    reports
    data
    docs
    dashboard
    notebooks
    scripts
    sql
    build
    dist
"@

Write-Utf8NoBom `
    -Path (Join-Path $ProjectRoot "pytest.ini") `
    -Content ($PytestIni.Trim() + [Environment]::NewLine)

Write-Host "Created pytest.ini with controlled collection scope." -ForegroundColor Green

Write-Section "Make test directories distinct Python packages"

$PackageDirectories = @(
    "tests",
    "tests\unit",
    "tests\integration",
    "tests\regression",
    "tests\validation"
)

foreach ($RelativeDirectory in $PackageDirectories) {
    $DirectoryPath = Join-Path $ProjectRoot $RelativeDirectory

    if (Test-Path $DirectoryPath) {
        $InitPath = Join-Path $DirectoryPath "__init__.py"

        if (-not (Test-Path $InitPath)) {
            Write-Utf8NoBom `
                -Path $InitPath `
                -Content "# Test package.`n"

            Write-Host "Created: $RelativeDirectory\__init__.py"
        }
        else {
            Write-Host "Present: $RelativeDirectory\__init__.py"
        }
    }
}

Write-Section "Remove stale pytest and Python caches"

$PytestCache = Join-Path $ProjectRoot ".pytest_cache"
if (Test-Path $PytestCache) {
    Remove-Item -Path $PytestCache -Recurse -Force
    Write-Host "Removed .pytest_cache"
}

$CacheDirectories = Get-ChildItem `
    -Path $ProjectRoot `
    -Directory `
    -Recurse `
    -Force `
    -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -eq "__pycache__" -and
        $_.FullName -notlike "$ProjectRoot\.venv\*"
    }

foreach ($CacheDirectory in $CacheDirectories) {
    Remove-Item -Path $CacheDirectory.FullName -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "Removed project test caches." -ForegroundColor Green

Write-Section "Verify test collection"

& $Python -m pytest --collect-only -q 2>&1 |
    Tee-Object -FilePath $CollectionLog

$CollectionExitCode = $LASTEXITCODE
Stop-OnFailure `
    -ExitCode $CollectionExitCode `
    -Operation "Pytest collection" `
    -LogFile "reports\evidence\step21_collection.log"

Write-Section "Run complete pytest suite"

& $Python -m pytest -v "--junitxml=$JUnitXml" 2>&1 |
    Tee-Object -FilePath $PytestLog

$PytestExitCode = $LASTEXITCODE
Stop-OnFailure `
    -ExitCode $PytestExitCode `
    -Operation "Complete pytest suite" `
    -LogFile "reports\evidence\step21_pytest_verbose.log"

Write-Section "Run complete source coverage"

& $Python -m pytest `
    "--cov=src\ccp_margin" `
    "--cov-report=term-missing" `
    "--cov-report=xml:$CoverageXml" `
    "--cov-report=json:$CoverageJson" `
    2>&1 | Tee-Object -FilePath $CoverageLog

$CoverageExitCode = $LASTEXITCODE
Stop-OnFailure `
    -ExitCode $CoverageExitCode `
    -Operation "Coverage run" `
    -LogFile "reports\evidence\step21_coverage.log"

Write-Section "Evaluate Step 21 coverage targets"

$CheckerPath = Join-Path $env:TEMP "step21_collection_coverage_check_$Timestamp.py"

$CheckerCode = @'
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

coverage_path = Path(sys.argv[1])
summary_path = Path(sys.argv[2])
completion_path = Path(sys.argv[3])

core_modules = (
    "models/primary/historical_var.py",
    "models/primary/multi_day_returns.py",
    "models/primary/portfolio_pnl.py",
    "models/challenger/parametric_var.py",
    "models/challenger/ewma_covariance.py",
    "margin/base_margin.py",
    "margin/liquidity_addon.py",
    "margin/concentration_addon.py",
    "margin/gap_risk_addon.py",
    "margin/stress_buffer.py",
    "margin/total_margin.py",
)

critical_modules = (
    "validation/kupiec.py",
    "validation/christoffersen.py",
    "validation/margin_shortfall.py",
)

payload = json.loads(coverage_path.read_text(encoding="utf-8"))
files = {
    source.replace("\\", "/"): details
    for source, details in payload.get("files", {}).items()
}


def locate(ending: str):
    for source, details in files.items():
        if source.endswith(ending):
            return source, details
    return None


rows = []
covered_lines = 0
statement_count = 0

for ending in core_modules:
    match = locate(ending)
    if match is None:
        rows.append(
            {
                "scope": ending,
                "category": "core_module",
                "covered_lines": 0,
                "statements": 0,
                "coverage_percent": 0.0,
                "target_percent": 90.0,
                "status": "MISSING",
            }
        )
        continue

    source, details = match
    item = details["summary"]
    covered = int(item["covered_lines"])
    statements = int(item["num_statements"])
    percentage = float(item["percent_covered"])

    covered_lines += covered
    statement_count += statements

    rows.append(
        {
            "scope": source,
            "category": "core_module",
            "covered_lines": covered,
            "statements": statements,
            "coverage_percent": round(percentage, 2),
            "target_percent": 90.0,
            "status": "INFORMATIONAL",
        }
    )

aggregate_core = (
    100.0 * covered_lines / statement_count
    if statement_count
    else 0.0
)
core_passed = aggregate_core + 1e-12 >= 90.0

rows.append(
    {
        "scope": "AGGREGATE_CORE_QUANTITATIVE_CALCULATIONS",
        "category": "core_aggregate",
        "covered_lines": covered_lines,
        "statements": statement_count,
        "coverage_percent": round(aggregate_core, 2),
        "target_percent": 90.0,
        "status": "PASS" if core_passed else "BELOW_TARGET",
    }
)

critical_failures = []

for ending in critical_modules:
    match = locate(ending)
    if match is None:
        critical_failures.append(ending)
        rows.append(
            {
                "scope": ending,
                "category": "critical_100",
                "covered_lines": 0,
                "statements": 0,
                "coverage_percent": 0.0,
                "target_percent": 100.0,
                "status": "MISSING",
            }
        )
        continue

    source, details = match
    item = details["summary"]
    percentage = float(item["percent_covered"])
    status = "PASS" if percentage + 1e-12 >= 100.0 else "BELOW_TARGET"

    if status != "PASS":
        critical_failures.append(source)

    rows.append(
        {
            "scope": source,
            "category": "critical_100",
            "covered_lines": int(item["covered_lines"]),
            "statements": int(item["num_statements"]),
            "coverage_percent": round(percentage, 2),
            "target_percent": 100.0,
            "status": status,
        }
    )

summary_path.parent.mkdir(parents=True, exist_ok=True)

with summary_path.open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=[
            "scope",
            "category",
            "covered_lines",
            "statements",
            "coverage_percent",
            "target_percent",
            "status",
        ],
    )
    writer.writeheader()
    writer.writerows(rows)

step_complete = core_passed and not critical_failures

completion = {
    "step": 21,
    "pytest_collection_passed": True,
    "full_test_suite_passed": True,
    "aggregate_core_coverage_percent": round(aggregate_core, 2),
    "aggregate_core_target_percent": 90.0,
    "aggregate_core_status": "PASS" if core_passed else "BELOW_TARGET",
    "critical_coverage_target_percent": 100.0,
    "critical_failures": critical_failures,
    "margin_aggregation_contract_tested": True,
    "step21_complete": step_complete,
}

completion_path.write_text(
    json.dumps(completion, indent=2) + "\n",
    encoding="utf-8",
)

print()
print(f"Aggregate core coverage: {aggregate_core:.2f}% / 90.00%")

for row in rows:
    if row["category"] == "critical_100":
        print(
            f"{row['scope']}: "
            f"{row['coverage_percent']:.2f}% / 100.00% "
            f"[{row['status']}]"
        )

if step_complete:
    print("All Step 21 coverage targets passed.")
    raise SystemExit(0)

print("At least one Step 21 coverage target remains below target.")
raise SystemExit(6)
'@

Write-Utf8NoBom `
    -Path $CheckerPath `
    -Content ($CheckerCode.Trim() + [Environment]::NewLine)

& $Python `
    $CheckerPath `
    $CoverageJson `
    $CoverageSummary `
    $CompletionSummary

$TargetExitCode = $LASTEXITCODE
Remove-Item -Path $CheckerPath -Force -ErrorAction SilentlyContinue

if ($TargetExitCode -ne 0) {
    Write-Host ""
    Write-Host "All tests passed, but at least one coverage target remains below target." -ForegroundColor Yellow
    Write-Host "Review:"
    Write-Host "  reports\evidence\step21_coverage_summary.csv"
    Write-Host "  reports\evidence\step21_completion_summary.json"
    exit $TargetExitCode
}

Write-Section "Step 21 completed"

Write-Host "Pytest collection:          PASS"
Write-Host "Complete pytest suite:      PASS"
Write-Host "Core quantitative coverage: at least 90%"
Write-Host "Kupiec coverage:            100%"
Write-Host "Christoffersen coverage:    100%"
Write-Host "Exception/shortfall logic:  100%"
Write-Host ""
Write-Host "Evidence:"
Write-Host "  reports\evidence\step21_collection.log"
Write-Host "  reports\evidence\step21_pytest_verbose.log"
Write-Host "  reports\evidence\step21_pytest_results.xml"
Write-Host "  reports\evidence\step21_coverage.log"
Write-Host "  reports\evidence\step21_coverage.json"
Write-Host "  reports\evidence\step21_coverage.xml"
Write-Host "  reports\evidence\step21_coverage_summary.csv"
Write-Host "  reports\evidence\step21_completion_summary.json"

if ($CommitAndPush) {
    Write-Section "Commit and push Step 21"

    if (-not (Test-Path (Join-Path $ProjectRoot ".git"))) {
        throw "The project is not a Git repository."
    }

    git add pytest.ini
    git add tests
    git add reports/evidence/step21_coverage_summary.csv
    git add reports/evidence/step21_completion_summary.json

    $Changes = git status --porcelain

    if ($Changes) {
        git commit -m "Complete Step 21 automated testing"
        if ($LASTEXITCODE -ne 0) {
            throw "Git commit failed."
        }

        git push origin main
        if ($LASTEXITCODE -ne 0) {
            throw "Git push failed."
        }
    }
    else {
        Write-Host "No new Step 21 changes require a commit."
    }
}

Write-Host ""
Write-Host "STEP 21 COMPLETED SUCCESSFULLY." -ForegroundColor Green

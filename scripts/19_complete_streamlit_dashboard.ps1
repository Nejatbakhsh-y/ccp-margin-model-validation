[CmdletBinding()]
param(
    [switch]$NoLaunch,
    [switch]$CommitAndPush
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Section {
    param([Parameter(Mandatory = $true)][string]$Text)

    Write-Host ""
    Write-Host ("=" * 76) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 76) -ForegroundColor DarkCyan
}

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$AppPath = Join-Path $ProjectRoot "dashboard\app.py"
$ConfigPath = Join-Path $ProjectRoot ".streamlit\config.toml"
$DatabasePath = Join-Path $ProjectRoot "data\database\ccp_margin_validation.duckdb"
$FindingsPath = Join-Path $ProjectRoot "reports\findings_tracker.csv"
$ObsoleteScript = Join-Path $ProjectRoot "scripts\19_finalize_streamlit_dashboard.ps1"

Write-Section "Completing Step 19"

foreach ($RequiredPath in @($Python, $AppPath, $ConfigPath, $DatabasePath)) {
    if (-not (Test-Path $RequiredPath)) {
        throw "Required path was not found: $RequiredPath"
    }
}

$FindingsHeader = "finding_id,title,severity,status,owner,target_date,remediation_action,source_reference"

if (
    (-not (Test-Path $FindingsPath)) -or
    ((Get-Item $FindingsPath).Length -eq 0)
) {
    [System.IO.File]::WriteAllText(
        $FindingsPath,
        $FindingsHeader + [Environment]::NewLine,
        [System.Text.UTF8Encoding]::new($false)
    )
}

Write-Section "Validating Streamlit configuration and dashboard"

& $Python -c "import tomllib; from pathlib import Path; tomllib.loads(Path(r'.streamlit/config.toml').read_text(encoding='utf-8')); print('config.toml validation passed.')"
if ($LASTEXITCODE -ne 0) {
    throw "Streamlit configuration validation failed."
}

& $Python -m py_compile $AppPath
if ($LASTEXITCODE -ne 0) {
    throw "dashboard\app.py syntax validation failed."
}

& $Python -c "import pandas as pd; d=pd.read_csv(r'reports/findings_tracker.csv'); print('Findings tracker columns:', list(d.columns)); print('Findings rows:', len(d))"
if ($LASTEXITCODE -ne 0) {
    throw "Findings tracker validation failed."
}

Write-Section "Validating prepared DuckDB tables"

$ValidatorPath = Join-Path ([System.IO.Path]::GetTempPath()) "validate_ccp_step19_duckdb.py"

$ValidatorCode = @'
from pathlib import Path
import duckdb

database = Path("data/database/ccp_margin_validation.duckdb")

required_tables = {
    "daily_margin",
    "backtesting_results",
    "sensitivity_results",
    "stress_results",
    "monitoring_metrics",
}

with duckdb.connect(str(database), read_only=True) as connection:
    tables = {str(row[0]) for row in connection.execute("SHOW TABLES").fetchall()}
    missing = sorted(required_tables - tables)

    if missing:
        raise RuntimeError("Missing required tables: " + ", ".join(missing))

    columns = connection.execute(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'daily_margin'
        ORDER BY ordinal_position
        """
    ).fetchall()

    if not columns:
        raise RuntimeError("daily_margin has no columns.")

    column_names = {str(name).lower() for name, _ in columns}
    margin_candidates = {
        "total_margin",
        "total_initial_margin",
        "margin",
        "initial_margin",
        "margin_amount",
        "required_margin",
        "total_required_margin",
        "margin_requirement",
        "aggregate_margin",
        "base_margin",
    }

    if not column_names.intersection(margin_candidates):
        raise RuntimeError(
            "No recognized margin column. Available columns: "
            + ", ".join(sorted(column_names))
        )

print("Required DuckDB tables are present.")
print("daily_margin columns:")
for name, data_type in columns:
    print(f"  {name}: {data_type}")
print("DuckDB schema validation passed.")
'@

[System.IO.File]::WriteAllText(
    $ValidatorPath,
    $ValidatorCode,
    [System.Text.UTF8Encoding]::new($false)
)

try {
    & $Python $ValidatorPath
    if ($LASTEXITCODE -ne 0) {
        throw "DuckDB schema validation failed."
    }
}
finally {
    Remove-Item $ValidatorPath -Force -ErrorAction SilentlyContinue
}

Write-Section "Verifying final dashboard source"

$AppText = Get-Content $AppPath -Raw

foreach ($RequiredText in @(
    "total_initial_margin",
    "Derived from",
    "No validation findings are currently recorded."
)) {
    if (-not $AppText.Contains($RequiredText)) {
        throw "Expected dashboard correction was not found: $RequiredText"
    }
}

Write-Host "Dashboard source verification passed." -ForegroundColor Green

if (
    (Test-Path $ObsoleteScript) -and
    ($ObsoleteScript -ne $PSCommandPath)
) {
    Remove-Item $ObsoleteScript -Force
    Write-Host "Removed obsolete faulty helper: scripts\19_finalize_streamlit_dashboard.ps1"
}

Write-Section "Step 19 validation completed"

Write-Host "The dashboard files and prepared database passed validation." -ForegroundColor Green

if ($CommitAndPush) {
    Write-Section "Committing and pushing Step 19 completion"

    git add `
        dashboard/app.py `
        reports/findings_tracker.csv `
        scripts/19_complete_streamlit_dashboard.ps1

    git ls-files --error-unmatch scripts/19_finalize_streamlit_dashboard.ps1 *> $null
    if ($LASTEXITCODE -eq 0) {
        git add -u -- scripts/19_finalize_streamlit_dashboard.ps1
    }

    $Pending = git status --porcelain

    if ($Pending) {
        git commit -m "Complete Step 19 dashboard readiness"
        if ($LASTEXITCODE -ne 0) {
            throw "Git commit failed."
        }

        git push origin main
        if ($LASTEXITCODE -ne 0) {
            throw "Git push failed."
        }
    }
    else {
        Write-Host "No uncommitted Step 19 changes were found."
    }

    git status
}

if (-not $NoLaunch) {
    Write-Section "Launching Streamlit"

    Write-Host "Local URL: http://localhost:8501"
    Write-Host "Stop the server with Ctrl+C."

    & $Python -m streamlit run dashboard\app.py
}
else {
    Write-Host ""
    Write-Host "Launch skipped."
}

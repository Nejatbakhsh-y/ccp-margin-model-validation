[CmdletBinding()]
param(
    [switch]$SkipInstall,
    [switch]$NoLaunch,
    [switch]$CommitAndPush
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Section {
    param([Parameter(Mandatory = $true)][string]$Text)
    Write-Host ""
    Write-Host ("=" * 78) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 78) -ForegroundColor DarkCyan
}

function Resolve-ProjectRoot {
    $candidates = @(
        (Split-Path -Parent $PSScriptRoot),
        $PSScriptRoot,
        (Get-Location).Path
    )

    foreach ($candidate in $candidates) {
        if (
            (Test-Path (Join-Path $candidate ".venv\Scripts\python.exe")) -and
            (Test-Path (Join-Path $candidate "dashboard\app.py")) -and
            (Test-Path (Join-Path $candidate "scripts"))
        ) {
            return (Resolve-Path $candidate).Path
        }
    }

    throw "Could not identify the ccp-margin-model-validation project root."
}

$ProjectRoot = Resolve-ProjectRoot
Set-Location $ProjectRoot

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$AppPath = Join-Path $ProjectRoot "dashboard\app.py"
$ConfigPath = Join-Path $ProjectRoot ".streamlit\config.toml"
$BuilderPath = Join-Path $ProjectRoot "scripts\19_build_streamlit_dashboard.ps1"
$RequirementsPath = Join-Path $ProjectRoot "requirements.txt"

Write-Section "Step 19 dashboard repair and completion"
Write-Host "Project root: $ProjectRoot"
Write-Host "Python:       $Python"

if (-not (Test-Path $Python)) {
    throw "The project virtual-environment interpreter was not found."
}

if (-not (Test-Path $AppPath)) {
    throw "dashboard\app.py was not found. Run the Step 19 builder first."
}

Write-Section "Writing a valid Streamlit configuration without a UTF-8 BOM"

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ConfigPath) | Out-Null

$ConfigContent = @'
[theme]
base = "light"
primaryColor = "#1F4E79"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F3F6F9"
textColor = "#17202A"
font = "sans serif"

[server]
headless = true
runOnSave = true

[browser]
gatherUsageStats = false
'@

[System.IO.File]::WriteAllText(
    $ConfigPath,
    $ConfigContent.TrimStart(),
    [System.Text.UTF8Encoding]::new($false)
)

Write-Host "Rewritten: .streamlit\config.toml" -ForegroundColor Green

Write-Section "Patching dashboard data access and deprecated Streamlit calls"

$PatchFile = Join-Path ([System.IO.Path]::GetTempPath()) "patch_step19_dashboard.py"

$PatchCode = @'
from __future__ import annotations

import re
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
app_path = root / "dashboard" / "app.py"
builder_path = root / "scripts" / "19_build_streamlit_dashboard.ps1"
requirements_path = root / "requirements.txt"

DATABASE_BLOCK = r'''def _database_candidates() -> list[Path]:
    preferred = [
        ROOT / "data/processed/ccp_margin_validation.duckdb",
        ROOT / "data/processed/ccp_margin_model_validation.duckdb",
        ROOT / "data/processed/ccp_margin.duckdb",
        ROOT / "data/processed/validation_results.duckdb",
        ROOT / "data/processed/ccp_validation.duckdb",
        ROOT / "sql/ccp_margin_validation.duckdb",
        ROOT / "data/processed/ccp_margin_validation.db",
        ROOT / "data/processed/ccp_margin.db",
        ROOT / "data/processed/validation_results.db",
        ROOT / "data/processed/ccp_validation.db",
        ROOT / "sql/ccp_margin_validation.db",
    ]
    discovered = (
        list((ROOT / "data").rglob("*.duckdb"))
        + list((ROOT / "sql").rglob("*.duckdb"))
        + list((ROOT / "data").rglob("*.db"))
        + list((ROOT / "data").rglob("*.sqlite"))
        + list((ROOT / "sql").rglob("*.db"))
        + list((ROOT / "sql").rglob("*.sqlite"))
    )
    ordered: list[Path] = []
    for path in preferred + discovered:
        if path.exists() and path not in ordered:
            ordered.append(path)
    return ordered


@st.cache_data(show_spinner=False)
def _read_file(path_text: str, modified_ns: int) -> pd.DataFrame:
    del modified_ns
    path = Path(path_text)
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".json":
        return pd.read_json(path)
    raise ValueError(f"Unsupported dashboard data format: {suffix}")


@st.cache_data(show_spinner=False)
def _read_sqlite(path_text: str, table: str, modified_ns: int) -> pd.DataFrame:
    del modified_ns
    with sqlite3.connect(path_text) as connection:
        return pd.read_sql_query(f'SELECT * FROM "{table}"', connection)


@st.cache_data(show_spinner=False)
def _read_duckdb(path_text: str, table: str, modified_ns: int) -> pd.DataFrame:
    del modified_ns
    with duckdb.connect(path_text, read_only=True) as connection:
        return connection.execute(f'SELECT * FROM "{table}"').df()


def _sqlite_tables(path: Path) -> set[str]:
    try:
        with sqlite3.connect(path) as connection:
            rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        return {str(row[0]) for row in rows}
    except sqlite3.Error:
        return set()


def _duckdb_tables(path: Path) -> set[str]:
    try:
        with duckdb.connect(str(path), read_only=True) as connection:
            rows = connection.execute("SHOW TABLES").fetchall()
        return {str(row[0]) for row in rows}
    except Exception:
        return set()


def _load_database_dataset(name: str) -> tuple[pd.DataFrame, str]:
    for database in _database_candidates():
        suffix = database.suffix.lower()
        if suffix == ".duckdb":
            tables = _duckdb_tables(database)
            reader = _read_duckdb
        else:
            tables = _sqlite_tables(database)
            reader = _read_sqlite

        for table in SQL_TABLES.get(name, []):
            if table not in tables:
                continue

            try:
                label = f"{database.relative_to(ROOT)} :: {table}"
            except ValueError:
                label = f"{database} :: {table}"

            try:
                frame = reader(str(database), table, database.stat().st_mtime_ns)
                return frame, label
            except Exception as exc:
                st.warning(f"Could not read {label}: {exc}")

    return pd.DataFrame(), "Not found"


def load_dataset(name: str) -> tuple[pd.DataFrame, str]:
    database_frame, database_source = _load_database_dataset(name)
    if not database_frame.empty:
        return database_frame, database_source

    for relative in DATASETS[name]:
        path = ROOT / relative
        if path.exists():
            try:
                return _read_file(str(path), path.stat().st_mtime_ns), relative
            except Exception as exc:
                st.warning(f"Could not read {relative}: {exc}")

    return pd.DataFrame(), "Not found"

'''


def patch_dashboard_source(text: str) -> str:
    newline = "\r\n" if "\r\n" in text else "\n"

    if not re.search(r"(?m)^import duckdb\s*$", text):
        text = re.sub(
            r"(?m)^import sqlite3\s*$",
            f"import sqlite3{newline}{newline}import duckdb",
            text,
            count=1,
        )

    if '"reports/findings_tracker.csv",' not in text:
        text = text.replace(
            '        "reports/evidence/findings.csv",' + newline,
            '        "reports/evidence/findings.csv",' + newline
            + '        "reports/findings_tracker.csv",' + newline,
            1,
        )

    backtesting_pattern = re.compile(
        r'("backtesting":\s*\[.*?)(^\s*"data/processed/sensitivity_scenario_results\.parquet",\s*$)(.*?^\s*\],)',
        re.MULTILINE | re.DOTALL,
    )
    text = backtesting_pattern.sub(r"\1\3", text, count=1)

    start = text.find("def _database_candidates()")
    end = text.find("\ndef find_col", start)
    if start == -1 or end == -1:
        raise RuntimeError("Could not locate the dashboard database-loading section.")
    text = text[:start] + DATABASE_BLOCK.replace("\n", newline) + text[end + 1 :]

    text = text.replace("use_container_width=True", 'width="stretch"')
    text = text.replace("use_container_width=False", 'width="content"')

    if 'validation, validation_source = load_dataset("validation_tests")' not in text:
        text = text.replace(
            '    backtest, back_source = load_dataset("backtesting")' + newline,
            '    backtest, back_source = load_dataset("backtesting")' + newline
            + '    validation, validation_source = load_dataset("validation_tests")' + newline
            + '    sensitivity, sensitivity_source = load_dataset("sensitivity")' + newline,
            1,
        )
        text = text.replace(
            '    stress, stress_source = load_dataset("stress")' + newline,
            '    stress, stress_source = load_dataset("stress")' + newline
            + '    procyclicality, procyclicality_source = load_dataset("procyclicality")' + newline,
            1,
        )

    readiness_anchor = (
        '            {"Area": "Backtesting", "Status": "Ready" if not backtest.empty else "Missing", '
        '"Source": back_source, "Rows": len(backtest)},' + newline
    )
    if '{"Area": "Validation tests"' not in text and readiness_anchor in text:
        text = text.replace(
            readiness_anchor,
            readiness_anchor
            + '            {"Area": "Validation tests", "Status": "Ready" if not validation.empty else "Missing", '
            '"Source": validation_source, "Rows": len(validation)},' + newline
            + '            {"Area": "Sensitivity analysis", "Status": "Ready" if not sensitivity.empty else "Missing", '
            '"Source": sensitivity_source, "Rows": len(sensitivity)},' + newline,
            1,
        )

    stress_anchor = (
        '            {"Area": "Stress testing", "Status": "Ready" if not stress.empty else "Missing", '
        '"Source": stress_source, "Rows": len(stress)},' + newline
    )
    if '{"Area": "Procyclicality"' not in text and stress_anchor in text:
        text = text.replace(
            stress_anchor,
            stress_anchor
            + '            {"Area": "Procyclicality", "Status": "Ready" if not procyclicality.empty else "Missing", '
            '"Source": procyclicality_source, "Rows": len(procyclicality)},' + newline,
            1,
        )

    text = text.replace(
        "This application reads prepared Parquet, CSV, or SQLite outputs only.",
        "This application reads prepared DuckDB, SQLite, Parquet, or CSV outputs only.",
    )

    return text


def patch_file(path: Path) -> None:
    if not path.exists():
        return
    original = path.read_text(encoding="utf-8-sig")
    patched = patch_dashboard_source(original)

    if path.name == "19_build_streamlit_dashboard.ps1":
        patched = patched.replace(
            "Set-Content -Path $ConfigPath -Value $ConfigContent -Encoding UTF8",
            "[System.IO.File]::WriteAllText(`n"
            "    $ConfigPath,`n"
            "    $ConfigContent.TrimStart(),`n"
            "    [System.Text.UTF8Encoding]::new($false)`n"
            ")",
        )

        if '"reports\\findings_tracker.csv"' not in patched:
            builder_newline = "\r\n" if "\r\n" in patched else "\n"
            patched = patched.replace(
                '        "reports\\evidence\\findings.csv",' + builder_newline,
                '        "reports\\evidence\\findings.csv",' + builder_newline
                + '        "reports\\findings_tracker.csv",' + builder_newline,
                1,
            )

        old_append = '        Add-Content -Path $script:RequirementsPath -Value $Requirement -Encoding UTF8'
        if old_append in patched:
            builder_newline = "\r\n" if "\r\n" in patched else "\n"
            replacement = (
                '        $CurrentRequirementText = [System.IO.File]::ReadAllText($script:RequirementsPath)' + builder_newline
                + '        $Prefix = if ($CurrentRequirementText.Length -gt 0 -and -not $CurrentRequirementText.EndsWith("`n")) { [Environment]::NewLine } else { "" }' + builder_newline
                + '        [System.IO.File]::AppendAllText(' + builder_newline
                + '            $script:RequirementsPath,' + builder_newline
                + '            $Prefix + $Requirement + [Environment]::NewLine,' + builder_newline
                + '            [System.Text.UTF8Encoding]::new($false)' + builder_newline
                + '        )'
            )
            patched = patched.replace(old_append, replacement)

        if 'Ensure-Requirement -PackageName "duckdb"' not in patched:
            anchor = 'Ensure-Requirement -PackageName "pyarrow" -Requirement "pyarrow>=15"'
            builder_newline = "\r\n" if "\r\n" in patched else "\n"
            patched = patched.replace(
                anchor,
                anchor + builder_newline
                + 'Ensure-Requirement -PackageName "duckdb" -Requirement "duckdb>=1.0"',
                1,
            )

    path.write_text(patched, encoding="utf-8", newline="")


patch_file(app_path)
patch_file(builder_path)

raw_requirements = requirements_path.read_text(encoding="utf-8-sig") if requirements_path.exists() else ""
raw_requirements = raw_requirements.replace("python-dotenvstreamlit", "python-dotenv\nstreamlit")
lines = [line.strip() for line in raw_requirements.splitlines() if line.strip()]

def has_package(package: str) -> bool:
    pattern = re.compile(rf"^{re.escape(package)}(?:\s|\[|=|<|>|!|~|$)", re.IGNORECASE)
    return any(pattern.search(line) for line in lines)

if not has_package("streamlit"):
    lines.append("streamlit>=1.36")
if not has_package("duckdb"):
    lines.append("duckdb>=1.0")
if not has_package("pyarrow"):
    lines.append("pyarrow>=15")

seen: set[str] = set()
cleaned: list[str] = []
for line in lines:
    key = line.casefold()
    if key not in seen:
        seen.add(key)
        cleaned.append(line)

requirements_path.write_text("\n".join(cleaned) + "\n", encoding="utf-8")
print("Dashboard and Step 19 builder patched successfully.")
'@

[System.IO.File]::WriteAllText(
    $PatchFile,
    $PatchCode,
    [System.Text.UTF8Encoding]::new($false)
)

try {
    & $Python $PatchFile $ProjectRoot
    if ($LASTEXITCODE -ne 0) {
        throw "The dashboard patch operation failed."
    }
}
finally {
    Remove-Item $PatchFile -Force -ErrorAction SilentlyContinue
}

Write-Host "Patched: dashboard\app.py" -ForegroundColor Green
if (Test-Path $BuilderPath) {
    Write-Host "Patched: scripts\19_build_streamlit_dashboard.ps1" -ForegroundColor Green
}
Write-Host "Normalized: requirements.txt" -ForegroundColor Green

Write-Section "Installing and validating dashboard dependencies"

if (-not $SkipInstall) {
    & $Python -m pip install -r $RequirementsPath
    if ($LASTEXITCODE -ne 0) {
        throw "Dependency installation failed."
    }
}
else {
    Write-Host "Dependency installation skipped."
}

& $Python -c "import duckdb, streamlit, pandas, numpy, scipy, pyarrow; print('DuckDB:', duckdb.__version__); print('Streamlit:', streamlit.__version__)"
if ($LASTEXITCODE -ne 0) {
    throw "Required dashboard packages could not be imported."
}

& $Python -c "import tomllib; from pathlib import Path; tomllib.loads(Path('.streamlit/config.toml').read_text(encoding='utf-8')); print('config.toml validation passed.')"
if ($LASTEXITCODE -ne 0) {
    throw ".streamlit\config.toml is still invalid."
}

& $Python -m py_compile $AppPath
if ($LASTEXITCODE -ne 0) {
    throw "dashboard\app.py failed Python syntax validation."
}

Write-Section "Prepared database inventory"

& $Python -c "from pathlib import Path; files=list(Path('data').rglob('*.duckdb'))+list(Path('sql').rglob('*.duckdb'))+list(Path('data').rglob('*.db'))+list(Path('sql').rglob('*.db')); print('Prepared databases:'); [print('  ', p) for p in files] if files else print('  None found; file fallbacks will be used.')"
if ($LASTEXITCODE -ne 0) {
    throw "Database inventory failed."
}

Write-Section "Step 19 repair completed"
Write-Host "The dashboard now:" -ForegroundColor Green
Write-Host "  - reads DuckDB tables produced by Step 18 before file fallbacks"
Write-Host "  - recognizes reports\findings_tracker.csv"
Write-Host "  - uses a valid BOM-free Streamlit TOML configuration"
Write-Host "  - replaces deprecated use_container_width arguments"
Write-Host "  - reports readiness for all principal validation areas"

if ($CommitAndPush) {
    Write-Section "Committing and pushing Step 19 corrections"

    git add `
        dashboard/app.py `
        .streamlit/config.toml `
        scripts/19_build_streamlit_dashboard.ps1 `
        scripts/19_repair_streamlit_dashboard.ps1 `
        requirements.txt

    $Pending = git status --porcelain
    if ($Pending) {
        git commit -m "Complete Streamlit dashboard and DuckDB integration"
        if ($LASTEXITCODE -ne 0) {
            throw "Git commit failed."
        }

        git push
        if ($LASTEXITCODE -ne 0) {
            throw "Git push failed."
        }
    }
    else {
        Write-Host "No uncommitted Step 19 changes were found."
    }
}

if (-not $NoLaunch) {
    Write-Section "Launching the corrected Streamlit dashboard"
    Write-Host "Local URL: http://localhost:8501"
    Write-Host "Stop the server with Ctrl+C."
    & $Python -m streamlit run dashboard\app.py
}
else {
    Write-Host ""
    Write-Host "Launch skipped because -NoLaunch was supplied."
    Write-Host "Manual command:"
    Write-Host "  .\.venv\Scripts\python.exe -m streamlit run dashboard\app.py"
}

$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Users\nejat\OneDrive\Desktop\UN\Skills\GitHub 2026\ccp-margin-model-validation"
Set-Location $ProjectRoot

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "Creating Python 3.11 virtual environment..."
    py -3.11 -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        py -3 -m venv .venv
    }
}

$Python = ".\.venv\Scripts\python.exe"

Write-Host "Installing required packages..."
& $Python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }

& $Python -m pip install "duckdb>=1.4,<2" pandas numpy pyarrow pytest
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

Write-Host "Generating Step 17 procyclicality outputs..."
& $Python ".\scripts\17_generate_procyclicality_results.py"
if ($LASTEXITCODE -ne 0) { throw "Step 17 generation failed." }

Write-Host "Building the deterministic Step 18 DuckDB database..."
& $Python ".\scripts\18_build_duckdb.py"
if ($LASTEXITCODE -ne 0) { throw "Step 18 database build failed." }

Write-Host "Running enhanced Step 18 tests..."
& $Python -m pytest ".\tests\test_sql_pipeline.py" -q
if ($LASTEXITCODE -ne 0) { throw "Step 18 tests failed." }

Write-Host ""
Write-Host "Step 17 and Step 18 completed successfully."
Write-Host "Database: data\database\ccp_margin_validation.duckdb"
Write-Host "Manifest: reports\sql\load_manifest.csv"

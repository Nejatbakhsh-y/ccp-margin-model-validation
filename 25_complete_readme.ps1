#requires -Version 5.1
<#
.SYNOPSIS
Completes Step 23 by generating a comprehensive README.md, capturing the
Streamlit dashboard, validating the required sections, and committing/pushing
the result to GitHub.

.RUN
Open the project folder in VS Code, open a PowerShell terminal, and run:

    Set-ExecutionPolicy -Scope Process Bypass
    .\25_complete_readme.ps1

Optional:
    .\25_complete_readme.ps1 -SkipDashboardCapture
    .\25_complete_readme.ps1 -SkipGitPush
#>

[CmdletBinding()]
param(
    [string]$ProjectRoot = "C:\Users\nejat\OneDrive\Desktop\UN\Skills\GitHub 2026\ccp-margin-model-validation",
    [switch]$SkipDashboardCapture,
    [switch]$SkipGitPush
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Write-Step {
    param([Parameter(Mandatory)][string]$Message)
    Write-Host ""
    Write-Host ("=" * 78) -ForegroundColor Cyan
    Write-Host $Message -ForegroundColor Cyan
    Write-Host ("=" * 78) -ForegroundColor Cyan
}

function Assert-Path {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Description
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "$Description was not found: $Path"
    }
}

function Assert-NativeSuccess {
    param([Parameter(Mandatory)][string]$Operation)
    if ($LASTEXITCODE -ne 0) {
        throw "$Operation failed with exit code $LASTEXITCODE."
    }
}

function Convert-ToGitHubUrl {
    param([string]$RemoteUrl)

    if ([string]::IsNullOrWhiteSpace($RemoteUrl)) {
        return "https://github.com/OWNER/ccp-margin-model-validation"
    }

    $url = $RemoteUrl.Trim()

    if ($url -match '^git@github\.com:(.+?)(?:\.git)?$') {
        return "https://github.com/$($Matches[1])"
    }

    if ($url -match '^https://github\.com/(.+?)(?:\.git)?$') {
        return "https://github.com/$($Matches[1])"
    }

    return $url.TrimEnd("/")
}

function Get-EdgePath {
    $candidates = @(
        "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
        "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
        "$env:LOCALAPPDATA\Microsoft\Edge\Application\msedge.exe"
    )

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
    }

    $command = Get-Command "msedge.exe" -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    return $null
}

function Wait-ForUrl {
    param(
        [Parameter(Mandatory)][string]$Url,
        [int]$MaximumAttempts = 45,
        [int]$DelaySeconds = 2
    )

    for ($attempt = 1; $attempt -le $MaximumAttempts; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return $true
            }
        }
        catch {
            Start-Sleep -Seconds $DelaySeconds
        }
    }

    return $false
}

function Capture-DashboardScreenshot {
    param(
        [Parameter(Mandatory)][string]$PythonPath,
        [Parameter(Mandatory)][string]$DashboardPath,
        [Parameter(Mandatory)][string]$ScreenshotPath,
        [Parameter(Mandatory)][string]$LogDirectory
    )

    $existingCandidates = @(
        $ScreenshotPath,
        (Join-Path $ProjectRoot "reports\figures\dashboard-overview.png"),
        (Join-Path $ProjectRoot "reports\figures\dashboard_overview.png"),
        (Join-Path $ProjectRoot "reports\figures\dashboard.png"),
        (Join-Path $ProjectRoot "dashboard-overview.png"),
        (Join-Path $ProjectRoot "dashboard.png")
    )

    $targetFullPath = [System.IO.Path]::GetFullPath($ScreenshotPath)

    foreach ($candidate in $existingCandidates) {
        if (Test-Path -LiteralPath $candidate) {
            $candidateFullPath = [System.IO.Path]::GetFullPath($candidate)
            if ($candidateFullPath -ne $targetFullPath) {
                Copy-Item -LiteralPath $candidate -Destination $ScreenshotPath -Force
            }
            if ((Get-Item -LiteralPath $ScreenshotPath).Length -gt 5000) {
                Write-Host "Using dashboard image: $candidate" -ForegroundColor Green
                return
            }
        }
    }

    $edgePath = Get-EdgePath
    if (-not $edgePath) {
        throw "Microsoft Edge was not found. Install Edge or place an existing dashboard PNG at docs\assets\dashboard-overview.png."
    }

    Assert-Path -Path $DashboardPath -Description "Streamlit dashboard"
    New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null

    $stdoutLog = Join-Path $LogDirectory "step23_streamlit_stdout.log"
    $stderrLog = Join-Path $LogDirectory "step23_streamlit_stderr.log"
    Remove-Item -LiteralPath $stdoutLog, $stderrLog -Force -ErrorAction SilentlyContinue

    $streamlitArguments = @(
        "-m", "streamlit", "run", $DashboardPath,
        "--server.headless=true",
        "--server.address=127.0.0.1",
        "--server.port=8523",
        "--browser.gatherUsageStats=false"
    )

    $streamlitProcess = $null
    try {
        Write-Host "Starting Streamlit for screenshot capture..." -ForegroundColor Yellow
        $streamlitProcess = Start-Process `
            -FilePath $PythonPath `
            -ArgumentList $streamlitArguments `
            -WorkingDirectory $ProjectRoot `
            -RedirectStandardOutput $stdoutLog `
            -RedirectStandardError $stderrLog `
            -PassThru `
            -WindowStyle Hidden

        $dashboardUrl = "http://127.0.0.1:8523"
        if (-not (Wait-ForUrl -Url $dashboardUrl)) {
            $details = ""
            if (Test-Path -LiteralPath $stderrLog) {
                $details = (Get-Content -LiteralPath $stderrLog -Raw -ErrorAction SilentlyContinue)
            }
            throw "The Streamlit dashboard did not become available. Review $stderrLog. $details"
        }

        Start-Sleep -Seconds 8

        $edgeArguments = @(
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--window-size=1600,1100",
            "--virtual-time-budget=12000",
            "--screenshot=$ScreenshotPath",
            $dashboardUrl
        )

        & $edgePath @edgeArguments | Out-Null
        Assert-NativeSuccess -Operation "Microsoft Edge dashboard capture"
        Start-Sleep -Seconds 2

        if (-not (Test-Path -LiteralPath $ScreenshotPath)) {
            throw "Edge did not create the dashboard screenshot."
        }

        $imageSize = (Get-Item -LiteralPath $ScreenshotPath).Length
        if ($imageSize -lt 5000) {
            throw "The dashboard screenshot appears invalid because it is only $imageSize bytes."
        }

        Write-Host "Dashboard screenshot created: $ScreenshotPath" -ForegroundColor Green
    }
    finally {
        if ($streamlitProcess -and -not $streamlitProcess.HasExited) {
            Stop-Process -Id $streamlitProcess.Id -Force -ErrorAction SilentlyContinue
        }
    }
}

function Get-PresenceLabel {
    param([Parameter(Mandatory)][string]$RelativePath)

    $fullPath = Join-Path $ProjectRoot $RelativePath
    if (Test-Path -LiteralPath $fullPath) {
        return "Available"
    }

    return "Not generated"
}

function Get-ScriptCommandsMarkdown {
    $scriptsDirectory = Join-Path $ProjectRoot "scripts"
    if (-not (Test-Path -LiteralPath $scriptsDirectory)) {
        return @"
No executable scripts were detected in the `scripts/` directory.
"@
    }

    $scriptFiles = Get-ChildItem -LiteralPath $scriptsDirectory -Filter "*.py" -File |
        Sort-Object Name

    if (-not $scriptFiles) {
        return @"
No executable Python scripts were detected in the `scripts/` directory.
"@
    }

    $lines = foreach ($file in $scriptFiles) {
        "python .\scripts\$($file.Name)"
    }

    return "``````powershell`r`n" + ($lines -join "`r`n") + "`r`n``````"
}

function Get-ArtifactStatusRows {
    $artifacts = [ordered]@{
        "Clean market dataset"          = "data\processed\market_prices_clean.parquet"
        "Risk-factor returns"           = "data\processed\log_returns_wide.parquet"
        "Clearing-member positions"     = "data\processed\clearing_member_positions.parquet"
        "Portfolio exposures"           = "data\processed\portfolio_exposures.parquet"
        "Daily member margin"            = "data\processed\daily_member_margin.parquet"
        "Sensitivity results"            = "data\processed\sensitivity_scenario_results.parquet"
        "Stress-test results"            = "data\processed\stress_test_results.parquet"
        "Procyclicality results"          = "data\processed\procyclicality_results.parquet"
        "Data-quality summary"            = "reports\tables\data_quality_summary.csv"
        "Validation findings"             = "reports\evidence\validation_findings.csv"
        "Independent validation report"   = "reports\independent_validation_report.md"
        "Dashboard screenshot"            = "docs\assets\dashboard-overview.png"
    }

    $rows = foreach ($entry in $artifacts.GetEnumerator()) {
        $status = Get-PresenceLabel -RelativePath $entry.Value
        $markdownPath = $entry.Value.Replace("\", "/")
        "| $($entry.Key) | ``$markdownPath`` | $status |"
    }

    return $rows -join "`r`n"
}

function Get-ModelStatus {
    param([Parameter(Mandatory)][string]$RelativePath)
    if (Test-Path -LiteralPath (Join-Path $ProjectRoot $RelativePath)) {
        return "Implemented"
    }
    return "Planned or unavailable"
}

Write-Step "STEP 23 - INITIAL VALIDATION"

Assert-Path -Path $ProjectRoot -Description "Project root"
Set-Location -LiteralPath $ProjectRoot

Assert-Path -Path (Join-Path $ProjectRoot ".git") -Description "Git repository"
Assert-Path -Path (Join-Path $ProjectRoot ".venv\Scripts\python.exe") -Description "Project virtual-environment Python"
Assert-Path -Path (Join-Path $ProjectRoot "dashboard\app.py") -Description "Streamlit dashboard"

$pythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$readmePath = Join-Path $ProjectRoot "README.md"
$assetsDirectory = Join-Path $ProjectRoot "docs\assets"
$logsDirectory = Join-Path $ProjectRoot "reports\evidence"
$screenshotPath = Join-Path $assetsDirectory "dashboard-overview.png"

New-Item -ItemType Directory -Path $assetsDirectory -Force | Out-Null
New-Item -ItemType Directory -Path $logsDirectory -Force | Out-Null

Write-Step "CAPTURE DASHBOARD SCREENSHOT"

if ($SkipDashboardCapture) {
    Assert-Path -Path $screenshotPath -Description "Existing dashboard screenshot required when -SkipDashboardCapture is used"
    Write-Host "Dashboard capture skipped; existing screenshot retained." -ForegroundColor Yellow
}
else {
    Capture-DashboardScreenshot `
        -PythonPath $pythonPath `
        -DashboardPath "dashboard\app.py" `
        -ScreenshotPath $screenshotPath `
        -LogDirectory $logsDirectory
}

Write-Step "BUILD README CONTENT"

$remoteUrlRaw = (& git config --get remote.origin.url 2>$null)
$repositoryUrl = Convert-ToGitHubUrl -RemoteUrl $remoteUrlRaw
$generatedDate = Get-Date -Format "MMMM d, yyyy"
$year = Get-Date -Format "yyyy"
$scriptCommands = Get-ScriptCommandsMarkdown
$artifactRows = Get-ArtifactStatusRows

$primaryStatus = Get-ModelStatus "src\ccp_margin\models\primary\historical_var.py"
$challengerStatus = Get-ModelStatus "src\ccp_margin\models\challenger\parametric_var.py"
$liquidityStatus = Get-ModelStatus "src\ccp_margin\margin\liquidity_addon.py"
$concentrationStatus = Get-ModelStatus "src\ccp_margin\margin\concentration_addon.py"
$gapRiskStatus = Get-ModelStatus "src\ccp_margin\margin\gap_risk_addon.py"
$stressBufferStatus = Get-ModelStatus "src\ccp_margin\margin\stress_buffer.py"

$readmeTemplate = @'
# CCP Margin Model Independent Validation Framework

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-pytest-informational.svg)](#test-commands)
[![Dashboard](https://img.shields.io/badge/dashboard-Streamlit-red.svg)](#dashboard-screenshot)
[![Purpose](https://img.shields.io/badge/purpose-educational%20validation-lightgrey.svg)](#project-disclaimer)

## Executive Description

This repository implements an end-to-end, reproducible framework for independently developing, challenging, and validating a central counterparty clearing margin model. The project covers synthetic clearing-member portfolios, public market data, primary and challenger margin methodologies, margin add-ons, backtesting, benchmark comparison, sensitivity analysis, stress testing, procyclicality assessment, implementation verification, validation findings, evidence generation, and an executive Streamlit dashboard.

The framework is designed as a model-risk-management portfolio project. It demonstrates how a validator can separate model development from independent review, translate conceptual requirements into testable controls, preserve reproducible evidence, and communicate conclusions, limitations, and remediation priorities.

## Business and Regulatory Motivation

Central counterparties manage counterparty exposure by collecting margin from clearing members. A margin framework must remain sufficiently risk-sensitive to cover potential liquidation losses while avoiding unexplained instability, excessive procyclicality, weak implementation controls, or dependence on a single methodology.

This project applies independent-validation principles commonly used in financial model-risk management:

- clear model purpose, scope, assumptions, and limitations;
- documented primary and challenger methodologies;
- data-quality and implementation controls;
- outcome analysis through backtesting and margin-shortfall testing;
- parameter sensitivity and benchmark comparison;
- historical, hypothetical, and reverse stress testing;
- procyclicality measurement and stability analysis;
- traceable findings, severity classification, and remediation evidence.

The implementation is not a regulatory approval, legal opinion, or representation of any clearing agency's proprietary methodology.

## Project Disclaimer

This repository is an independent educational and portfolio implementation
using public and synthetic data. It is not an implementation of any
proprietary DTCC, NSCC, FICC, OCC, CME, ICE, or other clearing-agency model.
It is not intended for production margining, regulatory compliance, trading,
investment, or risk-management decisions.

## Architecture Diagram

```mermaid
flowchart LR
    A[Public Market Data] --> D[Data Download and Validation]
    B[Public Macroeconomic Data] --> D
    C[Synthetic Member Portfolios] --> E[Portfolio and Exposure Engine]
    D --> F[Clean Prices and Returns]
    E --> G[Primary Historical-Simulation Model]
    F --> G
    E --> H[Challenger Parametric EWMA Model]
    F --> H
    G --> I[Margin Components]
    H --> J[Benchmark Comparison]
    I --> K[Total Member Margin]
    K --> L[Backtesting and Shortfall Analysis]
    K --> M[Sensitivity Analysis]
    K --> N[Stress Testing]
    K --> O[Procyclicality Monitoring]
    J --> P[Independent Validation Evidence]
    L --> P
    M --> P
    N --> P
    O --> P
    P --> Q[Validation Report and Findings]
    P --> R[Streamlit Dashboard]
```

## Model Inventory

| Component | Role | Core Methodology | Implementation Status |
|---|---|---|---|
| Primary margin model | Primary risk measure | 99% historical-simulation Value at Risk with configurable lookback and margin period of risk | __PRIMARY_STATUS__ |
| Challenger margin model | Independent benchmark | Parametric variance-covariance VaR with EWMA covariance and correlation controls | __CHALLENGER_STATUS__ |
| Multi-day risk | Liquidation-horizon scaling | Direct multi-day returns and square-root-of-time comparison | Implemented within primary and challenger workflows |
| Liquidity add-on | Market-liquidity risk | Position size relative to trading-volume or liquidity thresholds | __LIQUIDITY_STATUS__ |
| Concentration add-on | Name and portfolio concentration | Exposure concentration relative to configured thresholds | __CONCENTRATION_STATUS__ |
| Gap-risk add-on | Discontinuous price-move risk | Scenario-based or position-specific gap charge | __GAP_RISK_STATUS__ |
| Stress buffer | Tail and regime risk | Configurable stressed-loss buffer | __STRESS_BUFFER_STATUS__ |
| Total margin | Aggregate requirement | Base margin plus applicable add-ons and buffers | Implemented |
| Validation framework | Independent challenge | Coverage tests, independence tests, benchmark comparison, sensitivity, stress, shortfall, implementation verification, and procyclicality | Implemented |

## Margin Formula

For member \(m\) on date \(t\), the conceptual total initial-margin requirement is:

\[
IM_{m,t}
=
\max\left(
BM_{m,t},
SM_{m,t}
\right)
+
LA_{m,t}
+
CA_{m,t}
+
GA_{m,t}
+
SB_{m,t},
\]

where:

- \(BM\) is base margin from the primary VaR model;
- \(SM\) is any applicable stressed or benchmark floor;
- \(LA\) is the liquidity add-on;
- \(CA\) is the concentration add-on;
- \(GA\) is the gap-risk add-on;
- \(SB\) is the stress buffer.

The exact aggregation logic is configuration-driven and should be interpreted together with the model documentation, assumptions, and limitations.

## Validation Framework

The independent-validation framework includes:

| Validation Area | Principal Tests and Evidence |
|---|---|
| Conceptual soundness | Methodology review, assumptions, risk coverage, model inventory, and benchmark rationale |
| Data quality | Completeness, duplicates, missing observations, date continuity, schema checks, and exception evidence |
| Outcome analysis | Backtesting exceptions, margin shortfalls, realized-loss coverage, and member-level diagnostics |
| Statistical backtesting | Kupiec unconditional coverage; Christoffersen independence and conditional coverage |
| Traffic-light assessment | Basel-style exception classification |
| Benchmarking | Primary historical-simulation model versus parametric EWMA challenger |
| Sensitivity and stability | Confidence level, lookback, MPOR, EWMA decay, add-on thresholds, stress buffers, and correlation shocks |
| Stress testing | Historical, hypothetical, concentration, liquidity, wrong-way, and reverse-stress scenarios |
| Procyclicality | Daily and weekly changes, jump frequencies, volatility relationships, stressed-to-calm ratios, and buffer behavior |
| Implementation verification | Recalculation, deterministic execution, configuration checks, unit tests, and evidence reconciliation |
| Findings management | Severity, impact, recommendation, owner, target date, status, and compensating controls |

## Data Sources

The project uses only public or synthetic inputs:

- public equity and exchange-traded-fund price histories;
- public U.S. Treasury, interest-rate, volatility, and macroeconomic series obtained from FRED where configured;
- deterministic synthetic clearing-member portfolios and positions;
- locally generated model, validation, sensitivity, stress, and monitoring outputs.

Raw data, secrets, credentials, and API keys must not be committed. Local secrets should be stored in `.env` or another excluded configuration mechanism.

## Repository Structure

```text
ccp-margin-model-validation/
├── .github/workflows/           # Continuous-integration workflows
├── .vscode/                     # VS Code project configuration
├── configs/                     # Project, model, validation, stress, and monitoring settings
├── dashboard/                   # Streamlit executive dashboard
├── data/
│   ├── raw/                     # Locally downloaded source data
│   ├── interim/                 # Intermediate transformations
│   ├── processed/               # Reproducible analytical datasets
│   ├── synthetic/               # Synthetic portfolio inputs
│   └── manifests/               # Data lineage and ingestion manifests
├── docs/                        # Scope, charter, architecture, and supporting documentation
├── notebooks/exploratory/       # Non-production exploratory analysis
├── reports/
│   ├── figures/                 # Validation figures
│   ├── tables/                  # Validation tables
│   └── evidence/                # Exceptions, findings, logs, and reproducibility evidence
├── scripts/                     # Ordered pipeline and validation entry points
├── sql/                         # Analytical database and SQL pipeline assets
├── src/ccp_margin/              # Reusable Python package
├── tests/                       # Unit and integration tests
├── requirements.txt             # Runtime dependencies
├── requirements-dev.txt         # Development and testing dependencies
└── README.md                    # Project overview and reproduction guide
```

## Installation Instructions

### Prerequisites

- Windows 10 or Windows 11;
- Visual Studio Code;
- Git;
- Python 3.11;
- PowerShell;
- access to any externally configured public-data APIs.

### Create and Activate the Environment

```powershell
cd "C:\Users\nejat\OneDrive\Desktop\UN\Skills\GitHub 2026\ccp-margin-model-validation"

python -m venv .venv
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

### Configure Local Secrets

Create a local `.env` file only when an API key is required. Do not commit `.env`.

```text
FRED_API_KEY=your_local_key
```

## Reproduction Commands

Activate the project environment before executing the pipeline:

```powershell
cd "C:\Users\nejat\OneDrive\Desktop\UN\Skills\GitHub 2026\ccp-margin-model-validation"
.\.venv\Scripts\Activate.ps1
```

The currently detected Python pipeline entry points are:

__SCRIPT_COMMANDS__

Run the scripts in their numeric order unless a script's documentation explicitly states otherwise. The dashboard reads prepared result files and should not rebuild the full data pipeline at application startup.

### Launch the Dashboard

```powershell
streamlit run .\dashboard\app.py
```

## Test Commands

Run the complete test suite:

```powershell
python -m pytest -q
```

Run unit tests only:

```powershell
python -m pytest .\tests\unit -q
```

Run tests with coverage:

```powershell
python -m pytest --cov=ccp_margin --cov-report=term-missing --cov-report=html
```

Run static-quality checks when configured:

```powershell
python -m ruff check .
python -m ruff format --check .
```

## Results Summary

The framework produces auditable datasets, statistical-test outputs, figures, tables, evidence files, findings, and dashboard views. Availability depends on whether the associated pipeline steps have been executed in the local clone.

| Output | Expected Path | Current Local Status |
|---|---|---|
__ARTIFACT_ROWS__

Primary validation interpretation should be based on the generated independent-validation report and supporting evidence rather than on any single metric. A statistically acceptable exception rate does not, by itself, establish conceptual soundness, adequate stress coverage, appropriate calibration, or implementation correctness.

## Dashboard Screenshot

The Streamlit dashboard presents executive results for daily member margin, exceptions, traffic-light status, Kupiec and Christoffersen tests, shortfalls, sensitivity analysis, stress testing, procyclicality, findings, and remediation.

![CCP margin model validation dashboard](docs/assets/dashboard-overview.png)

## Findings Summary

The validation framework is structured to distinguish implementation defects, methodological limitations, calibration weaknesses, data-quality exceptions, and governance observations. Typical areas requiring explicit review include:

1. empirical calibration of liquidity, concentration, gap-risk, and stress-buffer parameters;
2. sensitivity of coverage and margin stability to confidence level, lookback, MPOR, and EWMA decay;
3. treatment of concentrated, leveraged, illiquid, and long-short portfolios;
4. independence and clustering of backtesting exceptions;
5. stressed-period coverage and reverse-stress breakpoints;
6. procyclical margin increases and buffer depletion or replenishment behavior;
7. reconciliation among prepared datasets, validation tables, dashboard views, and the final report.

Final conclusions, finding severities, compensating controls, and remediation statuses should be taken from `reports/independent_validation_report.md` and the corresponding evidence files.

## Limitations

- The portfolios and clearing-member structures are synthetic.
- Public market data cannot reproduce proprietary clearing-agency positions, liquidity measures, valuation controls, or default-management processes.
- Add-on parameters require empirical calibration and governance approval before any operational interpretation.
- Historical simulation is constrained by the observed sample and may not represent unobserved structural breaks.
- Parametric VaR depends on distributional, covariance, correlation, and scaling assumptions.
- Backtesting power is limited by the number of observations and exceptions.
- Stress scenarios are illustrative and cannot establish complete tail-risk coverage.
- Public price and macroeconomic sources may contain revisions, gaps, survivorship effects, or vendor-specific conventions.
- The framework does not model every legal, operational, settlement, wrong-way-risk, collateral, or default-waterfall feature of a production CCP.
- Local results may differ when source data, API responses, configurations, package versions, or execution dates change.

## Future Extensions

Potential extensions include:

- empirically calibrated add-ons using public liquidity and transaction-cost proxies;
- filtered historical simulation and volatility-rescaled returns;
- expected shortfall and additional challenger models;
- nonlinear instrument valuation and options portfolios;
- collateral haircuts and wrong-way-risk overlays;
- multi-currency and cross-asset portfolios;
- default-fund and waterfall analytics;
- automated model-change detection and monitoring thresholds;
- containerized execution and scheduled continuous validation;
- richer data-lineage, approval, issue-management, and audit-trail controls.

## License

No open-source license is granted unless a `LICENSE` file is present in the repository. In the absence of such a file, the source code and documentation remain subject to the repository owner's rights. The educational disclaimer above applies regardless of licensing status.

## Citation Information

When referencing this project, use the repository URL:

`__REPOSITORY_URL__`

Suggested citation:

> Nejatbakhsh, Yousef. *CCP Margin Model Independent Validation Framework*. GitHub repository, __YEAR__. __REPOSITORY_URL__.

Suggested BibTeX:

```bibtex
@software{nejatbakhsh_ccp_margin_validation___YEAR__,
  author       = {Yousef Nejatbakhsh},
  title        = {CCP Margin Model Independent Validation Framework},
  year         = {__YEAR__},
  url          = {__REPOSITORY_URL__},
  note         = {Independent educational and portfolio implementation using public and synthetic data}
}
```

---

README generated and validated on __GENERATED_DATE__.
'@

$readmeContent = $readmeTemplate
$readmeContent = $readmeContent.Replace("__PRIMARY_STATUS__", $primaryStatus)
$readmeContent = $readmeContent.Replace("__CHALLENGER_STATUS__", $challengerStatus)
$readmeContent = $readmeContent.Replace("__LIQUIDITY_STATUS__", $liquidityStatus)
$readmeContent = $readmeContent.Replace("__CONCENTRATION_STATUS__", $concentrationStatus)
$readmeContent = $readmeContent.Replace("__GAP_RISK_STATUS__", $gapRiskStatus)
$readmeContent = $readmeContent.Replace("__STRESS_BUFFER_STATUS__", $stressBufferStatus)
$readmeContent = $readmeContent.Replace("__SCRIPT_COMMANDS__", $scriptCommands)
$readmeContent = $readmeContent.Replace("__ARTIFACT_ROWS__", $artifactRows)
$readmeContent = $readmeContent.Replace("__REPOSITORY_URL__", $repositoryUrl)
$readmeContent = $readmeContent.Replace("__YEAR__", $year)
$readmeContent = $readmeContent.Replace("__GENERATED_DATE__", $generatedDate)

[System.IO.File]::WriteAllText(
    $readmePath,
    $readmeContent,
    [System.Text.UTF8Encoding]::new($false)
)

Write-Host "README created: $readmePath" -ForegroundColor Green

Write-Step "VALIDATE README COMPLETENESS"

$requiredSections = @(
    "# CCP Margin Model Independent Validation Framework",
    "## Executive Description",
    "## Business and Regulatory Motivation",
    "## Project Disclaimer",
    "## Architecture Diagram",
    "## Model Inventory",
    "## Margin Formula",
    "## Validation Framework",
    "## Data Sources",
    "## Repository Structure",
    "## Installation Instructions",
    "## Reproduction Commands",
    "## Test Commands",
    "## Results Summary",
    "## Dashboard Screenshot",
    "## Findings Summary",
    "## Limitations",
    "## Future Extensions",
    "## License",
    "## Citation Information"
)

$requiredDisclaimer = @'
This repository is an independent educational and portfolio implementation
using public and synthetic data. It is not an implementation of any
proprietary DTCC, NSCC, FICC, OCC, CME, ICE, or other clearing-agency model.
It is not intended for production margining, regulatory compliance, trading,
investment, or risk-management decisions.
'@

$finalReadme = Get-Content -LiteralPath $readmePath -Raw

$missingSections = foreach ($section in $requiredSections) {
    if (-not $finalReadme.Contains($section)) {
        $section
    }
}

if ($missingSections) {
    throw "README validation failed. Missing sections: $($missingSections -join ', ')"
}

if (-not $finalReadme.Contains($requiredDisclaimer.Trim())) {
    throw "README validation failed because the required disclaimer is not present verbatim."
}

Assert-Path -Path $screenshotPath -Description "Dashboard screenshot"
if ((Get-Item -LiteralPath $screenshotPath).Length -lt 5000) {
    throw "README validation failed because the dashboard screenshot is invalid or too small."
}

Write-Host "All required README sections are present." -ForegroundColor Green
Write-Host "The required disclaimer is present verbatim." -ForegroundColor Green
Write-Host "The dashboard screenshot exists and passed the size check." -ForegroundColor Green

Write-Step "GIT COMMIT AND PUSH"

& git add -- "README.md" "docs/assets/dashboard-overview.png"
Assert-NativeSuccess -Operation "Git staging"

$statusOutput = (& git status --porcelain)
if ($statusOutput) {
    & git commit -m "docs: complete project README"
    Assert-NativeSuccess -Operation "Git commit"
}
else {
    Write-Host "No README or screenshot changes require a new commit." -ForegroundColor Yellow
}

if ($SkipGitPush) {
    Write-Host "Git push skipped because -SkipGitPush was specified." -ForegroundColor Yellow
}
else {
    $branch = (& git branch --show-current).Trim()
    if ([string]::IsNullOrWhiteSpace($branch)) {
        throw "Unable to determine the current Git branch."
    }

    $originUrl = (& git remote get-url origin 2>$null)
    if ([string]::IsNullOrWhiteSpace($originUrl)) {
        throw "The Git remote named 'origin' is not configured. Add the GitHub origin remote and rerun the script."
    }

    & git push origin $branch
    Assert-NativeSuccess -Operation "Git push"
}

Write-Step "STEP 23 COMPLETED"

Write-Host "README.md has been generated and validated." -ForegroundColor Green
Write-Host "Dashboard screenshot: docs\assets\dashboard-overview.png" -ForegroundColor Green
Write-Host "Repository: $repositoryUrl" -ForegroundColor Green
if (-not $SkipGitPush) {
    Write-Host "Changes were pushed to GitHub." -ForegroundColor Green
}

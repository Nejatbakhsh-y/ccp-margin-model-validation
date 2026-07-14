# Contributing to the CCP Margin Model Validation Framework

Thank you for considering a contribution to this repository.

This project is an independent educational implementation of a CCP-style initial-margin model-validation framework. Contributions should preserve reproducibility, methodological transparency, model-risk governance, and clear disclosure of assumptions and limitations.

## Appropriate Contributions

Appropriate contributions include:

- Data-quality controls
- Historical-simulation and challenger-model enhancements
- Backtesting and statistical validation tests
- Stress-testing scenarios
- Sensitivity and stability analysis
- Procyclicality monitoring
- Margin add-on methodologies
- Model-risk governance documentation
- Streamlit dashboard improvements
- SQL validation queries
- Automated tests
- Documentation corrections

Contributions must not include proprietary clearing-agency methodologies, confidential data, personal information, credentials, API keys, or copyrighted datasets that cannot be redistributed.

## Development Environment

The project is designed for Windows, PowerShell, Python 3.11, and Visual Studio Code.

Create and activate the virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

## Branch Workflow

Create a focused branch for each contribution:

```powershell
git checkout main
git pull origin main
git checkout -b feature/descriptive-branch-name
```

Do not combine unrelated changes in the same branch or pull request.

## Coding Standards

Contributions should:

- Follow the existing repository structure.
- Use configuration files rather than hard-coded model parameters.
- Preserve deterministic results where practical.
- Include type hints for public functions.
- Include docstrings for nontrivial modules and functions.
- Use descriptive variable and function names.
- Avoid machine-specific absolute paths in project code.
- Avoid suppressing failed validation tests.
- Clearly identify assumptions and placeholder calibrations.
- Preserve the distinction between model development and independent validation.

## Quality Checks

Run the following checks before submitting a pull request:

```powershell
python -m ruff check .
python -m ruff format --check .
python -m pytest -v
python -m pytest --cov=src\ccp_margin --cov-report=term-missing
```

When relevant, also execute the project workflows:

```powershell
python scripts\03_validate_raw_data.py
python scripts\09_run_daily_member_margin.py
python scripts\10_run_backtesting.py
python scripts\11_run_sensitivity.py
python scripts\12_run_stress_tests.py
python scripts\13_run_procyclicality.py
python scripts\15_generate_reports.py
```

## Data and Secrets

Do not commit:

- Raw downloaded market datasets
- FRED API keys
- `.env` files
- Passwords or authentication tokens
- Personal or confidential data
- Large generated binary files
- Local virtual environments
- Cache directories

Synthetic datasets and small prepared result files may be committed when necessary to reproduce documented validation results.

## Validation Requirements

Changes affecting model calculations or validation results should include:

- A clear description of the methodology
- Relevant assumptions
- Expected behavior
- Unit or integration tests
- Updated evidence files where appropriate
- Updated limitations or findings
- An explanation of material changes in reported results

Validation failures must be disclosed and investigated. They must not be removed solely to obtain a passing result.

## Commit Messages

Use clear, action-oriented commit messages, for example:

```text
Add stressed-period margin shortfall analysis
Fix challenger covariance alignment
Document concentration add-on limitations
Add tests for Christoffersen independence statistic
```

## Pull Requests

A pull request should describe:

1. The purpose of the change
2. The files or components affected
3. The methodology or implementation approach
4. Tests performed
5. Result changes
6. New assumptions or limitations
7. Model-risk or data-quality implications

## Findings and Model-Risk Issues

Material concerns should use the appropriate repository labels:

- `validation-finding`
- `model-risk`
- `data-quality`
- `high-severity`
- `documentation`
- `enhancement`

Do not close a validation finding without documenting the resolution, compensating control, or accepted residual risk.

## Documentation

Update applicable documentation whenever a contribution changes model methodology, configuration, reproduction commands, validation tests, reported results, findings, limitations, or monitoring requirements.

## Project Disclaimer

This repository is an independent educational and portfolio implementation using public and synthetic data. It is not an implementation of any proprietary DTCC, NSCC, FICC, OCC, CME, ICE, or other clearing-agency model. It is not intended for production margining, regulatory compliance, trading, investment, or risk-management decisions.

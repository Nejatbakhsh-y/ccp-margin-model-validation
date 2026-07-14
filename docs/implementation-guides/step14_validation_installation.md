# Step 14 — Validation Tests

## Files included

- `src/ccp_margin/validation/kupiec.py`
- `src/ccp_margin/validation/christoffersen.py`
- `src/ccp_margin/validation/traffic_light.py`
- `src/ccp_margin/validation/margin_shortfall.py`
- `src/ccp_margin/validation/benchmark_comparison.py`
- `src/ccp_margin/validation/implementation_verification.py`
- `src/ccp_margin/validation/sensitivity.py`
- `src/ccp_margin/validation/procyclicality.py`
- Unit tests under `tests/validation/`
- `scripts/14_run_validation_smoke_test.py`

## Independence control

The validation modules do not import private functions from the primary model or
margin-component packages. Core returns, P&L, VaR, total-margin, and exception
calculations are independently reimplemented in
`implementation_verification.py`.

## Windows PowerShell installation

Use the project directory:

```powershell
Set-Location "C:\Users\nejat\OneDrive\Desktop\UN\Skills\GitHub 2026\ccp-margin-model-validation"
```

Activate the environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

Copy the contents of this bundle into the project root. Merge the `src`,
`tests`, and `scripts` directories; do not create a second nested project
directory.

Reinstall the editable package:

```powershell
python -m pip install -e .
```

Run only Step 14 tests:

```powershell
python -m pytest tests\validation -v
```

Run the deterministic smoke test:

```powershell
python scripts\14_run_validation_smoke_test.py
```

Run the complete project test suite:

```powershell
python -m pytest -v
```

Run static checks if configured:

```powershell
python -m ruff check src\ccp_margin\validation tests\validation scripts\14_run_validation_smoke_test.py
python -m black --check src\ccp_margin\validation tests\validation scripts\14_run_validation_smoke_test.py
```

## Required completion evidence

Step 14 is complete only when all of the following succeed:

1. `python -m pytest tests\validation -v`
2. `python scripts\14_run_validation_smoke_test.py`
3. `python -m pytest -v`
4. No validation module imports private primary-model or margin-component functions.
5. Validation results are saved rather than overwritten when integrated into the reporting pipeline.

## Interpretation controls

- A statistical-test pass means the null hypothesis was not rejected at the
  selected significance level. It does not prove model correctness.
- The Basel traffic-light classification is diagnostic only and is not a
  stand-alone CCP approval standard.
- Overlapping multi-day return horizons may induce serial dependence. Formal
  independence testing should use non-overlapping exception observations or
  explicitly disclose the limitation.
- Sensitivity and procyclicality functions provide metrics, not universal
  approval thresholds. Thresholds require documented governance approval.

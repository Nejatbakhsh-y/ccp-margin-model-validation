# Step 16 — Stress Testing

Repository:

`C:\Users\nejat\OneDrive\Desktop\UN\Skills\GitHub 2026\ccp-margin-model-validation`

Use the VS Code PowerShell terminal with `(.venv)` active.

## 1. Files in this bundle

Copy the **contents** of this bundle into the existing project root. Merge the
`configs`, `src`, `scripts`, and `tests` directories. Do not create a second
nested project directory.

```text
configs/stress_scenarios.yaml
src/ccp_margin/stress/__init__.py
src/ccp_margin/stress/historical.py
src/ccp_margin/stress/hypothetical.py
src/ccp_margin/stress/reverse_stress.py
scripts/12_run_stress_tests.py
tests/test_stress_testing.py
```

The YAML file contains controlled scenario definitions and transparent
placeholder risk parameters. They are implementation assumptions, not approved
production calibrations.

## 2. Scenario inventory

The runner generates exactly 20 stress scenarios:

- 6 historical scenarios.
- 14 hypothetical scenarios.

The hypothetical set contains:

- Equity down 10%, 20%, and 30%.
- Treasury yields up 100, 200, and 300 basis points.
- Credit spreads wider by 100, 250, and 500 basis points.
- Volatility doubled.
- Correlations set near one.
- Trading volume down 80%.
- Largest position gap of 25%.
- Largest member default during stressed liquidity.

The implementation does not misrepresent every scenario as a simple price loss:

- Historical, equity, rates, credit, and gap scenarios calculate portfolio loss.
- Volatility and correlation scenarios calculate stressed loss or stressed
  margin requirements.
- The volume scenario recalculates the liquidity-sensitive margin requirement.
- The largest-member-default scenario combines market loss with incremental
  stressed-liquidity requirement.

## 3. Required existing inputs

From the project root, run:

```powershell
Test-Path configs\project.yaml
Test-Path scripts\_daily_margin_common.py
Test-Path data\processed\returns_wide.parquet
Test-Path data\processed\daily_member_margin.parquet
Test-Path data\synthetic\member_positions.csv
```

All commands must return `True`. The position loader may use a canonical
processed Parquet position file instead of the synthetic CSV when one exists.

The daily margin file must contain the same as-of date used by the stress-test
runner. If it does not, rerun the Step 13 scripts for that date.

## 4. Preliminary-parameter warning

Keep the following project status until parameters receive empirical support and
governance approval:

```yaml
project:
  configuration_status: preliminary
```

The stress YAML separately uses:

```yaml
configuration_status: preliminary_placeholder
```

Before final validation, document and approve:

- Historical scenario date selection.
- Treasury duration and convexity assumptions.
- Credit spread-duration assumptions.
- Correlation-convergence severity.
- Liquidity-impact scaling.
- Reverse-stress directions and limits.

Do not change assumptions merely to remove unfavorable stress-test results.

## 5. Confirm the files are in the correct locations

```powershell
Get-Item configs\stress_scenarios.yaml
Get-Item src\ccp_margin\stress\historical.py
Get-Item src\ccp_margin\stress\hypothetical.py
Get-Item src\ccp_margin\stress\reverse_stress.py
Get-Item scripts\12_run_stress_tests.py
Get-Item tests\test_stress_testing.py
```

Do not place the files under a path such as:

```text
ccp-margin-model-validation\ccp_margin_step16_stress_testing_bundle\src\...
```

They must be merged directly into the existing repository.

## 6. Reinstall the editable package

Because new modules were added under `src`, run:

```powershell
python -m pip install -e .
```

## 7. Syntax and focused tests

```powershell
python -m py_compile `
  src\ccp_margin\stress\historical.py `
  src\ccp_margin\stress\hypothetical.py `
  src\ccp_margin\stress\reverse_stress.py `
  scripts\12_run_stress_tests.py

python -m pytest tests\test_stress_testing.py -q
```

Required focused result:

```text
7 passed
```

## 8. Run Step 16

Use the latest available return date and the matching daily margin date:

```powershell
python scripts\12_run_stress_tests.py
```

For an explicit date:

```powershell
python scripts\12_run_stress_tests.py --date 2026-07-10
```

The explicit date must exist in `daily_member_margin.parquet`. The return-date
resolver may move a weekend or holiday request to the latest earlier trading
date, but the daily margin file must then contain that resolved date exactly.

## 9. Generated outputs

Local processed outputs:

```text
data/processed/stress_test_results.parquet
data/processed/reverse_stress_results.parquet
```

Commit-eligible evidence:

```text
data/manifests/stress_scenario_manifest.csv
reports/evidence/stress_test_results.csv
reports/evidence/reverse_stress_results.csv
reports/evidence/stress_test_summary.json
```

## 10. Verify the 20-scenario manifest

```powershell
python -c "import pandas as pd; d=pd.read_csv('data/manifests/stress_scenario_manifest.csv'); print('Rows:',len(d)); print('Unique scenarios:',d['scenario_id'].nunique()); print(d.groupby('scenario_type')['scenario_id'].nunique())"
```

Required:

```text
Rows: 20
Unique scenarios: 20
historical       6
hypothetical    14
```

## 11. Verify stress results

```powershell
python -c "import pandas as pd; d=pd.read_parquet('data/processed/stress_test_results.parquet'); print('Rows:',len(d)); print('Scenarios:',d['scenario_id'].nunique()); print('Members:',d['member_id'].nunique()); print('Negative requirements:',int((d['stress_requirement']<0).sum())); print('Missing margin:',int(d['available_margin'].isna().sum())); print('Breaches:',int(d['margin_breach_flag'].sum())); print(d.sort_values('margin_shortfall',ascending=False)[['scenario_id','member_id','metric_basis','stress_requirement','available_margin','margin_shortfall']].head(10).to_string(index=False))"
```

Required structural results:

```text
Scenarios: 20
Negative requirements: 0
Missing margin: 0
```

The number of breaches is an empirical result. It is not required to be zero.
Do not modify or suppress scenarios to obtain a favorable result.

## 12. Verify reverse stress results

```powershell
python -c "import pandas as pd; d=pd.read_parquet('data/processed/reverse_stress_results.parquet'); print('Rows:',len(d)); print('Members:',d['member_id'].nunique()); print('Methods:',d['reverse_stress_id'].nunique()); print('Duplicate keys:',int(d.duplicated(['member_id','reverse_stress_id']).sum())); print(d[['member_id','reverse_stress_id','shock_required_pct','exhaustion_found']].head(12).to_string(index=False))"
```

Required structural results:

```text
Methods: 3
Duplicate keys: 0
```

A missing reverse-stress shock is permitted only when the member has no exposure
to the tested direction or the configured maximum shock cannot exhaust margin.

## 13. Run the full test suite

```powershell
python -m pytest -q
```

Do not stage or commit if any test fails.

## 14. Git review and commit

Processed Parquet files should remain ignored under the existing rule:

```gitignore
data/processed/*.parquet
```

Confirm:

```powershell
git status --short
git check-ignore -v data\processed\stress_test_results.parquet
git check-ignore -v data\processed\reverse_stress_results.parquet
```

Stage only the Step 16 source, configuration, tests, manifest, and evidence:

```powershell
git add `
  configs\stress_scenarios.yaml `
  src\ccp_margin\stress\__init__.py `
  src\ccp_margin\stress\historical.py `
  src\ccp_margin\stress\hypothetical.py `
  src\ccp_margin\stress\reverse_stress.py `
  scripts\12_run_stress_tests.py `
  tests\test_stress_testing.py `
  data\manifests\stress_scenario_manifest.csv `
  reports\evidence\stress_test_results.csv `
  reports\evidence\reverse_stress_results.csv `
  reports\evidence\stress_test_summary.json
```

Review the staged files:

```powershell
git diff --cached --name-only
```

Commit and push:

```powershell
git commit -m "Implement historical hypothetical and reverse stress testing"
git push
git status
```

## 15. Completion criteria

Step 16 is complete only when:

1. The focused and full test suites pass.
2. The manifest contains exactly 20 unique scenarios.
3. All six historical and fourteen hypothetical scenarios execute.
4. Stress requirements are nonnegative and reconcile to documented methods.
5. Available margin is present for every stress-result row.
6. Margin breaches and negative results remain preserved.
7. Reverse stress produces three methods per member without duplicate keys.
8. Processed Parquet files remain ignored by Git.
9. Source, configuration, tests, manifest, and evidence are committed and pushed.

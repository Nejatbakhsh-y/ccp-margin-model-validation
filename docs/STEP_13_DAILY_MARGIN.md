# Step 13 — Produce Daily Margin Calculations

Repository:

`C:\Users\nejat\OneDrive\Desktop\UN\Skills\GitHub 2026\ccp-margin-model-validation`

Use the VS Code PowerShell terminal with `(.venv)` active.

## Files in this package

Copy these files into the matching paths in the existing repository:

```text
scripts/_daily_margin_common.py
scripts/06_run_primary_model.py
scripts/07_run_challenger_model.py
scripts/08_calculate_margin_addons.py
scripts/09_run_daily_member_margin.py
tests/test_daily_margin_pipeline.py
```

The additional `_daily_margin_common.py` file centralizes schema controls, configuration access, date resolution, Parquet writing, and deterministic calculations. Do not place the outer bundle directory inside the repository.

## Operational interpretation

Each run calculates margin for one as-of date. By default, that date is the latest date in:

```text
data/processed/returns_wide.parquet
```

The final script upserts the date/member rows into:

```text
data/processed/daily_member_margin.parquet
```

Running the pipeline on later dates therefore builds a daily history without manufacturing historical position snapshots.

## Required existing inputs

Confirm these files exist:

```powershell
Test-Path data\processed\returns_wide.parquet
Test-Path data\synthetic\member_positions.csv
Test-Path configs\project.yaml
```

All three commands must return `True`.

The position file must contain:

```text
member_id
security_id
market_value
sector
asset_class
liquidity_bucket
```

`valuation_date` and `portfolio_id` are supported and recommended.

## Preliminary parameter warning

The Step 12 numerical margin parameters remain:

```text
PRELIMINARY PLACEHOLDER
```

They support implementation and testing but are not approved production calibrations. Keep:

```yaml
project:
  configuration_status: preliminary
```

Unknown liquidity buckets and asset classes intentionally cause an error. The implementation does not silently assign fallback rates.

## Syntax and focused test

Run:

```powershell
python -m py_compile `
  scripts\_daily_margin_common.py `
  scripts\06_run_primary_model.py `
  scripts\07_run_challenger_model.py `
  scripts\08_calculate_margin_addons.py `
  scripts\09_run_daily_member_margin.py

python -m pytest tests\test_daily_margin_pipeline.py -q
```

Expected focused result:

```text
1 passed
```

## Run Step 13

Run each command separately and stop if any command returns a traceback:

```powershell
python scripts\06_run_primary_model.py
python scripts\07_run_challenger_model.py
python scripts\08_calculate_margin_addons.py
python scripts\09_run_daily_member_margin.py
```

For an explicit date:

```powershell
python scripts\06_run_primary_model.py --date 2026-07-10
python scripts\07_run_challenger_model.py --date 2026-07-10
python scripts\08_calculate_margin_addons.py --date 2026-07-10
python scripts\09_run_daily_member_margin.py --date 2026-07-10
```

The requested date must have an eligible return observation. The model runners resolve a non-trading requested date to the latest earlier return date. The add-on and assembly scripts require the exact date produced by the model runners.

## Generated outputs

```text
data/processed/primary_member_margin.parquet
data/processed/primary_model_pnl_distribution.parquet
data/processed/challenger_member_margin.parquet
data/processed/margin_addons.parquet
data/processed/daily_member_margin.parquet
```

Evidence summaries:

```text
reports/evidence/primary_model_run_summary.json
reports/evidence/challenger_model_run_summary.json
reports/evidence/margin_addon_run_summary.json
reports/evidence/daily_member_margin_run_summary.json
```

## Verify the required final fields

Run:

```powershell
python -c "import pandas as pd; p='data/processed/daily_member_margin.parquet'; d=pd.read_parquet(p); required=['date','member_id','base_var','liquidity_addon','concentration_addon','gap_risk_addon','stress_buffer','total_margin','portfolio_value','gross_exposure','net_exposure','model_version']; print('Rows:',len(d)); print('Members:',d['member_id'].nunique()); print('Date range:',d['date'].min(),'to',d['date'].max()); print('Missing required fields:',sorted(set(required)-set(d.columns))); print(d[required].tail().to_string(index=False))"
```

`Missing required fields` must be:

```text
[]
```

Verify total-margin reconciliation:

```powershell
python -c "import pandas as pd; d=pd.read_parquet('data/processed/daily_member_margin.parquet'); c=d[['base_var','liquidity_addon','concentration_addon','gap_risk_addon','stress_buffer']].sum(axis=1); print('Maximum reconciliation error:',float((d['total_margin']-c).abs().max())); print('Negative margins:',int((d['total_margin']<0).sum()))"
```

Required result:

```text
Maximum reconciliation error: 0.0
Negative margins: 0
```

## Full test suite

Run:

```powershell
python -m pytest -q
```

Do not proceed to Git staging if any test fails.

## Git review and commit

Generated Parquet files should remain ignored under the existing rule:

```gitignore
data/processed/*.parquet
```

Check:

```powershell
git status --short
git check-ignore -v data\processed\daily_member_margin.parquet
```

Stage only Step 13 source, test, and evidence files:

```powershell
git add `
  scripts\_daily_margin_common.py `
  scripts\06_run_primary_model.py `
  scripts\07_run_challenger_model.py `
  scripts\08_calculate_margin_addons.py `
  scripts\09_run_daily_member_margin.py `
  tests\test_daily_margin_pipeline.py `
  reports\evidence\primary_model_run_summary.json `
  reports\evidence\challenger_model_run_summary.json `
  reports\evidence\margin_addon_run_summary.json `
  reports\evidence\daily_member_margin_run_summary.json
```

Review:

```powershell
git diff --cached --name-only
```

Commit and push:

```powershell
git commit -m "Produce daily clearing member margin calculations"
git push
git status
```

Step 13 is complete only when:

1. The focused and full test suites pass.
2. `daily_member_margin.parquet` exists.
3. All required fields are present.
4. Total margin reconciles exactly to its five components.
5. There are no duplicate `date` and `member_id` rows.
6. The generated Parquet file is ignored by Git.
7. The source and evidence files are committed and pushed.

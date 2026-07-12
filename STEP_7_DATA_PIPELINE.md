# Step 7 — Build the Data Pipeline

This package is designed for the Windows project path:

`C:\Users\nejat\OneDrive\Desktop\UN\Skills\GitHub 2026\ccp-margin-model-validation`

Use the VS Code PowerShell terminal and keep the Python 3.11 virtual environment active.

## 1. Copy the supplied files into the repository

Extract the bundle so that these paths are created or replaced:

- `configs/data/market_data.yaml`
- `.env.example`
- `scripts/_data_pipeline_common.py`
- `scripts/01_download_market_data.py`
- `scripts/02_download_fred_data.py`
- `scripts/03_validate_raw_data.py`
- `scripts/04_build_clean_market_dataset.py`
- `scripts/05_generate_member_portfolios.py`

Do not place the outer `ccp_margin_step7_bundle` directory inside the repository. Copy its contents into the repository root.

## 2. Confirm the existing project configuration

The following fields must already exist in `configs/project.yaml`:

```yaml
project:
  name: ccp-margin-model-validation
  currency: USD
  random_seed: 2026

data:
  start_date: "2007-01-01"
  end_date: null
  price_field: adjusted_close
  minimum_completeness: 0.995

portfolio:
  number_of_members: 30
  minimum_positions: 3
  maximum_positions: 10
  gross_notional_min: 10000000
  gross_notional_max: 1000000000
```

Do not duplicate these fields in another YAML file.

## 3. Update `.gitignore`

Open `.gitignore` and ensure that it contains:

```gitignore
.env
.venv/
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
data/raw/
data/interim/
*.log
*.db
```

Recommended additional protection for generated binary datasets:

```gitignore
data/processed/*.parquet
```

The generated CSV manifests, dictionaries, evidence summaries, and small synthetic portfolios remain eligible for version control.

## 4. Create the local FRED environment file

Run:

```powershell
Copy-Item .env.example .env -Force
code .env
```

Replace only the placeholder in `.env`:

```text
FRED_API_KEY=your_real_32_character_key
```

Do not paste the key into source code, YAML, screenshots, Git commits, or terminal commands.

Confirm that Git ignores it:

```powershell
git check-ignore -v .env
```

A matching `.gitignore` rule must be displayed.

## 5. Confirm packages and syntax

Run:

```powershell
python -c "import pandas, numpy, requests, yaml, dotenv, yfinance, pyarrow; print('STEP 7 PACKAGE CHECK PASSED')"

python -m py_compile `
  scripts/_data_pipeline_common.py `
  scripts/01_download_market_data.py `
  scripts/02_download_fred_data.py `
  scripts/03_validate_raw_data.py `
  scripts/04_build_clean_market_dataset.py `
  scripts/05_generate_member_portfolios.py
```

Expected result: no traceback and `STEP 7 PACKAGE CHECK PASSED`.

## 6. Run the pipeline in order

Run each command separately. Stop when a command returns a traceback or nonzero exit status.

```powershell
python scripts/01_download_market_data.py
python scripts/02_download_fred_data.py
python scripts/03_validate_raw_data.py
python scripts/04_build_clean_market_dataset.py
python scripts/05_generate_member_portfolios.py
```

The order is mandatory:

1. Market download.
2. FRED download.
3. Raw-data validation.
4. Clean dataset construction.
5. Synthetic clearing-member portfolio generation.

The scripts do not forward-fill missing prices. Adjusted-price returns are calculated only after raw validation. The clean wide dataset uses a complete common trading-date panel when `require_common_calendar: true`.

## 7. Inspect the expected outputs

### Raw data — local only, not committed

```text
data/raw/market/<TICKER>.parquet
data/raw/macro/<SERIES_ID>.parquet
data/raw/macro/fred_series_raw.parquet
```

### Processed binary data — generated locally

```text
data/processed/market_data_clean_long.parquet
data/processed/adjusted_close_wide.parquet
data/processed/close_wide.parquet
data/processed/volume_wide.parquet
data/processed/returns_wide.parquet
data/processed/log_returns_wide.parquet
```

### Commit-eligible evidence and metadata

```text
data/manifests/market_data_manifest.csv
data/manifests/market_data_dictionary.csv
data/manifests/market_download_summary.json
data/manifests/fred_data_manifest.csv
data/manifests/fred_data_dictionary.csv
data/manifests/fred_series_metadata.csv
data/manifests/fred_download_summary.json
data/manifests/raw_data_quality_summary.json
data/manifests/clean_market_dataset_manifest.csv
data/manifests/clean_market_dataset_summary.json
data/manifests/member_portfolio_manifest.json
data/manifests/member_portfolio_data_dictionary.csv
reports/evidence/raw_data_validation.csv
reports/evidence/raw_data_validation_summary.json
reports/evidence/market_completeness.csv
data/synthetic/member_positions.csv
data/synthetic/member_portfolio_summary.csv
data/synthetic/example_member_positions.csv
```

## 8. Run verification commands

```powershell
python -c "import pandas as pd; p=pd.read_parquet('data/processed/adjusted_close_wide.parquet'); print('Adjusted-close shape:', p.shape); print('Date range:', p.index.min(), 'to', p.index.max()); print('Missing values:', int(p.isna().sum().sum()))"

python -c "import pandas as pd; r=pd.read_parquet('data/processed/returns_wide.parquet'); print('Returns shape:', r.shape); print('Missing values:', int(r.isna().sum().sum()))"

python -c "import pandas as pd; x=pd.read_csv('data/synthetic/member_positions.csv'); s=pd.read_csv('data/synthetic/member_portfolio_summary.csv'); print('Members:', s['member_id'].nunique()); print('Positions:', len(x)); print('Weight reconciliation max error:', (x.groupby('member_id')['absolute_weight'].sum()-1).abs().max())"

python -c "import json; from pathlib import Path; p=Path('reports/evidence/raw_data_validation_summary.json'); print(json.loads(p.read_text()))"
```

Required results:

- Adjusted-close data have zero missing values because the common calendar is enforced.
- Return data have zero missing values.
- Exactly 30 member portfolios exist.
- The maximum absolute-weight reconciliation error is effectively zero.
- `raw_data_validation_summary.json` reports `status: passed` and zero error failures.

Warnings remain preserved. Do not delete a warning merely because the pipeline completes.

## 9. Confirm that prohibited files are not staged

Run:

```powershell
git status --short

git check-ignore -v data/raw/market/SPY.parquet
git check-ignore -v data/raw/macro/VIXCLS.parquet
git check-ignore -v .env
```

Each `git check-ignore` command must display the rule responsible for excluding the file.

Do not use `git add .` until this check is complete.

## 10. Stage only the appropriate Step 7 files

Run:

```powershell
git add `
  .gitignore `
  .env.example `
  configs/data/market_data.yaml `
  scripts/_data_pipeline_common.py `
  scripts/01_download_market_data.py `
  scripts/02_download_fred_data.py `
  scripts/03_validate_raw_data.py `
  scripts/04_build_clean_market_dataset.py `
  scripts/05_generate_member_portfolios.py `
  data/manifests `
  reports/evidence/*.csv `
  reports/evidence/*.json `
  data/synthetic/*.csv
```

Confirm the staged set:

```powershell
git diff --cached --name-only
```

The output must not contain:

- `.env`
- `.venv`
- `data/raw`
- `data/interim`
- log files
- database files
- processed Parquet files when the recommended processed-data ignore rule is used

## 11. Commit Step 7

```powershell
git commit -m "Build reproducible market and FRED data pipeline"
git status
```

Expected final status:

```text
nothing to commit, working tree clean
```

Local ignored data remain on the computer even though Git reports a clean tracked working tree.

## Control rationale

- `auto_adjust=False` is set explicitly so the download retains unadjusted OHLC and a separate adjusted-close field.
- `actions=True` is set explicitly so dividends and stock splits are requested; capital-gain distributions are retained when supplied.
- An explicit configured end date is converted to an exclusive provider end date so the configured date remains included.
- FRED downloads use the official HTTPS REST API and store no API key in output or logs.
- FRED data use the latest values available at retrieval; the vintage policy is recorded in manifests.
- Raw failures, warnings, checksums, observation counts, and data dictionaries are preserved as evidence.
- Synthetic portfolios are reproducible through the project random seed and reconcile gross notional, net notional, position counts, and absolute weights.

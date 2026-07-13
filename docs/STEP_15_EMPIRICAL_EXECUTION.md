# Step 15 Empirical Sensitivity Execution

This package adds the empirical result generator required after the Step 15
scenario manifest has been created.

## Inputs

- `data/processed/sensitivity_scenario_manifest.csv`
- `data/processed/returns_wide.parquet`
- `data/processed/volume_wide.parquet`
- A supported clearing-member position dataset
- `configs/project.yaml`

## Controlled design

- Exactly 20 manifest scenarios.
- Final 250 eligible backtesting dates.
- At least 1,000 preceding return observations.
- At least 5 forward observations.
- Current positions applied to historical return observations when only one
  position snapshot is available.
- Historical-simulation VaR.
- EWMA challenger VaR.
- PSD-controlled correlation shocks.
- Concentration, liquidity, gap-risk, and stress components.
- Forward compounded realized loss.
- Scenario-level checkpointing.

## Output

`data/processed/sensitivity_scenario_results.parquet`

Required fields:

- `scenario_id`
- `date`
- `member_id`
- `margin`
- `realized_loss`

The file also contains component and parameter traceability fields.

## Execution

```powershell
python -m py_compile scripts\15_generate_sensitivity_results.py
python -m pytest tests\validation\test_sensitivity_result_generator.py -q
python scripts\15_generate_sensitivity_results.py --reset
```

After successful completion:

```powershell
python scripts\15_run_sensitivity_tests.py
```

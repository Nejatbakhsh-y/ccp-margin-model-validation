# Step 15 — Sensitivity Testing

## Required scenario design

Use one-at-a-time sensitivity testing. Hold every parameter at the documented
baseline and change only the parameter named by the scenario.

The generated manifest contains 20 scenarios:

- 1 baseline.
- 19 non-baseline sensitivity scenarios.

This is not a full Cartesian grid. A full Cartesian grid would contain 14,580
combinations and would mix first-order effects with interaction effects.

## Required model-generated input

Create:

`data/processed/sensitivity_scenario_results.parquet`

Required columns:

| Column | Definition |
|---|---|
| `scenario_id` | Must match the generated manifest |
| `date` | Backtesting observation date |
| `member_id` | Clearing-member identifier |
| `margin` | Total margin under the scenario |
| `realized_loss` | Positive realized loss for the matching observation |

Optional columns:

- `exception`
- `shortfall`

The validation code independently recalculates both optional fields and rejects
inconsistent values.

## Required execution principle

For every scenario in:

`data/processed/sensitivity_scenario_manifest.csv`

rerun the relevant components rather than scaling baseline outputs:

- Primary historical-simulation model.
- Challenger EWMA model.
- Concentration add-on.
- Liquidity add-on.
- Stress buffer.
- Correlation-shock calculation.
- Backtesting exception calculation.
- Margin-shortfall calculation.

All scenarios must use identical dates, members, positions, and realized-loss
observations. Only the named scenario parameter may change.

## Required outputs

The runner writes:

- `reports/validation/sensitivity/scenario_summary.csv`
- `reports/validation/sensitivity/member_ranking_detail.csv`
- `reports/validation/sensitivity/parameter_stability.csv`
- `reports/validation/sensitivity/sensitivity_metadata.json`
- `reports/validation/sensitivity/sensitivity_report.md`

## Interpretation requirements

Investigate:

- Economically implausible direction of margin change.
- Non-monotonic response where monotonicity is expected.
- Material changes in exceptions or shortfall.
- Clearing-member rank instability.
- High parameter elasticity.
- Any parameter carrying a `REVIEW` stability flag.
- Any failed Kupiec result.

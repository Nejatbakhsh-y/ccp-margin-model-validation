# Step 15 Sensitivity Testing Report

## Scope

The analysis changes one parameter at a time relative to the documented
baseline. The scenario set covers confidence level, lookback window, MPOR,
EWMA lambda, concentration threshold, liquidity threshold as a percentage of
ADV, stress buffer, and correlation shock.

## Configuration Status

**PRELIMINARY PLACEHOLDER**

The review thresholds are diagnostic escalation thresholds. They are not
approved production calibrations or model-approval limits.

## Scenario-Level Results

| scenario_id | parameter | parameter_value | mean_margin_change_pct | exception_count_change | exception_rate_change | total_shortfall_change_pct | member_rank_correlation | maximum_absolute_member_rank_change | margin_elasticity |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | baseline | baseline | 0 | 0 | 0 | 0 | 1 | 0 |  |
| confidence_level__0p975 | confidence_level | 0.975 | -2.51882e-06 | 0 | 0 | 0 | 1 | 0 | 1.66242e-06 |
| confidence_level__0p995 | confidence_level | 0.995 | 0.0016544 | 0 | 0 | 0 | 1 | 0 | 0.00327572 |
| lookback_days__153 | lookback_days | 153 | -18.9397 | 1 | 0.000133333 |  | 0.994661 | 2 | 0.272906 |
| lookback_days__250 | lookback_days | 250 | -7.2506 | 0 | 0 | 0 | 0.99911 | 1 | 0.145012 |
| lookback_days__750 | lookback_days | 750 | 0.0986166 | 0 | 0 | 0 | 1 | 0 | 0.00197233 |
| lookback_days__1000 | lookback_days | 1000 | 0.900873 | 0 | 0 | 0 | 0.999555 | 1 | 0.00900873 |
| mpor_days__3 | mpor_days | 3 | 33.1509 | 0 | 0 | 0 | 0.991991 | 3 | 0.165754 |
| mpor_days__5 | mpor_days | 5 | 38.6848 | 0 | 0 | 0 | 0.983537 | 5 | 0.096712 |
| ewma_lambda__0p9 | ewma_lambda | 0.9 | 0.00034347 | 0 | 0 | 0 | 1 | 0 | -8.07153e-05 |
| ewma_lambda__0p97 | ewma_lambda | 0.97 | -2.51882e-06 | 0 | 0 | 0 | 1 | 0 | -7.8923e-07 |
| concentration_threshold__0p1 | concentration_threshold | 0.1 | 13.0163 | 0 | 0 | 0 | 0.99911 | 1 | -0.260327 |
| concentration_threshold__0p3 | concentration_threshold | 0.3 | -12.6501 | 0 | 0 | 0 | 0.99733 | 2 | -0.253001 |
| liquidity_threshold_adv__0p05 | liquidity_threshold_adv | 0.05 | 1.82139 | 0 | 0 | 0 | 1 | 0 | -0.0364277 |
| liquidity_threshold_adv__0p2 | liquidity_threshold_adv | 0.2 | -2.6819 | 0 | 0 | 0 | 0.999555 | 1 | -0.026819 |
| stress_buffer__0p0 | stress_buffer | 0.0 | -9.09091 | 0 | 0 | 0 | 1 | 0 | 0.0909091 |
| stress_buffer__0p25 | stress_buffer | 0.25 | 13.6364 | 0 | 0 | 0 | 1 | 0 | 0.0909091 |
| stress_buffer__0p5 | stress_buffer | 0.5 | 36.3636 | 0 | 0 | 0 | 1 | 0 | 0.0909091 |
| correlation_shock__plus_25_percent | correlation_shock | plus_25_percent | 5.70577e-05 | 0 | 0 | 0 | 1 | 0 |  |
| correlation_shock__near_one | correlation_shock | near_one | 0.00497708 | 0 | 0 | 0 | 1 | 0 |  |

## Parameter Stability

| parameter | scenario_count | maximum_absolute_margin_change_pct | maximum_absolute_exception_rate_change | maximum_absolute_shortfall_change_pct | minimum_member_rank_correlation | maximum_absolute_margin_elasticity | stability_flag | review_reasons |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| confidence_level | 2 | 0.0016544 | 0 | 0 | 1 | 0.00327572 | STABLE |  |
| lookback_days | 4 | 18.9397 | 0.000133333 | 0 | 0.994661 | 0.272906 | STABLE |  |
| mpor_days | 2 | 38.6848 | 0 | 0 | 0.983537 | 0.165754 | REVIEW | margin_change |
| ewma_lambda | 2 | 0.00034347 | 0 | 0 | 1 | 8.07153e-05 | STABLE |  |
| concentration_threshold | 2 | 13.0163 | 0 | 0 | 0.99733 | 0.260327 | STABLE |  |
| liquidity_threshold_adv | 2 | 2.6819 | 0 | 0 | 0.999555 | 0.0364277 | STABLE |  |
| stress_buffer | 3 | 36.3636 | 0 | 0 | 1 | 0.0909091 | REVIEW | margin_change |
| correlation_shock | 2 | 0.00497708 | 0 | 0 | 1 |  | STABLE |  |

## Required Interpretation

Review, at minimum:

- Margin change.
- Backtesting and Kupiec-result change.
- Exception-count and exception-rate change.
- Margin-shortfall change.
- Clearing-member ranking change.
- Parameter stability and elasticity.
- Non-monotonic or economically implausible responses.
- Any scenario classified as REVIEW.

## Evidence Files

- `scenario_summary.csv`
- `member_ranking_detail.csv`
- `parameter_stability.csv`
- `sensitivity_metadata.json`

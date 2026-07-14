-- Step 18: Load normalized temporary staging views into physical tables.
-- scripts/18_build_duckdb.py creates each stg_* view from a discovered
-- CSV or Parquet source and casts it to the schema defined in schema.sql.

BEGIN TRANSACTION;

DELETE FROM market_prices;
INSERT INTO market_prices (
    valuation_date, security_id, adjusted_close, price, volume, source
)
SELECT valuation_date, security_id, adjusted_close, price, volume, source
FROM stg_market_prices;

DELETE FROM risk_factor_returns;
INSERT INTO risk_factor_returns (
    valuation_date, risk_factor_id, security_id,
    return_1d, return_3d, return_5d, log_return_1d
)
SELECT valuation_date, risk_factor_id, security_id,
       return_1d, return_3d, return_5d, log_return_1d
FROM stg_risk_factor_returns;

DELETE FROM member_positions;
INSERT INTO member_positions (
    valuation_date, member_id, portfolio_id, security_id,
    quantity, price, market_value, long_short_flag,
    sector, asset_class, liquidity_bucket
)
SELECT valuation_date, member_id, portfolio_id, security_id,
       quantity, price, market_value, long_short_flag,
       sector, asset_class, liquidity_bucket
FROM stg_member_positions;

DELETE FROM portfolio_exposures;
INSERT INTO portfolio_exposures (
    valuation_date, member_id, portfolio_id, gross_exposure,
    net_exposure, long_exposure, short_exposure,
    top_position_weight, concentration_hhi, illiquid_exposure,
    leverage_ratio
)
SELECT valuation_date, member_id, portfolio_id, gross_exposure,
       net_exposure, long_exposure, short_exposure,
       top_position_weight, concentration_hhi, illiquid_exposure,
       leverage_ratio
FROM stg_portfolio_exposures;

DELETE FROM daily_margin;
INSERT INTO daily_margin (
    valuation_date, member_id, portfolio_id, model_name,
    mpor_days, confidence_level, base_var, liquidity_addon,
    concentration_addon, gap_risk_addon, stress_buffer,
    total_initial_margin, realized_loss
)
SELECT valuation_date, member_id, portfolio_id, model_name,
       mpor_days, confidence_level, base_var, liquidity_addon,
       concentration_addon, gap_risk_addon, stress_buffer,
       total_initial_margin, realized_loss
FROM stg_daily_margin;

DELETE FROM backtesting_results;
INSERT INTO backtesting_results (
    valuation_date, member_id, portfolio_id, model_name,
    mpor_days, confidence_level, margin_amount, realized_loss,
    exception_flag, margin_shortfall
)
SELECT valuation_date, member_id, portfolio_id, model_name,
       mpor_days, confidence_level, margin_amount, realized_loss,
       exception_flag, margin_shortfall
FROM stg_backtesting_results;

DELETE FROM stress_results;
INSERT INTO stress_results (
    valuation_date, member_id, portfolio_id, scenario_id,
    scenario_name, stressed_loss, available_margin,
    margin_shortfall, breach_flag
)
SELECT valuation_date, member_id, portfolio_id, scenario_id,
       scenario_name, stressed_loss, available_margin,
       margin_shortfall, breach_flag
FROM stg_stress_results;

DELETE FROM sensitivity_results;
INSERT INTO sensitivity_results (
    valuation_date, member_id, portfolio_id, scenario_id,
    parameter_name, baseline_value, shocked_value,
    baseline_margin, shocked_margin, absolute_change, pct_change
)
SELECT valuation_date, member_id, portfolio_id, scenario_id,
       parameter_name, baseline_value, shocked_value,
       baseline_margin, shocked_margin, absolute_change, pct_change
FROM stg_sensitivity_results;

DELETE FROM monitoring_metrics;
INSERT INTO monitoring_metrics (
    metric_date, member_id, metric_name, metric_value,
    threshold_value, status, source_table, details
)
SELECT metric_date, member_id, metric_name, metric_value,
       threshold_value, status, source_table, details
FROM stg_monitoring_metrics;

DELETE FROM validation_findings;
INSERT INTO validation_findings (
    finding_id, finding_date, test_name, finding_scope,
    severity, status, finding, evidence, recommendation,
    finding_owner, due_date
)
SELECT finding_id, finding_date, test_name, finding_scope,
       severity, status, finding, evidence, recommendation,
       finding_owner, due_date
FROM stg_validation_findings;

COMMIT;

-- Step 18: DuckDB physical schema
-- CCP Margin Model Independent Validation Framework

CREATE TABLE IF NOT EXISTS market_prices (
    valuation_date DATE,
    security_id VARCHAR,
    adjusted_close DOUBLE,
    price DOUBLE,
    volume DOUBLE,
    source VARCHAR,
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS risk_factor_returns (
    valuation_date DATE,
    risk_factor_id VARCHAR,
    security_id VARCHAR,
    return_1d DOUBLE,
    return_3d DOUBLE,
    return_5d DOUBLE,
    log_return_1d DOUBLE,
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS member_positions (
    valuation_date DATE,
    member_id VARCHAR,
    portfolio_id VARCHAR,
    security_id VARCHAR,
    quantity DOUBLE,
    price DOUBLE,
    market_value DOUBLE,
    long_short_flag VARCHAR,
    sector VARCHAR,
    asset_class VARCHAR,
    liquidity_bucket VARCHAR,
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS portfolio_exposures (
    valuation_date DATE,
    member_id VARCHAR,
    portfolio_id VARCHAR,
    gross_exposure DOUBLE,
    net_exposure DOUBLE,
    long_exposure DOUBLE,
    short_exposure DOUBLE,
    top_position_weight DOUBLE,
    concentration_hhi DOUBLE,
    illiquid_exposure DOUBLE,
    leverage_ratio DOUBLE,
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS daily_margin (
    valuation_date DATE,
    member_id VARCHAR,
    portfolio_id VARCHAR,
    model_name VARCHAR,
    mpor_days INTEGER,
    confidence_level DOUBLE,
    base_var DOUBLE,
    liquidity_addon DOUBLE,
    concentration_addon DOUBLE,
    gap_risk_addon DOUBLE,
    stress_buffer DOUBLE,
    total_initial_margin DOUBLE,
    realized_loss DOUBLE,
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS backtesting_results (
    valuation_date DATE,
    member_id VARCHAR,
    portfolio_id VARCHAR,
    model_name VARCHAR,
    mpor_days INTEGER,
    confidence_level DOUBLE,
    margin_amount DOUBLE,
    realized_loss DOUBLE,
    exception_flag INTEGER,
    margin_shortfall DOUBLE,
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stress_results (
    valuation_date DATE,
    member_id VARCHAR,
    portfolio_id VARCHAR,
    scenario_id VARCHAR,
    scenario_name VARCHAR,
    stressed_loss DOUBLE,
    available_margin DOUBLE,
    margin_shortfall DOUBLE,
    breach_flag INTEGER,
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sensitivity_results (
    valuation_date DATE,
    member_id VARCHAR,
    portfolio_id VARCHAR,
    scenario_id VARCHAR,
    parameter_name VARCHAR,
    baseline_value DOUBLE,
    shocked_value DOUBLE,
    baseline_margin DOUBLE,
    shocked_margin DOUBLE,
    absolute_change DOUBLE,
    pct_change DOUBLE,
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS monitoring_metrics (
    metric_date DATE,
    member_id VARCHAR,
    metric_name VARCHAR,
    metric_value DOUBLE,
    threshold_value DOUBLE,
    status VARCHAR,
    source_table VARCHAR,
    details VARCHAR,
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS validation_findings (
    finding_id VARCHAR,
    finding_date DATE,
    test_name VARCHAR,
    finding_scope VARCHAR,
    severity VARCHAR,
    status VARCHAR,
    finding VARCHAR,
    evidence VARCHAR,
    recommendation VARCHAR,
    finding_owner VARCHAR,
    due_date DATE,
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

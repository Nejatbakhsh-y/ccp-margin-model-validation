-- Step 18: Reusable validation views and analytical queries

CREATE OR REPLACE VIEW v_member_exception_summary AS
SELECT
    member_id,
    COUNT(*) FILTER (WHERE exception_flag = 1) AS exceptions,
    SUM(COALESCE(margin_shortfall, 0.0)) FILTER (WHERE exception_flag = 1)
        AS total_shortfall,
    COUNT(*) AS observations,
    AVG(COALESCE(exception_flag, 0)) AS observed_exception_rate,
    MAX(COALESCE(margin_shortfall, 0.0)) AS maximum_shortfall
FROM backtesting_results
GROUP BY member_id;

CREATE OR REPLACE VIEW v_model_backtesting_summary AS
SELECT
    model_name,
    mpor_days,
    confidence_level,
    COUNT(*) AS observations,
    SUM(CASE WHEN exception_flag = 1 THEN 1 ELSE 0 END) AS exceptions,
    AVG(CASE WHEN exception_flag = 1 THEN 1.0 ELSE 0.0 END)
        AS observed_exception_rate,
    SUM(COALESCE(margin_shortfall, 0.0)) AS total_shortfall,
    MAX(COALESCE(margin_shortfall, 0.0)) AS maximum_shortfall
FROM backtesting_results
GROUP BY model_name, mpor_days, confidence_level;

CREATE OR REPLACE VIEW v_stress_breach_summary AS
SELECT
    scenario_id,
    scenario_name,
    COUNT(*) AS tested_portfolios,
    SUM(CASE WHEN breach_flag = 1 THEN 1 ELSE 0 END) AS breaches,
    AVG(CASE WHEN breach_flag = 1 THEN 1.0 ELSE 0.0 END) AS breach_rate,
    SUM(COALESCE(margin_shortfall, 0.0)) AS aggregate_shortfall,
    MAX(COALESCE(margin_shortfall, 0.0)) AS maximum_shortfall
FROM stress_results
GROUP BY scenario_id, scenario_name;

CREATE OR REPLACE VIEW v_sensitivity_largest_movements AS
SELECT
    valuation_date,
    member_id,
    portfolio_id,
    scenario_id,
    parameter_name,
    baseline_margin,
    shocked_margin,
    absolute_change,
    pct_change,
    ABS(COALESCE(pct_change, 0.0)) AS absolute_pct_change
FROM sensitivity_results;

CREATE OR REPLACE VIEW v_open_validation_findings AS
SELECT
    finding_id,
    finding_date,
    test_name,
    finding_scope,
    severity,
    status,
    finding,
    recommendation,
    finding_owner,
    due_date
FROM validation_findings
WHERE LOWER(COALESCE(status, 'open')) NOT IN ('closed', 'resolved', 'remediated');

-- Required example query:
SELECT
    member_id,
    COUNT(*) AS exceptions,
    SUM(margin_shortfall) AS total_shortfall
FROM backtesting_results
WHERE exception_flag = 1
GROUP BY member_id
ORDER BY total_shortfall DESC;

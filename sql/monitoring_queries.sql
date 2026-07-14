-- Step 18: Reusable margin-monitoring and procyclicality views

CREATE OR REPLACE VIEW v_daily_margin_changes AS
WITH ordered_margin AS (
    SELECT
        valuation_date,
        member_id,
        portfolio_id,
        model_name,
        mpor_days,
        total_initial_margin,
        LAG(total_initial_margin) OVER (
            PARTITION BY member_id, portfolio_id, model_name, mpor_days
            ORDER BY valuation_date
        ) AS prior_margin,
        LAG(total_initial_margin, 5) OVER (
            PARTITION BY member_id, portfolio_id, model_name, mpor_days
            ORDER BY valuation_date
        ) AS margin_five_observations_ago
    FROM daily_margin
)
SELECT
    *,
    CASE
        WHEN prior_margin IS NULL OR prior_margin = 0 THEN NULL
        ELSE total_initial_margin / prior_margin - 1.0
    END AS daily_margin_pct_change,
    CASE
        WHEN margin_five_observations_ago IS NULL
          OR margin_five_observations_ago = 0 THEN NULL
        ELSE total_initial_margin / margin_five_observations_ago - 1.0
    END AS weekly_margin_pct_change
FROM ordered_margin;

CREATE OR REPLACE VIEW v_margin_jump_counts AS
SELECT
    member_id,
    COUNT(*) FILTER (WHERE ABS(daily_margin_pct_change) > 0.10) AS jumps_over_10pct,
    COUNT(*) FILTER (WHERE ABS(daily_margin_pct_change) > 0.20) AS jumps_over_20pct,
    COUNT(*) FILTER (WHERE ABS(daily_margin_pct_change) > 0.30) AS jumps_over_30pct,
    MAX(ABS(daily_margin_pct_change)) AS largest_absolute_daily_change
FROM v_daily_margin_changes
GROUP BY member_id;

CREATE OR REPLACE VIEW v_member_margin_volatility AS
SELECT
    member_id,
    AVG(total_initial_margin) AS average_margin,
    STDDEV_SAMP(total_initial_margin) AS margin_level_volatility,
    STDDEV_SAMP(daily_margin_pct_change) AS margin_change_volatility,
    MIN(total_initial_margin) AS minimum_margin,
    MAX(total_initial_margin) AS maximum_margin
FROM v_daily_margin_changes
GROUP BY member_id;

CREATE OR REPLACE VIEW v_margin_drawdown AS
WITH running_peak AS (
    SELECT
        valuation_date,
        member_id,
        portfolio_id,
        model_name,
        mpor_days,
        total_initial_margin,
        MAX(total_initial_margin) OVER (
            PARTITION BY member_id, portfolio_id, model_name, mpor_days
            ORDER BY valuation_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_peak_margin
    FROM daily_margin
)
SELECT
    *,
    CASE
        WHEN running_peak_margin IS NULL OR running_peak_margin = 0 THEN NULL
        ELSE total_initial_margin / running_peak_margin - 1.0
    END AS drawdown_from_peak
FROM running_peak;

CREATE OR REPLACE VIEW v_monitoring_status_summary AS
SELECT
    metric_date,
    metric_name,
    status,
    COUNT(*) AS metric_count,
    AVG(metric_value) AS average_metric_value,
    MAX(metric_value) AS maximum_metric_value
FROM monitoring_metrics
GROUP BY metric_date, metric_name, status;

SELECT *
FROM v_margin_jump_counts
ORDER BY jumps_over_30pct DESC, jumps_over_20pct DESC, jumps_over_10pct DESC;


"""Structural and data-quality verification for the Step 18 DuckDB pipeline."""

from pathlib import Path

import duckdb
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = PROJECT_ROOT / "data" / "database" / "ccp_margin_validation.duckdb"
MANIFEST_PATH = PROJECT_ROOT / "reports" / "sql" / "load_manifest.csv"
SENSITIVITY_PATH = PROJECT_ROOT / "data" / "processed" / "sensitivity_scenario_results.parquet"

REQUIRED_TABLES = {
    "market_prices",
    "risk_factor_returns",
    "member_positions",
    "portfolio_exposures",
    "daily_margin",
    "backtesting_results",
    "stress_results",
    "sensitivity_results",
    "monitoring_metrics",
    "validation_findings",
}

REQUIRED_VIEWS = {
    "v_member_exception_summary",
    "v_model_backtesting_summary",
    "v_stress_breach_summary",
    "v_sensitivity_largest_movements",
    "v_open_validation_findings",
    "v_daily_margin_changes",
    "v_margin_jump_counts",
    "v_member_margin_volatility",
    "v_margin_drawdown",
    "v_monitoring_status_summary",
}

EXPECTED_SOURCES = {
    "market_prices": "data/processed/market_prices_clean.parquet",
    "risk_factor_returns": "data/processed/log_returns_wide.parquet",
    "member_positions": "data/processed/clearing_member_positions.parquet",
    "portfolio_exposures": "data/processed/portfolio_exposures.parquet",
    "daily_margin": "data/processed/daily_member_margin.parquet",
    "backtesting_results": "data/processed/sensitivity_scenario_results.parquet",
    "stress_results": "data/processed/stress_test_results.parquet",
    "sensitivity_results": "data/processed/sensitivity_scenario_results.parquet",
    "monitoring_metrics": "data/processed/procyclicality_monitoring_metrics.csv",
    "validation_findings": "reports/evidence/findings/finding_register.csv",
}

FORBIDDEN_SOURCE_FRAGMENTS = {
    "reverse_stress_results",
    "fred_series_raw",
    "t10y2y",
    "dgs10",
    "dgs2",
    "vixcls",
    "raw_data_validation",
}


def baseline_mask(frame: pd.DataFrame) -> pd.Series:
    mask = pd.Series(False, index=frame.index)
    if "is_baseline" in frame.columns:
        values = frame["is_baseline"]
        if pd.api.types.is_bool_dtype(values):
            mask |= values.fillna(False)
        else:
            mask |= values.astype("string").str.strip().str.lower().isin({"true", "1", "yes", "y", "baseline"})
    if "scenario_id" in frame.columns:
        mask |= frame["scenario_id"].astype("string").str.strip().str.lower().eq("baseline")
    return mask


def test_database_exists() -> None:
    assert DATABASE_PATH.exists(), f"Database does not exist: {DATABASE_PATH}"


def test_required_tables_and_views_exist() -> None:
    with duckdb.connect(str(DATABASE_PATH), read_only=True) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='main' AND table_type='BASE TABLE'"
            ).fetchall()
        }
        views = {
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM information_schema.views WHERE table_schema='main'"
            ).fetchall()
        }
    assert REQUIRED_TABLES.issubset(tables)
    assert REQUIRED_VIEWS.issubset(views)


def test_manifest_uses_only_approved_sources() -> None:
    assert MANIFEST_PATH.exists(), f"Manifest does not exist: {MANIFEST_PATH}"
    manifest = pd.read_csv(MANIFEST_PATH)
    actual = {
        str(row.table_name): str(row.source_file).replace("\\", "/")
        for row in manifest.itertuples(index=False)
    }
    assert actual == EXPECTED_SOURCES
    combined = "\n".join(actual.values()).lower()
    assert not any(fragment in combined for fragment in FORBIDDEN_SOURCE_FRAGMENTS)
    assert set(manifest["status"]) == {"LOADED"}


def test_expected_tables_are_nonempty() -> None:
    expected_nonempty = REQUIRED_TABLES - {"validation_findings"}
    with duckdb.connect(str(DATABASE_PATH), read_only=True) as connection:
        counts = {
            table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            for table in expected_nonempty
        }
    assert all(count > 0 for count in counts.values()), counts


def test_risk_factor_returns_are_long_format() -> None:
    with duckdb.connect(str(DATABASE_PATH), read_only=True) as connection:
        rows, dates, factors, duplicates, null_keys = connection.execute(
            """
            SELECT
                COUNT(*) AS rows,
                COUNT(DISTINCT valuation_date) AS dates,
                COUNT(DISTINCT risk_factor_id) AS factors,
                COUNT(*) - COUNT(DISTINCT (valuation_date, risk_factor_id)) AS duplicates,
                SUM(CASE WHEN valuation_date IS NULL OR risk_factor_id IS NULL OR log_return_1d IS NULL THEN 1 ELSE 0 END) AS null_keys
            FROM risk_factor_returns
            """
        ).fetchone()
    assert factors > 1
    assert rows >= int(dates * factors * 0.95)
    assert duplicates == 0
    assert null_keys == 0


def test_backtesting_contains_only_baseline_observations_and_valid_derivations() -> None:
    source = pd.read_parquet(SENSITIVITY_PATH)
    source.columns = [str(column).strip().lower() for column in source.columns]
    expected_rows = int(baseline_mask(source).sum())

    with duckdb.connect(str(DATABASE_PATH), read_only=True) as connection:
        actual_rows, null_required, invalid_flags, formula_errors = connection.execute(
            """
            SELECT
                COUNT(*) AS actual_rows,
                SUM(CASE WHEN valuation_date IS NULL OR member_id IS NULL OR margin_amount IS NULL OR realized_loss IS NULL OR exception_flag IS NULL OR margin_shortfall IS NULL THEN 1 ELSE 0 END) AS null_required,
                SUM(CASE WHEN exception_flag NOT IN (0, 1) THEN 1 ELSE 0 END) AS invalid_flags,
                SUM(CASE
                    WHEN exception_flag <> CASE WHEN realized_loss > margin_amount THEN 1 ELSE 0 END
                      OR ABS(margin_shortfall - GREATEST(realized_loss - margin_amount, 0.0)) > 1e-9
                    THEN 1 ELSE 0 END) AS formula_errors
            FROM backtesting_results
            """
        ).fetchone()
    assert actual_rows == expected_rows
    assert null_required == 0
    assert invalid_flags == 0
    assert formula_errors == 0


def test_monitoring_metrics_are_legitimate_step17_outputs() -> None:
    required_metric_names = {
        "system_margin_daily_pct_change",
        "system_margin_weekly_pct_change",
        "system_peak_to_trough_margin_decline",
        "system_stressed_to_calm_margin_ratio",
        "system_margin_realized_volatility_correlation",
        "system_margin_change_market_loss_correlation",
        "system_margin_call_volatility",
    }
    with duckdb.connect(str(DATABASE_PATH), read_only=True) as connection:
        count = int(connection.execute("SELECT COUNT(*) FROM monitoring_metrics").fetchone()[0])
        metric_names = {row[0] for row in connection.execute("SELECT DISTINCT metric_name FROM monitoring_metrics").fetchall()}
        sources = {row[0] for row in connection.execute("SELECT DISTINCT source_table FROM monitoring_metrics").fetchall()}
        null_core = int(
            connection.execute(
                "SELECT COUNT(*) FROM monitoring_metrics WHERE metric_date IS NULL OR metric_name IS NULL OR status IS NULL OR source_table IS NULL"
            ).fetchone()[0]
        )
    assert count > 0
    assert required_metric_names.issubset(metric_names)
    assert sources.issubset({"procyclicality_margin_history", "sensitivity_scenario_results"})
    assert null_core == 0


def test_required_exception_query_executes() -> None:
    query = """
        SELECT
            member_id,
            COUNT(*) AS exceptions,
            SUM(margin_shortfall) AS total_shortfall
        FROM backtesting_results
        WHERE exception_flag = 1
        GROUP BY member_id
        ORDER BY total_shortfall DESC
    """
    with duckdb.connect(str(DATABASE_PATH), read_only=True) as connection:
        connection.execute(query).fetchall()

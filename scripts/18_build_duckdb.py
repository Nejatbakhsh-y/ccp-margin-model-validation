
"""Build the deterministic Step 18 DuckDB SQL layer.

Unlike the original discovery-based loader, this implementation uses explicit,
validated source mappings.  It performs required transformations for wide
risk-factor returns, baseline backtesting observations, sensitivity results,
and Step 17 monitoring metrics.
"""

from __future__ import annotations

import csv
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = PROJECT_ROOT / "sql"
DATABASE_DIR = PROJECT_ROOT / "data" / "database"
REPORT_DIR = PROJECT_ROOT / "reports" / "sql"
DATABASE_PATH = DATABASE_DIR / "ccp_margin_validation.duckdb"

SOURCE_PATHS = {
    "market_prices": PROJECT_ROOT / "data" / "processed" / "market_prices_clean.parquet",
    "risk_factor_returns": PROJECT_ROOT / "data" / "processed" / "log_returns_wide.parquet",
    "member_positions": PROJECT_ROOT / "data" / "processed" / "clearing_member_positions.parquet",
    "portfolio_exposures": PROJECT_ROOT / "data" / "processed" / "portfolio_exposures.parquet",
    "daily_margin": PROJECT_ROOT / "data" / "processed" / "daily_member_margin.parquet",
    "backtesting_results": PROJECT_ROOT / "data" / "processed" / "sensitivity_scenario_results.parquet",
    "stress_results": PROJECT_ROOT / "data" / "processed" / "stress_test_results.parquet",
    "sensitivity_results": PROJECT_ROOT / "data" / "processed" / "sensitivity_scenario_results.parquet",
    "monitoring_metrics": PROJECT_ROOT / "data" / "processed" / "procyclicality_monitoring_metrics.csv",
    "validation_findings": PROJECT_ROOT / "reports" / "evidence" / "findings" / "finding_register.csv",
}

REQUIRED_TABLES = list(SOURCE_PATHS)
EXPECTED_NONEMPTY = set(REQUIRED_TABLES) - {"validation_findings"}

ALIASES: dict[str, tuple[str, ...]] = {
    "valuation_date": ("date", "as_of_date", "business_date", "test_date", "observation_date"),
    "metric_date": ("date", "valuation_date", "as_of_date", "observation_date"),
    "finding_date": ("date_identified", "identified_date", "date", "issue_date", "created_date"),
    "due_date": ("target_completion_date", "target_date", "remediation_due_date", "closure_due_date"),
    "security_id": ("ticker", "symbol", "asset_id", "instrument_id", "risk_factor_id"),
    "risk_factor_id": ("security_id", "ticker", "symbol", "factor_id", "asset_id"),
    "adjusted_close": ("adj_close", "adjclose", "adjusted_price", "close_adjusted", "price"),
    "price": ("close", "adjusted_close", "adj_close", "market_price", "current_price"),
    "volume": ("trading_volume", "daily_volume", "adv", "average_daily_volume"),
    "source": ("data_source", "provider"),
    "member_id": ("clearing_member_id", "cm_id", "member", "participant_id"),
    "portfolio_id": ("account_id", "portfolio", "book_id"),
    "quantity": ("position_quantity", "shares", "units", "notional_quantity"),
    "market_value": ("position_value", "notional", "market_exposure", "exposure"),
    "long_short_flag": ("side", "position_side", "long_short", "direction"),
    "sector": ("industry_sector", "gics_sector"),
    "asset_class": ("asset_type", "product_type", "instrument_type"),
    "liquidity_bucket": ("liquidity_class", "liquidity_tier", "liquidity_category"),
    "gross_exposure": ("gross_market_value", "gross_notional", "gross_value", "absolute_notional"),
    "net_exposure": ("net_market_value", "net_notional", "net_value", "signed_notional"),
    "long_exposure": ("long_market_value", "long_notional", "long_value"),
    "short_exposure": ("short_market_value", "short_notional", "short_value"),
    "top_position_weight": ("largest_position_weight", "largest_single_name_weight", "max_position_weight", "top_weight", "position_weight"),
    "concentration_hhi": ("hhi", "herfindahl_index", "concentration_index"),
    "illiquid_exposure": ("illiquid_market_value", "low_liquidity_exposure", "illiquid_notional"),
    "leverage_ratio": ("leverage", "gross_to_net_ratio"),
    "scenario_id": ("stress_scenario_id", "sensitivity_scenario_id", "scenario"),
    "scenario_name": ("stress_scenario_name", "scenario_description", "scenario_label", "scenario_id"),
    "stressed_loss": ("stress_loss", "scenario_loss", "loss_under_stress", "loss"),
    "available_margin": ("margin_available", "total_initial_margin", "initial_margin", "margin_amount", "margin", "total_margin"),
    "margin_shortfall": ("shortfall", "margin_deficit", "uncovered_loss"),
    "breach_flag": ("stress_breach", "is_breach", "exception_flag", "breach"),
    "metric_name": ("metric", "measure_name", "monitoring_measure"),
    "metric_value": ("value", "measure_value", "result", "current_result"),
    "threshold_value": ("threshold", "limit_value", "trigger_value", "warning_threshold"),
    "status": ("result_status", "finding_status", "traffic_light", "rating", "current_status", "current_classification"),
    "source_table": ("source", "data_source", "origin"),
    "details": ("description", "notes", "comment", "monitoring_objective"),
    "finding_id": ("issue_id", "validation_finding_id", "id"),
    "test_name": ("validation_test", "test", "finding_type", "affected_component"),
    "finding_scope": ("scope", "member_scope", "model_scope", "affected_component", "affected_portfolios"),
    "severity": ("risk_rating", "priority", "finding_severity"),
    "finding": ("finding_title", "issue", "finding_description", "observation"),
    "evidence": ("remediation_evidence_reference", "supporting_evidence", "evidence_reference"),
    "recommendation": ("recommended_action", "remediation", "action"),
    "finding_owner": ("responsible_owner", "owner", "assigned_to", "responsible_party"),
}


@dataclass(frozen=True)
class LoadRecord:
    table_name: str
    source_file: str
    source_rows: int
    loaded_rows: int
    status: str
    matched_columns: int
    missing_columns: str


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def qid(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def qlit(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def read_sql(filename: str) -> str:
    path = SQL_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Required SQL file not found: {path}")
    return path.read_text(encoding="utf-8")


def table_columns(connection: duckdb.DuckDBPyConnection, table_name: str) -> list[tuple[str, str]]:
    rows = connection.execute(f"PRAGMA table_info({qlit(table_name)})").fetchall()
    return [(str(row[1]), str(row[2])) for row in rows if str(row[1]) != "loaded_at"]


def create_raw_view(connection: duckdb.DuckDBPyConnection, table_name: str, source_path: Path) -> tuple[str, int, dict[str, str]]:
    view_name = f"raw_{table_name}"
    source_sql = qlit(source_path.resolve().as_posix())
    if source_path.suffix.lower() == ".parquet":
        reader = f"read_parquet({source_sql}, union_by_name=true)"
    else:
        reader = f"read_csv_auto({source_sql}, header=true, union_by_name=true, ignore_errors=true, sample_size=-1)"
    connection.execute(f"CREATE OR REPLACE TEMP VIEW {qid(view_name)} AS SELECT * FROM {reader}")
    source_rows = int(connection.execute(f"SELECT COUNT(*) FROM {qid(view_name)}").fetchone()[0])
    columns = [str(row[0]) for row in connection.execute(f"DESCRIBE SELECT * FROM {qid(view_name)}").fetchall()]
    return view_name, source_rows, {normalize(column): column for column in columns}


def find_column(lookup: dict[str, str], target: str, *extra_aliases: str) -> str | None:
    for candidate in (target,) + ALIASES.get(target, ()) + extra_aliases:
        actual = lookup.get(normalize(candidate))
        if actual is not None:
            return actual
    return None


def cast_column(lookup: dict[str, str], target: str, data_type: str, *extra_aliases: str) -> str | None:
    actual = find_column(lookup, target, *extra_aliases)
    return f"TRY_CAST({qid(actual)} AS {data_type})" if actual else None


def create_generic_stage(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    source_path: Path,
    derive: Callable[[str, str, dict[str, str]], str | None] | None = None,
) -> tuple[int, int, list[str]]:
    raw_view, source_rows, lookup = create_raw_view(connection, table_name, source_path)
    expressions: list[str] = []
    missing: list[str] = []
    matched = 0

    for target, data_type in table_columns(connection, table_name):
        expression = cast_column(lookup, target, data_type)
        if expression is None and derive is not None:
            expression = derive(target, data_type, lookup)
        if expression is None:
            expression = f"CAST(NULL AS {data_type})"
            missing.append(target)
        else:
            matched += 1
        expressions.append(f"{expression} AS {qid(target)}")

    connection.execute(
        f"CREATE OR REPLACE TEMP VIEW {qid('stg_' + table_name)} AS "
        f"SELECT {', '.join(expressions)} FROM {qid(raw_view)}"
    )
    return source_rows, matched, missing


def market_derivation(source_path: Path) -> Callable[[str, str, dict[str, str]], str | None]:
    def derive(target: str, data_type: str, lookup: dict[str, str]) -> str | None:
        if target == "source":
            return f"CAST({qlit(source_path.name)} AS {data_type})"
        if target == "adjusted_close":
            return cast_column(lookup, "price", data_type)
        if target == "price":
            return cast_column(lookup, "adjusted_close", data_type)
        return None
    return derive


def exposure_derivation(target: str, data_type: str, lookup: dict[str, str]) -> str | None:
    member = find_column(lookup, "member_id")
    signed = find_column(lookup, "net_exposure", "signed_notional")
    gross = find_column(lookup, "gross_exposure", "absolute_notional")
    if target == "portfolio_id" and member:
        return f"TRY_CAST({qid(member)} AS {data_type})"
    if target == "long_exposure" and signed:
        return f"TRY_CAST(CASE WHEN TRY_CAST({qid(signed)} AS DOUBLE) > 0 THEN TRY_CAST({qid(signed)} AS DOUBLE) ELSE 0 END AS {data_type})"
    if target == "short_exposure" and signed:
        return f"TRY_CAST(CASE WHEN TRY_CAST({qid(signed)} AS DOUBLE) < 0 THEN ABS(TRY_CAST({qid(signed)} AS DOUBLE)) ELSE 0 END AS {data_type})"
    if target == "leverage_ratio" and gross and signed:
        return (
            f"TRY_CAST(CASE WHEN ABS(TRY_CAST({qid(signed)} AS DOUBLE)) = 0 THEN NULL "
            f"ELSE TRY_CAST({qid(gross)} AS DOUBLE) / ABS(TRY_CAST({qid(signed)} AS DOUBLE)) END AS {data_type})"
        )
    return None


def stress_derivation(target: str, data_type: str, lookup: dict[str, str]) -> str | None:
    member = find_column(lookup, "member_id")
    portfolio = find_column(lookup, "portfolio_id")
    scenario_id = find_column(lookup, "scenario_id")
    loss = find_column(lookup, "stressed_loss")
    margin = find_column(lookup, "available_margin")
    if target == "member_id" and portfolio:
        return f"TRY_CAST({qid(portfolio)} AS {data_type})"
    if target == "portfolio_id" and member:
        return f"TRY_CAST({qid(member)} AS {data_type})"
    if target == "scenario_name" and scenario_id:
        return f"TRY_CAST({qid(scenario_id)} AS {data_type})"
    if target == "margin_shortfall" and loss and margin:
        return f"TRY_CAST(GREATEST(TRY_CAST({qid(loss)} AS DOUBLE) - TRY_CAST({qid(margin)} AS DOUBLE), 0.0) AS {data_type})"
    if target == "breach_flag" and loss and margin:
        return f"CAST(CASE WHEN TRY_CAST({qid(loss)} AS DOUBLE) > TRY_CAST({qid(margin)} AS DOUBLE) THEN 1 ELSE 0 END AS {data_type})"
    return None


def findings_derivation(target: str, data_type: str, lookup: dict[str, str]) -> str | None:
    if target == "recommendation":
        remediation = find_column(lookup, "management_response", "management_response_received")
        return f"TRY_CAST({qid(remediation)} AS {data_type})" if remediation else None
    return None


def create_risk_return_stage(connection: duckdb.DuckDBPyConnection, source_path: Path) -> tuple[int, int, list[str]]:
    raw_view, source_rows, lookup = create_raw_view(connection, "risk_factor_returns", source_path)
    date_column = find_column(lookup, "valuation_date")
    if date_column is None:
        raise ValueError("log_returns_wide.parquet has no date column.")

    raw_columns = [str(row[0]) for row in connection.execute(f"DESCRIBE SELECT * FROM {qid(raw_view)}").fetchall()]
    factor_columns = [column for column in raw_columns if normalize(column) != normalize(date_column)]
    if not factor_columns:
        raise ValueError("log_returns_wide.parquet contains no risk-factor columns.")

    union_parts = [
        (
            f"SELECT TRY_CAST({qid(date_column)} AS DATE) AS valuation_date, "
            f"{qlit(column)} AS risk_factor_id, {qlit(column)} AS security_id, "
            f"TRY_CAST({qid(column)} AS DOUBLE) AS log_return_1d FROM {qid(raw_view)}"
        )
        for column in factor_columns
    ]
    union_sql = " UNION ALL ".join(union_parts)

    connection.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW stg_risk_factor_returns AS
        WITH long_returns AS (
            {union_sql}
        ), calculated AS (
            SELECT
                valuation_date,
                risk_factor_id,
                security_id,
                log_return_1d,
                COUNT(log_return_1d) OVER w3 AS count_3d,
                SUM(log_return_1d) OVER w3 AS sum_log_3d,
                COUNT(log_return_1d) OVER w5 AS count_5d,
                SUM(log_return_1d) OVER w5 AS sum_log_5d
            FROM long_returns
            WINDOW
                w3 AS (PARTITION BY risk_factor_id ORDER BY valuation_date ROWS BETWEEN 2 PRECEDING AND CURRENT ROW),
                w5 AS (PARTITION BY risk_factor_id ORDER BY valuation_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW)
        )
        SELECT
            valuation_date,
            risk_factor_id,
            security_id,
            EXP(log_return_1d) - 1.0 AS return_1d,
            CASE WHEN count_3d = 3 THEN EXP(sum_log_3d) - 1.0 ELSE NULL END AS return_3d,
            CASE WHEN count_5d = 5 THEN EXP(sum_log_5d) - 1.0 ELSE NULL END AS return_5d,
            log_return_1d
        FROM calculated
        WHERE valuation_date IS NOT NULL AND log_return_1d IS NOT NULL
        """
    )
    return source_rows, 7, []


def create_daily_margin_stage(connection: duckdb.DuckDBPyConnection, source_path: Path) -> tuple[int, int, list[str]]:
    raw_view, source_rows, lookup = create_raw_view(connection, "daily_margin", source_path)

    def required(target: str, data_type: str, *aliases: str) -> str:
        expression = cast_column(lookup, target, data_type, *aliases)
        if expression is None:
            raise ValueError(f"daily_member_margin.parquet is missing required field for {target}.")
        return expression

    date = required("valuation_date", "DATE")
    member = required("member_id", "VARCHAR")
    portfolio_actual = find_column(lookup, "portfolio_id")
    portfolio = f"TRY_CAST({qid(portfolio_actual)} AS VARCHAR)" if portfolio_actual else member
    model_actual = find_column(lookup, "model_name")
    model = f"TRY_CAST({qid(model_actual)} AS VARCHAR)" if model_actual else "'primary_historical_simulation'"
    mpor = required("mpor_days", "INTEGER", "primary_mpor_days")
    confidence_actual = find_column(lookup, "confidence_level")
    confidence = f"TRY_CAST({qid(confidence_actual)} AS DOUBLE)" if confidence_actual else "CAST(0.99 AS DOUBLE)"

    mappings = {
        "base_var": required("base_var", "DOUBLE"),
        "liquidity_addon": required("liquidity_addon", "DOUBLE"),
        "concentration_addon": required("concentration_addon", "DOUBLE"),
        "gap_risk_addon": required("gap_risk_addon", "DOUBLE"),
        "stress_buffer": required("stress_buffer", "DOUBLE"),
        "total_initial_margin": required("total_initial_margin", "DOUBLE", "total_margin"),
    }
    realized_actual = find_column(lookup, "realized_loss")
    realized = f"TRY_CAST({qid(realized_actual)} AS DOUBLE)" if realized_actual else "CAST(NULL AS DOUBLE)"

    connection.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW stg_daily_margin AS
        SELECT
            {date} AS valuation_date,
            {member} AS member_id,
            {portfolio} AS portfolio_id,
            {model} AS model_name,
            {mpor} AS mpor_days,
            {confidence} AS confidence_level,
            {mappings['base_var']} AS base_var,
            {mappings['liquidity_addon']} AS liquidity_addon,
            {mappings['concentration_addon']} AS concentration_addon,
            {mappings['gap_risk_addon']} AS gap_risk_addon,
            {mappings['stress_buffer']} AS stress_buffer,
            {mappings['total_initial_margin']} AS total_initial_margin,
            {realized} AS realized_loss
        FROM {qid(raw_view)}
        """
    )
    missing = [] if realized_actual else ["realized_loss"]
    return source_rows, 13 - len(missing), missing


def baseline_filter(lookup: dict[str, str]) -> str:
    conditions: list[str] = []
    is_baseline = find_column(lookup, "is_baseline")
    scenario_id = find_column(lookup, "scenario_id")
    if is_baseline:
        conditions.append(
            f"(TRY_CAST({qid(is_baseline)} AS BOOLEAN) = TRUE OR LOWER(TRIM(CAST({qid(is_baseline)} AS VARCHAR))) IN ('true','1','yes','y','baseline'))"
        )
    if scenario_id:
        conditions.append(f"LOWER(TRIM(CAST({qid(scenario_id)} AS VARCHAR))) = 'baseline'")
    if not conditions:
        raise ValueError("Sensitivity results have neither is_baseline nor scenario_id for baseline selection.")
    return "(" + " OR ".join(conditions) + ")"


def create_backtesting_stage(connection: duckdb.DuckDBPyConnection, source_path: Path) -> tuple[int, int, list[str]]:
    raw_view, source_rows, lookup = create_raw_view(connection, "backtesting_results", source_path)
    date = cast_column(lookup, "valuation_date", "DATE")
    member = cast_column(lookup, "member_id", "VARCHAR")
    margin = cast_column(lookup, "margin_amount", "DOUBLE", "margin")
    realized = cast_column(lookup, "realized_loss", "DOUBLE")
    if None in {date, member, margin, realized}:
        raise ValueError("Sensitivity results do not contain date, member_id, margin, and realized_loss for backtesting.")

    portfolio_actual = find_column(lookup, "portfolio_id")
    portfolio = f"TRY_CAST({qid(portfolio_actual)} AS VARCHAR)" if portfolio_actual else member
    model_actual = find_column(lookup, "model_name")
    model = f"TRY_CAST({qid(model_actual)} AS VARCHAR)" if model_actual else "'primary_historical_simulation'"
    mpor_actual = find_column(lookup, "mpor_days")
    mpor = f"TRY_CAST({qid(mpor_actual)} AS INTEGER)" if mpor_actual else "CAST(1 AS INTEGER)"
    confidence_actual = find_column(lookup, "confidence_level")
    confidence = f"TRY_CAST({qid(confidence_actual)} AS DOUBLE)" if confidence_actual else "CAST(0.99 AS DOUBLE)"
    where = baseline_filter(lookup)

    connection.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW stg_backtesting_results AS
        SELECT
            {date} AS valuation_date,
            {member} AS member_id,
            {portfolio} AS portfolio_id,
            {model} AS model_name,
            {mpor} AS mpor_days,
            {confidence} AS confidence_level,
            {margin} AS margin_amount,
            {realized} AS realized_loss,
            CAST(CASE WHEN {realized} > {margin} THEN 1 ELSE 0 END AS INTEGER) AS exception_flag,
            GREATEST({realized} - {margin}, 0.0) AS margin_shortfall
        FROM {qid(raw_view)}
        WHERE {where}
          AND {date} IS NOT NULL
          AND {member} IS NOT NULL
          AND {margin} IS NOT NULL
          AND {realized} IS NOT NULL
        """
    )
    return source_rows, 10, []


def parameter_case(alias: str, lookup: dict[str, str]) -> str:
    parameter = find_column(lookup, "parameter_name", "parameter")
    if parameter is None:
        return "CAST(NULL AS DOUBLE)"
    pairs = [
        ("confidence_level", "confidence_level"),
        ("lookback_days", "lookback_days"),
        ("mpor_days", "mpor_days"),
        ("ewma_lambda", "ewma_lambda"),
        ("concentration_threshold", "concentration_threshold"),
        ("liquidity_threshold_adv", "liquidity_threshold_adv"),
        ("stress_buffer", "stress_buffer"),
        ("correlation_shock", "correlation_shock"),
    ]
    clauses: list[str] = []
    for parameter_name, column_name in pairs:
        actual = find_column(lookup, column_name)
        if actual:
            clauses.append(
                f"WHEN LOWER(TRIM(CAST(s.{qid(parameter)} AS VARCHAR))) = {qlit(parameter_name)} THEN TRY_CAST({alias}.{qid(actual)} AS DOUBLE)"
            )
    if not clauses:
        return "CAST(NULL AS DOUBLE)"
    return "CASE " + " ".join(clauses) + " ELSE NULL END"


def create_sensitivity_stage(connection: duckdb.DuckDBPyConnection, source_path: Path) -> tuple[int, int, list[str]]:
    raw_view, source_rows, lookup = create_raw_view(connection, "sensitivity_results", source_path)
    date_actual = find_column(lookup, "valuation_date")
    member_actual = find_column(lookup, "member_id")
    scenario_actual = find_column(lookup, "scenario_id")
    parameter_actual = find_column(lookup, "parameter_name", "parameter")
    parameter_value_actual = find_column(lookup, "shocked_value", "parameter_value")
    margin_actual = find_column(lookup, "shocked_margin", "margin")
    if not all([date_actual, member_actual, scenario_actual, parameter_actual, margin_actual]):
        raise ValueError("Sensitivity source lacks required date/member/scenario/parameter/margin columns.")

    where = baseline_filter(lookup)
    portfolio_actual = find_column(lookup, "portfolio_id")
    portfolio_expr = f"TRY_CAST(s.{qid(portfolio_actual)} AS VARCHAR)" if portfolio_actual else f"TRY_CAST(s.{qid(member_actual)} AS VARCHAR)"
    shocked_value_expr = f"TRY_CAST(s.{qid(parameter_value_actual)} AS DOUBLE)" if parameter_value_actual else parameter_case("s", lookup)
    baseline_value_expr = parameter_case("b", lookup)

    connection.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW stg_sensitivity_results AS
        WITH source_data AS (
            SELECT * FROM {qid(raw_view)}
        ), baseline AS (
            SELECT *
            FROM source_data
            WHERE {where.replace(qid(find_column(lookup, 'is_baseline') or '__missing__'), qid(find_column(lookup, 'is_baseline') or '__missing__'))}
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY TRY_CAST({qid(date_actual)} AS DATE), TRY_CAST({qid(member_actual)} AS VARCHAR)
                ORDER BY TRY_CAST({qid(margin_actual)} AS DOUBLE) DESC NULLS LAST
            ) = 1
        )
        SELECT
            TRY_CAST(s.{qid(date_actual)} AS DATE) AS valuation_date,
            TRY_CAST(s.{qid(member_actual)} AS VARCHAR) AS member_id,
            {portfolio_expr} AS portfolio_id,
            TRY_CAST(s.{qid(scenario_actual)} AS VARCHAR) AS scenario_id,
            TRY_CAST(s.{qid(parameter_actual)} AS VARCHAR) AS parameter_name,
            {baseline_value_expr} AS baseline_value,
            {shocked_value_expr} AS shocked_value,
            TRY_CAST(b.{qid(margin_actual)} AS DOUBLE) AS baseline_margin,
            TRY_CAST(s.{qid(margin_actual)} AS DOUBLE) AS shocked_margin,
            TRY_CAST(s.{qid(margin_actual)} AS DOUBLE) - TRY_CAST(b.{qid(margin_actual)} AS DOUBLE) AS absolute_change,
            CASE
                WHEN TRY_CAST(b.{qid(margin_actual)} AS DOUBLE) = 0 THEN NULL
                ELSE TRY_CAST(s.{qid(margin_actual)} AS DOUBLE) / TRY_CAST(b.{qid(margin_actual)} AS DOUBLE) - 1.0
            END AS pct_change
        FROM source_data s
        LEFT JOIN baseline b
          ON TRY_CAST(s.{qid(date_actual)} AS DATE) = TRY_CAST(b.{qid(date_actual)} AS DATE)
         AND TRY_CAST(s.{qid(member_actual)} AS VARCHAR) = TRY_CAST(b.{qid(member_actual)} AS VARCHAR)
        WHERE TRY_CAST(s.{qid(date_actual)} AS DATE) IS NOT NULL
          AND TRY_CAST(s.{qid(member_actual)} AS VARCHAR) IS NOT NULL
        """
    )
    return source_rows, 11, []


def write_manifest(records: list[LoadRecord]) -> None:
    path = REPORT_DIR / "load_manifest.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["table_name", "source_file", "source_rows", "loaded_rows", "status", "matched_columns", "missing_columns"])
        for record in records:
            writer.writerow([
                record.table_name,
                record.source_file,
                record.source_rows,
                record.loaded_rows,
                record.status,
                record.matched_columns,
                record.missing_columns,
            ])


def export_query(connection: duckdb.DuckDBPyConnection, query: str, filename: str) -> None:
    output = (REPORT_DIR / filename).resolve().as_posix()
    connection.execute(f"COPY ({query}) TO {qlit(output)} (FORMAT CSV, HEADER TRUE)")


def validate_sources() -> None:
    missing = [str(path.relative_to(PROJECT_ROOT)) for path in SOURCE_PATHS.values() if not path.exists()]
    if missing:
        raise FileNotFoundError("Required Step 18 sources are missing:\n  " + "\n  ".join(missing))


def main() -> int:
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    validate_sources()

    if DATABASE_PATH.exists():
        DATABASE_PATH.unlink()
    wal_path = Path(str(DATABASE_PATH) + ".wal")
    if wal_path.exists():
        wal_path.unlink()

    records: list[LoadRecord] = []
    details: dict[str, tuple[int, int, list[str]]] = {}

    print(f"Project root: {PROJECT_ROOT}")
    print(f"DuckDB file:  {DATABASE_PATH}")

    with duckdb.connect(str(DATABASE_PATH)) as connection:
        connection.execute(read_sql("schema.sql"))

        details["market_prices"] = create_generic_stage(
            connection,
            "market_prices",
            SOURCE_PATHS["market_prices"],
            market_derivation(SOURCE_PATHS["market_prices"]),
        )
        details["risk_factor_returns"] = create_risk_return_stage(connection, SOURCE_PATHS["risk_factor_returns"])
        details["member_positions"] = create_generic_stage(connection, "member_positions", SOURCE_PATHS["member_positions"])
        details["portfolio_exposures"] = create_generic_stage(
            connection,
            "portfolio_exposures",
            SOURCE_PATHS["portfolio_exposures"],
            exposure_derivation,
        )
        details["daily_margin"] = create_daily_margin_stage(connection, SOURCE_PATHS["daily_margin"])
        details["backtesting_results"] = create_backtesting_stage(connection, SOURCE_PATHS["backtesting_results"])
        details["stress_results"] = create_generic_stage(
            connection,
            "stress_results",
            SOURCE_PATHS["stress_results"],
            stress_derivation,
        )
        details["sensitivity_results"] = create_sensitivity_stage(connection, SOURCE_PATHS["sensitivity_results"])
        details["monitoring_metrics"] = create_generic_stage(connection, "monitoring_metrics", SOURCE_PATHS["monitoring_metrics"])
        details["validation_findings"] = create_generic_stage(
            connection,
            "validation_findings",
            SOURCE_PATHS["validation_findings"],
            findings_derivation,
        )

        connection.execute(read_sql("load_processed_data.sql"))
        connection.execute(read_sql("validation_queries.sql"))
        connection.execute(read_sql("monitoring_queries.sql"))

        for table_name in REQUIRED_TABLES:
            source_rows, matched, missing = details[table_name]
            loaded_rows = int(connection.execute(f"SELECT COUNT(*) FROM {qid(table_name)}").fetchone()[0])
            if table_name in EXPECTED_NONEMPTY and loaded_rows == 0:
                raise ValueError(f"Required table {table_name} loaded zero rows.")
            records.append(
                LoadRecord(
                    table_name=table_name,
                    source_file=str(SOURCE_PATHS[table_name].relative_to(PROJECT_ROOT)),
                    source_rows=source_rows,
                    loaded_rows=loaded_rows,
                    status="LOADED",
                    matched_columns=matched,
                    missing_columns="|".join(missing),
                )
            )

        export_query(connection, "SELECT * FROM v_member_exception_summary ORDER BY total_shortfall DESC NULLS LAST", "member_exception_summary.csv")
        export_query(connection, "SELECT * FROM v_model_backtesting_summary ORDER BY model_name, mpor_days", "model_backtesting_summary.csv")
        export_query(connection, "SELECT * FROM v_stress_breach_summary ORDER BY aggregate_shortfall DESC NULLS LAST", "stress_breach_summary.csv")
        export_query(connection, "SELECT * FROM v_sensitivity_largest_movements ORDER BY absolute_pct_change DESC NULLS LAST LIMIT 250", "sensitivity_largest_movements.csv")
        export_query(connection, "SELECT * FROM v_margin_jump_counts ORDER BY jumps_over_30pct DESC, jumps_over_20pct DESC", "margin_jump_counts.csv")
        export_query(connection, "SELECT * FROM v_member_margin_volatility ORDER BY margin_change_volatility DESC NULLS LAST", "member_margin_volatility.csv")
        export_query(connection, "SELECT * FROM v_open_validation_findings ORDER BY severity, due_date", "open_validation_findings.csv")

        write_manifest(records)

        result_rows = connection.execute(
            """
            SELECT member_id, COUNT(*) AS exceptions, SUM(margin_shortfall) AS total_shortfall
            FROM backtesting_results
            WHERE exception_flag = 1
            GROUP BY member_id
            ORDER BY total_shortfall DESC
            """
        ).fetchall()

        print("\nLoad summary")
        print("------------")
        for record in records:
            print(f"{record.table_name:24s} {record.loaded_rows:12,d} rows  {record.source_file}")
        print(f"\nRequired exception query executed successfully ({len(result_rows)} result rows).")
        print(f"Load manifest: {REPORT_DIR / 'load_manifest.csv'}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[ERROR] Step 18 pipeline failed: {exc}", file=sys.stderr)
        raise

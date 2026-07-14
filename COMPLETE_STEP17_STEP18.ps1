param(
    [switch]$SkipGit
)

$ErrorActionPreference = "Stop"
if (Test-Path Variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}
$ProjectRoot = "C:\Users\nejat\OneDrive\Desktop\UN\Skills\GitHub 2026\ccp-margin-model-validation"
Set-Location $ProjectRoot

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host ("=" * 100)
    Write-Host $Title
    Write-Host ("=" * 100)
}

function Assert-LastExitCode {
    param([string]$Action)
    if ($LASTEXITCODE -ne 0) {
        throw "$Action failed with exit code $LASTEXITCODE."
    }
}

Write-Section "STEP 17 AND STEP 18 AUTOMATION"
Write-Host "Project root: $ProjectRoot"

if (-not (Test-Path ".git")) {
    throw "The project root is not a Git repository: $ProjectRoot"
}

$RequiredSqlFiles = @(
    "sql\schema.sql",
    "sql\load_processed_data.sql",
    "sql\validation_queries.sql",
    "sql\monitoring_queries.sql"
)
foreach ($File in $RequiredSqlFiles) {
    if (-not (Test-Path $File)) {
        throw "Required SQL file is missing: $File"
    }
}

$RequiredInputFiles = @(
    "data\processed\market_prices_clean.parquet",
    "data\processed\log_returns_wide.parquet",
    "data\processed\clearing_member_positions.parquet",
    "data\processed\portfolio_exposures.parquet",
    "data\processed\daily_member_margin.parquet",
    "data\processed\sensitivity_scenario_results.parquet",
    "data\processed\stress_test_results.parquet"
)
foreach ($File in $RequiredInputFiles) {
    if (-not (Test-Path $File)) {
        throw "Required processed-data input is missing: $File"
    }
}

Write-Section "BACK UP CURRENT STEP 17 AND STEP 18 FILES"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupRoot = Join-Path $ProjectRoot "reports\evidence\archive\step17_step18_before_fix_$Timestamp"
New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null

$BackupFiles = @(
    "scripts\17_generate_procyclicality_results.py",
    "scripts\18_build_duckdb.py",
    "tests\test_sql_pipeline.py",
    "STEP18_RUN.ps1",
    "reports\sql\load_manifest.csv",
    "data\database\ccp_margin_validation.duckdb"
)
foreach ($File in $BackupFiles) {
    if (Test-Path $File) {
        $Destination = Join-Path $BackupRoot $File
        New-Item -ItemType Directory -Path (Split-Path $Destination -Parent) -Force | Out-Null
        Copy-Item $File $Destination -Force
        Write-Host "Backed up: $File"
    }
}

Write-Section "PREPARE DIRECTORIES AND THE FINDINGS REGISTER"
$Directories = @(
    "scripts",
    "tests",
    "data\processed",
    "data\database",
    "reports\evidence",
    "reports\evidence\findings",
    "reports\sql"
)
foreach ($Directory in $Directories) {
    New-Item -ItemType Directory -Path $Directory -Force | Out-Null
}

$FindingRegister = "reports\evidence\findings\finding_register.csv"
if (-not (Test-Path $FindingRegister)) {
    $FindingHeader = "finding_id,finding_title,severity,affected_component,date_identified,responsible_owner,target_completion_date,current_status,management_response_received,remediation_evidence_reference"
    Set-Content -Path $FindingRegister -Value $FindingHeader -Encoding utf8
    Write-Host "Created an empty governed findings register: $FindingRegister"
}

Write-Section "CREATE THE STEP 17 GENERATOR"
$Step17Code = @'

"""Generate Step 17 procyclicality and monitoring evidence.

The generator uses the empirical baseline observations contained in
``data/processed/sensitivity_scenario_results.parquet``.  It produces a
member/date margin history, member-level and system-level procyclicality
metrics, scenario-variant comparisons, buffer-depletion/replenishment events,
and a normalized monitoring feed for the Step 18 DuckDB layer.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = PROJECT_ROOT / "data" / "processed" / "sensitivity_scenario_results.parquet"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
EVIDENCE_DIR = PROJECT_ROOT / "reports" / "evidence"

HISTORY_PATH = PROCESSED_DIR / "procyclicality_margin_history.parquet"
MONITORING_PATH = PROCESSED_DIR / "procyclicality_monitoring_metrics.csv"
MEMBER_METRICS_PATH = EVIDENCE_DIR / "procyclicality_member_metrics.csv"
SYSTEM_METRICS_PATH = EVIDENCE_DIR / "procyclicality_system_metrics.csv"
VARIANT_PATH = EVIDENCE_DIR / "procyclicality_variant_comparison.csv"
BUFFER_EVENTS_PATH = EVIDENCE_DIR / "procyclicality_buffer_events.csv"
SUMMARY_PATH = EVIDENCE_DIR / "procyclicality_summary.md"


REQUIRED_COLUMNS = {"date", "member_id", "margin", "realized_loss"}


def as_bool(series: pd.Series) -> pd.Series:
    """Convert common true/false representations to a Boolean mask."""
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    normalized = series.astype("string").str.strip().str.lower()
    return normalized.isin({"true", "1", "yes", "y", "baseline"})


def safe_corr(left: pd.Series, right: pd.Series) -> float:
    """Return a finite Pearson correlation when enough data exist."""
    pair = pd.concat(
        [pd.to_numeric(left, errors="coerce"), pd.to_numeric(right, errors="coerce")],
        axis=1,
    ).dropna()
    if len(pair) < 3:
        return math.nan
    if pair.iloc[:, 0].nunique() < 2 or pair.iloc[:, 1].nunique() < 2:
        return math.nan
    return float(pair.iloc[:, 0].corr(pair.iloc[:, 1]))


def finite_or_nan(value: Any) -> float:
    """Convert a scalar to float, retaining unavailable results as NaN."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return math.nan
    return result if math.isfinite(result) else math.nan


def status_for(metric_name: str, value: float) -> tuple[float | None, str, str]:
    """Return warning threshold, status, and threshold interpretation."""
    if not math.isfinite(value):
        return None, "NOT_AVAILABLE", "Insufficient observations for this metric."

    name = metric_name.lower()
    absolute_value = abs(value)

    if "daily_margin_pct_change" in name:
        warning, critical = 0.10, 0.20
        status = "CRITICAL" if absolute_value > critical else "WARNING" if absolute_value > warning else "NORMAL"
        return warning, status, "Absolute daily change; warning >10%, critical >20%."

    if "weekly_margin_pct_change" in name:
        warning, critical = 0.20, 0.30
        status = "CRITICAL" if absolute_value > critical else "WARNING" if absolute_value > warning else "NORMAL"
        return warning, status, "Absolute five-observation change; warning >20%, critical >30%."

    if "peak_to_trough" in name or "drawdown" in name:
        warning, critical = 0.20, 0.30
        status = "CRITICAL" if absolute_value > critical else "WARNING" if absolute_value > warning else "NORMAL"
        return warning, status, "Peak-to-trough margin decline; warning >20%, critical >30%."

    if "stressed_to_calm_margin_ratio" in name:
        warning, critical = 1.50, 2.00
        status = "CRITICAL" if value > critical else "WARNING" if value > warning else "NORMAL"
        return warning, status, "Stressed/calm average-margin ratio; warning >1.50, critical >2.00."

    if "correlation" in name:
        warning, critical = 0.75, 0.85
        status = "CRITICAL" if absolute_value > critical else "WARNING" if absolute_value > warning else "NORMAL"
        return warning, status, "Absolute Pearson correlation; warning >0.75, critical >0.85."

    if "margin_call_volatility" in name:
        warning, critical = 0.10, 0.20
        status = "CRITICAL" if value > critical else "WARNING" if value > warning else "NORMAL"
        return warning, status, "Standard deviation of daily margin changes; warning >10%, critical >20%."

    if "jumps_over_30pct" in name:
        warning = 0.0
        return warning, "WARNING" if value > 0 else "NORMAL", "Any margin jump above 30% is escalated."

    if "jumps_over_20pct" in name:
        warning = 0.0
        return warning, "WARNING" if value > 0 else "NORMAL", "Any margin jump above 20% is escalated."

    if "jumps_over_10pct" in name:
        warning = 5.0
        return warning, "WARNING" if value > warning else "NORMAL", "More than five margin jumps above 10% is escalated."

    if "buffer_depletion" in name:
        warning = 5.0
        return warning, "WARNING" if value > warning else "NORMAL", "More than five buffer-depletion events is escalated."

    if "buffer_replenishment" in name:
        return None, "INFORMATIONAL", "Descriptive replenishment-event count."

    if "variant_average_margin_change" in name:
        warning, critical = 0.10, 0.20
        status = "CRITICAL" if absolute_value > critical else "WARNING" if absolute_value > warning else "NORMAL"
        return warning, status, "Absolute average scenario-versus-baseline margin change; warning >10%, critical >20%."

    return None, "INFORMATIONAL", "Descriptive monitoring metric."


def metric_row(
    metric_date: pd.Timestamp,
    member_id: str | None,
    metric_name: str,
    metric_value: float,
    source_table: str,
    details: str,
) -> dict[str, Any]:
    threshold, status, interpretation = status_for(metric_name, metric_value)
    return {
        "metric_date": metric_date.date().isoformat(),
        "member_id": member_id,
        "metric_name": metric_name,
        "metric_value": metric_value if math.isfinite(metric_value) else np.nan,
        "threshold_value": threshold,
        "status": status,
        "source_table": source_table,
        "details": f"{details} {interpretation}".strip(),
    }


def baseline_mask(frame: pd.DataFrame) -> pd.Series:
    mask = pd.Series(False, index=frame.index)
    if "is_baseline" in frame.columns:
        mask |= as_bool(frame["is_baseline"])
    if "scenario_id" in frame.columns:
        mask |= frame["scenario_id"].astype("string").str.strip().str.lower().eq("baseline")
    return mask


def calculate_member_metrics(history: pd.DataFrame, stressed_dates: set[pd.Timestamp], calm_dates: set[pd.Timestamp]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for member_id, group in history.groupby("member_id", sort=True):
        group = group.sort_values("date").copy()
        latest = group.iloc[-1]
        stressed = group[group["date"].isin(stressed_dates)]
        calm = group[group["date"].isin(calm_dates)]
        calm_average = pd.to_numeric(calm["margin"], errors="coerce").mean()
        stressed_average = pd.to_numeric(stressed["margin"], errors="coerce").mean()
        stress_calm_ratio = (
            stressed_average / calm_average
            if pd.notna(calm_average) and calm_average != 0 and pd.notna(stressed_average)
            else math.nan
        )

        drawdown = pd.to_numeric(group["drawdown_from_peak"], errors="coerce")
        peak_to_trough = abs(float(drawdown.min())) if drawdown.notna().any() else math.nan

        rows.append(
            {
                "metric_date": latest["date"].date().isoformat(),
                "member_id": str(member_id),
                "observations": int(len(group)),
                "latest_margin": finite_or_nan(latest["margin"]),
                "latest_daily_margin_pct_change": finite_or_nan(latest["daily_margin_pct_change"]),
                "latest_weekly_margin_pct_change": finite_or_nan(latest["weekly_margin_pct_change"]),
                "peak_to_trough_margin_decline": peak_to_trough,
                "stressed_to_calm_margin_ratio": finite_or_nan(stress_calm_ratio),
                "margin_realized_volatility_correlation": safe_corr(group["margin"], group["realized_volatility_20d"]),
                "margin_change_market_loss_correlation": safe_corr(group["daily_margin_pct_change"], group["market_loss_rate"]),
                "jumps_over_10pct": int((group["daily_margin_pct_change"].abs() > 0.10).sum()),
                "jumps_over_20pct": int((group["daily_margin_pct_change"].abs() > 0.20).sum()),
                "jumps_over_30pct": int((group["daily_margin_pct_change"].abs() > 0.30).sum()),
                "margin_call_volatility": finite_or_nan(group["daily_margin_pct_change"].std(ddof=1)),
                "buffer_depletion_events": int((group["stress_buffer_change"] < 0).sum()),
                "buffer_replenishment_events": int((group["stress_buffer_change"] > 0).sum()),
                "average_stress_buffer": finite_or_nan(group["stress_buffer"].mean()),
            }
        )

    return pd.DataFrame(rows)


def build_variant_comparison(all_scenarios: pd.DataFrame, baseline: pd.DataFrame) -> pd.DataFrame:
    key_columns = ["date", "member_id"]
    baseline_reference = baseline[key_columns + ["margin"]].rename(columns={"margin": "baseline_margin"})

    candidates = all_scenarios.copy()
    candidates["date"] = pd.to_datetime(candidates["date"], errors="coerce")
    candidates["member_id"] = candidates["member_id"].astype("string")
    candidates["margin"] = pd.to_numeric(candidates["margin"], errors="coerce")
    candidates = candidates.merge(baseline_reference, on=key_columns, how="left", validate="many_to_one")

    if "scenario_id" not in candidates.columns:
        candidates["scenario_id"] = "unspecified"
    if "parameter" not in candidates.columns:
        candidates["parameter"] = candidates["scenario_id"]
    if "parameter_value" not in candidates.columns:
        candidates["parameter_value"] = np.nan

    candidates["scenario_margin_change"] = candidates["margin"] - candidates["baseline_margin"]
    candidates["scenario_margin_pct_change"] = np.where(
        candidates["baseline_margin"].ne(0),
        candidates["margin"] / candidates["baseline_margin"] - 1.0,
        np.nan,
    )

    variants = candidates[~baseline_mask(candidates)].copy()
    if variants.empty:
        return pd.DataFrame(
            columns=[
                "scenario_id",
                "parameter",
                "parameter_value",
                "observations",
                "average_baseline_margin",
                "average_scenario_margin",
                "average_margin_change",
                "average_margin_pct_change",
                "maximum_absolute_margin_pct_change",
            ]
        )

    grouped = (
        variants.groupby(["scenario_id", "parameter", "parameter_value"], dropna=False)
        .agg(
            observations=("margin", "size"),
            average_baseline_margin=("baseline_margin", "mean"),
            average_scenario_margin=("margin", "mean"),
            average_margin_change=("scenario_margin_change", "mean"),
            average_margin_pct_change=("scenario_margin_pct_change", "mean"),
            maximum_absolute_margin_pct_change=("scenario_margin_pct_change", lambda values: values.abs().max()),
        )
        .reset_index()
        .sort_values("maximum_absolute_margin_pct_change", ascending=False, na_position="last")
    )
    return grouped


def main() -> int:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Required Step 17 input was not found: {INPUT_PATH}")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    all_scenarios = pd.read_parquet(INPUT_PATH)
    all_scenarios.columns = [str(column).strip().lower() for column in all_scenarios.columns]

    missing = sorted(REQUIRED_COLUMNS - set(all_scenarios.columns))
    if missing:
        raise ValueError(f"Sensitivity results are missing required columns: {missing}")

    all_scenarios["date"] = pd.to_datetime(all_scenarios["date"], errors="coerce")
    all_scenarios["member_id"] = all_scenarios["member_id"].astype("string")
    all_scenarios["margin"] = pd.to_numeric(all_scenarios["margin"], errors="coerce")
    all_scenarios["realized_loss"] = pd.to_numeric(all_scenarios["realized_loss"], errors="coerce")

    baseline = all_scenarios[baseline_mask(all_scenarios)].copy()
    baseline = baseline.dropna(subset=["date", "member_id", "margin", "realized_loss"])
    baseline = baseline.sort_values(["member_id", "date"])

    if baseline.empty:
        raise ValueError("No baseline rows were found in sensitivity_scenario_results.parquet.")

    duplicate_count = int(baseline.duplicated(["date", "member_id"]).sum())
    if duplicate_count:
        numeric_columns = baseline.select_dtypes(include=[np.number]).columns.tolist()
        aggregation: dict[str, str] = {column: "first" for column in baseline.columns if column not in {"date", "member_id"}}
        for column in numeric_columns:
            if column not in {"date", "member_id"}:
                aggregation[column] = "mean"
        baseline = baseline.groupby(["date", "member_id"], as_index=False).agg(aggregation)

    for optional_column in ["gross_exposure", "stress_buffer", "primary_var", "challenger_var"]:
        if optional_column not in baseline.columns:
            baseline[optional_column] = 0.0 if optional_column == "stress_buffer" else np.nan
        baseline[optional_column] = pd.to_numeric(baseline[optional_column], errors="coerce")

    baseline = baseline.sort_values(["member_id", "date"]).reset_index(drop=True)
    baseline["daily_margin_pct_change"] = baseline.groupby("member_id")["margin"].pct_change(fill_method=None)
    baseline["weekly_margin_pct_change"] = baseline["margin"] / baseline.groupby("member_id")["margin"].shift(5) - 1.0
    baseline["running_peak_margin"] = baseline.groupby("member_id")["margin"].cummax()
    baseline["drawdown_from_peak"] = np.where(
        baseline["running_peak_margin"].ne(0),
        baseline["margin"] / baseline["running_peak_margin"] - 1.0,
        np.nan,
    )

    gross_denominator = baseline["gross_exposure"].abs()
    fallback_denominator = baseline["margin"].abs().replace(0, np.nan)
    denominator = gross_denominator.where(gross_denominator.gt(0), fallback_denominator)
    baseline["market_loss_rate"] = baseline["realized_loss"] / denominator
    baseline["realized_volatility_20d"] = (
        baseline.groupby("member_id", group_keys=False)["market_loss_rate"]
        .rolling(window=20, min_periods=5)
        .std(ddof=1)
        .reset_index(level=0, drop=True)
    )
    baseline["stress_buffer_change"] = baseline.groupby("member_id")["stress_buffer"].diff()

    system_history = (
        baseline.groupby("date", as_index=False)
        .agg(
            total_margin=("margin", "sum"),
            total_realized_loss=("realized_loss", "sum"),
            total_gross_exposure=("gross_exposure", "sum"),
            total_stress_buffer=("stress_buffer", "sum"),
            realized_volatility=("realized_volatility_20d", "mean"),
        )
        .sort_values("date")
    )
    system_history["daily_margin_pct_change"] = system_history["total_margin"].pct_change(fill_method=None)
    system_history["weekly_margin_pct_change"] = system_history["total_margin"] / system_history["total_margin"].shift(5) - 1.0
    system_history["running_peak_margin"] = system_history["total_margin"].cummax()
    system_history["drawdown_from_peak"] = np.where(
        system_history["running_peak_margin"].ne(0),
        system_history["total_margin"] / system_history["running_peak_margin"] - 1.0,
        np.nan,
    )
    system_denominator = system_history["total_gross_exposure"].abs().replace(0, np.nan)
    system_history["market_loss_rate"] = system_history["total_realized_loss"] / system_denominator

    stress_indicator = system_history["realized_volatility"].copy()
    if stress_indicator.notna().sum() < 5 or stress_indicator.nunique(dropna=True) < 2:
        stress_indicator = system_history["market_loss_rate"].abs()
    if stress_indicator.notna().sum() < 5 or stress_indicator.nunique(dropna=True) < 2:
        stress_indicator = system_history["total_realized_loss"].abs()

    lower_quantile = stress_indicator.quantile(0.25)
    upper_quantile = stress_indicator.quantile(0.75)
    stressed_dates = set(system_history.loc[stress_indicator >= upper_quantile, "date"])
    calm_dates = set(system_history.loc[stress_indicator <= lower_quantile, "date"])

    member_metrics = calculate_member_metrics(baseline, stressed_dates, calm_dates)

    latest_date = pd.Timestamp(system_history["date"].max())
    stressed_average = system_history.loc[system_history["date"].isin(stressed_dates), "total_margin"].mean()
    calm_average = system_history.loc[system_history["date"].isin(calm_dates), "total_margin"].mean()
    stressed_to_calm_ratio = stressed_average / calm_average if pd.notna(calm_average) and calm_average != 0 else math.nan
    system_peak_to_trough = abs(float(system_history["drawdown_from_peak"].min())) if system_history["drawdown_from_peak"].notna().any() else math.nan

    system_metric_values = {
        "system_margin_daily_pct_change": finite_or_nan(system_history.iloc[-1]["daily_margin_pct_change"]),
        "system_margin_weekly_pct_change": finite_or_nan(system_history.iloc[-1]["weekly_margin_pct_change"]),
        "system_peak_to_trough_margin_decline": finite_or_nan(system_peak_to_trough),
        "system_stressed_to_calm_margin_ratio": finite_or_nan(stressed_to_calm_ratio),
        "system_margin_realized_volatility_correlation": safe_corr(system_history["total_margin"], system_history["realized_volatility"]),
        "system_margin_change_market_loss_correlation": safe_corr(system_history["daily_margin_pct_change"], system_history["market_loss_rate"]),
        "system_jumps_over_10pct": float((system_history["daily_margin_pct_change"].abs() > 0.10).sum()),
        "system_jumps_over_20pct": float((system_history["daily_margin_pct_change"].abs() > 0.20).sum()),
        "system_jumps_over_30pct": float((system_history["daily_margin_pct_change"].abs() > 0.30).sum()),
        "system_margin_call_volatility": finite_or_nan(system_history["daily_margin_pct_change"].std(ddof=1)),
        "system_buffer_depletion_events": float((system_history["total_stress_buffer"].diff() < 0).sum()),
        "system_buffer_replenishment_events": float((system_history["total_stress_buffer"].diff() > 0).sum()),
    }

    system_metrics_rows: list[dict[str, Any]] = []
    for metric_name, metric_value in system_metric_values.items():
        threshold, status, interpretation = status_for(metric_name, metric_value)
        system_metrics_rows.append(
            {
                "metric_date": latest_date.date().isoformat(),
                "metric_name": metric_name,
                "metric_value": metric_value,
                "threshold_value": threshold,
                "status": status,
                "details": interpretation,
            }
        )
    system_metrics = pd.DataFrame(system_metrics_rows)

    variant_comparison = build_variant_comparison(all_scenarios, baseline)

    buffer_events = baseline.loc[
        baseline["stress_buffer_change"].notna() & baseline["stress_buffer_change"].ne(0),
        ["date", "member_id", "stress_buffer", "stress_buffer_change", "margin", "daily_margin_pct_change"],
    ].copy()
    if not buffer_events.empty:
        buffer_events["event_type"] = np.where(
            buffer_events["stress_buffer_change"] < 0,
            "DEPLETION",
            "REPLENISHMENT",
        )
        buffer_events = buffer_events[
            ["date", "member_id", "event_type", "stress_buffer", "stress_buffer_change", "margin", "daily_margin_pct_change"]
        ]

    monitoring_rows: list[dict[str, Any]] = []
    member_metric_map = {
        "latest_daily_margin_pct_change": "member_daily_margin_pct_change",
        "latest_weekly_margin_pct_change": "member_weekly_margin_pct_change",
        "peak_to_trough_margin_decline": "member_peak_to_trough_margin_decline",
        "stressed_to_calm_margin_ratio": "member_stressed_to_calm_margin_ratio",
        "margin_realized_volatility_correlation": "member_margin_realized_volatility_correlation",
        "margin_change_market_loss_correlation": "member_margin_change_market_loss_correlation",
        "jumps_over_10pct": "member_jumps_over_10pct",
        "jumps_over_20pct": "member_jumps_over_20pct",
        "jumps_over_30pct": "member_jumps_over_30pct",
        "margin_call_volatility": "member_margin_call_volatility",
        "buffer_depletion_events": "member_buffer_depletion_events",
        "buffer_replenishment_events": "member_buffer_replenishment_events",
    }

    for row in member_metrics.to_dict(orient="records"):
        metric_date = pd.Timestamp(row["metric_date"])
        member_id = str(row["member_id"])
        for source_column, metric_name in member_metric_map.items():
            value = finite_or_nan(row[source_column])
            monitoring_rows.append(
                metric_row(
                    metric_date,
                    member_id,
                    metric_name,
                    value,
                    "procyclicality_margin_history",
                    f"Calculated from {int(row['observations'])} baseline observations for member {member_id}.",
                )
            )

    for row in system_metrics.to_dict(orient="records"):
        monitoring_rows.append(
            {
                "metric_date": row["metric_date"],
                "member_id": None,
                "metric_name": row["metric_name"],
                "metric_value": row["metric_value"],
                "threshold_value": row["threshold_value"],
                "status": row["status"],
                "source_table": "procyclicality_margin_history",
                "details": row["details"],
            }
        )

    for row in variant_comparison.head(250).to_dict(orient="records"):
        scenario_id = str(row.get("scenario_id", "unspecified"))
        parameter = str(row.get("parameter", "unspecified"))
        value = finite_or_nan(row.get("average_margin_pct_change"))
        monitoring_rows.append(
            metric_row(
                latest_date,
                None,
                f"variant_average_margin_change__{scenario_id}",
                value,
                "sensitivity_scenario_results",
                f"Scenario {scenario_id}; parameter {parameter}; average scenario-versus-baseline margin change.",
            )
        )

    monitoring_metrics = pd.DataFrame(monitoring_rows)
    monitoring_metrics = monitoring_metrics.sort_values(
        ["metric_date", "member_id", "metric_name"],
        na_position="first",
    ).reset_index(drop=True)

    baseline.to_parquet(HISTORY_PATH, index=False)
    member_metrics.to_csv(MEMBER_METRICS_PATH, index=False)
    system_metrics.to_csv(SYSTEM_METRICS_PATH, index=False)
    variant_comparison.to_csv(VARIANT_PATH, index=False)
    buffer_events.to_csv(BUFFER_EVENTS_PATH, index=False)
    monitoring_metrics.to_csv(MONITORING_PATH, index=False)

    summary_lines = [
        "# Step 17 Procyclicality Results",
        "",
        f"- Source: `{INPUT_PATH.relative_to(PROJECT_ROOT)}`",
        f"- Baseline observations: {len(baseline):,}",
        f"- Members: {baseline['member_id'].nunique():,}",
        f"- Dates: {baseline['date'].nunique():,}",
        f"- Duplicate baseline member-date rows consolidated: {duplicate_count:,}",
        f"- Monitoring metric rows: {len(monitoring_metrics):,}",
        f"- Variant comparison rows: {len(variant_comparison):,}",
        f"- Buffer events: {len(buffer_events):,}",
        "",
        "## System metrics",
        "",
    ]
    for row in system_metrics.to_dict(orient="records"):
        summary_lines.append(
            f"- `{row['metric_name']}`: {row['metric_value']} ({row['status']})"
        )
    SUMMARY_PATH.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print("Step 17 procyclicality outputs generated successfully.")
    print(f"Baseline observations: {len(baseline):,}")
    print(f"Members: {baseline['member_id'].nunique():,}")
    print(f"Dates: {baseline['date'].nunique():,}")
    print(f"Monitoring rows: {len(monitoring_metrics):,}")
    print(f"History: {HISTORY_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Monitoring feed: {MONITORING_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Evidence directory: {EVIDENCE_DIR.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[ERROR] Step 17 generation failed: {exc}", file=sys.stderr)
        raise
'@
Set-Content -Path "scripts\17_generate_procyclicality_results.py" -Value $Step17Code -Encoding utf8
Write-Host "Created: scripts\17_generate_procyclicality_results.py"

Write-Section "CREATE THE DETERMINISTIC STEP 18 LOADER"
$Step18Code = @'

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
'@
Set-Content -Path "scripts\18_build_duckdb.py" -Value $Step18Code -Encoding utf8
Write-Host "Created: scripts\18_build_duckdb.py"

Write-Section "CREATE THE ENHANCED STEP 18 TESTS"
$TestCode = @'

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
'@
Set-Content -Path "tests\test_sql_pipeline.py" -Value $TestCode -Encoding utf8
Write-Host "Created: tests\test_sql_pipeline.py"

Write-Section "UPDATE THE REUSABLE STEP18_RUN SCRIPT"
$Step18RunCode = @'
$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Users\nejat\OneDrive\Desktop\UN\Skills\GitHub 2026\ccp-margin-model-validation"
Set-Location $ProjectRoot

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "Creating Python 3.11 virtual environment..."
    py -3.11 -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        py -3 -m venv .venv
    }
}

$Python = ".\.venv\Scripts\python.exe"

Write-Host "Installing required packages..."
& $Python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }

& $Python -m pip install "duckdb>=1.4,<2" pandas numpy pyarrow pytest
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

Write-Host "Generating Step 17 procyclicality outputs..."
& $Python ".\scripts\17_generate_procyclicality_results.py"
if ($LASTEXITCODE -ne 0) { throw "Step 17 generation failed." }

Write-Host "Building the deterministic Step 18 DuckDB database..."
& $Python ".\scripts\18_build_duckdb.py"
if ($LASTEXITCODE -ne 0) { throw "Step 18 database build failed." }

Write-Host "Running enhanced Step 18 tests..."
& $Python -m pytest ".\tests\test_sql_pipeline.py" -q
if ($LASTEXITCODE -ne 0) { throw "Step 18 tests failed." }

Write-Host ""
Write-Host "Step 17 and Step 18 completed successfully."
Write-Host "Database: data\database\ccp_margin_validation.duckdb"
Write-Host "Manifest: reports\sql\load_manifest.csv"
'@
Set-Content -Path "STEP18_RUN.ps1" -Value $Step18RunCode -Encoding utf8
Write-Host "Updated: STEP18_RUN.ps1"

Write-Section "UPDATE .GITIGNORE"
$GitIgnoreEntries = @(
    "data/database/*.duckdb",
    "data/database/*.wal",
    "data/database/*.duckdb.wal"
)
if (-not (Test-Path ".gitignore")) {
    New-Item -ItemType File -Path ".gitignore" -Force | Out-Null
}
$GitIgnoreText = Get-Content ".gitignore" -Raw
foreach ($Entry in $GitIgnoreEntries) {
    if ($GitIgnoreText -notmatch "(?m)^$([regex]::Escape($Entry))$") {
        Add-Content -Path ".gitignore" -Value $Entry
        Write-Host "Added to .gitignore: $Entry"
    }
}

Write-Section "CREATE OR REUSE THE PROJECT VIRTUAL ENVIRONMENT"
if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    py -3.11 -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        py -3 -m venv .venv
        Assert-LastExitCode "Virtual-environment creation"
    }
}
$Python = ".\.venv\Scripts\python.exe"

Write-Host "Installing DuckDB, pandas, NumPy, PyArrow, and pytest..."
& $Python -m pip install --upgrade pip
Assert-LastExitCode "pip upgrade"
& $Python -m pip install "duckdb>=1.4,<2" pandas numpy pyarrow pytest
Assert-LastExitCode "Dependency installation"

Write-Section "RUN STEP 17 AND STEP 18"
Set-ExecutionPolicy -Scope Process Bypass -Force
& ".\STEP18_RUN.ps1"
if ($LASTEXITCODE -ne 0) {
    throw "STEP18_RUN.ps1 failed."
}

Write-Section "FINAL DATABASE AND MANIFEST VERIFICATION"
$VerificationCode = @'
from pathlib import Path
import duckdb
import pandas as pd

root = Path.cwd()
database = root / "data" / "database" / "ccp_margin_validation.duckdb"
manifest_path = root / "reports" / "sql" / "load_manifest.csv"

expected_sources = {
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
forbidden = (
    "reverse_stress_results",
    "fred_series_raw",
    "t10y2y",
    "dgs10",
    "dgs2",
    "vixcls",
    "raw_data_validation",
)

manifest = pd.read_csv(manifest_path)
actual_sources = {
    str(row.table_name): str(row.source_file).replace("\\", "/")
    for row in manifest.itertuples(index=False)
}
if actual_sources != expected_sources:
    raise SystemExit(f"Manifest source mismatch.\nExpected: {expected_sources}\nActual: {actual_sources}")
combined = "\n".join(actual_sources.values()).lower()
if any(item in combined for item in forbidden):
    raise SystemExit("A forbidden unrelated source remains in the load manifest.")

with duckdb.connect(str(database), read_only=True) as con:
    tables = [
        row[0]
        for row in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main' AND table_type='BASE TABLE' ORDER BY table_name"
        ).fetchall()
    ]
    views = [
        row[0]
        for row in con.execute(
            "SELECT table_name FROM information_schema.views WHERE table_schema='main' ORDER BY table_name"
        ).fetchall()
    ]
    print(f"Physical tables: {len(tables)}")
    print(f"Reusable views: {len(views)}")
    print("\nTABLE ROW COUNTS")
    print("-" * 55)
    for table in tables:
        count = con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        print(f"{table:28s} {count:>15,}")

    long_stats = con.execute(
        "SELECT COUNT(*), COUNT(DISTINCT valuation_date), COUNT(DISTINCT risk_factor_id) FROM risk_factor_returns"
    ).fetchone()
    print("\nRISK-FACTOR LONG-FORM CHECK")
    print(f"Rows: {long_stats[0]:,}; dates: {long_stats[1]:,}; factors: {long_stats[2]:,}")

    backtest_stats = con.execute(
        "SELECT COUNT(*), SUM(exception_flag), SUM(margin_shortfall), COUNT(*) FILTER (WHERE margin_amount IS NULL OR realized_loss IS NULL) FROM backtesting_results"
    ).fetchone()
    print("\nBACKTESTING CHECK")
    print(f"Rows: {backtest_stats[0]:,}; exceptions: {int(backtest_stats[1] or 0):,}; total shortfall: {float(backtest_stats[2] or 0):,.2f}; null required rows: {backtest_stats[3]:,}")

    monitoring_stats = con.execute(
        "SELECT COUNT(*), COUNT(DISTINCT metric_name), COUNT(DISTINCT member_id) FROM monitoring_metrics"
    ).fetchone()
    print("\nMONITORING CHECK")
    print(f"Rows: {monitoring_stats[0]:,}; metrics: {monitoring_stats[1]:,}; members: {monitoring_stats[2]:,}")

    exception_rows = con.execute(
        """
        SELECT member_id, COUNT(*) AS exceptions, SUM(margin_shortfall) AS total_shortfall
        FROM backtesting_results
        WHERE exception_flag = 1
        GROUP BY member_id
        ORDER BY total_shortfall DESC
        """
    ).fetchall()
    print("\nREQUIRED EXCEPTION QUERY")
    if exception_rows:
        for row in exception_rows:
            print(row)
    else:
        print("No exception rows. The query executed successfully.")

if len(tables) != 10:
    raise SystemExit(f"Expected 10 physical tables, found {len(tables)}.")
if len(views) < 10:
    raise SystemExit(f"Expected at least 10 reusable views, found {len(views)}.")

print("\nFINAL VERIFICATION PASSED.")
'@
$VerificationCode | & $Python -
Assert-LastExitCode "Final database verification"

Write-Section "GIT COMMIT AND PUSH"
if ($SkipGit) {
    Write-Host "Git commit and push were skipped because -SkipGit was supplied."
}
else {
    $TrackedDatabase = git ls-files -- "data/database/ccp_margin_validation.duckdb"
    if ($TrackedDatabase) {
        git rm --cached -- "data/database/ccp_margin_validation.duckdb"
        Assert-LastExitCode "Removing the generated DuckDB file from Git tracking"
    }

    $GitPaths = @(
        ".gitignore",
        "sql",
        "scripts/17_generate_procyclicality_results.py",
        "scripts/18_build_duckdb.py",
        "tests/test_sql_pipeline.py",
        "STEP18_RUN.ps1",
        "data/processed/procyclicality_margin_history.parquet",
        "data/processed/procyclicality_monitoring_metrics.csv",
        "reports/evidence/procyclicality_member_metrics.csv",
        "reports/evidence/procyclicality_system_metrics.csv",
        "reports/evidence/procyclicality_variant_comparison.csv",
        "reports/evidence/procyclicality_buffer_events.csv",
        "reports/evidence/procyclicality_summary.md",
        "reports/evidence/findings/finding_register.csv",
        "reports/sql/load_manifest.csv",
        "reports/sql/member_exception_summary.csv",
        "reports/sql/model_backtesting_summary.csv",
        "reports/sql/stress_breach_summary.csv",
        "reports/sql/sensitivity_largest_movements.csv",
        "reports/sql/margin_jump_counts.csv",
        "reports/sql/member_margin_volatility.csv",
        "reports/sql/open_validation_findings.csv"
    )

    git add -- $GitPaths
    Assert-LastExitCode "Staging Step 17 and Step 18 files"

    git diff --cached --quiet
    $HasStagedChanges = $LASTEXITCODE -ne 0

    if ($HasStagedChanges) {
        git commit -m "Complete procyclicality monitoring and DuckDB SQL pipeline"
        Assert-LastExitCode "Git commit"

        git push
        Assert-LastExitCode "Git push"
        Write-Host "Commit and push completed successfully."
    }
    else {
        Write-Host "No new staged changes were detected. Nothing was committed or pushed."
    }
}

Write-Section "COMPLETION STATUS"
Write-Host "Step 17 calculated outputs:       COMPLETE"
Write-Host "Step 18 deterministic mappings:  COMPLETE"
Write-Host "DuckDB physical tables:          10 VERIFIED"
Write-Host "DuckDB reusable views:           10+ VERIFIED"
Write-Host "Risk-factor returns long format: VERIFIED"
Write-Host "Backtesting baseline derivation: VERIFIED"
Write-Host "Monitoring metrics:              VERIFIED"
Write-Host "Enhanced pytest suite:           PASSED"
if ($SkipGit) {
    Write-Host "GitHub commit and push:           SKIPPED"
}
else {
    Write-Host "GitHub commit and push:           COMPLETE OR NO CHANGES"
}
Write-Host ""
Write-Host "Backup folder: $BackupRoot"

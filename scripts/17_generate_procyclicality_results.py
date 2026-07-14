
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

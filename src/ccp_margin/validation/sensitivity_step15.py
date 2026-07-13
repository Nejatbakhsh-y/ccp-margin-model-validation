"""Independent sensitivity-analysis utilities for CCP margin validation.

The module deliberately separates:
1. Scenario design.
2. Model execution.
3. Independent comparison and reporting.

The model runner must produce scenario-level results using the schema documented
in ``validate_scenario_results``. This module does not silently manufacture
scenario outputs or infer missing model runs.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
from scipy.stats import chi2


PARAMETER_COLUMNS = (
    "confidence_level",
    "lookback_days",
    "mpor_days",
    "ewma_lambda",
    "concentration_threshold",
    "liquidity_threshold_adv",
    "stress_buffer",
    "correlation_shock",
)

RESULT_COLUMNS = (
    "scenario_id",
    "date",
    "member_id",
    "margin",
    "realized_loss",
)

MANIFEST_COLUMNS = (
    "scenario_id",
    "parameter",
    "parameter_value",
    "is_baseline",
    *PARAMETER_COLUMNS,
)


@dataclass(frozen=True)
class SensitivityAnalysisResult:
    """Container for independently calculated sensitivity evidence."""

    scenario_summary: pd.DataFrame
    member_ranking_detail: pd.DataFrame
    parameter_stability: pd.DataFrame
    metadata: dict[str, Any]


def _value_equal(left: Any, right: Any) -> bool:
    """Compare numerical and categorical parameter values safely."""

    if isinstance(left, (int, float, np.integer, np.floating)) and isinstance(
        right, (int, float, np.integer, np.floating)
    ):
        return bool(np.isclose(float(left), float(right), rtol=0.0, atol=1e-12))
    return str(left) == str(right)


def _scenario_id(parameter: str, value: Any) -> str:
    text = str(value).replace(".", "p").replace("-", "m").replace(" ", "_")
    return f"{parameter}__{text}"


def build_one_at_a_time_manifest(
    baseline: Mapping[str, Any],
    parameter_sets: Mapping[str, list[Any] | tuple[Any, ...]],
) -> pd.DataFrame:
    """Build the required baseline plus one-at-a-time sensitivity scenarios.

    The baseline is emitted once. Any value equal to the baseline is not emitted
    again as a separate scenario.
    """

    missing_baseline = [name for name in PARAMETER_COLUMNS if name not in baseline]
    missing_grids = [name for name in PARAMETER_COLUMNS if name not in parameter_sets]
    if missing_baseline or missing_grids:
        raise ValueError(
            "Sensitivity configuration is incomplete. "
            f"Missing baseline keys={missing_baseline}; "
            f"missing parameter sets={missing_grids}."
        )

    rows: list[dict[str, Any]] = [
        {
            "scenario_id": "baseline",
            "parameter": "baseline",
            "parameter_value": "baseline",
            "is_baseline": True,
            **{name: baseline[name] for name in PARAMETER_COLUMNS},
        }
    ]

    for parameter in PARAMETER_COLUMNS:
        values = list(parameter_sets[parameter])
        if not values:
            raise ValueError(f"Parameter set '{parameter}' is empty.")

        for value in values:
            if _value_equal(value, baseline[parameter]):
                continue

            scenario = {name: baseline[name] for name in PARAMETER_COLUMNS}
            scenario[parameter] = value
            rows.append(
                {
                    "scenario_id": _scenario_id(parameter, value),
                    "parameter": parameter,
                    "parameter_value": value,
                    "is_baseline": False,
                    **scenario,
                }
            )

    manifest = pd.DataFrame(rows)
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: pd.DataFrame) -> None:
    """Validate scenario-manifest structure and one-at-a-time isolation."""

    missing = [column for column in MANIFEST_COLUMNS if column not in manifest.columns]
    if missing:
        raise ValueError(f"Sensitivity manifest is missing columns: {missing}")

    if manifest.empty:
        raise ValueError("Sensitivity manifest is empty.")

    duplicated = manifest["scenario_id"].duplicated(keep=False)
    if duplicated.any():
        values = manifest.loc[duplicated, "scenario_id"].tolist()
        raise ValueError(f"Duplicate scenario_id values found: {values}")

    baseline_rows = manifest.loc[manifest["is_baseline"].astype(bool)]
    if len(baseline_rows) != 1:
        raise ValueError("Manifest must contain exactly one baseline scenario.")

    baseline = baseline_rows.iloc[0]
    for _, row in manifest.loc[~manifest["is_baseline"].astype(bool)].iterrows():
        changed = [
            name
            for name in PARAMETER_COLUMNS
            if not _value_equal(row[name], baseline[name])
        ]
        if changed != [row["parameter"]]:
            raise ValueError(
                f"Scenario '{row['scenario_id']}' must change exactly its named "
                f"parameter. Changed columns={changed}; named parameter="
                f"{row['parameter']}."
            )


def validate_scenario_results(results: pd.DataFrame, manifest: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize model-generated sensitivity results.

    Required input columns:
    - scenario_id
    - date
    - member_id
    - margin
    - realized_loss

    ``realized_loss`` must use a positive-loss convention. An exception occurs
    when realized_loss > margin. Shortfall equals max(realized_loss - margin, 0).

    The model runner may provide ``exception`` and ``shortfall`` columns. When
    absent, they are calculated independently here. When present, they are
    checked against the independent calculations.
    """

    validate_manifest(manifest)

    missing = [column for column in RESULT_COLUMNS if column not in results.columns]
    if missing:
        raise ValueError(f"Scenario results are missing columns: {missing}")

    if results.empty:
        raise ValueError("Scenario results are empty.")

    normalized = results.copy()
    normalized["date"] = pd.to_datetime(normalized["date"], errors="raise")
    normalized["member_id"] = normalized["member_id"].astype(str)
    normalized["scenario_id"] = normalized["scenario_id"].astype(str)
    normalized["margin"] = pd.to_numeric(normalized["margin"], errors="raise")
    normalized["realized_loss"] = pd.to_numeric(
        normalized["realized_loss"], errors="raise"
    )

    if not np.isfinite(normalized[["margin", "realized_loss"]].to_numpy()).all():
        raise ValueError("Margin and realized_loss must be finite.")
    if (normalized["margin"] < 0).any():
        raise ValueError("Margin cannot be negative.")
    if (normalized["realized_loss"] < 0).any():
        raise ValueError(
            "realized_loss cannot be negative. Use a positive-loss convention."
        )

    duplicate_keys = normalized.duplicated(
        subset=["scenario_id", "date", "member_id"], keep=False
    )
    if duplicate_keys.any():
        sample = normalized.loc[
            duplicate_keys, ["scenario_id", "date", "member_id"]
        ].head(10)
        raise ValueError(
            "Duplicate scenario/date/member rows found. Sample:\n"
            + sample.to_string(index=False)
        )

    manifest_ids = set(manifest["scenario_id"].astype(str))
    result_ids = set(normalized["scenario_id"])
    missing_runs = sorted(manifest_ids - result_ids)
    unexpected_runs = sorted(result_ids - manifest_ids)
    if missing_runs or unexpected_runs:
        raise ValueError(
            "Scenario result coverage does not match the manifest. "
            f"Missing runs={missing_runs}; unexpected runs={unexpected_runs}."
        )

    independent_exception = normalized["realized_loss"] > normalized["margin"]
    independent_shortfall = (
        normalized["realized_loss"] - normalized["margin"]
    ).clip(lower=0.0)

    if "exception" in normalized.columns:
        supplied_exception = normalized["exception"].astype(bool)
        mismatch = supplied_exception != independent_exception
        if mismatch.any():
            raise ValueError(
                f"Provided exception values disagree with independent calculation "
                f"for {int(mismatch.sum())} rows."
            )
    normalized["exception"] = independent_exception.astype(int)

    if "shortfall" in normalized.columns:
        supplied_shortfall = pd.to_numeric(
            normalized["shortfall"], errors="raise"
        )
        mismatch = ~np.isclose(
            supplied_shortfall.to_numpy(),
            independent_shortfall.to_numpy(),
            rtol=1e-9,
            atol=1e-8,
        )
        if mismatch.any():
            raise ValueError(
                f"Provided shortfall values disagree with independent calculation "
                f"for {int(mismatch.sum())} rows."
            )
    normalized["shortfall"] = independent_shortfall

    return normalized


def _safe_xlogy(count: int, probability: float) -> float:
    if count == 0:
        return 0.0
    if probability <= 0.0:
        return -math.inf
    return count * math.log(probability)


def _kupiec_metrics(
    exceptions: pd.Series,
    target_exception_probability: float,
    significance_level: float,
) -> dict[str, Any]:
    """Calculate unconditional-coverage metrics without calling model code."""

    x = int(pd.Series(exceptions).astype(int).sum())
    n = int(len(exceptions))
    if n <= 0:
        raise ValueError("Kupiec calculation requires at least one observation.")
    if not 0.0 < target_exception_probability < 1.0:
        raise ValueError("Target exception probability must be between 0 and 1.")

    observed = x / n
    null_ll = _safe_xlogy(x, target_exception_probability) + _safe_xlogy(
        n - x, 1.0 - target_exception_probability
    )

    if x == 0:
        alt_ll = 0.0
    elif x == n:
        alt_ll = 0.0
    else:
        alt_ll = _safe_xlogy(x, observed) + _safe_xlogy(n - x, 1.0 - observed)

    lr_stat = max(0.0, -2.0 * (null_ll - alt_ll))
    p_value = float(chi2.sf(lr_stat, df=1))

    return {
        "observations": n,
        "exceptions": x,
        "exception_rate": observed,
        "target_exception_probability": target_exception_probability,
        "kupiec_lr_statistic": lr_stat,
        "kupiec_p_value": p_value,
        "kupiec_pass_5pct": bool(p_value >= significance_level),
    }


def _safe_pct_change(current: float, baseline: float) -> float:
    if np.isclose(baseline, 0.0):
        return 0.0 if np.isclose(current, 0.0) else np.nan
    return 100.0 * (current - baseline) / abs(baseline)


def _top_member_overlap(
    baseline_member: pd.DataFrame,
    scenario_member: pd.DataFrame,
    top_n: int,
) -> float:
    base_top = set(
        baseline_member.nsmallest(top_n, "baseline_rank")["member_id"].astype(str)
    )
    scenario_top = set(
        scenario_member.nsmallest(top_n, "scenario_rank")["member_id"].astype(str)
    )
    denominator = max(1, min(top_n, len(base_top), len(scenario_top)))
    return len(base_top & scenario_top) / denominator


def run_sensitivity_analysis(
    results: pd.DataFrame,
    manifest: pd.DataFrame,
    *,
    significance_level: float = 0.05,
    top_member_count: int = 5,
    stability_review_thresholds: Mapping[str, float] | None = None,
) -> SensitivityAnalysisResult:
    """Compare every sensitivity scenario with the baseline.

    Comparison matching is performed on identical ``date`` and ``member_id``
    keys. A scenario with different coverage from the baseline is rejected.
    """

    normalized = validate_scenario_results(results, manifest)
    manifest_clean = manifest.copy()
    manifest_clean["scenario_id"] = manifest_clean["scenario_id"].astype(str)

    if not 0.0 < significance_level < 1.0:
        raise ValueError("significance_level must be between 0 and 1.")
    if top_member_count <= 0:
        raise ValueError("top_member_count must be positive.")

    baseline_row = manifest_clean.loc[
        manifest_clean["is_baseline"].astype(bool)
    ].iloc[0]
    baseline_id = str(baseline_row["scenario_id"])
    baseline_results = normalized.loc[
        normalized["scenario_id"] == baseline_id
    ].copy()

    key_columns = ["date", "member_id"]
    baseline_keys = baseline_results[key_columns].sort_values(key_columns).reset_index(
        drop=True
    )

    baseline_target = 1.0 - float(baseline_row["confidence_level"])
    baseline_kupiec = _kupiec_metrics(
        baseline_results["exception"], baseline_target, significance_level
    )

    baseline_member = (
        baseline_results.groupby("member_id", as_index=False)["margin"]
        .mean()
        .rename(columns={"margin": "baseline_average_margin"})
    )
    baseline_member["baseline_rank"] = baseline_member[
        "baseline_average_margin"
    ].rank(method="min", ascending=False)

    summary_rows: list[dict[str, Any]] = []
    ranking_rows: list[pd.DataFrame] = []

    for _, scenario_meta in manifest_clean.iterrows():
        scenario_id = str(scenario_meta["scenario_id"])
        scenario_results = normalized.loc[
            normalized["scenario_id"] == scenario_id
        ].copy()

        scenario_keys = scenario_results[key_columns].sort_values(
            key_columns
        ).reset_index(drop=True)
        if not baseline_keys.equals(scenario_keys):
            raise ValueError(
                f"Scenario '{scenario_id}' does not have identical date/member "
                "coverage to the baseline."
            )

        paired = baseline_results.merge(
            scenario_results,
            on=key_columns,
            how="inner",
            validate="one_to_one",
            suffixes=("_baseline", "_scenario"),
        )

        margin_delta = paired["margin_scenario"] - paired["margin_baseline"]
        shortfall_delta = (
            paired["shortfall_scenario"] - paired["shortfall_baseline"]
        )

        target_probability = 1.0 - float(scenario_meta["confidence_level"])
        scenario_kupiec = _kupiec_metrics(
            scenario_results["exception"],
            target_probability,
            significance_level,
        )

        scenario_member = (
            scenario_results.groupby("member_id", as_index=False)["margin"]
            .mean()
            .rename(columns={"margin": "scenario_average_margin"})
        )
        member_detail = baseline_member.merge(
            scenario_member, on="member_id", how="inner", validate="one_to_one"
        )
        member_detail["scenario_rank"] = member_detail[
            "scenario_average_margin"
        ].rank(method="min", ascending=False)
        member_detail["rank_change"] = (
            member_detail["scenario_rank"] - member_detail["baseline_rank"]
        )
        member_detail["absolute_rank_change"] = member_detail["rank_change"].abs()
        member_detail["scenario_id"] = scenario_id
        member_detail["parameter"] = scenario_meta["parameter"]
        member_detail["parameter_value"] = scenario_meta["parameter_value"]
        ranking_rows.append(member_detail)

        rank_correlation = member_detail[
            ["baseline_rank", "scenario_rank"]
        ].corr(method="spearman").iloc[0, 1]
        if pd.isna(rank_correlation):
            rank_correlation = 1.0

        mean_baseline_margin = float(paired["margin_baseline"].mean())
        mean_scenario_margin = float(paired["margin_scenario"].mean())
        total_baseline_shortfall = float(paired["shortfall_baseline"].sum())
        total_scenario_shortfall = float(paired["shortfall_scenario"].sum())

        parameter = str(scenario_meta["parameter"])
        baseline_parameter_value = (
            baseline_row[parameter] if parameter in PARAMETER_COLUMNS else np.nan
        )
        parameter_value = (
            scenario_meta[parameter] if parameter in PARAMETER_COLUMNS else np.nan
        )

        parameter_change_pct = np.nan
        margin_elasticity = np.nan
        if parameter in PARAMETER_COLUMNS:
            try:
                baseline_numeric = float(baseline_parameter_value)
                scenario_numeric = float(parameter_value)
                parameter_change_pct = _safe_pct_change(
                    scenario_numeric, baseline_numeric
                )
                margin_change_pct = _safe_pct_change(
                    mean_scenario_margin, mean_baseline_margin
                )
                if (
                    np.isfinite(parameter_change_pct)
                    and not np.isclose(parameter_change_pct, 0.0)
                ):
                    margin_elasticity = margin_change_pct / parameter_change_pct
            except (TypeError, ValueError):
                pass

        summary_rows.append(
            {
                "scenario_id": scenario_id,
                "parameter": parameter,
                "parameter_value": scenario_meta["parameter_value"],
                "is_baseline": bool(scenario_meta["is_baseline"]),
                "observations": scenario_kupiec["observations"],
                "members": int(scenario_results["member_id"].nunique()),
                "mean_margin": mean_scenario_margin,
                "median_margin": float(scenario_results["margin"].median()),
                "total_margin": float(scenario_results["margin"].sum()),
                "mean_margin_change": float(margin_delta.mean()),
                "median_margin_change": float(margin_delta.median()),
                "mean_absolute_margin_change": float(margin_delta.abs().mean()),
                "mean_margin_change_pct": _safe_pct_change(
                    mean_scenario_margin, mean_baseline_margin
                ),
                "maximum_absolute_margin_change_pct": float(
                    np.nanmax(
                        np.abs(
                            np.where(
                                paired["margin_baseline"].to_numpy() == 0.0,
                                np.nan,
                                100.0
                                * margin_delta.to_numpy()
                                / np.abs(paired["margin_baseline"].to_numpy()),
                            )
                        )
                    )
                )
                if (paired["margin_baseline"] != 0.0).any()
                else 0.0,
                "exception_count": scenario_kupiec["exceptions"],
                "exception_count_change": (
                    scenario_kupiec["exceptions"] - baseline_kupiec["exceptions"]
                ),
                "exception_rate": scenario_kupiec["exception_rate"],
                "exception_rate_change": (
                    scenario_kupiec["exception_rate"]
                    - baseline_kupiec["exception_rate"]
                ),
                "target_exception_probability": target_probability,
                "kupiec_lr_statistic": scenario_kupiec["kupiec_lr_statistic"],
                "kupiec_p_value": scenario_kupiec["kupiec_p_value"],
                "kupiec_pass_5pct": scenario_kupiec["kupiec_pass_5pct"],
                "kupiec_p_value_change": (
                    scenario_kupiec["kupiec_p_value"]
                    - baseline_kupiec["kupiec_p_value"]
                ),
                "total_shortfall": total_scenario_shortfall,
                "mean_shortfall": float(scenario_results["shortfall"].mean()),
                "maximum_shortfall": float(scenario_results["shortfall"].max()),
                "total_shortfall_change": (
                    total_scenario_shortfall - total_baseline_shortfall
                ),
                "total_shortfall_change_pct": _safe_pct_change(
                    total_scenario_shortfall, total_baseline_shortfall
                ),
                "member_rank_correlation": float(rank_correlation),
                "mean_absolute_member_rank_change": float(
                    member_detail["absolute_rank_change"].mean()
                ),
                "maximum_absolute_member_rank_change": float(
                    member_detail["absolute_rank_change"].max()
                ),
                "top_member_overlap": float(
                    _top_member_overlap(
                        baseline_member, member_detail, top_member_count
                    )
                ),
                "parameter_change_pct": parameter_change_pct,
                "margin_elasticity": margin_elasticity,
            }
        )

    scenario_summary = pd.DataFrame(summary_rows)
    member_ranking_detail = pd.concat(ranking_rows, ignore_index=True)

    thresholds = {
        "max_absolute_margin_change_pct": 25.0,
        "max_absolute_exception_rate_change": 0.01,
        "max_absolute_shortfall_change_pct": 25.0,
        "minimum_member_rank_correlation": 0.90,
    }
    if stability_review_thresholds:
        thresholds.update(
            {key: float(value) for key, value in stability_review_thresholds.items()}
        )

    parameter_rows: list[dict[str, Any]] = []
    non_baseline = scenario_summary.loc[~scenario_summary["is_baseline"]].copy()

    for parameter, group in non_baseline.groupby("parameter", sort=False):
        finite_shortfall = group["total_shortfall_change_pct"].replace(
            [np.inf, -np.inf], np.nan
        )
        max_abs_shortfall = (
            float(finite_shortfall.abs().max())
            if finite_shortfall.notna().any()
            else np.nan
        )
        max_abs_margin = float(group["mean_margin_change_pct"].abs().max())
        max_abs_exception_rate = float(group["exception_rate_change"].abs().max())
        min_rank_correlation = float(group["member_rank_correlation"].min())

        review_reasons: list[str] = []
        if max_abs_margin > thresholds["max_absolute_margin_change_pct"]:
            review_reasons.append("margin_change")
        if (
            max_abs_exception_rate
            > thresholds["max_absolute_exception_rate_change"]
        ):
            review_reasons.append("exception_rate")
        if np.isfinite(max_abs_shortfall) and (
            max_abs_shortfall
            > thresholds["max_absolute_shortfall_change_pct"]
        ):
            review_reasons.append("shortfall")
        if min_rank_correlation < thresholds["minimum_member_rank_correlation"]:
            review_reasons.append("member_ranking")

        parameter_rows.append(
            {
                "parameter": parameter,
                "scenario_count": int(len(group)),
                "mean_absolute_margin_change_pct": float(
                    group["mean_margin_change_pct"].abs().mean()
                ),
                "maximum_absolute_margin_change_pct": max_abs_margin,
                "mean_absolute_exception_rate_change": float(
                    group["exception_rate_change"].abs().mean()
                ),
                "maximum_absolute_exception_rate_change": max_abs_exception_rate,
                "mean_absolute_shortfall_change_pct": float(
                    finite_shortfall.abs().mean()
                )
                if finite_shortfall.notna().any()
                else np.nan,
                "maximum_absolute_shortfall_change_pct": max_abs_shortfall,
                "minimum_member_rank_correlation": min_rank_correlation,
                "maximum_absolute_member_rank_change": float(
                    group["maximum_absolute_member_rank_change"].max()
                ),
                "maximum_absolute_margin_elasticity": float(
                    group["margin_elasticity"].abs().max()
                )
                if group["margin_elasticity"].notna().any()
                else np.nan,
                "stability_flag": "REVIEW" if review_reasons else "STABLE",
                "review_reasons": ", ".join(review_reasons),
            }
        )

    parameter_stability = pd.DataFrame(parameter_rows)

    metadata = {
        "methodology": "one_at_a_time",
        "baseline_scenario_id": baseline_id,
        "scenario_count": int(len(manifest_clean)),
        "non_baseline_scenario_count": int(len(manifest_clean) - 1),
        "significance_level": significance_level,
        "top_member_count": top_member_count,
        "stability_review_thresholds": thresholds,
        "configuration_status": "preliminary",
        "warning": (
            "Stability review thresholds are preliminary diagnostic thresholds "
            "and are not approved production limits."
        ),
    }

    return SensitivityAnalysisResult(
        scenario_summary=scenario_summary,
        member_ranking_detail=member_ranking_detail,
        parameter_stability=parameter_stability,
        metadata=metadata,
    )


def _markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    selected = frame.loc[:, columns].copy()
    selected = selected.replace({np.nan: ""})
    headers = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = []
    for _, row in selected.iterrows():
        values = []
        for value in row:
            if isinstance(value, float):
                values.append(f"{value:.6g}")
            else:
                values.append(str(value))
        rows.append("| " + " | ".join(values) + " |")
    return "\n".join([headers, separator, *rows])


def write_sensitivity_report(
    analysis: SensitivityAnalysisResult,
    output_directory: str | Path,
) -> dict[str, Path]:
    """Write reproducible CSV, JSON, and Markdown sensitivity evidence."""

    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)

    paths = {
        "scenario_summary": output / "scenario_summary.csv",
        "member_ranking_detail": output / "member_ranking_detail.csv",
        "parameter_stability": output / "parameter_stability.csv",
        "metadata": output / "sensitivity_metadata.json",
        "report": output / "sensitivity_report.md",
    }

    analysis.scenario_summary.to_csv(paths["scenario_summary"], index=False)
    analysis.member_ranking_detail.to_csv(
        paths["member_ranking_detail"], index=False
    )
    analysis.parameter_stability.to_csv(
        paths["parameter_stability"], index=False
    )
    paths["metadata"].write_text(
        json.dumps(analysis.metadata, indent=2, default=str),
        encoding="utf-8",
    )

    scenario_columns = [
        "scenario_id",
        "parameter",
        "parameter_value",
        "mean_margin_change_pct",
        "exception_count_change",
        "exception_rate_change",
        "total_shortfall_change_pct",
        "member_rank_correlation",
        "maximum_absolute_member_rank_change",
        "margin_elasticity",
    ]
    stability_columns = [
        "parameter",
        "scenario_count",
        "maximum_absolute_margin_change_pct",
        "maximum_absolute_exception_rate_change",
        "maximum_absolute_shortfall_change_pct",
        "minimum_member_rank_correlation",
        "maximum_absolute_margin_elasticity",
        "stability_flag",
        "review_reasons",
    ]

    report_text = f"""# Step 15 Sensitivity Testing Report

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

{_markdown_table(analysis.scenario_summary, scenario_columns)}

## Parameter Stability

{_markdown_table(analysis.parameter_stability, stability_columns)}

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
"""
    paths["report"].write_text(report_text, encoding="utf-8")
    return paths

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ccp_margin.validation.sensitivity_step15 import (
    PARAMETER_COLUMNS,
    build_one_at_a_time_manifest,
    run_sensitivity_analysis,
    write_sensitivity_report,
)


BASELINE = {
    "confidence_level": 0.99,
    "lookback_days": 500,
    "mpor_days": 1,
    "ewma_lambda": 0.94,
    "concentration_threshold": 0.20,
    "liquidity_threshold_adv": 0.10,
    "stress_buffer": 0.10,
    "correlation_shock": "current",
}

PARAMETER_SETS = {
    "confidence_level": [0.975, 0.99, 0.995],
    "lookback_days": [153, 250, 500, 750, 1000],
    "mpor_days": [1, 3, 5],
    "ewma_lambda": [0.90, 0.94, 0.97],
    "concentration_threshold": [0.10, 0.20, 0.30],
    "liquidity_threshold_adv": [0.05, 0.10, 0.20],
    "stress_buffer": [0.00, 0.10, 0.25, 0.50],
    "correlation_shock": ["current", "plus_25_percent", "near_one"],
}


def make_results(manifest: pd.DataFrame) -> pd.DataFrame:
    dates = pd.date_range("2025-01-02", periods=40, freq="B")
    members = ["CM001", "CM002", "CM003", "CM004", "CM005", "CM006"]
    rows = []

    for scenario_index, scenario in manifest.reset_index(drop=True).iterrows():
        factor = 1.0 + 0.01 * scenario_index
        for date_index, date in enumerate(dates):
            for member_index, member in enumerate(members):
                baseline_margin = 100.0 + 10.0 * member_index
                margin = baseline_margin * factor
                # Deterministic positive-loss convention with occasional exceptions.
                realized_loss = (
                    70.0
                    + 8.0 * member_index
                    + (45.0 if (date_index + member_index) % 19 == 0 else 0.0)
                )
                rows.append(
                    {
                        "scenario_id": scenario["scenario_id"],
                        "date": date,
                        "member_id": member,
                        "margin": margin,
                        "realized_loss": realized_loss,
                    }
                )

    return pd.DataFrame(rows)


def test_manifest_contains_all_required_parameter_sets() -> None:
    manifest = build_one_at_a_time_manifest(BASELINE, PARAMETER_SETS)

    assert len(manifest) == 20
    assert manifest["is_baseline"].sum() == 1
    assert set(manifest.loc[~manifest["is_baseline"], "parameter"]) == set(
        PARAMETER_COLUMNS
    )


def test_each_non_baseline_scenario_changes_one_parameter() -> None:
    manifest = build_one_at_a_time_manifest(BASELINE, PARAMETER_SETS)
    baseline = manifest.loc[manifest["is_baseline"]].iloc[0]

    for _, row in manifest.loc[~manifest["is_baseline"]].iterrows():
        changed = [
            name for name in PARAMETER_COLUMNS if str(row[name]) != str(baseline[name])
        ]
        assert changed == [row["parameter"]]


def test_analysis_reports_all_required_dimensions(tmp_path: Path) -> None:
    manifest = build_one_at_a_time_manifest(BASELINE, PARAMETER_SETS)
    results = make_results(manifest)

    analysis = run_sensitivity_analysis(results, manifest)

    required_summary = {
        "mean_margin_change_pct",
        "kupiec_p_value_change",
        "exception_count_change",
        "exception_rate_change",
        "total_shortfall_change_pct",
        "member_rank_correlation",
        "maximum_absolute_member_rank_change",
        "margin_elasticity",
    }
    assert required_summary.issubset(analysis.scenario_summary.columns)
    assert set(analysis.parameter_stability["parameter"]) == set(PARAMETER_COLUMNS)
    assert len(analysis.scenario_summary) == len(manifest)
    assert np.isfinite(analysis.scenario_summary["mean_margin"]).all()

    paths = write_sensitivity_report(analysis, tmp_path)
    assert all(path.exists() for path in paths.values())


def test_missing_scenario_is_rejected() -> None:
    manifest = build_one_at_a_time_manifest(BASELINE, PARAMETER_SETS)
    results = make_results(manifest)
    missing_id = manifest.iloc[-1]["scenario_id"]
    incomplete = results.loc[results["scenario_id"] != missing_id]

    try:
        run_sensitivity_analysis(incomplete, manifest)
    except ValueError as exc:
        assert "Missing runs" in str(exc)
    else:
        raise AssertionError("Missing scenario results were not rejected.")

"""Run historical, hypothetical, and reverse stress tests for Step 16."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from _daily_margin_common import (  # noqa: E402
    atomic_write_parquet,
    load_positions,
    load_project_config,
    load_returns,
    model_version,
    project_path,
    resolve_as_of_date,
    utc_timestamp,
    write_json,
)
from ccp_margin.stress.historical import (  # noqa: E402
    HistoricalScenario,
    run_historical_scenarios,
)
from ccp_margin.stress.hypothetical import run_hypothetical_scenarios  # noqa: E402
from ccp_margin.stress.reverse_stress import run_reverse_stress_tests  # noqa: E402


EXPECTED_HISTORICAL_SCENARIOS = 6
EXPECTED_HYPOTHETICAL_SCENARIOS = 14
EXPECTED_TOTAL_SCENARIOS = 20


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="Optional calculation date in YYYY-MM-DD format.")
    parser.add_argument(
        "--config",
        default="configs/stress_scenarios.yaml",
        help="Stress-scenario YAML configuration path.",
    )
    parser.add_argument(
        "--returns",
        default="data/processed/returns_wide.parquet",
        help="Wide daily-return Parquet path.",
    )
    parser.add_argument(
        "--positions",
        default=None,
        help="Optional explicit position CSV or Parquet path.",
    )
    parser.add_argument(
        "--margin",
        default="data/processed/daily_member_margin.parquet",
        help="Daily member-margin Parquet path.",
    )
    return parser.parse_args()


def load_stress_config(path: str | Path) -> dict[str, Any]:
    source = project_path(path)
    if not source.exists():
        raise FileNotFoundError(f"Stress configuration not found: {source}")
    with source.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    if not isinstance(config, dict):
        raise TypeError("Stress configuration must contain a YAML mapping.")
    required = {"historical_scenarios", "hypothetical_scenarios", "reverse_stress"}
    missing = required.difference(config)
    if missing:
        raise ValueError(f"Stress configuration is missing sections: {sorted(missing)}")
    status = str(config.get("configuration_status", "")).lower()
    if "preliminary" in status or "placeholder" in status:
        print(
            "WARNING: stress-scenario parameters are PRELIMINARY PLACEHOLDER "
            "calibrations and are not approved for production use."
        )
    return config


def load_margin_for_date(path: str | Path, as_of_date: pd.Timestamp) -> pd.DataFrame:
    source = project_path(path)
    if not source.exists():
        raise FileNotFoundError(
            f"Daily member margin not found: {source}. "
            "Run scripts/09_run_daily_member_margin.py first."
        )
    frame = pd.read_parquet(source)
    required = {
        "date",
        "member_id",
        "total_margin",
        "liquidity_addon",
        "gross_exposure",
        "net_exposure",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(
            f"Daily member margin is missing required fields: {sorted(missing)}"
        )
    frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
    selected = frame.loc[frame["date"] == as_of_date].copy()
    if selected.empty:
        available_dates = sorted(frame["date"].dropna().unique())
        latest = available_dates[-1] if available_dates else None
        raise ValueError(
            f"No daily-member-margin rows exist for {as_of_date.date()}. "
            f"Latest available date: {latest}. Run the Step 13 scripts for the "
            "same date before running stress tests."
        )
    if selected["member_id"].astype(str).duplicated().any():
        raise ValueError("Daily member margin contains duplicate member rows for the date.")
    numeric = ["total_margin", "liquidity_addon", "gross_exposure", "net_exposure"]
    selected[numeric] = selected[numeric].apply(pd.to_numeric, errors="raise")
    return selected.reset_index(drop=True)


def build_manifest(
    historical: list[HistoricalScenario],
    hypothetical_results: pd.DataFrame,
) -> pd.DataFrame:
    historical_rows = [
        {
            "scenario_id": scenario.scenario_id,
            "scenario_type": "historical",
            "scenario_name": scenario.name,
            "start_date": scenario.start_date.date().isoformat(),
            "end_date": scenario.end_date.date().isoformat(),
            "description": scenario.description,
        }
        for scenario in historical
    ]
    hypothetical_rows = (
        hypothetical_results[
            ["scenario_id", "scenario_type", "scenario_name", "shock_description"]
        ]
        .drop_duplicates("scenario_id")
        .rename(columns={"shock_description": "description"})
    )
    hypothetical_rows["start_date"] = ""
    hypothetical_rows["end_date"] = ""
    manifest = pd.concat(
        [pd.DataFrame(historical_rows), hypothetical_rows],
        ignore_index=True,
        sort=False,
    )
    manifest = manifest[
        [
            "scenario_id",
            "scenario_type",
            "scenario_name",
            "start_date",
            "end_date",
            "description",
        ]
    ].sort_values(["scenario_type", "scenario_id"]).reset_index(drop=True)
    if len(manifest) != EXPECTED_TOTAL_SCENARIOS:
        raise AssertionError(
            f"Expected {EXPECTED_TOTAL_SCENARIOS} manifest rows, found {len(manifest)}."
        )
    if manifest["scenario_id"].nunique() != EXPECTED_TOTAL_SCENARIOS:
        raise AssertionError("Stress scenario IDs are not unique.")
    return manifest


def add_margin_adequacy(
    results: pd.DataFrame,
    margin: pd.DataFrame,
) -> pd.DataFrame:
    margin_columns = margin[
        [
            "member_id",
            "total_margin",
            "liquidity_addon",
            "gross_exposure",
            "net_exposure",
        ]
    ].copy()
    margin_columns["member_id"] = margin_columns["member_id"].astype(str)
    output = results.copy()
    output["member_id"] = output["member_id"].astype(str)
    output = output.merge(
        margin_columns.rename(
            columns={
                "total_margin": "available_margin",
                "liquidity_addon": "baseline_liquidity_addon",
                "gross_exposure": "baseline_gross_exposure",
                "net_exposure": "baseline_net_exposure",
            }
        ),
        on="member_id",
        how="left",
        validate="many_to_one",
    )
    if output["available_margin"].isna().any():
        missing = sorted(output.loc[output["available_margin"].isna(), "member_id"].unique())
        raise KeyError(f"Stress results have no available margin for members: {missing}")
    output["stress_requirement"] = pd.to_numeric(
        output["stress_requirement"], errors="raise"
    ).clip(lower=0.0)
    output["margin_surplus"] = output["available_margin"] - output["stress_requirement"]
    output["margin_shortfall"] = (-output["margin_surplus"]).clip(lower=0.0)
    output["coverage_ratio"] = np.where(
        output["stress_requirement"] > 0.0,
        output["available_margin"] / output["stress_requirement"],
        np.inf,
    )
    output["margin_breach_flag"] = output["margin_shortfall"] > 0.0
    return output


def main() -> None:
    args = parse_args()
    project_config = load_project_config()
    stress_config = load_stress_config(args.config)
    returns = load_returns(args.returns)
    as_of_date = resolve_as_of_date(returns, args.date)
    returns = returns.loc[returns.index <= as_of_date].copy()
    positions = load_positions(as_of_date, args.positions)
    margin = load_margin_for_date(args.margin, as_of_date)

    position_members = set(positions["member_id"].astype(str))
    margin_members = set(margin["member_id"].astype(str))
    if position_members != margin_members:
        raise ValueError(
            "Position and margin member sets do not match. "
            f"Only in positions: {sorted(position_members - margin_members)}; "
            f"only in margin: {sorted(margin_members - position_members)}"
        )

    historical_scenarios = [
        HistoricalScenario.from_mapping(payload)
        for payload in stress_config["historical_scenarios"]
    ]
    if len(historical_scenarios) != EXPECTED_HISTORICAL_SCENARIOS:
        raise ValueError(
            f"Expected {EXPECTED_HISTORICAL_SCENARIOS} historical scenarios, "
            f"found {len(historical_scenarios)}."
        )
    unavailable = [
        scenario.scenario_id
        for scenario in historical_scenarios
        if scenario.end_date > as_of_date
    ]
    if unavailable:
        raise ValueError(
            f"Historical scenarios end after the as-of date {as_of_date.date()}: "
            f"{unavailable}"
        )

    historical_results = run_historical_scenarios(
        positions,
        returns,
        historical_scenarios,
    )
    hypothetical_results = run_hypothetical_scenarios(
        positions,
        returns,
        margin,
        stress_config["hypothetical_scenarios"],
    )
    if hypothetical_results["scenario_id"].nunique() != EXPECTED_HYPOTHETICAL_SCENARIOS:
        raise AssertionError("The required fourteen hypothetical scenarios were not generated.")

    stress_results = pd.concat(
        [
            historical_results.dropna(axis=1, how="all"),
            hypothetical_results.dropna(axis=1, how="all"),
        ],
        ignore_index=True,
        sort=False,
    )
    if stress_results["scenario_id"].nunique() != EXPECTED_TOTAL_SCENARIOS:
        raise AssertionError("The required twenty total stress scenarios were not generated.")
    stress_results = add_margin_adequacy(stress_results, margin)
    stress_results["as_of_date"] = as_of_date
    stress_results["model_version"] = model_version(project_config)
    stress_results = stress_results.sort_values(
        ["scenario_type", "scenario_id", "member_id"]
    ).reset_index(drop=True)

    reverse_cfg = stress_config["reverse_stress"]
    reverse_results = run_reverse_stress_tests(
        positions,
        margin,
        equity_securities=stress_config["hypothetical_scenarios"]["equity_securities"],
        maximum_shock_pct=float(reverse_cfg["maximum_shock_pct"]),
        tolerance=float(reverse_cfg["tolerance"]),
        maximum_iterations=int(reverse_cfg["maximum_iterations"]),
    )
    reverse_results["as_of_date"] = as_of_date
    reverse_results["model_version"] = model_version(project_config)

    manifest = build_manifest(historical_scenarios, hypothetical_results)

    stress_parquet = atomic_write_parquet(
        stress_results,
        "data/processed/stress_test_results.parquet",
    )
    reverse_parquet = atomic_write_parquet(
        reverse_results,
        "data/processed/reverse_stress_results.parquet",
    )

    evidence_dir = project_path("reports/evidence")
    evidence_dir.mkdir(parents=True, exist_ok=True)
    stress_csv = evidence_dir / "stress_test_results.csv"
    reverse_csv = evidence_dir / "reverse_stress_results.csv"
    stress_results.to_csv(stress_csv, index=False)
    reverse_results.to_csv(reverse_csv, index=False)

    manifest_path = project_path("data/manifests/stress_scenario_manifest.csv")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(manifest_path, index=False)

    worst = stress_results.sort_values(
        ["margin_shortfall", "stress_requirement"], ascending=[False, False]
    ).iloc[0]
    summary = {
        "status": "completed",
        "execution_timestamp_utc": utc_timestamp(),
        "as_of_date": as_of_date.date().isoformat(),
        "model_version": model_version(project_config),
        "configuration_status": stress_config.get("configuration_status"),
        "historical_scenario_count": int(
            manifest.loc[manifest["scenario_type"] == "historical", "scenario_id"].nunique()
        ),
        "hypothetical_scenario_count": int(
            manifest.loc[manifest["scenario_type"] == "hypothetical", "scenario_id"].nunique()
        ),
        "total_scenario_count": int(manifest["scenario_id"].nunique()),
        "member_count": int(len(position_members)),
        "stress_result_rows": int(len(stress_results)),
        "margin_breach_rows": int(stress_results["margin_breach_flag"].sum()),
        "members_with_at_least_one_breach": int(
            stress_results.loc[stress_results["margin_breach_flag"], "member_id"].nunique()
        ),
        "worst_scenario_id": str(worst["scenario_id"]),
        "worst_member_id": str(worst["member_id"]),
        "largest_margin_shortfall": float(worst["margin_shortfall"]),
        "outputs": {
            "stress_results_parquet": str(stress_parquet.relative_to(REPO_ROOT)),
            "reverse_results_parquet": str(reverse_parquet.relative_to(REPO_ROOT)),
            "stress_results_csv": str(stress_csv.relative_to(REPO_ROOT)),
            "reverse_results_csv": str(reverse_csv.relative_to(REPO_ROOT)),
            "scenario_manifest_csv": str(manifest_path.relative_to(REPO_ROOT)),
        },
    }
    summary_path = write_json(summary, "reports/evidence/stress_test_summary.json")

    print("Step 16 stress testing completed.")
    print(f"As-of date: {as_of_date.date()}")
    print(f"Historical scenarios: {summary['historical_scenario_count']}")
    print(f"Hypothetical scenarios: {summary['hypothetical_scenario_count']}")
    print(f"Total scenarios: {summary['total_scenario_count']}")
    print(f"Stress result rows: {len(stress_results)}")
    print(f"Margin-breach rows: {summary['margin_breach_rows']}")
    print(f"Scenario manifest: {manifest_path}")
    print(f"Stress results: {stress_parquet}")
    print(f"Reverse stress results: {reverse_parquet}")
    print(f"Evidence summary: {summary_path}")


if __name__ == "__main__":
    main()

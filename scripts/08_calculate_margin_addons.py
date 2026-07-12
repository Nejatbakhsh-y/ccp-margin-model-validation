"""Calculate member-level liquidity, concentration, gap-risk, and stress add-ons."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from _daily_margin_common import (
    atomic_write_parquet,
    load_positions,
    load_project_config,
    member_exposures,
    nested,
    project_path,
    utc_timestamp,
    write_json,
)


PRIMARY_PATH = "data/processed/primary_member_margin.parquet"
OUTPUT_PATH = "data/processed/margin_addons.parquet"
EVIDENCE_PATH = "reports/evidence/margin_addon_run_summary.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Calculation date in YYYY-MM-DD format.")
    return parser.parse_args()


def _cap(value: float, minimum: float, maximum: float | None) -> float:
    result = max(float(minimum), float(value))
    if maximum is not None:
        result = min(result, float(maximum))
    return result


def main() -> None:
    args = parse_args()
    config = load_project_config()
    primary_source = project_path(PRIMARY_PATH)
    if not primary_source.exists():
        raise FileNotFoundError(
            f"Primary model output not found: {primary_source}. "
            "Run scripts/06_run_primary_model.py first."
        )

    primary = pd.read_parquet(primary_source)
    primary["date"] = pd.to_datetime(primary["date"]).dt.normalize()
    if args.date:
        requested = pd.Timestamp(args.date).normalize()
        primary = primary.loc[primary["date"] == requested].copy()
        if primary.empty:
            raise ValueError(f"No primary-model rows exist for {requested.date()}.")
    else:
        primary = primary.loc[primary["date"] == primary["date"].max()].copy()

    as_of_date = pd.Timestamp(primary["date"].iloc[0]).normalize()
    positions = load_positions(as_of_date)
    exposures = member_exposures(positions).set_index("member_id")

    margin = nested(config, "margin", default={}) or {}
    base_cfg = margin.get("base_margin", {})
    liquidity_cfg = margin.get("liquidity_addon", {})
    concentration_cfg = margin.get("concentration_addon", {})
    gap_cfg = margin.get("gap_risk_addon", {})
    stress_cfg = margin.get("stress_buffer", {})

    liquidity_rates = {
        str(key).strip().lower(): float(value)
        for key, value in (liquidity_cfg.get("rates_by_bucket", {}) or {}).items()
    }
    gap_rates = {
        str(key).strip().lower(): float(value)
        for key, value in (gap_cfg.get("rates_by_asset_class", {}) or {}).items()
    }

    expected_liquidity = sorted(set(positions["liquidity_bucket"]))
    missing_liquidity = sorted(set(expected_liquidity).difference(liquidity_rates))
    if missing_liquidity:
        raise KeyError(
            "No configured liquidity rate for bucket(s): "
            + ", ".join(missing_liquidity)
        )

    expected_asset_classes = sorted(set(positions["asset_class"]))
    missing_asset_classes = sorted(set(expected_asset_classes).difference(gap_rates))
    if missing_asset_classes:
        raise KeyError(
            "No configured gap-risk rate for asset class(es): "
            + ", ".join(missing_asset_classes)
        )

    rows: list[dict[str, object]] = []
    run_timestamp = utc_timestamp()

    for primary_row in primary.sort_values("member_id").itertuples(index=False):
        member_id = str(primary_row.member_id)
        member_positions = positions.loc[positions["member_id"] == member_id].copy()
        if member_positions.empty:
            raise KeyError(f"No position records found for member {member_id}.")

        gross = float(exposures.loc[member_id, "gross_exposure"])
        net = float(exposures.loc[member_id, "net_exposure"])
        portfolio_value = float(exposures.loc[member_id, "portfolio_value"])

        raw_base = float(primary_row.base_var)
        base_margin = _cap(
            raw_base,
            float(base_cfg.get("floor_usd", 0.0)),
            base_cfg.get("cap_usd"),
        )

        member_positions["absolute_market_value"] = member_positions["market_value"].abs()

        raw_liquidity = float(
            sum(
                row.absolute_market_value * liquidity_rates[row.liquidity_bucket]
                for row in member_positions.itertuples(index=False)
            )
        )
        liquidity_maximum = (
            gross * float(liquidity_cfg["maximum_fraction_of_gross"])
            if liquidity_cfg.get("maximum_fraction_of_gross") is not None
            else None
        )
        liquidity_addon = _cap(
            raw_liquidity,
            float(liquidity_cfg.get("minimum_usd", 0.0)),
            liquidity_maximum,
        )

        if gross > 0.0:
            single_name_weights = (
                member_positions.groupby("security_id")["absolute_market_value"].sum()
                / gross
            )
            sector_weights = (
                member_positions.groupby("sector")["absolute_market_value"].sum()
                / gross
            )
            largest_name_weight = float(single_name_weights.max())
            largest_sector_weight = float(sector_weights.max())
        else:
            largest_name_weight = 0.0
            largest_sector_weight = 0.0

        single_threshold = float(
            concentration_cfg.get("single_name_threshold", 0.20)
        )
        sector_threshold = float(concentration_cfg.get("sector_threshold", 0.40))
        single_component = (
            max(0.0, largest_name_weight - single_threshold)
            * gross
            * float(concentration_cfg.get("single_name_rate", 0.10))
        )
        sector_component = (
            max(0.0, largest_sector_weight - sector_threshold)
            * gross
            * float(concentration_cfg.get("sector_rate", 0.05))
        )

        method = str(
            concentration_cfg.get("aggregation_method", "max")
        ).strip().lower()
        if method == "max":
            raw_concentration = max(single_component, sector_component)
        elif method == "sum":
            raw_concentration = single_component + sector_component
        else:
            raise ValueError(
                "margin.concentration_addon.aggregation_method must be 'max' or 'sum'."
            )

        concentration_maximum = (
            gross * float(concentration_cfg["maximum_fraction_of_gross"])
            if concentration_cfg.get("maximum_fraction_of_gross") is not None
            else None
        )
        concentration_addon = _cap(
            raw_concentration,
            float(concentration_cfg.get("minimum_usd", 0.0)),
            concentration_maximum,
        )

        raw_gap = float(
            sum(
                row.absolute_market_value * gap_rates[row.asset_class]
                for row in member_positions.itertuples(index=False)
            )
        )
        gap_maximum = (
            gross * float(gap_cfg["maximum_fraction_of_gross"])
            if gap_cfg.get("maximum_fraction_of_gross") is not None
            else None
        )
        gap_risk_addon = _cap(
            raw_gap,
            float(gap_cfg.get("minimum_usd", 0.0)),
            gap_maximum,
        )

        required_coverage_ratio = float(
            stress_cfg.get("required_coverage_ratio", 1.0)
        )
        stress_requirement = required_coverage_ratio * float(primary_row.worst_loss)
        pre_stress_margin = (
            base_margin + liquidity_addon + concentration_addon + gap_risk_addon
        )
        raw_stress_buffer = max(0.0, stress_requirement - pre_stress_margin)
        stress_buffer = _cap(
            raw_stress_buffer,
            0.0,
            stress_cfg.get("maximum_buffer_usd"),
        )

        total_margin = (
            base_margin
            + liquidity_addon
            + concentration_addon
            + gap_risk_addon
            + stress_buffer
        )

        rows.append(
            {
                "date": as_of_date,
                "member_id": member_id,
                "base_var": base_margin,
                "liquidity_addon": liquidity_addon,
                "concentration_addon": concentration_addon,
                "gap_risk_addon": gap_risk_addon,
                "stress_buffer": stress_buffer,
                "total_margin": total_margin,
                "portfolio_value": portfolio_value,
                "gross_exposure": gross,
                "net_exposure": net,
                "largest_single_name_weight": largest_name_weight,
                "largest_sector_weight": largest_sector_weight,
                "model_version": primary_row.model_version,
                "calculation_timestamp_utc": run_timestamp,
            }
        )

    results = pd.DataFrame(rows).sort_values(["date", "member_id"])
    component_sum = results[
        [
            "base_var",
            "liquidity_addon",
            "concentration_addon",
            "gap_risk_addon",
            "stress_buffer",
        ]
    ].sum(axis=1)
    if not np.allclose(results["total_margin"], component_sum, rtol=0.0, atol=1.0e-8):
        raise AssertionError("Total-margin reconciliation failed.")

    output = atomic_write_parquet(results, OUTPUT_PATH)
    write_json(
        {
            "status": "passed",
            "calculation_date": str(as_of_date.date()),
            "member_count": int(results["member_id"].nunique()),
            "total_margin_sum": float(results["total_margin"].sum()),
            "maximum_reconciliation_error": float(
                (results["total_margin"] - component_sum).abs().max()
            ),
            "configuration_status": nested(
                config, "project", "configuration_status", default="unknown"
            ),
            "output": str(output),
            "calculation_timestamp_utc": run_timestamp,
        },
        EVIDENCE_PATH,
    )

    print(f"MARGIN ADD-ONS PASSED: {len(results)} member rows")
    print(f"Created: {output}")


if __name__ == "__main__":
    main()

"""Run the primary historical-simulation margin model for one as-of date."""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from _daily_margin_common import (
    atomic_write_parquet,
    compound_overlapping_returns,
    load_positions,
    load_project_config,
    load_returns,
    member_exposures,
    model_version,
    nested,
    quantile_higher,
    require_risk_factors,
    resolve_as_of_date,
    utc_timestamp,
    write_json,
)


OUTPUT_PATH = "data/processed/primary_member_margin.parquet"
PNL_OUTPUT_PATH = "data/processed/primary_model_pnl_distribution.parquet"
EVIDENCE_PATH = "reports/evidence/primary_model_run_summary.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--date", help="Requested calculation date in YYYY-MM-DD format."
    )
    parser.add_argument(
        "--mpor-days",
        type=int,
        help="Margin period of risk. Defaults to the maximum configured primary MPOR.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_project_config()
    returns = load_returns()
    as_of_date = resolve_as_of_date(returns, args.date)
    positions = load_positions(as_of_date)

    confidence = float(
        nested(config, "primary_model", "confidence_level", default=0.99)
    )
    lookback = int(nested(config, "primary_model", "lookback_days", default=500))
    configured_mpors = nested(config, "primary_model", "mpor_days", default=[1])
    mpor_days = int(args.mpor_days or max(int(value) for value in configured_mpors))
    missing_policy = str(
        nested(config, "primary_model", "missing_risk_factor_policy", default="raise")
    )

    positions, relevant_returns = require_risk_factors(
        positions, returns.loc[:as_of_date], missing_policy
    )

    required_daily_rows = lookback + mpor_days - 1
    daily_window = relevant_returns.tail(required_daily_rows)
    multi_day = compound_overlapping_returns(daily_window, mpor_days).dropna(how="any")
    multi_day = multi_day.tail(lookback)

    if len(multi_day) < min(30, lookback):
        raise ValueError(
            f"Insufficient observations for primary model: {len(multi_day)} available."
        )

    run_timestamp = utc_timestamp()
    version = model_version(config)
    exposure_table = member_exposures(positions).set_index("member_id")
    result_rows: list[dict[str, object]] = []
    pnl_frames: list[pd.DataFrame] = []

    for member_id, member_positions in positions.groupby("member_id", sort=True):
        exposures = (
            member_positions.set_index("security_id")["market_value"]
            .reindex(multi_day.columns)
            .fillna(0.0)
        )
        pnl = multi_day.mul(exposures, axis=1).sum(axis=1)
        losses = -pnl.to_numpy(dtype=float)

        base_var = max(0.0, quantile_higher(losses, confidence))
        tail_losses = losses[losses >= base_var]
        expected_shortfall = max(
            0.0, float(tail_losses.mean()) if tail_losses.size else base_var
        )
        worst_loss = max(0.0, float(np.max(losses)))

        member_exposure = exposure_table.loc[member_id]
        result_rows.append(
            {
                "date": as_of_date,
                "member_id": member_id,
                "base_var": base_var,
                "expected_shortfall": expected_shortfall,
                "worst_loss": worst_loss,
                "portfolio_value": float(member_exposure["portfolio_value"]),
                "gross_exposure": float(member_exposure["gross_exposure"]),
                "net_exposure": float(member_exposure["net_exposure"]),
                "confidence_level": confidence,
                "lookback_days": lookback,
                "mpor_days": mpor_days,
                "observations": int(len(multi_day)),
                "model_name": "primary_historical_simulation",
                "model_version": version,
                "calculation_timestamp_utc": run_timestamp,
            }
        )

        pnl_frames.append(
            pd.DataFrame(
                {
                    "date": as_of_date,
                    "member_id": member_id,
                    "simulation_end_date": multi_day.index,
                    "pnl": pnl.to_numpy(dtype=float),
                    "loss": losses,
                    "mpor_days": mpor_days,
                    "model_version": version,
                }
            )
        )

    results = pd.DataFrame(result_rows).sort_values(["date", "member_id"])
    pnl_distribution = pd.concat(pnl_frames, ignore_index=True).sort_values(
        ["date", "member_id", "simulation_end_date"]
    )

    output = atomic_write_parquet(results, OUTPUT_PATH)
    pnl_output = atomic_write_parquet(pnl_distribution, PNL_OUTPUT_PATH)
    write_json(
        {
            "status": "passed",
            "calculation_date": str(as_of_date.date()),
            "member_count": int(results["member_id"].nunique()),
            "confidence_level": confidence,
            "lookback_days": lookback,
            "mpor_days": mpor_days,
            "observations_per_member": int(len(multi_day)),
            "model_version": version,
            "output": str(output),
            "pnl_distribution_output": str(pnl_output),
            "calculation_timestamp_utc": run_timestamp,
        },
        EVIDENCE_PATH,
    )

    print(f"PRIMARY MODEL PASSED: {len(results)} member rows")
    print(f"Created: {output}")
    print(f"Created: {pnl_output}")


if __name__ == "__main__":
    main()

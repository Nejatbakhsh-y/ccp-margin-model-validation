"""Run the challenger parametric EWMA VaR model for one as-of date."""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from scipy.stats import norm

from _daily_margin_common import (
    atomic_write_parquet,
    ewma_covariance,
    load_positions,
    load_project_config,
    load_returns,
    member_exposures,
    model_version,
    nested,
    require_risk_factors,
    resolve_as_of_date,
    utc_timestamp,
    write_json,
)


OUTPUT_PATH = "data/processed/challenger_member_margin.parquet"
EVIDENCE_PATH = "reports/evidence/challenger_model_run_summary.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--date", help="Requested calculation date in YYYY-MM-DD format."
    )
    parser.add_argument(
        "--mpor-days",
        type=int,
        help="Margin period of risk. Defaults to the maximum configured challenger MPOR.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_project_config()
    returns = load_returns()
    as_of_date = resolve_as_of_date(returns, args.date)
    positions = load_positions(as_of_date)

    confidence = float(
        nested(config, "challenger_model", "confidence_level", default=0.99)
    )
    lookback = int(nested(config, "challenger_model", "lookback_days", default=500))
    decay = float(nested(config, "challenger_model", "ewma_lambda", default=0.94))
    include_mean = bool(
        nested(config, "challenger_model", "include_mean", default=False)
    )
    eigenvalue_floor = float(
        nested(
            config,
            "challenger_model",
            "covariance_controls",
            "eigenvalue_floor",
            default=1.0e-12,
        )
    )
    configured_mpors = nested(config, "challenger_model", "mpor_days", default=[1])
    mpor_days = int(args.mpor_days or max(int(value) for value in configured_mpors))
    missing_policy = str(
        nested(
            config, "challenger_model", "missing_risk_factor_policy", default="raise"
        )
    )

    positions, relevant_returns = require_risk_factors(
        positions, returns.loc[:as_of_date], missing_policy
    )
    window = relevant_returns.tail(lookback).dropna(how="any")
    if len(window) < min(30, lookback):
        raise ValueError(
            f"Insufficient observations for challenger model: {len(window)} available."
        )

    covariance = ewma_covariance(window, decay, include_mean, eigenvalue_floor)
    z_score = float(norm.ppf(confidence))
    run_timestamp = utc_timestamp()
    version = model_version(config)
    exposure_table = member_exposures(positions).set_index("member_id")
    rows: list[dict[str, object]] = []

    for member_id, member_positions in positions.groupby("member_id", sort=True):
        exposure_vector = (
            member_positions.set_index("security_id")["market_value"]
            .reindex(window.columns)
            .fillna(0.0)
            .to_numpy(dtype=float)
        )

        daily_variance = float(exposure_vector @ covariance @ exposure_vector)
        daily_variance = max(0.0, daily_variance)
        horizon_volatility = float(np.sqrt(daily_variance * mpor_days))
        challenger_var = max(0.0, z_score * horizon_volatility)

        member_exposure = exposure_table.loc[member_id]
        rows.append(
            {
                "date": as_of_date,
                "member_id": member_id,
                "challenger_var": challenger_var,
                "parametric_volatility": horizon_volatility,
                "portfolio_value": float(member_exposure["portfolio_value"]),
                "gross_exposure": float(member_exposure["gross_exposure"]),
                "net_exposure": float(member_exposure["net_exposure"]),
                "confidence_level": confidence,
                "lookback_days": lookback,
                "ewma_lambda": decay,
                "mpor_days": mpor_days,
                "observations": int(len(window)),
                "model_name": "challenger_parametric_ewma",
                "model_version": version,
                "calculation_timestamp_utc": run_timestamp,
            }
        )

    results = pd.DataFrame(rows).sort_values(["date", "member_id"])
    output = atomic_write_parquet(results, OUTPUT_PATH)
    write_json(
        {
            "status": "passed",
            "calculation_date": str(as_of_date.date()),
            "member_count": int(results["member_id"].nunique()),
            "confidence_level": confidence,
            "lookback_days": lookback,
            "ewma_lambda": decay,
            "mpor_days": mpor_days,
            "observations_per_member": int(len(window)),
            "model_version": version,
            "output": str(output),
            "calculation_timestamp_utc": run_timestamp,
        },
        EVIDENCE_PATH,
    )

    print(f"CHALLENGER MODEL PASSED: {len(results)} member rows")
    print(f"Created: {output}")


if __name__ == "__main__":
    main()

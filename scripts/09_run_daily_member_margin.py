"""Assemble and preserve the daily clearing-member margin dataset."""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from _daily_margin_common import (
    project_path,
    upsert_parquet,
    utc_timestamp,
    write_json,
)


PRIMARY_PATH = "data/processed/primary_member_margin.parquet"
CHALLENGER_PATH = "data/processed/challenger_member_margin.parquet"
ADDON_PATH = "data/processed/margin_addons.parquet"
OUTPUT_PATH = "data/processed/daily_member_margin.parquet"
EVIDENCE_PATH = "reports/evidence/daily_member_margin_run_summary.json"

REQUIRED_COLUMNS = [
    "date",
    "member_id",
    "base_var",
    "liquidity_addon",
    "concentration_addon",
    "gap_risk_addon",
    "stress_buffer",
    "total_margin",
    "portfolio_value",
    "gross_exposure",
    "net_exposure",
    "model_version",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Calculation date in YYYY-MM-DD format.")
    return parser.parse_args()


def _read_latest(path: str, requested: str | None) -> pd.DataFrame:
    source = project_path(path)
    if not source.exists():
        raise FileNotFoundError(f"Required Step 13 input not found: {source}")

    frame = pd.read_parquet(source)
    frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()

    if requested:
        target = pd.Timestamp(requested).normalize()
        frame = frame.loc[frame["date"] == target].copy()
        if frame.empty:
            raise ValueError(f"No rows for {target.date()} in {source.name}.")
    else:
        frame = frame.loc[frame["date"] == frame["date"].max()].copy()

    if frame.duplicated(["date", "member_id"]).any():
        raise ValueError(f"Duplicate date/member rows found in {source.name}.")
    return frame


def main() -> None:
    args = parse_args()
    primary = _read_latest(PRIMARY_PATH, args.date)
    challenger = _read_latest(CHALLENGER_PATH, args.date)
    addons = _read_latest(ADDON_PATH, args.date)

    keys = ["date", "member_id"]
    primary_keys = set(map(tuple, primary[keys].astype(str).to_numpy()))
    challenger_keys = set(map(tuple, challenger[keys].astype(str).to_numpy()))
    addon_keys = set(map(tuple, addons[keys].astype(str).to_numpy()))
    if not (primary_keys == challenger_keys == addon_keys):
        raise ValueError(
            "Primary, challenger, and add-on outputs do not contain identical date/member keys."
        )

    challenger_subset = challenger[
        keys + ["challenger_var", "parametric_volatility", "mpor_days"]
    ].rename(columns={"mpor_days": "challenger_mpor_days"})

    final = addons.merge(
        challenger_subset,
        on=keys,
        how="inner",
        validate="one_to_one",
    )
    primary_subset = primary[
        keys + ["expected_shortfall", "worst_loss", "mpor_days"]
    ].rename(columns={"mpor_days": "primary_mpor_days"})
    final = final.merge(primary_subset, on=keys, how="inner", validate="one_to_one")

    final["primary_to_challenger_ratio"] = np.where(
        final["challenger_var"] > 0.0,
        final["base_var"] / final["challenger_var"],
        np.nan,
    )
    final["calculation_timestamp_utc"] = utc_timestamp()

    missing = [column for column in REQUIRED_COLUMNS if column not in final.columns]
    if missing:
        raise AssertionError(f"Final output is missing required columns: {missing}")

    components = final[
        [
            "base_var",
            "liquidity_addon",
            "concentration_addon",
            "gap_risk_addon",
            "stress_buffer",
        ]
    ].sum(axis=1)
    reconciliation_error = (final["total_margin"] - components).abs()
    if float(reconciliation_error.max()) > 1.0e-8:
        raise AssertionError(
            f"Total margin failed reconciliation; max error={reconciliation_error.max()}."
        )
    if (final["total_margin"] < 0.0).any():
        raise AssertionError("Negative total margin is not permitted.")

    ordered = REQUIRED_COLUMNS + [
        "challenger_var",
        "expected_shortfall",
        "worst_loss",
        "parametric_volatility",
        "primary_to_challenger_ratio",
        "primary_mpor_days",
        "challenger_mpor_days",
        "largest_single_name_weight",
        "largest_sector_weight",
        "calculation_timestamp_utc",
    ]
    final = final[ordered].sort_values(keys).reset_index(drop=True)

    output = upsert_parquet(final, OUTPUT_PATH, keys=keys)
    full_history = pd.read_parquet(output)
    write_json(
        {
            "status": "passed",
            "calculation_date": str(pd.Timestamp(final["date"].iloc[0]).date()),
            "rows_written": int(len(final)),
            "member_count": int(final["member_id"].nunique()),
            "history_row_count": int(len(full_history)),
            "history_start_date": str(
                pd.to_datetime(full_history["date"]).min().date()
            ),
            "history_end_date": str(pd.to_datetime(full_history["date"]).max().date()),
            "total_margin_sum": float(final["total_margin"].sum()),
            "maximum_reconciliation_error": float(reconciliation_error.max()),
            "output": str(output),
            "calculation_timestamp_utc": final["calculation_timestamp_utc"].iloc[0],
        },
        EVIDENCE_PATH,
    )

    print(f"DAILY MEMBER MARGIN PASSED: {len(final)} member rows")
    print(f"Created/updated: {output}")
    print("Required columns confirmed:")
    for column in REQUIRED_COLUMNS:
        print(f"  - {column}")


if __name__ == "__main__":
    main()

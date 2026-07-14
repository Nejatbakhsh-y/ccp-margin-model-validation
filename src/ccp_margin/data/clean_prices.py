"""Clean raw market prices without concealing data-quality exceptions."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ccp_margin.data.manifests import (
    find_project_root,
    load_project_config,
    make_run_id,
    record_dataset,
    utc_now,
)


NUMERIC_COLUMNS = [
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
    "dividends",
    "stock_splits",
]


def _stale_run_length(series: pd.Series) -> pd.Series:
    """Count consecutive equal, non-missing observations."""
    values = series.copy()
    new_run = values.ne(values.shift()) | values.isna()
    run_length = values.groupby(new_run.cumsum()).cumcount() + 1
    return run_length.where(values.notna(), 0).astype("int64")


def clean_market_prices(
    *,
    root: Path | None = None,
) -> pd.DataFrame:
    project_root = root or find_project_root()
    config = load_project_config(project_root)
    data_config: dict[str, Any] = config["data"]
    market_config: dict[str, Any] = data_config.get("market", {})

    raw_path = project_root / "data" / "raw" / "market" / "market_prices_raw.parquet"
    if not raw_path.exists():
        raise FileNotFoundError(
            f"Raw market data not found: {raw_path}. Run download_market.py first."
        )

    frame = pd.read_parquet(raw_path)
    required = {"date", "security_id", "adjusted_close", "source"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(
            "Raw market data is missing required columns: " + ", ".join(sorted(missing))
        )

    frame = frame.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    frame["security_id"] = frame["security_id"].astype("string").str.strip().str.upper()
    frame = frame.dropna(subset=["date", "security_id"])

    for column in NUMERIC_COLUMNS:
        if column not in frame.columns:
            frame[column] = np.nan
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    if "source_priority" not in frame.columns:
        source_rank = {"yahoo": 1, "stooq": 2}
        frame["source_priority"] = (
            frame["source"].astype(str).str.lower().map(source_rank).fillna(99)
        )

    frame["duplicate_security_date_raw"] = frame.duplicated(
        ["security_id", "date"], keep=False
    )

    frame = frame.sort_values(
        ["security_id", "date", "source_priority"],
        kind="mergesort",
    )
    frame = frame.drop_duplicates(
        ["security_id", "date"],
        keep="first",
    )

    frame["is_non_positive_price"] = frame["adjusted_close"].notna() & (
        frame["adjusted_close"] <= 0
    )
    frame["model_price"] = frame["adjusted_close"].where(frame["adjusted_close"] > 0)

    reference_security = str(
        market_config.get("calendar_reference_security", "SPY")
    ).upper()
    available_counts = (
        frame.dropna(subset=["model_price"])
        .groupby("security_id")["date"]
        .nunique()
        .sort_values(ascending=False)
    )
    if available_counts.empty:
        raise RuntimeError("No valid positive adjusted prices are available.")

    if reference_security not in available_counts.index:
        reference_security = str(available_counts.index[0])

    reference_dates = (
        frame.loc[
            (frame["security_id"] == reference_security) & frame["model_price"].notna(),
            "date",
        ]
        .drop_duplicates()
        .sort_values()
    )
    if reference_dates.empty:
        raise RuntimeError("The reference security has no valid dates.")

    securities = sorted(frame["security_id"].dropna().unique().tolist())
    panel_index = pd.MultiIndex.from_product(
        [securities, reference_dates],
        names=["security_id", "date"],
    )

    panel = frame.set_index(["security_id", "date"]).reindex(panel_index)
    panel = panel.reset_index()
    panel["calendar_reference_security"] = reference_security

    security_bounds = (
        frame.loc[frame["model_price"].notna()]
        .groupby("security_id", as_index=False)["date"]
        .agg(
            security_first_valid_date="min",
            security_last_valid_date="max",
        )
    )
    panel = panel.merge(
        security_bounds,
        on="security_id",
        how="left",
        validate="many_to_one",
    )

    panel["pre_inception"] = panel["security_first_valid_date"].notna() & (
        panel["date"] < panel["security_first_valid_date"]
    )
    panel["post_last_observation"] = panel["security_last_valid_date"].notna() & (
        panel["date"] > panel["security_last_valid_date"]
    )
    panel["active_history"] = (
        panel["security_first_valid_date"].notna()
        & panel["security_last_valid_date"].notna()
        & ~panel["pre_inception"]
        & ~panel["post_last_observation"]
    )

    panel["calendar_gap"] = panel["source"].isna()
    panel["model_price_missing"] = panel["model_price"].isna()
    panel["active_calendar_gap"] = panel["active_history"] & panel["calendar_gap"]
    panel["active_model_price_missing"] = (
        panel["active_history"] & panel["model_price_missing"]
    )

    panel = panel.sort_values(
        ["security_id", "date"],
        kind="mergesort",
    ).reset_index(drop=True)

    panel["return_1d"] = panel.groupby("security_id", sort=False)[
        "model_price"
    ].pct_change(fill_method=None)
    panel["log_return_1d"] = np.log1p(panel["return_1d"])
    panel["stale_run_length"] = panel.groupby(
        "security_id", group_keys=False, sort=False
    )["model_price"].transform(_stale_run_length)

    panel["adjustment_ratio"] = (panel["close"] / panel["adjusted_close"]).replace(
        [np.inf, -np.inf], np.nan
    )
    panel["adjustment_ratio_change"] = panel.groupby("security_id", sort=False)[
        "adjustment_ratio"
    ].pct_change(fill_method=None)

    panel["clean_run_id"] = make_run_id()
    panel["cleaned_timestamp_utc"] = utc_now()

    output_path = project_root / "data" / "processed" / "market_prices_clean.parquet"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(output_path, index=False)

    record_dataset(
        dataset_name="market_prices_clean",
        dataset_path=output_path,
        root=project_root,
        request_parameters={
            "raw_dataset": "data/raw/market/market_prices_raw.parquet",
            "reference_security": reference_security,
            "price_field": str(data_config.get("price_field", "adjusted_close")),
            "cleaning_version": "2.0-pre-inception-aware",
        },
        run_id=str(panel["clean_run_id"].iloc[0]),
    )

    return panel


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    cleaned = clean_market_prices()
    print(
        "Price cleaning completed: "
        f"{len(cleaned):,} panel rows, "
        f"{cleaned['security_id'].nunique()} securities."
    )
    print(f"Reference calendar: {cleaned['calendar_reference_security'].iloc[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

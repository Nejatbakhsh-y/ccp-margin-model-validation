"""Portfolio exposure calculations for synthetic clearing members."""

from __future__ import annotations

import numpy as np
import pandas as pd

_GROUP_KEYS = ["valuation_date", "member_id", "portfolio_id"]


def calculate_exposures(positions: pd.DataFrame) -> pd.DataFrame:
    """Calculate daily gross, long, short, and net portfolio exposures."""

    required = {*_GROUP_KEYS, "security_id", "market_value"}
    missing = sorted(required - set(positions.columns))
    if missing:
        raise ValueError(f"Position data is missing required columns: {missing}")

    frame = positions.copy()
    frame["market_value"] = pd.to_numeric(frame["market_value"], errors="raise")
    frame["absolute_market_value"] = frame["market_value"].abs()
    frame["long_market_value"] = frame["market_value"].clip(lower=0.0)
    frame["short_market_value"] = -frame["market_value"].clip(upper=0.0)

    grouped = frame.groupby(_GROUP_KEYS, sort=True, observed=True)
    result = grouped.agg(
        gross_exposure=("absolute_market_value", "sum"),
        long_exposure=("long_market_value", "sum"),
        short_exposure=("short_market_value", "sum"),
        net_exposure=("market_value", "sum"),
        position_count=("security_id", "nunique"),
    ).reset_index()

    net_abs = result["net_exposure"].abs()
    result["gross_to_net_ratio"] = np.where(
        net_abs > 0.0, result["gross_exposure"] / net_abs, np.inf
    )
    result["short_gross_share"] = np.where(
        result["gross_exposure"] > 0.0,
        result["short_exposure"] / result["gross_exposure"],
        0.0,
    )
    result["net_gross_ratio"] = np.where(
        result["gross_exposure"] > 0.0,
        result["net_exposure"] / result["gross_exposure"],
        0.0,
    )

    return result.sort_values(_GROUP_KEYS, kind="mergesort").reset_index(drop=True)


def calculate_exposure_breakdown(
    positions: pd.DataFrame, dimension: str
) -> pd.DataFrame:
    """Calculate signed and gross exposure by sector, asset class, or liquidity."""

    if dimension not in {"sector", "asset_class", "liquidity_bucket", "security_id"}:
        raise ValueError(
            "dimension must be sector, asset_class, liquidity_bucket, or security_id."
        )
    required = {*_GROUP_KEYS, dimension, "market_value"}
    missing = sorted(required - set(positions.columns))
    if missing:
        raise ValueError(f"Position data is missing required columns: {missing}")

    frame = positions.copy()
    frame["gross_market_value"] = frame["market_value"].abs()
    grouped = frame.groupby(_GROUP_KEYS + [dimension], sort=True, observed=True)
    result = grouped.agg(
        net_exposure=("market_value", "sum"),
        gross_exposure=("gross_market_value", "sum"),
    ).reset_index()
    portfolio_gross = result.groupby(_GROUP_KEYS, sort=True)[
        "gross_exposure"
    ].transform("sum")
    result["gross_exposure_share"] = np.where(
        portfolio_gross > 0.0, result["gross_exposure"] / portfolio_gross, 0.0
    )
    return result.sort_values(_GROUP_KEYS + [dimension], kind="mergesort").reset_index(
        drop=True
    )

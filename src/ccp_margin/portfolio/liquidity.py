"""Liquidity-risk metrics for synthetic clearing-member portfolios."""

from __future__ import annotations

import numpy as np
import pandas as pd

_GROUP_KEYS = ["valuation_date", "member_id", "portfolio_id"]
_LIQUIDITY_SCORE = {"High": 1.0, "Medium": 3.0, "Low": 5.0}
_STRESS_HAIRCUT = {"High": 0.005, "Medium": 0.015, "Low": 0.040}


def calculate_liquidity_metrics(positions: pd.DataFrame) -> pd.DataFrame:
    """Calculate bucket shares, weighted liquidity score, and stress add-on."""

    required = {*_GROUP_KEYS, "market_value", "liquidity_bucket"}
    missing = sorted(required - set(positions.columns))
    if missing:
        raise ValueError(f"Position data is missing required columns: {missing}")

    frame = positions.copy()
    frame["liquidity_bucket"] = frame["liquidity_bucket"].astype("string").str.title()
    invalid = sorted(set(frame["liquidity_bucket"].dropna()) - set(_LIQUIDITY_SCORE))
    if invalid:
        raise ValueError(f"Unsupported liquidity buckets: {invalid}")

    frame["absolute_market_value"] = frame["market_value"].abs()
    frame["liquidity_score_amount"] = frame["absolute_market_value"] * frame[
        "liquidity_bucket"
    ].map(_LIQUIDITY_SCORE).astype(float)
    frame["liquidity_stress_add_on"] = frame["absolute_market_value"] * frame[
        "liquidity_bucket"
    ].map(_STRESS_HAIRCUT).astype(float)

    grouped = frame.groupby(_GROUP_KEYS, sort=True, observed=True)
    result = grouped.agg(
        gross_exposure=("absolute_market_value", "sum"),
        liquidity_score_amount=("liquidity_score_amount", "sum"),
        liquidity_stress_add_on=("liquidity_stress_add_on", "sum"),
    ).reset_index()

    bucket_amounts = (
        frame.pivot_table(
            index=_GROUP_KEYS,
            columns="liquidity_bucket",
            values="absolute_market_value",
            aggfunc="sum",
            fill_value=0.0,
            observed=True,
        )
        .rename_axis(columns=None)
        .reset_index()
    )
    for bucket in ("High", "Medium", "Low"):
        if bucket not in bucket_amounts.columns:
            bucket_amounts[bucket] = 0.0
        bucket_amounts = bucket_amounts.rename(
            columns={bucket: f"{bucket.lower()}_liquidity_exposure"}
        )

    result = result.merge(bucket_amounts, on=_GROUP_KEYS, how="left", validate="one_to_one")
    result["weighted_liquidity_score"] = np.where(
        result["gross_exposure"] > 0.0,
        result["liquidity_score_amount"] / result["gross_exposure"],
        0.0,
    )
    for bucket in ("high", "medium", "low"):
        result[f"{bucket}_liquidity_share"] = np.where(
            result["gross_exposure"] > 0.0,
            result[f"{bucket}_liquidity_exposure"] / result["gross_exposure"],
            0.0,
        )
    result["liquidity_stressed_flag"] = (
        (result["weighted_liquidity_score"] >= 3.5)
        | (result["low_liquidity_share"] >= 0.30)
    )
    result = result.drop(columns=["liquidity_score_amount"])
    return result.sort_values(_GROUP_KEYS, kind="mergesort").reset_index(drop=True)


def liquidity_bucket_exposures(positions: pd.DataFrame) -> pd.DataFrame:
    """Return detailed gross exposure and share by liquidity bucket."""

    required = {*_GROUP_KEYS, "market_value", "liquidity_bucket"}
    missing = sorted(required - set(positions.columns))
    if missing:
        raise ValueError(f"Position data is missing required columns: {missing}")

    frame = positions.copy()
    frame["gross_exposure"] = frame["market_value"].abs()
    result = (
        frame.groupby(_GROUP_KEYS + ["liquidity_bucket"], sort=True, observed=True)[
            "gross_exposure"
        ]
        .sum()
        .reset_index()
    )
    total = result.groupby(_GROUP_KEYS, sort=True)["gross_exposure"].transform("sum")
    result["gross_exposure_share"] = np.where(
        total > 0.0, result["gross_exposure"] / total, 0.0
    )
    return result.sort_values(
        _GROUP_KEYS + ["liquidity_bucket"], kind="mergesort"
    ).reset_index(drop=True)

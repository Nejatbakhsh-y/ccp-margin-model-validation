"""Concentration metrics for synthetic clearing-member portfolios."""

from __future__ import annotations

import numpy as np
import pandas as pd

_GROUP_KEYS = ["valuation_date", "member_id", "portfolio_id"]


def calculate_concentration_metrics(positions: pd.DataFrame) -> pd.DataFrame:
    """Calculate HHI, effective position count, and top-weight measures."""

    required = {*_GROUP_KEYS, "security_id", "market_value"}
    missing = sorted(required - set(positions.columns))
    if missing:
        raise ValueError(f"Position data is missing required columns: {missing}")

    frame = positions.copy()
    frame["absolute_market_value"] = frame["market_value"].abs()
    rows: list[dict[str, object]] = []

    for keys, group in frame.groupby(_GROUP_KEYS, sort=True, observed=True):
        by_security = group.groupby("security_id", sort=True)[
            "absolute_market_value"
        ].sum()
        gross = float(by_security.sum())
        if gross <= 0.0:
            weights = np.zeros(len(by_security), dtype=float)
        else:
            weights = by_security.to_numpy(dtype=float) / gross
        descending = np.sort(weights)[::-1]
        hhi = float(np.square(weights).sum())
        rows.append(
            {
                "valuation_date": keys[0],
                "member_id": keys[1],
                "portfolio_id": keys[2],
                "gross_exposure": gross,
                "position_count": int(len(by_security)),
                "hhi": hhi,
                "effective_position_count": float(1.0 / hhi) if hhi > 0.0 else 0.0,
                "largest_position_weight": float(descending[:1].sum()),
                "top_3_weight": float(descending[:3].sum()),
                "top_5_weight": float(descending[:5].sum()),
                "concentration_flag": bool(
                    (descending[:1].sum() > 0.35) or (hhi > 0.25)
                ),
            }
        )

    result = pd.DataFrame(rows)
    return result.sort_values(_GROUP_KEYS, kind="mergesort").reset_index(drop=True)


def calculate_dimension_concentration(
    positions: pd.DataFrame, dimension: str
) -> pd.DataFrame:
    """Calculate concentration by sector, asset class, or liquidity bucket."""

    if dimension not in {"sector", "asset_class", "liquidity_bucket"}:
        raise ValueError("dimension must be sector, asset_class, or liquidity_bucket.")
    required = {*_GROUP_KEYS, dimension, "market_value"}
    missing = sorted(required - set(positions.columns))
    if missing:
        raise ValueError(f"Position data is missing required columns: {missing}")

    frame = positions.copy()
    frame["absolute_market_value"] = frame["market_value"].abs()
    by_dimension = (
        frame.groupby(_GROUP_KEYS + [dimension], sort=True, observed=True)[
            "absolute_market_value"
        ]
        .sum()
        .reset_index()
    )
    gross = by_dimension.groupby(_GROUP_KEYS, sort=True)[
        "absolute_market_value"
    ].transform("sum")
    by_dimension["weight"] = np.where(
        gross > 0.0, by_dimension["absolute_market_value"] / gross, 0.0
    )
    return by_dimension.sort_values(
        _GROUP_KEYS + [dimension], kind="mergesort"
    ).reset_index(drop=True)

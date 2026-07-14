"""Liquidity add-on for the CCP margin framework.

Business rationale
------------------
The primary VaR model may not fully capture liquidation costs, bid-ask spread,
market depth, or the additional cost of exiting positions during stressed
conditions. This component applies approved liquidation-cost rates to gross
position market values by liquidity bucket.

Formula
-------
For member m and position i::

    RawLiquidity_m = sum_i(abs(MV_i) * Rate[Bucket_i])
    LiquidityAddon_m = min(max(RawLiquidity_m, FloorUSD), CapFraction * GrossMV_m)

The cap is optional. Unknown buckets must either have an explicitly approved
rate or cause calculation failure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np
import pandas as pd


BUSINESS_RATIONALE = (
    "Covers liquidation cost and market-depth risk not fully represented in base VaR."
)
KNOWN_LIMITATIONS = (
    "Bucket rates are simplified proxies for liquidation cost and do not model "
    "order-book depth, nonlinear market impact, time-to-liquidate, or correlated "
    "member liquidations unless those effects are embedded in the approved rates."
)


@dataclass(frozen=True)
class LiquidityAddonResult:
    member_addon: pd.DataFrame
    attribution: pd.DataFrame
    metadata: dict[str, Any]


def calculate_liquidity_addon(
    positions: pd.DataFrame,
    *,
    rates_by_bucket: Mapping[str, float],
    parameter_source: str,
    member_col: str = "member_id",
    security_col: str = "security_id",
    market_value_col: str = "market_value",
    liquidity_bucket_col: str = "liquidity_bucket",
    minimum_usd: float = 0.0,
    maximum_fraction_of_gross: float | None = None,
) -> LiquidityAddonResult:
    """Calculate member-level liquidity add-ons with position attribution."""

    _validate_limits(minimum_usd, maximum_fraction_of_gross)
    required = {member_col, market_value_col, liquidity_bucket_col}
    missing = required.difference(positions.columns)
    if missing:
        raise KeyError(f"Missing required columns: {sorted(missing)}")
    if not parameter_source.strip():
        raise ValueError("parameter_source must be documented")

    normalized_rates = {str(k): float(v) for k, v in rates_by_bucket.items()}
    if not normalized_rates:
        raise ValueError("rates_by_bucket must not be empty")
    if any((not np.isfinite(v)) or v < 0 for v in normalized_rates.values()):
        raise ValueError("All liquidity rates must be finite and non-negative")

    work = positions.copy()
    if security_col not in work.columns:
        work[security_col] = np.arange(len(work)).astype(str)
    work[market_value_col] = pd.to_numeric(work[market_value_col], errors="coerce")
    if (
        work[market_value_col].isna().any()
        or (~np.isfinite(work[market_value_col])).any()
    ):
        raise ValueError(
            f"{market_value_col} contains missing, non-numeric, or non-finite values"
        )

    work[liquidity_bucket_col] = work[liquidity_bucket_col].astype(str)
    missing_buckets = sorted(set(work[liquidity_bucket_col]) - set(normalized_rates))
    if missing_buckets:
        raise KeyError(
            "No approved liquidity rate for bucket(s): " + ", ".join(missing_buckets)
        )

    work["gross_position_value"] = work[market_value_col].abs()
    work["liquidity_rate"] = work[liquidity_bucket_col].map(normalized_rates)
    work["raw_attribution_amount"] = (
        work["gross_position_value"] * work["liquidity_rate"]
    )

    summary = work.groupby(member_col, as_index=False, sort=True).agg(
        gross_market_value=("gross_position_value", "sum"),
        raw_liquidity_addon=("raw_attribution_amount", "sum"),
    )
    summary["liquidity_addon"] = summary["raw_liquidity_addon"].clip(lower=minimum_usd)
    summary["floor_applied"] = summary["raw_liquidity_addon"] < minimum_usd

    if maximum_fraction_of_gross is None:
        summary["cap_usd"] = np.nan
        summary["cap_applied"] = False
    else:
        summary["cap_usd"] = summary["gross_market_value"] * maximum_fraction_of_gross
        summary["cap_applied"] = summary["liquidity_addon"] > summary["cap_usd"]
        summary["liquidity_addon"] = np.minimum(
            summary["liquidity_addon"], summary["cap_usd"]
        )

    # Reconcile position attribution to the final member charge. A proportional
    # scale preserves relative position contributions when a floor or cap applies.
    scale = summary[[member_col, "raw_liquidity_addon", "liquidity_addon"]].copy()
    scale["attribution_scale"] = np.where(
        scale["raw_liquidity_addon"] > 0,
        scale["liquidity_addon"] / scale["raw_liquidity_addon"],
        0.0,
    )
    attribution = work.merge(
        scale[[member_col, "attribution_scale"]], on=member_col, how="left"
    )
    attribution["attribution_amount"] = (
        attribution["raw_attribution_amount"] * attribution["attribution_scale"]
    )

    # If a positive floor applies to a member with zero raw charge, assign the
    # floor to an explicit member-level residual row rather than distorting a position.
    floor_residuals = summary.loc[
        (summary["raw_liquidity_addon"] == 0) & (summary["liquidity_addon"] > 0),
        [member_col, "liquidity_addon"],
    ]
    if not floor_residuals.empty:
        residual = pd.DataFrame(
            {
                member_col: floor_residuals[member_col],
                security_col: "__MEMBER_FLOOR__",
                liquidity_bucket_col: "__POLICY_FLOOR__",
                market_value_col: 0.0,
                "gross_position_value": 0.0,
                "liquidity_rate": 0.0,
                "raw_attribution_amount": 0.0,
                "attribution_scale": 0.0,
                "attribution_amount": floor_residuals["liquidity_addon"],
            }
        )
        attribution = pd.concat([attribution, residual], ignore_index=True, sort=False)

    attribution["component"] = "liquidity_addon"
    columns = [
        member_col,
        security_col,
        liquidity_bucket_col,
        market_value_col,
        "gross_position_value",
        "liquidity_rate",
        "raw_attribution_amount",
        "attribution_amount",
        "component",
    ]
    attribution = (
        attribution[columns]
        .sort_values([member_col, security_col], kind="stable")
        .reset_index(drop=True)
    )

    return LiquidityAddonResult(
        member_addon=summary,
        attribution=attribution,
        metadata={
            "business_rationale": BUSINESS_RATIONALE,
            "formula": "sum(abs(market_value) * approved_bucket_rate), subject to floor/cap",
            "parameter_source": parameter_source,
            "minimum_behavior": f"Absolute floor of {float(minimum_usd):.2f} USD",
            "maximum_behavior": (
                "No cap"
                if maximum_fraction_of_gross is None
                else f"Capped at {maximum_fraction_of_gross:.6f} of gross market value"
            ),
            "known_limitations": KNOWN_LIMITATIONS,
            "rates_by_bucket": normalized_rates,
        },
    )


def _validate_limits(
    minimum_usd: float, maximum_fraction_of_gross: float | None
) -> None:
    if minimum_usd < 0 or not np.isfinite(minimum_usd):
        raise ValueError("minimum_usd must be finite and non-negative")
    if maximum_fraction_of_gross is not None:
        if not np.isfinite(maximum_fraction_of_gross):
            raise ValueError("maximum_fraction_of_gross must be finite")
        if not 0 <= maximum_fraction_of_gross <= 1:
            raise ValueError("maximum_fraction_of_gross must be between 0 and 1")

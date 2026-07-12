"""Gap-risk add-on for the CCP margin framework.

Business rationale
------------------
Historical VaR can understate discontinuous moves that occur between valuation
and liquidation, including overnight price gaps, limit moves, defaults, and
market closures. The component applies approved adverse gap shocks to gross
position exposure by asset class.

Formula
-------
For member m and position i::

    RawGapRisk_m = sum_i(abs(MV_i) * GapShock[AssetClass_i])
    GapRiskAddon_m = min(max(RawGapRisk_m, FloorUSD), CapFraction * GrossMV_m)

This is deliberately transparent and conservative. Diversification offsets are
not recognized unless an independently approved methodology is implemented.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np
import pandas as pd


BUSINESS_RATIONALE = (
    "Covers discontinuous adverse moves that may not be adequately represented "
    "in the historical return distribution used by base VaR."
)
KNOWN_LIMITATIONS = (
    "The gross-exposure shock approach may overstate risk by ignoring hedges and "
    "understate risk when approved shocks are too mild. It does not explicitly "
    "model jump dependence, trading halts, wrong-way risk, or issuer-specific default."
)


@dataclass(frozen=True)
class GapRiskAddonResult:
    member_addon: pd.DataFrame
    attribution: pd.DataFrame
    metadata: dict[str, Any]


def calculate_gap_risk_addon(
    positions: pd.DataFrame,
    *,
    shocks_by_asset_class: Mapping[str, float],
    parameter_source: str,
    member_col: str = "member_id",
    security_col: str = "security_id",
    market_value_col: str = "market_value",
    asset_class_col: str = "asset_class",
    minimum_usd: float = 0.0,
    maximum_fraction_of_gross: float | None = None,
) -> GapRiskAddonResult:
    """Calculate member-level gap-risk add-ons with position attribution."""

    if not parameter_source.strip():
        raise ValueError("parameter_source must be documented")
    if minimum_usd < 0 or not np.isfinite(minimum_usd):
        raise ValueError("minimum_usd must be finite and non-negative")
    if maximum_fraction_of_gross is not None:
        if not np.isfinite(maximum_fraction_of_gross):
            raise ValueError("maximum_fraction_of_gross must be finite")
        if not 0 <= maximum_fraction_of_gross <= 1:
            raise ValueError("maximum_fraction_of_gross must be between 0 and 1")

    required = {member_col, market_value_col, asset_class_col}
    missing = required.difference(positions.columns)
    if missing:
        raise KeyError(f"Missing required columns: {sorted(missing)}")

    normalized_shocks = {str(k): float(v) for k, v in shocks_by_asset_class.items()}
    if not normalized_shocks:
        raise ValueError("shocks_by_asset_class must not be empty")
    if any((not np.isfinite(v)) or v < 0 or v > 1 for v in normalized_shocks.values()):
        raise ValueError("All gap shocks must be finite fractions between 0 and 1")

    work = positions.copy()
    if security_col not in work.columns:
        work[security_col] = np.arange(len(work)).astype(str)
    work[market_value_col] = pd.to_numeric(work[market_value_col], errors="coerce")
    if work[market_value_col].isna().any() or (~np.isfinite(work[market_value_col])).any():
        raise ValueError(f"{market_value_col} contains missing, non-numeric, or non-finite values")

    work[asset_class_col] = work[asset_class_col].astype(str)
    missing_classes = sorted(set(work[asset_class_col]) - set(normalized_shocks))
    if missing_classes:
        raise KeyError(
            "No approved gap shock for asset class(es): " + ", ".join(missing_classes)
        )

    work["gross_position_value"] = work[market_value_col].abs()
    work["gap_shock"] = work[asset_class_col].map(normalized_shocks)
    work["raw_attribution_amount"] = work["gross_position_value"] * work["gap_shock"]

    summary = (
        work.groupby(member_col, as_index=False, sort=True)
        .agg(
            gross_market_value=("gross_position_value", "sum"),
            raw_gap_risk_addon=("raw_attribution_amount", "sum"),
        )
    )
    summary["gap_risk_addon"] = summary["raw_gap_risk_addon"].clip(lower=minimum_usd)
    summary["floor_applied"] = summary["raw_gap_risk_addon"] < minimum_usd

    if maximum_fraction_of_gross is None:
        summary["cap_usd"] = np.nan
        summary["cap_applied"] = False
    else:
        summary["cap_usd"] = summary["gross_market_value"] * maximum_fraction_of_gross
        summary["cap_applied"] = summary["gap_risk_addon"] > summary["cap_usd"]
        summary["gap_risk_addon"] = np.minimum(summary["gap_risk_addon"], summary["cap_usd"])

    scale = summary[[member_col, "raw_gap_risk_addon", "gap_risk_addon"]].copy()
    scale["attribution_scale"] = np.where(
        scale["raw_gap_risk_addon"] > 0,
        scale["gap_risk_addon"] / scale["raw_gap_risk_addon"],
        0.0,
    )
    attribution = work.merge(scale[[member_col, "attribution_scale"]], on=member_col, how="left")
    attribution["attribution_amount"] = (
        attribution["raw_attribution_amount"] * attribution["attribution_scale"]
    )

    floor_residuals = summary.loc[
        (summary["raw_gap_risk_addon"] == 0) & (summary["gap_risk_addon"] > 0),
        [member_col, "gap_risk_addon"],
    ]
    if not floor_residuals.empty:
        residual = pd.DataFrame(
            {
                member_col: floor_residuals[member_col],
                security_col: "__MEMBER_FLOOR__",
                asset_class_col: "__POLICY_FLOOR__",
                market_value_col: 0.0,
                "gross_position_value": 0.0,
                "gap_shock": 0.0,
                "raw_attribution_amount": 0.0,
                "attribution_scale": 0.0,
                "attribution_amount": floor_residuals["gap_risk_addon"],
            }
        )
        attribution = pd.concat([attribution, residual], ignore_index=True, sort=False)

    attribution["component"] = "gap_risk_addon"
    columns = [
        member_col,
        security_col,
        asset_class_col,
        market_value_col,
        "gross_position_value",
        "gap_shock",
        "raw_attribution_amount",
        "attribution_amount",
        "component",
    ]
    attribution = attribution[columns].sort_values(
        [member_col, security_col], kind="stable"
    ).reset_index(drop=True)

    return GapRiskAddonResult(
        member_addon=summary,
        attribution=attribution,
        metadata={
            "business_rationale": BUSINESS_RATIONALE,
            "formula": "sum(abs(market_value) * approved_asset_class_gap_shock), subject to floor/cap",
            "parameter_source": parameter_source,
            "minimum_behavior": f"Absolute floor of {float(minimum_usd):.2f} USD",
            "maximum_behavior": (
                "No cap"
                if maximum_fraction_of_gross is None
                else f"Capped at {maximum_fraction_of_gross:.6f} of gross market value"
            ),
            "known_limitations": KNOWN_LIMITATIONS,
            "shocks_by_asset_class": normalized_shocks,
        },
    )

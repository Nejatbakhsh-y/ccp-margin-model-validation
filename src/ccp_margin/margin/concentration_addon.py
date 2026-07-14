"""Concentration add-on for the CCP margin framework.

Business rationale
------------------
Concentrated portfolios can generate losses and liquidation costs that are not
well represented by a diversified historical distribution. The component
charges only the portion of single-name or sector exposure above approved
concentration thresholds.

Formula
-------
For a concentration group g with gross share w_g and threshold t::

    ScaledExcess_g = max((w_g - t) / (1 - t), 0)
    Charge_g = GrossExposure_g * AddonRate * ScaledExcess_g

The member raw charge is either the greater of the single-name and sector
charges (default, which reduces double counting) or their sum when an approved
methodology explicitly requires additive treatment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd


BUSINESS_RATIONALE = (
    "Covers nonlinear risk and liquidation exposure arising from excessive "
    "single-name or sector concentration."
)
KNOWN_LIMITATIONS = (
    "The threshold approach does not explicitly model correlation breakdown, "
    "issuer default, crowded positioning, cross-member concentration, or dynamic "
    "market depth. Sector classifications may also be coarse or stale."
)


@dataclass(frozen=True)
class ConcentrationAddonResult:
    member_addon: pd.DataFrame
    attribution: pd.DataFrame
    metadata: dict[str, Any]


def calculate_concentration_addon(
    positions: pd.DataFrame,
    *,
    single_name_threshold: float,
    single_name_rate: float,
    sector_threshold: float,
    sector_rate: float,
    parameter_source: str,
    aggregation_method: Literal["max", "sum"] = "max",
    member_col: str = "member_id",
    security_col: str = "security_id",
    sector_col: str = "sector",
    market_value_col: str = "market_value",
    minimum_usd: float = 0.0,
    maximum_fraction_of_gross: float | None = None,
) -> ConcentrationAddonResult:
    """Calculate a transparent single-name and sector concentration add-on."""

    _validate_fraction("single_name_threshold", single_name_threshold, upper_open=True)
    _validate_fraction("sector_threshold", sector_threshold, upper_open=True)
    _validate_fraction("single_name_rate", single_name_rate)
    _validate_fraction("sector_rate", sector_rate)
    if aggregation_method not in {"max", "sum"}:
        raise ValueError("aggregation_method must be 'max' or 'sum'")
    if minimum_usd < 0 or not np.isfinite(minimum_usd):
        raise ValueError("minimum_usd must be finite and non-negative")
    if maximum_fraction_of_gross is not None:
        _validate_fraction("maximum_fraction_of_gross", maximum_fraction_of_gross)
    if not parameter_source.strip():
        raise ValueError("parameter_source must be documented")

    required = {member_col, security_col, sector_col, market_value_col}
    missing = required.difference(positions.columns)
    if missing:
        raise KeyError(f"Missing required columns: {sorted(missing)}")

    work = positions[[member_col, security_col, sector_col, market_value_col]].copy()
    work[market_value_col] = pd.to_numeric(work[market_value_col], errors="coerce")
    if (
        work[market_value_col].isna().any()
        or (~np.isfinite(work[market_value_col])).any()
    ):
        raise ValueError(
            f"{market_value_col} contains missing, non-numeric, or non-finite values"
        )
    work["gross_position_value"] = work[market_value_col].abs()

    gross = (
        work.groupby(member_col, as_index=False, sort=True)["gross_position_value"]
        .sum()
        .rename(columns={"gross_position_value": "gross_market_value"})
    )

    security = (
        work.groupby([member_col, security_col], as_index=False, sort=True)[
            "gross_position_value"
        ]
        .sum()
        .merge(gross, on=member_col, how="left")
    )
    security["concentration_ratio"] = np.where(
        security["gross_market_value"] > 0,
        security["gross_position_value"] / security["gross_market_value"],
        0.0,
    )
    security["scaled_excess"] = np.maximum(
        (security["concentration_ratio"] - single_name_threshold)
        / (1.0 - single_name_threshold),
        0.0,
    )
    security["raw_attribution_amount"] = (
        security["gross_position_value"] * single_name_rate * security["scaled_excess"]
    )
    security["concentration_type"] = "single_name"
    security["concentration_key"] = security[security_col].astype(str)

    sector = (
        work.groupby([member_col, sector_col], as_index=False, sort=True)[
            "gross_position_value"
        ]
        .sum()
        .merge(gross, on=member_col, how="left")
    )
    sector["concentration_ratio"] = np.where(
        sector["gross_market_value"] > 0,
        sector["gross_position_value"] / sector["gross_market_value"],
        0.0,
    )
    sector["scaled_excess"] = np.maximum(
        (sector["concentration_ratio"] - sector_threshold) / (1.0 - sector_threshold),
        0.0,
    )
    sector["raw_attribution_amount"] = (
        sector["gross_position_value"] * sector_rate * sector["scaled_excess"]
    )
    sector["concentration_type"] = "sector"
    sector["concentration_key"] = sector[sector_col].astype(str)

    security_total = (
        security.groupby(member_col, as_index=False, sort=True)[
            "raw_attribution_amount"
        ]
        .sum()
        .rename(columns={"raw_attribution_amount": "single_name_charge"})
    )
    sector_total = (
        sector.groupby(member_col, as_index=False, sort=True)["raw_attribution_amount"]
        .sum()
        .rename(columns={"raw_attribution_amount": "sector_charge"})
    )
    summary = gross.merge(security_total, on=member_col, how="left").merge(
        sector_total, on=member_col, how="left"
    )
    summary[["single_name_charge", "sector_charge"]] = summary[
        ["single_name_charge", "sector_charge"]
    ].fillna(0.0)

    if aggregation_method == "max":
        summary["selected_basis"] = np.where(
            summary["single_name_charge"] >= summary["sector_charge"],
            "single_name",
            "sector",
        )
        summary["raw_concentration_addon"] = summary[
            ["single_name_charge", "sector_charge"]
        ].max(axis=1)
    else:
        summary["selected_basis"] = "single_name_plus_sector"
        summary["raw_concentration_addon"] = (
            summary["single_name_charge"] + summary["sector_charge"]
        )

    summary["concentration_addon"] = summary["raw_concentration_addon"].clip(
        lower=minimum_usd
    )
    summary["floor_applied"] = summary["raw_concentration_addon"] < minimum_usd
    if maximum_fraction_of_gross is None:
        summary["cap_usd"] = np.nan
        summary["cap_applied"] = False
    else:
        summary["cap_usd"] = summary["gross_market_value"] * maximum_fraction_of_gross
        summary["cap_applied"] = summary["concentration_addon"] > summary["cap_usd"]
        summary["concentration_addon"] = np.minimum(
            summary["concentration_addon"], summary["cap_usd"]
        )

    detail_cols = [
        member_col,
        "concentration_type",
        "concentration_key",
        "gross_position_value",
        "gross_market_value",
        "concentration_ratio",
        "scaled_excess",
        "raw_attribution_amount",
    ]
    detail = pd.concat([security[detail_cols], sector[detail_cols]], ignore_index=True)
    detail = detail.merge(
        summary[
            [
                member_col,
                "selected_basis",
                "raw_concentration_addon",
                "concentration_addon",
            ]
        ],
        on=member_col,
        how="left",
    )

    if aggregation_method == "max":
        detail["included_in_member_charge"] = (
            detail["concentration_type"] == detail["selected_basis"]
        )
    else:
        detail["included_in_member_charge"] = True

    detail["selected_raw_amount"] = np.where(
        detail["included_in_member_charge"], detail["raw_attribution_amount"], 0.0
    )
    detail["attribution_scale"] = np.where(
        detail["raw_concentration_addon"] > 0,
        detail["concentration_addon"] / detail["raw_concentration_addon"],
        0.0,
    )
    detail["attribution_amount"] = (
        detail["selected_raw_amount"] * detail["attribution_scale"]
    )

    floor_residuals = summary.loc[
        (summary["raw_concentration_addon"] == 0)
        & (summary["concentration_addon"] > 0),
        [member_col, "gross_market_value", "concentration_addon"],
    ]
    if not floor_residuals.empty:
        residual = pd.DataFrame(
            {
                member_col: floor_residuals[member_col],
                "concentration_type": "policy_floor",
                "concentration_key": "__MEMBER_FLOOR__",
                "gross_position_value": 0.0,
                "gross_market_value": floor_residuals["gross_market_value"],
                "concentration_ratio": 0.0,
                "scaled_excess": 0.0,
                "raw_attribution_amount": 0.0,
                "selected_basis": "policy_floor",
                "raw_concentration_addon": 0.0,
                "concentration_addon": floor_residuals["concentration_addon"],
                "included_in_member_charge": True,
                "selected_raw_amount": 0.0,
                "attribution_scale": 0.0,
                "attribution_amount": floor_residuals["concentration_addon"],
            }
        )
        detail = pd.concat([detail, residual], ignore_index=True, sort=False)

    detail["component"] = "concentration_addon"
    detail = detail.sort_values(
        [member_col, "concentration_type", "concentration_key"], kind="stable"
    ).reset_index(drop=True)

    return ConcentrationAddonResult(
        member_addon=summary,
        attribution=detail,
        metadata={
            "business_rationale": BUSINESS_RATIONALE,
            "formula": (
                "gross_exposure * rate * max((concentration_ratio - threshold) / "
                "(1 - threshold), 0)"
            ),
            "parameter_source": parameter_source,
            "minimum_behavior": f"Absolute floor of {float(minimum_usd):.2f} USD",
            "maximum_behavior": (
                "No cap"
                if maximum_fraction_of_gross is None
                else f"Capped at {maximum_fraction_of_gross:.6f} of gross market value"
            ),
            "aggregation_method": aggregation_method,
            "single_name_threshold": single_name_threshold,
            "single_name_rate": single_name_rate,
            "sector_threshold": sector_threshold,
            "sector_rate": sector_rate,
            "known_limitations": KNOWN_LIMITATIONS,
        },
    )


def _validate_fraction(name: str, value: float, *, upper_open: bool = False) -> None:
    if not np.isfinite(value):
        raise ValueError(f"{name} must be finite")
    upper_ok = value < 1 if upper_open else value <= 1
    if value < 0 or not upper_ok:
        operator = "[0, 1)" if upper_open else "[0, 1]"
        raise ValueError(f"{name} must be in {operator}")

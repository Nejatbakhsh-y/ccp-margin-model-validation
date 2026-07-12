"""Base margin component for the CCP margin framework.

Business rationale
------------------
Base margin covers ordinary market risk represented by the approved primary
margin model, normally historical-simulation VaR at the configured confidence
level and margin period of risk.

Formula
-------
For member m::

    BaseMargin_m = min(max(BaseVaR_m, Floor_m), Cap_m)

The cap is optional. A cap should normally be disabled because capping market
risk can create under-margining. It is included only so that explicit policy
limits can be represented and independently tested.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


BUSINESS_RATIONALE = (
    "Covers ordinary market risk measured by the approved primary VaR model."
)
PARAMETER_SOURCE = (
    "Primary-model output and validation-approved margin policy parameters."
)
KNOWN_LIMITATIONS = (
    "The component inherits the limitations of the primary VaR model, including "
    "historical-window representativeness, confidence-level uncertainty, and "
    "risk-factor history availability."
)


@dataclass(frozen=True)
class BaseMarginResult:
    """Calculated member-level base margin and reconciliation metadata."""

    member_margin: pd.DataFrame
    attribution: pd.DataFrame
    metadata: dict[str, Any]


def calculate_base_margin(
    var_by_member: pd.DataFrame,
    *,
    member_col: str = "member_id",
    var_col: str = "base_var",
    floor_usd: float = 0.0,
    cap_usd: float | None = None,
) -> BaseMarginResult:
    """Calculate base margin from approved member-level VaR results.

    Parameters
    ----------
    var_by_member:
        DataFrame containing one or more VaR observations per member. If more
        than one row exists for a member, the maximum non-missing VaR is used.
    member_col:
        Clearing-member identifier column.
    var_col:
        Non-negative VaR amount in currency units.
    floor_usd:
        Absolute minimum base margin. Must be non-negative.
    cap_usd:
        Optional absolute maximum. Must be greater than or equal to the floor.

    Returns
    -------
    BaseMarginResult
        Member-level margin, source-row attribution, and parameter metadata.
    """

    if floor_usd < 0:
        raise ValueError("floor_usd must be non-negative")
    if cap_usd is not None and cap_usd < floor_usd:
        raise ValueError("cap_usd must be greater than or equal to floor_usd")
    missing = {member_col, var_col}.difference(var_by_member.columns)
    if missing:
        raise KeyError(f"Missing required columns: {sorted(missing)}")
    if var_by_member.empty:
        empty = pd.DataFrame(
            columns=[member_col, "base_var", "base_margin", "floor_applied", "cap_applied"]
        )
        return BaseMarginResult(
            member_margin=empty.copy(),
            attribution=empty.copy(),
            metadata=_metadata(floor_usd, cap_usd),
        )

    work = var_by_member[[member_col, var_col]].copy()
    work[var_col] = pd.to_numeric(work[var_col], errors="coerce")
    if work[var_col].isna().any():
        raise ValueError(f"{var_col} contains missing or non-numeric values")
    if (~np.isfinite(work[var_col])).any():
        raise ValueError(f"{var_col} contains non-finite values")
    if (work[var_col] < 0).any():
        raise ValueError(f"{var_col} must be non-negative")

    grouped = (
        work.groupby(member_col, as_index=False, sort=True)[var_col]
        .max()
        .rename(columns={var_col: "base_var"})
    )
    grouped["base_margin"] = grouped["base_var"].clip(lower=floor_usd)
    grouped["floor_applied"] = grouped["base_var"] < floor_usd
    if cap_usd is None:
        grouped["cap_applied"] = False
    else:
        grouped["cap_applied"] = grouped["base_margin"] > cap_usd
        grouped["base_margin"] = grouped["base_margin"].clip(upper=cap_usd)

    attribution = grouped[[member_col, "base_var", "base_margin"]].copy()
    attribution["component"] = "base_margin"
    attribution["attribution_amount"] = attribution["base_margin"]

    return BaseMarginResult(
        member_margin=grouped,
        attribution=attribution,
        metadata=_metadata(floor_usd, cap_usd),
    )


def _metadata(floor_usd: float, cap_usd: float | None) -> dict[str, Any]:
    return {
        "business_rationale": BUSINESS_RATIONALE,
        "formula": "min(max(base_var, floor_usd), cap_usd) with optional cap",
        "parameter_source": PARAMETER_SOURCE,
        "minimum_behavior": f"Absolute floor of {float(floor_usd):.2f} USD",
        "maximum_behavior": (
            "No cap" if cap_usd is None else f"Absolute cap of {float(cap_usd):.2f} USD"
        ),
        "known_limitations": KNOWN_LIMITATIONS,
    }

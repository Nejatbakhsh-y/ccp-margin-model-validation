"""Stress buffer for the CCP margin framework.

Business rationale
------------------
The stress buffer is a coverage bridge, not a percentage uplift selected to
improve backtesting. It applies only when approved stressed losses exceed the
coverage supplied by base margin and the other independently justified add-ons.

Formula
-------
For member m::

    TargetStressCoverage_m = CoverageRatio * MaxApprovedStressLoss_m
    RawStressBuffer_m = max(TargetStressCoverage_m - PreStressMargin_m, 0)
    StressBuffer_m = min(RawStressBuffer_m, OptionalAbsoluteCap)

Using the residual formulation reduces mechanical double counting between the
stress buffer and other components.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


BUSINESS_RATIONALE = (
    "Bridges any shortfall between approved stressed loss coverage and the margin "
    "already supplied by base VaR plus the other independently justified add-ons."
)
KNOWN_LIMITATIONS = (
    "The result depends on the completeness, severity, and plausibility of the "
    "approved scenario library. A finite scenario set cannot guarantee coverage "
    "of all future crises, and using the maximum scenario may create cliff effects."
)


@dataclass(frozen=True)
class StressBufferResult:
    member_buffer: pd.DataFrame
    attribution: pd.DataFrame
    metadata: dict[str, Any]


def calculate_stress_buffer(
    stress_losses: pd.DataFrame,
    pre_stress_margin: pd.DataFrame,
    *,
    required_coverage_ratio: float,
    parameter_source: str,
    member_col: str = "member_id",
    scenario_col: str = "scenario_id",
    stress_loss_col: str = "stress_loss",
    pre_stress_margin_col: str = "pre_stress_margin",
    maximum_usd: float | None = None,
) -> StressBufferResult:
    """Calculate a residual stress-coverage buffer by member."""

    if required_coverage_ratio < 0 or not np.isfinite(required_coverage_ratio):
        raise ValueError("required_coverage_ratio must be finite and non-negative")
    if maximum_usd is not None and (maximum_usd < 0 or not np.isfinite(maximum_usd)):
        raise ValueError("maximum_usd must be finite and non-negative")
    if not parameter_source.strip():
        raise ValueError("parameter_source must be documented")

    stress_required = {member_col, scenario_col, stress_loss_col}
    margin_required = {member_col, pre_stress_margin_col}
    missing_stress = stress_required.difference(stress_losses.columns)
    missing_margin = margin_required.difference(pre_stress_margin.columns)
    if missing_stress:
        raise KeyError(f"Missing stress-loss columns: {sorted(missing_stress)}")
    if missing_margin:
        raise KeyError(f"Missing pre-stress-margin columns: {sorted(missing_margin)}")

    stress = stress_losses[[member_col, scenario_col, stress_loss_col]].copy()
    stress[stress_loss_col] = pd.to_numeric(stress[stress_loss_col], errors="coerce")
    if (
        stress[stress_loss_col].isna().any()
        or (~np.isfinite(stress[stress_loss_col])).any()
    ):
        raise ValueError(
            f"{stress_loss_col} contains missing, non-numeric, or non-finite values"
        )
    if (stress[stress_loss_col] < 0).any():
        raise ValueError(f"{stress_loss_col} must be non-negative")

    margin = pre_stress_margin[[member_col, pre_stress_margin_col]].copy()
    margin[pre_stress_margin_col] = pd.to_numeric(
        margin[pre_stress_margin_col], errors="coerce"
    )
    if (
        margin[pre_stress_margin_col].isna().any()
        or (~np.isfinite(margin[pre_stress_margin_col])).any()
    ):
        raise ValueError(
            f"{pre_stress_margin_col} contains missing, non-numeric, or non-finite values"
        )
    if (margin[pre_stress_margin_col] < 0).any():
        raise ValueError(f"{pre_stress_margin_col} must be non-negative")
    if margin[member_col].duplicated().any():
        raise ValueError("pre_stress_margin must contain one row per member")

    # Deterministically select the maximum loss; scenario name is a stable tie breaker.
    stress[scenario_col] = stress[scenario_col].astype(str)
    worst = (
        stress.sort_values(
            [member_col, stress_loss_col, scenario_col],
            ascending=[True, False, True],
            kind="stable",
        )
        .groupby(member_col, as_index=False, sort=True)
        .first()
        .rename(
            columns={
                scenario_col: "binding_scenario_id",
                stress_loss_col: "maximum_stress_loss",
            }
        )
    )

    summary = margin.merge(worst, on=member_col, how="outer", validate="one_to_one")
    if summary[pre_stress_margin_col].isna().any():
        missing_members = summary.loc[
            summary[pre_stress_margin_col].isna(), member_col
        ].tolist()
        raise ValueError(f"Missing pre-stress margin for member(s): {missing_members}")
    if summary["maximum_stress_loss"].isna().any():
        missing_members = summary.loc[
            summary["maximum_stress_loss"].isna(), member_col
        ].tolist()
        raise ValueError(
            f"Missing approved stress loss for member(s): {missing_members}"
        )

    summary["target_stress_coverage"] = (
        required_coverage_ratio * summary["maximum_stress_loss"]
    )
    summary["raw_stress_buffer"] = np.maximum(
        summary["target_stress_coverage"] - summary[pre_stress_margin_col], 0.0
    )
    summary["stress_buffer"] = summary["raw_stress_buffer"]
    if maximum_usd is None:
        summary["cap_applied"] = False
    else:
        summary["cap_applied"] = summary["stress_buffer"] > maximum_usd
        summary["stress_buffer"] = summary["stress_buffer"].clip(upper=maximum_usd)

    attribution = summary[
        [
            member_col,
            "binding_scenario_id",
            "maximum_stress_loss",
            pre_stress_margin_col,
            "target_stress_coverage",
            "raw_stress_buffer",
            "stress_buffer",
        ]
    ].copy()
    attribution["component"] = "stress_buffer"
    attribution["attribution_amount"] = attribution["stress_buffer"]

    return StressBufferResult(
        member_buffer=summary.sort_values(member_col, kind="stable").reset_index(
            drop=True
        ),
        attribution=attribution.sort_values(member_col, kind="stable").reset_index(
            drop=True
        ),
        metadata={
            "business_rationale": BUSINESS_RATIONALE,
            "formula": (
                "max(required_coverage_ratio * maximum_approved_stress_loss - "
                "pre_stress_margin, 0), subject to optional absolute cap"
            ),
            "parameter_source": parameter_source,
            "minimum_behavior": "Zero when pre-stress margin already meets the coverage target",
            "maximum_behavior": (
                "No cap"
                if maximum_usd is None
                else f"Absolute cap of {maximum_usd:.2f} USD"
            ),
            "required_coverage_ratio": required_coverage_ratio,
            "known_limitations": KNOWN_LIMITATIONS,
        },
    )

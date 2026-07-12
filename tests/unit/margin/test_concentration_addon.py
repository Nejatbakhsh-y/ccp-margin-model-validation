from __future__ import annotations

import pandas as pd
import pytest

from ccp_margin.margin.concentration_addon import calculate_concentration_addon


def _calculate(positions: pd.DataFrame, threshold: float = 0.20):
    return calculate_concentration_addon(
        positions,
        single_name_threshold=threshold,
        single_name_rate=0.10,
        sector_threshold=0.40,
        sector_rate=0.05,
        parameter_source="Approved test source",
        aggregation_method="max",
    )


def test_concentration_addon_is_positive_for_concentrated_member(
    positions: pd.DataFrame,
) -> None:
    result = _calculate(positions)
    member = result.member_addon.set_index("member_id")
    assert member.loc["M001", "concentration_addon"] > 0
    reconciled = result.attribution.groupby("member_id")["attribution_amount"].sum()
    assert reconciled.loc["M001"] == pytest.approx(
        member.loc["M001", "concentration_addon"]
    )


def test_concentration_addon_falls_when_threshold_increases(
    positions: pd.DataFrame,
) -> None:
    low_threshold = _calculate(positions, threshold=0.10).member_addon.set_index(
        "member_id"
    )
    high_threshold = _calculate(positions, threshold=0.60).member_addon.set_index(
        "member_id"
    )
    assert (
        high_threshold["concentration_addon"]
        <= low_threshold["concentration_addon"]
    ).all()


def test_diversified_portfolio_can_have_zero_single_name_charge() -> None:
    diversified = pd.DataFrame(
        {
            "member_id": ["M1"] * 5,
            "security_id": ["A", "B", "C", "D", "E"],
            "sector": ["S1", "S2", "S3", "S4", "S5"],
            "market_value": [20.0] * 5,
        }
    )
    result = _calculate(diversified, threshold=0.20)
    row = result.member_addon.iloc[0]
    assert row["single_name_charge"] == pytest.approx(0.0)
    assert row["sector_charge"] == pytest.approx(0.0)
    assert row["concentration_addon"] == pytest.approx(0.0)

from __future__ import annotations

import pandas as pd
import pytest

from ccp_margin.margin.liquidity_addon import calculate_liquidity_addon


def test_liquidity_addon_formula_and_reconciliation(positions: pd.DataFrame) -> None:
    result = calculate_liquidity_addon(
        positions,
        rates_by_bucket={"high": 0.001, "medium": 0.003, "low": 0.01},
        parameter_source="Approved test source",
    )
    member = result.member_addon.set_index("member_id")
    assert member.loc["M001", "liquidity_addon"] == pytest.approx(
        600 * 0.001 + 250 * 0.003 + 150 * 0.01
    )
    reconciled = result.attribution.groupby("member_id")["attribution_amount"].sum()
    assert reconciled.loc["M001"] == pytest.approx(
        member.loc["M001", "liquidity_addon"]
    )


def test_liquidity_addon_increases_when_rate_increases(positions: pd.DataFrame) -> None:
    low = calculate_liquidity_addon(
        positions,
        rates_by_bucket={"high": 0.001, "medium": 0.003, "low": 0.01},
        parameter_source="Approved test source",
    ).member_addon.set_index("member_id")
    high = calculate_liquidity_addon(
        positions,
        rates_by_bucket={"high": 0.002, "medium": 0.006, "low": 0.02},
        parameter_source="Approved test source",
    ).member_addon.set_index("member_id")
    assert (high["liquidity_addon"] >= low["liquidity_addon"]).all()
    assert (high["liquidity_addon"] > low["liquidity_addon"]).any()


def test_liquidity_addon_rejects_undocumented_bucket(positions: pd.DataFrame) -> None:
    with pytest.raises(KeyError, match="No approved liquidity rate"):
        calculate_liquidity_addon(
            positions,
            rates_by_bucket={"high": 0.001},
            parameter_source="Approved test source",
        )

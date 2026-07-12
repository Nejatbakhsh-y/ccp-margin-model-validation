from __future__ import annotations

import pandas as pd
import pytest

from ccp_margin.margin.gap_risk_addon import calculate_gap_risk_addon


def test_gap_risk_uses_gross_exposure(positions: pd.DataFrame) -> None:
    result = calculate_gap_risk_addon(
        positions,
        shocks_by_asset_class={"equity": 0.08, "rates": 0.02},
        parameter_source="Approved test source",
    )
    member = result.member_addon.set_index("member_id")
    assert member.loc["M002", "gap_risk_addon"] == pytest.approx(1000 * 0.02)


def test_gap_risk_is_monotonic_in_shock_size(positions: pd.DataFrame) -> None:
    low = calculate_gap_risk_addon(
        positions,
        shocks_by_asset_class={"equity": 0.04, "rates": 0.01},
        parameter_source="Approved test source",
    ).member_addon.set_index("member_id")
    high = calculate_gap_risk_addon(
        positions,
        shocks_by_asset_class={"equity": 0.08, "rates": 0.02},
        parameter_source="Approved test source",
    ).member_addon.set_index("member_id")
    assert (high["gap_risk_addon"] > low["gap_risk_addon"]).all()


def test_gap_risk_rejects_missing_asset_class_parameter(
    positions: pd.DataFrame,
) -> None:
    with pytest.raises(KeyError, match="No approved gap shock"):
        calculate_gap_risk_addon(
            positions,
            shocks_by_asset_class={"equity": 0.08},
            parameter_source="Approved test source",
        )

from __future__ import annotations

import numpy as np
import pandas as pd

from ccp_margin.margin.total_margin import calculate_total_margin


def test_total_margin_reconciles_all_components(
    positions: pd.DataFrame, margin_config: dict
) -> None:
    var = pd.DataFrame({"member_id": ["M001", "M002"], "base_var": [90.0, 70.0]})
    stress = pd.DataFrame(
        {
            "member_id": ["M001", "M001", "M002", "M002"],
            "scenario_id": ["crash", "rates", "crash", "rates"],
            "stress_loss": [250.0, 120.0, 100.0, 130.0],
        }
    )
    result = calculate_total_margin(positions, var, stress, config=margin_config)
    member = result.member_margin
    recomputed = (
        member["base_margin"]
        + member["liquidity_addon"]
        + member["concentration_addon"]
        + member["gap_risk_addon"]
        + member["stress_buffer"]
    )
    np.testing.assert_allclose(member["total_initial_margin"], recomputed)

    attribution = (
        result.attribution.groupby(["member_id", "component"])["attribution_amount"]
        .sum()
        .unstack(fill_value=0.0)
    )
    for component in [
        "base_margin",
        "liquidity_addon",
        "concentration_addon",
        "gap_risk_addon",
        "stress_buffer",
    ]:
        expected = member.set_index("member_id")[component]
        np.testing.assert_allclose(attribution[component], expected)


def test_total_margin_is_deterministic(
    positions: pd.DataFrame, margin_config: dict
) -> None:
    var = pd.DataFrame({"member_id": ["M001", "M002"], "base_var": [90.0, 70.0]})
    stress = pd.DataFrame(
        {
            "member_id": ["M001", "M002"],
            "scenario_id": ["S1", "S1"],
            "stress_loss": [200.0, 100.0],
        }
    )
    first = calculate_total_margin(positions, var, stress, config=margin_config)
    second = calculate_total_margin(positions, var, stress, config=margin_config)
    pd.testing.assert_frame_equal(first.member_margin, second.member_margin)
    pd.testing.assert_frame_equal(first.attribution, second.attribution)

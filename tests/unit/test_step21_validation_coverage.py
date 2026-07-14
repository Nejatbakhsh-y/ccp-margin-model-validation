from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ccp_margin.validation.christoffersen import (
    christoffersen_conditional_coverage,
    christoffersen_independence,
)
from ccp_margin.validation.kupiec import kupiec_unconditional_coverage
from ccp_margin.validation.margin_shortfall import calculate_margin_shortfall


@pytest.mark.parametrize(
    "flags",
    [
        np.zeros(250, dtype=int),
        np.ones(250, dtype=int),
        np.array(([0] * 24 + [1]) * 10, dtype=int),
        np.array(([0, 1] * 125), dtype=int),
    ],
)
def test_kupiec_and_christoffersen_are_serializable_across_edge_sequences(flags):
    kupiec = kupiec_unconditional_coverage(
        flags,
        target_exception_probability=0.01,
        significance_level=0.05,
    )
    kupiec_dict = kupiec.to_dict()
    assert kupiec_dict["number_of_observations"] == len(flags)
    assert kupiec_dict["number_of_exceptions"] == int(flags.sum())
    assert 0.0 <= kupiec_dict["p_value"] <= 1.0

    independence = christoffersen_independence(
        flags,
        significance_level=0.05,
    )
    independence_dict = independence.to_dict()
    assert independence_dict["number_of_transitions"] == len(flags) - 1
    assert (
        independence_dict["n00"]
        + independence_dict["n01"]
        + independence_dict["n10"]
        + independence_dict["n11"]
        == len(flags) - 1
    )
    assert 0.0 <= independence_dict["p_value"] <= 1.0

    conditional = christoffersen_conditional_coverage(
        flags,
        target_exception_probability=0.01,
        significance_level=0.05,
    )
    conditional_dict = conditional.to_dict()
    assert conditional_dict["conditional_coverage_statistic"] >= 0.0
    assert 0.0 <= conditional_dict["p_value"] <= 1.0


def test_margin_shortfall_zero_exception_and_custom_column_contracts():
    observations = pd.DataFrame(
        {
            "loss_amount": [5.0, 10.0],
            "margin_amount": [5.0, 12.0],
            "member": ["A", "B"],
            "portfolio": ["P1", "P2"],
            "stress": [None, False],
        }
    )

    result = calculate_margin_shortfall(
        observations,
        actual_loss_column="loss_amount",
        available_margin_column="margin_amount",
        member_column="member",
        portfolio_type_column="portfolio",
        stressed_period_column="stress",
    )

    assert result.number_of_observations == 2
    assert result.number_of_exceptions == 0
    assert result.total_shortfall == 0.0
    assert result.mean_shortfall == 0.0
    assert result.maximum_shortfall == 0.0
    assert result.exception_records.empty

    serialized = result.to_dict()
    assert serialized["exception_records"] == []
    assert serialized["shortfall_by_member"] == []
    assert serialized["shortfall_by_portfolio_type"] == []
    assert serialized["shortfall_by_stress_status"] == []

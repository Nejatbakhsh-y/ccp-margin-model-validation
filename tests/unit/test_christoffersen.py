from __future__ import annotations

import numpy as np
import pytest

from ccp_margin.validation.christoffersen import (
    christoffersen_conditional_coverage,
    christoffersen_independence,
)


def test_christoffersen_returns_transition_counts_and_valid_p_value():
    exceptions = np.array(
        [0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0, 0],
        dtype=int,
    )

    result = christoffersen_independence(
        exceptions,
        significance_level=0.05,
    )

    assert result.number_of_observations == len(exceptions)
    assert result.number_of_transitions == len(exceptions) - 1
    assert result.n00 + result.n01 + result.n10 + result.n11 == len(exceptions) - 1
    assert result.likelihood_ratio_statistic >= 0.0
    assert 0.0 <= result.p_value <= 1.0

    serialized = result.to_dict()
    assert serialized["number_of_observations"] == len(exceptions)
    assert serialized["n00"] == result.n00
    assert serialized["p_value"] == result.p_value

    combined = christoffersen_conditional_coverage(
        exceptions,
        target_exception_probability=0.01,
        significance_level=0.05,
    )
    assert combined.conditional_coverage_statistic >= 0.0
    assert 0.0 <= combined.p_value <= 1.0

    combined_dict = combined.to_dict()
    assert combined_dict["conditional_coverage_statistic"] == (
        combined.conditional_coverage_statistic
    )
    assert combined_dict["kupiec_result"]["number_of_observations"] == len(exceptions)

    with pytest.raises(ValueError, match="At least two"):
        christoffersen_independence([0])
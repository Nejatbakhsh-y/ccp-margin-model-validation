import numpy as np

from ccp_margin.validation.christoffersen import (
    christoffersen_conditional_coverage,
    christoffersen_independence,
)


def test_transition_counts():
    flags = np.array([0, 0, 1, 1, 0, 1], dtype=int)

    result = christoffersen_independence(flags)

    assert result.n00 == 1
    assert result.n01 == 2
    assert result.n10 == 1
    assert result.n11 == 1
    assert result.number_of_transitions == 5


def test_conditional_coverage_statistic_is_sum():
    flags = np.zeros(250, dtype=int)
    flags[[30, 170]] = 1

    result = christoffersen_conditional_coverage(flags)

    expected = (
        result.kupiec_result.likelihood_ratio_statistic
        + result.independence_result.likelihood_ratio_statistic
    )
    assert result.conditional_coverage_statistic == expected
    assert 0.0 <= result.p_value <= 1.0

from __future__ import annotations

import numpy as np

from ccp_margin.validation.kupiec import kupiec_unconditional_coverage


def test_kupiec_reports_correct_observation_and_exception_counts():
    exceptions = np.zeros(250, dtype=int)
    exceptions[[10, 100]] = 1

    result = kupiec_unconditional_coverage(
        exceptions,
        target_exception_probability=0.01,
        significance_level=0.05,
    )

    assert result.number_of_observations == 250
    assert result.number_of_exceptions == 2
    assert result.target_exception_probability == 0.01
    assert result.target_coverage == 0.99
    assert result.observed_exception_rate == 2 / 250
    assert result.observed_coverage == 248 / 250
    assert result.likelihood_ratio_statistic >= 0.0
    assert 0.0 <= result.p_value <= 1.0
    assert result.passed is True

    serialized = result.to_dict()
    assert serialized["number_of_observations"] == 250
    assert serialized["number_of_exceptions"] == 2
    assert serialized["p_value"] == result.p_value

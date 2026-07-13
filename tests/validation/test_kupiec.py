import numpy as np

from ccp_margin.validation.kupiec import kupiec_unconditional_coverage


def test_kupiec_returns_expected_counts_and_passes_reasonable_sample():
    flags = np.zeros(250, dtype=int)
    flags[[10, 100]] = 1

    result = kupiec_unconditional_coverage(flags)

    assert result.number_of_observations == 250
    assert result.number_of_exceptions == 2
    assert result.observed_exception_rate == 2 / 250
    assert 0.0 <= result.p_value <= 1.0
    assert result.passed


def test_kupiec_rejects_excessive_exceptions():
    flags = np.zeros(250, dtype=int)
    flags[:20] = 1

    result = kupiec_unconditional_coverage(flags)

    assert not result.passed

import numpy as np

from ccp_margin.validation.procyclicality import assess_procyclicality


def test_procyclicality_metrics():
    margin = np.array([100.0, 110.0, 90.0, 135.0, 120.0])
    volatility = np.array([10.0, 11.0, 9.0, 14.0, 12.0])
    stress = np.array([False, False, False, True, True])

    result = assess_procyclicality(
        margin,
        volatility_series=volatility,
        stressed_period_flags=stress,
        rolling_window=2,
    )

    assert result.number_of_observations == 5
    assert result.maximum_one_period_increase == 0.5
    assert result.peak_to_trough_decline > 0.0
    assert result.stressed_to_calm_mean_margin_ratio > 1.0

import numpy as np
import pytest

from ccp_margin.validation.traffic_light import basel_traffic_light


@pytest.mark.parametrize(
    ("exceptions", "expected_zone"),
    [(4, "green"), (5, "yellow"), (9, "yellow"), (10, "red")],
)
def test_basel_thresholds(exceptions, expected_zone):
    flags = np.zeros(250, dtype=int)
    flags[:exceptions] = 1

    result = basel_traffic_light(flags, require_250_observations=True)

    assert result.zone == expected_zone
    assert result.applicable_standard_window
    assert result.diagnostic_only

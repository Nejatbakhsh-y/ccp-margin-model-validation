from __future__ import annotations

import numpy as np
import pytest

from tests._step21_support import (
    UnsupportedSignature,
    find_callable,
    import_any,
    invoke,
    normalized_label,
)


def _classify(exception_count: int) -> str:
    module = import_any("ccp_margin.validation.traffic_light")
    function = find_callable(
        module,
        "traffic_light",
        "traffic_light_classification",
        "classify_traffic_light",
        "basel_traffic_light",
        contains=("traffic", "light"),
    )
    if function is None:
        pytest.fail("No public traffic-light callable was found.")

    exceptions = np.zeros(250, dtype=int)
    exceptions[:exception_count] = 1

    try:
        result = invoke(
            function,
            {
                "exceptions": exceptions,
                "n_observations": 250,
                "n_exceptions": exception_count,
                "alpha": 0.05,
            },
        )
    except UnsupportedSignature as exc:
        pytest.fail(str(exc))

    return normalized_label(result)


def test_basel_traffic_light_boundaries():
    assert "green" in _classify(4)
    assert "yellow" in _classify(5)
    assert "red" in _classify(10)

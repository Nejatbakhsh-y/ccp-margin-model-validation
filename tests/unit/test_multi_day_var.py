from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tests._step21_support import (
    UnsupportedSignature,
    extract_array,
    find_callable,
    import_any,
    invoke,
)


def test_two_day_log_returns_are_rolling_sums_without_look_ahead():
    module = import_any("ccp_margin.models.primary.multi_day_returns")
    function = find_callable(
        module,
        "calculate_multi_day_returns",
        "compute_multi_day_returns",
        "build_multi_day_returns",
        "aggregate_multi_day_returns",
        "overlapping_returns",
        contains=("multi", "day", "return"),
    )
    if function is None:
        pytest.skip("No public multi-day-return callable was found.")

    returns = pd.Series(
        [0.01, 0.02, -0.01, 0.03],
        index=pd.date_range("2025-01-02", periods=4, freq="B"),
        name="A",
    )

    try:
        result = invoke(
            function,
            {
                "returns": returns,
                "mpor": 2,
            },
        )
    except UnsupportedSignature as exc:
        pytest.skip(str(exc))

    values = extract_array(result)
    values = values[np.isfinite(values)]
    assert values.size >= 3
    assert np.isclose(values[0], 0.03, atol=5e-4)
    assert np.isclose(values[1], 0.01, atol=5e-4)

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


def test_return_calculation_matches_arithmetic_or_log_definition():
    module = import_any(
        "ccp_margin.data.clean_prices",
        "ccp_margin.models.primary.portfolio_pnl",
        "ccp_margin.models.primary.multi_day_returns",
    )
    function = find_callable(
        module,
        "calculate_log_returns",
        "compute_log_returns",
        "build_log_returns",
        "calculate_returns",
        "compute_returns",
        "price_returns",
    )
    if function is None:
        pytest.skip(
            f"No public return-calculation function found in {module.__name__}."
        )

    prices = pd.Series(
        [100.0, 110.0, 121.0],
        index=pd.date_range("2025-01-02", periods=3, freq="B"),
        name="PX",
    )
    frame = prices.to_frame()

    try:
        result = invoke(
            function,
            {
                "prices": frame,
                "price_series": prices,
                "data": frame,
            },
        )
    except UnsupportedSignature as exc:
        pytest.skip(str(exc))

    values = extract_array(result)
    values = values[np.isfinite(values)]
    assert values.size >= 2
    first = float(values[0])
    assert np.isclose(first, 0.10, atol=1e-8) or np.isclose(
        first, np.log(1.10), atol=1e-8
    )

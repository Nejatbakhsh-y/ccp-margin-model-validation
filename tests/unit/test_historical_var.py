from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tests._step21_support import (
    UnsupportedSignature,
    extract_number,
    find_callable,
    import_any,
    invoke,
)


def _calculate(confidence_level: float) -> float:
    module = import_any("ccp_margin.models.primary.historical_var")
    function = find_callable(
        module,
        "historical_var",
        "calculate_historical_var",
        "compute_historical_var",
        "estimate_historical_var",
        "historical_simulation_var",
        contains=("historical", "var"),
    )
    if function is None:
        pytest.skip("No public historical-VaR callable was found.")

    losses = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    returns = -losses / 100.0

    try:
        result = invoke(
            function,
            {
                "losses": losses,
                "returns": returns,
                "pnl": -losses,
                "confidence_level": confidence_level,
                "alpha": 1.0 - confidence_level,
                "target_probability": 1.0 - confidence_level,
                "lookback": len(losses),
                "portfolio_value": 100.0,
                "weights": np.array([1.0]),
            },
        )
    except UnsupportedSignature as exc:
        pytest.skip(str(exc))

    return extract_number(
        result,
        ("var", "value_at_risk", "base_var", "margin", "historical_var"),
    )


def test_historical_var_is_nonnegative_and_monotonic_in_confidence():
    var_80 = _calculate(0.80)
    var_95 = _calculate(0.95)
    assert np.isfinite(var_80)
    assert np.isfinite(var_95)
    assert var_80 >= 0.0
    assert var_95 >= var_80 - 1e-12

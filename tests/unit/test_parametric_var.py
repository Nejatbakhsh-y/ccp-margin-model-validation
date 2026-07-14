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
    module = import_any("ccp_margin.models.challenger.parametric_var")
    function = find_callable(
        module,
        "parametric_var",
        "calculate_parametric_var",
        "compute_parametric_var",
        "estimate_parametric_var",
        "variance_covariance_var",
        contains=("parametric", "var"),
    )
    if function is None:
        pytest.skip("No public parametric-VaR callable was found.")

    returns = pd.DataFrame(
        {
            "A": [-0.02, 0.01, -0.01, 0.015, 0.005, -0.005],
            "B": [-0.01, 0.004, -0.006, 0.009, 0.003, -0.002],
        }
    )
    weights = np.array([0.60, 0.40])
    covariance = returns.cov().to_numpy()

    try:
        result = invoke(
            function,
            {
                "returns": returns,
                "confidence_level": confidence_level,
                "alpha": 1.0 - confidence_level,
                "target_probability": 1.0 - confidence_level,
                "weights": weights,
                "covariance": covariance,
                "portfolio_value": 1_000_000.0,
                "mpor": 1,
            },
        )
    except UnsupportedSignature as exc:
        pytest.skip(str(exc))

    return extract_number(
        result,
        ("var", "value_at_risk", "base_var", "margin", "parametric_var"),
    )


def test_parametric_var_is_finite_nonnegative_and_monotonic():
    var_95 = _calculate(0.95)
    var_99 = _calculate(0.99)
    assert np.isfinite(var_95)
    assert np.isfinite(var_99)
    assert var_95 >= 0.0
    assert var_99 >= var_95 - 1e-12

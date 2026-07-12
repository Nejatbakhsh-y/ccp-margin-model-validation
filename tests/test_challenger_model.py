"""Tests for the Step 11 parametric challenger margin model."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ccp_margin.models.challenger.correlation_controls import correct_covariance_psd
from ccp_margin.models.challenger.ewma_covariance import (
    compound_multi_day_returns,
    ewma_covariance,
)
from ccp_margin.models.challenger.parametric_var import ParametricVaRModel


def _returns(seed: int = 2026, observations: int = 800) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    market = rng.normal(0.0, 0.01, observations)
    return pd.DataFrame(
        {
            "AAA": market + rng.normal(0.0, 0.005, observations),
            "BBB": 0.45 * market + rng.normal(0.0, 0.008, observations),
            "CCC": -0.20 * market + rng.normal(0.0, 0.012, observations),
        },
        index=pd.date_range("2020-01-01", periods=observations, freq="B"),
    )


def _positions() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "security_id": ["AAA", "BBB", "CCC"],
            "market_value": [1_000_000.0, 800_000.0, 500_000.0],
            "long_short_flag": ["long", "long", "short"],
        }
    )


def test_ewma_is_deterministic() -> None:
    returns = _returns()
    first = ewma_covariance(returns, decay_factor=0.94)
    second = ewma_covariance(returns, decay_factor=0.94)
    pd.testing.assert_frame_equal(first.covariance, second.covariance)
    pd.testing.assert_series_equal(first.mean_returns, second.mean_returns)


def test_psd_correction_repairs_indefinite_matrix() -> None:
    covariance = pd.DataFrame(
        [[1.0, 2.0], [2.0, 1.0]],
        index=["A", "B"],
        columns=["A", "B"],
    )
    result = correct_covariance_psd(covariance)
    assert result.was_corrected
    assert np.linalg.eigvalsh(result.covariance.to_numpy()).min() >= -1.0e-10
    np.testing.assert_allclose(
        np.diag(result.covariance.to_numpy()),
        np.diag(covariance.to_numpy()),
        rtol=1.0e-10,
        atol=1.0e-10,
    )


def test_overlapping_multi_day_returns_have_expected_length() -> None:
    returns = _returns(observations=20)
    result = compound_multi_day_returns(returns, 5, overlapping=True)
    assert len(result) == 16


def test_non_overlapping_multi_day_returns_reduce_dependence() -> None:
    returns = _returns(observations=20)
    overlapping = compound_multi_day_returns(returns, 5, overlapping=True)
    non_overlapping = compound_multi_day_returns(returns, 5, overlapping=False)
    assert len(non_overlapping) < len(overlapping)


def test_model_supports_one_three_and_five_day_horizons() -> None:
    model = ParametricVaRModel(
        covariance_method="ewma",
        multi_day_method="sqrt_time",
    )
    result = model.calculate(_positions(), _returns(), horizons=(1, 3, 5))
    assert set(result.horizons) == {1, 3, 5}
    assert all(item.var >= 0.0 for item in result.horizons.values())


def test_sqrt_time_volatility_scaling() -> None:
    model = ParametricVaRModel(
        covariance_method="sample",
        multi_day_method="sqrt_time",
        student_t_sensitivity_df=None,
        correlation_stress_multiplier=None,
    )
    result = model.calculate(_positions(), _returns(), horizons=(1, 5))
    one_day = result.horizons[1].portfolio_volatility
    five_day = result.horizons[5].portfolio_volatility
    assert five_day == pytest.approx(one_day * np.sqrt(5.0), rel=1.0e-10)


def test_direct_multi_day_alternative() -> None:
    model = ParametricVaRModel(
        covariance_method="sample",
        multi_day_method="direct",
        direct_returns_overlapping=True,
    )
    result = model.calculate(_positions(), _returns(), horizons=(3, 5))
    assert result.horizons[3].multi_day_method == "direct"
    assert result.horizons[5].observations_used > 0


def test_component_var_reconciles_to_portfolio_var() -> None:
    model = ParametricVaRModel()
    result = model.calculate(_positions(), _returns(), horizons=(1,))
    one_day = result.horizons[1]
    assert one_day.component_var.sum() == pytest.approx(one_day.var, rel=1.0e-10)


def test_student_t_sensitivity_is_reported() -> None:
    model = ParametricVaRModel(student_t_sensitivity_df=6.0)
    result = model.calculate(_positions(), _returns(), horizons=(1,))
    assert result.horizons[1].student_t_sensitivity_var is not None


def test_missing_risk_factor_can_raise_or_drop() -> None:
    positions = _positions()
    returns = _returns().drop(columns="CCC")

    strict_model = ParametricVaRModel(missing_risk_factor_policy="raise")
    with pytest.raises(ValueError, match="CCC"):
        strict_model.calculate(positions, returns)

    drop_model = ParametricVaRModel(missing_risk_factor_policy="drop")
    result = drop_model.calculate(positions, returns, horizons=(1,))
    assert result.excluded_risk_factors == ("CCC",)
    assert "CCC" not in result.included_risk_factors


def test_correlation_stress_is_reported() -> None:
    model = ParametricVaRModel(correlation_stress_multiplier=1.25)
    result = model.calculate(_positions(), _returns(), horizons=(1,))
    assert result.horizons[1].correlation_stress_var is not None

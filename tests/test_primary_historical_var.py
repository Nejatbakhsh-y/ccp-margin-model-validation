from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ccp_margin.models.primary.historical_var import (
    HistoricalSimulationVaR,
    HistoricalVaRConfig,
)
from ccp_margin.models.primary.multi_day_returns import (
    non_overlapping_multi_day_returns,
    overlapping_multi_day_returns,
)
from ccp_margin.models.primary.portfolio_pnl import simulate_portfolio_pnl


def _positions() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "valuation_date": ["2026-01-30", "2026-01-30"],
            "member_id": ["CM001", "CM001"],
            "portfolio_id": ["P001", "P001"],
            "security_id": ["AAA", "BBB"],
            "quantity": [100.0, 50.0],
            "price": [100.0, 200.0],
            "market_value": [10_000.0, 10_000.0],
            "long_short_flag": ["LONG", "SHORT"],
            "sector": ["Technology", "Financials"],
            "asset_class": ["Equity", "Equity"],
            "liquidity_bucket": ["High", "Medium"],
        }
    )


def _returns(periods: int = 30) -> pd.DataFrame:
    dates = pd.bdate_range("2025-12-01", periods=periods)
    return pd.DataFrame(
        {
            "AAA": np.linspace(-0.03, 0.02, periods),
            "BBB": np.linspace(0.025, -0.015, periods),
        },
        index=dates,
    )


def test_direct_overlapping_three_day_return() -> None:
    daily = _returns(6)
    result = overlapping_multi_day_returns(daily, 3)
    expected = (1 + daily["AAA"].iloc[:3]).prod() - 1
    assert result["AAA"].iloc[2] == pytest.approx(expected)


def test_non_overlapping_has_disjoint_blocks() -> None:
    daily = _returns(7)
    result = non_overlapping_multi_day_returns(daily, 3, anchor="end")
    assert len(result) == 2
    expected_last = (1 + daily["AAA"].iloc[-3:]).prod() - 1
    assert result["AAA"].iloc[-1] == pytest.approx(expected_last)


def test_long_short_current_position_pnl() -> None:
    scenario_returns = pd.DataFrame(
        {"AAA": [0.10], "BBB": [0.10]},
        index=[pd.Timestamp("2025-12-31")],
    )
    result = simulate_portfolio_pnl(_positions(), scenario_returns)
    # +1000 long AAA and -1000 short BBB cancel.
    assert result.portfolio_pnl.iloc[0] == pytest.approx(0.0)


def test_model_is_deterministic_and_preserves_distribution() -> None:
    config = HistoricalVaRConfig(
        confidence_level=0.99,
        lookback_days=20,
        minimum_scenarios=10,
        quantile_method="higher",
    )
    model = HistoricalSimulationVaR(config)
    first = model.calculate(
        _positions(),
        _returns(30),
        horizon_days=3,
        valuation_date="2026-01-30",
    )
    second = model.calculate(
        _positions(),
        _returns(30),
        horizon_days=3,
        valuation_date="2026-01-30",
    )

    assert first.value_at_risk == pytest.approx(second.value_at_risk)
    pd.testing.assert_frame_equal(first.pnl_distribution, second.pnl_distribution)
    pd.testing.assert_frame_equal(
        first.component_attribution,
        second.component_attribution,
    )
    assert first.scenario_count == len(first.pnl_distribution)
    assert first.component_attribution["scenario_loss_contribution"].sum() == (
        pytest.approx(first.value_at_risk)
    )


def test_missing_history_drop_scenario_policy() -> None:
    returns = _returns(30)
    returns.loc[returns.index[-1], "BBB"] = np.nan
    config = HistoricalVaRConfig(
        lookback_days=20,
        minimum_scenarios=10,
        missing_history_policy="drop_scenario",
    )
    result = HistoricalSimulationVaR(config).calculate(
        _positions(),
        returns,
        horizon_days=1,
        valuation_date=returns.index[-1],
    )
    assert result.diagnostics["dropped_scenario_count"] == 1
    assert result.missing_history_report["missing_observations"].sum() == 1


def test_missing_history_error_policy() -> None:
    returns = _returns(30).drop(columns=["BBB"])
    config = HistoricalVaRConfig(
        lookback_days=20,
        minimum_scenarios=10,
        missing_history_policy="error",
    )
    with pytest.raises(ValueError, match="risk-factor history is missing"):
        HistoricalSimulationVaR(config).calculate(
            _positions(),
            returns,
            horizon_days=1,
            valuation_date=returns.index[-1],
        )

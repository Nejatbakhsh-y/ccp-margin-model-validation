from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from ccp_margin.stress.historical import (
    HistoricalScenario,
    apply_security_shocks,
    compound_scenario_returns,
)
from ccp_margin.stress.hypothetical import (
    correlation_convergence_scenario,
    equity_price_scenarios,
    trading_volume_scenario,
    treasury_yield_scenarios,
)
from ccp_margin.stress.reverse_stress import (
    run_reverse_stress_tests,
    solve_exhaustion_shock,
)


def _positions() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "member_id": ["M1", "M1", "M2", "M2"],
            "security_id": ["SPY", "TLT", "SPY", "LQD"],
            "market_value": [100.0, 50.0, -80.0, 120.0],
            "asset_class": ["equity", "rates", "equity", "credit"],
            "liquidity_bucket": ["high", "high", "high", "medium"],
            "sector": ["broad", "rates", "broad", "credit"],
        }
    )


def _returns(rows: int = 30) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=rows, freq="B")
    data = {
        "SPY": np.linspace(-0.01, 0.01, rows),
        "TLT": np.linspace(0.005, -0.005, rows),
        "LQD": np.linspace(-0.003, 0.004, rows),
    }
    return pd.DataFrame(data, index=index)


def _margin() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "member_id": ["M1", "M2"],
            "total_margin": [30.0, 40.0],
            "liquidity_addon": [4.0, 9.0],
            "gross_exposure": [150.0, 200.0],
            "net_exposure": [150.0, 40.0],
        }
    )


def test_historical_compounding_is_exact() -> None:
    returns = pd.DataFrame(
        {"SPY": [0.10, -0.10]},
        index=pd.to_datetime(["2020-01-02", "2020-01-03"]),
    )
    scenario = HistoricalScenario(
        "TEST",
        "Test",
        pd.Timestamp("2020-01-02"),
        pd.Timestamp("2020-01-03"),
    )
    shocks, observations, _, _ = compound_scenario_returns(
        returns, scenario, ["SPY"]
    )
    assert observations == 2
    assert np.isclose(shocks["SPY"], -0.01)


def test_equity_shock_respects_signed_positions() -> None:
    results = equity_price_scenarios(_positions(), ["SPY"], [0.20])[0]
    m1 = results.loc[results["member_id"] == "M1"].iloc[0]
    m2 = results.loc[results["member_id"] == "M2"].iloc[0]
    assert np.isclose(m1["scenario_pnl"], -20.0)
    assert np.isclose(m1["stress_requirement"], 20.0)
    assert np.isclose(m2["scenario_pnl"], 16.0)
    assert np.isclose(m2["stress_requirement"], 0.0)


def test_treasury_duration_convexity_formula() -> None:
    result = treasury_yield_scenarios(
        _positions(),
        ["TLT"],
        [100],
        {"TLT": 10.0},
        {"TLT": 100.0},
    )[0]
    m1 = result.loc[result["member_id"] == "M1"].iloc[0]
    expected_return = -10.0 * 0.01 + 0.5 * 100.0 * 0.01**2
    assert np.isclose(m1["scenario_pnl"], 50.0 * expected_return)


def test_volume_stress_recalculates_total_requirement() -> None:
    result = trading_volume_scenario(
        _margin(), decline_pct=0.80, impact_exponent=0.50
    )
    m1 = result.loc[result["member_id"] == "M1"].iloc[0]
    multiplier = 0.20 ** -0.50
    expected = 30.0 - 4.0 + 4.0 * multiplier
    assert np.isclose(m1["stress_requirement"], expected)


def test_correlation_scenario_is_finite_and_nonnegative() -> None:
    result = correlation_convergence_scenario(
        _positions(),
        _returns(),
        target_correlation=0.95,
        confidence_level=0.99,
        horizon_days=5,
        lookback_days=20,
    )
    assert len(result) == 2
    assert np.isfinite(result["stress_requirement"]).all()
    assert (result["stress_requirement"] >= 0.0).all()


def test_reverse_stress_solver_and_member_results() -> None:
    solution = solve_exhaustion_shock(lambda shock: 200.0 * shock, 40.0)
    assert solution["exhaustion_found"]
    assert np.isclose(solution["shock_required"], 0.20, atol=1e-7)

    results = run_reverse_stress_tests(
        _positions(), _margin(), equity_securities=["SPY"]
    )
    row = results.loc[
        (results["member_id"] == "M1")
        & (results["reverse_stress_id"] == "REVERSE_UNIFORM_ADVERSE")
    ].iloc[0]
    assert np.isclose(row["shock_required"], 30.0 / 150.0, atol=1e-7)


def test_configuration_contains_exactly_twenty_scenarios() -> None:
    config_path = (
        Path(__file__).resolve().parents[1] / "configs" / "stress_scenarios.yaml"
    )
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    historical = config["historical_scenarios"]
    hypothetical = config["hypothetical_scenarios"]
    count = (
        len(historical)
        + len(hypothetical["equity_down_pct"])
        + len(hypothetical["treasury_yield_up_bps"])
        + len(hypothetical["credit_spread_wider_bps"])
        + 5
    )
    assert len(historical) == 6
    assert count == 20

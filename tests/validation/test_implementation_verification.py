import numpy as np
import pandas as pd

from ccp_margin.validation.implementation_verification import (
    independently_calculate_exception_flags,
    independently_calculate_portfolio_pnl,
    independently_calculate_returns,
    independently_calculate_total_margin,
    independently_calculate_var,
    reconcile_arrays,
    verify_implementation,
)


def test_independent_calculations():
    prices = pd.DataFrame(
        {"A": [100.0, 110.0, 99.0], "B": [50.0, 55.0, 60.5]}
    )
    returns = independently_calculate_returns(prices).dropna()
    pnl = independently_calculate_portfolio_pnl(
        returns,
        {"A": 1000.0, "B": -500.0},
    )
    var = independently_calculate_var(pnl, confidence_level=0.99)
    margin = independently_calculate_total_margin(
        var,
        liquidity_addon=10.0,
        concentration_addon=20.0,
        gap_risk_addon=5.0,
        stress_buffer=15.0,
    )
    flags = independently_calculate_exception_flags(
        [float(margin) + 1.0],
        [float(margin)],
    )

    assert list(returns.columns) == ["A", "B"]
    assert len(pnl) == 2
    assert var >= 0.0
    assert float(margin) == var + 50.0
    assert flags.tolist() == [True]


def test_reconciliation_and_suite():
    check = reconcile_arrays(
        [1.0, 2.0],
        [1.0, 2.0 + 1e-9],
        name="var",
    )
    assert check.passed

    suite = verify_implementation(
        {"var": [1.0], "total_margin": [2.0]},
        {"var": [1.0], "total_margin": [2.0]},
    )
    assert suite.passed

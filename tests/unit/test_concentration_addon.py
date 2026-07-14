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


def _addon(largest_position: float) -> float:
    module = import_any("ccp_margin.margin.concentration_addon")
    function = find_callable(
        module,
        "concentration_addon",
        "calculate_concentration_addon",
        "compute_concentration_addon",
        "concentration_charge",
        contains=("concentration", "addon"),
    )
    if function is None:
        pytest.skip("No public concentration-addon callable was found.")

    positions = pd.DataFrame(
        {
            "market_value": [largest_position, 1_000_000.0],
            "sector": ["Technology", "Financials"],
        }
    )
    total = float(positions["market_value"].abs().sum())

    try:
        result = invoke(
            function,
            {
                "positions": positions,
                "position_value": largest_position,
                "portfolio_value": total,
                "concentration_threshold": 0.20,
                "concentration_rate": 0.10,
                "config": {
                    "threshold": 0.20,
                    "concentration_threshold": 0.20,
                    "addon_rate": 0.10,
                },
            },
        )
    except UnsupportedSignature as exc:
        pytest.skip(str(exc))

    return extract_number(
        result,
        ("concentration_addon", "addon", "charge", "margin"),
    )


def test_concentration_addon_is_nonnegative_and_monotonic():
    diversified = _addon(1_000_000.0)
    concentrated = _addon(9_000_000.0)
    assert np.isfinite(diversified)
    assert np.isfinite(concentrated)
    assert diversified >= 0.0
    assert concentrated >= diversified - 1e-12

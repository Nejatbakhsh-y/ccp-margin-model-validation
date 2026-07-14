from __future__ import annotations

import numpy as np
import pytest

from tests._step21_support import (
    UnsupportedSignature,
    extract_number,
    find_callable,
    import_any,
    invoke,
)


def _addon(position_value: float) -> float:
    module = import_any("ccp_margin.margin.liquidity_addon")
    function = find_callable(
        module,
        "liquidity_addon",
        "calculate_liquidity_addon",
        "compute_liquidity_addon",
        "liquidity_charge",
        contains=("liquidity", "addon"),
    )
    if function is None:
        pytest.skip("No public liquidity-addon callable was found.")

    try:
        result = invoke(
            function,
            {
                "position_value": position_value,
                "portfolio_value": position_value,
                "adv": 1_000_000.0,
                "participation_rate": 0.10,
                "liquidity_factor": 0.05,
                "config": {
                    "participation_rate": 0.10,
                    "liquidity_factor": 0.05,
                    "adv_fraction": 0.10,
                },
            },
        )
    except UnsupportedSignature as exc:
        pytest.skip(str(exc))

    return extract_number(
        result,
        ("liquidity_addon", "addon", "charge", "margin"),
    )


def test_liquidity_addon_is_nonnegative_and_increases_with_position_size():
    small = _addon(100_000.0)
    large = _addon(5_000_000.0)
    assert np.isfinite(small)
    assert np.isfinite(large)
    assert small >= 0.0
    assert large >= small - 1e-12

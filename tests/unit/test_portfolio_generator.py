from __future__ import annotations

import pandas as pd
import pytest

from tests._step21_support import (
    UnsupportedSignature,
    find_callable,
    import_any,
    invoke,
    stable_digest,
)


def test_portfolio_generation_is_reproducible_for_fixed_seed():
    module = import_any("ccp_margin.portfolio.generator")
    function = find_callable(
        module,
        "generate_member_portfolios",
        "generate_portfolios",
        "generate_portfolio",
        "build_member_portfolios",
        "create_member_portfolios",
        contains=("generate", "portfolio"),
    )
    if function is None:
        pytest.skip("No public portfolio-generator callable was found.")

    universe = pd.DataFrame(
        {
            "security_id": ["A", "B", "C", "D", "E"],
            "sector": [
                "Technology",
                "Financials",
                "Healthcare",
                "Industrials",
                "Energy",
            ],
            "asset_class": ["Equity"] * 5,
            "liquidity_bucket": ["high", "high", "medium", "medium", "low"],
            "price": [100.0, 50.0, 80.0, 40.0, 25.0],
        }
    )
    config = {
        "random_seed": 2026,
        "n_members": 3,
        "n_securities": 5,
        "portfolio_categories": ["diversified_long_only"],
    }
    values = {
        "universe": universe,
        "config": config,
        "seed": 2026,
        "n_members": 3,
        "n_securities": 5,
    }

    try:
        first = invoke(function, values)
        second = invoke(function, values)
    except UnsupportedSignature as exc:
        pytest.skip(str(exc))

    assert stable_digest(first) == stable_digest(second)

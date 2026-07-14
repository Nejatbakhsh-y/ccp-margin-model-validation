from __future__ import annotations

import pandas as pd
import pytest

from ccp_margin.margin.base_margin import calculate_base_margin


def test_base_margin_applies_floor_and_cap() -> None:
    result = calculate_base_margin(
        pd.DataFrame({"member_id": ["M1", "M2"], "base_var": [50.0, 500.0]}),
        floor_usd=100.0,
        cap_usd=400.0,
    )
    actual = result.member_margin.set_index("member_id")["base_margin"].to_dict()
    assert actual == {"M1": 100.0, "M2": 400.0}


def test_base_margin_rejects_negative_var() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        calculate_base_margin(pd.DataFrame({"member_id": ["M1"], "base_var": [-1.0]}))

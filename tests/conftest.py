from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture
def deterministic_returns() -> pd.DataFrame:
    index = pd.date_range("2025-01-02", periods=8, freq="B")
    return pd.DataFrame(
        {
            "EQ_A": [0.010, -0.015, 0.008, -0.004, 0.012, -0.020, 0.006, 0.003],
            "EQ_B": [0.004, -0.006, 0.005, -0.002, 0.009, -0.011, 0.002, 0.001],
        },
        index=index,
    )


@pytest.fixture
def deterministic_positions() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "member_id": ["CM001", "CM001"],
            "security_id": ["EQ_A", "EQ_B"],
            "market_value": [1_000_000.0, 500_000.0],
            "sector": ["Technology", "Financials"],
            "asset_class": ["Equity", "Equity"],
            "liquidity_bucket": ["high", "medium"],
            "average_daily_volume": [20_000_000.0, 8_000_000.0],
        }
    )

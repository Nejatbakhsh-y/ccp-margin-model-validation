from __future__ import annotations

import numpy as np
import pandas as pd

from tests._step21_support import ROOT, first_existing, read_table


def test_processed_market_data_and_returns_are_available_and_valid():
    market_path = first_existing(
        "data/processed/market_prices_clean.parquet",
        "data/processed/clean_market_data.parquet",
        "data/processed/market_prices.parquet",
    )
    returns_path = first_existing(
        "data/processed/log_returns_wide.parquet",
        "data/processed/returns_wide.parquet",
        "data/processed/risk_factor_returns.parquet",
    )

    assert market_path is not None, "No processed market-price file was found."
    assert returns_path is not None, "No processed return file was found."

    market = read_table(market_path)
    returns = read_table(returns_path)

    assert not market.empty
    assert not returns.empty
    assert len(returns) >= 250

    numeric = returns.select_dtypes(include=[np.number])
    assert not numeric.empty
    assert np.isfinite(numeric.to_numpy(dtype=float)).any()

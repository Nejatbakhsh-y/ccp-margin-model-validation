from __future__ import annotations

import pandas as pd
import pytest


@pytest.fixture
def positions() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "member_id": ["M001", "M001", "M001", "M002", "M002"],
            "security_id": ["AAA", "BBB", "CCC", "DDD", "EEE"],
            "market_value": [600.0, 250.0, -150.0, 500.0, -500.0],
            "liquidity_bucket": ["high", "medium", "low", "medium", "medium"],
            "sector": ["technology", "financials", "healthcare", "rates", "rates"],
            "asset_class": ["equity", "equity", "equity", "rates", "rates"],
        }
    )


@pytest.fixture
def margin_config() -> dict:
    return {
        "base_margin": {
            "var_col": "base_var",
            "floor_usd": 0.0,
            "cap_usd": None,
        },
        "liquidity_addon": {
            "parameter_source": "Unit-test approved assumptions",
            "rates_by_bucket": {"high": 0.001, "medium": 0.003, "low": 0.01},
            "minimum_usd": 0.0,
            "maximum_fraction_of_gross": 0.05,
        },
        "concentration_addon": {
            "parameter_source": "Unit-test approved assumptions",
            "single_name_threshold": 0.20,
            "single_name_rate": 0.10,
            "sector_threshold": 0.40,
            "sector_rate": 0.05,
            "aggregation_method": "max",
            "minimum_usd": 0.0,
            "maximum_fraction_of_gross": 0.10,
        },
        "gap_risk_addon": {
            "parameter_source": "Unit-test approved assumptions",
            "shocks_by_asset_class": {"equity": 0.08, "rates": 0.02},
            "minimum_usd": 0.0,
            "maximum_fraction_of_gross": 0.20,
        },
        "stress_buffer": {
            "parameter_source": "Unit-test approved stress scenarios",
            "required_coverage_ratio": 1.0,
            "maximum_usd": None,
        },
    }

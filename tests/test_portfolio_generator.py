from __future__ import annotations

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from ccp_margin.portfolio.concentration import calculate_concentration_metrics
from ccp_margin.portfolio.exposures import calculate_exposures
from ccp_margin.portfolio.generator import (
    PORTFOLIO_CATEGORIES,
    PortfolioGenerationConfig,
    canonical_portfolio_sha256,
    generate_synthetic_portfolios,
)
from ccp_margin.portfolio.liquidity import calculate_liquidity_metrics


def sample_market_data() -> pd.DataFrame:
    dates = pd.date_range("2026-01-02", periods=8, freq="B")
    securities = [
        ("SPY", "Broad Market", "Equity", "High"),
        ("QQQ", "Technology", "Equity", "High"),
        ("IWM", "Small Cap", "Equity", "High"),
        ("EFA", "International", "Equity", "Medium"),
        ("EEM", "International", "Equity", "Medium"),
        ("TLT", "Government Rates", "Rates", "High"),
        ("IEF", "Government Rates", "Rates", "High"),
        ("LQD", "Investment Grade Credit", "Credit", "Medium"),
        ("HYG", "High Yield Credit", "Credit", "Low"),
        ("GLD", "Precious Metals", "Commodity", "Medium"),
        ("DBC", "Broad Commodities", "Commodity", "Low"),
        ("VNQ", "Real Estate", "Equity", "Medium"),
    ]
    rows = []
    for date_index, date in enumerate(dates):
        for security_index, (security, sector, asset_class, liquidity) in enumerate(
            securities
        ):
            rows.append(
                {
                    "valuation_date": date,
                    "security_id": security,
                    "price": 50.0 + security_index * 5.0 + date_index * 0.25,
                    "volume": 1_000_000 - security_index * 50_000,
                    "sector": sector,
                    "asset_class": asset_class,
                    "liquidity_bucket": liquidity,
                }
            )
    return pd.DataFrame(rows)


def config(seed: int = 2026) -> PortfolioGenerationConfig:
    return PortfolioGenerationConfig(
        random_seed=seed,
        number_of_members=10,
        minimum_positions=3,
        maximum_positions=7,
        gross_notional_min=10_000_000,
        gross_notional_max=50_000_000,
    )


def test_same_seed_reproduces_identical_portfolios() -> None:
    market_data = sample_market_data()
    first = generate_synthetic_portfolios(market_data, config(2026))
    second = generate_synthetic_portfolios(market_data, config(2026))
    assert_frame_equal(first, second, check_exact=True)
    assert canonical_portfolio_sha256(first) == canonical_portfolio_sha256(second)


def test_different_seed_changes_portfolios() -> None:
    market_data = sample_market_data()
    first = generate_synthetic_portfolios(market_data, config(2026))
    second = generate_synthetic_portfolios(market_data, config(2027))
    assert canonical_portfolio_sha256(first) != canonical_portfolio_sha256(second)


def test_required_schema_and_categories() -> None:
    positions = generate_synthetic_portfolios(sample_market_data(), config())
    required = {
        "valuation_date",
        "member_id",
        "portfolio_id",
        "security_id",
        "quantity",
        "price",
        "market_value",
        "long_short_flag",
        "sector",
        "asset_class",
        "liquidity_bucket",
    }
    assert required.issubset(positions.columns)
    categories = set(positions["portfolio_category"].unique())
    assert categories == set(PORTFOLIO_CATEGORIES)


def test_no_duplicate_positions_and_values_reconcile() -> None:
    positions = generate_synthetic_portfolios(sample_market_data(), config())
    keys = ["valuation_date", "member_id", "portfolio_id", "security_id"]
    assert not positions.duplicated(keys).any()
    assert (positions["price"] > 0).all()
    expected = (positions["quantity"] * positions["price"]).round(2)
    assert np.allclose(positions["market_value"], expected)
    assert set(positions["long_short_flag"]) <= {"LONG", "SHORT"}


def test_portfolio_analytics_return_one_row_per_portfolio_date() -> None:
    positions = generate_synthetic_portfolios(sample_market_data(), config())
    unique_groups = positions[
        ["valuation_date", "member_id", "portfolio_id"]
    ].drop_duplicates()
    exposures = calculate_exposures(positions)
    concentration = calculate_concentration_metrics(positions)
    liquidity = calculate_liquidity_metrics(positions)
    assert len(exposures) == len(unique_groups)
    assert len(concentration) == len(unique_groups)
    assert len(liquidity) == len(unique_groups)
    assert exposures["gross_exposure"].gt(0).all()
    assert concentration["hhi"].between(0, 1).all()
    assert liquidity["weighted_liquidity_score"].between(1, 5).all()

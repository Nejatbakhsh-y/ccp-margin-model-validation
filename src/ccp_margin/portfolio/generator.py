"""Deterministic synthetic clearing-member portfolio generation.

The generator selects one static set of positions for each synthetic member and
revalues those positions over the available market-data history.  Given the
same cleaned market data, configuration, NumPy version, and random seed, the
output is reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import StringIO
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

PORTFOLIO_CATEGORIES: tuple[str, ...] = (
    "diversified_long_only",
    "concentrated_equity",
    "technology_heavy",
    "small_cap_heavy",
    "international_equity",
    "rates_heavy",
    "credit_heavy",
    "long_short",
    "leveraged",
    "liquidity_stressed",
)

REQUIRED_POSITION_COLUMNS: tuple[str, ...] = (
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
)

# Metadata for a practical public ETF/equity universe. Unknown securities are
# handled by deterministic fallbacks and, when available, volume-based liquidity.
_DEFAULT_METADATA: dict[str, tuple[str, str, str]] = {
    "SPY": ("Broad Market", "Equity", "High"),
    "QQQ": ("Technology", "Equity", "High"),
    "IWM": ("Small Cap", "Equity", "High"),
    "IJR": ("Small Cap", "Equity", "High"),
    "VB": ("Small Cap", "Equity", "High"),
    "EFA": ("International", "Equity", "High"),
    "EEM": ("International", "Equity", "High"),
    "VEA": ("International", "Equity", "High"),
    "VWO": ("International", "Equity", "High"),
    "TLT": ("Government Rates", "Rates", "High"),
    "IEF": ("Government Rates", "Rates", "High"),
    "SHY": ("Government Rates", "Rates", "High"),
    "AGG": ("Aggregate Bonds", "Rates", "High"),
    "LQD": ("Investment Grade Credit", "Credit", "High"),
    "HYG": ("High Yield Credit", "Credit", "High"),
    "JNK": ("High Yield Credit", "Credit", "Medium"),
    "GLD": ("Precious Metals", "Commodity", "High"),
    "SLV": ("Precious Metals", "Commodity", "High"),
    "DBC": ("Broad Commodities", "Commodity", "Medium"),
    "USO": ("Energy", "Commodity", "High"),
    "VNQ": ("Real Estate", "Equity", "High"),
    "UUP": ("US Dollar", "FX", "Medium"),
    "FXE": ("Euro", "FX", "Medium"),
    "AAPL": ("Technology", "Equity", "High"),
    "MSFT": ("Technology", "Equity", "High"),
    "NVDA": ("Technology", "Equity", "High"),
    "META": ("Technology", "Equity", "High"),
    "GOOGL": ("Technology", "Equity", "High"),
    "GOOG": ("Technology", "Equity", "High"),
    "AMZN": ("Consumer Discretionary", "Equity", "High"),
    "TSLA": ("Consumer Discretionary", "Equity", "High"),
}

_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "valuation_date": ("valuation_date", "date", "Date", "timestamp"),
    "security_id": ("security_id", "ticker", "symbol", "asset", "Security"),
    "price": (
        "price",
        "adjusted_close",
        "adj_close",
        "Adj Close",
        "close",
        "Close",
    ),
    "volume": ("volume", "Volume", "trading_volume"),
}


@dataclass(frozen=True)
class PortfolioGenerationConfig:
    """Configuration for deterministic portfolio generation."""

    random_seed: int = 2026
    number_of_members: int = 30
    minimum_positions: int = 3
    maximum_positions: int = 10
    gross_notional_min: float = 10_000_000.0
    gross_notional_max: float = 1_000_000_000.0
    categories: tuple[str, ...] = PORTFOLIO_CATEGORIES

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "PortfolioGenerationConfig":
        project = raw.get("project", {}) if isinstance(raw, Mapping) else {}
        portfolio = raw.get("portfolio", {}) if isinstance(raw, Mapping) else {}
        categories = tuple(portfolio.get("categories", PORTFOLIO_CATEGORIES))
        config = cls(
            random_seed=int(project.get("random_seed", 2026)),
            number_of_members=int(portfolio.get("number_of_members", 30)),
            minimum_positions=int(portfolio.get("minimum_positions", 3)),
            maximum_positions=int(portfolio.get("maximum_positions", 10)),
            gross_notional_min=float(
                portfolio.get("gross_notional_min", 10_000_000)
            ),
            gross_notional_max=float(
                portfolio.get("gross_notional_max", 1_000_000_000)
            ),
            categories=categories,
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.number_of_members < 1:
            raise ValueError("number_of_members must be at least 1.")
        if self.minimum_positions < 1:
            raise ValueError("minimum_positions must be at least 1.")
        if self.maximum_positions < self.minimum_positions:
            raise ValueError("maximum_positions must be >= minimum_positions.")
        if self.gross_notional_min <= 0:
            raise ValueError("gross_notional_min must be positive.")
        if self.gross_notional_max < self.gross_notional_min:
            raise ValueError("gross_notional_max must be >= gross_notional_min.")
        unknown = sorted(set(self.categories) - set(PORTFOLIO_CATEGORIES))
        if unknown:
            raise ValueError(f"Unsupported portfolio categories: {unknown}")
        if not self.categories:
            raise ValueError("At least one portfolio category is required.")


def _find_column(frame: pd.DataFrame, canonical_name: str) -> str | None:
    for candidate in _COLUMN_ALIASES[canonical_name]:
        if candidate in frame.columns:
            return candidate
    return None


def _canonicalize_market_data(market_data: pd.DataFrame) -> pd.DataFrame:
    if market_data.empty:
        raise ValueError("Market data is empty.")

    date_col = _find_column(market_data, "valuation_date")
    security_col = _find_column(market_data, "security_id")
    price_col = _find_column(market_data, "price")
    if date_col is None or security_col is None or price_col is None:
        raise ValueError(
            "Market data must contain date, security, and price columns. "
            "Accepted aliases include valuation_date/date, security_id/ticker, "
            "and price/adjusted_close/close."
        )

    rename_map = {
        date_col: "valuation_date",
        security_col: "security_id",
        price_col: "price",
    }
    volume_col = _find_column(market_data, "volume")
    if volume_col is not None:
        rename_map[volume_col] = "volume"

    frame = market_data.rename(columns=rename_map).copy()
    keep = ["valuation_date", "security_id", "price"]
    for optional in ("volume", "sector", "asset_class", "liquidity_bucket"):
        if optional in frame.columns:
            keep.append(optional)
    frame = frame.loc[:, keep]

    frame["valuation_date"] = pd.to_datetime(
        frame["valuation_date"], errors="coerce"
    ).dt.normalize()
    frame["security_id"] = frame["security_id"].astype("string").str.strip().str.upper()
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")

    if frame["valuation_date"].isna().any():
        raise ValueError("Market data contains invalid or missing valuation dates.")
    if frame["security_id"].isna().any() or (frame["security_id"] == "").any():
        raise ValueError("Market data contains missing security identifiers.")
    if frame["price"].isna().any():
        raise ValueError(
            "Market data contains missing prices. Run the Step 8 data-quality "
            "controls and use the cleaned output."
        )
    if (frame["price"] <= 0).any():
        raise ValueError(
            "Market data contains non-positive prices. Run the Step 8 "
            "data-quality controls before portfolio generation."
        )

    duplicate_mask = frame.duplicated(
        subset=["valuation_date", "security_id"], keep=False
    )
    if duplicate_mask.any():
        sample = frame.loc[
            duplicate_mask, ["valuation_date", "security_id"]
        ].head(10)
        raise ValueError(
            "Duplicate security-date rows were found in market data. Sample:\n"
            + sample.to_string(index=False)
        )

    if "volume" in frame.columns:
        frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce")

    return frame.sort_values(["valuation_date", "security_id"], kind="mergesort").reset_index(drop=True)


def _infer_metadata(frame: pd.DataFrame) -> pd.DataFrame:
    latest = (
        frame.sort_values(["security_id", "valuation_date"], kind="mergesort")
        .groupby("security_id", as_index=False, sort=True)
        .tail(1)
        .copy()
    )

    securities = latest["security_id"].astype(str)
    default_sector = securities.map(
        lambda value: _DEFAULT_METADATA.get(value, ("Other", "Equity", "Medium"))[0]
    )
    default_asset_class = securities.map(
        lambda value: _DEFAULT_METADATA.get(value, ("Other", "Equity", "Medium"))[1]
    )
    default_liquidity = securities.map(
        lambda value: _DEFAULT_METADATA.get(value, ("Other", "Equity", "Medium"))[2]
    )

    if "sector" not in latest.columns:
        latest["sector"] = default_sector.to_numpy()
    else:
        latest["sector"] = latest["sector"].astype("string").fillna(default_sector)
        latest.loc[latest["sector"].str.strip() == "", "sector"] = default_sector

    if "asset_class" not in latest.columns:
        latest["asset_class"] = default_asset_class.to_numpy()
    else:
        latest["asset_class"] = (
            latest["asset_class"].astype("string").fillna(default_asset_class)
        )
        latest.loc[
            latest["asset_class"].str.strip() == "", "asset_class"
        ] = default_asset_class

    # Prefer explicit liquidity buckets. Otherwise derive deterministic buckets
    # from average dollar volume when volume is available.
    volume_liquidity: pd.Series | None = None
    if "volume" in frame.columns and frame["volume"].notna().any():
        volume_frame = frame.loc[frame["volume"].notna()].copy()
        volume_frame["dollar_volume"] = volume_frame["price"] * volume_frame["volume"]
        average_dollar_volume = volume_frame.groupby("security_id", sort=True)[
            "dollar_volume"
        ].mean()
        percentile = average_dollar_volume.rank(method="average", pct=True)
        volume_liquidity = pd.Series(
            np.select(
                [percentile <= 1 / 3, percentile <= 2 / 3],
                ["Low", "Medium"],
                default="High",
            ),
            index=percentile.index,
            dtype="string",
        )

    if "liquidity_bucket" not in latest.columns:
        latest["liquidity_bucket"] = default_liquidity.to_numpy()
    else:
        latest["liquidity_bucket"] = latest["liquidity_bucket"].astype("string")

    if volume_liquidity is not None:
        mapped_volume_bucket = latest["security_id"].map(volume_liquidity)
        latest["liquidity_bucket"] = latest["liquidity_bucket"].fillna(
            mapped_volume_bucket
        )
    latest["liquidity_bucket"] = latest["liquidity_bucket"].fillna(default_liquidity)
    latest.loc[
        latest["liquidity_bucket"].str.strip() == "", "liquidity_bucket"
    ] = default_liquidity

    allowed_buckets = {"High", "Medium", "Low"}
    latest["liquidity_bucket"] = latest["liquidity_bucket"].str.title()
    latest.loc[
        ~latest["liquidity_bucket"].isin(allowed_buckets), "liquidity_bucket"
    ] = "Medium"

    return latest[
        ["security_id", "price", "sector", "asset_class", "liquidity_bucket"]
    ].rename(columns={"price": "reference_price"})


def _selection_scores(universe: pd.DataFrame, category: str) -> np.ndarray:
    score = np.ones(len(universe), dtype=float)
    sector = universe["sector"].astype(str).str.casefold()
    asset_class = universe["asset_class"].astype(str).str.casefold()
    liquidity = universe["liquidity_bucket"].astype(str).str.casefold()
    security = universe["security_id"].astype(str).str.upper()

    equity = asset_class.eq("equity")
    technology = sector.str.contains("technology", regex=False) | security.isin(
        {"QQQ", "XLK", "AAPL", "MSFT", "NVDA", "META", "GOOG", "GOOGL"}
    )
    small_cap = sector.str.contains("small cap", regex=False) | security.isin(
        {"IWM", "IJR", "VB"}
    )
    international = sector.str.contains("international", regex=False) | security.isin(
        {"EFA", "EEM", "VEA", "VWO"}
    )
    rates = asset_class.eq("rates")
    credit = asset_class.eq("credit")
    low_liquidity = liquidity.eq("low")
    medium_liquidity = liquidity.eq("medium")

    if category == "concentrated_equity":
        score = np.where(equity, 10.0, 0.10)
    elif category == "technology_heavy":
        score = np.where(technology, 15.0, np.where(equity, 1.5, 0.20))
    elif category == "small_cap_heavy":
        score = np.where(small_cap, 15.0, np.where(equity, 1.5, 0.20))
    elif category == "international_equity":
        score = np.where(international, 15.0, np.where(equity, 1.0, 0.20))
    elif category == "rates_heavy":
        score = np.where(rates, 15.0, np.where(credit, 1.5, 0.20))
    elif category == "credit_heavy":
        score = np.where(credit, 15.0, np.where(rates, 1.5, 0.20))
    elif category == "long_short":
        score = np.where(equity, 8.0, 0.50)
    elif category == "leveraged":
        score = np.where(equity, 5.0, 1.0)
    elif category == "liquidity_stressed":
        score = np.where(low_liquidity, 20.0, np.where(medium_liquidity, 5.0, 0.50))
    elif category == "diversified_long_only":
        # Mildly favor underrepresented asset classes by giving every security
        # a positive score and avoiding category-specific concentration.
        score = np.ones(len(universe), dtype=float)
    else:
        raise ValueError(f"Unsupported portfolio category: {category}")

    if not np.isfinite(score).all() or score.sum() <= 0:
        return np.ones(len(universe), dtype=float)
    return score


def _position_count(
    category: str,
    config: PortfolioGenerationConfig,
    universe_size: int,
    rng: np.random.Generator,
) -> int:
    lower = min(config.minimum_positions, universe_size)
    upper = min(config.maximum_positions, universe_size)
    if lower < 1:
        raise ValueError("The market-data universe contains no eligible securities.")

    if category == "concentrated_equity":
        upper = min(upper, max(lower, 4))
    elif category == "diversified_long_only":
        lower = min(upper, max(lower, min(6, universe_size)))
    elif category == "long_short":
        lower = min(upper, max(lower, min(4, universe_size)))

    return int(rng.integers(lower, upper + 1)) if upper > lower else lower


def _absolute_weights(
    category: str, number_of_positions: int, rng: np.random.Generator
) -> np.ndarray:
    alpha_by_category = {
        "diversified_long_only": 2.50,
        "concentrated_equity": 0.25,
        "technology_heavy": 0.70,
        "small_cap_heavy": 0.70,
        "international_equity": 0.80,
        "rates_heavy": 0.80,
        "credit_heavy": 0.80,
        "long_short": 1.00,
        "leveraged": 0.60,
        "liquidity_stressed": 0.55,
    }
    alpha = np.full(number_of_positions, alpha_by_category[category], dtype=float)
    return rng.dirichlet(alpha)


def _position_signs(
    category: str, number_of_positions: int, rng: np.random.Generator
) -> np.ndarray:
    signs = np.ones(number_of_positions, dtype=np.int8)
    if category == "long_short":
        number_short = max(1, int(round(number_of_positions * 0.40)))
        number_short = min(number_short, number_of_positions - 1)
        signs[:number_short] = -1
        rng.shuffle(signs)
    elif category == "leveraged" and number_of_positions >= 3:
        # A leveraged portfolio can include a small financing/hedging short leg.
        number_short = max(1, int(round(number_of_positions * 0.20)))
        signs[:number_short] = -1
        rng.shuffle(signs)
    return signs


def _target_gross_notional(
    category: str,
    config: PortfolioGenerationConfig,
    rng: np.random.Generator,
) -> float:
    log_min = np.log10(config.gross_notional_min)
    log_max = np.log10(config.gross_notional_max)
    notional = float(10 ** rng.uniform(log_min, log_max))
    if category == "leveraged":
        notional *= 2.0
    return notional


def generate_synthetic_portfolios(
    market_data: pd.DataFrame,
    config: PortfolioGenerationConfig | Mapping[str, Any],
) -> pd.DataFrame:
    """Generate deterministic daily synthetic clearing-member positions.

    Parameters
    ----------
    market_data:
        Cleaned long-form price history. Required logical fields are date,
        security, and positive price. Optional metadata fields are sector,
        asset_class, liquidity_bucket, and volume.
    config:
        ``PortfolioGenerationConfig`` or the full project YAML mapping.

    Returns
    -------
    pandas.DataFrame
        Daily position records. In addition to the required fields, the output
        includes ``portfolio_category`` for validation and reporting.
    """

    if not isinstance(config, PortfolioGenerationConfig):
        config = PortfolioGenerationConfig.from_mapping(config)
    config.validate()

    frame = _canonicalize_market_data(market_data)
    universe = _infer_metadata(frame).sort_values("security_id", kind="mergesort")
    universe = universe.reset_index(drop=True)
    if len(universe) < config.minimum_positions:
        raise ValueError(
            f"Only {len(universe)} securities are available, but "
            f"minimum_positions={config.minimum_positions}."
        )

    rng = np.random.default_rng(config.random_seed)
    records: list[pd.DataFrame] = []

    price_history = frame[["valuation_date", "security_id", "price"]]

    for member_number in range(1, config.number_of_members + 1):
        category = config.categories[(member_number - 1) % len(config.categories)]
        member_id = f"CM{member_number:03d}"
        portfolio_id = f"PF{member_number:03d}"

        n_positions = _position_count(category, config, len(universe), rng)
        selection_score = _selection_scores(universe, category)
        probabilities = selection_score / selection_score.sum()
        selected_indices = rng.choice(
            len(universe),
            size=n_positions,
            replace=False,
            p=probabilities,
        )
        selected = (
            universe.iloc[np.sort(selected_indices)]
            .copy()
            .sort_values("security_id", kind="mergesort")
            .reset_index(drop=True)
        )

        weights = _absolute_weights(category, n_positions, rng)
        signs = _position_signs(category, n_positions, rng)
        gross_notional = _target_gross_notional(category, config, rng)
        position_notionals = gross_notional * weights

        raw_quantities = np.floor(
            position_notionals / selected["reference_price"].to_numpy(dtype=float)
        ).astype(np.int64)
        raw_quantities = np.maximum(raw_quantities, 1)
        signed_quantities = raw_quantities * signs.astype(np.int64)

        selected["quantity"] = signed_quantities
        selected["member_id"] = member_id
        selected["portfolio_id"] = portfolio_id
        selected["portfolio_category"] = category

        member_positions = price_history.merge(
            selected[
                [
                    "security_id",
                    "quantity",
                    "member_id",
                    "portfolio_id",
                    "portfolio_category",
                    "sector",
                    "asset_class",
                    "liquidity_bucket",
                ]
            ],
            on="security_id",
            how="inner",
            validate="many_to_one",
        )
        member_positions["market_value"] = (
            member_positions["quantity"] * member_positions["price"]
        ).round(2)
        member_positions["long_short_flag"] = np.where(
            member_positions["quantity"] >= 0, "LONG", "SHORT"
        )
        records.append(member_positions)

    positions = pd.concat(records, ignore_index=True)
    output_columns = [
        "valuation_date",
        "member_id",
        "portfolio_id",
        "portfolio_category",
        "security_id",
        "quantity",
        "price",
        "market_value",
        "long_short_flag",
        "sector",
        "asset_class",
        "liquidity_bucket",
    ]
    positions = positions.loc[:, output_columns]
    positions["quantity"] = positions["quantity"].astype("int64")
    positions["price"] = positions["price"].astype("float64")
    positions["market_value"] = positions["market_value"].astype("float64")
    positions = positions.sort_values(
        ["valuation_date", "member_id", "portfolio_id", "security_id"],
        kind="mergesort",
    ).reset_index(drop=True)

    duplicate_positions = positions.duplicated(
        subset=["valuation_date", "member_id", "portfolio_id", "security_id"]
    )
    if duplicate_positions.any():
        raise RuntimeError("The generated portfolio output contains duplicate positions.")

    return positions


def canonical_portfolio_sha256(positions: pd.DataFrame) -> str:
    """Return a deterministic SHA-256 hash of the logical position content."""

    missing = [column for column in REQUIRED_POSITION_COLUMNS if column not in positions]
    if missing:
        raise ValueError(f"Position data is missing required columns: {missing}")

    ordered_columns = [
        "valuation_date",
        "member_id",
        "portfolio_id",
        "portfolio_category",
        "security_id",
        "quantity",
        "price",
        "market_value",
        "long_short_flag",
        "sector",
        "asset_class",
        "liquidity_bucket",
    ]
    ordered_columns = [column for column in ordered_columns if column in positions.columns]
    canonical = positions.loc[:, ordered_columns].copy()
    canonical["valuation_date"] = pd.to_datetime(canonical["valuation_date"]).dt.strftime(
        "%Y-%m-%d"
    )
    canonical = canonical.sort_values(
        ["valuation_date", "member_id", "portfolio_id", "security_id"],
        kind="mergesort",
    ).reset_index(drop=True)

    buffer = StringIO()
    canonical.to_csv(
        buffer,
        index=False,
        lineterminator="\n",
        float_format="%.8f",
    )
    return sha256(buffer.getvalue().encode("utf-8")).hexdigest()

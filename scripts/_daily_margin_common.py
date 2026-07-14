"""Shared utilities for the Step 13 daily margin production scripts."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if SRC_ROOT.exists() and str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def project_path(relative_path: str | Path) -> Path:
    """Return an absolute path anchored at the repository root."""
    return REPO_ROOT / Path(relative_path)


def load_project_config(path: str | Path = "configs/project.yaml") -> dict[str, Any]:
    """Load the project YAML configuration and validate its basic structure."""
    config_path = project_path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Project configuration not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}

    if not isinstance(config, dict):
        raise TypeError("configs/project.yaml must contain a YAML mapping.")

    status = str(config.get("project", {}).get("configuration_status", "")).lower()
    if status == "preliminary":
        print(
            "WARNING: project.configuration_status is preliminary. "
            "Margin parameters remain PRELIMINARY PLACEHOLDER calibrations."
        )
    return config


def nested(config: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Read a nested configuration value."""
    current: Any = config
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def resolve_as_of_date(returns: pd.DataFrame, requested: str | None) -> pd.Timestamp:
    """Resolve the calculation date to an available return date."""
    if returns.empty:
        raise ValueError("The returns dataset is empty.")

    dates = pd.DatetimeIndex(pd.to_datetime(returns.index)).sort_values()
    if requested is None:
        return pd.Timestamp(dates.max()).normalize()

    target = pd.Timestamp(requested).normalize()
    eligible = dates[dates <= target]
    if len(eligible) == 0:
        raise ValueError(
            f"No return observation exists on or before requested date {target.date()}."
        )
    resolved = pd.Timestamp(eligible.max()).normalize()
    if resolved != target:
        print(
            f"Requested date {target.date()} is not a return date; "
            f"using {resolved.date()}."
        )
    return resolved


def load_returns(
    path: str | Path = "data/processed/returns_wide.parquet",
) -> pd.DataFrame:
    """Load and validate the wide daily-return matrix."""
    source = project_path(path)
    if not source.exists():
        raise FileNotFoundError(
            f"Return matrix not found: {source}. Run the Step 7 data pipeline first."
        )

    frame = pd.read_parquet(source)
    if "date" in frame.columns:
        frame = frame.set_index("date")

    frame.index = pd.to_datetime(frame.index)
    frame = frame.sort_index()
    frame.columns = [str(column) for column in frame.columns]
    frame = frame.apply(pd.to_numeric, errors="coerce")

    if frame.index.duplicated().any():
        duplicate_dates = frame.index[frame.index.duplicated()].unique().tolist()
        raise ValueError(
            f"Duplicate dates found in return matrix: {duplicate_dates[:5]}"
        )
    if frame.columns.duplicated().any():
        raise ValueError("Duplicate security columns found in return matrix.")
    return frame


def _first_existing(columns: Iterable[str], candidates: Iterable[str]) -> str | None:
    available = {str(column) for column in columns}
    for candidate in candidates:
        if candidate in available:
            return candidate
    return None


def load_positions(
    as_of_date: pd.Timestamp,
    path: str | Path | None = None,
) -> pd.DataFrame:
    """Load the latest eligible member-position snapshot and normalize its schema.

    The production loader prefers the canonical Step 9 Parquet output. The
    synthetic CSV remains a fallback for controlled tests and legacy runs.
    """
    if path is not None:
        candidates = [project_path(path)]
    else:
        candidates = [
            project_path("data/processed/clearing_member_positions.parquet"),
            project_path("data/processed/member_positions.parquet"),
            project_path("data/synthetic/clearing_member_positions.parquet"),
            project_path("data/synthetic/member_positions.parquet"),
            project_path("data/synthetic/member_positions.csv"),
        ]

    source = next((candidate for candidate in candidates if candidate.exists()), None)
    if source is None:
        checked = "\n  - ".join(str(candidate) for candidate in candidates)
        raise FileNotFoundError(
            "Member positions were not found. Checked:\n"
            f"  - {checked}\n"
            "Run scripts/05_generate_member_portfolios.py first."
        )

    suffix = source.suffix.lower()
    if suffix in {".parquet", ".pq"}:
        positions = pd.read_parquet(source)
    elif suffix == ".csv":
        positions = pd.read_csv(source)
    else:
        raise ValueError(f"Unsupported member-position file format: {source.suffix}")

    if positions.empty:
        raise ValueError(f"Member-position source is empty: {source}")

    positions.columns = [str(column).strip() for column in positions.columns]
    print(f"Using member-position source: {source}")

    rename_map: dict[str, str] = {}

    security_column = _first_existing(
        positions.columns,
        ("security_id", "ticker", "symbol", "risk_factor"),
    )
    if security_column is not None and security_column != "security_id":
        rename_map[security_column] = "security_id"

    valuation_date_column = _first_existing(
        positions.columns,
        ("valuation_date", "reference_date", "as_of_date", "date"),
    )
    if valuation_date_column is not None and valuation_date_column != "valuation_date":
        rename_map[valuation_date_column] = "valuation_date"

    price_column = _first_existing(
        positions.columns,
        ("price", "reference_price", "market_price", "close"),
    )
    if price_column is not None and price_column != "price":
        rename_map[price_column] = "price"

    long_short_column = _first_existing(
        positions.columns,
        ("long_short_flag", "direction", "side"),
    )
    if long_short_column is not None and long_short_column != "long_short_flag":
        rename_map[long_short_column] = "long_short_flag"

    if rename_map:
        positions = positions.rename(columns=rename_map)

    if "market_value" not in positions.columns:
        market_value_source = _first_existing(
            positions.columns,
            ("signed_notional", "position_value", "current_value", "notional"),
        )
        if market_value_source is not None:
            positions["market_value"] = positions[market_value_source]
        elif {"quantity", "price"}.issubset(positions.columns):
            quantity = pd.to_numeric(positions["quantity"], errors="raise")
            price = pd.to_numeric(positions["price"], errors="raise")
            positions["market_value"] = quantity * price

            if "long_short_flag" in positions.columns:
                side = positions["long_short_flag"].astype(str).str.strip().str.upper()
                signs = side.map(
                    {
                        "LONG": 1.0,
                        "SHORT": -1.0,
                        "L": 1.0,
                        "S": -1.0,
                        "BUY": 1.0,
                        "SELL": -1.0,
                        "1": 1.0,
                        "-1": -1.0,
                    }
                )
                unknown_sides = sorted(set(side.loc[signs.isna()].dropna().astype(str)))
                if unknown_sides:
                    raise ValueError(
                        "Unrecognized long/short values while calculating "
                        f"market_value: {unknown_sides}"
                    )
                positions["market_value"] = positions["market_value"].abs() * signs

    required_core = {"member_id", "security_id", "market_value"}
    missing_core = required_core.difference(positions.columns)
    if missing_core:
        raise ValueError(
            "Member positions are missing required core fields: "
            f"{sorted(missing_core)}. Source: {source}"
        )

    required_classifications = {
        "sector",
        "asset_class",
        "liquidity_bucket",
    }
    missing_classifications = required_classifications.difference(positions.columns)
    if missing_classifications:
        raise ValueError(
            "Member positions are missing required controlled classifications: "
            f"{sorted(missing_classifications)}. Source: {source}. "
            "Use the canonical Step 9 position output; do not assign "
            "undocumented fallback classifications."
        )

    positions["member_id"] = positions["member_id"].astype(str).str.strip()
    positions["security_id"] = positions["security_id"].astype(str).str.strip()
    positions["market_value"] = pd.to_numeric(
        positions["market_value"],
        errors="raise",
    )

    if positions["member_id"].eq("").any():
        raise ValueError("Blank member_id values are not permitted.")
    if positions["security_id"].eq("").any():
        raise ValueError("Blank security_id values are not permitted.")
    if not np.isfinite(positions["market_value"]).all():
        raise ValueError("market_value contains non-finite values.")

    if "valuation_date" in positions.columns:
        positions["valuation_date"] = pd.to_datetime(
            positions["valuation_date"],
            errors="raise",
        ).dt.normalize()
        positions = positions.loc[positions["valuation_date"] <= as_of_date].copy()
        if positions.empty:
            raise ValueError(
                f"No position snapshot exists on or before {as_of_date.date()}."
            )

        keys = ["member_id"]
        if "portfolio_id" in positions.columns:
            positions["portfolio_id"] = (
                positions["portfolio_id"].astype(str).str.strip()
            )
            keys.append("portfolio_id")

        latest = (
            positions.groupby(keys, as_index=False)["valuation_date"]
            .max()
            .rename(
                columns={
                    "valuation_date": "_latest_valuation_date",
                }
            )
        )
        positions = positions.merge(latest, on=keys, how="inner")
        positions = positions.loc[
            positions["valuation_date"] == positions["_latest_valuation_date"]
        ].drop(columns="_latest_valuation_date")

    positions["liquidity_bucket"] = (
        positions["liquidity_bucket"].astype(str).str.strip().str.lower()
    )
    positions["asset_class"] = (
        positions["asset_class"].astype(str).str.strip().str.lower()
    )
    positions["sector"] = (
        positions["sector"].fillna("unknown").astype(str).str.strip().str.lower()
    )

    for column in ("liquidity_bucket", "asset_class", "sector"):
        invalid = positions[column].isin({"", "nan", "none"})
        if invalid.any():
            raise ValueError(f"Member positions contain blank or null {column} values.")

    duplicate_keys = ["member_id", "security_id"]
    if positions.duplicated(duplicate_keys).any():
        aggregation: dict[str, str] = {
            "market_value": "sum",
            "liquidity_bucket": "first",
            "sector": "first",
            "asset_class": "first",
        }
        optional = [
            column
            for column in (
                "quantity",
                "price",
                "portfolio_id",
                "valuation_date",
                "long_short_flag",
            )
            if column in positions.columns
        ]
        for column in optional:
            aggregation[column] = "first"

        positions = positions.groupby(duplicate_keys, as_index=False).agg(aggregation)

    return positions.reset_index(drop=True)


def member_exposures(positions: pd.DataFrame) -> pd.DataFrame:
    """Calculate gross, net, and portfolio-value measures by clearing member."""
    result = (
        positions.assign(_absolute_market_value=positions["market_value"].abs())
        .groupby("member_id", as_index=False)
        .agg(
            gross_exposure=("_absolute_market_value", "sum"),
            net_exposure=("market_value", "sum"),
        )
    )
    # For the synthetic portfolio framework, portfolio value is represented by
    # total absolute current market value. Net exposure is retained separately.
    result["portfolio_value"] = result["gross_exposure"]
    return result


def require_risk_factors(
    positions: pd.DataFrame,
    returns: pd.DataFrame,
    policy: str = "raise",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Enforce the configured missing-risk-factor policy."""
    needed = sorted(set(positions["security_id"]))
    available = set(returns.columns)
    missing = sorted(set(needed).difference(available))
    normalized_policy = str(policy).strip().lower()

    if missing and normalized_policy == "raise":
        raise KeyError(
            "Missing return histories for position risk factors: " + ", ".join(missing)
        )
    if missing and normalized_policy in {"drop", "exclude"}:
        print(
            "WARNING: excluding positions with missing return histories: "
            + ", ".join(missing)
        )
        positions = positions.loc[~positions["security_id"].isin(missing)].copy()
        needed = sorted(set(positions["security_id"]))
    elif missing:
        raise ValueError(
            f"Unsupported missing_risk_factor_policy={policy!r}; use 'raise' or 'drop'."
        )

    if positions.empty:
        raise ValueError("No positions remain after applying risk-factor controls.")

    return positions, returns.loc[:, needed].copy()


def compound_overlapping_returns(
    daily_returns: pd.DataFrame,
    horizon_days: int,
) -> pd.DataFrame:
    """Construct directly observed overlapping multi-day simple returns."""
    if horizon_days < 1:
        raise ValueError("horizon_days must be at least 1.")
    if horizon_days == 1:
        return daily_returns.copy()
    return (1.0 + daily_returns).rolling(horizon_days).apply(np.prod, raw=True) - 1.0


def quantile_higher(values: np.ndarray, probability: float) -> float:
    """Return a deterministic upper empirical quantile."""
    clean = np.asarray(values, dtype=float)
    clean = clean[np.isfinite(clean)]
    if clean.size == 0:
        raise ValueError("Cannot calculate a quantile from an empty array.")
    try:
        return float(np.quantile(clean, probability, method="higher"))
    except TypeError:  # NumPy before 1.22
        return float(np.quantile(clean, probability, interpolation="higher"))


def ewma_covariance(
    returns: pd.DataFrame,
    decay: float,
    include_mean: bool,
    eigenvalue_floor: float,
) -> np.ndarray:
    """Calculate a deterministic EWMA covariance matrix with PSD correction."""
    if not 0.0 < decay < 1.0:
        raise ValueError("ewma_lambda must be strictly between 0 and 1.")

    matrix = returns.to_numpy(dtype=float)
    if matrix.shape[0] < 2:
        raise ValueError("At least two return observations are required.")

    powers = np.arange(matrix.shape[0] - 1, -1, -1, dtype=float)
    weights = (1.0 - decay) * np.power(decay, powers)
    weights = weights / weights.sum()

    if include_mean:
        mean = np.sum(matrix * weights[:, None], axis=0)
    else:
        mean = np.zeros(matrix.shape[1], dtype=float)

    centered = matrix - mean
    covariance = (centered * weights[:, None]).T @ centered
    covariance = 0.5 * (covariance + covariance.T)

    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    eigenvalues = np.maximum(eigenvalues, float(eigenvalue_floor))
    corrected = (eigenvectors * eigenvalues) @ eigenvectors.T
    return 0.5 * (corrected + corrected.T)


def model_version(config: dict[str, Any]) -> str:
    """Return a traceable model version, preferring configuration then Git."""
    configured = nested(config, "project", "model_version", default=None)
    if configured:
        return str(configured)

    try:
        value = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if value:
            return value
    except (OSError, subprocess.SubprocessError):
        pass

    return "unversioned-development"


def atomic_write_parquet(frame: pd.DataFrame, path: str | Path) -> Path:
    """Write a Parquet file atomically."""
    destination = project_path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    frame.to_parquet(temporary, index=False)
    os.replace(temporary, destination)
    return destination


def upsert_parquet(
    new_rows: pd.DataFrame,
    path: str | Path,
    keys: list[str],
) -> Path:
    """Upsert rows into a Parquet file using deterministic key ordering."""
    destination = project_path(path)
    if destination.exists():
        existing = pd.read_parquet(destination)
        combined = pd.concat([existing, new_rows], ignore_index=True, sort=False)
    else:
        combined = new_rows.copy()

    combined = combined.drop_duplicates(subset=keys, keep="last")
    combined = combined.sort_values(keys).reset_index(drop=True)
    return atomic_write_parquet(combined, path)


def write_json(payload: dict[str, Any], path: str | Path) -> Path:
    """Write a reproducible JSON evidence file."""
    destination = project_path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
    return destination


def utc_timestamp() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

"""Generate empirical Step 15 sensitivity scenario results.

This runner uses the sensitivity manifest as the source of scenario parameters,
applies current clearing-member positions to historical return observations,
calculates primary historical-simulation VaR, challenger EWMA parametric VaR,
margin add-ons, and forward realized loss, and checkpoints each completed
scenario to Parquet.

The permanent configs/project.yaml file is never modified.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys
from typing import Any, Iterable

import numpy as np
import pandas as pd
from scipy.stats import norm
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from _daily_margin_common import atomic_write_parquet, load_project_config, load_returns


PARAMETER_COLUMNS = (
    "confidence_level",
    "lookback_days",
    "mpor_days",
    "ewma_lambda",
    "concentration_threshold",
    "liquidity_threshold_adv",
    "stress_buffer",
    "correlation_shock",
)

REQUIRED_OUTPUT_COLUMNS = (
    "scenario_id",
    "date",
    "member_id",
    "margin",
    "realized_loss",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Step 15 empirical sensitivity results."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPO_ROOT / "data" / "processed" / "sensitivity_scenario_manifest.csv",
    )
    parser.add_argument(
        "--returns",
        type=Path,
        default=REPO_ROOT / "data" / "processed" / "returns_wide.parquet",
    )
    parser.add_argument(
        "--volume",
        type=Path,
        default=REPO_ROOT / "data" / "processed" / "volume_wide.parquet",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "data" / "processed" / "sensitivity_scenario_results.parquet",
    )
    parser.add_argument(
        "--runtime-directory",
        type=Path,
        default=REPO_ROOT / "data" / "interim" / "sensitivity_runtime",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPO_ROOT / "reports" / "evidence" / "sensitivity_execution_summary.json",
    )
    parser.add_argument(
        "--backtest-dates",
        type=int,
        default=250,
        help="Number of final eligible dates. Default: 250.",
    )
    parser.add_argument(
        "--adv-window",
        type=int,
        default=20,
        help="Trailing average daily volume window. Default: 20.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete an existing sensitivity result file before execution.",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Recompute scenarios even when complete checkpoint rows exist.",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        default=None,
        help="Run only a named scenario. May be supplied multiple times.",
    )
    return parser.parse_args()


def _python_scalar(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if pd.isna(value):
        return None
    return value


def _read_wide_parquet(path: Path, label: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"{label} file not found: {path}")
    frame = pd.read_parquet(path)
    if "date" in frame.columns:
        frame = frame.set_index("date")
    frame.index = pd.to_datetime(frame.index, errors="raise").normalize()
    frame = frame.sort_index()
    frame.columns = [str(column).strip() for column in frame.columns]
    frame = frame.apply(pd.to_numeric, errors="coerce")
    if frame.empty:
        raise ValueError(f"{label} data are empty: {path}")
    if frame.index.duplicated().any():
        raise ValueError(f"{label} data contain duplicate dates.")
    if frame.columns.duplicated().any():
        raise ValueError(f"{label} data contain duplicate security columns.")
    return frame


def _values_equal(left: Any, right: Any) -> bool:
    try:
        return bool(
            np.isclose(
                float(left),
                float(right),
                rtol=0.0,
                atol=1e-12,
            )
        )
    except (TypeError, ValueError):
        return str(left).strip() == str(right).strip()


def load_and_validate_manifest(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Sensitivity manifest not found: {path}\n"
            "Run: python scripts\\15_generate_sensitivity_manifest.py"
        )

    manifest = pd.read_csv(path)
    required = {
        "scenario_id",
        "parameter",
        "parameter_value",
        "is_baseline",
        *PARAMETER_COLUMNS,
    }
    missing = sorted(required.difference(manifest.columns))
    if missing:
        raise ValueError(f"Sensitivity manifest is missing columns: {missing}")

    if len(manifest) != 20:
        raise ValueError(
            f"Step 15 requires exactly 20 scenarios; found {len(manifest)}."
        )
    if manifest["scenario_id"].duplicated().any():
        duplicates = manifest.loc[
            manifest["scenario_id"].duplicated(keep=False), "scenario_id"
        ].tolist()
        raise ValueError(f"Duplicate scenario IDs found: {duplicates}")

    manifest["scenario_id"] = manifest["scenario_id"].astype(str).str.strip()
    manifest["parameter"] = manifest["parameter"].astype(str).str.strip()
    manifest["is_baseline"] = (
        manifest["is_baseline"]
        .astype(str)
        .str.strip()
        .str.lower()
        .map({"true": True, "false": False})
    )
    if manifest["is_baseline"].isna().any():
        raise ValueError("is_baseline must contain only True or False.")
    if int(manifest["is_baseline"].sum()) != 1:
        raise ValueError("Manifest must contain exactly one baseline scenario.")

    numeric_columns = (
        "confidence_level",
        "lookback_days",
        "mpor_days",
        "ewma_lambda",
        "concentration_threshold",
        "liquidity_threshold_adv",
        "stress_buffer",
    )
    for column in numeric_columns:
        manifest[column] = pd.to_numeric(manifest[column], errors="raise")

    manifest["lookback_days"] = manifest["lookback_days"].astype(int)
    manifest["mpor_days"] = manifest["mpor_days"].astype(int)
    manifest["correlation_shock"] = (
        manifest["correlation_shock"].astype(str).str.strip().str.lower()
    )

    baseline = manifest.loc[manifest["is_baseline"]].iloc[0]
    allowed_shocks = {"current", "plus_25_percent", "near_one"}
    unknown_shocks = sorted(set(manifest["correlation_shock"]) - allowed_shocks)
    if unknown_shocks:
        raise ValueError(f"Unsupported correlation shocks: {unknown_shocks}")

    for _, row in manifest.loc[~manifest["is_baseline"]].iterrows():
        changed = [
            name
            for name in PARAMETER_COLUMNS
            if not _values_equal(row[name], baseline[name])
        ]
        if changed != [row["parameter"]]:
            raise ValueError(
                f"Scenario {row['scenario_id']!r} must change exactly "
                f"{row['parameter']!r}; detected changes={changed}."
            )

    return manifest.reset_index(drop=True)


def select_test_dates(
    returns_index: pd.DatetimeIndex,
    *,
    maximum_lookback: int,
    maximum_forward_mpor: int,
    count: int,
) -> pd.DatetimeIndex:
    if maximum_lookback < 2:
        raise ValueError("maximum_lookback must be at least 2.")
    if maximum_forward_mpor < 1:
        raise ValueError("maximum_forward_mpor must be at least 1.")
    if count < 1:
        raise ValueError("backtest date count must be positive.")

    dates = pd.DatetimeIndex(pd.to_datetime(returns_index)).sort_values()
    first_eligible_position = maximum_lookback
    last_eligible_exclusive = len(dates) - maximum_forward_mpor

    eligible = dates[first_eligible_position:last_eligible_exclusive]
    if len(eligible) < count:
        minimum_required = maximum_lookback + maximum_forward_mpor + count
        raise ValueError(
            "Insufficient return history for the requested empirical design. "
            f"Available observations={len(dates)}; minimum required="
            f"{minimum_required}; eligible test dates={len(eligible)}; "
            f"requested test dates={count}."
        )
    return eligible[-count:]


def _discover_position_source() -> Path:
    candidates = (
        REPO_ROOT / "data" / "processed" / "clearing_member_positions.parquet",
        REPO_ROOT / "data" / "processed" / "member_positions.parquet",
        REPO_ROOT / "data" / "synthetic" / "clearing_member_positions.parquet",
        REPO_ROOT / "data" / "synthetic" / "member_positions.parquet",
        REPO_ROOT / "data" / "synthetic" / "member_positions.csv",
    )
    source = next((path for path in candidates if path.exists()), None)
    if source is None:
        checked = "\n  - ".join(str(path) for path in candidates)
        raise FileNotFoundError(
            "No clearing-member position dataset was found. Checked:\n  - "
            + checked
        )
    return source


def _first_existing(columns: Iterable[str], candidates: Iterable[str]) -> str | None:
    available = {str(column) for column in columns}
    return next((candidate for candidate in candidates if candidate in available), None)


def load_position_history() -> tuple[pd.DataFrame, Path, str]:
    source = _discover_position_source()
    if source.suffix.lower() in {".parquet", ".pq"}:
        frame = pd.read_parquet(source)
    else:
        frame = pd.read_csv(source)

    if frame.empty:
        raise ValueError(f"Position source is empty: {source}")
    frame.columns = [str(column).strip() for column in frame.columns]

    rename_map: dict[str, str] = {}
    security = _first_existing(
        frame.columns, ("security_id", "ticker", "symbol", "risk_factor")
    )
    if security is None:
        raise ValueError("Positions require a security identifier.")
    if security != "security_id":
        rename_map[security] = "security_id"

    date_column = _first_existing(
        frame.columns, ("valuation_date", "reference_date", "as_of_date", "date")
    )
    if date_column is not None and date_column != "valuation_date":
        rename_map[date_column] = "valuation_date"

    side_column = _first_existing(
        frame.columns, ("long_short_flag", "direction", "side")
    )
    if side_column is not None and side_column != "long_short_flag":
        rename_map[side_column] = "long_short_flag"

    price_column = _first_existing(
        frame.columns, ("price", "reference_price", "market_price", "close")
    )
    if price_column is not None and price_column != "price":
        rename_map[price_column] = "price"

    if rename_map:
        frame = frame.rename(columns=rename_map)

    if "market_value" not in frame.columns:
        market_value_source = _first_existing(
            frame.columns,
            ("signed_notional", "position_value", "current_value", "notional"),
        )
        if market_value_source:
            frame["market_value"] = frame[market_value_source]
        elif {"quantity", "price"}.issubset(frame.columns):
            frame["market_value"] = (
                pd.to_numeric(frame["quantity"], errors="raise")
                * pd.to_numeric(frame["price"], errors="raise")
            )
        else:
            raise ValueError(
                "Positions require market_value, a supported notional field, "
                "or quantity and price."
            )

    required = {
        "member_id",
        "security_id",
        "market_value",
        "sector",
        "asset_class",
        "liquidity_bucket",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Position source is missing columns: {missing}")

    frame["member_id"] = frame["member_id"].astype(str).str.strip()
    frame["security_id"] = frame["security_id"].astype(str).str.strip()
    frame["market_value"] = pd.to_numeric(frame["market_value"], errors="raise")

    if "quantity" in frame.columns:
        frame["quantity"] = pd.to_numeric(frame["quantity"], errors="coerce")
    elif "price" in frame.columns:
        price = pd.to_numeric(frame["price"], errors="coerce")
        frame["quantity"] = np.where(
            price.abs() > 0.0,
            frame["market_value"] / price,
            np.nan,
        )
    else:
        raise ValueError(
            "Liquidity-threshold sensitivity requires quantity, or price so "
            "quantity can be inferred from market_value."
        )

    if frame["quantity"].isna().any() or not np.isfinite(frame["quantity"]).all():
        raise ValueError("Position quantity contains missing or non-finite values.")

    if "long_short_flag" in frame.columns:
        side = frame["long_short_flag"].astype(str).str.strip().str.upper()
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
        if signs.notna().all():
            frame["market_value"] = frame["market_value"].abs() * signs
            frame["quantity"] = frame["quantity"].abs() * signs

    for column in ("sector", "asset_class", "liquidity_bucket"):
        frame[column] = (
            frame[column].fillna("unknown").astype(str).str.strip().str.lower()
        )
        if frame[column].isin({"", "nan", "none"}).any():
            raise ValueError(f"Position source contains invalid {column} values.")

    if "valuation_date" in frame.columns:
        frame["valuation_date"] = pd.to_datetime(
            frame["valuation_date"], errors="raise"
        ).dt.normalize()
        unique_dates = frame["valuation_date"].nunique()
        mode = (
            "static_single_snapshot"
            if unique_dates == 1
            else "dated_position_snapshots"
        )
    else:
        mode = "static_without_valuation_date"

    return frame.reset_index(drop=True), source, mode


def positions_for_date(
    history: pd.DataFrame,
    date: pd.Timestamp,
    mode: str,
) -> pd.DataFrame:
    if mode.startswith("static"):
        selected = history.copy()
    else:
        eligible = history.loc[history["valuation_date"] <= date].copy()
        if eligible.empty:
            raise ValueError(
                f"No position snapshot exists on or before {date.date()}."
            )
        keys = ["member_id"]
        if "portfolio_id" in eligible.columns:
            keys.append("portfolio_id")
        latest = (
            eligible.groupby(keys, as_index=False)["valuation_date"]
            .max()
            .rename(columns={"valuation_date": "_latest"})
        )
        selected = eligible.merge(latest, on=keys, how="inner")
        selected = selected.loc[
            selected["valuation_date"] == selected["_latest"]
        ].drop(columns="_latest")

    aggregation: dict[str, str] = {
        "market_value": "sum",
        "quantity": "sum",
        "sector": "first",
        "asset_class": "first",
        "liquidity_bucket": "first",
    }
    for optional in ("price", "portfolio_id", "valuation_date", "long_short_flag"):
        if optional in selected.columns:
            aggregation[optional] = "first"

    selected = (
        selected.groupby(["member_id", "security_id"], as_index=False)
        .agg(aggregation)
        .sort_values(["member_id", "security_id"])
        .reset_index(drop=True)
    )
    return selected


def _quantile_higher(matrix: np.ndarray, probability: float, axis: int = 0) -> np.ndarray:
    try:
        return np.quantile(matrix, probability, axis=axis, method="higher")
    except TypeError:
        return np.quantile(matrix, probability, axis=axis, interpolation="higher")


def overlapping_compounded_returns(
    daily_returns: np.ndarray,
    horizon: int,
) -> np.ndarray:
    if horizon < 1:
        raise ValueError("MPOR must be at least one day.")
    if horizon == 1:
        return daily_returns.copy()
    if daily_returns.shape[0] < horizon:
        raise ValueError("Insufficient daily observations for the MPOR.")
    gross = 1.0 + daily_returns
    output = np.empty(
        (daily_returns.shape[0] - horizon + 1, daily_returns.shape[1]),
        dtype=float,
    )
    for offset in range(output.shape[0]):
        output[offset] = gross[offset : offset + horizon].prod(axis=0) - 1.0
    return output


def forward_compounded_return(
    returns: pd.DataFrame,
    date_position: int,
    horizon: int,
    securities: list[str],
) -> np.ndarray:
    forward = returns.iloc[
        date_position + 1 : date_position + 1 + horizon
    ][securities].to_numpy(dtype=float)
    if forward.shape[0] != horizon:
        raise ValueError("Incomplete forward return window.")
    if not np.isfinite(forward).all():
        raise ValueError("Forward return window contains missing values.")
    return np.prod(1.0 + forward, axis=0) - 1.0


def ewma_covariance(
    returns: np.ndarray,
    decay: float,
    eigenvalue_floor: float = 1e-14,
) -> np.ndarray:
    if not 0.0 < decay < 1.0:
        raise ValueError("EWMA lambda must be strictly between zero and one.")
    if returns.shape[0] < 2:
        raise ValueError("EWMA covariance requires at least two observations.")
    powers = np.arange(returns.shape[0] - 1, -1, -1, dtype=float)
    weights = (1.0 - decay) * np.power(decay, powers)
    weights = weights / weights.sum()
    centered = returns
    covariance = (centered * weights[:, None]).T @ centered
    covariance = 0.5 * (covariance + covariance.T)
    values, vectors = np.linalg.eigh(covariance)
    values = np.maximum(values, eigenvalue_floor)
    covariance = (vectors * values) @ vectors.T
    return 0.5 * (covariance + covariance.T)


def _nearest_correlation(matrix: np.ndarray, floor: float = 1e-10) -> np.ndarray:
    symmetric = 0.5 * (matrix + matrix.T)
    values, vectors = np.linalg.eigh(symmetric)
    values = np.maximum(values, floor)
    corrected = (vectors * values) @ vectors.T
    scale = np.sqrt(np.clip(np.diag(corrected), floor, None))
    corrected = corrected / np.outer(scale, scale)
    corrected = np.clip(corrected, -0.999999, 0.999999)
    np.fill_diagonal(corrected, 1.0)
    return 0.5 * (corrected + corrected.T)


def apply_correlation_shock(
    covariance: np.ndarray,
    shock: str,
) -> np.ndarray:
    normalized = str(shock).strip().lower()
    covariance = 0.5 * (covariance + covariance.T)
    variances = np.clip(np.diag(covariance), 1e-18, None)
    standard_deviations = np.sqrt(variances)
    correlation = covariance / np.outer(standard_deviations, standard_deviations)
    correlation = np.clip(correlation, -0.999999, 0.999999)
    np.fill_diagonal(correlation, 1.0)

    if normalized == "current":
        shocked = correlation
    elif normalized == "plus_25_percent":
        shocked = correlation.copy()
        off_diagonal = ~np.eye(len(shocked), dtype=bool)
        shocked[off_diagonal] = np.clip(
            shocked[off_diagonal] * 1.25,
            -0.999,
            0.999,
        )
        np.fill_diagonal(shocked, 1.0)
    elif normalized == "near_one":
        shocked = np.full_like(correlation, 0.999, dtype=float)
        np.fill_diagonal(shocked, 1.0)
    else:
        raise ValueError(f"Unsupported correlation shock: {shock!r}")

    shocked = _nearest_correlation(shocked)
    output = shocked * np.outer(standard_deviations, standard_deviations)
    output = 0.5 * (output + output.T)

    minimum_eigenvalue = float(np.linalg.eigvalsh(output).min())
    if minimum_eigenvalue < -1e-8:
        raise ValueError(
            f"Correlation shock produced a non-PSD covariance matrix: "
            f"minimum eigenvalue={minimum_eigenvalue}."
        )
    return output


def build_exposure_matrix(
    positions: pd.DataFrame,
    securities: list[str],
    members: list[str],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    security_index = {security: index for index, security in enumerate(securities)}
    member_index = {member: index for index, member in enumerate(members)}

    exposure = np.zeros((len(securities), len(members)), dtype=float)
    quantity = np.zeros_like(exposure)
    absolute_position = np.zeros_like(exposure)

    for row in positions.itertuples(index=False):
        security = str(row.security_id)
        member = str(row.member_id)
        if security not in security_index:
            raise KeyError(f"Missing return history for security {security!r}.")
        i = security_index[security]
        j = member_index[member]
        value = float(row.market_value)
        exposure[i, j] += value
        quantity[i, j] += float(row.quantity)
        absolute_position[i, j] += abs(value)

    gross = absolute_position.sum(axis=0)
    if (gross <= 0.0).any():
        affected = [members[i] for i in np.where(gross <= 0.0)[0]]
        raise ValueError(f"Members have non-positive gross exposure: {affected}")
    return exposure, quantity, absolute_position, gross


def _config_number(
    config: dict[str, Any],
    candidate_paths: tuple[tuple[str, ...], ...],
    default: float,
) -> float:
    for path in candidate_paths:
        current: Any = config
        for key in path:
            if not isinstance(current, dict) or key not in current:
                current = None
                break
            current = current[key]
        if current is not None:
            try:
                return float(current)
            except (TypeError, ValueError):
                continue
    return float(default)


def write_runtime_config(
    baseline_config: dict[str, Any],
    scenario: pd.Series,
    destination: Path,
    *,
    calculation_assumptions: dict[str, Any],
) -> None:
    runtime = deepcopy(baseline_config)
    runtime["sensitivity_runtime"] = {
        "scenario_id": str(scenario["scenario_id"]),
        "changed_parameter": str(scenario["parameter"]),
        "changed_value": _python_scalar(scenario["parameter_value"]),
        "is_baseline": bool(scenario["is_baseline"]),
        "effective_parameters": {
            name: _python_scalar(scenario[name]) for name in PARAMETER_COLUMNS
        },
        "calculation_assumptions": calculation_assumptions,
        "permanent_project_config_modified": False,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        yaml.safe_dump(runtime, sort_keys=False),
        encoding="utf-8",
    )


def _existing_checkpoint(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_parquet(path)
    missing = sorted(set(REQUIRED_OUTPUT_COLUMNS).difference(frame.columns))
    if missing:
        raise ValueError(
            f"Existing checkpoint is missing required columns: {missing}. "
            "Use --reset after preserving the defective file as evidence."
        )
    frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.normalize()
    frame["member_id"] = frame["member_id"].astype(str)
    frame["scenario_id"] = frame["scenario_id"].astype(str)
    return frame


def _scenario_complete(
    checkpoint: pd.DataFrame,
    scenario_id: str,
    expected_keys: pd.MultiIndex,
) -> bool:
    subset = checkpoint.loc[
        checkpoint["scenario_id"] == scenario_id,
        ["date", "member_id"],
    ].copy()
    if len(subset) != len(expected_keys):
        return False
    if subset.duplicated().any():
        return False
    actual = pd.MultiIndex.from_frame(
        subset.sort_values(["date", "member_id"]).reset_index(drop=True)
    )
    return actual.equals(expected_keys)


def run() -> None:
    args = parse_args()

    if args.reset and args.output.exists():
        args.output.unlink()

    manifest = load_and_validate_manifest(args.manifest)
    if args.scenario:
        requested = set(args.scenario)
        unknown = sorted(requested - set(manifest["scenario_id"]))
        if unknown:
            raise ValueError(f"Unknown requested scenarios: {unknown}")
        manifest_to_run = manifest.loc[
            manifest["scenario_id"].isin(requested)
        ].copy()
    else:
        manifest_to_run = manifest.copy()

    returns = load_returns(
        str(args.returns.relative_to(REPO_ROOT))
        if args.returns.is_relative_to(REPO_ROOT)
        else args.returns
    )
    volume = _read_wide_parquet(args.volume, "Volume")

    common_dates = returns.index.intersection(volume.index)
    returns = returns.loc[common_dates].copy()
    volume = volume.loc[common_dates].copy()

    maximum_lookback = int(manifest["lookback_days"].max())
    maximum_forward = int(manifest["mpor_days"].max())
    test_dates = select_test_dates(
        returns.index,
        maximum_lookback=maximum_lookback,
        maximum_forward_mpor=maximum_forward,
        count=args.backtest_dates,
    )

    project_config = load_project_config()
    position_history, position_source, position_mode = load_position_history()

    position_cache: dict[pd.Timestamp, pd.DataFrame] = {}
    member_set: list[str] | None = None
    all_securities: set[str] = set()

    for date in test_dates:
        selected = positions_for_date(position_history, pd.Timestamp(date), position_mode)
        members = sorted(selected["member_id"].astype(str).unique())
        if member_set is None:
            member_set = members
        elif members != member_set:
            raise ValueError(
                "Member coverage changes across test dates. Step 15 requires "
                "identical member coverage for all observations."
            )
        all_securities.update(selected["security_id"].astype(str))
        position_cache[pd.Timestamp(date)] = selected

    assert member_set is not None
    missing_returns = sorted(all_securities - set(returns.columns))
    missing_volume = sorted(all_securities - set(volume.columns))
    if missing_returns:
        raise KeyError(f"Missing return histories: {missing_returns}")
    if missing_volume:
        raise KeyError(f"Missing volume histories: {missing_volume}")

    securities = sorted(all_securities)
    members = member_set
    expected_keys = pd.MultiIndex.from_product(
        [test_dates, members],
        names=["date", "member_id"],
    )

    concentration_rate = _config_number(
        project_config,
        (
            ("margin_components", "concentration_addon", "rate"),
            ("margin", "concentration_addon", "rate"),
            ("concentration_addon", "rate"),
        ),
        default=0.10,
    )
    liquidity_rate = _config_number(
        project_config,
        (
            ("margin_components", "liquidity_addon", "rate"),
            ("margin", "liquidity_addon", "rate"),
            ("liquidity_addon", "rate"),
        ),
        default=0.05,
    )
    gap_quantile = _config_number(
        project_config,
        (
            ("margin_components", "gap_risk_addon", "quantile"),
            ("margin", "gap_risk_addon", "quantile"),
            ("gap_risk_addon", "quantile"),
        ),
        default=0.999,
    )
    if not 0.0 < gap_quantile < 1.0:
        raise ValueError("gap_quantile must be between zero and one.")

    assumptions = {
        "backtest_dates": int(len(test_dates)),
        "maximum_lookback": maximum_lookback,
        "maximum_forward_mpor": maximum_forward,
        "adv_window": int(args.adv_window),
        "base_margin_rule": "maximum_of_primary_and_challenger",
        "concentration_addon_rate": concentration_rate,
        "liquidity_addon_rate": liquidity_rate,
        "gap_risk_quantile": gap_quantile,
        "position_snapshot_mode": position_mode,
    }

    checkpoint = _existing_checkpoint(args.output)
    if not checkpoint.empty:
        checkpoint = checkpoint.loc[
            checkpoint["scenario_id"].isin(set(manifest["scenario_id"]))
        ].copy()

    date_positions = {pd.Timestamp(date): returns.index.get_loc(date) for date in test_dates}
    model_cache: dict[tuple[Any, ...], dict[str, np.ndarray]] = {}

    for scenario_number, (_, scenario) in enumerate(
        manifest_to_run.iterrows(), start=1
    ):
        scenario_id = str(scenario["scenario_id"])
        runtime_path = args.runtime_directory / f"{scenario_id}.yaml"
        write_runtime_config(
            project_config,
            scenario,
            runtime_path,
            calculation_assumptions=assumptions,
        )

        if (
            not args.no_resume
            and not checkpoint.empty
            and _scenario_complete(checkpoint, scenario_id, expected_keys)
        ):
            print(
                f"[{scenario_number}/{len(manifest_to_run)}] "
                f"Skipping complete checkpoint: {scenario_id}"
            )
            continue

        if not checkpoint.empty:
            checkpoint = checkpoint.loc[
                checkpoint["scenario_id"] != scenario_id
            ].copy()

        confidence = float(scenario["confidence_level"])
        lookback = int(scenario["lookback_days"])
        mpor = int(scenario["mpor_days"])
        decay = float(scenario["ewma_lambda"])
        concentration_threshold = float(scenario["concentration_threshold"])
        liquidity_threshold = float(scenario["liquidity_threshold_adv"])
        stress_fraction = float(scenario["stress_buffer"])
        correlation_shock = str(scenario["correlation_shock"])

        if not 0.0 < confidence < 1.0:
            raise ValueError(f"Invalid confidence level in {scenario_id}.")
        if lookback < 2:
            raise ValueError(f"Invalid lookback in {scenario_id}.")
        if mpor < 1:
            raise ValueError(f"Invalid MPOR in {scenario_id}.")
        if not 0.0 < decay < 1.0:
            raise ValueError(f"Invalid EWMA lambda in {scenario_id}.")
        if concentration_threshold < 0.0:
            raise ValueError(f"Invalid concentration threshold in {scenario_id}.")
        if liquidity_threshold < 0.0:
            raise ValueError(f"Invalid liquidity threshold in {scenario_id}.")
        if stress_fraction < 0.0:
            raise ValueError(f"Invalid stress buffer in {scenario_id}.")

        print(
            f"[{scenario_number}/{len(manifest_to_run)}] "
            f"Running {scenario_id}"
        )
        scenario_rows: list[pd.DataFrame] = []

        for date_number, date in enumerate(test_dates, start=1):
            date = pd.Timestamp(date)
            date_position = date_positions[date]
            selected_positions = position_cache[date]
            exposure, quantity, absolute_position, gross = build_exposure_matrix(
                selected_positions, securities, members
            )

            cache_key = (
                date,
                confidence,
                lookback,
                mpor,
                decay,
                correlation_shock,
                tuple(np.round(exposure.ravel(), 8)),
            )
            cached = model_cache.get(cache_key)
            if cached is None:
                historical = returns.iloc[
                    date_position - lookback : date_position
                ][securities].to_numpy(dtype=float)
                if historical.shape[0] != lookback:
                    raise ValueError(
                        f"Incomplete historical window for {date.date()}."
                    )
                if not np.isfinite(historical).all():
                    raise ValueError(
                        f"Historical return window contains missing values "
                        f"for {date.date()}."
                    )

                multi_day = overlapping_compounded_returns(historical, mpor)
                pnl_distribution = multi_day @ exposure
                loss_distribution = -pnl_distribution
                primary_var = np.maximum(
                    _quantile_higher(loss_distribution, confidence, axis=0),
                    0.0,
                )

                covariance = ewma_covariance(historical, decay)
                shocked_covariance = apply_correlation_shock(
                    covariance, correlation_shock
                )
                variance = np.einsum(
                    "im,ij,jm->m",
                    exposure,
                    shocked_covariance,
                    exposure,
                    optimize=True,
                )
                volatility = np.sqrt(np.maximum(variance, 0.0))
                challenger_var = (
                    float(norm.ppf(confidence))
                    * volatility
                    * math.sqrt(mpor)
                )
                challenger_var = np.maximum(challenger_var, 0.0)
                base_var = np.maximum(primary_var, challenger_var)

                extreme_loss = np.maximum(
                    _quantile_higher(loss_distribution, gap_quantile, axis=0),
                    0.0,
                )
                gap_risk = np.maximum(extreme_loss - base_var, 0.0)

                cached = {
                    "primary_var": primary_var,
                    "challenger_var": challenger_var,
                    "base_var": base_var,
                    "gap_risk": gap_risk,
                }
                model_cache[cache_key] = cached

            largest_weight = absolute_position.max(axis=0) / gross
            concentration_excess = np.maximum(
                largest_weight - concentration_threshold,
                0.0,
            )
            concentration_addon = (
                gross * concentration_excess * concentration_rate
            )

            volume_window = volume.iloc[
                max(0, date_position - args.adv_window + 1) : date_position + 1
            ][securities]
            if len(volume_window) < args.adv_window:
                raise ValueError(
                    f"Insufficient ADV window for {date.date()}."
                )
            adv = volume_window.mean(axis=0).to_numpy(dtype=float)
            if not np.isfinite(adv).all() or (adv <= 0.0).any():
                affected = [
                    securities[i]
                    for i in np.where((~np.isfinite(adv)) | (adv <= 0.0))[0]
                ]
                raise ValueError(
                    f"Invalid ADV values for {date.date()}: {affected}"
                )
            utilization = np.abs(quantity) / adv[:, None]
            liquidity_excess = np.maximum(
                utilization - liquidity_threshold,
                0.0,
            )
            liquidity_addon = (
                absolute_position * liquidity_excess * liquidity_rate
            ).sum(axis=0)

            subtotal = (
                cached["base_var"]
                + liquidity_addon
                + concentration_addon
                + cached["gap_risk"]
            )
            stress_amount = subtotal * stress_fraction
            total_margin = subtotal + stress_amount

            forward_return = forward_compounded_return(
                returns,
                date_position,
                mpor,
                securities,
            )
            forward_pnl = forward_return @ exposure
            realized_loss = np.maximum(-forward_pnl, 0.0)

            frame = pd.DataFrame(
                {
                    "scenario_id": scenario_id,
                    "date": date,
                    "member_id": members,
                    "margin": total_margin,
                    "realized_loss": realized_loss,
                    "parameter": str(scenario["parameter"]),
                    "parameter_value": str(scenario["parameter_value"]),
                    "is_baseline": bool(scenario["is_baseline"]),
                    "confidence_level": confidence,
                    "lookback_days": lookback,
                    "mpor_days": mpor,
                    "ewma_lambda": decay,
                    "concentration_threshold": concentration_threshold,
                    "liquidity_threshold_adv": liquidity_threshold,
                    "stress_buffer": stress_fraction,
                    "correlation_shock": correlation_shock,
                    "primary_var": cached["primary_var"],
                    "challenger_var": cached["challenger_var"],
                    "base_var": cached["base_var"],
                    "liquidity_addon": liquidity_addon,
                    "concentration_addon": concentration_addon,
                    "gap_risk_addon": cached["gap_risk"],
                    "stress_buffer_amount": stress_amount,
                    "gross_exposure": gross,
                    "largest_position_weight": largest_weight,
                }
            )
            scenario_rows.append(frame)

            if date_number % 50 == 0 or date_number == len(test_dates):
                print(
                    f"    dates completed: {date_number}/{len(test_dates)}"
                )

        scenario_result = pd.concat(scenario_rows, ignore_index=True)
        if len(scenario_result) != len(expected_keys):
            raise ValueError(
                f"Scenario {scenario_id} produced {len(scenario_result)} rows; "
                f"expected {len(expected_keys)}."
            )

        checkpoint = pd.concat(
            [checkpoint, scenario_result],
            ignore_index=True,
            sort=False,
        )
        checkpoint = checkpoint.drop_duplicates(
            ["scenario_id", "date", "member_id"],
            keep="last",
        )
        checkpoint = checkpoint.sort_values(
            ["scenario_id", "date", "member_id"]
        ).reset_index(drop=True)
        atomic_write_parquet(
            checkpoint,
            str(args.output.relative_to(REPO_ROOT))
            if args.output.is_relative_to(REPO_ROOT)
            else args.output,
        )
        print(
            f"    checkpoint written: {args.output} "
            f"({len(checkpoint):,} total rows)"
        )

    final = _existing_checkpoint(args.output)
    expected_scenarios = (
        set(manifest_to_run["scenario_id"])
        if args.scenario
        else set(manifest["scenario_id"])
    )
    actual_scenarios = set(final["scenario_id"])
    missing_scenarios = sorted(expected_scenarios - actual_scenarios)
    if missing_scenarios:
        raise ValueError(
            f"Final checkpoint is missing scenarios: {missing_scenarios}"
        )

    final_subset = final.loc[final["scenario_id"].isin(expected_scenarios)].copy()
    if final_subset.duplicated(["scenario_id", "date", "member_id"]).any():
        raise ValueError("Final output contains duplicate scenario/date/member keys.")
    if (final_subset["margin"] < 0.0).any():
        raise ValueError("Final output contains negative margin values.")
    if (final_subset["realized_loss"] < 0.0).any():
        raise ValueError("Final output contains negative realized losses.")

    expected_row_count = len(expected_scenarios) * len(expected_keys)
    if len(final_subset) != expected_row_count:
        raise ValueError(
            f"Final output contains {len(final_subset)} rows; "
            f"expected {expected_row_count}."
        )

    summary = {
        "status": "completed",
        "executed_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "manifest": str(args.manifest),
        "output": str(args.output),
        "position_source": str(position_source),
        "position_snapshot_mode": position_mode,
        "return_observations": int(len(returns)),
        "test_date_count": int(len(test_dates)),
        "test_date_start": str(test_dates.min().date()),
        "test_date_end": str(test_dates.max().date()),
        "member_count": int(len(members)),
        "security_count": int(len(securities)),
        "scenario_count": int(len(expected_scenarios)),
        "row_count": int(len(final_subset)),
        "required_columns": list(REQUIRED_OUTPUT_COLUMNS),
        "calculation_assumptions": assumptions,
        "limitations": [
            (
                "Current/static positions are applied to historical returns."
                if position_mode.startswith("static")
                else "Historical positions use the latest eligible snapshot."
            ),
            "Numerical margin parameters remain preliminary calibrations.",
            "The liquidity add-on uses position quantity divided by trailing ADV.",
            "Total base margin is the maximum of primary and challenger VaR.",
        ],
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print()
    print("STEP 15 EMPIRICAL SENSITIVITY RESULTS COMPLETED")
    print(f"Scenarios: {len(expected_scenarios)}")
    print(f"Dates per scenario: {len(test_dates)}")
    print(f"Members per date: {len(members)}")
    print(f"Rows: {len(final_subset):,}")
    print(f"Output: {args.output}")
    print(f"Summary: {args.summary}")


if __name__ == "__main__":
    run()

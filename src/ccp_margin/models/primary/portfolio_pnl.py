"""Current-position historical scenario P&L calculations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

MissingHistoryPolicy = Literal["drop_scenario", "zero", "error"]

_LONG_FLAGS = {"LONG", "L", "+", "+1", "1", "BUY"}
_SHORT_FLAGS = {"SHORT", "S", "-", "-1", "SELL"}


@dataclass(frozen=True)
class PortfolioPnLResult:
    """Full portfolio and component P&L simulation output."""

    portfolio_pnl: pd.Series
    component_pnl: pd.DataFrame
    positions: pd.DataFrame
    missing_history_report: pd.DataFrame
    diagnostics: dict[str, int | float | str]


def prepare_current_positions(positions: pd.DataFrame) -> pd.DataFrame:
    """Validate and aggregate current positions to security-level exposure.

    The returned ``current_market_value`` is signed: long exposure is positive
    and short exposure is negative. ``long_short_flag`` takes precedence over
    the sign of quantity or market value when it is available.
    """
    if not isinstance(positions, pd.DataFrame):
        raise TypeError("positions must be a pandas DataFrame")
    if positions.empty:
        raise ValueError("positions is empty")
    if "security_id" not in positions.columns:
        raise ValueError("positions must contain security_id")

    frame = positions.copy()
    frame["security_id"] = frame["security_id"].astype(str)
    if frame["security_id"].str.strip().eq("").any():
        raise ValueError("security_id cannot be blank")

    for identifier_column in ("valuation_date", "member_id", "portfolio_id"):
        if identifier_column in frame.columns:
            unique_count = frame[identifier_column].dropna().nunique()
            if unique_count > 1:
                raise ValueError(
                    f"positions must represent one current portfolio; "
                    f"found multiple {identifier_column} values"
                )

    quantity = _numeric_column(frame, "quantity")
    price = _numeric_column(frame, "price")
    market_value = _numeric_column(frame, "market_value")

    derived_value: pd.Series | None = None
    if quantity is not None and price is not None:
        derived_value = quantity * price

    if market_value is None:
        if derived_value is None:
            raise ValueError(
                "positions must contain market_value or both quantity and price"
            )
        signed_source_value = derived_value
    elif market_value.isna().any():
        if derived_value is None:
            raise ValueError(
                "missing market_value rows require both quantity and price"
            )
        signed_source_value = market_value.fillna(derived_value)
    else:
        signed_source_value = market_value

    unsigned_value = signed_source_value.abs()
    if unsigned_value.isna().any():
        raise ValueError("position market values cannot be missing")
    if np.isinf(unsigned_value.to_numpy()).any():
        raise ValueError("position market values cannot be infinite")

    direction = pd.Series(np.nan, index=frame.index, dtype=float)
    if "long_short_flag" in frame.columns:
        normalized_flag = (
            frame["long_short_flag"].astype(str).str.strip().str.upper()
        )
        direction.loc[normalized_flag.isin(_LONG_FLAGS)] = 1.0
        direction.loc[normalized_flag.isin(_SHORT_FLAGS)] = -1.0
        unknown = normalized_flag.notna() & ~normalized_flag.isin(
            _LONG_FLAGS | _SHORT_FLAGS | {"", "NAN", "NONE"}
        )
        if unknown.any():
            bad_flags = sorted(normalized_flag.loc[unknown].unique().tolist())
            raise ValueError(f"unrecognized long_short_flag values: {bad_flags}")

    if quantity is not None:
        quantity_direction = np.sign(quantity).replace(0.0, np.nan)
        direction = direction.fillna(quantity_direction)
    value_direction = np.sign(signed_source_value).replace(0.0, np.nan)
    direction = direction.fillna(value_direction)

    direction = direction.fillna(1.0)
    frame["current_market_value"] = unsigned_value * direction

    metadata_columns = [
        column
        for column in (
            "valuation_date",
            "member_id",
            "portfolio_id",
            "sector",
            "asset_class",
            "liquidity_bucket",
        )
        if column in frame.columns
    ]

    aggregation: dict[str, object] = {"current_market_value": "sum"}
    for column in metadata_columns:
        aggregation[column] = _single_or_multiple

    prepared = (
        frame.groupby("security_id", sort=True, as_index=False)
        .agg(aggregation)
        .sort_values("security_id")
        .reset_index(drop=True)
    )

    if prepared["current_market_value"].eq(0.0).all():
        raise ValueError("all net security exposures are zero")
    return prepared


def simulate_portfolio_pnl(
    positions: pd.DataFrame,
    scenario_returns: pd.DataFrame,
    *,
    missing_history_policy: MissingHistoryPolicy = "drop_scenario",
) -> PortfolioPnLResult:
    """Apply historical returns to current signed market values.

    Policies
    --------
    drop_scenario:
        Remove each scenario date having a missing return for any active
        security. This is the default and avoids silently understating risk.
    zero:
        Replace missing returns with zero and retain all scenarios. Every
        imputation is disclosed in ``missing_history_report``.
    error:
        Raise an exception if any required history is missing.
    """
    if missing_history_policy not in {"drop_scenario", "zero", "error"}:
        raise ValueError(
            "missing_history_policy must be 'drop_scenario', 'zero', or 'error'"
        )

    prepared = prepare_current_positions(positions)
    returns = _coerce_scenario_returns(scenario_returns)
    securities = prepared["security_id"].tolist()
    aligned = returns.reindex(columns=securities)

    missing_count = aligned.isna().sum()
    available_count = aligned.notna().sum()
    missing_entirely = available_count.eq(0)

    report = prepared.loc[:, ["security_id", "current_market_value"]].copy()
    report["available_observations"] = report["security_id"].map(available_count)
    report["missing_observations"] = report["security_id"].map(missing_count)
    report["missing_entire_history"] = report["security_id"].map(missing_entirely)
    report["history_coverage_ratio"] = (
        report["available_observations"] / max(len(aligned), 1)
    )
    report["treatment"] = "none"

    missing_mask = aligned.isna()
    missing_cells = int(missing_mask.to_numpy().sum())
    initial_scenarios = len(aligned)

    if missing_cells:
        if missing_history_policy == "error":
            missing_names = report.loc[
                report["missing_observations"].gt(0), "security_id"
            ].tolist()
            raise ValueError(
                "required risk-factor history is missing for securities: "
                f"{missing_names}"
            )
        if missing_history_policy == "drop_scenario":
            rows_to_drop = missing_mask.any(axis=1)
            aligned = aligned.loc[~rows_to_drop].copy()
            report.loc[report["missing_observations"].gt(0), "treatment"] = (
                "affected scenarios dropped"
            )
        else:
            aligned = aligned.fillna(0.0)
            report.loc[report["missing_observations"].gt(0), "treatment"] = (
                "missing returns set to zero"
            )

    if aligned.empty:
        raise ValueError(
            "no complete historical scenarios remain after applying the "
            f"missing-history policy '{missing_history_policy}'"
        )

    exposures = prepared.set_index("security_id")["current_market_value"]
    component_pnl = aligned.mul(exposures, axis="columns")
    component_pnl = component_pnl.reindex(columns=securities)
    portfolio_pnl = component_pnl.sum(axis=1)
    portfolio_pnl.name = "portfolio_pnl"

    diagnostics: dict[str, int | float | str] = {
        "missing_history_policy": missing_history_policy,
        "initial_scenario_count": int(initial_scenarios),
        "retained_scenario_count": int(len(aligned)),
        "dropped_scenario_count": int(initial_scenarios - len(aligned)),
        "missing_return_cells": missing_cells,
        "security_count": int(len(securities)),
        "gross_market_value": float(exposures.abs().sum()),
        "net_market_value": float(exposures.sum()),
    }

    return PortfolioPnLResult(
        portfolio_pnl=portfolio_pnl,
        component_pnl=component_pnl,
        positions=prepared,
        missing_history_report=report,
        diagnostics=diagnostics,
    )


def _coerce_scenario_returns(scenario_returns: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(scenario_returns, pd.DataFrame):
        raise TypeError("scenario_returns must be a pandas DataFrame")
    if scenario_returns.empty:
        raise ValueError("scenario_returns is empty")

    frame = scenario_returns.copy()
    frame.index = pd.to_datetime(frame.index, errors="raise")
    if frame.index.has_duplicates:
        raise ValueError("scenario_returns contains duplicate scenario dates")
    frame.columns = frame.columns.map(str)
    if frame.columns.has_duplicates:
        raise ValueError("scenario_returns contains duplicate security columns")
    frame = frame.sort_index().reindex(sorted(frame.columns), axis=1)
    frame = frame.apply(pd.to_numeric, errors="coerce").astype(float)
    if np.isinf(frame.to_numpy(dtype=float, na_value=np.nan)).any():
        raise ValueError("scenario_returns contains infinity")
    frame.index.name = "scenario_date"
    return frame


def _numeric_column(frame: pd.DataFrame, column: str) -> pd.Series | None:
    if column not in frame.columns:
        return None
    values = pd.to_numeric(frame[column], errors="coerce")
    if frame[column].notna().any() and values.isna().any():
        raise ValueError(f"{column} contains non-numeric values")
    if values.isna().all():
        return None
    return values.astype(float)


def _single_or_multiple(values: pd.Series) -> object:
    non_null = values.dropna()
    unique = non_null.astype(str).unique().tolist()
    if not unique:
        return np.nan
    if len(unique) == 1:
        return non_null.iloc[0]
    return "MULTIPLE"

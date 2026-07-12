"""EWMA and multi-day covariance estimators for the challenger margin model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

MissingDataPolicy = Literal["drop_rows", "fill_zero"]


@dataclass(frozen=True)
class CovarianceEstimate:
    """Container for a covariance estimate and its supporting diagnostics."""

    covariance: pd.DataFrame
    mean_returns: pd.Series
    volatilities: pd.Series
    correlation: pd.DataFrame
    observations_used: int
    method: str
    horizon_days: int
    decay_factor: float | None = None


def _validate_returns(returns: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(returns, pd.DataFrame):
        raise TypeError("returns must be a pandas DataFrame.")
    if returns.empty:
        raise ValueError("returns must contain at least one observation.")
    if returns.columns.duplicated().any():
        duplicates = returns.columns[returns.columns.duplicated()].tolist()
        raise ValueError(f"returns contains duplicate columns: {duplicates}")

    cleaned = returns.copy()
    cleaned.columns = cleaned.columns.map(str)
    cleaned = cleaned.apply(pd.to_numeric, errors="coerce")
    cleaned = cleaned.replace([np.inf, -np.inf], np.nan)
    return cleaned.sort_index()


def _apply_missing_policy(
    returns: pd.DataFrame,
    missing_policy: MissingDataPolicy,
) -> pd.DataFrame:
    if missing_policy == "drop_rows":
        cleaned = returns.dropna(axis=0, how="any")
    elif missing_policy == "fill_zero":
        cleaned = returns.fillna(0.0)
    else:
        raise ValueError(
            "missing_policy must be either 'drop_rows' or 'fill_zero'."
        )

    if cleaned.empty:
        raise ValueError("No usable return observations remain after missing-data treatment.")
    return cleaned


def compound_multi_day_returns(
    returns: pd.DataFrame,
    horizon_days: int,
    *,
    overlapping: bool = True,
) -> pd.DataFrame:
    """Create directly observed compounded multi-day returns.

    Overlapping observations maximize the sample available for margin estimation.
    They are serially dependent and therefore should not be treated as independent
    observations in formal independence testing.
    """

    cleaned = _validate_returns(returns)
    if horizon_days < 1:
        raise ValueError("horizon_days must be at least 1.")
    if horizon_days == 1:
        return cleaned.copy()
    if len(cleaned) < horizon_days:
        raise ValueError(
            f"At least {horizon_days} daily observations are required for a "
            f"{horizon_days}-day return."
        )

    multi_day = (1.0 + cleaned).rolling(horizon_days).apply(np.prod, raw=True) - 1.0
    multi_day = multi_day.dropna(axis=0, how="all")

    if not overlapping:
        multi_day = multi_day.iloc[::horizon_days]

    return multi_day


def sample_covariance(
    returns: pd.DataFrame,
    *,
    horizon_days: int = 1,
    missing_policy: MissingDataPolicy = "drop_rows",
) -> CovarianceEstimate:
    """Estimate an equally weighted sample covariance matrix."""

    cleaned = _apply_missing_policy(_validate_returns(returns), missing_policy)
    if len(cleaned) < 2:
        raise ValueError("At least two usable observations are required.")

    mean_returns = cleaned.mean(axis=0)
    covariance = cleaned.cov(ddof=1)
    volatilities = pd.Series(
        np.sqrt(np.clip(np.diag(covariance.to_numpy(dtype=float)), 0.0, None)),
        index=covariance.index,
        name="volatility",
    )
    correlation = cleaned.corr()

    return CovarianceEstimate(
        covariance=covariance,
        mean_returns=mean_returns,
        volatilities=volatilities,
        correlation=correlation,
        observations_used=len(cleaned),
        method="sample",
        horizon_days=horizon_days,
    )


def ewma_covariance(
    returns: pd.DataFrame,
    *,
    decay_factor: float = 0.94,
    demean: bool = False,
    horizon_days: int = 1,
    missing_policy: MissingDataPolicy = "drop_rows",
) -> CovarianceEstimate:
    """Estimate a deterministic RiskMetrics-style EWMA covariance matrix.

    The newest observation receives the largest weight. By default, returns are
    treated as zero-mean, which is conventional for short-horizon market-risk VaR.
    Set ``demean=True`` to subtract the weighted mean before covariance estimation.
    """

    if not 0.0 < decay_factor < 1.0:
        raise ValueError("decay_factor must be strictly between 0 and 1.")

    cleaned = _apply_missing_policy(_validate_returns(returns), missing_policy)
    if len(cleaned) < 2:
        raise ValueError("At least two usable observations are required.")

    values = cleaned.to_numpy(dtype=float)
    n_observations = len(cleaned)
    raw_weights = decay_factor ** np.arange(n_observations - 1, -1, -1)
    weights = raw_weights / raw_weights.sum()

    weighted_mean_values = np.average(values, axis=0, weights=weights)
    weighted_mean = pd.Series(
        weighted_mean_values,
        index=cleaned.columns,
        name="weighted_mean_return",
    )

    centered = values - weighted_mean_values if demean else values
    covariance_values = (centered * weights[:, None]).T @ centered
    covariance_values = 0.5 * (covariance_values + covariance_values.T)

    covariance = pd.DataFrame(
        covariance_values,
        index=cleaned.columns,
        columns=cleaned.columns,
    )
    volatilities = pd.Series(
        np.sqrt(np.clip(np.diag(covariance_values), 0.0, None)),
        index=cleaned.columns,
        name="volatility",
    )

    denominator = np.outer(volatilities.to_numpy(), volatilities.to_numpy())
    correlation_values = np.divide(
        covariance_values,
        denominator,
        out=np.zeros_like(covariance_values),
        where=denominator > 0.0,
    )
    np.fill_diagonal(correlation_values, 1.0)
    correlation = pd.DataFrame(
        correlation_values,
        index=cleaned.columns,
        columns=cleaned.columns,
    )

    return CovarianceEstimate(
        covariance=covariance,
        mean_returns=weighted_mean,
        volatilities=volatilities,
        correlation=correlation,
        observations_used=n_observations,
        method="ewma",
        horizon_days=horizon_days,
        decay_factor=decay_factor,
    )

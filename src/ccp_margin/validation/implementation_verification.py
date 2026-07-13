"""Independent implementation verification and reconciliation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

import numpy as np
import pandas as pd

from ._utils import as_1d_float, validate_probability


@dataclass(frozen=True)
class ReconciliationResult:
    """Numerical reconciliation between production and independent outputs."""

    name: str
    number_of_values: int
    maximum_absolute_difference: float
    mean_absolute_difference: float
    maximum_relative_difference: float
    absolute_tolerance: float
    relative_tolerance: float
    mismatch_count: int
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VerificationSuiteResult:
    """Collection of reconciliation checks."""

    checks: dict[str, ReconciliationResult]
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "checks": {
                name: check.to_dict() for name, check in self.checks.items()
            },
            "passed": self.passed,
        }


def independently_calculate_returns(
    prices: pd.DataFrame,
    *,
    method: str = "simple",
) -> pd.DataFrame:
    """Recalculate asset returns from prices using a separate validation path."""
    if not isinstance(prices, pd.DataFrame):
        raise TypeError("prices must be a pandas DataFrame.")
    if prices.empty:
        raise ValueError("prices must not be empty.")
    numeric = prices.apply(pd.to_numeric, errors="raise")
    if not np.all(np.isfinite(numeric.to_numpy(dtype=float))):
        raise ValueError("prices must contain only finite values.")
    if (numeric <= 0).any().any():
        raise ValueError("prices must be strictly positive.")

    normalized_method = method.strip().lower()
    if normalized_method == "simple":
        result = numeric.divide(numeric.shift(1)).subtract(1.0)
    elif normalized_method == "log":
        result = np.log(numeric).diff()
    else:
        raise ValueError("method must be 'simple' or 'log'.")
    return result


def independently_calculate_portfolio_pnl(
    returns: pd.DataFrame,
    current_market_values: Mapping[str, float] | pd.Series,
) -> pd.Series:
    """Apply historical risk-factor returns to current market values."""
    if not isinstance(returns, pd.DataFrame):
        raise TypeError("returns must be a pandas DataFrame.")
    if returns.empty:
        raise ValueError("returns must not be empty.")

    market_values = pd.Series(current_market_values, dtype=float)
    missing = returns.columns.difference(market_values.index)
    if len(missing):
        raise KeyError(f"Missing market values for: {missing.tolist()}")

    aligned_values = market_values.reindex(returns.columns)
    if not np.all(np.isfinite(aligned_values.to_numpy(dtype=float))):
        raise ValueError("current_market_values must contain only finite values.")

    numeric_returns = returns.apply(pd.to_numeric, errors="raise")
    if not np.all(np.isfinite(numeric_returns.to_numpy(dtype=float))):
        raise ValueError("returns must contain only finite values.")

    return numeric_returns.mul(aligned_values, axis="columns").sum(axis=1)


def independently_calculate_var(
    portfolio_pnl: np.ndarray | pd.Series | list[float],
    *,
    confidence_level: float = 0.99,
    quantile_method: str = "linear",
) -> float:
    """Calculate positive VaR as the selected quantile of the loss distribution."""
    pnl = as_1d_float(portfolio_pnl, name="portfolio_pnl")
    confidence = validate_probability(confidence_level, name="confidence_level")
    losses = -pnl
    quantile_loss = float(
        np.quantile(losses, confidence, method=quantile_method)
    )
    return max(0.0, quantile_loss)


def independently_calculate_total_margin(
    base_var: np.ndarray | list[float] | float,
    *,
    liquidity_addon: np.ndarray | list[float] | float = 0.0,
    concentration_addon: np.ndarray | list[float] | float = 0.0,
    gap_risk_addon: np.ndarray | list[float] | float = 0.0,
    stress_buffer: np.ndarray | list[float] | float = 0.0,
) -> np.ndarray:
    """Recalculate total margin by direct component summation."""
    components = np.broadcast_arrays(
        np.asarray(base_var, dtype=float),
        np.asarray(liquidity_addon, dtype=float),
        np.asarray(concentration_addon, dtype=float),
        np.asarray(gap_risk_addon, dtype=float),
        np.asarray(stress_buffer, dtype=float),
    )
    for component in components:
        if not np.all(np.isfinite(component)):
            raise ValueError("All margin components must be finite.")
        if np.any(component < 0):
            raise ValueError("All margin components must be non-negative.")
    return np.sum(np.stack(components, axis=0), axis=0)


def independently_calculate_exception_flags(
    actual_loss: np.ndarray | list[float],
    available_margin: np.ndarray | list[float],
) -> np.ndarray:
    """Flag an exception where positive actual loss exceeds available margin."""
    loss = as_1d_float(actual_loss, name="actual_loss")
    margin = as_1d_float(available_margin, name="available_margin")
    if loss.shape != margin.shape:
        raise ValueError("actual_loss and available_margin must have equal length.")
    if np.any(loss < 0) or np.any(margin < 0):
        raise ValueError("Loss and margin values must be non-negative.")
    return loss > margin


def reconcile_arrays(
    production: np.ndarray | pd.Series | list[float],
    independent: np.ndarray | pd.Series | list[float],
    *,
    name: str,
    absolute_tolerance: float = 1e-8,
    relative_tolerance: float = 1e-6,
) -> ReconciliationResult:
    """Reconcile two numeric outputs using explicit absolute and relative tolerances."""
    left = np.asarray(production, dtype=float)
    right = np.asarray(independent, dtype=float)
    if left.shape != right.shape:
        raise ValueError(
            f"{name}: production and independent outputs must have equal shape."
        )
    if left.size == 0:
        raise ValueError(f"{name}: outputs must not be empty.")
    if not np.all(np.isfinite(left)) or not np.all(np.isfinite(right)):
        raise ValueError(f"{name}: outputs must contain only finite values.")
    if absolute_tolerance < 0 or relative_tolerance < 0:
        raise ValueError("Tolerances must be non-negative.")

    absolute_difference = np.abs(left - right)
    scale = np.maximum(np.abs(left), np.abs(right))
    relative_difference = np.divide(
        absolute_difference,
        scale,
        out=np.zeros_like(absolute_difference, dtype=float),
        where=scale != 0.0,
    )
    matches = np.isclose(
        left,
        right,
        atol=absolute_tolerance,
        rtol=relative_tolerance,
        equal_nan=False,
    )

    return ReconciliationResult(
        name=name,
        number_of_values=int(left.size),
        maximum_absolute_difference=float(np.max(absolute_difference)),
        mean_absolute_difference=float(np.mean(absolute_difference)),
        maximum_relative_difference=float(np.max(relative_difference)),
        absolute_tolerance=float(absolute_tolerance),
        relative_tolerance=float(relative_tolerance),
        mismatch_count=int(np.size(matches) - np.count_nonzero(matches)),
        passed=bool(np.all(matches)),
    )


def verify_implementation(
    production_outputs: Mapping[str, Any],
    independent_outputs: Mapping[str, Any],
    *,
    absolute_tolerance: float = 1e-8,
    relative_tolerance: float = 1e-6,
) -> VerificationSuiteResult:
    """Reconcile matching production and independently calculated outputs.

    The caller should supply named outputs such as ``returns``, ``portfolio_pnl``,
    ``var``, ``liquidity_addon``, ``concentration_addon``, ``gap_risk_addon``,
    ``stress_buffer``, ``total_margin``, and ``exception_flags``.
    """
    production_keys = set(production_outputs)
    independent_keys = set(independent_outputs)
    if production_keys != independent_keys:
        missing_independent = sorted(production_keys - independent_keys)
        missing_production = sorted(independent_keys - production_keys)
        raise KeyError(
            "Output keys do not match. "
            f"Missing independent={missing_independent}; "
            f"missing production={missing_production}."
        )

    checks: dict[str, ReconciliationResult] = {}
    for name in sorted(production_keys):
        checks[name] = reconcile_arrays(
            production_outputs[name],
            independent_outputs[name],
            name=name,
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        )

    return VerificationSuiteResult(
        checks=checks,
        passed=all(check.passed for check in checks.values()),
    )

"""Margin procyclicality diagnostics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from ._utils import as_1d_float


@dataclass(frozen=True)
class ProcyclicalityResult:
    """Summary of margin variability and stress responsiveness."""

    number_of_observations: int
    mean_margin: float
    margin_coefficient_of_variation: float
    maximum_one_period_increase: float
    maximum_one_period_decrease: float
    maximum_rolling_increase: float
    maximum_rolling_decrease: float
    peak_to_trough_decline: float
    maximum_drawdown: float
    correlation_with_volatility: float | None
    stressed_to_calm_mean_margin_ratio: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def assess_procyclicality(
    margin_series: np.ndarray | pd.Series | list[float],
    *,
    volatility_series: np.ndarray | pd.Series | list[float] | None = None,
    stressed_period_flags: np.ndarray | pd.Series | list[bool] | None = None,
    rolling_window: int = 20,
) -> ProcyclicalityResult:
    """Assess margin variability, jumps, drawdowns, and stress-state behavior.

    This function supplies diagnostics rather than a universal pass/fail rule.
    Thresholds should be established through the model's approved risk appetite
    and governance process.
    """
    margin = as_1d_float(margin_series, name="margin_series")
    if np.any(margin < 0):
        raise ValueError("margin_series must be non-negative.")
    if rolling_window < 1:
        raise ValueError("rolling_window must be at least 1.")

    mean_margin = float(np.mean(margin))
    coefficient_of_variation = (
        float(np.std(margin, ddof=1) / mean_margin)
        if margin.size > 1 and mean_margin != 0.0
        else 0.0
    )

    previous = margin[:-1]
    changes = np.divide(
        margin[1:] - previous,
        previous,
        out=np.full_like(previous, np.nan, dtype=float),
        where=previous != 0.0,
    )
    max_one_increase = (
        float(np.nanmax(changes))
        if changes.size and np.any(np.isfinite(changes))
        else 0.0
    )
    max_one_decrease = (
        float(np.nanmin(changes))
        if changes.size and np.any(np.isfinite(changes))
        else 0.0
    )

    rolling_change = np.full(margin.shape, np.nan, dtype=float)
    if margin.size > rolling_window:
        base = margin[:-rolling_window]
        rolling_change[rolling_window:] = np.divide(
            margin[rolling_window:] - base,
            base,
            out=np.full_like(base, np.nan, dtype=float),
            where=base != 0.0,
        )
    finite_rolling = rolling_change[np.isfinite(rolling_change)]
    max_rolling_increase = (
        float(np.max(finite_rolling)) if finite_rolling.size else 0.0
    )
    max_rolling_decrease = (
        float(np.min(finite_rolling)) if finite_rolling.size else 0.0
    )

    running_peak = np.maximum.accumulate(margin)
    drawdown = np.divide(
        margin - running_peak,
        running_peak,
        out=np.zeros_like(margin, dtype=float),
        where=running_peak != 0.0,
    )
    maximum_drawdown = float(np.min(drawdown))
    peak_to_trough_decline = abs(maximum_drawdown)

    volatility_correlation = None
    if volatility_series is not None:
        volatility = as_1d_float(volatility_series, name="volatility_series")
        if volatility.shape != margin.shape:
            raise ValueError(
                "volatility_series must have the same length as margin_series."
            )
        volatility_correlation = (
            float(np.corrcoef(margin, volatility)[0, 1])
            if margin.size > 1
            and np.std(margin) > 0
            and np.std(volatility) > 0
            else float("nan")
        )

    stress_ratio = None
    if stressed_period_flags is not None:
        flags = np.asarray(stressed_period_flags)
        if flags.ndim != 1 or flags.shape != margin.shape:
            raise ValueError(
                "stressed_period_flags must be one-dimensional and match margin_series."
            )
        flags = flags.astype(bool)
        if np.any(flags) and np.any(~flags):
            calm_mean = float(np.mean(margin[~flags]))
            stress_mean = float(np.mean(margin[flags]))
            stress_ratio = (
                stress_mean / calm_mean if calm_mean != 0.0 else float("nan")
            )
        else:
            stress_ratio = float("nan")

    return ProcyclicalityResult(
        number_of_observations=int(margin.size),
        mean_margin=mean_margin,
        margin_coefficient_of_variation=coefficient_of_variation,
        maximum_one_period_increase=max_one_increase,
        maximum_one_period_decrease=max_one_decrease,
        maximum_rolling_increase=max_rolling_increase,
        maximum_rolling_decrease=max_rolling_decrease,
        peak_to_trough_decline=peak_to_trough_decline,
        maximum_drawdown=maximum_drawdown,
        correlation_with_volatility=volatility_correlation,
        stressed_to_calm_mean_margin_ratio=stress_ratio,
    )

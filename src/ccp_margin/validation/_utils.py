"""Internal utilities used only by the independent validation package."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
from scipy.special import xlogy


def as_1d_float(values: Iterable[float], *, name: str) -> np.ndarray:
    """Convert input to a finite one-dimensional float array."""
    array = np.asarray(values, dtype=float)
    if array.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional.")
    if array.size == 0:
        raise ValueError(f"{name} must not be empty.")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must contain only finite values.")
    return array


def as_binary_flags(
    values: Iterable[int | bool], *, name: str = "exceptions"
) -> np.ndarray:
    """Convert input to a one-dimensional integer array containing only 0 and 1."""
    array = np.asarray(values)
    if array.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional.")
    if array.size == 0:
        raise ValueError(f"{name} must not be empty.")

    if array.dtype == bool:
        return array.astype(np.int8)

    numeric = np.asarray(array, dtype=float)
    if not np.all(np.isfinite(numeric)):
        raise ValueError(f"{name} must contain only finite values.")
    if not np.all(np.isin(numeric, [0.0, 1.0])):
        raise ValueError(f"{name} must contain only 0/1 or False/True values.")
    return numeric.astype(np.int8)


def validate_probability(value: float, *, name: str) -> float:
    """Require a probability strictly between zero and one."""
    result = float(value)
    if not 0.0 < result < 1.0:
        raise ValueError(f"{name} must be strictly between 0 and 1.")
    return result


def bernoulli_log_likelihood(successes: int, trials: int, probability: float) -> float:
    """Return a numerically stable Bernoulli log-likelihood.

    ``scipy.special.xlogy`` correctly handles boundary terms such as
    ``0 * log(0)``.
    """
    if trials < 0 or successes < 0 or successes > trials:
        raise ValueError("Invalid Bernoulli counts.")
    p = float(probability)
    if not 0.0 <= p <= 1.0:
        raise ValueError("probability must be between 0 and 1 inclusive.")
    failures = trials - successes
    return float(xlogy(successes, p) + xlogy(failures, 1.0 - p))


def safe_divide(numerator: float, denominator: float) -> float:
    """Return NaN where a rate is undefined because its denominator is zero."""
    if denominator == 0:
        return float("nan")
    return float(numerator / denominator)

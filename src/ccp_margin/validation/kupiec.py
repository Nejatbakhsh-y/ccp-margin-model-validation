"""Kupiec unconditional-coverage test."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
from scipy.stats import chi2

from ._utils import (
    as_binary_flags,
    bernoulli_log_likelihood,
    validate_probability,
)


@dataclass(frozen=True)
class KupiecResult:
    """Structured result of the Kupiec unconditional-coverage test."""

    number_of_observations: int
    number_of_exceptions: int
    target_exception_probability: float
    target_coverage: float
    observed_exception_rate: float
    observed_coverage: float
    likelihood_ratio_statistic: float
    p_value: float
    significance_level: float
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def kupiec_unconditional_coverage(
    exceptions: np.ndarray | list[int] | list[bool],
    *,
    target_exception_probability: float = 0.01,
    significance_level: float = 0.05,
) -> KupiecResult:
    """Test whether the exception frequency is consistent with the target rate.

    Parameters
    ----------
    exceptions:
        One-dimensional sequence in which 1/True denotes a VaR or margin
        exception and 0/False denotes no exception.
    target_exception_probability:
        Expected exception probability. For 99% VaR, use 0.01.
    significance_level:
        Test size used for pass/fail classification.

    Notes
    -----
    The asymptotic reference distribution is chi-square with one degree of
    freedom. ``passed`` is True when the null hypothesis is not rejected.
    """
    flags = as_binary_flags(exceptions)
    p0 = validate_probability(
        target_exception_probability,
        name="target_exception_probability",
    )
    alpha = validate_probability(significance_level, name="significance_level")

    observations = int(flags.size)
    exception_count = int(flags.sum())
    observed_rate = exception_count / observations

    null_log_likelihood = bernoulli_log_likelihood(
        exception_count,
        observations,
        p0,
    )
    unrestricted_log_likelihood = bernoulli_log_likelihood(
        exception_count,
        observations,
        observed_rate,
    )

    statistic = max(
        0.0,
        -2.0 * (null_log_likelihood - unrestricted_log_likelihood),
    )
    p_value = float(chi2.sf(statistic, df=1))

    return KupiecResult(
        number_of_observations=observations,
        number_of_exceptions=exception_count,
        target_exception_probability=p0,
        target_coverage=1.0 - p0,
        observed_exception_rate=float(observed_rate),
        observed_coverage=float(1.0 - observed_rate),
        likelihood_ratio_statistic=float(statistic),
        p_value=p_value,
        significance_level=alpha,
        passed=bool(p_value >= alpha),
    )

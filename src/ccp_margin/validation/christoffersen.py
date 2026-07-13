"""Christoffersen independence and conditional-coverage tests."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
from scipy.stats import chi2

from ._utils import as_binary_flags, bernoulli_log_likelihood, safe_divide, validate_probability
from .kupiec import KupiecResult, kupiec_unconditional_coverage


@dataclass(frozen=True)
class ChristoffersenIndependenceResult:
    """Structured result of the Christoffersen independence test."""

    number_of_observations: int
    number_of_transitions: int
    n00: int
    n01: int
    n10: int
    n11: int
    transition_probability_after_no_exception: float
    transition_probability_after_exception: float
    unconditional_transition_probability: float
    likelihood_ratio_statistic: float
    p_value: float
    significance_level: float
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ChristoffersenConditionalCoverageResult:
    """Combined unconditional-coverage and independence result."""

    kupiec_result: KupiecResult
    independence_result: ChristoffersenIndependenceResult
    conditional_coverage_statistic: float
    p_value: float
    significance_level: float
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        return result


def _transition_counts(flags: np.ndarray) -> tuple[int, int, int, int]:
    previous = flags[:-1]
    current = flags[1:]
    n00 = int(np.sum((previous == 0) & (current == 0)))
    n01 = int(np.sum((previous == 0) & (current == 1)))
    n10 = int(np.sum((previous == 1) & (current == 0)))
    n11 = int(np.sum((previous == 1) & (current == 1)))
    return n00, n01, n10, n11


def christoffersen_independence(
    exceptions: np.ndarray | list[int] | list[bool],
    *,
    significance_level: float = 0.05,
) -> ChristoffersenIndependenceResult:
    """Test whether exceptions are serially independent.

    At least two observations are required. Where no exception-state
    transitions are observed, the corresponding conditional transition rate is
    undefined and reported as NaN. The likelihood calculation remains valid
    because the absent state's contribution is zero.
    """
    flags = as_binary_flags(exceptions)
    alpha = validate_probability(significance_level, name="significance_level")
    if flags.size < 2:
        raise ValueError("At least two exception observations are required.")

    n00, n01, n10, n11 = _transition_counts(flags)
    transitions = int(flags.size - 1)

    from_zero = n00 + n01
    from_one = n10 + n11
    pi0 = safe_divide(n01, from_zero)
    pi1 = safe_divide(n11, from_one)
    pooled = (n01 + n11) / transitions

    null_log_likelihood = bernoulli_log_likelihood(
        n01 + n11,
        transitions,
        pooled,
    )

    alternative_log_likelihood = 0.0
    if from_zero > 0:
        alternative_log_likelihood += bernoulli_log_likelihood(
            n01,
            from_zero,
            n01 / from_zero,
        )
    if from_one > 0:
        alternative_log_likelihood += bernoulli_log_likelihood(
            n11,
            from_one,
            n11 / from_one,
        )

    statistic = max(
        0.0,
        -2.0 * (null_log_likelihood - alternative_log_likelihood),
    )
    p_value = float(chi2.sf(statistic, df=1))

    return ChristoffersenIndependenceResult(
        number_of_observations=int(flags.size),
        number_of_transitions=transitions,
        n00=n00,
        n01=n01,
        n10=n10,
        n11=n11,
        transition_probability_after_no_exception=float(pi0),
        transition_probability_after_exception=float(pi1),
        unconditional_transition_probability=float(pooled),
        likelihood_ratio_statistic=float(statistic),
        p_value=p_value,
        significance_level=alpha,
        passed=bool(p_value >= alpha),
    )


def christoffersen_conditional_coverage(
    exceptions: np.ndarray | list[int] | list[bool],
    *,
    target_exception_probability: float = 0.01,
    significance_level: float = 0.05,
) -> ChristoffersenConditionalCoverageResult:
    """Combine Kupiec coverage and Christoffersen independence statistics.

    The conditional-coverage statistic is the sum of the two one-degree-of-
    freedom likelihood-ratio statistics and is compared with a chi-square
    distribution with two degrees of freedom.
    """
    alpha = validate_probability(significance_level, name="significance_level")
    coverage = kupiec_unconditional_coverage(
        exceptions,
        target_exception_probability=target_exception_probability,
        significance_level=alpha,
    )
    independence = christoffersen_independence(
        exceptions,
        significance_level=alpha,
    )

    statistic = (
        coverage.likelihood_ratio_statistic
        + independence.likelihood_ratio_statistic
    )
    p_value = float(chi2.sf(statistic, df=2))

    return ChristoffersenConditionalCoverageResult(
        kupiec_result=coverage,
        independence_result=independence,
        conditional_coverage_statistic=float(statistic),
        p_value=p_value,
        significance_level=alpha,
        passed=bool(p_value >= alpha),
    )

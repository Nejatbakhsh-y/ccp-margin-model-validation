"""Primary-versus-benchmark margin comparison."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
from scipy.stats import spearmanr

from ._utils import as_1d_float


@dataclass(frozen=True)
class BenchmarkComparisonResult:
    """Summary statistics comparing primary and benchmark margin estimates."""

    number_of_observations: int
    mean_primary_margin: float
    mean_benchmark_margin: float
    mean_difference: float
    median_difference: float
    mean_absolute_difference: float
    root_mean_squared_difference: float
    mean_ratio_primary_to_benchmark: float
    percentage_primary_below_benchmark: float
    pearson_correlation: float
    spearman_correlation: float
    primary_exception_rate: float | None
    benchmark_exception_rate: float | None
    primary_only_exception_count: int | None
    benchmark_only_exception_count: int | None
    both_exception_count: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compare_with_benchmark(
    primary_margin: np.ndarray | list[float],
    benchmark_margin: np.ndarray | list[float],
    *,
    actual_loss: np.ndarray | list[float] | None = None,
) -> BenchmarkComparisonResult:
    """Compare primary and challenger/benchmark margin series observation by observation."""
    primary = as_1d_float(primary_margin, name="primary_margin")
    benchmark = as_1d_float(benchmark_margin, name="benchmark_margin")
    if primary.shape != benchmark.shape:
        raise ValueError("primary_margin and benchmark_margin must have equal length.")
    if np.any(primary < 0) or np.any(benchmark < 0):
        raise ValueError("Margin values must be non-negative.")

    difference = primary - benchmark
    nonzero_benchmark = benchmark != 0.0
    ratio = np.divide(
        primary,
        benchmark,
        out=np.full_like(primary, np.nan, dtype=float),
        where=nonzero_benchmark,
    )

    if primary.size > 1 and np.std(primary) > 0 and np.std(benchmark) > 0:
        pearson = float(np.corrcoef(primary, benchmark)[0, 1])
        spearman = float(spearmanr(primary, benchmark).statistic)
    else:
        pearson = float("nan")
        spearman = float("nan")

    primary_rate = None
    benchmark_rate = None
    primary_only = None
    benchmark_only = None
    both = None

    if actual_loss is not None:
        loss = as_1d_float(actual_loss, name="actual_loss")
        if loss.shape != primary.shape:
            raise ValueError("actual_loss must have the same length as margin inputs.")
        if np.any(loss < 0):
            raise ValueError("actual_loss must use positive loss magnitudes.")

        primary_exceptions = loss > primary
        benchmark_exceptions = loss > benchmark
        primary_rate = float(np.mean(primary_exceptions))
        benchmark_rate = float(np.mean(benchmark_exceptions))
        primary_only = int(np.sum(primary_exceptions & ~benchmark_exceptions))
        benchmark_only = int(np.sum(~primary_exceptions & benchmark_exceptions))
        both = int(np.sum(primary_exceptions & benchmark_exceptions))

    return BenchmarkComparisonResult(
        number_of_observations=int(primary.size),
        mean_primary_margin=float(np.mean(primary)),
        mean_benchmark_margin=float(np.mean(benchmark)),
        mean_difference=float(np.mean(difference)),
        median_difference=float(np.median(difference)),
        mean_absolute_difference=float(np.mean(np.abs(difference))),
        root_mean_squared_difference=float(np.sqrt(np.mean(difference**2))),
        mean_ratio_primary_to_benchmark=float(np.nanmean(ratio))
        if np.any(nonzero_benchmark)
        else float("nan"),
        percentage_primary_below_benchmark=float(100.0 * np.mean(primary < benchmark)),
        pearson_correlation=pearson,
        spearman_correlation=spearman,
        primary_exception_rate=primary_rate,
        benchmark_exception_rate=benchmark_rate,
        primary_only_exception_count=primary_only,
        benchmark_only_exception_count=benchmark_only,
        both_exception_count=both,
    )

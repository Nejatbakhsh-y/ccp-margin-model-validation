import numpy as np

from ccp_margin.validation.benchmark_comparison import compare_with_benchmark


def test_benchmark_comparison_with_losses():
    primary = np.array([100.0, 120.0, 140.0])
    benchmark = np.array([90.0, 125.0, 150.0])
    losses = np.array([95.0, 130.0, 130.0])

    result = compare_with_benchmark(
        primary,
        benchmark,
        actual_loss=losses,
    )

    assert result.number_of_observations == 3
    assert result.primary_exception_rate == 1 / 3
    assert result.benchmark_exception_rate == 2 / 3
    assert result.benchmark_only_exception_count == 1

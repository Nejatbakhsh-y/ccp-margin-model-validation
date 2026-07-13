"""Run a deterministic smoke test for Step 14 validation modules."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ccp_margin.validation import (
    analyze_sensitivity,
    assess_procyclicality,
    basel_traffic_light,
    calculate_margin_shortfall,
    christoffersen_conditional_coverage,
    christoffersen_independence,
    compare_with_benchmark,
    kupiec_unconditional_coverage,
)


def main() -> None:
    exceptions = np.zeros(250, dtype=int)
    exceptions[[30, 170]] = 1

    observations = pd.DataFrame(
        {
            "actual_loss": [90.0, 150.0, 140.0, 75.0],
            "available_margin": [100.0, 100.0, 110.0, 75.0],
            "member_id": ["M1", "M1", "M2", "M2"],
            "portfolio_type": ["equity", "equity", "rates", "rates"],
            "is_stressed_period": [False, True, True, False],
        }
    )

    primary_margin = np.array([100.0, 120.0, 140.0, 160.0])
    benchmark_margin = np.array([95.0, 125.0, 150.0, 155.0])
    actual_loss = observations["actual_loss"].to_numpy()

    results = {
        "kupiec": kupiec_unconditional_coverage(exceptions).to_dict(),
        "christoffersen_independence": christoffersen_independence(
            exceptions
        ).to_dict(),
        "christoffersen_conditional_coverage": (
            christoffersen_conditional_coverage(exceptions).to_dict()
        ),
        "traffic_light": basel_traffic_light(
            exceptions,
            require_250_observations=True,
        ).to_dict(),
        "margin_shortfall": calculate_margin_shortfall(
            observations
        ).to_dict(),
        "benchmark_comparison": compare_with_benchmark(
            primary_margin,
            benchmark_margin,
            actual_loss=actual_loss,
        ).to_dict(),
        "sensitivity": analyze_sensitivity(
            primary_margin,
            {
                "lookback_shorter": primary_margin * 0.95,
                "lookback_longer": primary_margin * 1.08,
            },
            parameter_changes={
                "lookback_shorter": -0.20,
                "lookback_longer": 0.20,
            },
        ).to_dict(),
        "procyclicality": assess_procyclicality(
            primary_margin,
            volatility_series=[0.15, 0.18, 0.22, 0.25],
            stressed_period_flags=[False, False, True, True],
            rolling_window=2,
        ).to_dict(),
    }

    print(json.dumps(results, indent=2, default=str))
    print("STEP 14 VALIDATION SMOKE TEST PASSED")


if __name__ == "__main__":
    main()

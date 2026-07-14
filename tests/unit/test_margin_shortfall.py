from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ccp_margin.validation.margin_shortfall import (
    _aggregate,
    calculate_margin_shortfall,
)


def test_margin_shortfall_and_exception_flags_use_strict_loss_excess():
    observations = pd.DataFrame(
        {
            "actual_loss": [80.0, 100.0, 125.0],
            "available_margin": [100.0, 100.0, 100.0],
            "member_id": ["CM001", "CM001", "CM002"],
            "portfolio_type": ["diversified", "diversified", "concentrated"],
            "is_stressed_period": [False, False, True],
        }
    )

    result = calculate_margin_shortfall(observations)

    assert result.number_of_observations == 3
    assert result.number_of_exceptions == 1
    assert result.total_shortfall == 25.0
    assert result.mean_shortfall == 25.0
    assert result.maximum_shortfall == 25.0

    records = result.exception_records
    assert records["exception_flag"].tolist() == [True]
    assert records["shortfall"].tolist() == [25.0]
    assert records["actual_loss"].tolist() == [125.0]

    serialized = result.to_dict()
    assert serialized["number_of_observations"] == 3
    assert serialized["number_of_exceptions"] == 1
    assert serialized["exception_records"][0]["shortfall"] == 25.0


def test_margin_shortfall_validation_and_empty_aggregation_branches():
    with pytest.raises(TypeError, match="pandas DataFrame"):
        calculate_margin_shortfall([{"actual_loss": 1.0, "available_margin": 1.0}])

    with pytest.raises(KeyError, match="Missing required columns"):
        calculate_margin_shortfall(pd.DataFrame({"actual_loss": [1.0]}))

    with pytest.raises(ValueError, match="finite"):
        calculate_margin_shortfall(
            pd.DataFrame(
                {
                    "actual_loss": [np.nan],
                    "available_margin": [1.0],
                }
            )
        )

    with pytest.raises(ValueError, match="positive loss magnitudes"):
        calculate_margin_shortfall(
            pd.DataFrame(
                {
                    "actual_loss": [-1.0],
                    "available_margin": [1.0],
                }
            )
        )

    with pytest.raises(ValueError, match="non-negative"):
        calculate_margin_shortfall(
            pd.DataFrame(
                {
                    "actual_loss": [1.0],
                    "available_margin": [-1.0],
                }
            )
        )

    missing_group = _aggregate(
        pd.DataFrame({"shortfall": [2.0]}),
        "member_id",
    )
    assert missing_group.empty
    assert "member_id" in missing_group.columns

    empty_group = _aggregate(
        pd.DataFrame(
            {
                "member_id": pd.Series(dtype="object"),
                "shortfall": pd.Series(dtype="float64"),
            }
        ),
        "member_id",
    )
    assert empty_group.empty
    assert list(empty_group.columns) == [
        "member_id",
        "exception_count",
        "total_shortfall",
        "mean_shortfall",
        "maximum_shortfall",
    ]

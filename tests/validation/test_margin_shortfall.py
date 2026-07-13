import pandas as pd

from ccp_margin.validation.margin_shortfall import calculate_margin_shortfall


def test_margin_shortfall_aggregations():
    observations = pd.DataFrame(
        {
            "actual_loss": [90.0, 150.0, 140.0, 75.0],
            "available_margin": [100.0, 100.0, 110.0, 75.0],
            "member_id": ["M1", "M1", "M2", "M2"],
            "portfolio_type": ["equity", "equity", "rates", "rates"],
            "is_stressed_period": [False, True, True, False],
        }
    )

    result = calculate_margin_shortfall(observations)

    assert result.number_of_exceptions == 2
    assert result.total_shortfall == 80.0
    assert result.mean_shortfall == 40.0
    assert result.maximum_shortfall == 50.0
    assert set(result.shortfall_by_member["member_id"]) == {"M1", "M2"}

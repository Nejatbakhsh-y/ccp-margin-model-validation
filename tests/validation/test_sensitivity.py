from ccp_margin.validation.sensitivity import analyze_sensitivity


def test_sensitivity_identifies_largest_mean_change():
    result = analyze_sensitivity(
        [100.0, 100.0],
        {
            "low": [90.0, 90.0],
            "high": [120.0, 120.0],
        },
        parameter_changes={"low": -0.1, "high": 0.1},
    )

    assert result.most_sensitive_scenario == "high"
    assert result.scenario_results["high"]["mean_percentage_change"] == 0.2

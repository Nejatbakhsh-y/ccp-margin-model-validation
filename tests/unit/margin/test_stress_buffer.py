from __future__ import annotations

import pandas as pd
import pytest

from ccp_margin.margin.stress_buffer import calculate_stress_buffer


def test_stress_buffer_is_residual_coverage_bridge() -> None:
    stress = pd.DataFrame(
        {
            "member_id": ["M1", "M1", "M2"],
            "scenario_id": ["S1", "S2", "S1"],
            "stress_loss": [100.0, 150.0, 80.0],
        }
    )
    pre = pd.DataFrame({"member_id": ["M1", "M2"], "pre_stress_margin": [120.0, 100.0]})
    result = calculate_stress_buffer(
        stress,
        pre,
        required_coverage_ratio=1.0,
        parameter_source="Approved scenario library",
    ).member_buffer.set_index("member_id")
    assert result.loc["M1", "stress_buffer"] == pytest.approx(30.0)
    assert result.loc["M2", "stress_buffer"] == pytest.approx(0.0)
    assert result.loc["M1", "binding_scenario_id"] == "S2"


def test_stress_buffer_increases_with_coverage_ratio() -> None:
    stress = pd.DataFrame(
        {"member_id": ["M1"], "scenario_id": ["S1"], "stress_loss": [100.0]}
    )
    pre = pd.DataFrame({"member_id": ["M1"], "pre_stress_margin": [50.0]})
    low = calculate_stress_buffer(
        stress,
        pre,
        required_coverage_ratio=0.8,
        parameter_source="Approved scenario library",
    ).member_buffer.loc[0, "stress_buffer"]
    high = calculate_stress_buffer(
        stress,
        pre,
        required_coverage_ratio=1.0,
        parameter_source="Approved scenario library",
    ).member_buffer.loc[0, "stress_buffer"]
    assert high > low

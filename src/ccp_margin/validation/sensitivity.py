"""Parameter and output sensitivity analysis."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

import numpy as np

from ._utils import as_1d_float


@dataclass(frozen=True)
class SensitivityResult:
    """Sensitivity of model output to one or more parameter scenarios."""

    base_mean: float
    base_minimum: float
    base_maximum: float
    scenario_results: dict[str, dict[str, float]]
    maximum_absolute_percentage_change: float
    most_sensitive_scenario: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def analyze_sensitivity(
    base_output: np.ndarray | list[float],
    scenario_outputs: Mapping[str, np.ndarray | list[float]],
    *,
    parameter_changes: Mapping[str, float] | None = None,
) -> SensitivityResult:
    """Compare scenario outputs with a base output.

    ``parameter_changes`` may contain signed decimal parameter changes, such as
    ``0.10`` for a 10% increase. Where supplied and non-zero, the function also
    reports elasticity as percentage output change divided by percentage
    parameter change.
    """
    base = as_1d_float(base_output, name="base_output")
    if not scenario_outputs:
        raise ValueError("scenario_outputs must contain at least one scenario.")

    results: dict[str, dict[str, float]] = {}
    most_sensitive = None
    maximum_change = -1.0

    for scenario_name, values in scenario_outputs.items():
        scenario = as_1d_float(values, name=f"scenario_outputs[{scenario_name!r}]")
        if scenario.shape != base.shape:
            raise ValueError(
                f"Scenario {scenario_name!r} must have the same length as base_output."
            )

        difference = scenario - base
        denominator = np.where(np.abs(base) > 0.0, np.abs(base), np.nan)
        percentage_change = np.divide(
            difference,
            denominator,
            out=np.full_like(difference, np.nan, dtype=float),
            where=~np.isnan(denominator),
        )

        mean_base = float(np.mean(base))
        mean_scenario = float(np.mean(scenario))
        mean_pct = (
            float((mean_scenario - mean_base) / abs(mean_base))
            if mean_base != 0.0
            else float("nan")
        )

        row = {
            "mean_output": mean_scenario,
            "mean_absolute_change": float(np.mean(np.abs(difference))),
            "maximum_absolute_change": float(np.max(np.abs(difference))),
            "mean_percentage_change": mean_pct,
            "median_observation_percentage_change": float(
                np.nanmedian(percentage_change)
            )
            if np.any(np.isfinite(percentage_change))
            else float("nan"),
        }

        if parameter_changes is not None and scenario_name in parameter_changes:
            parameter_change = float(parameter_changes[scenario_name])
            row["parameter_change"] = parameter_change
            row["elasticity"] = (
                mean_pct / parameter_change
                if parameter_change != 0.0 and np.isfinite(mean_pct)
                else float("nan")
            )

        results[scenario_name] = row
        abs_change = abs(mean_pct) if np.isfinite(mean_pct) else -1.0
        if abs_change > maximum_change:
            maximum_change = abs_change
            most_sensitive = scenario_name

    return SensitivityResult(
        base_mean=float(np.mean(base)),
        base_minimum=float(np.min(base)),
        base_maximum=float(np.max(base)),
        scenario_results=results,
        maximum_absolute_percentage_change=float(maximum_change)
        if maximum_change >= 0
        else float("nan"),
        most_sensitive_scenario=most_sensitive,
    )

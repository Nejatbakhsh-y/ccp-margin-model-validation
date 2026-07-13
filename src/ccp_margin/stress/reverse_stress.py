"""Reverse stress testing for available-margin exhaustion."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

import numpy as np
import pandas as pd


LossFunction = Callable[[float], float]


def solve_exhaustion_shock(
    loss_function: LossFunction,
    available_margin: float,
    *,
    initial_upper: float = 0.01,
    maximum_shock: float = 5.0,
    tolerance: float = 1e-8,
    maximum_iterations: int = 200,
) -> dict[str, Any]:
    """Find the minimum nonnegative shock whose loss exhausts available margin.

    The loss function must be nondecreasing over the searched interval. The
    solver expands the upper bracket and then performs deterministic bisection.
    """
    margin = float(available_margin)
    if not np.isfinite(margin) or margin < 0.0:
        raise ValueError("available_margin must be finite and nonnegative.")
    if initial_upper <= 0.0 or maximum_shock <= 0.0:
        raise ValueError("Shock bounds must be positive.")
    if tolerance <= 0.0 or maximum_iterations < 1:
        raise ValueError("Invalid reverse-stress solver controls.")
    if margin == 0.0:
        return {
            "shock_required": 0.0,
            "loss_at_shock": 0.0,
            "exhaustion_found": True,
            "iterations": 0,
        }

    lower = 0.0
    upper = min(float(initial_upper), float(maximum_shock))
    loss_upper = float(loss_function(upper))
    expansion_iterations = 0
    while loss_upper < margin and upper < maximum_shock:
        lower = upper
        upper = min(upper * 2.0, maximum_shock)
        loss_upper = float(loss_function(upper))
        expansion_iterations += 1
        if expansion_iterations > maximum_iterations:
            break

    if not np.isfinite(loss_upper):
        raise ValueError("loss_function returned a non-finite value.")
    if loss_upper < margin:
        return {
            "shock_required": np.nan,
            "loss_at_shock": loss_upper,
            "exhaustion_found": False,
            "iterations": expansion_iterations,
        }

    iterations = expansion_iterations
    while upper - lower > tolerance and iterations < maximum_iterations:
        midpoint = 0.5 * (lower + upper)
        loss_midpoint = float(loss_function(midpoint))
        if not np.isfinite(loss_midpoint):
            raise ValueError("loss_function returned a non-finite value.")
        if loss_midpoint >= margin:
            upper = midpoint
        else:
            lower = midpoint
        iterations += 1

    final_loss = float(loss_function(upper))
    return {
        "shock_required": upper,
        "loss_at_shock": final_loss,
        "exhaustion_found": final_loss >= margin,
        "iterations": iterations,
    }


def _validate_inputs(
    positions: pd.DataFrame,
    margin: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    required_positions = {"member_id", "security_id", "market_value"}
    missing_positions = required_positions.difference(positions.columns)
    if missing_positions:
        raise ValueError(
            f"Positions are missing required fields: {sorted(missing_positions)}"
        )
    required_margin = {"member_id", "total_margin"}
    missing_margin = required_margin.difference(margin.columns)
    if missing_margin:
        raise ValueError(
            f"Margin data are missing required fields: {sorted(missing_margin)}"
        )

    p = positions.copy()
    p["member_id"] = p["member_id"].astype(str).str.strip()
    p["security_id"] = p["security_id"].astype(str).str.strip()
    p["market_value"] = pd.to_numeric(p["market_value"], errors="raise")
    m = margin.copy()
    m["member_id"] = m["member_id"].astype(str).str.strip()
    m["total_margin"] = pd.to_numeric(m["total_margin"], errors="raise")
    if m["member_id"].duplicated().any():
        raise ValueError("Margin data contain duplicate member_id rows.")
    missing_members = sorted(set(p["member_id"]).difference(m["member_id"]))
    if missing_members:
        raise KeyError(f"Margin data are missing members: {missing_members}")
    return p, m


def run_reverse_stress_tests(
    positions: pd.DataFrame,
    margin: pd.DataFrame,
    *,
    equity_securities: Iterable[str],
    maximum_shock_pct: float = 5.0,
    tolerance: float = 1e-8,
    maximum_iterations: int = 200,
) -> pd.DataFrame:
    """Calculate member-level shocks required to exhaust available margin.

    Three interpretable directions are tested:
    1. every position moves adversely by the same percentage;
    2. the single largest position gaps adversely;
    3. all configured equity positions move adversely together.
    """
    p, m = _validate_inputs(positions, margin)
    equity_set = {str(value) for value in equity_securities}
    rows: list[dict[str, Any]] = []

    for member_id, group in p.groupby("member_id", sort=True):
        available_margin = float(
            m.loc[m["member_id"] == member_id, "total_margin"].iloc[0]
        )
        absolute_values = group["market_value"].abs()
        gross_exposure = float(absolute_values.sum())
        largest_position = float(absolute_values.max())
        equity_gross = float(
            group.loc[group["security_id"].isin(equity_set), "market_value"].abs().sum()
        )

        methods = [
            (
                "REVERSE_UNIFORM_ADVERSE",
                "Uniform adverse move across all positions",
                gross_exposure,
                "Every position moves against its current direction by the same percentage.",
            ),
            (
                "REVERSE_LARGEST_POSITION_GAP",
                "Adverse gap in the largest position",
                largest_position,
                "Only the member's largest absolute position gaps adversely.",
            ),
            (
                "REVERSE_EQUITY_ADVERSE",
                "Uniform adverse move across equity positions",
                equity_gross,
                "All configured equity positions move against their current direction together.",
            ),
        ]

        for method_id, method_name, exposure_basis, description in methods:
            if exposure_basis <= 0.0:
                solution = {
                    "shock_required": np.nan,
                    "loss_at_shock": 0.0,
                    "exhaustion_found": False,
                    "iterations": 0,
                }
            else:
                solution = solve_exhaustion_shock(
                    lambda shock, basis=exposure_basis: basis * shock,
                    available_margin,
                    maximum_shock=float(maximum_shock_pct),
                    tolerance=float(tolerance),
                    maximum_iterations=int(maximum_iterations),
                )
            rows.append(
                {
                    "member_id": member_id,
                    "reverse_stress_id": method_id,
                    "reverse_stress_name": method_name,
                    "available_margin": available_margin,
                    "exposure_basis": exposure_basis,
                    "shock_required": solution["shock_required"],
                    "shock_required_pct": (
                        float(solution["shock_required"]) * 100.0
                        if np.isfinite(solution["shock_required"])
                        else np.nan
                    ),
                    "loss_at_shock": solution["loss_at_shock"],
                    "exhaustion_found": bool(solution["exhaustion_found"]),
                    "iterations": int(solution["iterations"]),
                    "method_description": description,
                }
            )

    return pd.DataFrame(rows)

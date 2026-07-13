"""Historical stress-scenario construction and portfolio revaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


_REQUIRED_POSITION_COLUMNS = {"member_id", "security_id", "market_value"}


@dataclass(frozen=True)
class HistoricalScenario:
    """Definition of an empirical historical stress window."""

    scenario_id: str
    name: str
    start_date: pd.Timestamp
    end_date: pd.Timestamp
    description: str = ""

    @classmethod
    def from_mapping(cls, payload: dict[str, object]) -> "HistoricalScenario":
        required = {"scenario_id", "name", "start_date", "end_date"}
        missing = required.difference(payload)
        if missing:
            raise ValueError(
                "Historical scenario is missing required fields: "
                f"{sorted(missing)}"
            )
        scenario = cls(
            scenario_id=str(payload["scenario_id"]).strip(),
            name=str(payload["name"]).strip(),
            start_date=pd.Timestamp(payload["start_date"]).normalize(),
            end_date=pd.Timestamp(payload["end_date"]).normalize(),
            description=str(payload.get("description", "")).strip(),
        )
        scenario.validate()
        return scenario

    def validate(self) -> None:
        if not self.scenario_id:
            raise ValueError("Historical scenario_id cannot be blank.")
        if not self.name:
            raise ValueError("Historical scenario name cannot be blank.")
        if self.end_date < self.start_date:
            raise ValueError(
                f"Historical scenario {self.scenario_id} has end_date before start_date."
            )


def _validate_positions(positions: pd.DataFrame) -> pd.DataFrame:
    missing = _REQUIRED_POSITION_COLUMNS.difference(positions.columns)
    if missing:
        raise ValueError(
            f"Positions are missing required fields: {sorted(missing)}"
        )
    frame = positions.copy()
    frame["member_id"] = frame["member_id"].astype(str).str.strip()
    frame["security_id"] = frame["security_id"].astype(str).str.strip()
    frame["market_value"] = pd.to_numeric(frame["market_value"], errors="raise")
    if frame.empty:
        raise ValueError("Positions cannot be empty.")
    if frame[["member_id", "security_id"]].eq("").any().any():
        raise ValueError("member_id and security_id cannot be blank.")
    if not np.isfinite(frame["market_value"]).all():
        raise ValueError("market_value contains non-finite values.")
    return frame


def _validate_returns(returns: pd.DataFrame) -> pd.DataFrame:
    if returns.empty:
        raise ValueError("Returns cannot be empty.")
    frame = returns.copy()
    if "date" in frame.columns:
        frame = frame.set_index("date")
    frame.index = pd.to_datetime(frame.index)
    frame = frame.sort_index()
    frame.columns = [str(column).strip() for column in frame.columns]
    frame = frame.apply(pd.to_numeric, errors="coerce")
    if frame.index.duplicated().any():
        raise ValueError("Returns contain duplicate dates.")
    if frame.columns.duplicated().any():
        raise ValueError("Returns contain duplicate security columns.")
    return frame


def compound_scenario_returns(
    returns: pd.DataFrame,
    scenario: HistoricalScenario,
    securities: Iterable[str],
    minimum_observations: int = 2,
) -> tuple[pd.Series, int, pd.Timestamp, pd.Timestamp]:
    """Compound simple returns over the inclusive historical scenario window."""
    scenario.validate()
    frame = _validate_returns(returns)
    requested = sorted({str(security) for security in securities})
    missing = sorted(set(requested).difference(frame.columns))
    if missing:
        raise KeyError(
            f"Scenario {scenario.scenario_id} is missing return histories for: {missing}"
        )

    window = frame.loc[
        (frame.index >= scenario.start_date) & (frame.index <= scenario.end_date),
        requested,
    ].copy()
    if len(window) < minimum_observations:
        raise ValueError(
            f"Scenario {scenario.scenario_id} has only {len(window)} observations; "
            f"at least {minimum_observations} are required."
        )
    missing_cells = int(window.isna().sum().sum())
    if missing_cells:
        raise ValueError(
            f"Scenario {scenario.scenario_id} contains {missing_cells} missing returns."
        )
    if (window <= -1.0).any().any():
        raise ValueError(
            f"Scenario {scenario.scenario_id} contains a return at or below -100%."
        )

    compounded = (1.0 + window).prod(axis=0) - 1.0
    return (
        compounded.astype(float),
        int(len(window)),
        pd.Timestamp(window.index.min()).normalize(),
        pd.Timestamp(window.index.max()).normalize(),
    )


def apply_security_shocks(
    positions: pd.DataFrame,
    security_shocks: pd.Series,
    *,
    scenario_id: str,
    scenario_type: str,
    scenario_name: str,
    metric_basis: str = "portfolio_loss",
    shock_description: str = "",
    observations: int | None = None,
    scenario_start_date: pd.Timestamp | None = None,
    scenario_end_date: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Apply simple security-price returns to signed current market values."""
    frame = _validate_positions(positions)
    shocks = pd.Series(security_shocks, dtype=float)
    shocks.index = shocks.index.astype(str)
    missing = sorted(set(frame["security_id"]).difference(shocks.index))
    if missing:
        raise KeyError(
            f"Scenario {scenario_id} has no shock for securities: {missing}"
        )
    if not np.isfinite(shocks.to_numpy(dtype=float)).all():
        raise ValueError(f"Scenario {scenario_id} contains non-finite shocks.")

    detail = frame.copy()
    detail["security_shock"] = detail["security_id"].map(shocks)
    detail["position_pnl"] = detail["market_value"] * detail["security_shock"]
    detail["absolute_market_value"] = detail["market_value"].abs()

    worst = (
        detail.sort_values(
            ["member_id", "position_pnl", "security_id"],
            ascending=[True, True, True],
        )
        .groupby("member_id", as_index=False)
        .first()[["member_id", "security_id", "position_pnl", "security_shock"]]
        .rename(
            columns={
                "security_id": "worst_security_id",
                "position_pnl": "worst_security_pnl",
                "security_shock": "worst_security_shock",
            }
        )
    )
    result = (
        detail.groupby("member_id", as_index=False)
        .agg(
            scenario_pnl=("position_pnl", "sum"),
            gross_exposure=("absolute_market_value", "sum"),
            net_exposure=("market_value", "sum"),
        )
        .merge(worst, on="member_id", how="left", validate="one_to_one")
    )
    result["stress_requirement"] = (-result["scenario_pnl"]).clip(lower=0.0)
    result.insert(0, "scenario_name", scenario_name)
    result.insert(0, "scenario_type", scenario_type)
    result.insert(0, "scenario_id", scenario_id)
    result["metric_basis"] = metric_basis
    result["shock_description"] = shock_description
    result["observations"] = observations
    result["scenario_start_date"] = scenario_start_date
    result["scenario_end_date"] = scenario_end_date
    return result


def run_historical_scenarios(
    positions: pd.DataFrame,
    returns: pd.DataFrame,
    scenarios: Iterable[HistoricalScenario],
) -> pd.DataFrame:
    """Run all historical scenarios against current signed positions."""
    position_frame = _validate_positions(positions)
    scenario_list = list(scenarios)
    if not scenario_list:
        raise ValueError("At least one historical scenario is required.")
    ids = [scenario.scenario_id for scenario in scenario_list]
    if len(ids) != len(set(ids)):
        raise ValueError("Historical scenario IDs must be unique.")

    outputs: list[pd.DataFrame] = []
    securities = sorted(position_frame["security_id"].unique())
    for scenario in scenario_list:
        shocks, observations, actual_start, actual_end = compound_scenario_returns(
            returns,
            scenario,
            securities,
        )
        outputs.append(
            apply_security_shocks(
                position_frame,
                shocks,
                scenario_id=scenario.scenario_id,
                scenario_type="historical",
                scenario_name=scenario.name,
                metric_basis="portfolio_loss",
                shock_description=scenario.description,
                observations=observations,
                scenario_start_date=actual_start,
                scenario_end_date=actual_end,
            )
        )
    return pd.concat(outputs, ignore_index=True, sort=False)

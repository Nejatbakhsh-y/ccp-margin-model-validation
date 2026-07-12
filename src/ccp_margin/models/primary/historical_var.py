"""Primary historical-simulation value-at-risk margin model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from ccp_margin.models.primary.multi_day_returns import (
    SUPPORTED_HORIZONS,
    coerce_return_matrix,
    overlapping_multi_day_returns,
)
from ccp_margin.models.primary.portfolio_pnl import (
    MissingHistoryPolicy,
    PortfolioPnLResult,
    simulate_portfolio_pnl,
)

QuantileMethod = Literal[
    "inverted_cdf",
    "averaged_inverted_cdf",
    "closest_observation",
    "interpolated_inverted_cdf",
    "hazen",
    "weibull",
    "linear",
    "median_unbiased",
    "normal_unbiased",
    "lower",
    "higher",
    "midpoint",
    "nearest",
]


@dataclass(frozen=True)
class HistoricalVaRConfig:
    """Configuration for the primary historical-simulation model."""

    confidence_level: float = 0.99
    lookback_days: int = 500
    supported_horizons: tuple[int, ...] = SUPPORTED_HORIZONS
    missing_history_policy: MissingHistoryPolicy = "drop_scenario"
    minimum_scenarios: int = 100
    quantile_method: QuantileMethod = "higher"

    def __post_init__(self) -> None:
        if not 0.0 < self.confidence_level < 1.0:
            raise ValueError("confidence_level must be strictly between 0 and 1")
        if self.lookback_days <= 0:
            raise ValueError("lookback_days must be positive")
        if self.minimum_scenarios <= 0:
            raise ValueError("minimum_scenarios must be positive")
        if not self.supported_horizons:
            raise ValueError("supported_horizons cannot be empty")
        if any(horizon <= 0 for horizon in self.supported_horizons):
            raise ValueError("all supported_horizons must be positive")


@dataclass(frozen=True)
class HistoricalVaRResult:
    """Auditable output from one portfolio-horizon calculation."""

    valuation_date: pd.Timestamp
    horizon_days: int
    confidence_level: float
    lookback_days: int
    value_at_risk: float
    margin_amount: float
    var_scenario_date: pd.Timestamp
    scenario_count: int
    pnl_distribution: pd.DataFrame
    component_attribution: pd.DataFrame
    missing_history_report: pd.DataFrame
    diagnostics: dict[str, int | float | str]

    def summary(self) -> dict[str, int | float | str]:
        return {
            "valuation_date": self.valuation_date.date().isoformat(),
            "horizon_days": self.horizon_days,
            "confidence_level": self.confidence_level,
            "lookback_days": self.lookback_days,
            "scenario_count": self.scenario_count,
            "value_at_risk": self.value_at_risk,
            "margin_amount": self.margin_amount,
            "var_scenario_date": self.var_scenario_date.date().isoformat(),
            **self.diagnostics,
        }


class HistoricalSimulationVaR:
    """Apply observed historical returns to current portfolio positions."""

    def __init__(self, config: HistoricalVaRConfig | None = None) -> None:
        self.config = config or HistoricalVaRConfig()

    def calculate(
        self,
        positions: pd.DataFrame,
        daily_returns: pd.DataFrame,
        *,
        horizon_days: int,
        valuation_date: str | pd.Timestamp | None = None,
        lookback_days: int | None = None,
    ) -> HistoricalVaRResult:
        """Calculate historical VaR for one current portfolio and one horizon.

        Multi-day margin scenarios use directly observed overlapping compounded
        returns. The full scenario P&L distribution and security attribution at
        the selected historical quantile scenario are retained.
        """
        self._validate_horizon(horizon_days)
        effective_lookback = lookback_days or self.config.lookback_days
        if effective_lookback <= 0:
            raise ValueError("lookback_days must be positive")

        return_matrix = coerce_return_matrix(daily_returns)
        effective_valuation_date = self._resolve_valuation_date(
            positions,
            return_matrix,
            valuation_date,
        )
        eligible_daily = return_matrix.loc[
            return_matrix.index <= effective_valuation_date
        ]
        if eligible_daily.empty:
            raise ValueError(
                "no return observations are available on or before valuation_date"
            )

        horizon_returns = overlapping_multi_day_returns(
            eligible_daily,
            horizon_days,
        )
        horizon_returns = horizon_returns.dropna(how="all")
        horizon_returns = horizon_returns.tail(effective_lookback)
        if horizon_returns.empty:
            raise ValueError(
                f"no {horizon_days}-day return scenarios can be constructed"
            )

        pnl_result = simulate_portfolio_pnl(
            positions,
            horizon_returns,
            missing_history_policy=self.config.missing_history_policy,
        )
        self._validate_scenario_count(pnl_result, horizon_days)

        losses = -pnl_result.portfolio_pnl
        value_at_risk = float(
            np.quantile(
                losses.to_numpy(),
                self.config.confidence_level,
                method=self.config.quantile_method,
            )
        )
        margin_amount = max(value_at_risk, 0.0)
        var_scenario_date = self._select_var_scenario(losses, value_at_risk)

        distribution = pd.DataFrame(
            {
                "scenario_date": pnl_result.portfolio_pnl.index,
                "portfolio_pnl": pnl_result.portfolio_pnl.to_numpy(),
                "portfolio_loss": losses.to_numpy(),
            }
        ).sort_values("scenario_date", kind="mergesort")
        distribution["horizon_days"] = horizon_days
        distribution["is_var_scenario"] = distribution["scenario_date"].eq(
            var_scenario_date
        )
        distribution = distribution.reset_index(drop=True)

        attribution = self._build_component_attribution(
            pnl_result,
            var_scenario_date,
            value_at_risk,
        )

        diagnostics = dict(pnl_result.diagnostics)
        diagnostics.update(
            {
                "quantile_method": self.config.quantile_method,
                "overlapping_multi_day_returns": "yes",
                "serial_dependence_disclosure": (
                    "overlapping horizons create serial dependence; use "
                    "non-overlapping observations for formal independence tests"
                    if horizon_days > 1
                    else "not applicable for one-day horizon"
                ),
                "requested_lookback_scenarios": int(effective_lookback),
                "available_pre_policy_scenarios": int(len(horizon_returns)),
            }
        )

        return HistoricalVaRResult(
            valuation_date=effective_valuation_date,
            horizon_days=horizon_days,
            confidence_level=self.config.confidence_level,
            lookback_days=effective_lookback,
            value_at_risk=value_at_risk,
            margin_amount=margin_amount,
            var_scenario_date=var_scenario_date,
            scenario_count=len(pnl_result.portfolio_pnl),
            pnl_distribution=distribution,
            component_attribution=attribution,
            missing_history_report=pnl_result.missing_history_report,
            diagnostics=diagnostics,
        )

    def calculate_all_horizons(
        self,
        positions: pd.DataFrame,
        daily_returns: pd.DataFrame,
        *,
        valuation_date: str | pd.Timestamp | None = None,
        lookback_days: int | None = None,
    ) -> dict[int, HistoricalVaRResult]:
        """Calculate each configured horizon in deterministic sorted order."""
        return {
            horizon: self.calculate(
                positions,
                daily_returns,
                horizon_days=horizon,
                valuation_date=valuation_date,
                lookback_days=lookback_days,
            )
            for horizon in sorted(self.config.supported_horizons)
        }

    def _validate_horizon(self, horizon_days: int) -> None:
        if horizon_days not in self.config.supported_horizons:
            raise ValueError(
                f"unsupported horizon {horizon_days}; supported horizons are "
                f"{self.config.supported_horizons}"
            )

    def _validate_scenario_count(
        self,
        pnl_result: PortfolioPnLResult,
        horizon_days: int,
    ) -> None:
        actual = len(pnl_result.portfolio_pnl)
        if actual < self.config.minimum_scenarios:
            raise ValueError(
                f"only {actual} complete {horizon_days}-day scenarios remain; "
                f"minimum_scenarios={self.config.minimum_scenarios}"
            )

    @staticmethod
    def _resolve_valuation_date(
        positions: pd.DataFrame,
        return_matrix: pd.DataFrame,
        explicit_date: str | pd.Timestamp | None,
    ) -> pd.Timestamp:
        if explicit_date is not None:
            return pd.Timestamp(explicit_date)

        if "valuation_date" in positions.columns:
            dates = pd.to_datetime(
                positions["valuation_date"].dropna().unique(),
                errors="raise",
            )
            if len(dates) > 1:
                raise ValueError("positions contains multiple valuation_date values")
            if len(dates) == 1:
                return pd.Timestamp(dates[0])

        return pd.Timestamp(return_matrix.index.max())

    @staticmethod
    def _select_var_scenario(
        losses: pd.Series,
        value_at_risk: float,
    ) -> pd.Timestamp:
        exact = np.isclose(
            losses.to_numpy(),
            value_at_risk,
            rtol=1e-12,
            atol=1e-12,
        )
        if exact.any():
            candidates = losses.index[exact]
            return pd.Timestamp(min(candidates))

        distance = (losses - value_at_risk).abs()
        minimum = distance.min()
        candidates = distance.index[np.isclose(distance.to_numpy(), minimum)]
        return pd.Timestamp(min(candidates))

    @staticmethod
    def _build_component_attribution(
        pnl_result: PortfolioPnLResult,
        scenario_date: pd.Timestamp,
        value_at_risk: float,
    ) -> pd.DataFrame:
        scenario_returns_pnl = pnl_result.component_pnl.loc[scenario_date]
        positions = pnl_result.positions.set_index("security_id").copy()
        positions["scenario_pnl_contribution"] = scenario_returns_pnl
        positions["scenario_loss_contribution"] = -scenario_returns_pnl

        if not np.isclose(value_at_risk, 0.0):
            positions["loss_contribution_pct"] = (
                positions["scenario_loss_contribution"] / value_at_risk
            )
        else:
            positions["loss_contribution_pct"] = np.nan

        positions["var_scenario_date"] = scenario_date
        ordered_columns = [
            "current_market_value",
            "scenario_pnl_contribution",
            "scenario_loss_contribution",
            "loss_contribution_pct",
            "var_scenario_date",
        ]
        metadata = [
            column
            for column in (
                "member_id",
                "portfolio_id",
                "sector",
                "asset_class",
                "liquidity_bucket",
            )
            if column in positions.columns
        ]
        result = positions.loc[:, ordered_columns + metadata].reset_index()
        return result.sort_values(
            ["scenario_loss_contribution", "security_id"],
            ascending=[False, True],
            kind="mergesort",
        ).reset_index(drop=True)

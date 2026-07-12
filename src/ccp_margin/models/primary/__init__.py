"""Primary CCP margin-model implementations."""

from ccp_margin.models.primary.historical_var import (
    HistoricalSimulationVaR,
    HistoricalVaRConfig,
    HistoricalVaRResult,
)
from ccp_margin.models.primary.multi_day_returns import (
    build_horizon_return_matrices,
    non_overlapping_multi_day_returns,
    overlapping_multi_day_returns,
)
from ccp_margin.models.primary.portfolio_pnl import (
    PortfolioPnLResult,
    prepare_current_positions,
    simulate_portfolio_pnl,
)

__all__ = [
    "HistoricalSimulationVaR",
    "HistoricalVaRConfig",
    "HistoricalVaRResult",
    "PortfolioPnLResult",
    "build_horizon_return_matrices",
    "non_overlapping_multi_day_returns",
    "overlapping_multi_day_returns",
    "prepare_current_positions",
    "simulate_portfolio_pnl",
]

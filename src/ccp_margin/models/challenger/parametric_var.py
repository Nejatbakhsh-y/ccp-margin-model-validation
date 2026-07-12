"""Variance-covariance challenger VaR with EWMA and sensitivity controls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

import numpy as np
import pandas as pd
from scipy.stats import norm, t

from .correlation_controls import (
    correct_covariance_psd,
    stress_correlations,
)
from .ewma_covariance import (
    CovarianceEstimate,
    compound_multi_day_returns,
    ewma_covariance,
    sample_covariance,
)

CovarianceMethod = Literal["sample", "ewma"]
MultiDayMethod = Literal["sqrt_time", "direct"]
Distribution = Literal["normal", "student_t"]
MissingRiskFactorPolicy = Literal["raise", "drop"]


@dataclass(frozen=True)
class HorizonVaRResult:
    """Challenger-model result for one margin period of risk."""

    horizon_days: int
    var: float
    portfolio_volatility: float
    expected_pnl: float
    quantile: float
    distribution: str
    covariance_method: str
    multi_day_method: str
    observations_used: int
    covariance: pd.DataFrame
    component_var: pd.Series
    standalone_var_sum: float
    diversification_benefit: float
    psd_was_corrected: bool
    minimum_eigenvalue_before: float
    minimum_eigenvalue_after: float
    student_t_sensitivity_var: float | None = None
    correlation_stress_var: float | None = None


@dataclass(frozen=True)
class ParametricVaRResult:
    """Complete deterministic challenger-model result."""

    valuation_date: object | None
    confidence_level: float
    exposure_vector: pd.Series
    included_risk_factors: tuple[str, ...]
    excluded_risk_factors: tuple[str, ...]
    horizons: dict[int, HorizonVaRResult]

    def summary(self) -> pd.DataFrame:
        """Return a compact table suitable for reporting and reconciliation."""

        rows: list[dict[str, object]] = []
        for horizon, result in sorted(self.horizons.items()):
            rows.append(
                {
                    "horizon_days": horizon,
                    "var": result.var,
                    "portfolio_volatility": result.portfolio_volatility,
                    "expected_pnl": result.expected_pnl,
                    "observations_used": result.observations_used,
                    "covariance_method": result.covariance_method,
                    "multi_day_method": result.multi_day_method,
                    "psd_was_corrected": result.psd_was_corrected,
                    "standalone_var_sum": result.standalone_var_sum,
                    "diversification_benefit": result.diversification_benefit,
                    "student_t_sensitivity_var": result.student_t_sensitivity_var,
                    "correlation_stress_var": result.correlation_stress_var,
                }
            )
        return pd.DataFrame(rows).set_index("horizon_days")


class ParametricVaRModel:
    """Variance-covariance VaR challenger model.

    The model uses current signed market-value exposures and a covariance matrix
    estimated from historical risk-factor returns. Multi-day risk can be obtained
    by square-root-of-time scaling or by directly estimating covariance from
    compounded multi-day returns.
    """

    def __init__(
        self,
        *,
        confidence_level: float = 0.99,
        lookback_days: int = 500,
        covariance_method: CovarianceMethod = "ewma",
        ewma_lambda: float = 0.94,
        multi_day_method: MultiDayMethod = "sqrt_time",
        distribution: Distribution = "normal",
        student_t_df: float = 6.0,
        include_mean: bool = False,
        direct_returns_overlapping: bool = True,
        missing_risk_factor_policy: MissingRiskFactorPolicy = "raise",
        psd_eigenvalue_floor: float = 1.0e-12,
        student_t_sensitivity_df: float | None = 6.0,
        correlation_stress_multiplier: float | None = 1.25,
    ) -> None:
        if not 0.5 < confidence_level < 1.0:
            raise ValueError("confidence_level must be between 0.5 and 1.0.")
        if lookback_days < 2:
            raise ValueError("lookback_days must be at least 2.")
        if covariance_method not in {"sample", "ewma"}:
            raise ValueError("covariance_method must be 'sample' or 'ewma'.")
        if multi_day_method not in {"sqrt_time", "direct"}:
            raise ValueError("multi_day_method must be 'sqrt_time' or 'direct'.")
        if distribution not in {"normal", "student_t"}:
            raise ValueError("distribution must be 'normal' or 'student_t'.")
        if distribution == "student_t" and student_t_df <= 2.0:
            raise ValueError("student_t_df must exceed 2 so variance is finite.")
        if student_t_sensitivity_df is not None and student_t_sensitivity_df <= 2.0:
            raise ValueError("student_t_sensitivity_df must exceed 2.")
        if missing_risk_factor_policy not in {"raise", "drop"}:
            raise ValueError("missing_risk_factor_policy must be 'raise' or 'drop'.")

        self.confidence_level = confidence_level
        self.lookback_days = lookback_days
        self.covariance_method = covariance_method
        self.ewma_lambda = ewma_lambda
        self.multi_day_method = multi_day_method
        self.distribution = distribution
        self.student_t_df = student_t_df
        self.include_mean = include_mean
        self.direct_returns_overlapping = direct_returns_overlapping
        self.missing_risk_factor_policy = missing_risk_factor_policy
        self.psd_eigenvalue_floor = psd_eigenvalue_floor
        self.student_t_sensitivity_df = student_t_sensitivity_df
        self.correlation_stress_multiplier = correlation_stress_multiplier

    @staticmethod
    def build_exposure_vector(
        positions: pd.DataFrame,
        *,
        security_column: str = "security_id",
        exposure_column: str = "market_value",
        long_short_column: str = "long_short_flag",
    ) -> pd.Series:
        """Aggregate position records into signed current market-value exposures."""

        if not isinstance(positions, pd.DataFrame) or positions.empty:
            raise ValueError("positions must be a non-empty pandas DataFrame.")
        required = {security_column, exposure_column}
        missing = required.difference(positions.columns)
        if missing:
            raise ValueError(f"positions is missing required columns: {sorted(missing)}")

        frame = positions[[security_column, exposure_column]].copy()
        frame[security_column] = frame[security_column].astype(str)
        frame[exposure_column] = pd.to_numeric(frame[exposure_column], errors="coerce")
        if frame[exposure_column].isna().any():
            raise ValueError("positions contains missing or non-numeric market values.")

        # If market values are all non-negative, use long_short_flag to establish sign.
        if long_short_column in positions.columns and (frame[exposure_column] >= 0.0).all():
            flags = positions[long_short_column].astype(str).str.strip().str.lower()
            sign_map = {
                "long": 1.0,
                "l": 1.0,
                "+1": 1.0,
                "1": 1.0,
                "short": -1.0,
                "s": -1.0,
                "-1": -1.0,
            }
            signs = flags.map(sign_map)
            if signs.isna().any():
                unknown = sorted(flags[signs.isna()].unique().tolist())
                raise ValueError(f"Unrecognized long/short flags: {unknown}")
            frame[exposure_column] = frame[exposure_column] * signs.to_numpy()

        exposures = frame.groupby(security_column, sort=True)[exposure_column].sum()
        exposures.name = "signed_market_value"
        return exposures.astype(float)

    def _quantile(self, distribution: Distribution, degrees_of_freedom: float) -> float:
        if distribution == "normal":
            return float(norm.ppf(self.confidence_level))
        if degrees_of_freedom <= 2.0:
            raise ValueError("Student-t degrees of freedom must exceed 2.")
        # Standardize Student-t to unit variance so covariance remains comparable.
        return float(
            t.ppf(self.confidence_level, df=degrees_of_freedom)
            * np.sqrt((degrees_of_freedom - 2.0) / degrees_of_freedom)
        )

    def _estimate_covariance(
        self,
        daily_returns: pd.DataFrame,
        horizon_days: int,
    ) -> CovarianceEstimate:
        if self.multi_day_method == "sqrt_time":
            window = daily_returns.tail(self.lookback_days)
            estimate = self._estimate_one_window(window, horizon_days=1)
            return CovarianceEstimate(
                covariance=estimate.covariance * horizon_days,
                mean_returns=estimate.mean_returns * horizon_days,
                volatilities=estimate.volatilities * np.sqrt(horizon_days),
                correlation=estimate.correlation,
                observations_used=estimate.observations_used,
                method=estimate.method,
                horizon_days=horizon_days,
                decay_factor=estimate.decay_factor,
            )

        required_daily_rows = self.lookback_days + horizon_days - 1
        daily_window = daily_returns.tail(required_daily_rows)
        multi_day_returns = compound_multi_day_returns(
            daily_window,
            horizon_days,
            overlapping=self.direct_returns_overlapping,
        ).tail(self.lookback_days)
        return self._estimate_one_window(multi_day_returns, horizon_days=horizon_days)

    def _estimate_one_window(
        self,
        returns_window: pd.DataFrame,
        *,
        horizon_days: int,
    ) -> CovarianceEstimate:
        if self.covariance_method == "ewma":
            return ewma_covariance(
                returns_window,
                decay_factor=self.ewma_lambda,
                demean=self.include_mean,
                horizon_days=horizon_days,
                missing_policy="drop_rows",
            )
        return sample_covariance(
            returns_window,
            horizon_days=horizon_days,
            missing_policy="drop_rows",
        )

    @staticmethod
    def _portfolio_volatility(exposures: pd.Series, covariance: pd.DataFrame) -> float:
        vector = exposures.to_numpy(dtype=float)
        variance = float(vector @ covariance.to_numpy(dtype=float) @ vector)
        return float(np.sqrt(max(variance, 0.0)))

    def _var_from_covariance(
        self,
        exposures: pd.Series,
        covariance: pd.DataFrame,
        mean_returns: pd.Series,
        *,
        distribution: Distribution,
        degrees_of_freedom: float,
    ) -> tuple[float, float, float, float, pd.Series, float, float]:
        covariance = covariance.reindex(index=exposures.index, columns=exposures.index)
        mean_returns = mean_returns.reindex(exposures.index).fillna(0.0)

        quantile = self._quantile(distribution, degrees_of_freedom)
        portfolio_volatility = self._portfolio_volatility(exposures, covariance)
        expected_pnl = (
            float(exposures @ mean_returns) if self.include_mean else 0.0
        )
        raw_var = -expected_pnl + quantile * portfolio_volatility
        var_value = max(0.0, raw_var)

        covariance_times_exposure = covariance.to_numpy(dtype=float) @ exposures.to_numpy(dtype=float)
        if portfolio_volatility > 0.0:
            volatility_component = (
                quantile
                * exposures.to_numpy(dtype=float)
                * covariance_times_exposure
                / portfolio_volatility
            )
        else:
            volatility_component = np.zeros(len(exposures), dtype=float)

        mean_component = (
            -exposures.to_numpy(dtype=float) * mean_returns.to_numpy(dtype=float)
            if self.include_mean
            else np.zeros(len(exposures), dtype=float)
        )
        component_values = volatility_component + mean_component
        if raw_var < 0.0:
            component_values = np.zeros(len(exposures), dtype=float)
        component_var = pd.Series(
            component_values,
            index=exposures.index,
            name="component_var",
        )

        standalone_volatilities = np.sqrt(
            np.clip(np.diag(covariance.to_numpy(dtype=float)), 0.0, None)
        )
        standalone_var_sum = float(
            quantile
            * np.sum(np.abs(exposures.to_numpy(dtype=float)) * standalone_volatilities)
        )
        diversification_benefit = standalone_var_sum - quantile * portfolio_volatility

        return (
            var_value,
            portfolio_volatility,
            expected_pnl,
            quantile,
            component_var,
            standalone_var_sum,
            diversification_benefit,
        )

    def calculate(
        self,
        positions: pd.DataFrame,
        returns: pd.DataFrame,
        *,
        horizons: Iterable[int] = (1, 3, 5),
        valuation_date: object | None = None,
    ) -> ParametricVaRResult:
        """Calculate challenger VaR for one or more margin periods of risk."""

        exposures = self.build_exposure_vector(positions)
        if not isinstance(returns, pd.DataFrame) or returns.empty:
            raise ValueError("returns must be a non-empty pandas DataFrame.")

        return_frame = returns.copy()
        return_frame.columns = return_frame.columns.map(str)
        return_frame = return_frame.apply(pd.to_numeric, errors="coerce")
        return_frame = return_frame.replace([np.inf, -np.inf], np.nan).sort_index()

        missing_factors = tuple(sorted(set(exposures.index) - set(return_frame.columns)))
        if missing_factors and self.missing_risk_factor_policy == "raise":
            raise ValueError(
                "Return history is missing for risk factors: " + ", ".join(missing_factors)
            )
        if missing_factors:
            exposures = exposures.drop(list(missing_factors))
        if exposures.empty:
            raise ValueError("No positions remain after risk-factor alignment.")

        aligned_returns = return_frame.loc[:, exposures.index]
        all_missing = aligned_returns.columns[aligned_returns.isna().all()].tolist()
        if all_missing and self.missing_risk_factor_policy == "raise":
            raise ValueError(
                "Return history contains no usable observations for: "
                + ", ".join(all_missing)
            )
        if all_missing:
            aligned_returns = aligned_returns.drop(columns=all_missing)
            exposures = exposures.drop(all_missing)
            missing_factors = tuple(sorted(set(missing_factors).union(all_missing)))

        horizon_list = sorted({int(horizon) for horizon in horizons})
        if not horizon_list or any(horizon < 1 for horizon in horizon_list):
            raise ValueError("horizons must contain positive integers.")

        horizon_results: dict[int, HorizonVaRResult] = {}
        for horizon in horizon_list:
            estimate = self._estimate_covariance(aligned_returns, horizon)
            psd_result = correct_covariance_psd(
                estimate.covariance,
                eigenvalue_floor=self.psd_eigenvalue_floor,
            )
            covariance = psd_result.covariance.reindex(
                index=exposures.index,
                columns=exposures.index,
            )

            (
                var_value,
                portfolio_volatility,
                expected_pnl,
                quantile,
                component_var,
                standalone_var_sum,
                diversification_benefit,
            ) = self._var_from_covariance(
                exposures,
                covariance,
                estimate.mean_returns,
                distribution=self.distribution,
                degrees_of_freedom=self.student_t_df,
            )

            student_t_sensitivity_var: float | None = None
            if self.student_t_sensitivity_df is not None:
                student_t_sensitivity_var = self._var_from_covariance(
                    exposures,
                    covariance,
                    estimate.mean_returns,
                    distribution="student_t",
                    degrees_of_freedom=self.student_t_sensitivity_df,
                )[0]

            correlation_stress_var: float | None = None
            if self.correlation_stress_multiplier is not None:
                stressed_psd = stress_correlations(
                    covariance,
                    multiplier=self.correlation_stress_multiplier,
                    eigenvalue_floor=self.psd_eigenvalue_floor,
                )
                correlation_stress_var = self._var_from_covariance(
                    exposures,
                    stressed_psd.covariance,
                    estimate.mean_returns,
                    distribution=self.distribution,
                    degrees_of_freedom=self.student_t_df,
                )[0]

            horizon_results[horizon] = HorizonVaRResult(
                horizon_days=horizon,
                var=var_value,
                portfolio_volatility=portfolio_volatility,
                expected_pnl=expected_pnl,
                quantile=quantile,
                distribution=self.distribution,
                covariance_method=self.covariance_method,
                multi_day_method=self.multi_day_method,
                observations_used=estimate.observations_used,
                covariance=covariance,
                component_var=component_var,
                standalone_var_sum=standalone_var_sum,
                diversification_benefit=diversification_benefit,
                psd_was_corrected=psd_result.was_corrected,
                minimum_eigenvalue_before=psd_result.minimum_eigenvalue_before,
                minimum_eigenvalue_after=psd_result.minimum_eigenvalue_after,
                student_t_sensitivity_var=student_t_sensitivity_var,
                correlation_stress_var=correlation_stress_var,
            )

        return ParametricVaRResult(
            valuation_date=valuation_date,
            confidence_level=self.confidence_level,
            exposure_vector=exposures,
            included_risk_factors=tuple(exposures.index),
            excluded_risk_factors=missing_factors,
            horizons=horizon_results,
        )

    def run_lookback_sensitivity(
        self,
        positions: pd.DataFrame,
        returns: pd.DataFrame,
        *,
        lookbacks: Iterable[int] = (250, 500, 750),
        horizon_days: int = 1,
    ) -> pd.DataFrame:
        """Measure historical-window instability without modifying the model."""

        rows: list[dict[str, float | int]] = []
        original_lookback = self.lookback_days
        try:
            for lookback in sorted({int(value) for value in lookbacks}):
                if lookback < 2:
                    raise ValueError("Every lookback must be at least 2.")
                self.lookback_days = lookback
                result = self.calculate(
                    positions,
                    returns,
                    horizons=(horizon_days,),
                ).horizons[horizon_days]
                rows.append(
                    {
                        "lookback_days": lookback,
                        "var": result.var,
                        "portfolio_volatility": result.portfolio_volatility,
                        "observations_used": result.observations_used,
                    }
                )
        finally:
            self.lookback_days = original_lookback

        return pd.DataFrame(rows).set_index("lookback_days")

"""Challenger margin-model implementations."""

from .correlation_controls import (
    PSDCorrectionResult,
    correct_covariance_psd,
    covariance_to_correlation,
    correlation_to_covariance,
    stress_correlations,
)
from .ewma_covariance import (
    CovarianceEstimate,
    compound_multi_day_returns,
    ewma_covariance,
    sample_covariance,
)
from .parametric_var import (
    HorizonVaRResult,
    ParametricVaRModel,
    ParametricVaRResult,
)

__all__ = [
    "CovarianceEstimate",
    "HorizonVaRResult",
    "PSDCorrectionResult",
    "ParametricVaRModel",
    "ParametricVaRResult",
    "compound_multi_day_returns",
    "correct_covariance_psd",
    "correlation_to_covariance",
    "covariance_to_correlation",
    "ewma_covariance",
    "sample_covariance",
    "stress_correlations",
]

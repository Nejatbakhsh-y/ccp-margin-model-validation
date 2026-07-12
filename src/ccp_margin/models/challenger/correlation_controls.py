"""Correlation diagnostics, stress controls, and PSD covariance correction."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PSDCorrectionResult:
    """Corrected covariance matrix and numerical diagnostics."""

    covariance: pd.DataFrame
    was_corrected: bool
    minimum_eigenvalue_before: float
    minimum_eigenvalue_after: float
    condition_number_before: float
    condition_number_after: float
    frobenius_adjustment: float


def _validate_square_matrix(matrix: pd.DataFrame, name: str) -> pd.DataFrame:
    if not isinstance(matrix, pd.DataFrame):
        raise TypeError(f"{name} must be a pandas DataFrame.")
    if matrix.empty or matrix.shape[0] != matrix.shape[1]:
        raise ValueError(f"{name} must be a non-empty square matrix.")
    if list(matrix.index.map(str)) != list(matrix.columns.map(str)):
        raise ValueError(f"{name} index and columns must contain the same labels in the same order.")

    validated = matrix.copy()
    validated.index = validated.index.map(str)
    validated.columns = validated.columns.map(str)
    validated = validated.apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(validated.to_numpy(dtype=float)).all():
        raise ValueError(f"{name} contains NaN or infinite values.")
    return validated


def covariance_to_correlation(
    covariance: pd.DataFrame,
    *,
    variance_floor: float = 1.0e-18,
) -> tuple[pd.DataFrame, pd.Series]:
    """Convert a covariance matrix to a correlation matrix and volatilities."""

    covariance = _validate_square_matrix(covariance, "covariance")
    if variance_floor <= 0.0:
        raise ValueError("variance_floor must be positive.")

    values = 0.5 * (covariance.to_numpy(dtype=float) + covariance.to_numpy(dtype=float).T)
    variances = np.clip(np.diag(values), variance_floor, None)
    volatilities = np.sqrt(variances)
    denominator = np.outer(volatilities, volatilities)
    correlation_values = values / denominator
    correlation_values = np.clip(correlation_values, -1.0, 1.0)
    np.fill_diagonal(correlation_values, 1.0)

    labels = covariance.index
    return (
        pd.DataFrame(correlation_values, index=labels, columns=labels),
        pd.Series(volatilities, index=labels, name="volatility"),
    )


def correlation_to_covariance(
    correlation: pd.DataFrame,
    volatilities: pd.Series,
) -> pd.DataFrame:
    """Reconstruct a covariance matrix from correlation and volatility inputs."""

    correlation = _validate_square_matrix(correlation, "correlation")
    volatilities = pd.to_numeric(volatilities, errors="coerce").reindex(correlation.index)
    if volatilities.isna().any() or (volatilities < 0.0).any():
        raise ValueError("volatilities must be finite, non-negative, and aligned.")

    values = correlation.to_numpy(dtype=float) * np.outer(volatilities, volatilities)
    values = 0.5 * (values + values.T)
    return pd.DataFrame(values, index=correlation.index, columns=correlation.columns)


def _safe_condition_number(values: np.ndarray, eigenvalue_floor: float) -> float:
    eigenvalues = np.linalg.eigvalsh(values)
    maximum = float(np.max(np.abs(eigenvalues)))
    minimum = float(np.min(np.abs(eigenvalues)))
    if maximum == 0.0:
        return 1.0
    if minimum <= eigenvalue_floor:
        return float("inf")
    return maximum / minimum


def correct_covariance_psd(
    covariance: pd.DataFrame,
    *,
    eigenvalue_floor: float = 1.0e-12,
    tolerance: float = 1.0e-12,
) -> PSDCorrectionResult:
    """Project a covariance matrix to a PSD matrix while preserving variances.

    The correction is performed in correlation space by clipping eigenvalues,
    renormalizing the diagonal to one, and reconstructing covariance using the
    original marginal volatilities.
    """

    if eigenvalue_floor <= 0.0:
        raise ValueError("eigenvalue_floor must be positive.")
    if tolerance < 0.0:
        raise ValueError("tolerance must be non-negative.")

    covariance = _validate_square_matrix(covariance, "covariance")
    symmetric = 0.5 * (
        covariance.to_numpy(dtype=float) + covariance.to_numpy(dtype=float).T
    )
    labels = covariance.index

    eigenvalues_before = np.linalg.eigvalsh(symmetric)
    minimum_before = float(eigenvalues_before.min())
    condition_before = _safe_condition_number(symmetric, eigenvalue_floor)

    correlation, volatilities = covariance_to_correlation(
        pd.DataFrame(symmetric, index=labels, columns=labels)
    )
    corr_values = 0.5 * (
        correlation.to_numpy(dtype=float) + correlation.to_numpy(dtype=float).T
    )
    eigenvalues, eigenvectors = np.linalg.eigh(corr_values)
    clipped = np.clip(eigenvalues, eigenvalue_floor, None)
    corrected_corr = eigenvectors @ np.diag(clipped) @ eigenvectors.T
    corrected_corr = 0.5 * (corrected_corr + corrected_corr.T)

    diagonal_scale = np.sqrt(np.clip(np.diag(corrected_corr), eigenvalue_floor, None))
    corrected_corr = corrected_corr / np.outer(diagonal_scale, diagonal_scale)
    corrected_corr = np.clip(corrected_corr, -1.0, 1.0)
    np.fill_diagonal(corrected_corr, 1.0)

    corrected_covariance = corrected_corr * np.outer(volatilities, volatilities)
    corrected_covariance = 0.5 * (corrected_covariance + corrected_covariance.T)

    eigenvalues_after = np.linalg.eigvalsh(corrected_covariance)
    minimum_after = float(eigenvalues_after.min())
    condition_after = _safe_condition_number(corrected_covariance, eigenvalue_floor)
    adjustment = float(np.linalg.norm(corrected_covariance - symmetric, ord="fro"))
    was_corrected = minimum_before < -tolerance or adjustment > tolerance

    corrected_frame = pd.DataFrame(
        corrected_covariance,
        index=labels,
        columns=labels,
    )
    return PSDCorrectionResult(
        covariance=corrected_frame,
        was_corrected=was_corrected,
        minimum_eigenvalue_before=minimum_before,
        minimum_eigenvalue_after=minimum_after,
        condition_number_before=condition_before,
        condition_number_after=condition_after,
        frobenius_adjustment=adjustment,
    )


def stress_correlations(
    covariance: pd.DataFrame,
    *,
    multiplier: float = 1.25,
    absolute_shift: float = 0.0,
    eigenvalue_floor: float = 1.0e-12,
) -> PSDCorrectionResult:
    """Stress off-diagonal correlations, then restore PSD consistency.

    Positive correlations are moved upward and negative correlations are made
    more negative under a multiplier greater than one. ``absolute_shift`` can be
    used to move every off-diagonal correlation toward +1 or -1.
    """

    if multiplier < 0.0:
        raise ValueError("multiplier must be non-negative.")
    if not -1.0 <= absolute_shift <= 1.0:
        raise ValueError("absolute_shift must be between -1 and 1.")

    correlation, volatilities = covariance_to_correlation(covariance)
    stressed = correlation.to_numpy(dtype=float).copy()
    off_diagonal = ~np.eye(len(stressed), dtype=bool)
    stressed[off_diagonal] = (
        stressed[off_diagonal] * multiplier + absolute_shift
    )
    stressed[off_diagonal] = np.clip(stressed[off_diagonal], -0.999, 0.999)
    np.fill_diagonal(stressed, 1.0)

    stressed_covariance = correlation_to_covariance(
        pd.DataFrame(stressed, index=correlation.index, columns=correlation.columns),
        volatilities,
    )
    return correct_covariance_psd(
        stressed_covariance,
        eigenvalue_floor=eigenvalue_floor,
    )

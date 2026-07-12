"""Utilities for directly observed multi-day historical returns.

The margin calculation uses overlapping multi-day returns. Formal statistical
independence tests should use non-overlapping returns, or explicitly disclose
that overlapping observations are serially dependent.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

SUPPORTED_HORIZONS: tuple[int, ...] = (1, 3, 5)


def coerce_return_matrix(
    returns: pd.DataFrame,
    *,
    date_column: str = "date",
    security_column: str = "security_id",
    return_column: str = "return",
) -> pd.DataFrame:
    """Convert wide or long-form returns into a deterministic wide matrix.

    Accepted inputs
    ---------------
    Wide form:
        Datetime-like index and one column per security.
    Long form:
        Columns named ``date``, ``security_id``, and ``return`` by default.

    Returns
    -------
    pd.DataFrame
        Rows are sorted scenario dates and columns are sorted security IDs.
    """
    if not isinstance(returns, pd.DataFrame):
        raise TypeError("returns must be a pandas DataFrame")

    long_columns = {date_column, security_column, return_column}
    if long_columns.issubset(returns.columns):
        frame = returns.loc[:, [date_column, security_column, return_column]].copy()
        frame[date_column] = pd.to_datetime(frame[date_column], errors="raise")
        if frame.duplicated([date_column, security_column]).any():
            duplicates = frame.loc[
                frame.duplicated([date_column, security_column], keep=False),
                [date_column, security_column],
            ]
            raise ValueError(
                "returns contains duplicate date-security rows; examples: "
                f"{duplicates.head(5).to_dict(orient='records')}"
            )
        matrix = frame.pivot(
            index=date_column,
            columns=security_column,
            values=return_column,
        )
    else:
        matrix = returns.copy()
        if date_column in matrix.columns:
            matrix[date_column] = pd.to_datetime(matrix[date_column], errors="raise")
            matrix = matrix.set_index(date_column)
        else:
            matrix.index = pd.to_datetime(matrix.index, errors="raise")

    if matrix.index.has_duplicates:
        duplicate_dates = matrix.index[matrix.index.duplicated()].unique()
        raise ValueError(
            "returns contains duplicate dates; examples: "
            f"{[str(value) for value in duplicate_dates[:5]]}"
        )

    matrix = matrix.sort_index()
    matrix.columns = matrix.columns.map(str)
    matrix = matrix.reindex(sorted(matrix.columns), axis=1)
    matrix = matrix.apply(pd.to_numeric, errors="coerce").astype(float)

    if matrix.empty:
        raise ValueError("returns is empty")
    if not matrix.index.is_monotonic_increasing:
        raise ValueError("returns index must be sortable in increasing date order")
    if np.isinf(matrix.to_numpy(dtype=float, na_value=np.nan)).any():
        raise ValueError("returns contains positive or negative infinity")
    if (matrix <= -1.0).any().any():
        bad = matrix.where(matrix <= -1.0).stack().head(5)
        raise ValueError(
            "simple returns must be greater than -1.0; examples: "
            f"{bad.to_dict()}"
        )

    matrix.index.name = "scenario_date"
    return matrix


def overlapping_multi_day_returns(
    daily_returns: pd.DataFrame,
    horizon_days: int,
) -> pd.DataFrame:
    """Compound directly observed overlapping returns over ``horizon_days``.

    For a horizon ``h``, the return ending on date ``t`` is
    ``prod(1 + r[t-h+1:t]) - 1``. Each security requires all ``h`` daily
    observations in its window; otherwise that security-horizon return is NaN.
    """
    matrix = coerce_return_matrix(daily_returns)
    _validate_horizon(horizon_days)

    if horizon_days == 1:
        return matrix.copy()

    compounded = (
        (1.0 + matrix)
        .rolling(window=horizon_days, min_periods=horizon_days)
        .apply(np.prod, raw=True)
        - 1.0
    )
    compounded.index.name = "scenario_date"
    return compounded


def non_overlapping_multi_day_returns(
    daily_returns: pd.DataFrame,
    horizon_days: int,
    *,
    anchor: str = "end",
) -> pd.DataFrame:
    """Compound non-overlapping returns for formal independence analysis.

    ``anchor='end'`` discards the earliest incomplete block so that the most
    recent daily observation remains in the sample. ``anchor='start'`` keeps
    the earliest complete blocks and discards a trailing incomplete block.
    """
    matrix = coerce_return_matrix(daily_returns)
    _validate_horizon(horizon_days)

    if anchor not in {"start", "end"}:
        raise ValueError("anchor must be 'start' or 'end'")
    if horizon_days == 1:
        return matrix.copy()

    remainder = len(matrix) % horizon_days
    if anchor == "end" and remainder:
        matrix = matrix.iloc[remainder:]
    elif anchor == "start" and remainder:
        matrix = matrix.iloc[:-remainder]

    if matrix.empty:
        return matrix.copy()

    block_number = np.arange(len(matrix)) // horizon_days
    values: list[pd.Series] = []
    dates: list[pd.Timestamp] = []

    for _, block in matrix.groupby(block_number, sort=True):
        if len(block) != horizon_days:
            continue
        values.append((1.0 + block).prod(min_count=horizon_days) - 1.0)
        dates.append(pd.Timestamp(block.index[-1]))

    result = pd.DataFrame(values, index=pd.DatetimeIndex(dates))
    result = result.reindex(columns=matrix.columns)
    result.index.name = "scenario_date"
    return result


def build_horizon_return_matrices(
    daily_returns: pd.DataFrame,
    horizons: Iterable[int] = SUPPORTED_HORIZONS,
    *,
    overlapping: bool = True,
) -> dict[int, pd.DataFrame]:
    """Build deterministic return matrices for multiple horizons."""
    normalized_horizons = tuple(int(value) for value in horizons)
    if not normalized_horizons:
        raise ValueError("at least one horizon must be provided")

    builder = (
        overlapping_multi_day_returns
        if overlapping
        else non_overlapping_multi_day_returns
    )
    return {
        horizon: builder(daily_returns, horizon)
        for horizon in normalized_horizons
    }


def _validate_horizon(horizon_days: int) -> None:
    if isinstance(horizon_days, bool) or not isinstance(horizon_days, int):
        raise TypeError("horizon_days must be an integer")
    if horizon_days <= 0:
        raise ValueError("horizon_days must be positive")

"""Margin-shortfall measurement and aggregation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MarginShortfallResult:
    """Structured margin-shortfall results."""

    number_of_observations: int
    number_of_exceptions: int
    total_shortfall: float
    mean_shortfall: float
    maximum_shortfall: float
    exception_records: pd.DataFrame
    shortfall_by_member: pd.DataFrame
    shortfall_by_portfolio_type: pd.DataFrame
    shortfall_by_stress_status: pd.DataFrame

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for key in (
            "exception_records",
            "shortfall_by_member",
            "shortfall_by_portfolio_type",
            "shortfall_by_stress_status",
        ):
            result[key] = result[key].to_dict(orient="records")
        return result


_REQUIRED_COLUMNS = {"actual_loss", "available_margin"}


def _aggregate(frame: pd.DataFrame, group_column: str) -> pd.DataFrame:
    if group_column not in frame.columns:
        return pd.DataFrame(
            columns=[
                group_column,
                "exception_count",
                "total_shortfall",
                "mean_shortfall",
                "maximum_shortfall",
            ]
        )

    if frame.empty:
        return pd.DataFrame(
            columns=[
                group_column,
                "exception_count",
                "total_shortfall",
                "mean_shortfall",
                "maximum_shortfall",
            ]
        )

    return (
        frame.groupby(group_column, dropna=False, observed=True)
        .agg(
            exception_count=("shortfall", "size"),
            total_shortfall=("shortfall", "sum"),
            mean_shortfall=("shortfall", "mean"),
            maximum_shortfall=("shortfall", "max"),
        )
        .reset_index()
        .sort_values("total_shortfall", ascending=False, kind="stable")
        .reset_index(drop=True)
    )


def calculate_margin_shortfall(
    observations: pd.DataFrame,
    *,
    actual_loss_column: str = "actual_loss",
    available_margin_column: str = "available_margin",
    member_column: str = "member_id",
    portfolio_type_column: str = "portfolio_type",
    stressed_period_column: str = "is_stressed_period",
) -> MarginShortfallResult:
    """Calculate positive margin shortfall for every exception.

    ``actual_loss`` must be represented as a positive loss amount. The exception
    condition is ``actual_loss > available_margin`` and the shortfall is
    ``actual_loss - available_margin``.
    """
    if not isinstance(observations, pd.DataFrame):
        raise TypeError("observations must be a pandas DataFrame.")

    required = {actual_loss_column, available_margin_column}
    missing = required.difference(observations.columns)
    if missing:
        raise KeyError(f"Missing required columns: {sorted(missing)}")

    frame = observations.copy()
    for column in (actual_loss_column, available_margin_column):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
        if not np.all(np.isfinite(frame[column].to_numpy(dtype=float))):
            raise ValueError(f"{column} must contain only finite values.")

    if (frame[actual_loss_column] < 0).any():
        raise ValueError("actual_loss must use positive loss magnitudes.")
    if (frame[available_margin_column] < 0).any():
        raise ValueError("available_margin must be non-negative.")

    frame["exception_flag"] = frame[actual_loss_column] > frame[available_margin_column]
    frame["shortfall"] = (
        frame[actual_loss_column] - frame[available_margin_column]
    ).clip(lower=0.0)

    exceptions = frame.loc[frame["exception_flag"]].copy()
    exceptions = exceptions.sort_values(
        "shortfall",
        ascending=False,
        kind="stable",
    ).reset_index(drop=True)

    count = int(len(exceptions))
    total = float(exceptions["shortfall"].sum()) if count else 0.0
    mean = float(exceptions["shortfall"].mean()) if count else 0.0
    maximum = float(exceptions["shortfall"].max()) if count else 0.0

    stress_group = stressed_period_column
    if stress_group in exceptions.columns:
        exceptions[stress_group] = exceptions[stress_group].fillna(False).astype(bool)

    return MarginShortfallResult(
        number_of_observations=int(len(frame)),
        number_of_exceptions=count,
        total_shortfall=total,
        mean_shortfall=mean,
        maximum_shortfall=maximum,
        exception_records=exceptions,
        shortfall_by_member=_aggregate(exceptions, member_column),
        shortfall_by_portfolio_type=_aggregate(
            exceptions,
            portfolio_type_column,
        ),
        shortfall_by_stress_status=_aggregate(exceptions, stress_group),
    )

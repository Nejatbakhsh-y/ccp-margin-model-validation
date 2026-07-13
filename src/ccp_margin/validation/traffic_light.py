"""Basel-style traffic-light diagnostic for 99% VaR backtesting."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from ._utils import as_binary_flags


@dataclass(frozen=True)
class TrafficLightResult:
    """Basel-style exception-zone diagnostic."""

    number_of_observations: int
    number_of_exceptions: int
    zone: str
    applicable_standard_window: bool
    diagnostic_only: bool
    disclosure: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def basel_traffic_light(
    exceptions: list[int] | list[bool],
    *,
    require_250_observations: bool = False,
) -> TrafficLightResult:
    """Classify 99% VaR exceptions using the Basel 250-day thresholds.

    Green: 0-4 exceptions
    Yellow: 5-9 exceptions
    Red: 10 or more exceptions

    The thresholds are returned as a diagnostic. They were developed for bank
    trading-book VaR backtesting and are not, by themselves, a CCP margin-model
    approval standard.
    """
    flags = as_binary_flags(exceptions)
    observations = int(flags.size)
    if require_250_observations and observations != 250:
        raise ValueError(
            "The Basel traffic-light diagnostic requires exactly 250 "
            "observations when require_250_observations=True."
        )

    exceptions_count = int(flags.sum())
    if exceptions_count <= 4:
        zone = "green"
    elif exceptions_count <= 9:
        zone = "yellow"
    else:
        zone = "red"

    disclosure = (
        "Diagnostic based on the Basel 99% VaR backtesting framework for a "
        "250-observation window. It was designed for a bank VaR context and "
        "must not be treated as a stand-alone CCP margin-model approval rule."
    )

    return TrafficLightResult(
        number_of_observations=observations,
        number_of_exceptions=exceptions_count,
        zone=zone,
        applicable_standard_window=bool(observations == 250),
        diagnostic_only=True,
        disclosure=disclosure,
    )

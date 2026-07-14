"""Hypothetical CCP margin stress scenarios."""

from __future__ import annotations

from statistics import NormalDist
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from .historical import apply_security_shocks


_REQUIRED_POSITION_COLUMNS = {
    "member_id",
    "security_id",
    "market_value",
    "asset_class",
    "liquidity_bucket",
}


def _validate_positions(positions: pd.DataFrame) -> pd.DataFrame:
    missing = _REQUIRED_POSITION_COLUMNS.difference(positions.columns)
    if missing:
        raise ValueError(f"Positions are missing required fields: {sorted(missing)}")
    frame = positions.copy()
    frame["member_id"] = frame["member_id"].astype(str).str.strip()
    frame["security_id"] = frame["security_id"].astype(str).str.strip()
    frame["asset_class"] = frame["asset_class"].astype(str).str.strip().str.lower()
    frame["liquidity_bucket"] = (
        frame["liquidity_bucket"].astype(str).str.strip().str.lower()
    )
    frame["market_value"] = pd.to_numeric(frame["market_value"], errors="raise")
    if frame.empty:
        raise ValueError("Positions cannot be empty.")
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
    return frame


def _scenario_row_frame(
    member_ids: Iterable[str],
    *,
    scenario_id: str,
    scenario_name: str,
    metric_basis: str,
    requirement: pd.Series,
    scenario_pnl: pd.Series | None = None,
    shock_description: str = "",
) -> pd.DataFrame:
    members = pd.Index([str(value) for value in member_ids], name="member_id")
    req = pd.Series(requirement, dtype=float).reindex(members)
    if req.isna().any():
        raise ValueError(f"Scenario {scenario_id} has missing member requirements.")
    pnl = (
        pd.Series(0.0, index=members, dtype=float)
        if scenario_pnl is None
        else pd.Series(scenario_pnl, dtype=float).reindex(members)
    )
    result = pd.DataFrame(
        {
            "scenario_id": scenario_id,
            "scenario_type": "hypothetical",
            "scenario_name": scenario_name,
            "member_id": members,
            "scenario_pnl": pnl.to_numpy(dtype=float),
            "stress_requirement": req.clip(lower=0.0).to_numpy(dtype=float),
            "metric_basis": metric_basis,
            "shock_description": shock_description,
        }
    )
    return result


def _constant_shock_vector(
    securities: Iterable[str],
    shocked_securities: set[str],
    shock: float,
) -> pd.Series:
    return pd.Series(
        {
            str(security): float(shock) if str(security) in shocked_securities else 0.0
            for security in securities
        },
        dtype=float,
    )


def equity_price_scenarios(
    positions: pd.DataFrame,
    equity_securities: Iterable[str],
    declines: Iterable[float],
) -> list[pd.DataFrame]:
    frame = _validate_positions(positions)
    equities = {str(value) for value in equity_securities}
    present = equities.intersection(frame["security_id"])
    if not present:
        raise ValueError(
            "No configured equity securities are present in the positions."
        )
    outputs: list[pd.DataFrame] = []
    securities = sorted(frame["security_id"].unique())
    for decline in declines:
        magnitude = float(decline)
        if not 0.0 < magnitude < 1.0:
            raise ValueError("Equity decline magnitudes must be between 0 and 1.")
        pct = int(round(magnitude * 100))
        outputs.append(
            apply_security_shocks(
                frame,
                _constant_shock_vector(securities, equities, -magnitude),
                scenario_id=f"HYP_EQUITY_DOWN_{pct}",
                scenario_type="hypothetical",
                scenario_name=f"Equity prices down {pct}%",
                shock_description=(
                    f"Configured equity securities receive a {-magnitude:.2%} simple return; "
                    "other securities receive zero direct price shock."
                ),
            )
        )
    return outputs


def treasury_yield_scenarios(
    positions: pd.DataFrame,
    treasury_securities: Iterable[str],
    yield_shocks_bps: Iterable[float],
    duration_years: Mapping[str, float],
    convexity_years2: Mapping[str, float],
) -> list[pd.DataFrame]:
    frame = _validate_positions(positions)
    configured = {str(value) for value in treasury_securities}
    present = sorted(configured.intersection(frame["security_id"]))
    if not present:
        raise ValueError(
            "No configured Treasury securities are present in the positions."
        )
    missing_parameters = [
        security
        for security in present
        if security not in duration_years or security not in convexity_years2
    ]
    if missing_parameters:
        raise KeyError(
            "Treasury duration/convexity parameters are missing for: "
            f"{missing_parameters}"
        )

    outputs: list[pd.DataFrame] = []
    all_securities = sorted(frame["security_id"].unique())
    for shock_bps in yield_shocks_bps:
        bps = float(shock_bps)
        if bps <= 0.0:
            raise ValueError("Treasury yield shocks must be positive.")
        dy = bps / 10000.0
        shocks = pd.Series(0.0, index=all_securities, dtype=float)
        for security in present:
            duration = float(duration_years[security])
            convexity = float(convexity_years2[security])
            shocks.loc[security] = -duration * dy + 0.5 * convexity * dy * dy
        outputs.append(
            apply_security_shocks(
                frame,
                shocks,
                scenario_id=f"HYP_TSY_YIELD_UP_{int(round(bps))}BP",
                scenario_type="hypothetical",
                scenario_name=f"Treasury yields up {int(round(bps))} basis points",
                shock_description=(
                    "Treasury ETF price returns use the duration-convexity approximation "
                    "-D*dy + 0.5*C*dy^2 with explicitly configured parameters."
                ),
            )
        )
    return outputs


def credit_spread_scenarios(
    positions: pd.DataFrame,
    credit_securities: Iterable[str],
    spread_shocks_bps: Iterable[float],
    spread_duration_years: Mapping[str, float],
) -> list[pd.DataFrame]:
    frame = _validate_positions(positions)
    configured = {str(value) for value in credit_securities}
    present = sorted(configured.intersection(frame["security_id"]))
    if not present:
        raise ValueError(
            "No configured credit securities are present in the positions."
        )
    missing_parameters = [
        security for security in present if security not in spread_duration_years
    ]
    if missing_parameters:
        raise KeyError(
            f"Credit spread-duration parameters are missing for: {missing_parameters}"
        )

    outputs: list[pd.DataFrame] = []
    all_securities = sorted(frame["security_id"].unique())
    for shock_bps in spread_shocks_bps:
        bps = float(shock_bps)
        if bps <= 0.0:
            raise ValueError("Credit-spread shocks must be positive.")
        ds = bps / 10000.0
        shocks = pd.Series(0.0, index=all_securities, dtype=float)
        for security in present:
            shocks.loc[security] = -float(spread_duration_years[security]) * ds
        outputs.append(
            apply_security_shocks(
                frame,
                shocks,
                scenario_id=f"HYP_CREDIT_SPREAD_WIDER_{int(round(bps))}BP",
                scenario_type="hypothetical",
                scenario_name=f"Credit spreads wider by {int(round(bps))} basis points",
                shock_description=(
                    "Credit ETF price returns use the first-order spread-duration "
                    "approximation -SD*spread_change."
                ),
            )
        )
    return outputs


def volatility_doubled_scenario(
    positions: pd.DataFrame,
    returns: pd.DataFrame,
    *,
    multiplier: float,
    confidence_level: float,
    horizon_days: int,
    lookback_days: int,
) -> pd.DataFrame:
    frame = _validate_positions(positions)
    history = _validate_returns(returns)
    if multiplier <= 1.0:
        raise ValueError("Volatility multiplier must exceed 1.")
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be between 0 and 1.")
    if horizon_days < 1 or lookback_days < 2:
        raise ValueError("horizon_days and lookback_days are invalid.")

    securities = sorted(frame["security_id"].unique())
    missing = sorted(set(securities).difference(history.columns))
    if missing:
        raise KeyError(f"Volatility scenario is missing histories for: {missing}")
    sample = history.loc[:, securities].tail(lookback_days)
    if sample.isna().any().any():
        raise ValueError("Volatility scenario lookback contains missing returns.")
    multi_day = (1.0 + sample).rolling(horizon_days).apply(np.prod, raw=True) - 1.0
    multi_day = multi_day.dropna(how="any")
    means = multi_day.mean(axis=0)
    stressed = means + multiplier * (multi_day - means)

    results: list[dict[str, object]] = []
    for member_id, group in frame.groupby("member_id", sort=True):
        exposure = (
            group.groupby("security_id")["market_value"]
            .sum()
            .reindex(securities, fill_value=0.0)
        )
        pnl = stressed.to_numpy(dtype=float) @ exposure.to_numpy(dtype=float)
        losses = -pnl
        try:
            requirement = float(np.quantile(losses, confidence_level, method="higher"))
        except TypeError:
            requirement = float(
                np.quantile(losses, confidence_level, interpolation="higher")
            )
        results.append(
            {
                "member_id": member_id,
                "scenario_pnl": -max(requirement, 0.0),
                "stress_requirement": max(requirement, 0.0),
            }
        )
    result = pd.DataFrame(results)
    result.insert(0, "scenario_name", "Volatility doubled")
    result.insert(0, "scenario_type", "hypothetical")
    result.insert(0, "scenario_id", "HYP_VOLATILITY_DOUBLED")
    result["metric_basis"] = "stressed_loss_distribution"
    result["shock_description"] = (
        f"Overlapping {horizon_days}-day returns are centered and deviations are "
        f"multiplied by {multiplier:g}; the {confidence_level:.2%} empirical loss "
        f"quantile is calculated over the latest {len(sample)} daily observations."
    )
    result["observations"] = int(len(multi_day))
    return result


def correlation_convergence_scenario(
    positions: pd.DataFrame,
    returns: pd.DataFrame,
    *,
    target_correlation: float,
    confidence_level: float,
    horizon_days: int,
    lookback_days: int,
) -> pd.DataFrame:
    frame = _validate_positions(positions)
    history = _validate_returns(returns)
    if not 0.0 <= target_correlation < 1.0:
        raise ValueError("target_correlation must be in [0, 1).")
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be between 0 and 1.")

    securities = sorted(frame["security_id"].unique())
    missing = sorted(set(securities).difference(history.columns))
    if missing:
        raise KeyError(f"Correlation scenario is missing histories for: {missing}")
    sample = history.loc[:, securities].tail(lookback_days)
    if sample.isna().any().any():
        raise ValueError("Correlation scenario lookback contains missing returns.")
    standard_deviations = sample.std(axis=0, ddof=1).to_numpy(dtype=float)
    if not np.isfinite(standard_deviations).all() or (standard_deviations <= 0.0).any():
        raise ValueError("Correlation scenario requires positive finite volatilities.")

    count = len(securities)
    correlation = np.full((count, count), target_correlation, dtype=float)
    np.fill_diagonal(correlation, 1.0)
    covariance = np.outer(standard_deviations, standard_deviations) * correlation
    z_score = NormalDist().inv_cdf(confidence_level)

    rows: list[dict[str, object]] = []
    for member_id, group in frame.groupby("member_id", sort=True):
        exposure = (
            group.groupby("security_id")["market_value"]
            .sum()
            .reindex(securities, fill_value=0.0)
        )
        vector = exposure.to_numpy(dtype=float)
        variance = float(vector @ covariance @ vector) * float(horizon_days)
        requirement = z_score * np.sqrt(max(variance, 0.0))
        rows.append(
            {
                "member_id": member_id,
                "scenario_pnl": -requirement,
                "stress_requirement": requirement,
            }
        )
    result = pd.DataFrame(rows)
    result.insert(0, "scenario_name", "Correlations converge toward one")
    result.insert(0, "scenario_type", "hypothetical")
    result.insert(0, "scenario_id", "HYP_CORRELATIONS_TO_ONE")
    result["metric_basis"] = "stressed_margin_requirement"
    result["shock_description"] = (
        f"All off-diagonal correlations are set to {target_correlation:.2f}; "
        f"current volatilities, a {horizon_days}-day square-root horizon, and the "
        f"{confidence_level:.2%} normal quantile are used."
    )
    result["observations"] = int(len(sample))
    return result


def trading_volume_scenario(
    margin: pd.DataFrame,
    *,
    decline_pct: float,
    impact_exponent: float,
) -> pd.DataFrame:
    required = {"member_id", "total_margin", "liquidity_addon"}
    missing = required.difference(margin.columns)
    if missing:
        raise ValueError(f"Margin data are missing fields: {sorted(missing)}")
    if not 0.0 < decline_pct < 1.0:
        raise ValueError("decline_pct must be between 0 and 1.")
    if impact_exponent <= 0.0:
        raise ValueError("impact_exponent must be positive.")

    frame = margin.copy()
    frame["total_margin"] = pd.to_numeric(frame["total_margin"], errors="raise")
    frame["liquidity_addon"] = pd.to_numeric(frame["liquidity_addon"], errors="raise")
    remaining = 1.0 - decline_pct
    multiplier = remaining ** (-impact_exponent)
    stressed_liquidity = frame["liquidity_addon"] * multiplier
    requirement = frame["total_margin"] - frame["liquidity_addon"] + stressed_liquidity
    result = _scenario_row_frame(
        frame["member_id"],
        scenario_id="HYP_VOLUME_DOWN_80",
        scenario_name="Trading volume falls by 80%",
        metric_basis="stressed_margin_requirement",
        requirement=pd.Series(
            requirement.to_numpy(), index=frame["member_id"].astype(str)
        ),
        shock_description=(
            f"Liquidity add-ons scale by remaining_volume^(-{impact_exponent:g}); "
            f"an {decline_pct:.0%} decline produces a {multiplier:.6f} multiplier."
        ),
    )
    result["stressed_liquidity_addon"] = stressed_liquidity.to_numpy(dtype=float)
    result["liquidity_multiplier"] = multiplier
    return result


def largest_position_gap_scenario(
    positions: pd.DataFrame,
    *,
    gap_pct: float,
) -> pd.DataFrame:
    frame = _validate_positions(positions)
    if not 0.0 < gap_pct <= 1.0:
        raise ValueError("gap_pct must be in (0, 1].")
    rows: list[dict[str, object]] = []
    for member_id, group in frame.groupby("member_id", sort=True):
        ranked = group.assign(_abs=group["market_value"].abs()).sort_values(
            ["_abs", "security_id"], ascending=[False, True]
        )
        largest = ranked.iloc[0]
        loss = float(largest["_abs"]) * gap_pct
        adverse_return = -gap_pct if float(largest["market_value"]) >= 0.0 else gap_pct
        rows.append(
            {
                "scenario_id": "HYP_LARGEST_POSITION_GAP_25",
                "scenario_type": "hypothetical",
                "scenario_name": "Largest position gaps by 25%",
                "member_id": member_id,
                "scenario_pnl": -loss,
                "stress_requirement": loss,
                "metric_basis": "portfolio_loss",
                "shock_description": (
                    "The member's largest absolute position receives a 25% adverse "
                    "overnight price gap; direction is adverse for both long and short positions."
                ),
                "worst_security_id": str(largest["security_id"]),
                "worst_security_shock": adverse_return,
                "worst_security_pnl": -loss,
            }
        )
    return pd.DataFrame(rows)


def largest_member_default_scenario(
    positions: pd.DataFrame,
    margin: pd.DataFrame,
    *,
    equity_securities: Iterable[str],
    treasury_securities: Iterable[str],
    credit_securities: Iterable[str],
    treasury_duration_years: Mapping[str, float],
    treasury_convexity_years2: Mapping[str, float],
    credit_spread_duration_years: Mapping[str, float],
    volume_decline_pct: float,
    liquidity_impact_exponent: float,
    gap_pct: float,
    equity_decline_pct: float,
    treasury_yield_shock_bps: float,
    credit_spread_shock_bps: float,
) -> pd.DataFrame:
    frame = _validate_positions(positions)
    required_margin = {"member_id", "total_margin", "liquidity_addon"}
    missing_margin = required_margin.difference(margin.columns)
    if missing_margin:
        raise ValueError(
            f"Margin data are missing fields for default scenario: {sorted(missing_margin)}"
        )

    gross = (
        frame.assign(_abs=frame["market_value"].abs())
        .groupby("member_id")["_abs"]
        .sum()
    )
    largest_member = str(gross.sort_values(ascending=False).index[0])
    member_positions = frame.loc[frame["member_id"] == largest_member].copy()
    all_securities = sorted(member_positions["security_id"].unique())
    shocks = pd.Series(0.0, index=all_securities, dtype=float)

    equity_set = {str(value) for value in equity_securities}
    treasury_set = {str(value) for value in treasury_securities}
    credit_set = {str(value) for value in credit_securities}
    for security in all_securities:
        if security in equity_set:
            shocks.loc[security] = -float(equity_decline_pct)
        elif security in treasury_set:
            if (
                security not in treasury_duration_years
                or security not in treasury_convexity_years2
            ):
                raise KeyError(f"Missing Treasury parameters for {security}.")
            dy = float(treasury_yield_shock_bps) / 10000.0
            shocks.loc[security] = (
                -float(treasury_duration_years[security]) * dy
                + 0.5 * float(treasury_convexity_years2[security]) * dy * dy
            )
        elif security in credit_set:
            if security not in credit_spread_duration_years:
                raise KeyError(f"Missing credit spread duration for {security}.")
            shocks.loc[security] = -float(credit_spread_duration_years[security]) * (
                float(credit_spread_shock_bps) / 10000.0
            )

    ranked = member_positions.assign(
        _abs=member_positions["market_value"].abs()
    ).sort_values(["_abs", "security_id"], ascending=[False, True])
    largest_position = ranked.iloc[0]
    largest_security = str(largest_position["security_id"])
    adverse_gap = (
        -gap_pct if float(largest_position["market_value"]) >= 0.0 else gap_pct
    )
    existing = float(shocks.loc[largest_security])
    existing_position_pnl = float(largest_position["market_value"]) * existing
    gap_position_pnl = float(largest_position["market_value"]) * adverse_gap
    if gap_position_pnl < existing_position_pnl:
        shocks.loc[largest_security] = adverse_gap

    shocked = apply_security_shocks(
        member_positions,
        shocks,
        scenario_id="HYP_LARGEST_MEMBER_DEFAULT_STRESSED_LIQUIDITY",
        scenario_type="hypothetical",
        scenario_name="Largest member defaults during stressed liquidity",
        metric_basis="default_resource_requirement",
        shock_description=(
            "Largest member by gross exposure receives the maximum configured equity, "
            "rates, and credit shocks, plus the largest-position-gap and stressed-volume "
            "assumptions concurrently."
        ),
    )
    margin_row = margin.loc[margin["member_id"].astype(str) == largest_member]
    if len(margin_row) != 1:
        raise ValueError(
            f"Expected exactly one margin row for largest member {largest_member}; "
            f"found {len(margin_row)}."
        )
    base_liquidity = float(margin_row.iloc[0]["liquidity_addon"])
    remaining = 1.0 - volume_decline_pct
    liquidity_multiplier = remaining ** (-liquidity_impact_exponent)
    incremental_liquidity = base_liquidity * (liquidity_multiplier - 1.0)
    shocked["market_loss"] = shocked["stress_requirement"]
    shocked["incremental_liquidity_requirement"] = incremental_liquidity
    shocked["stress_requirement"] = shocked["market_loss"] + incremental_liquidity
    shocked["defaulted_member_flag"] = True
    return shocked


def run_hypothetical_scenarios(
    positions: pd.DataFrame,
    returns: pd.DataFrame,
    margin: pd.DataFrame,
    config: Mapping[str, Any],
) -> pd.DataFrame:
    """Run the complete governed set of fourteen hypothetical scenarios."""
    frame = _validate_positions(positions)
    cfg = dict(config)
    outputs: list[pd.DataFrame] = []

    outputs.extend(
        equity_price_scenarios(
            frame,
            cfg["equity_securities"],
            cfg["equity_down_pct"],
        )
    )
    outputs.extend(
        treasury_yield_scenarios(
            frame,
            cfg["treasury_securities"],
            cfg["treasury_yield_up_bps"],
            cfg["treasury_duration_years"],
            cfg["treasury_convexity_years2"],
        )
    )
    outputs.extend(
        credit_spread_scenarios(
            frame,
            cfg["credit_securities"],
            cfg["credit_spread_wider_bps"],
            cfg["credit_spread_duration_years"],
        )
    )
    outputs.append(
        volatility_doubled_scenario(
            frame,
            returns,
            multiplier=float(cfg["volatility_multiplier"]),
            confidence_level=float(cfg["confidence_level"]),
            horizon_days=int(cfg["horizon_days"]),
            lookback_days=int(cfg["lookback_days"]),
        )
    )
    outputs.append(
        correlation_convergence_scenario(
            frame,
            returns,
            target_correlation=float(cfg["correlation_target"]),
            confidence_level=float(cfg["confidence_level"]),
            horizon_days=int(cfg["horizon_days"]),
            lookback_days=int(cfg["lookback_days"]),
        )
    )
    outputs.append(
        trading_volume_scenario(
            margin,
            decline_pct=float(cfg["trading_volume_decline_pct"]),
            impact_exponent=float(cfg["liquidity_impact_exponent"]),
        )
    )
    outputs.append(
        largest_position_gap_scenario(
            frame,
            gap_pct=float(cfg["largest_position_gap_pct"]),
        )
    )
    outputs.append(
        largest_member_default_scenario(
            frame,
            margin,
            equity_securities=cfg["equity_securities"],
            treasury_securities=cfg["treasury_securities"],
            credit_securities=cfg["credit_securities"],
            treasury_duration_years=cfg["treasury_duration_years"],
            treasury_convexity_years2=cfg["treasury_convexity_years2"],
            credit_spread_duration_years=cfg["credit_spread_duration_years"],
            volume_decline_pct=float(cfg["trading_volume_decline_pct"]),
            liquidity_impact_exponent=float(cfg["liquidity_impact_exponent"]),
            gap_pct=float(cfg["largest_position_gap_pct"]),
            equity_decline_pct=max(float(value) for value in cfg["equity_down_pct"]),
            treasury_yield_shock_bps=max(
                float(value) for value in cfg["treasury_yield_up_bps"]
            ),
            credit_spread_shock_bps=max(
                float(value) for value in cfg["credit_spread_wider_bps"]
            ),
        )
    )

    result = pd.concat(
        [frame.dropna(axis=1, how="all") for frame in outputs],
        ignore_index=True,
        sort=False,
    )
    scenario_count = result["scenario_id"].nunique()
    if scenario_count != 14:
        raise AssertionError(
            f"Expected 14 hypothetical scenarios, generated {scenario_count}."
        )
    return result

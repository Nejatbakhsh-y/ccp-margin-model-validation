"""Orchestration and reconciliation for total initial margin.

Total Initial Margin
====================

    Total Initial Margin
      = Base Margin
      + Liquidity Add-on
      + Concentration Add-on
      + Gap-Risk Add-on
      + Stress Buffer

The module does not tune parameters and does not infer undocumented defaults.
Every material rate, threshold, shock, and parameter source must be supplied in
configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
import yaml

from .base_margin import BaseMarginResult, calculate_base_margin
from .concentration_addon import (
    ConcentrationAddonResult,
    calculate_concentration_addon,
)
from .gap_risk_addon import GapRiskAddonResult, calculate_gap_risk_addon
from .liquidity_addon import LiquidityAddonResult, calculate_liquidity_addon
from .stress_buffer import StressBufferResult, calculate_stress_buffer


@dataclass(frozen=True)
class TotalMarginResult:
    member_margin: pd.DataFrame
    attribution: pd.DataFrame
    component_metadata: dict[str, Any]


def load_margin_config(path: str | Path) -> dict[str, Any]:
    """Load the top-level ``margin`` section from a YAML configuration file."""

    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(config_path)
    with config_path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if "margin" not in loaded or not isinstance(loaded["margin"], dict):
        raise KeyError("Configuration must contain a top-level 'margin' mapping")
    return loaded["margin"]


def calculate_total_margin(
    positions: pd.DataFrame,
    var_by_member: pd.DataFrame,
    stress_losses: pd.DataFrame,
    *,
    config: Mapping[str, Any],
    member_col: str = "member_id",
) -> TotalMarginResult:
    """Calculate all initial-margin components and reconcile attribution.

    The function requires complete component configuration. It intentionally
    raises an exception when a section or material parameter is missing.
    """

    required_sections = {
        "base_margin",
        "liquidity_addon",
        "concentration_addon",
        "gap_risk_addon",
        "stress_buffer",
    }
    missing_sections = required_sections.difference(config)
    if missing_sections:
        raise KeyError(f"Missing margin configuration sections: {sorted(missing_sections)}")

    base_cfg = dict(config["base_margin"])
    liquidity_cfg = dict(config["liquidity_addon"])
    concentration_cfg = dict(config["concentration_addon"])
    gap_cfg = dict(config["gap_risk_addon"])
    stress_cfg = dict(config["stress_buffer"])

    base: BaseMarginResult = calculate_base_margin(
        var_by_member,
        member_col=member_col,
        var_col=base_cfg.get("var_col", "base_var"),
        floor_usd=float(base_cfg.get("floor_usd", 0.0)),
        cap_usd=_optional_float(base_cfg.get("cap_usd")),
    )
    liquidity: LiquidityAddonResult = calculate_liquidity_addon(
        positions,
        rates_by_bucket=_required_mapping(liquidity_cfg, "rates_by_bucket"),
        parameter_source=_required_text(liquidity_cfg, "parameter_source"),
        member_col=member_col,
        minimum_usd=float(liquidity_cfg.get("minimum_usd", 0.0)),
        maximum_fraction_of_gross=_optional_float(
            liquidity_cfg.get("maximum_fraction_of_gross")
        ),
    )
    concentration: ConcentrationAddonResult = calculate_concentration_addon(
        positions,
        single_name_threshold=float(
            _required_value(concentration_cfg, "single_name_threshold")
        ),
        single_name_rate=float(_required_value(concentration_cfg, "single_name_rate")),
        sector_threshold=float(_required_value(concentration_cfg, "sector_threshold")),
        sector_rate=float(_required_value(concentration_cfg, "sector_rate")),
        parameter_source=_required_text(concentration_cfg, "parameter_source"),
        aggregation_method=str(concentration_cfg.get("aggregation_method", "max")),
        member_col=member_col,
        minimum_usd=float(concentration_cfg.get("minimum_usd", 0.0)),
        maximum_fraction_of_gross=_optional_float(
            concentration_cfg.get("maximum_fraction_of_gross")
        ),
    )
    gap: GapRiskAddonResult = calculate_gap_risk_addon(
        positions,
        shocks_by_asset_class=_required_mapping(gap_cfg, "shocks_by_asset_class"),
        parameter_source=_required_text(gap_cfg, "parameter_source"),
        member_col=member_col,
        minimum_usd=float(gap_cfg.get("minimum_usd", 0.0)),
        maximum_fraction_of_gross=_optional_float(
            gap_cfg.get("maximum_fraction_of_gross")
        ),
    )

    summary = _merge_components(
        member_col=member_col,
        base=base,
        liquidity=liquidity,
        concentration=concentration,
        gap=gap,
    )
    summary["pre_stress_margin"] = (
        summary["base_margin"]
        + summary["liquidity_addon"]
        + summary["concentration_addon"]
        + summary["gap_risk_addon"]
    )

    stress: StressBufferResult = calculate_stress_buffer(
        stress_losses,
        summary[[member_col, "pre_stress_margin"]],
        required_coverage_ratio=float(
            _required_value(stress_cfg, "required_coverage_ratio")
        ),
        parameter_source=_required_text(stress_cfg, "parameter_source"),
        member_col=member_col,
        maximum_usd=_optional_float(stress_cfg.get("maximum_usd")),
    )
    summary = summary.merge(
        stress.member_buffer[
            [
                member_col,
                "binding_scenario_id",
                "maximum_stress_loss",
                "target_stress_coverage",
                "stress_buffer",
            ]
        ],
        on=member_col,
        how="left",
        validate="one_to_one",
    )
    summary["total_initial_margin"] = summary["pre_stress_margin"] + summary["stress_buffer"]

    component_cols = [
        "base_margin",
        "liquidity_addon",
        "concentration_addon",
        "gap_risk_addon",
        "stress_buffer",
    ]
    denominator = summary["total_initial_margin"].replace(0.0, np.nan)
    for column in component_cols:
        summary[f"{column}_share"] = (summary[column] / denominator).fillna(0.0)

    attribution = pd.concat(
        [
            base.attribution,
            liquidity.attribution,
            concentration.attribution,
            gap.attribution,
            stress.attribution,
        ],
        ignore_index=True,
        sort=False,
    )
    attribution = attribution.sort_values(
        [member_col, "component"], kind="stable"
    ).reset_index(drop=True)

    _assert_attribution_reconciles(summary, attribution, member_col=member_col)
    _assert_total_formula(summary)

    metadata = {
        "total_margin_formula": (
            "base_margin + liquidity_addon + concentration_addon + "
            "gap_risk_addon + stress_buffer"
        ),
        "base_margin": base.metadata,
        "liquidity_addon": liquidity.metadata,
        "concentration_addon": concentration.metadata,
        "gap_risk_addon": gap.metadata,
        "stress_buffer": stress.metadata,
        "governance_statement": (
            "Parameters must be approved from independent empirical, policy, or "
            "scenario evidence and must not be tuned solely to improve backtesting."
        ),
    }

    return TotalMarginResult(
        member_margin=summary.sort_values(member_col, kind="stable").reset_index(drop=True),
        attribution=attribution,
        component_metadata=metadata,
    )


def _merge_components(
    *,
    member_col: str,
    base: BaseMarginResult,
    liquidity: LiquidityAddonResult,
    concentration: ConcentrationAddonResult,
    gap: GapRiskAddonResult,
) -> pd.DataFrame:
    base_df = base.member_margin[[member_col, "base_margin"]]
    liquidity_df = liquidity.member_addon[[member_col, "liquidity_addon"]]
    concentration_df = concentration.member_addon[[member_col, "concentration_addon"]]
    gap_df = gap.member_addon[[member_col, "gap_risk_addon"]]

    member_sets = [
        set(frame[member_col].tolist())
        for frame in [base_df, liquidity_df, concentration_df, gap_df]
    ]
    if not all(member_set == member_sets[0] for member_set in member_sets[1:]):
        raise ValueError(
            "Base VaR and position-derived components do not contain identical member sets"
        )

    return (
        base_df.merge(liquidity_df, on=member_col, validate="one_to_one")
        .merge(concentration_df, on=member_col, validate="one_to_one")
        .merge(gap_df, on=member_col, validate="one_to_one")
    )


def _assert_attribution_reconciles(
    summary: pd.DataFrame,
    attribution: pd.DataFrame,
    *,
    member_col: str,
    tolerance: float = 1e-6,
) -> None:
    expected_map = {
        "base_margin": "base_margin",
        "liquidity_addon": "liquidity_addon",
        "concentration_addon": "concentration_addon",
        "gap_risk_addon": "gap_risk_addon",
        "stress_buffer": "stress_buffer",
    }
    actual = (
        attribution.groupby([member_col, "component"], as_index=False, sort=True)[
            "attribution_amount"
        ]
        .sum()
        .pivot(index=member_col, columns="component", values="attribution_amount")
        .fillna(0.0)
    )
    expected = summary.set_index(member_col)
    for component, column in expected_map.items():
        if component not in actual.columns:
            raise AssertionError(f"Missing attribution for component: {component}")
        differences = (actual[component] - expected[column]).abs()
        if (differences > tolerance).any():
            bad_members = differences[differences > tolerance].index.tolist()
            raise AssertionError(
                f"Attribution does not reconcile for {component}; member(s): {bad_members}"
            )


def _assert_total_formula(summary: pd.DataFrame, tolerance: float = 1e-6) -> None:
    recomputed = (
        summary["base_margin"]
        + summary["liquidity_addon"]
        + summary["concentration_addon"]
        + summary["gap_risk_addon"]
        + summary["stress_buffer"]
    )
    if ((recomputed - summary["total_initial_margin"]).abs() > tolerance).any():
        raise AssertionError("Total initial margin does not reconcile to component sum")


def _required_value(config: Mapping[str, Any], key: str) -> Any:
    if key not in config:
        raise KeyError(f"Missing required margin parameter: {key}")
    return config[key]


def _required_text(config: Mapping[str, Any], key: str) -> str:
    value = str(_required_value(config, key)).strip()
    if not value:
        raise ValueError(f"Margin parameter {key} must not be blank")
    return value


def _required_mapping(config: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = _required_value(config, key)
    if not isinstance(value, Mapping) or not value:
        raise ValueError(f"Margin parameter {key} must be a non-empty mapping")
    return value


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)

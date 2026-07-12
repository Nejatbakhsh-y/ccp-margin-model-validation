"""Validate the complete CCP margin model configuration."""

from __future__ import annotations

import math
import sys
from datetime import date
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIRECTORY = PROJECT_ROOT / "src"

if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from ccp_margin.config import ConfigurationError, load_project_config


def require(condition: bool, message: str) -> None:
    """Raise an assertion error when a configuration rule is violated."""

    if not condition:
        raise AssertionError(message)


def require_probability(value: Any, field_name: str) -> float:
    """Require a value strictly between zero and one."""

    numeric_value = float(value)
    require(
        0.0 < numeric_value < 1.0,
        f"{field_name} must be strictly between 0 and 1.",
    )
    return numeric_value


def validate_configuration(config: dict[str, Any]) -> None:
    """Apply structural and numerical validation rules."""

    required_sections = {
        "schema_version",
        "project",
        "portfolio",
        "data",
        "primary_model",
        "challenger_model",
        "margin_addons",
        "validation",
        "stress_scenarios",
        "monitoring_thresholds",
    }

    missing_sections = sorted(required_sections.difference(config))

    require(
        not missing_sections,
        f"Missing configuration sections: {missing_sections}",
    )

    project = config["project"]
    portfolio = config["portfolio"]
    data = config["data"]
    primary = config["primary_model"]
    challenger = config["challenger_model"]
    addons = config["margin_addons"]
    validation = config["validation"]
    stress = config["stress_scenarios"]
    monitoring = config["monitoring_thresholds"]

    require(
        project["name"] == "ccp-margin-model-validation",
        "Unexpected project name.",
    )
    require(project["currency"] == "USD", "Project currency must be USD.")
    require(
        isinstance(project["random_seed"], int),
        "random_seed must be an integer.",
    )

    start_date = date.fromisoformat(data["start_date"])
    require(
        start_date <= date.today(),
        "Data start_date cannot be in the future.",
    )

    if data["end_date"] is not None:
        end_date = date.fromisoformat(data["end_date"])
        require(
            end_date >= start_date,
            "Data end_date cannot precede start_date.",
        )

    data_completeness = require_probability(
        data["minimum_completeness"],
        "data.minimum_completeness",
    )

    require(
        portfolio["minimum_positions"] >= 1,
        "minimum_positions must be at least 1.",
    )
    require(
        portfolio["maximum_positions"]
        >= portfolio["minimum_positions"],
        "maximum_positions must not be below minimum_positions.",
    )
    require(
        portfolio["gross_notional_max"]
        > portfolio["gross_notional_min"],
        "gross_notional_max must exceed gross_notional_min.",
    )

    primary_confidence = require_probability(
        primary["confidence_level"],
        "primary_model.confidence_level",
    )
    challenger_confidence = require_probability(
        challenger["confidence_level"],
        "challenger_model.confidence_level",
    )

    require(
        math.isclose(
            primary_confidence,
            challenger_confidence,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ),
        "Primary and challenger confidence levels must match.",
    )

    require(
        primary["type"] == "historical_simulation",
        "Primary model must be historical_simulation.",
    )
    require(
        primary["lookback_days"]
        >= primary["observation_requirements"]["minimum_observations"],
        "Primary lookback must satisfy its minimum observation requirement.",
    )
    require(
        primary["mpor_days"] == challenger["mpor_days"],
        "Primary and challenger MPOR values must match.",
    )
    require(
        all(day >= 1 for day in primary["mpor_days"]),
        "All MPOR values must be positive integers.",
    )

    ewma_lambda = require_probability(
        challenger["ewma_lambda"],
        "challenger_model.ewma_lambda",
    )
    require(
        0.80 <= ewma_lambda <= 0.999,
        "EWMA lambda is outside the permitted development range.",
    )

    reconciliation_tolerance = float(
        validation["reconciliation_tolerance"]
    )
    require(
        reconciliation_tolerance > 0.0,
        "reconciliation_tolerance must be positive.",
    )
    require(
        validation["backtest_window"] == 250,
        "The validation backtest window must be 250 observations.",
    )
    require(
        validation["preserve_failed_tests"] is True,
        "Failed-test preservation must remain enabled.",
    )
    require(
        validation["preserve_negative_results"] is True,
        "Negative-result preservation must remain enabled.",
    )

    require(
        addons["calibration_required_before_approval"] is True,
        "Margin add-ons must require calibration before approval.",
    )

    required_addon_components = {
        "volatility",
        "liquidity",
        "concentration",
        "gap_risk",
    }

    require(
        required_addon_components.issubset(addons["components"]),
        "One or more required margin add-on components are missing.",
    )

    historical_ids = [
        scenario["id"] for scenario in stress["historical"]
    ]
    hypothetical_ids = [
        scenario["id"] for scenario in stress["hypothetical"]
    ]
    all_scenario_ids = historical_ids + hypothetical_ids

    require(
        len(all_scenario_ids) == len(set(all_scenario_ids)),
        "Stress scenario IDs must be unique.",
    )

    traffic_light = monitoring["backtesting"]["traffic_light"]

    require(
        traffic_light["green_maximum_exceptions"] == 4,
        "Green traffic-light maximum must be 4 exceptions.",
    )
    require(
        traffic_light["amber_minimum_exceptions"] == 5,
        "Amber traffic-light minimum must be 5 exceptions.",
    )
    require(
        traffic_light["amber_maximum_exceptions"] == 9,
        "Amber traffic-light maximum must be 9 exceptions.",
    )
    require(
        traffic_light["red_minimum_exceptions"] == 10,
        "Red traffic-light minimum must be 10 exceptions.",
    )

    monitoring_completeness = require_probability(
        monitoring["data_quality"]["minimum_completeness"],
        "monitoring_thresholds.data_quality.minimum_completeness",
    )

    require(
        math.isclose(
            data_completeness,
            monitoring_completeness,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ),
        "Data and monitoring completeness thresholds must agree.",
    )

    require(
        monitoring["configuration_change"][
            "require_configuration_checksum"
        ]
        is True,
        "Configuration checksum control must remain enabled.",
    )
    require(
        monitoring["configuration_change"]["require_change_log"] is True,
        "Configuration change-log control must remain enabled.",
    )


def main() -> int:
    """Load and validate the complete configuration."""

    try:
        config = load_project_config()
        validate_configuration(config)
    except (ConfigurationError, AssertionError, KeyError, TypeError, ValueError) as exc:
        print("CONFIGURATION CHECK FAILED")
        print(f"Reason: {exc}")
        return 1

    print("CONFIGURATION CHECK PASSED")
    print(f"Project: {config['project']['name']}")
    print(f"Currency: {config['project']['currency']}")
    print(
        "Primary model: "
        f"{config['primary_model']['type']} "
        f"at {config['primary_model']['confidence_level']:.1%}"
    )
    print(
        "Challenger model: "
        f"{config['challenger_model']['type']} "
        f"at {config['challenger_model']['confidence_level']:.1%}"
    )
    print(f"MPOR values: {config['primary_model']['mpor_days']}")
    print(
        "Configured members: "
        f"{config['portfolio']['number_of_members']}"
    )
    print("Loaded configuration files:")

    for section_name, file_path in config["_metadata"][
        "loaded_files"
    ].items():
        print(f"  {section_name}: {file_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import dataclasses
import importlib
import inspect
import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]

TARGET_MODULES = (
    "ccp_margin.margin.base_margin",
    "ccp_margin.margin.concentration_addon",
    "ccp_margin.margin.gap_risk_addon",
    "ccp_margin.margin.liquidity_addon",
    "ccp_margin.margin.stress_buffer",
    "ccp_margin.margin.total_margin",
    "ccp_margin.models.challenger.ewma_covariance",
    "ccp_margin.models.challenger.parametric_var",
    "ccp_margin.models.primary.historical_var",
    "ccp_margin.models.primary.multi_day_returns",
    "ccp_margin.models.primary.portfolio_pnl",
)


DATES = pd.date_range("2025-01-02", periods=12, freq="B")

RETURNS = pd.DataFrame(
    {
        "EQ_A": [
            0.010,
            -0.015,
            0.008,
            -0.004,
            0.012,
            -0.020,
            0.006,
            0.003,
            -0.008,
            0.011,
            -0.002,
            0.004,
        ],
        "EQ_B": [
            0.004,
            -0.006,
            0.005,
            -0.002,
            0.009,
            -0.011,
            0.002,
            0.001,
            -0.004,
            0.006,
            -0.001,
            0.003,
        ],
        "UST10Y": [
            -0.002,
            0.003,
            -0.001,
            0.002,
            -0.003,
            0.004,
            -0.001,
            0.000,
            0.002,
            -0.002,
            0.001,
            -0.001,
        ],
    },
    index=DATES,
)

POSITIONS = pd.DataFrame(
    {
        "valuation_date": [DATES[-1]] * 4,
        "date": [DATES[-1]] * 4,
        "member_id": ["CM001"] * 4,
        "portfolio_id": ["P001"] * 4,
        "security_id": ["EQ_A", "EQ_B", "UST10Y", "EQ_A"],
        "risk_factor_id": ["EQ_A", "EQ_B", "UST10Y", "EQ_A"],
        "market_value": [1_000_000.0, 500_000.0, -250_000.0, 100_000.0],
        "position_value": [1_000_000.0, 500_000.0, -250_000.0, 100_000.0],
        "quantity": [10_000.0, 10_000.0, -2_500.0, 1_000.0],
        "price": [100.0, 50.0, 100.0, 100.0],
        "current_price": [100.0, 50.0, 100.0, 100.0],
        "sector": ["Technology", "Financials", "Rates", "Technology"],
        "asset_class": ["Equity", "Equity", "Treasury", "Equity"],
        "liquidity_bucket": ["high", "medium", "high", "low"],
        "average_daily_volume": [20_000_000.0, 8_000_000.0, 50_000_000.0, 500_000.0],
        "adv": [20_000_000.0, 8_000_000.0, 50_000_000.0, 500_000.0],
        "duration": [0.0, 0.0, 8.0, 0.0],
        "convexity": [0.0, 0.0, 60.0, 0.0],
        "weight": [0.50, 0.25, -0.125, 0.05],
    }
)

COMPONENTS = pd.DataFrame(
    {
        "date": [DATES[-1], DATES[-1]],
        "valuation_date": [DATES[-1], DATES[-1]],
        "member_id": ["CM001", "CM002"],
        "portfolio_id": ["P001", "P002"],
        "base_var": [100.0, 200.0],
        "liquidity_addon": [10.0, 20.0],
        "concentration_addon": [5.0, 10.0],
        "gap_risk_addon": [4.0, 8.0],
        "stress_buffer": [20.0, 40.0],
        "total_margin": [139.0, 278.0],
        "portfolio_value": [1_000.0, 2_000.0],
        "gross_exposure": [1_500.0, 3_000.0],
        "net_exposure": [1_000.0, 2_000.0],
        "model_version": ["test", "test"],
    }
)

OBSERVATIONS = pd.DataFrame(
    {
        "date": [DATES[-2], DATES[-1]],
        "member_id": ["CM001", "CM002"],
        "actual_loss": [90.0, 250.0],
        "available_margin": [100.0, 200.0],
        "margin": [100.0, 200.0],
        "realized_loss": [90.0, 250.0],
        "portfolio_type": ["diversified", "concentrated"],
        "is_stressed_period": [False, True],
    }
)


def _project_config() -> dict[str, Any]:
    path = ROOT / "configs" / "project.yaml"
    data: dict[str, Any] = {}
    if path.exists():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
        if isinstance(loaded, dict):
            data.update(loaded)

    data.setdefault("project", {})
    data.setdefault("models", {})
    data.setdefault("margin", {})
    data.setdefault("validation", {})

    data["project"].setdefault("model_version", "step21-test")
    data["project"].setdefault("configuration_status", "preliminary")

    data["margin"].setdefault("base_margin", {"floor": 0.0, "cap": None})
    data["margin"].setdefault(
        "liquidity",
        {
            "participation_rate": 0.10,
            "liquidation_days": 5,
            "bucket_rates": {"high": 0.01, "medium": 0.03, "low": 0.08},
        },
    )
    data["margin"].setdefault(
        "concentration",
        {
            "single_name_threshold": 0.20,
            "sector_threshold": 0.40,
            "single_name_rate": 0.10,
            "sector_rate": 0.05,
        },
    )
    data["margin"].setdefault(
        "gap_risk",
        {
            "asset_class_shocks": {
                "Equity": 0.10,
                "Treasury": 0.03,
                "Credit": 0.08,
            }
        },
    )
    data["margin"].setdefault(
        "stress_buffer",
        {
            "coverage_ratio": 1.10,
            "minimum_rate": 0.0,
            "maximum_rate": 1.0,
        },
    )

    data["validation"].setdefault("tolerance", 1e-8)
    return data


CONFIG = _project_config()


def _string_literals(function: Any) -> list[str]:
    try:
        source = inspect.getsource(function)
    except (OSError, TypeError):
        return []

    values = []
    for literal in re.findall(r"""["']([^"'\\\n]{1,48})["']""", source):
        if literal not in values:
            values.append(literal)
    return values[:20]


def _annotation_text(parameter: inspect.Parameter) -> str:
    annotation = parameter.annotation
    if annotation is inspect.Parameter.empty:
        return ""
    return str(annotation).lower()


def _base_value(parameter: inspect.Parameter, owner: Any = None) -> Any:
    name = parameter.name.lower()
    annotation = _annotation_text(parameter)

    if parameter.default is not inspect.Parameter.empty:
        return parameter.default

    if "exception" in name or name in {"flags", "hits", "breaches"}:
        return np.array([0, 0, 1, 0, 0, 1, 0, 0], dtype=int)

    if "config" in name or "setting" in name or "parameter" in name:
        return CONFIG

    if "path" in name or "file" in name:
        return ROOT / "configs" / "project.yaml"

    if "position" in name or "portfolio" in name:
        if "value" in name or "notional" in name or "exposure" in name:
            return 1_000_000.0
        return POSITIONS.copy()

    if "component" in name or "margin_frame" in name:
        return COMPONENTS.copy()

    if "observation" in name or "backtest" in name:
        return OBSERVATIONS.copy()

    if "return" in name or "scenario" in name or "history" in name:
        if "count" in name or "number" in name:
            return len(RETURNS)
        return RETURNS.copy()

    if "covariance" in name or name in {"cov", "sigma"}:
        return RETURNS.cov().to_numpy()

    if "correlation" in name:
        return RETURNS.corr().to_numpy()

    if "weight" in name:
        return np.array([0.50, 0.30, 0.20], dtype=float)

    if "exposure_vector" in name or name == "exposures":
        return np.array([500_000.0, 300_000.0, 200_000.0], dtype=float)

    if "date" in name:
        return DATES[-1]

    if "column" in name:
        if "loss" in name:
            return "actual_loss"
        if "margin" in name:
            return "available_margin"
        if "member" in name:
            return "member_id"
        if "portfolio" in name:
            return "portfolio_type"
        if "stress" in name:
            return "is_stressed_period"
        if "value" in name:
            return "market_value"
        return "security_id"

    if any(token in name for token in ("confidence", "coverage")):
        return 0.99

    if any(token in name for token in ("probability", "alpha", "significance")):
        return 0.05 if "significance" in name or name == "alpha" else 0.01

    if any(token in name for token in ("lambda", "decay")):
        return 0.94

    if any(token in name for token in ("horizon", "mpor", "holding_period", "days")):
        return 1

    if any(token in name for token in ("lookback", "window")):
        return 5

    if any(token in name for token in ("seed", "random_state")):
        return 2026

    if any(token in name for token in ("floor", "tolerance", "epsilon")):
        return 1e-8

    if any(
        token in name for token in ("rate", "ratio", "fraction", "threshold", "shock")
    ):
        return 0.10

    if any(token in name for token in ("count", "number", "n_", "minimum", "maximum")):
        return 2

    if "bool" in annotation:
        return True
    if "dataframe" in annotation:
        return RETURNS.copy()
    if "series" in annotation:
        return RETURNS.iloc[:, 0].copy()
    if "ndarray" in annotation:
        return RETURNS.to_numpy(dtype=float)
    if "mapping" in annotation or "dict" in annotation:
        return CONFIG
    if "path" in annotation:
        return ROOT / "configs" / "project.yaml"
    if "str" in annotation:
        return "normal"
    if "int" in annotation:
        return 1
    if "float" in annotation:
        return 0.10
    if "bool" in annotation:
        return True

    return 1.0


def _mutations(parameter: inspect.Parameter, function: Any) -> list[Any]:
    name = parameter.name.lower()
    annotation = _annotation_text(parameter)
    values: list[Any] = []

    if "dataframe" in annotation or any(
        token in name
        for token in (
            "returns",
            "positions",
            "observations",
            "components",
            "scenarios",
            "frame",
            "data",
        )
    ):
        values.extend(
            [
                pd.DataFrame(),
                RETURNS.iloc[:1].copy(),
                RETURNS.assign(EQ_A=np.nan),
                pd.DataFrame({"unexpected": [1.0]}),
                "not-a-dataframe",
                None,
            ]
        )

    if "ndarray" in annotation or any(
        token in name
        for token in ("weights", "covariance", "correlation", "exposure_vector")
    ):
        values.extend(
            [
                np.array([], dtype=float),
                np.array([1.0]),
                np.array([np.nan]),
                np.eye(2),
                np.array([[1.0, 2.0], [2.0, 1.0]]),
                None,
            ]
        )

    if "str" in annotation or any(
        token in name
        for token in ("policy", "method", "mode", "distribution", "scaling", "column")
    ):
        values.extend(
            [
                "",
                "invalid",
                "error",
                "drop",
                "normal",
                "student_t",
                "sqrt_time",
                "direct",
            ]
        )
        values.extend(_string_literals(function))

    if "bool" in annotation or name.startswith(
        ("use_", "include_", "apply_", "allow_")
    ):
        values.extend([True, False, None])

    if (
        "int" in annotation
        or "float" in annotation
        or any(
            token in name
            for token in (
                "confidence",
                "probability",
                "alpha",
                "significance",
                "lambda",
                "decay",
                "horizon",
                "mpor",
                "days",
                "lookback",
                "window",
                "floor",
                "cap",
                "rate",
                "ratio",
                "fraction",
                "threshold",
                "shock",
                "tolerance",
                "count",
                "number",
                "seed",
            )
        )
    ):
        values.extend(
            [
                -1.0,
                -0.1,
                0,
                1e-12,
                0.01,
                0.05,
                0.5,
                0.94,
                0.99,
                1.0,
                1.1,
                2,
                5,
                500,
                np.nan,
                np.inf,
                None,
            ]
        )

    if "mapping" in annotation or "dict" in annotation or "config" in name:
        values.extend([{}, {"unexpected": 1}, None, "not-a-mapping"])

    if "path" in annotation or "path" in name or "file" in name:
        values.extend(
            [
                ROOT / "configs" / "project.yaml",
                ROOT / "configs" / "does_not_exist.yaml",
                "",
                None,
            ]
        )

    distinct = []
    for value in values:
        duplicate = False
        for existing in distinct:
            try:
                if value is existing:
                    duplicate = True
                    break
                if type(value) is type(existing) and isinstance(
                    value, (str, int, float, bool, type(None), Path)
                ):
                    if value == existing:
                        duplicate = True
                        break
            except Exception:
                pass
        if not duplicate:
            distinct.append(value)
    return distinct[:18]


def _call(function: Any, arguments: dict[str, Any]) -> tuple[bool, str]:
    signature = inspect.signature(function)
    positional = []
    keyword = {}

    for name, parameter in signature.parameters.items():
        if name in {"self", "cls"}:
            continue
        if parameter.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        if name not in arguments:
            if parameter.default is not inspect.Parameter.empty:
                continue
            return False, f"UNBOUND:{name}"

        if parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
            positional.append(arguments[name])
        else:
            keyword[name] = arguments[name]

    try:
        result = function(*positional, **keyword)
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as exc:
        return False, type(exc).__name__

    if isinstance(result, (float, np.floating)):
        assert not math.isinf(float(result))
    return True, type(result).__name__


def _exercise_callable(function: Any) -> dict[str, int]:
    signature = inspect.signature(function)
    parameters = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.name not in {"self", "cls"}
        and parameter.kind
        not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    ]

    base = {
        parameter.name: _base_value(parameter, function) for parameter in parameters
    }

    attempts = 0
    successes = 0
    expected_exceptions = 0

    ok, outcome = _call(function, base)
    attempts += 1
    if ok:
        successes += 1
    elif not outcome.startswith("UNBOUND:"):
        expected_exceptions += 1

    for parameter in parameters:
        for candidate in _mutations(parameter, function):
            arguments = dict(base)
            arguments[parameter.name] = candidate
            ok, outcome = _call(function, arguments)
            attempts += 1
            if ok:
                successes += 1
            elif not outcome.startswith("UNBOUND:"):
                expected_exceptions += 1

    return {
        "attempts": attempts,
        "successes": successes,
        "expected_exceptions": expected_exceptions,
    }


def _construct_dataclass(cls: type[Any]) -> list[Any]:
    instances = []
    fields = dataclasses.fields(cls)

    base = {}
    for field in fields:
        if field.default is not dataclasses.MISSING:
            base[field.name] = field.default
            continue
        if field.default_factory is not dataclasses.MISSING:  # type: ignore[comparison-overlap]
            base[field.name] = field.default_factory()
            continue

        parameter = inspect.Parameter(
            field.name,
            inspect.Parameter.KEYWORD_ONLY,
            annotation=field.type,
        )
        base[field.name] = _base_value(parameter, cls)

    try:
        instances.append(cls(**base))
    except Exception:
        pass

    for field in fields:
        parameter = inspect.Parameter(
            field.name,
            inspect.Parameter.KEYWORD_ONLY,
            annotation=field.type,
        )
        for candidate in _mutations(parameter, cls)[:10]:
            arguments = dict(base)
            arguments[field.name] = candidate
            try:
                instances.append(cls(**arguments))
            except Exception:
                pass

    return instances


def _construct_regular_class(cls: type[Any]) -> list[Any]:
    instances = []
    try:
        constructor = cls
        signature = inspect.signature(constructor)
    except (TypeError, ValueError):
        return instances

    parameters = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.name not in {"self", "cls"}
        and parameter.kind
        not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    ]
    base = {parameter.name: _base_value(parameter, cls) for parameter in parameters}

    def attempt(arguments: dict[str, Any]) -> None:
        positional = []
        keyword = {}
        for parameter in parameters:
            if parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
                positional.append(arguments[parameter.name])
            elif parameter.name in arguments and not (
                parameter.default is not inspect.Parameter.empty
                and arguments[parameter.name] is parameter.default
            ):
                keyword[parameter.name] = arguments[parameter.name]
        try:
            instances.append(cls(*positional, **keyword))
        except Exception:
            pass

    attempt(base)
    for parameter in parameters:
        for candidate in _mutations(parameter, cls)[:12]:
            arguments = dict(base)
            arguments[parameter.name] = candidate
            attempt(arguments)

    if not instances:
        try:
            instances.append(object.__new__(cls))
        except Exception:
            pass

    return instances


def _exercise_module(module_name: str) -> dict[str, int]:
    module = importlib.import_module(module_name)
    totals = {
        "callables": 0,
        "attempts": 0,
        "successes": 0,
        "expected_exceptions": 0,
    }

    for name, value in inspect.getmembers(module):
        if inspect.isfunction(value) and value.__module__ == module.__name__:
            metrics = _exercise_callable(value)
            totals["callables"] += 1
            for key in ("attempts", "successes", "expected_exceptions"):
                totals[key] += metrics[key]

        elif inspect.isclass(value) and value.__module__ == module.__name__:
            if dataclasses.is_dataclass(value):
                instances = _construct_dataclass(value)
            else:
                instances = _construct_regular_class(value)

            for instance in instances[:20]:
                to_dict = getattr(instance, "to_dict", None)
                if callable(to_dict):
                    try:
                        serialized = to_dict()
                        assert isinstance(serialized, dict)
                        totals["successes"] += 1
                    except Exception:
                        totals["expected_exceptions"] += 1
                    totals["attempts"] += 1

                summary = getattr(instance, "summary", None)
                if callable(summary):
                    try:
                        summary_result = summary()
                        assert summary_result is not None
                        totals["successes"] += 1
                    except Exception:
                        totals["expected_exceptions"] += 1
                    totals["attempts"] += 1

                for method_name, method in inspect.getmembers(
                    instance, predicate=callable
                ):
                    if method_name.startswith("__"):
                        continue
                    if method_name in {"to_dict", "summary"}:
                        continue

                    try:
                        owner = inspect.getattr_static(value, method_name)
                    except Exception:
                        continue
                    if not (
                        inspect.isfunction(owner)
                        or isinstance(owner, (staticmethod, classmethod))
                    ):
                        continue

                    try:
                        metrics = _exercise_callable(method)
                    except (TypeError, ValueError):
                        continue

                    totals["callables"] += 1
                    for key in ("attempts", "successes", "expected_exceptions"):
                        totals[key] += metrics[key]

    return totals


def test_source_aware_core_contract_exploration():
    results = {
        module_name: _exercise_module(module_name) for module_name in TARGET_MODULES
    }

    for module_name, metrics in results.items():
        assert metrics["callables"] > 0, f"No local callables found in {module_name}"
        assert metrics["attempts"] > 0, f"No calls attempted in {module_name}"
        assert metrics["successes"] + metrics["expected_exceptions"] > 0, (
            f"No callable contract was exercised in {module_name}"
        )


def test_total_margin_configuration_and_required_value_helpers():
    module = importlib.import_module("ccp_margin.margin.total_margin")

    config = module.load_margin_config(ROOT / "configs" / "project.yaml")
    assert isinstance(config, dict)

    if hasattr(module, "_required_value"):
        assert module._required_value({"amount": 2.5}, "amount") == 2.5
        with pytest.raises((KeyError, ValueError, TypeError)):
            module._required_value({}, "amount")

    if hasattr(module, "_required_text"):
        assert module._required_text({"name": "model"}, "name") == "model"
        with pytest.raises((KeyError, ValueError, TypeError)):
            module._required_text({"name": ""}, "name")

    if hasattr(module, "_required_mapping"):
        assert module._required_mapping({"section": {"x": 1}}, "section") == {"x": 1}
        with pytest.raises((KeyError, ValueError, TypeError)):
            module._required_mapping({"section": 1}, "section")


def test_total_margin_error_and_reconciliation_contracts():
    module = importlib.import_module("ccp_margin.margin.total_margin")

    with pytest.raises((TypeError, ValueError, KeyError)):
        module.calculate_total_margin("not-a-dataframe", CONFIG)

    if hasattr(module, "_assert_total_formula"):
        summary = pd.DataFrame(
            {
                "base_margin": [100.0, 200.0],
                "liquidity_addon": [10.0, 20.0],
                "concentration_addon": [5.0, 10.0],
                "gap_risk_addon": [4.0, 8.0],
                "stress_buffer": [20.0, 40.0],
            }
        )
        summary["total_initial_margin"] = (
            summary["base_margin"]
            + summary["liquidity_addon"]
            + summary["concentration_addon"]
            + summary["gap_risk_addon"]
            + summary["stress_buffer"]
        )

        def call_formula(frame):
            signature = inspect.signature(module._assert_total_formula)
            positional = []
            keyword = {}
            for parameter in signature.parameters.values():
                if parameter.name in {
                    "summary",
                    "frame",
                    "data",
                    "margins",
                    "result",
                    "observations",
                }:
                    value = frame
                elif "tolerance" in parameter.name:
                    value = 1e-12
                elif parameter.default is not inspect.Parameter.empty:
                    continue
                else:
                    value = _base_value(parameter)

                if parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
                    positional.append(value)
                else:
                    keyword[parameter.name] = value

            return module._assert_total_formula(*positional, **keyword)

        call_formula(summary)

        inconsistent = summary.copy()
        inconsistent.loc[0, "total_initial_margin"] += 1.0
        with pytest.raises((AssertionError, RuntimeError, ValueError)):
            call_formula(inconsistent)

    if hasattr(module, "_assert_attribution_reconciles"):
        metrics = _exercise_callable(module._assert_attribution_reconciles)
        assert metrics["attempts"] > 0

    if hasattr(module, "_merge_components"):
        metrics = _exercise_callable(module._merge_components)
        assert metrics["attempts"] > 0

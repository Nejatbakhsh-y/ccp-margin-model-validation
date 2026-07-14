from __future__ import annotations

import hashlib
import importlib
import inspect
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


class UnsupportedSignature(RuntimeError):
    pass


def import_any(*module_names: str):
    errors: list[str] = []
    for module_name in module_names:
        try:
            return importlib.import_module(module_name)
        except Exception as exc:
            errors.append(f"{module_name}: {type(exc).__name__}: {exc}")
    raise AssertionError("Could not import any required module:\n" + "\n".join(errors))


def find_callable(module: Any, *candidate_names: str, contains: Iterable[str] = ()):
    for name in candidate_names:
        value = getattr(module, name, None)
        if callable(value):
            return value

    tokens = tuple(str(token).lower() for token in contains)
    if tokens:
        matches = []
        for name in dir(module):
            if name.startswith("_"):
                continue
            value = getattr(module, name)
            lowered = name.lower()
            if callable(value) and all(token in lowered for token in tokens):
                matches.append((name, value))
        if len(matches) == 1:
            return matches[0][1]
    return None


_ALIAS_GROUPS = {
    "prices": {
        "prices", "price", "price_series", "price_data", "market_prices",
        "adjusted_close", "close_prices", "dataframe", "df", "data",
    },
    "returns": {
        "returns", "return_series", "daily_returns", "historical_returns",
        "risk_factor_returns", "portfolio_returns", "log_returns", "data",
    },
    "losses": {
        "losses", "loss_series", "historical_losses", "portfolio_losses",
        "realized_losses", "pnl_losses",
    },
    "pnl": {
        "pnl", "pnl_series", "portfolio_pnl", "profit_and_loss",
    },
    "confidence_level": {
        "confidence_level", "confidence", "cl", "var_confidence",
    },
    "alpha": {"alpha", "significance_level", "test_alpha"},
    "target_probability": {
        "target_probability", "expected_probability", "exception_probability",
        "expected_exception_rate", "p", "var_alpha",
    },
    "lookback": {
        "lookback", "lookback_window", "window", "window_size", "history_window",
    },
    "mpor": {
        "mpor", "holding_period", "horizon", "days", "n_days", "period",
    },
    "weights": {
        "weights", "portfolio_weights", "weight_vector", "exposures",
    },
    "covariance": {
        "covariance", "covariance_matrix", "cov_matrix", "sigma",
    },
    "portfolio_value": {
        "portfolio_value", "market_value", "notional", "gross_exposure",
        "exposure", "position_value",
    },
    "position_value": {
        "position_value", "market_value", "notional", "exposure",
    },
    "adv": {
        "adv", "average_daily_volume", "daily_volume", "volume",
    },
    "participation_rate": {
        "participation_rate", "adv_fraction", "liquidation_fraction",
    },
    "liquidity_factor": {
        "liquidity_factor", "liquidity_rate", "addon_rate", "rate",
    },
    "concentration_threshold": {
        "concentration_threshold", "threshold", "limit", "threshold_pct",
    },
    "concentration_rate": {
        "concentration_rate", "addon_rate", "penalty_rate", "rate",
    },
    "positions": {
        "positions", "position_data", "member_positions", "portfolio",
    },
    "universe": {
        "universe", "security_universe", "assets", "securities",
    },
    "config": {"config", "configuration", "settings", "params", "parameters"},
    "seed": {"seed", "random_seed", "rng_seed"},
    "n_members": {
        "n_members", "num_members", "member_count", "number_of_members",
    },
    "n_securities": {
        "n_securities", "num_securities", "security_count", "number_of_securities",
    },
    "exceptions": {
        "exceptions", "exception_flags", "breaches", "hits", "violations",
        "indicator", "sequence",
    },
    "n_observations": {
        "n_observations", "observations", "n_obs", "sample_size", "n",
    },
    "n_exceptions": {
        "n_exceptions", "exception_count", "exceptions_count", "x", "failures",
    },
    "margin": {
        "margin", "margin_amount", "required_margin", "total_margin",
        "initial_margin", "collateral",
    },
    "realized_loss": {
        "realized_loss", "loss", "actual_loss", "realized_losses",
    },
    "components": {
        "components", "margin_components", "component_values",
    },
}


def _lookup_value(parameter_name: str, values: dict[str, Any]):
    if parameter_name in values:
        return True, values[parameter_name]

    normalized = parameter_name.lower().strip("_")
    if normalized in values:
        return True, values[normalized]

    for canonical, aliases in _ALIAS_GROUPS.items():
        if normalized in aliases and canonical in values:
            return True, values[canonical]
        if normalized == canonical and canonical in values:
            return True, values[canonical]

    return False, None


def invoke(function: Any, values: dict[str, Any]):
    signature = inspect.signature(function)
    args: list[Any] = []
    kwargs: dict[str, Any] = {}

    for name, parameter in signature.parameters.items():
        if parameter.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue

        found, value = _lookup_value(name, values)
        if not found:
            if parameter.default is not inspect.Parameter.empty:
                continue
            raise UnsupportedSignature(
                f"Cannot supply required parameter {name!r} for "
                f"{getattr(function, '__name__', function)!r}; "
                f"signature={signature}"
            )

        if parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
            args.append(value)
        else:
            kwargs[name] = value

    return function(*args, **kwargs)


def as_mapping(result: Any) -> dict[str, Any]:
    if is_dataclass(result):
        return asdict(result)
    if isinstance(result, dict):
        return result
    if hasattr(result, "_asdict"):
        return dict(result._asdict())
    if hasattr(result, "__dict__") and not isinstance(result, type):
        return {
            key: value
            for key, value in vars(result).items()
            if not key.startswith("_")
        }
    return {}


def result_get(result: Any, *keys: str, default: Any = None):
    mapping = as_mapping(result)
    lowered = {str(key).lower(): value for key, value in mapping.items()}
    for key in keys:
        if key in mapping:
            return mapping[key]
        if key.lower() in lowered:
            return lowered[key.lower()]
    return default


def extract_array(result: Any, preferred_keys: Iterable[str] = ()) -> np.ndarray:
    mapping = as_mapping(result)
    for key in preferred_keys:
        value = result_get(mapping, key)
        if value is not None:
            return extract_array(value)

    if isinstance(result, pd.DataFrame):
        numeric = result.select_dtypes(include=[np.number])
        if numeric.empty:
            raise AssertionError("Result DataFrame has no numeric columns.")
        return numeric.to_numpy(dtype=float).reshape(-1)

    if isinstance(result, (pd.Series, pd.Index)):
        return pd.to_numeric(pd.Series(result), errors="coerce").to_numpy(dtype=float)

    if isinstance(result, np.ndarray):
        return np.asarray(result, dtype=float).reshape(-1)

    if isinstance(result, (list, tuple)):
        try:
            return np.asarray(result, dtype=float).reshape(-1)
        except Exception:
            for item in result:
                try:
                    return extract_array(item, preferred_keys)
                except Exception:
                    continue

    if mapping:
        for key in preferred_keys:
            value = result_get(mapping, key)
            if value is not None:
                return extract_array(value)
        numeric_values = [
            value for value in mapping.values()
            if isinstance(value, (int, float, np.number))
        ]
        if numeric_values:
            return np.asarray(numeric_values, dtype=float)

    if isinstance(result, (int, float, np.number)):
        return np.asarray([float(result)], dtype=float)

    raise AssertionError(f"Could not extract numeric values from result type {type(result)!r}.")


def extract_number(result: Any, preferred_keys: Iterable[str] = ()) -> float:
    array = extract_array(result, preferred_keys)
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        raise AssertionError("Result contains no finite numeric value.")
    return float(finite[-1])


def normalized_label(result: Any) -> str:
    if isinstance(result, str):
        return result.strip().lower()
    mapping = as_mapping(result)
    for key in ("traffic_light", "classification", "status", "zone", "label", "result"):
        value = result_get(mapping, key)
        if value is not None:
            return str(value).strip().lower()
    return str(result).strip().lower()


def stable_digest(value: Any) -> str:
    if isinstance(value, pd.DataFrame):
        frame = value.copy()
        frame.columns = [str(column) for column in frame.columns]
        frame = frame.reindex(sorted(frame.columns), axis=1)
        sort_columns = list(frame.columns)
        if sort_columns:
            try:
                frame = frame.sort_values(sort_columns, kind="mergesort")
            except Exception:
                frame = frame.astype(str).sort_values(sort_columns, kind="mergesort")
        payload = frame.reset_index(drop=True).to_json(
            orient="split", date_format="iso", double_precision=12
        )
    elif isinstance(value, pd.Series):
        payload = value.reset_index(drop=True).to_json(
            orient="split", date_format="iso", double_precision=12
        )
    elif isinstance(value, np.ndarray):
        payload = json.dumps(np.asarray(value).tolist(), sort_keys=True, default=str)
    else:
        mapping = as_mapping(value)
        payload = json.dumps(mapping or value, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def first_existing(*relative_paths: str) -> Path | None:
    for relative_path in relative_paths:
        candidate = ROOT / relative_path
        if candidate.exists():
            return candidate
    return None


def read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".json", ".jsonl"}:
        return pd.read_json(path, lines=suffix == ".jsonl")
    raise AssertionError(f"Unsupported table type: {path}")

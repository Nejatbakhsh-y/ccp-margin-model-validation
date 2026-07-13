from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "15_generate_sensitivity_results.py"

spec = importlib.util.spec_from_file_location(
    "step15_generate_sensitivity_results",
    SCRIPT_PATH,
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_selects_final_250_eligible_dates() -> None:
    dates = pd.bdate_range("2020-01-01", periods=1300)
    selected = module.select_test_dates(
        dates,
        maximum_lookback=1000,
        maximum_forward_mpor=5,
        count=250,
    )

    assert len(selected) == 250
    assert dates.get_loc(selected[0]) >= 1000
    assert len(dates) - 1 - dates.get_loc(selected[-1]) == 5


def test_correlation_shocks_preserve_variances_and_psd() -> None:
    rng = np.random.default_rng(2026)
    returns = rng.normal(0.0, 0.01, size=(500, 4))
    covariance = module.ewma_covariance(returns, 0.94)

    for shock in ("current", "plus_25_percent", "near_one"):
        shocked = module.apply_correlation_shock(covariance, shock)
        assert np.allclose(np.diag(shocked), np.diag(covariance))
        assert np.linalg.eigvalsh(shocked).min() >= -1e-8
        assert np.allclose(shocked, shocked.T)


def test_overlapping_and_forward_compounding() -> None:
    daily = np.array(
        [
            [0.10, 0.00],
            [0.10, 0.20],
            [-0.10, 0.00],
        ]
    )
    compounded = module.overlapping_compounded_returns(daily, 2)

    expected = np.array(
        [
            [0.21, 0.20],
            [-0.01, 0.20],
        ]
    )
    assert np.allclose(compounded, expected)

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml


REQUIRED = {
    "date",
    "member_id",
    "base_var",
    "liquidity_addon",
    "concentration_addon",
    "gap_risk_addon",
    "stress_buffer",
    "total_margin",
    "portfolio_value",
    "gross_exposure",
    "net_exposure",
    "model_version",
}


def _run(repo: Path, script: str) -> None:
    subprocess.run(
        [sys.executable, str(repo / "scripts" / script)],
        cwd=repo,
        check=True,
    )


def test_step13_end_to_end(tmp_path: Path) -> None:
    repo = tmp_path
    (repo / "scripts").mkdir()
    (repo / "configs").mkdir()
    (repo / "data" / "processed").mkdir(parents=True)
    (repo / "data" / "synthetic").mkdir(parents=True)

    source_scripts = Path(__file__).resolve().parents[1] / "scripts"
    for name in (
        "_daily_margin_common.py",
        "06_run_primary_model.py",
        "07_run_challenger_model.py",
        "08_calculate_margin_addons.py",
        "09_run_daily_member_margin.py",
    ):
        (repo / "scripts" / name).write_text(
            (source_scripts / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    config = {
        "project": {
            "name": "ccp-margin-model-validation",
            "configuration_status": "preliminary",
            "model_version": "test-v1",
        },
        "primary_model": {
            "confidence_level": 0.99,
            "lookback_days": 40,
            "mpor_days": [1, 3],
            "missing_risk_factor_policy": "raise",
        },
        "challenger_model": {
            "confidence_level": 0.99,
            "lookback_days": 40,
            "ewma_lambda": 0.94,
            "include_mean": False,
            "mpor_days": [1, 3],
            "missing_risk_factor_policy": "raise",
            "covariance_controls": {"eigenvalue_floor": 1.0e-12},
        },
        "margin": {
            "base_margin": {"floor_usd": 0.0, "cap_usd": None},
            "liquidity_addon": {
                "rates_by_bucket": {
                    "high": 0.001,
                    "medium": 0.003,
                    "low": 0.010,
                    "stressed": 0.025,
                },
                "minimum_usd": 0.0,
                "maximum_fraction_of_gross": 0.05,
            },
            "concentration_addon": {
                "single_name_threshold": 0.20,
                "single_name_rate": 0.10,
                "sector_threshold": 0.40,
                "sector_rate": 0.05,
                "aggregation_method": "max",
                "minimum_usd": 0.0,
                "maximum_fraction_of_gross": 0.10,
            },
            "gap_risk_addon": {
                "rates_by_asset_class": {
                    "equity": 0.080,
                    "rates": 0.025,
                    "credit": 0.050,
                },
                "minimum_usd": 0.0,
                "maximum_fraction_of_gross": 0.20,
            },
            "stress_buffer": {
                "required_coverage_ratio": 1.0,
                "maximum_buffer_usd": None,
            },
        },
    }
    (repo / "configs" / "project.yaml").write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
    )

    rng = np.random.default_rng(2026)
    dates = pd.bdate_range("2025-01-01", periods=70)
    returns = pd.DataFrame(
        rng.normal(0.0002, 0.012, size=(len(dates), 3)),
        index=dates,
        columns=["SPY", "TLT", "LQD"],
    )
    returns.to_parquet(repo / "data" / "processed" / "returns_wide.parquet")

    positions = pd.DataFrame(
        [
            {
                "valuation_date": dates[-1],
                "member_id": "M001",
                "portfolio_id": "P001",
                "security_id": "SPY",
                "market_value": 600_000.0,
                "sector": "equity",
                "asset_class": "equity",
                "liquidity_bucket": "high",
            },
            {
                "valuation_date": dates[-1],
                "member_id": "M001",
                "portfolio_id": "P001",
                "security_id": "TLT",
                "market_value": 400_000.0,
                "sector": "rates",
                "asset_class": "rates",
                "liquidity_bucket": "medium",
            },
            {
                "valuation_date": dates[-1],
                "member_id": "M002",
                "portfolio_id": "P002",
                "security_id": "SPY",
                "market_value": 800_000.0,
                "sector": "equity",
                "asset_class": "equity",
                "liquidity_bucket": "low",
            },
            {
                "valuation_date": dates[-1],
                "member_id": "M002",
                "portfolio_id": "P002",
                "security_id": "LQD",
                "market_value": -200_000.0,
                "sector": "credit",
                "asset_class": "credit",
                "liquidity_bucket": "medium",
            },
        ]
    )
    positions.to_csv(repo / "data" / "synthetic" / "member_positions.csv", index=False)

    _run(repo, "06_run_primary_model.py")
    _run(repo, "07_run_challenger_model.py")
    _run(repo, "08_calculate_margin_addons.py")
    _run(repo, "09_run_daily_member_margin.py")

    output = repo / "data" / "processed" / "daily_member_margin.parquet"
    result = pd.read_parquet(output)

    assert len(result) == 2
    assert REQUIRED.issubset(result.columns)
    expected_total = result[
        [
            "base_var",
            "liquidity_addon",
            "concentration_addon",
            "gap_risk_addon",
            "stress_buffer",
        ]
    ].sum(axis=1)
    assert np.allclose(result["total_margin"], expected_total)
    assert (result["total_margin"] >= 0.0).all()

    # Rerunning the final assembly for the same date must upsert, not duplicate.
    _run(repo, "09_run_daily_member_margin.py")
    rerun = pd.read_parquet(output)
    assert len(rerun) == 2

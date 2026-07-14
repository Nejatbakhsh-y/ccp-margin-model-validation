from __future__ import annotations

import numpy as np
import pandas as pd

from tests._step21_support import first_existing, read_table


def test_validation_result_rows_support_exception_and_shortfall_recalculation():
    path = first_existing(
        "data/processed/sensitivity_scenario_results.parquet",
        "data/processed/backtesting_results.parquet",
        "reports/tables/backtesting_results.csv",
    )
    assert path is not None, "No prepared validation/backtesting result file was found."

    frame = read_table(path)
    assert not frame.empty

    margin_candidates = [
        "margin", "margin_amount", "total_margin", "required_margin", "base_margin"
    ]
    loss_candidates = ["realized_loss", "loss", "actual_loss"]

    margin_col = next((column for column in margin_candidates if column in frame.columns), None)
    loss_col = next((column for column in loss_candidates if column in frame.columns), None)

    assert margin_col is not None, "Validation results lack a recognized margin field."
    assert loss_col is not None, "Validation results lack a recognized realized-loss field."

    margin = pd.to_numeric(frame[margin_col], errors="coerce")
    loss = pd.to_numeric(frame[loss_col], errors="coerce")
    valid = margin.notna() & loss.notna()
    assert valid.any()

    expected_exception = loss[valid] > margin[valid]
    expected_shortfall = (loss[valid] - margin[valid]).clip(lower=0.0)

    if "exception_flag" in frame.columns:
        actual_exception = frame.loc[valid, "exception_flag"]
        if actual_exception.dtype != bool:
            actual_exception = (
                actual_exception.astype(str).str.strip().str.lower()
                .isin({"1", "true", "yes", "y", "exception", "breach"})
            )
        np.testing.assert_array_equal(actual_exception.to_numpy(), expected_exception.to_numpy())

    if "margin_shortfall" in frame.columns:
        actual_shortfall = pd.to_numeric(frame.loc[valid, "margin_shortfall"])
        np.testing.assert_allclose(
            actual_shortfall.to_numpy(),
            expected_shortfall.to_numpy(),
            rtol=1e-9,
            atol=1e-8,
        )

from __future__ import annotations

import numpy as np
import pandas as pd

from tests._step21_support import first_existing, read_table


def test_daily_margin_output_has_required_schema_and_aggregation_identity():
    path = first_existing(
        "data/processed/daily_member_margin.parquet",
        "data/processed/daily_margin.parquet",
    )
    assert path is not None, "Daily margin output was not found."

    frame = read_table(path)
    assert not frame.empty

    required = {"date", "member_id", "total_margin"}
    missing = required.difference(frame.columns)
    assert not missing, f"Missing daily-margin columns: {sorted(missing)}"

    assert frame["member_id"].astype(str).str.strip().ne("").all()
    assert pd.to_datetime(frame["date"], errors="coerce").notna().all()
    assert np.isfinite(pd.to_numeric(frame["total_margin"], errors="coerce")).all()
    assert (pd.to_numeric(frame["total_margin"]) >= 0.0).all()

    components = [
        column
        for column in (
            "base_var",
            "liquidity_addon",
            "concentration_addon",
            "gap_risk_addon",
            "stress_buffer",
        )
        if column in frame.columns
    ]
    if len(components) == 5:
        expected = frame[components].apply(pd.to_numeric).sum(axis=1)
        actual = pd.to_numeric(frame["total_margin"])
        np.testing.assert_allclose(actual, expected, rtol=1e-9, atol=1e-6)

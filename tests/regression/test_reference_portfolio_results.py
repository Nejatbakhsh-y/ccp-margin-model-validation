from __future__ import annotations

import json

import numpy as np
import pandas as pd

from tests._step21_support import ROOT, first_existing, read_table


def test_latest_reference_portfolio_margin_matches_approved_baseline():
    baseline_path = (
        ROOT / "tests" / "regression" / "reference" /
        "reference_portfolio_results.json"
    )
    assert baseline_path.exists(), "Regression baseline was not generated."

    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    data_path = first_existing(
        "data/processed/daily_member_margin.parquet",
        "data/processed/daily_margin.parquet",
    )
    assert data_path is not None

    frame = read_table(data_path)
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    target_date = pd.Timestamp(baseline["date"])
    current = frame.loc[frame["date"] == target_date].copy()
    assert not current.empty

    current["member_id"] = current["member_id"].astype(str)
    current = current.set_index("member_id")

    for row in baseline["rows"]:
        member = str(row["member_id"])
        assert member in current.index
        observed = float(current.loc[member, "total_margin"])
        expected = float(row["total_margin"])
        assert np.isclose(observed, expected, rtol=1e-10, atol=1e-6)

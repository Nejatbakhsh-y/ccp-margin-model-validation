from __future__ import annotations

import json

from tests._step21_support import ROOT, read_table, stable_digest


def test_fixed_seed_portfolio_artifact_matches_regression_digest():
    baseline_path = (
        ROOT / "tests" / "regression" / "reference" / "fixed_seed_reproducibility.json"
    )
    assert baseline_path.exists(), "Fixed-seed regression baseline was not generated."

    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    source_path = ROOT / baseline["source_file"]
    assert source_path.exists(), f"Baseline source is missing: {source_path}"

    frame = read_table(source_path)
    assert stable_digest(frame) == baseline["sha256"]

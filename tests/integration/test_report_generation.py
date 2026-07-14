from __future__ import annotations

from tests._step21_support import ROOT


def test_independent_validation_report_exists_and_contains_core_sections():
    path = ROOT / "reports" / "independent_validation_report.md"
    assert path.exists(), f"Missing report: {path}"

    text = path.read_text(encoding="utf-8-sig")
    assert len(text.strip()) >= 500

    lowered = text.lower()
    required_topics = (
        "executive",
        "model purpose",
        "scope",
        "methodology",
        "backtest",
        "stress",
        "procyclic",
        "finding",
    )
    missing = [topic for topic in required_topics if topic not in lowered]
    assert not missing, f"Report is missing expected topics: {missing}"

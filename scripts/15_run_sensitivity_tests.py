"""Run independent Step 15 sensitivity comparisons and create evidence files.

This script analyzes actual model-generated scenario results. It does not create
synthetic results and does not treat missing scenario runs as successful.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ccp_margin.validation.sensitivity_step15 import (
    run_sensitivity_analysis,
    write_sensitivity_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=REPO_ROOT / "configs" / "validation" / "sensitivity.yaml",
    )
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--results", type=Path, default=None)
    parser.add_argument("--output-directory", type=Path, default=None)
    return parser.parse_args()


def read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"Unsupported input format: {path}. Use CSV or Parquet.")


def resolve_path(value: Path | None, configured: str) -> Path:
    path = value if value is not None else Path(configured)
    return path if path.is_absolute() else REPO_ROOT / path


def main() -> None:
    args = parse_args()
    config_path = args.config.resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"Sensitivity config not found: {config_path}")

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    manifest_path = resolve_path(args.manifest, config["paths"]["manifest"])
    results_path = resolve_path(args.results, config["paths"]["scenario_results"])
    output_directory = resolve_path(
        args.output_directory, config["paths"]["report_directory"]
    )

    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Scenario manifest not found: {manifest_path}\n"
            "Run: python scripts\\15_generate_sensitivity_manifest.py"
        )
    if not results_path.exists():
        raise FileNotFoundError(
            f"Actual scenario results not found: {results_path}\n"
            "Run the primary margin, challenger, add-on, and backtesting pipeline "
            "for every scenario in the manifest. Combine those outputs into one "
            "CSV or Parquet file with columns: scenario_id, date, member_id, "
            "margin, realized_loss."
        )

    manifest = read_table(manifest_path)
    results = read_table(results_path)
    reporting = config.get("reporting", {})

    analysis = run_sensitivity_analysis(
        results=results,
        manifest=manifest,
        significance_level=float(reporting.get("significance_level", 0.05)),
        top_member_count=int(reporting.get("top_member_count", 5)),
        stability_review_thresholds=reporting.get(
            "stability_review_thresholds", {}
        ),
    )
    paths = write_sensitivity_report(analysis, output_directory)

    print("STEP 15 SENSITIVITY ANALYSIS COMPLETED")
    print(f"Scenarios analyzed: {analysis.metadata['scenario_count']}")
    print(f"Report: {paths['report']}")
    print(f"Scenario summary: {paths['scenario_summary']}")
    print(f"Parameter stability: {paths['parameter_stability']}")


if __name__ == "__main__":
    main()


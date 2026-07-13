"""Generate the Step 15 one-at-a-time sensitivity scenario manifest."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ccp_margin.validation.sensitivity_step15 import build_one_at_a_time_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=REPO_ROOT / "configs" / "validation" / "sensitivity.yaml",
    )
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = args.config.resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"Sensitivity config not found: {config_path}")

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    output = args.output
    if output is None:
        output = REPO_ROOT / config["paths"]["manifest"]
    elif not output.is_absolute():
        output = REPO_ROOT / output

    manifest = build_one_at_a_time_manifest(
        baseline=config["baseline"],
        parameter_sets=config["parameter_sets"],
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(output, index=False)

    print("STEP 15 SENSITIVITY MANIFEST CREATED")
    print(f"Path: {output}")
    print(f"Total scenarios: {len(manifest)}")
    print(f"Baseline scenarios: {int(manifest['is_baseline'].sum())}")
    print(f"Non-baseline scenarios: {int((~manifest['is_baseline']).sum())}")


if __name__ == "__main__":
    main()


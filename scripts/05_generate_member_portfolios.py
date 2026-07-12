"""Generate deterministic synthetic clearing-member portfolios.

Run from the project root:
    python scripts/05_generate_member_portfolios.py

An explicit input can be supplied when the processed market-data file has a
non-standard name:
    python scripts/05_generate_member_portfolios.py --input data/processed/FILE.parquet
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ccp_margin.portfolio.concentration import calculate_concentration_metrics
from ccp_margin.portfolio.exposures import calculate_exposures
from ccp_margin.portfolio.generator import (
    PortfolioGenerationConfig,
    canonical_portfolio_sha256,
    generate_synthetic_portfolios,
)
from ccp_margin.portfolio.liquidity import calculate_liquidity_metrics

DEFAULT_INPUT_CANDIDATES = (
    "data/processed/validated_market_data.parquet",
    "data/processed/market_data_clean.parquet",
    "data/processed/market_data.parquet",
    "data/processed/prices_clean.parquet",
    "data/processed/market_prices.parquet",
    "data/processed/validated_market_data.csv",
    "data/processed/market_data_clean.csv",
    "data/processed/market_data.csv",
    "data/processed/prices_clean.csv",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/project.yaml"),
        help="Project YAML configuration file.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Cleaned long-form market-data parquet or CSV file.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed"),
        help="Directory for portfolio outputs.",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError("The project YAML root must be a mapping.")
    return raw


def resolve_input(explicit_input: Path | None) -> Path:
    if explicit_input is not None:
        path = explicit_input if explicit_input.is_absolute() else PROJECT_ROOT / explicit_input
        if not path.exists():
            raise FileNotFoundError(f"Market-data input not found: {path}")
        return path

    for relative in DEFAULT_INPUT_CANDIDATES:
        candidate = PROJECT_ROOT / relative
        if candidate.exists():
            return candidate

    processed_dir = PROJECT_ROOT / "data" / "processed"
    available = []
    if processed_dir.exists():
        available = sorted(
            str(path.relative_to(PROJECT_ROOT))
            for path in processed_dir.iterdir()
            if path.suffix.lower() in {".parquet", ".csv"}
        )
    available_text = "\n".join(f"  - {path}" for path in available) or "  (none)"
    raise FileNotFoundError(
        "No cleaned market-data file was found under data/processed. "
        "Use --input with the correct filename. Available tabular files:\n"
        + available_text
    )


def read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"Unsupported input format: {path.suffix}")


def write_outputs(
    positions: pd.DataFrame,
    output_dir: Path,
    config: PortfolioGenerationConfig,
    input_path: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    positions_path = output_dir / "clearing_member_positions.parquet"
    exposures_path = output_dir / "portfolio_exposures.parquet"
    concentration_path = output_dir / "portfolio_concentration.parquet"
    liquidity_path = output_dir / "portfolio_liquidity.parquet"
    registry_path = output_dir / "portfolio_registry.csv"
    manifest_path = output_dir / "portfolio_generation_manifest.json"

    exposures = calculate_exposures(positions)
    concentration = calculate_concentration_metrics(positions)
    liquidity = calculate_liquidity_metrics(positions)

    positions.to_parquet(positions_path, index=False)
    exposures.to_parquet(exposures_path, index=False)
    concentration.to_parquet(concentration_path, index=False)
    liquidity.to_parquet(liquidity_path, index=False)

    latest_date = positions["valuation_date"].max()
    latest = positions.loc[positions["valuation_date"] == latest_date].copy()
    registry = (
        latest.groupby(
            ["member_id", "portfolio_id", "portfolio_category"],
            sort=True,
            observed=True,
        )
        .agg(
            position_count=("security_id", "nunique"),
            gross_market_value=("market_value", lambda values: values.abs().sum()),
            net_market_value=("market_value", "sum"),
        )
        .reset_index()
    )
    registry["reference_valuation_date"] = pd.Timestamp(latest_date).date().isoformat()
    registry.to_csv(registry_path, index=False)

    manifest = {
        "input_file": str(input_path.resolve()),
        "random_seed": config.random_seed,
        "number_of_members": config.number_of_members,
        "minimum_positions": config.minimum_positions,
        "maximum_positions": config.maximum_positions,
        "gross_notional_min": config.gross_notional_min,
        "gross_notional_max": config.gross_notional_max,
        "categories": list(config.categories),
        "position_rows": int(len(positions)),
        "valuation_date_min": positions["valuation_date"].min().date().isoformat(),
        "valuation_date_max": positions["valuation_date"].max().date().isoformat(),
        "portfolio_sha256": canonical_portfolio_sha256(positions),
        "output_files": {
            "positions": str(positions_path.resolve()),
            "exposures": str(exposures_path.resolve()),
            "concentration": str(concentration_path.resolve()),
            "liquidity": str(liquidity_path.resolve()),
            "registry": str(registry_path.resolve()),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print("Synthetic clearing-member portfolios generated successfully.")
    print(f"Input: {input_path}")
    print(f"Seed: {config.random_seed}")
    print(f"Members: {config.number_of_members}")
    print(f"Position rows: {len(positions):,}")
    print(f"Date range: {manifest['valuation_date_min']} to {manifest['valuation_date_max']}")
    print(f"SHA-256: {manifest['portfolio_sha256']}")
    print(f"Positions: {positions_path}")
    print(f"Manifest: {manifest_path}")


def main() -> None:
    args = parse_args()
    config_path = args.config if args.config.is_absolute() else PROJECT_ROOT / args.config
    output_dir = (
        args.output_dir if args.output_dir.is_absolute() else PROJECT_ROOT / args.output_dir
    )
    raw_config = load_yaml(config_path)
    generation_config = PortfolioGenerationConfig.from_mapping(raw_config)
    input_path = resolve_input(args.input)
    market_data = read_table(input_path)
    positions = generate_synthetic_portfolios(market_data, generation_config)
    write_outputs(positions, output_dir, generation_config, input_path)


if __name__ == "__main__":
    main()

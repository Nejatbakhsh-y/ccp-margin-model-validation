"""Generate reproducible synthetic clearing-member portfolios."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from _data_pipeline_common import (
    ROOT,
    configure_logging,
    ensure_directories,
    load_configs,
    relative_path,
    sha256_file,
    utc_now_iso,
    write_json,
)

SCRIPT = Path(__file__).stem
LOGGER = configure_logging(SCRIPT)


def sample_weights(
    rng: np.random.Generator,
    number_of_positions: int,
    concentration: float,
    maximum_weight: float,
    maximum_attempts: int,
) -> np.ndarray:
    if maximum_weight * number_of_positions < 1.0:
        raise ValueError(
            "maximum_single_position_weight is infeasible for the configured minimum positions."
        )
    alpha = np.full(number_of_positions, concentration, dtype=float)
    for _ in range(maximum_attempts):
        weights = rng.dirichlet(alpha)
        if float(weights.max()) <= maximum_weight:
            return weights
    raise RuntimeError(
        "Unable to sample portfolio weights within the concentration limit. "
        "Increase maximum_single_position_weight or dirichlet_concentration."
    )


def main() -> int:
    ensure_directories()
    project_config, data_config = load_configs()

    project_settings = project_config["project"]
    portfolio_settings = project_config["portfolio"]
    synthetic_settings = data_config["synthetic_portfolios"]

    seed = int(project_settings["random_seed"])
    rng = np.random.default_rng(seed)

    number_of_members = int(portfolio_settings["number_of_members"])
    minimum_positions = int(portfolio_settings["minimum_positions"])
    maximum_positions = int(portfolio_settings["maximum_positions"])
    gross_notional_min = float(portfolio_settings["gross_notional_min"])
    gross_notional_max = float(portfolio_settings["gross_notional_max"])

    maximum_weight = float(synthetic_settings["maximum_single_position_weight"])
    short_probability = float(synthetic_settings["short_position_probability"])
    concentration = float(synthetic_settings["dirichlet_concentration"])
    maximum_attempts = int(synthetic_settings["maximum_weight_sampling_attempts"])

    if not 0.0 <= short_probability <= 1.0:
        raise ValueError("short_position_probability must be between 0 and 1.")
    if gross_notional_min <= 0 or gross_notional_max < gross_notional_min:
        raise ValueError("Gross-notional limits are invalid.")

    price_path = ROOT / "data" / "processed" / "adjusted_close_wide.parquet"
    if not price_path.exists():
        raise FileNotFoundError(
            f"Missing {relative_path(price_path)}. Run scripts/04_build_clean_market_dataset.py first."
        )
    prices = pd.read_parquet(price_path).sort_index()
    if prices.empty:
        raise ValueError("The clean adjusted-close dataset is empty.")

    reference_date = pd.Timestamp(prices.index.max())
    reference_prices = pd.to_numeric(prices.loc[reference_date], errors="coerce").dropna()
    reference_prices = reference_prices[reference_prices > 0]
    available_tickers = reference_prices.index.astype(str).tolist()
    if len(available_tickers) < maximum_positions:
        raise ValueError("Insufficient assets for the configured maximum_positions value.")

    position_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []

    for member_number in range(1, number_of_members + 1):
        member_id = f"CM{member_number:03d}"
        number_of_positions = int(rng.integers(minimum_positions, maximum_positions + 1))
        selected = rng.choice(available_tickers, size=number_of_positions, replace=False)

        weights = sample_weights(
            rng=rng,
            number_of_positions=number_of_positions,
            concentration=concentration,
            maximum_weight=maximum_weight,
            maximum_attempts=maximum_attempts,
        )
        directions = np.where(rng.random(number_of_positions) < short_probability, -1.0, 1.0)

        log_min = math.log10(gross_notional_min)
        log_max = math.log10(gross_notional_max)
        gross_notional = float(10 ** rng.uniform(log_min, log_max))

        absolute_notionals = weights * gross_notional
        signed_notionals = absolute_notionals * directions
        long_notional = float(signed_notionals[signed_notionals > 0].sum())
        short_notional = float(-signed_notionals[signed_notionals < 0].sum())
        net_notional = float(signed_notionals.sum())

        for position_number, (ticker, weight, direction, absolute_notional, signed_notional) in enumerate(
            zip(selected, weights, directions, absolute_notionals, signed_notionals, strict=True),
            start=1,
        ):
            reference_price = float(reference_prices.loc[str(ticker)])
            quantity = float(signed_notional / reference_price)
            position_rows.append(
                {
                    "member_id": member_id,
                    "position_id": f"{member_id}-P{position_number:02d}",
                    "ticker": str(ticker),
                    "direction": "LONG" if direction > 0 else "SHORT",
                    "absolute_weight": float(weight),
                    "signed_weight": float(weight * direction),
                    "reference_date": reference_date.date().isoformat(),
                    "reference_price": reference_price,
                    "quantity": quantity,
                    "absolute_notional": float(absolute_notional),
                    "signed_notional": float(signed_notional),
                    "currency": str(project_settings["currency"]),
                }
            )

        summary_rows.append(
            {
                "member_id": member_id,
                "number_of_positions": number_of_positions,
                "gross_notional": gross_notional,
                "long_notional": long_notional,
                "short_notional": short_notional,
                "net_notional": net_notional,
                "largest_absolute_weight": float(weights.max()),
                "weight_hhi": float(np.square(weights).sum()),
                "reference_date": reference_date.date().isoformat(),
                "currency": str(project_settings["currency"]),
            }
        )

    positions = pd.DataFrame(position_rows)
    summaries = pd.DataFrame(summary_rows)

    # Reconciliation controls.
    reconciled = positions.groupby("member_id").agg(
        calculated_gross_notional=("absolute_notional", "sum"),
        calculated_net_notional=("signed_notional", "sum"),
        calculated_positions=("position_id", "count"),
        calculated_weight_sum=("absolute_weight", "sum"),
    )
    check = summaries.set_index("member_id").join(reconciled)
    if not np.allclose(check["gross_notional"], check["calculated_gross_notional"], rtol=1e-10):
        raise AssertionError("Gross-notional reconciliation failed.")
    if not np.allclose(check["net_notional"], check["calculated_net_notional"], rtol=1e-10):
        raise AssertionError("Net-notional reconciliation failed.")
    if not np.allclose(check["calculated_weight_sum"], 1.0, rtol=1e-10):
        raise AssertionError("Absolute portfolio weights do not sum to one.")

    synthetic_directory = ROOT / "data" / "synthetic"
    positions_path = synthetic_directory / "member_positions.csv"
    summaries_path = synthetic_directory / "member_portfolio_summary.csv"
    example_path = synthetic_directory / "example_member_positions.csv"
    positions.to_csv(positions_path, index=False)
    summaries.to_csv(summaries_path, index=False)
    positions[positions["member_id"].isin(["CM001", "CM002", "CM003"])].to_csv(
        example_path, index=False
    )

    dictionary = pd.DataFrame(
        [
            ("member_id", "string", "Synthetic clearing-member identifier."),
            ("position_id", "string", "Unique synthetic position identifier."),
            ("ticker", "string", "Underlying market-data ticker."),
            ("direction", "string", "LONG or SHORT position direction."),
            ("absolute_weight", "float", "Position share of member gross notional."),
            ("signed_weight", "float", "Direction-adjusted portfolio weight."),
            ("reference_date", "date", "Date used to convert notional into quantity."),
            ("reference_price", "float", "Adjusted close on the reference date."),
            ("quantity", "float", "Signed units of the underlying asset."),
            ("absolute_notional", "float", "Positive contribution to gross notional."),
            ("signed_notional", "float", "Direction-adjusted notional."),
            ("currency", "string", "Configured project currency."),
        ],
        columns=["field", "type", "definition"],
    )
    dictionary.to_csv(
        ROOT / "data" / "manifests" / "member_portfolio_data_dictionary.csv", index=False
    )

    manifest_path = ROOT / "data" / "manifests" / "member_portfolio_manifest.json"
    write_json(
        manifest_path,
        {
            "status": "completed",
            "random_seed": seed,
            "members": number_of_members,
            "positions": int(len(positions)),
            "reference_date": reference_date.date().isoformat(),
            "positions_file": relative_path(positions_path),
            "positions_sha256": sha256_file(positions_path),
            "summary_file": relative_path(summaries_path),
            "summary_sha256": sha256_file(summaries_path),
            "example_file": relative_path(example_path),
            "example_sha256": sha256_file(example_path),
            "generated_at_utc": utc_now_iso(),
        },
    )
    LOGGER.info(
        "Generated %d members and %d positions using seed %d",
        number_of_members,
        len(positions),
        seed,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Build deterministic clean long-form and wide-form market datasets."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from _data_pipeline_common import (
    ROOT,
    configure_logging,
    configured_observation_end,
    ensure_directories,
    load_configs,
    relative_path,
    sha256_file,
    utc_now_iso,
    write_json,
)

SCRIPT = Path(__file__).stem
LOGGER = configure_logging(SCRIPT)


def main() -> int:
    ensure_directories()
    project_config, data_config = load_configs()

    start_date = pd.Timestamp(project_config["data"]["start_date"])
    end_date = pd.Timestamp(configured_observation_end(project_config["data"].get("end_date")))
    minimum_completeness = float(project_config["data"]["minimum_completeness"])
    tickers = [str(item).upper() for item in data_config["market_data"]["tickers"]]
    cleaning_settings = data_config["cleaning"]

    frames: list[pd.DataFrame] = []
    for ticker in tickers:
        path = ROOT / "data" / "raw" / "market" / f"{ticker}.parquet"
        if not path.exists():
            raise FileNotFoundError(
                f"Missing {relative_path(path)}. Run scripts/01_download_market_data.py first."
            )
        frame = pd.read_parquet(path)
        frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.tz_localize(None)
        frame = frame[(frame["date"] >= start_date) & (frame["date"] <= end_date)].copy()
        frames.append(frame)

    market = pd.concat(frames, ignore_index=True)
    market = market.drop_duplicates(["ticker", "date"], keep="last")
    market = market.sort_values(["ticker", "date"]).reset_index(drop=True)

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "adj_close",
        "volume",
        "dividends",
        "stock_splits",
        "capital_gains",
    ]
    for column in numeric_columns:
        market[column] = pd.to_numeric(market[column], errors="coerce")

    if bool(cleaning_settings["drop_rows_missing_adjusted_close"]):
        market = market[market["adj_close"].notna()].copy()

    if (market["adj_close"] <= 0).any():
        raise ValueError("Nonpositive adjusted prices remain after raw-data validation.")

    market["simple_return"] = market.groupby("ticker", sort=False)["adj_close"].pct_change(
        fill_method=None
    )
    market["log_adjusted_close"] = np.log(market["adj_close"])
    market["log_return"] = market.groupby("ticker", sort=False)["log_adjusted_close"].diff()
    market = market.drop(columns="log_adjusted_close")

    processed_directory = ROOT / "data" / "processed"
    long_path = processed_directory / "market_data_clean_long.parquet"
    market.to_parquet(long_path, index=False)

    adjusted_close_all = market.pivot(index="date", columns="ticker", values="adj_close").sort_index()
    close_all = market.pivot(index="date", columns="ticker", values="close").sort_index()
    volume_all = market.pivot(index="date", columns="ticker", values="volume").sort_index()

    union_dates = adjusted_close_all.index
    completeness = adjusted_close_all.notna().sum().div(len(union_dates)).sort_index()
    completeness_frame = completeness.rename("completeness").reset_index()
    completeness_frame["required_minimum"] = minimum_completeness
    completeness_frame["status"] = np.where(
        completeness_frame["completeness"] >= minimum_completeness,
        "PASS",
        "FAIL",
    )
    completeness_path = ROOT / "reports" / "evidence" / "market_completeness.csv"
    completeness_frame.to_csv(completeness_path, index=False)

    failed = completeness_frame[completeness_frame["status"] == "FAIL"]
    if not failed.empty:
        raise ValueError(
            "Market completeness threshold failed for: "
            + ", ".join(failed["ticker"].astype(str).tolist())
            + f". Review {relative_path(completeness_path)}."
        )

    if bool(cleaning_settings["require_common_calendar"]):
        adjusted_close = adjusted_close_all.dropna(how="any")
        common_dates = adjusted_close.index
        close = close_all.reindex(common_dates)
        volume = volume_all.reindex(common_dates)
    else:
        adjusted_close = adjusted_close_all
        close = close_all
        volume = volume_all

    if bool(cleaning_settings["do_not_forward_fill_prices"]):
        # Explicitly document the control. No fill operation is performed.
        LOGGER.info("Price forward-filling is disabled by configuration")

    adjusted_close_path = processed_directory / "adjusted_close_wide.parquet"
    close_path = processed_directory / "close_wide.parquet"
    volume_path = processed_directory / "volume_wide.parquet"
    adjusted_close.to_parquet(adjusted_close_path)
    close.to_parquet(close_path)
    volume.to_parquet(volume_path)

    returns = adjusted_close.pct_change(fill_method=None).dropna(how="any")
    log_returns = np.log(adjusted_close).diff().dropna(how="any")
    returns_path = processed_directory / "returns_wide.parquet"
    log_returns_path = processed_directory / "log_returns_wide.parquet"
    returns.to_parquet(returns_path)
    log_returns.to_parquet(log_returns_path)

    manifest_rows = []
    for path in (
        long_path,
        adjusted_close_path,
        close_path,
        volume_path,
        returns_path,
        log_returns_path,
    ):
        manifest_rows.append(
            {
                "file": relative_path(path),
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    manifest = pd.DataFrame(manifest_rows)
    manifest_path = ROOT / "data" / "manifests" / "clean_market_dataset_manifest.csv"
    manifest.to_csv(manifest_path, index=False)

    write_json(
        ROOT / "data" / "manifests" / "clean_market_dataset_summary.json",
        {
            "status": "completed",
            "long_rows": int(len(market)),
            "ticker_count": int(market["ticker"].nunique()),
            "common_price_dates": int(len(adjusted_close)),
            "common_return_dates": int(len(returns)),
            "first_common_price_date": adjusted_close.index.min().date().isoformat(),
            "last_common_price_date": adjusted_close.index.max().date().isoformat(),
            "minimum_observed_completeness": float(completeness.min()),
            "forward_fill_used": False,
            "manifest_file": relative_path(manifest_path),
            "manifest_sha256": sha256_file(manifest_path),
            "generated_at_utc": utc_now_iso(),
        },
    )
    LOGGER.info(
        "Clean dataset completed: %d tickers, %d common price dates",
        market["ticker"].nunique(),
        len(adjusted_close),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

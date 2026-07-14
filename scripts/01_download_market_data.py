"""Download unadjusted prices, adjusted prices, volume, and corporate actions."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

from _data_pipeline_common import (
    ROOT,
    configure_logging,
    ensure_directories,
    inclusive_end_to_exclusive,
    load_configs,
    relative_path,
    sha256_file,
    snake_case,
    utc_now_iso,
    write_json,
)

SCRIPT = Path(__file__).stem
LOGGER = configure_logging(SCRIPT)

REQUIRED_COLUMNS = {
    "date",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
}
ACTION_COLUMNS = ("dividends", "stock_splits", "capital_gains")


def download_one_ticker(
    ticker: str,
    start_date: str,
    end_date_exclusive: str | None,
    interval: str,
    retries: int,
    pause_seconds: float,
    timeout_seconds: float,
    repair: bool,
) -> pd.DataFrame:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            LOGGER.info("Downloading %s (attempt %d/%d)", ticker, attempt, retries)
            frame = yf.download(
                tickers=ticker,
                start=start_date,
                end=end_date_exclusive,
                interval=interval,
                actions=True,
                auto_adjust=False,
                repair=repair,
                threads=False,
                progress=False,
                timeout=timeout_seconds,
                multi_level_index=False,
            )
            if frame is None or frame.empty:
                raise RuntimeError(f"No observations returned for {ticker}")

            if isinstance(frame.columns, pd.MultiIndex):
                frame.columns = [
                    "_".join(str(part) for part in column if str(part))
                    for column in frame.columns
                ]

            frame = frame.reset_index()
            frame.columns = [snake_case(column) for column in frame.columns]

            # yfinance names the adjusted-close column "Adj Close".
            if "adjusted_close" in frame.columns and "adj_close" not in frame.columns:
                frame = frame.rename(columns={"adjusted_close": "adj_close"})

            missing = REQUIRED_COLUMNS.difference(frame.columns)
            if missing:
                raise RuntimeError(
                    f"{ticker} is missing required yfinance columns: {sorted(missing)}. "
                    "Confirm that auto_adjust=False and use a current yfinance release."
                )

            for action_column in ACTION_COLUMNS:
                if action_column not in frame.columns:
                    frame[action_column] = 0.0

            frame["date"] = pd.to_datetime(
                frame["date"], errors="raise"
            ).dt.tz_localize(None)
            numeric_columns = [
                "open",
                "high",
                "low",
                "close",
                "adj_close",
                "volume",
                *ACTION_COLUMNS,
            ]
            for column in numeric_columns:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")

            frame["ticker"] = ticker
            frame["source"] = "yahoo_finance_via_yfinance"
            frame["retrieved_at_utc"] = utc_now_iso()
            frame = frame.sort_values("date").reset_index(drop=True)
            return frame
        except Exception as exc:  # noqa: BLE001 - preserve provider error context
            last_error = exc
            LOGGER.warning("Download failed for %s: %s", ticker, exc)
            if attempt < retries:
                time.sleep(pause_seconds)

    raise RuntimeError(
        f"Download failed for {ticker} after {retries} attempts"
    ) from last_error


def main() -> int:
    ensure_directories()
    project_config, data_config = load_configs()

    data_settings = project_config["data"]
    market_settings = data_config["market_data"]
    download_settings = market_settings["download"]

    start_date = str(data_settings["start_date"])
    configured_end = data_settings.get("end_date")
    end_date_exclusive = inclusive_end_to_exclusive(configured_end)
    tickers = [str(item).upper() for item in market_settings["tickers"]]

    raw_directory = ROOT / "data" / "raw" / "market"
    manifest_rows: list[dict[str, object]] = []

    for ticker in tickers:
        frame = download_one_ticker(
            ticker=ticker,
            start_date=start_date,
            end_date_exclusive=end_date_exclusive,
            interval=str(market_settings["interval"]),
            retries=int(download_settings["retries"]),
            pause_seconds=float(download_settings["retry_pause_seconds"]),
            timeout_seconds=float(download_settings["timeout_seconds"]),
            repair=bool(download_settings["repair"]),
        )

        output_path = raw_directory / f"{ticker}.parquet"
        frame.to_parquet(output_path, index=False)

        manifest_rows.append(
            {
                "ticker": ticker,
                "provider": market_settings["provider"],
                "file": relative_path(output_path),
                "sha256": sha256_file(output_path),
                "observations": int(len(frame)),
                "first_date": frame["date"].min().date().isoformat(),
                "last_date": frame["date"].max().date().isoformat(),
                "missing_adj_close": int(frame["adj_close"].isna().sum()),
                "missing_close": int(frame["close"].isna().sum()),
                "missing_volume": int(frame["volume"].isna().sum()),
                "dividend_observations": int((frame["dividends"].fillna(0) != 0).sum()),
                "split_observations": int((frame["stock_splits"].fillna(0) != 0).sum()),
                "capital_gain_observations": int(
                    (frame["capital_gains"].fillna(0) != 0).sum()
                ),
                "retrieved_at_utc": frame["retrieved_at_utc"].iloc[0],
            }
        )
        LOGGER.info("Saved %s observations for %s", len(frame), ticker)

    manifest = pd.DataFrame(manifest_rows).sort_values("ticker")
    manifest_path = ROOT / "data" / "manifests" / "market_data_manifest.csv"
    manifest.to_csv(manifest_path, index=False)

    dictionary = pd.DataFrame(
        [
            (
                "date",
                "date",
                "Trading date; timezone removed after daily-data retrieval.",
            ),
            ("ticker", "string", "Yahoo Finance ticker identifier."),
            ("open", "float", "Unadjusted daily opening price."),
            ("high", "float", "Unadjusted daily high price."),
            ("low", "float", "Unadjusted daily low price."),
            (
                "close",
                "float",
                "Unadjusted daily closing price returned with auto_adjust=False.",
            ),
            (
                "adj_close",
                "float",
                "Closing price adjusted for applicable distributions and splits.",
            ),
            ("volume", "float", "Reported daily trading volume."),
            ("dividends", "float", "Cash dividend corporate action, when available."),
            ("stock_splits", "float", "Stock-split factor, when available."),
            ("capital_gains", "float", "Capital-gain distribution, when available."),
            ("source", "string", "Data-provider lineage."),
            ("retrieved_at_utc", "string", "UTC retrieval timestamp."),
        ],
        columns=["field", "type", "definition"],
    )
    dictionary.to_csv(
        ROOT / "data" / "manifests" / "market_data_dictionary.csv", index=False
    )

    write_json(
        ROOT / "data" / "manifests" / "market_download_summary.json",
        {
            "status": "completed",
            "provider": market_settings["provider"],
            "start_date": start_date,
            "configured_end_date": configured_end,
            "tickers_requested": tickers,
            "tickers_completed": manifest["ticker"].tolist(),
            "total_observations": int(manifest["observations"].sum()),
            "manifest_file": relative_path(manifest_path),
            "manifest_sha256": sha256_file(manifest_path),
            "generated_at_utc": utc_now_iso(),
        },
    )
    LOGGER.info("Market-data download completed for %d tickers", len(tickers))
    return 0


if __name__ == "__main__":
    sys.exit(main())

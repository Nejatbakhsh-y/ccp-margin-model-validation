"""Download equity and ETF market data with source and fallback evidence."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf
from pandas_datareader import data as web

from ccp_margin.data.manifests import (
    find_project_root,
    load_project_config,
    make_run_id,
    record_dataset,
    utc_now,
)


DEFAULT_TICKERS = [
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
    "TLT",
    "IEF",
    "LQD",
    "HYG",
    "GLD",
    "VNQ",
]


def _flatten_yfinance_columns(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame.columns, pd.MultiIndex):
        return frame

    first_level = frame.columns.get_level_values(0)
    if len(set(first_level)) < len(frame.columns):
        frame.columns = frame.columns.get_level_values(-1)
    else:
        frame.columns = first_level
    return frame


def _normalize_market_frame(
    frame: pd.DataFrame,
    *,
    ticker: str,
    source: str,
    run_id: str,
    fallback_used: bool,
) -> pd.DataFrame:
    normalized = frame.copy()
    normalized = _flatten_yfinance_columns(normalized)

    if "Date" in normalized.columns:
        normalized = normalized.set_index("Date")

    normalized.index = pd.to_datetime(
        normalized.index, errors="coerce", utc=True
    ).tz_convert(None)
    normalized = normalized[normalized.index.notna()].sort_index()

    column_map = {
        str(column).strip().lower().replace(" ", "_"): column
        for column in normalized.columns
    }

    def get_column(name: str) -> pd.Series:
        original = column_map.get(name)
        if original is None:
            return pd.Series(index=normalized.index, dtype="float64")
        return pd.to_numeric(normalized[original], errors="coerce")

    output = pd.DataFrame(
        {
            "date": normalized.index.normalize(),
            "security_id": ticker.upper(),
            "open": get_column("open"),
            "high": get_column("high"),
            "low": get_column("low"),
            "close": get_column("close"),
            "adjusted_close": get_column("adj_close"),
            "volume": get_column("volume"),
            "dividends": get_column("dividends"),
            "stock_splits": get_column("stock_splits"),
        }
    )

    if output["adjusted_close"].isna().all():
        output["adjusted_close"] = output["close"]

    output["source"] = source
    output["source_priority"] = 2 if fallback_used else 1
    output["primary_source_available"] = not fallback_used
    output["fallback_used"] = fallback_used
    output["run_id"] = run_id
    output["download_timestamp_utc"] = utc_now()
    return output.reset_index(drop=True)


def _download_yahoo(
    ticker: str,
    start_date: str,
    end_date: str | None,
) -> pd.DataFrame:
    end_exclusive = None
    if end_date:
        end_exclusive = (
            pd.Timestamp(end_date) + pd.Timedelta(days=1)
        ).date().isoformat()

    frame = yf.download(
        tickers=ticker,
        start=start_date,
        end=end_exclusive,
        interval="1d",
        auto_adjust=False,
        actions=True,
        repair=False,
        progress=False,
        threads=False,
        group_by="column",
    )
    if frame is None or frame.empty:
        raise RuntimeError("Yahoo returned no rows.")
    return frame


def _download_stooq(
    ticker: str,
    start_date: str,
    end_date: str | None,
) -> pd.DataFrame:
    last_error: Exception | None = None
    candidates = [ticker]
    if "." not in ticker:
        candidates.append(f"{ticker}.US")

    for candidate in candidates:
        try:
            frame = web.DataReader(
                candidate,
                "stooq",
                start=pd.Timestamp(start_date),
                end=pd.Timestamp(end_date) if end_date else pd.Timestamp.today(),
            )
            if frame is not None and not frame.empty:
                return frame.sort_index()
        except Exception as exc:  # network/provider errors vary
            last_error = exc

    raise RuntimeError(
        f"Stooq returned no rows. Last error: {last_error}"
    )


def download_market_data(
    *,
    root: Path | None = None,
    allow_fallback: bool | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    project_root = root or find_project_root()
    config = load_project_config(project_root)
    data_config: dict[str, Any] = config["data"]
    market_config: dict[str, Any] = data_config.get("market", {})

    start_date = str(data_config.get("start_date", "2007-01-01"))
    end_value = data_config.get("end_date")
    end_date = None if end_value in (None, "", "null") else str(end_value)

    tickers = [
        str(ticker).upper()
        for ticker in market_config.get("tickers", DEFAULT_TICKERS)
    ]
    fallback_enabled = (
        bool(market_config.get("allow_fallback", True))
        if allow_fallback is None
        else allow_fallback
    )

    run_id = make_run_id()
    data_frames: list[pd.DataFrame] = []
    statuses: list[dict[str, Any]] = []

    for ticker in tickers:
        status: dict[str, Any] = {
            "run_id": run_id,
            "security_id": ticker,
            "requested_start_date": start_date,
            "requested_end_date": end_date or "",
            "primary_source": "yahoo",
            "primary_status": "FAILED",
            "fallback_source": "stooq",
            "fallback_attempted": False,
            "fallback_status": "NOT_ATTEMPTED",
            "selected_source": "",
            "row_count": 0,
            "error_message": "",
            "download_timestamp_utc": utc_now(),
        }

        try:
            raw = _download_yahoo(ticker, start_date, end_date)
            normalized = _normalize_market_frame(
                raw,
                ticker=ticker,
                source="yahoo",
                run_id=run_id,
                fallback_used=False,
            )
            if normalized.empty:
                raise RuntimeError("Yahoo normalization produced no rows.")
            data_frames.append(normalized)
            status["primary_status"] = "SUCCESS"
            status["selected_source"] = "yahoo"
            status["row_count"] = len(normalized)
        except Exception as primary_error:
            status["error_message"] = f"Yahoo: {primary_error}"

            if fallback_enabled:
                status["fallback_attempted"] = True
                try:
                    raw = _download_stooq(ticker, start_date, end_date)
                    normalized = _normalize_market_frame(
                        raw,
                        ticker=ticker,
                        source="stooq",
                        run_id=run_id,
                        fallback_used=True,
                    )
                    if normalized.empty:
                        raise RuntimeError(
                            "Stooq normalization produced no rows."
                        )
                    data_frames.append(normalized)
                    status["fallback_status"] = "SUCCESS"
                    status["selected_source"] = "stooq"
                    status["row_count"] = len(normalized)
                except Exception as fallback_error:
                    status["fallback_status"] = "FAILED"
                    status["error_message"] += f" | Stooq: {fallback_error}"

        statuses.append(status)

    status_frame = pd.DataFrame(statuses)
    status_path = (
        project_root / "data" / "manifests" / "market_download_status.csv"
    )
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_frame.to_csv(status_path, index=False)

    if not data_frames:
        failed_path = (
            project_root / "data" / "raw" / "market" / "market_prices_raw.parquet"
        )
        record_dataset(
            dataset_name="market_prices_raw",
            dataset_path=failed_path,
            root=project_root,
            request_parameters={
                "tickers": tickers,
                "start_date": start_date,
                "end_date": end_date,
                "allow_fallback": fallback_enabled,
            },
            status="FAILED",
            error_message="No market-data source returned usable rows.",
            run_id=run_id,
        )
        raise RuntimeError(
            "No market data were downloaded. Review "
            "data/manifests/market_download_status.csv."
        )

    market_data = pd.concat(data_frames, ignore_index=True)
    market_data = market_data.sort_values(
        ["security_id", "date", "source_priority"],
        kind="mergesort",
    ).reset_index(drop=True)

    output_path = (
        project_root / "data" / "raw" / "market" / "market_prices_raw.parquet"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    market_data.to_parquet(output_path, index=False)

    record_dataset(
        dataset_name="market_prices_raw",
        dataset_path=output_path,
        root=project_root,
        request_parameters={
            "tickers": tickers,
            "start_date": start_date,
            "end_date": end_date,
            "allow_fallback": fallback_enabled,
            "primary_source": "yahoo",
            "fallback_source": "stooq",
        },
        run_id=run_id,
    )

    return market_data, status_frame


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="Disable the Stooq fallback.",
    )
    args = parser.parse_args()

    market_data, status = download_market_data(
        allow_fallback=not args.no_fallback
    )
    print(
        "Market download completed: "
        f"{len(market_data):,} rows, "
        f"{market_data['security_id'].nunique()} securities."
    )
    print(status[["security_id", "selected_source", "row_count"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Download configured FRED series and preserve source-status evidence."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv
from pandas_datareader import data as web

from ccp_margin.data.manifests import (
    find_project_root,
    load_project_config,
    make_run_id,
    record_dataset,
    utc_now,
)


DEFAULT_FRED_SERIES = [
    "DFF",
    "DGS2",
    "DGS10",
    "T10Y2Y",
    "VIXCLS",
    "BAMLH0A0HYM2",
]


def _valid_api_key(value: str | None) -> bool:
    if value is None:
        return False
    normalized = value.strip()
    invalid_values = {
        "",
        "your_actual_key",
        "your_fred_api_key",
        "replace_me",
        "none",
        "null",
    }
    return normalized.lower() not in invalid_values


def _download_fred_api(
    *,
    series_id: str,
    api_key: str,
    start_date: str,
    end_date: str | None,
    timeout_seconds: int,
) -> pd.DataFrame:
    endpoint = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start_date,
    }
    if end_date:
        params["observation_end"] = end_date

    response = requests.get(endpoint, params=params, timeout=timeout_seconds)
    response.raise_for_status()
    payload = response.json()

    observations = payload.get("observations", [])
    if not observations:
        raise RuntimeError("FRED API returned no observations.")

    frame = pd.DataFrame(observations)
    return pd.DataFrame(
        {
            "date": pd.to_datetime(frame["date"], errors="coerce"),
            "value": pd.to_numeric(frame["value"], errors="coerce"),
        }
    )


def _download_pandas_datareader(
    *,
    series_id: str,
    start_date: str,
    end_date: str | None,
) -> pd.DataFrame:
    frame = web.DataReader(
        series_id,
        "fred",
        start=pd.Timestamp(start_date),
        end=pd.Timestamp(end_date) if end_date else pd.Timestamp.today(),
    )
    if frame is None or frame.empty:
        raise RuntimeError("pandas-datareader returned no observations.")

    frame = frame.reset_index()
    date_column = frame.columns[0]
    value_column = frame.columns[1]
    return pd.DataFrame(
        {
            "date": pd.to_datetime(frame[date_column], errors="coerce"),
            "value": pd.to_numeric(frame[value_column], errors="coerce"),
        }
    )


def download_fred_data(
    *,
    root: Path | None = None,
    allow_client_fallback: bool | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    project_root = root or find_project_root()
    load_dotenv(project_root / ".env")

    config = load_project_config(project_root)
    data_config: dict[str, Any] = config["data"]
    fred_config: dict[str, Any] = data_config.get("fred", {})

    start_date = str(data_config.get("start_date", "2007-01-01"))
    end_value = data_config.get("end_date")
    end_date = None if end_value in (None, "", "null") else str(end_value)

    series_ids = [
        str(series_id).upper()
        for series_id in fred_config.get("series", DEFAULT_FRED_SERIES)
    ]
    timeout_seconds = int(fred_config.get("timeout_seconds", 30))
    fallback_enabled = (
        bool(fred_config.get("allow_client_fallback", True))
        if allow_client_fallback is None
        else allow_client_fallback
    )

    api_key = os.getenv("FRED_API_KEY")
    api_key_available = _valid_api_key(api_key)
    run_id = make_run_id()

    frames: list[pd.DataFrame] = []
    statuses: list[dict[str, Any]] = []

    for series_id in series_ids:
        status: dict[str, Any] = {
            "run_id": run_id,
            "series_id": series_id,
            "requested_start_date": start_date,
            "requested_end_date": end_date or "",
            "primary_client": "fred_api",
            "api_key_available": api_key_available,
            "primary_status": "NOT_ATTEMPTED",
            "fallback_client": "pandas_datareader",
            "fallback_attempted": False,
            "fallback_status": "NOT_ATTEMPTED",
            "selected_client": "",
            "row_count": 0,
            "error_message": "",
            "download_timestamp_utc": utc_now(),
        }

        series_frame: pd.DataFrame | None = None
        if api_key_available:
            status["primary_status"] = "FAILED"
            try:
                series_frame = _download_fred_api(
                    series_id=series_id,
                    api_key=str(api_key),
                    start_date=start_date,
                    end_date=end_date,
                    timeout_seconds=timeout_seconds,
                )
                status["primary_status"] = "SUCCESS"
                status["selected_client"] = "fred_api"
            except Exception as primary_error:
                status["error_message"] = f"FRED API: {primary_error}"
        else:
            status["error_message"] = (
                "FRED_API_KEY is missing or still contains a placeholder."
            )

        if series_frame is None and fallback_enabled:
            status["fallback_attempted"] = True
            status["fallback_status"] = "FAILED"
            try:
                series_frame = _download_pandas_datareader(
                    series_id=series_id,
                    start_date=start_date,
                    end_date=end_date,
                )
                status["fallback_status"] = "SUCCESS"
                status["selected_client"] = "pandas_datareader"
            except Exception as fallback_error:
                status["error_message"] += f" | pandas-datareader: {fallback_error}"

        if series_frame is not None and not series_frame.empty:
            series_frame = series_frame.dropna(subset=["date"]).copy()
            series_frame["series_id"] = series_id
            series_frame["source"] = "FRED"
            series_frame["client"] = status["selected_client"]
            series_frame["run_id"] = run_id
            series_frame["download_timestamp_utc"] = utc_now()
            frames.append(series_frame)
            status["row_count"] = len(series_frame)

        statuses.append(status)

    status_frame = pd.DataFrame(statuses)
    status_path = project_root / "data" / "manifests" / "fred_download_status.csv"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_frame.to_csv(status_path, index=False)

    output_path = project_root / "data" / "raw" / "macro" / "fred_series_raw.parquet"

    if not frames:
        record_dataset(
            dataset_name="fred_series_raw",
            dataset_path=output_path,
            root=project_root,
            request_parameters={
                "series": series_ids,
                "start_date": start_date,
                "end_date": end_date,
                "allow_client_fallback": fallback_enabled,
            },
            status="FAILED",
            error_message="No FRED series returned usable observations.",
            run_id=run_id,
        )
        raise RuntimeError(
            "No FRED data were downloaded. Review "
            "data/manifests/fred_download_status.csv."
        )

    fred_data = pd.concat(frames, ignore_index=True)
    fred_data = fred_data[
        [
            "date",
            "series_id",
            "value",
            "source",
            "client",
            "run_id",
            "download_timestamp_utc",
        ]
    ].sort_values(["series_id", "date"], kind="mergesort")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fred_data.to_parquet(output_path, index=False)

    record_dataset(
        dataset_name="fred_series_raw",
        dataset_path=output_path,
        root=project_root,
        request_parameters={
            "series": series_ids,
            "start_date": start_date,
            "end_date": end_date,
            "allow_client_fallback": fallback_enabled,
        },
        run_id=run_id,
    )

    return fred_data, status_frame


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-client-fallback",
        action="store_true",
        help="Do not use pandas-datareader when the direct FRED call fails.",
    )
    args = parser.parse_args()

    fred_data, status = download_fred_data(
        allow_client_fallback=not args.no_client_fallback
    )
    print(
        "FRED download completed: "
        f"{len(fred_data):,} rows, "
        f"{fred_data['series_id'].nunique()} series."
    )
    print(status[["series_id", "selected_client", "row_count"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

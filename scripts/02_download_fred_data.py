"""Download configured FRED series through the official HTTPS REST API."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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


def build_session(retries: int, backoff_factor: float) -> requests.Session:
    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        status=retries,
        backoff_factor=backoff_factor,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    return session


def request_json(
    session: requests.Session,
    url: str,
    params: dict[str, object],
    timeout_seconds: float,
) -> dict[str, object]:
    response = session.get(url, params=params, timeout=timeout_seconds)
    if response.status_code != 200:
        safe_params = {key: value for key, value in params.items() if key != "api_key"}
        raise RuntimeError(
            f"FRED request failed with HTTP {response.status_code}; "
            f"endpoint={url}; parameters={safe_params}; response={response.text[:500]}"
        )
    payload = response.json()
    if "error_code" in payload:
        raise RuntimeError(f"FRED API error: {payload.get('error_message', payload)}")
    return payload


def main() -> int:
    ensure_directories()
    load_dotenv(ROOT / ".env")
    api_key = os.getenv("FRED_API_KEY", "").strip()
    if not api_key or api_key == "your_key_here":
        raise RuntimeError(
            "FRED_API_KEY is missing. Copy .env.example to .env and place the real key in .env."
        )

    project_config, data_config = load_configs()
    start_date = str(project_config["data"]["start_date"])
    end_date = configured_observation_end(project_config["data"].get("end_date"))

    fred_settings = data_config["fred"]
    download_settings = fred_settings["download"]
    base_url = str(fred_settings["base_url"]).rstrip("/")
    session = build_session(
        retries=int(download_settings["retries"]),
        backoff_factor=float(download_settings["backoff_factor"]),
    )
    timeout_seconds = float(download_settings["timeout_seconds"])

    raw_directory = ROOT / "data" / "raw" / "macro"
    manifest_rows: list[dict[str, object]] = []
    metadata_rows: list[dict[str, object]] = []
    combined_frames: list[pd.DataFrame] = []

    for series_id, configured_metadata in fred_settings["series"].items():
        series_id = str(series_id)
        LOGGER.info("Downloading FRED series %s", series_id)

        metadata_payload = request_json(
            session,
            f"{base_url}/series",
            {"series_id": series_id, "api_key": api_key, "file_type": "json"},
            timeout_seconds,
        )
        series_metadata = metadata_payload.get("seriess", [])
        if not series_metadata:
            raise RuntimeError(f"No FRED metadata returned for {series_id}")
        metadata = dict(series_metadata[0])

        observations_payload = request_json(
            session,
            f"{base_url}/series/observations",
            {
                "series_id": series_id,
                "api_key": api_key,
                "file_type": "json",
                "observation_start": start_date,
                "observation_end": end_date,
                "sort_order": "asc",
            },
            timeout_seconds,
        )
        observations = observations_payload.get("observations", [])
        if not observations:
            raise RuntimeError(f"No FRED observations returned for {series_id}")

        frame = pd.DataFrame(observations)
        required = {"date", "value"}
        missing = required.difference(frame.columns)
        if missing:
            raise RuntimeError(f"FRED response for {series_id} lacks columns {sorted(missing)}")

        frame["date"] = pd.to_datetime(frame["date"], errors="raise")
        frame["value"] = pd.to_numeric(frame["value"].replace(".", pd.NA), errors="coerce")
        frame["series_id"] = series_id
        frame["source"] = "fred_rest_api"
        frame["retrieved_at_utc"] = utc_now_iso()
        frame = frame[
            [
                "series_id",
                "date",
                "value",
                "realtime_start",
                "realtime_end",
                "source",
                "retrieved_at_utc",
            ]
        ].sort_values("date")

        output_path = raw_directory / f"{series_id}.parquet"
        frame.to_parquet(output_path, index=False)
        combined_frames.append(frame)

        manifest_rows.append(
            {
                "series_id": series_id,
                "configured_description": configured_metadata["description"],
                "configured_expected_frequency": configured_metadata["expected_frequency"],
                "file": relative_path(output_path),
                "sha256": sha256_file(output_path),
                "observations": int(len(frame)),
                "nonmissing_observations": int(frame["value"].notna().sum()),
                "first_date": frame["date"].min().date().isoformat(),
                "last_date": frame["date"].max().date().isoformat(),
                "vintage_policy": fred_settings["vintage_policy"],
                "retrieved_at_utc": frame["retrieved_at_utc"].iloc[0],
            }
        )

        metadata_rows.append(
            {
                "series_id": series_id,
                "title": metadata.get("title"),
                "frequency": metadata.get("frequency"),
                "units": metadata.get("units"),
                "seasonal_adjustment": metadata.get("seasonal_adjustment"),
                "observation_start": metadata.get("observation_start"),
                "observation_end": metadata.get("observation_end"),
                "last_updated": metadata.get("last_updated"),
                "notes": metadata.get("notes"),
            }
        )

    combined = pd.concat(combined_frames, ignore_index=True)
    combined_path = raw_directory / "fred_series_raw.parquet"
    combined.to_parquet(combined_path, index=False)

    manifest = pd.DataFrame(manifest_rows).sort_values("series_id")
    manifest_path = ROOT / "data" / "manifests" / "fred_data_manifest.csv"
    manifest.to_csv(manifest_path, index=False)

    metadata_frame = pd.DataFrame(metadata_rows).sort_values("series_id")
    metadata_frame.to_csv(ROOT / "data" / "manifests" / "fred_series_metadata.csv", index=False)

    dictionary = pd.DataFrame(
        [
            ("series_id", "string", "FRED series identifier."),
            ("date", "date", "Observation date."),
            ("value", "float", "Numeric observation; FRED period markers are converted to missing."),
            ("realtime_start", "date", "Beginning of the FRED real-time period."),
            ("realtime_end", "date", "End of the FRED real-time period."),
            ("source", "string", "Data-provider lineage."),
            ("retrieved_at_utc", "string", "UTC retrieval timestamp."),
        ],
        columns=["field", "type", "definition"],
    )
    dictionary.to_csv(ROOT / "data" / "manifests" / "fred_data_dictionary.csv", index=False)

    write_json(
        ROOT / "data" / "manifests" / "fred_download_summary.json",
        {
            "status": "completed",
            "start_date": start_date,
            "end_date": end_date,
            "vintage_policy": fred_settings["vintage_policy"],
            "series_completed": manifest["series_id"].tolist(),
            "total_observations": int(len(combined)),
            "combined_file": relative_path(combined_path),
            "combined_sha256": sha256_file(combined_path),
            "manifest_file": relative_path(manifest_path),
            "manifest_sha256": sha256_file(manifest_path),
            "generated_at_utc": utc_now_iso(),
        },
    )
    LOGGER.info("FRED download completed for %d series", len(manifest))
    return 0


if __name__ == "__main__":
    sys.exit(main())

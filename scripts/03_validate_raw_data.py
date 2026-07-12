"""Validate raw market and FRED data and preserve all findings."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

from _data_pipeline_common import (
    ROOT,
    configure_logging,
    configured_observation_end,
    ensure_directories,
    load_configs,
    relative_path,
    utc_now_iso,
    write_json,
)

SCRIPT = Path(__file__).stem
LOGGER = configure_logging(SCRIPT)

MARKET_REQUIRED_COLUMNS = {
    "date",
    "ticker",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "dividends",
    "stock_splits",
    "capital_gains",
    "source",
    "retrieved_at_utc",
}
FRED_REQUIRED_COLUMNS = {
    "series_id",
    "date",
    "value",
    "realtime_start",
    "realtime_end",
    "source",
    "retrieved_at_utc",
}


def finding(
    findings: list[dict[str, object]],
    dataset: str,
    item: str,
    check: str,
    severity: str,
    status: str,
    observed: object,
    threshold: object,
    detail: str,
) -> None:
    findings.append(
        {
            "dataset": dataset,
            "item": item,
            "check": check,
            "severity": severity,
            "status": status,
            "observed": observed,
            "threshold": threshold,
            "detail": detail,
        }
    )


def main() -> int:
    ensure_directories()
    project_config, data_config = load_configs()
    findings: list[dict[str, object]] = []

    start_date = pd.Timestamp(project_config["data"]["start_date"])
    end_date = pd.Timestamp(configured_observation_end(project_config["data"].get("end_date")))
    minimum_completeness = float(project_config["data"]["minimum_completeness"])

    market_settings = data_config["market_data"]
    market_directory = ROOT / "data" / "raw" / "market"
    max_staleness = int(market_settings["validation"]["max_staleness_calendar_days"])
    min_volume_fraction = float(
        market_settings["validation"]["minimum_nonmissing_volume_fraction"]
    )

    for ticker in [str(item).upper() for item in market_settings["tickers"]]:
        path = market_directory / f"{ticker}.parquet"
        if not path.exists():
            finding(
                findings,
                "market",
                ticker,
                "file_exists",
                "ERROR",
                "FAIL",
                False,
                True,
                f"Missing raw file: {relative_path(path)}",
            )
            continue

        frame = pd.read_parquet(path)
        missing_columns = sorted(MARKET_REQUIRED_COLUMNS.difference(frame.columns))
        finding(
            findings,
            "market",
            ticker,
            "required_columns",
            "ERROR",
            "PASS" if not missing_columns else "FAIL",
            missing_columns,
            [],
            "All required market fields must be retained.",
        )
        if missing_columns:
            continue

        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        row_count = len(frame)
        finding(
            findings,
            "market",
            ticker,
            "nonempty",
            "ERROR",
            "PASS" if row_count > 0 else "FAIL",
            row_count,
            "> 0",
            "Raw ticker file must contain observations.",
        )
        if row_count == 0:
            continue

        duplicates = int(frame.duplicated(["ticker", "date"]).sum())
        finding(
            findings,
            "market",
            ticker,
            "unique_ticker_date",
            "ERROR",
            "PASS" if duplicates == 0 else "FAIL",
            duplicates,
            0,
            "Duplicate ticker-date rows are prohibited.",
        )

        invalid_dates = int(frame["date"].isna().sum())
        finding(
            findings,
            "market",
            ticker,
            "valid_dates",
            "ERROR",
            "PASS" if invalid_dates == 0 else "FAIL",
            invalid_dates,
            0,
            "Dates must parse without coercion failures.",
        )

        for price_column in ("open", "high", "low", "close", "adj_close"):
            values = pd.to_numeric(frame[price_column], errors="coerce")
            nonpositive = int((values.dropna() <= 0).sum())
            finding(
                findings,
                "market",
                ticker,
                f"positive_{price_column}",
                "ERROR",
                "PASS" if nonpositive == 0 else "FAIL",
                nonpositive,
                0,
                f"{price_column} must be positive when present.",
            )

        volume = pd.to_numeric(frame["volume"], errors="coerce")
        negative_volume = int((volume.dropna() < 0).sum())
        finding(
            findings,
            "market",
            ticker,
            "nonnegative_volume",
            "ERROR",
            "PASS" if negative_volume == 0 else "FAIL",
            negative_volume,
            0,
            "Trading volume cannot be negative.",
        )

        adj_completeness = float(frame["adj_close"].notna().mean())
        finding(
            findings,
            "market",
            ticker,
            "adjusted_close_completeness",
            "ERROR",
            "PASS" if adj_completeness >= minimum_completeness else "FAIL",
            round(adj_completeness, 8),
            minimum_completeness,
            "Adjusted-close completeness must meet the project threshold.",
        )

        volume_completeness = float(volume.notna().mean())
        finding(
            findings,
            "market",
            ticker,
            "volume_completeness",
            "WARNING",
            "PASS" if volume_completeness >= min_volume_fraction else "FAIL",
            round(volume_completeness, 8),
            min_volume_fraction,
            "Volume completeness is monitored separately from price completeness.",
        )

        first_date = frame["date"].min()
        last_date = frame["date"].max()
        finding(
            findings,
            "market",
            ticker,
            "date_range_start",
            "WARNING",
            "PASS" if first_date <= start_date + pd.Timedelta(days=10) else "FAIL",
            first_date.date().isoformat(),
            f"on or near {start_date.date().isoformat()}",
            "A later first date can reduce the common historical window.",
        )

        # Only apply staleness to an open-ended run; historical snapshots are not stale.
        if project_config["data"].get("end_date") in (None, "", "null"):
            staleness_days = (pd.Timestamp(date.today()) - last_date.normalize()).days
            finding(
                findings,
                "market",
                ticker,
                "latest_observation_staleness",
                "WARNING",
                "PASS" if staleness_days <= max_staleness else "FAIL",
                staleness_days,
                f"<= {max_staleness}",
                "Calendar-day tolerance accommodates weekends and market holidays.",
            )

        outside_range = int(((frame["date"] < start_date) | (frame["date"] > end_date)).sum())
        finding(
            findings,
            "market",
            ticker,
            "configured_date_range",
            "ERROR",
            "PASS" if outside_range == 0 else "FAIL",
            outside_range,
            0,
            "Raw observations must remain within the configured inclusive date range.",
        )

    fred_settings = data_config["fred"]
    fred_directory = ROOT / "data" / "raw" / "macro"
    for series_id in fred_settings["series"]:
        series_id = str(series_id)
        path = fred_directory / f"{series_id}.parquet"
        if not path.exists():
            finding(
                findings,
                "fred",
                series_id,
                "file_exists",
                "ERROR",
                "FAIL",
                False,
                True,
                f"Missing raw file: {relative_path(path)}",
            )
            continue

        frame = pd.read_parquet(path)
        missing_columns = sorted(FRED_REQUIRED_COLUMNS.difference(frame.columns))
        finding(
            findings,
            "fred",
            series_id,
            "required_columns",
            "ERROR",
            "PASS" if not missing_columns else "FAIL",
            missing_columns,
            [],
            "All required FRED fields must be retained.",
        )
        if missing_columns:
            continue

        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        finding(
            findings,
            "fred",
            series_id,
            "nonempty",
            "ERROR",
            "PASS" if len(frame) > 0 else "FAIL",
            len(frame),
            "> 0",
            "Raw series file must contain observations.",
        )
        duplicates = int(frame.duplicated(["series_id", "date"]).sum())
        finding(
            findings,
            "fred",
            series_id,
            "unique_series_date",
            "ERROR",
            "PASS" if duplicates == 0 else "FAIL",
            duplicates,
            0,
            "Duplicate FRED series-date rows are prohibited.",
        )
        nonmissing = int(pd.to_numeric(frame["value"], errors="coerce").notna().sum())
        finding(
            findings,
            "fred",
            series_id,
            "numeric_observations_present",
            "ERROR",
            "PASS" if nonmissing > 0 else "FAIL",
            nonmissing,
            "> 0",
            "At least one numeric observation is required.",
        )
        missing_fraction = float(frame["value"].isna().mean()) if len(frame) else 1.0
        finding(
            findings,
            "fred",
            series_id,
            "missing_value_fraction",
            "WARNING",
            "PASS" if missing_fraction <= 0.05 else "FAIL",
            round(missing_fraction, 8),
            "<= 0.05",
            "FRED period markers and non-publication dates may create missing values.",
        )

    results = pd.DataFrame(findings)
    results["validated_at_utc"] = utc_now_iso()
    output_csv = ROOT / "reports" / "evidence" / "raw_data_validation.csv"
    results.to_csv(output_csv, index=False)

    error_failures = results[
        (results["severity"] == "ERROR") & (results["status"] == "FAIL")
    ]
    warning_failures = results[
        (results["severity"] == "WARNING") & (results["status"] == "FAIL")
    ]

    summary = {
        "status": "failed" if len(error_failures) else "passed",
        "checks": int(len(results)),
        "error_failures": int(len(error_failures)),
        "warning_failures": int(len(warning_failures)),
        "validation_file": relative_path(output_csv),
        "validated_at_utc": utc_now_iso(),
    }
    write_json(ROOT / "reports" / "evidence" / "raw_data_validation_summary.json", summary)
    write_json(ROOT / "data" / "manifests" / "raw_data_quality_summary.json", summary)

    LOGGER.info(
        "Raw-data validation completed: %d error failures, %d warning failures",
        len(error_failures),
        len(warning_failures),
    )
    if len(error_failures):
        LOGGER.error("Validation failed. Review %s", relative_path(output_csv))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

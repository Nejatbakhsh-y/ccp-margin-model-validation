"""Run independent market-data quality controls and preserve exceptions."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from ccp_margin.data.manifests import (
    MANIFEST_COLUMNS,
    find_project_root,
    load_project_config,
    make_run_id,
    utc_now,
)


EXCEPTION_COLUMNS = [
    "run_id",
    "check_id",
    "check_name",
    "severity",
    "security_id",
    "date",
    "field",
    "observed_value",
    "threshold",
    "message",
]

CHECK_DEFINITIONS = [
    (
        "DQ001",
        "Duplicate dates within a security and source",
        "HIGH",
        "No security/source combination may contain repeated dates.",
    ),
    (
        "DQ002",
        "Duplicate security-date rows",
        "HIGH",
        "Each security-date key must be unique before cleaning.",
    ),
    (
        "DQ003",
        "Missing prices",
        "HIGH",
        "Model-price completeness must satisfy the configured minimum.",
    ),
    (
        "DQ004",
        "Non-positive prices",
        "CRITICAL",
        "Adjusted prices used by the model must be strictly positive.",
    ),
    (
        "DQ005",
        "Missing volume",
        "MEDIUM",
        "Volume must be available unless explicitly documented as unavailable.",
    ),
    (
        "DQ006",
        "Stale prices",
        "MEDIUM",
        "Repeated unchanged prices must not exceed the configured stale run.",
    ),
    (
        "DQ007",
        "Extreme returns",
        "HIGH",
        "Absolute one-day returns above the configured threshold require review.",
    ),
    (
        "DQ008",
        "Corporate-action discontinuities",
        "HIGH",
        "Large price jumps or adjustment-ratio changes require review.",
    ),
    (
        "DQ009",
        "Inconsistent calendars",
        "MEDIUM",
        "Each security must align sufficiently with the reference calendar.",
    ),
    (
        "DQ010",
        "Insufficient history",
        "HIGH",
        "Each security must meet the configured minimum valid-price history.",
    ),
    (
        "DQ011",
        "Unavailable primary data source",
        "HIGH",
        "Requested securities must have a usable primary or approved fallback source.",
    ),
    (
        "DQ012",
        "Alternative-source behavior",
        "MEDIUM",
        "Fallback use and fallback failure must be explicitly evidenced.",
    ),
    (
        "DQ013",
        "Reproducibility of downloads",
        "HIGH",
        "Comparable reruns must not change unexplained historical content.",
    ),
    (
        "DQ014",
        "Data manifest completeness",
        "HIGH",
        "Current manifest records must contain all required evidence fields.",
    ),
]


def _empty_exceptions() -> pd.DataFrame:
    return pd.DataFrame(columns=EXCEPTION_COLUMNS)


def _exception_frame(
    rows: pd.DataFrame,
    *,
    run_id: str,
    check_id: str,
    check_name: str,
    severity: str,
    field: str,
    threshold: str,
    message_builder: Callable[[pd.Series], str],
    value_column: str | None = None,
) -> pd.DataFrame:
    if rows.empty:
        return _empty_exceptions()

    output = pd.DataFrame()
    output["run_id"] = run_id
    output["check_id"] = check_id
    output["check_name"] = check_name
    output["severity"] = severity
    output["security_id"] = rows.get(
        "security_id", rows.get("series_id", "")
    ).astype(str)
    if "date" in rows.columns:
        output["date"] = pd.to_datetime(
            rows["date"], errors="coerce"
        ).dt.strftime("%Y-%m-%d")
    else:
        output["date"] = ""
    output["field"] = field

    if value_column and value_column in rows.columns:
        output["observed_value"] = rows[value_column].astype(str).values
    else:
        output["observed_value"] = ""

    output["threshold"] = threshold
    output["message"] = rows.apply(message_builder, axis=1).values
    return output[EXCEPTION_COLUMNS]


def _single_exception(
    *,
    run_id: str,
    check_id: str,
    check_name: str,
    severity: str,
    field: str,
    observed_value: str,
    threshold: str,
    message: str,
    security_id: str = "",
    date: str = "",
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "run_id": run_id,
                "check_id": check_id,
                "check_name": check_name,
                "severity": severity,
                "security_id": security_id,
                "date": date,
                "field": field,
                "observed_value": observed_value,
                "threshold": threshold,
                "message": message,
            }
        ],
        columns=EXCEPTION_COLUMNS,
    )


def run_quality_checks(
    *,
    root: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    project_root = root or find_project_root()
    config = load_project_config(project_root)
    data_config: dict[str, Any] = config["data"]
    quality_config: dict[str, Any] = data_config.get("quality", {})

    minimum_completeness = float(
        data_config.get("minimum_completeness", 0.995)
    )
    stale_days = int(quality_config.get("stale_price_days", 5))
    extreme_return = float(
        quality_config.get("extreme_absolute_return", 0.20)
    )
    corporate_return = float(
        quality_config.get(
            "corporate_action_absolute_return",
            0.50,
        )
    )
    adjustment_ratio_change = float(
        quality_config.get("adjustment_ratio_change", 0.20)
    )
    calendar_gap_ratio = float(
        quality_config.get("maximum_calendar_gap_ratio", 0.01)
    )

    primary_lookback = int(
        config.get("primary_model", {}).get("lookback_days", 500)
    )
    minimum_history = int(
        quality_config.get("minimum_history_rows", primary_lookback)
    )

    raw_path = (
        project_root / "data" / "raw" / "market" / "market_prices_raw.parquet"
    )
    clean_path = (
        project_root
        / "data"
        / "processed"
        / "market_prices_clean.parquet"
    )
    status_path = (
        project_root / "data" / "manifests" / "market_download_status.csv"
    )
    manifest_path = (
        project_root / "data" / "manifests" / "market_data_manifest.csv"
    )

    missing_inputs = [
        str(path)
        for path in (raw_path, clean_path, status_path, manifest_path)
        if not path.exists()
    ]
    if missing_inputs:
        raise FileNotFoundError(
            "Required Step 8 inputs are missing:\n- "
            + "\n- ".join(missing_inputs)
        )

    raw = pd.read_parquet(raw_path)
    clean = pd.read_parquet(clean_path)
    status = pd.read_csv(status_path)
    manifest = pd.read_csv(manifest_path, dtype=str).fillna("")

    raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
    clean["date"] = pd.to_datetime(clean["date"], errors="coerce")
    run_id = make_run_id()

    definition_lookup = {
        check_id: (name, severity, description)
        for check_id, name, severity, description in CHECK_DEFINITIONS
    }
    results: dict[str, pd.DataFrame] = {}

    name, severity, _ = definition_lookup["DQ001"]
    duplicate_dates = raw[
        raw.duplicated(
            ["security_id", "source", "date"],
            keep=False,
        )
    ].copy()
    results["DQ001"] = _exception_frame(
        duplicate_dates,
        run_id=run_id,
        check_id="DQ001",
        check_name=name,
        severity=severity,
        field="date",
        threshold="0 duplicate dates",
        value_column="date",
        message_builder=lambda row: (
            f"{row['security_id']} has a repeated {row['date'].date()} "
            f"observation from {row['source']}."
        ),
    )

    name, severity, _ = definition_lookup["DQ002"]
    duplicate_keys = raw[
        raw.duplicated(["security_id", "date"], keep=False)
    ].copy()
    results["DQ002"] = _exception_frame(
        duplicate_keys,
        run_id=run_id,
        check_id="DQ002",
        check_name=name,
        severity=severity,
        field="security_id,date",
        threshold="unique key",
        value_column="source",
        message_builder=lambda row: (
            f"Duplicate security-date key for {row['security_id']} "
            f"on {row['date'].date()}."
        ),
    )

    name, severity, _ = definition_lookup["DQ003"]
    if "active_history" in clean.columns:
        completeness_scope = clean[clean["active_history"]].copy()
    else:
        completeness_scope = clean.copy()

    missing_prices = completeness_scope[
        completeness_scope["model_price"].isna()
    ].copy()
    completeness = (
        completeness_scope.groupby("security_id")["model_price"]
        .apply(lambda values: float(values.notna().mean()))
        .rename("completeness")
        .reset_index()
    )
    incomplete = completeness[
        completeness["completeness"] < minimum_completeness
    ]
    results["DQ003"] = _exception_frame(
        incomplete,
        run_id=run_id,
        check_id="DQ003",
        check_name=name,
        severity=severity,
        field="active_history_model_price_completeness",
        threshold=f">={minimum_completeness:.4f}",
        value_column="completeness",
        message_builder=lambda row: (
            f"{row['security_id']} active-history completeness is "
            f"{float(row['completeness']):.4%}; "
            f"{len(missing_prices[missing_prices['security_id'] == row['security_id']])} "
            "active-history price observations are missing. "
            "Pre-inception dates are excluded."
        ),
    )

    name, severity, _ = definition_lookup["DQ004"]
    non_positive = raw[
        raw["adjusted_close"].notna()
        & (pd.to_numeric(raw["adjusted_close"], errors="coerce") <= 0)
    ].copy()
    results["DQ004"] = _exception_frame(
        non_positive,
        run_id=run_id,
        check_id="DQ004",
        check_name=name,
        severity=severity,
        field="adjusted_close",
        threshold="> 0",
        value_column="adjusted_close",
        message_builder=lambda row: (
            f"{row['security_id']} has a non-positive adjusted price."
        ),
    )

    name, severity, _ = definition_lookup["DQ005"]
    missing_volume = raw[raw["volume"].isna()].copy()
    results["DQ005"] = _exception_frame(
        missing_volume,
        run_id=run_id,
        check_id="DQ005",
        check_name=name,
        severity=severity,
        field="volume",
        threshold="not missing",
        value_column="volume",
        message_builder=lambda row: (
            f"{row['security_id']} is missing volume on "
            f"{row['date'].date()}."
        ),
    )

    name, severity, _ = definition_lookup["DQ006"]
    stale = clean[
        clean["stale_run_length"] >= stale_days
    ].copy()
    results["DQ006"] = _exception_frame(
        stale,
        run_id=run_id,
        check_id="DQ006",
        check_name=name,
        severity=severity,
        field="model_price",
        threshold=f"stale run < {stale_days}",
        value_column="stale_run_length",
        message_builder=lambda row: (
            f"{row['security_id']} price has been unchanged for "
            f"{int(row['stale_run_length'])} reference-calendar observations."
        ),
    )

    name, severity, _ = definition_lookup["DQ007"]
    extreme = clean[
        clean["return_1d"].abs() > extreme_return
    ].copy()
    results["DQ007"] = _exception_frame(
        extreme,
        run_id=run_id,
        check_id="DQ007",
        check_name=name,
        severity=severity,
        field="return_1d",
        threshold=f"absolute return <= {extreme_return:.2%}",
        value_column="return_1d",
        message_builder=lambda row: (
            f"{row['security_id']} one-day return is "
            f"{float(row['return_1d']):.2%}."
        ),
    )

    name, severity, _ = definition_lookup["DQ008"]
    corporate = clean[
        (clean["return_1d"].abs() > corporate_return)
        | (
            clean["adjustment_ratio_change"].abs()
            > adjustment_ratio_change
        )
    ].copy()
    corporate["corporate_signal"] = np.where(
        corporate["return_1d"].abs() > corporate_return,
        corporate["return_1d"],
        corporate["adjustment_ratio_change"],
    )
    results["DQ008"] = _exception_frame(
        corporate,
        run_id=run_id,
        check_id="DQ008",
        check_name=name,
        severity=severity,
        field="return_or_adjustment_ratio",
        threshold=(
            f"return <= {corporate_return:.2%} and adjustment-ratio "
            f"change <= {adjustment_ratio_change:.2%}"
        ),
        value_column="corporate_signal",
        message_builder=lambda row: (
            f"{row['security_id']} has a possible unadjusted corporate-action "
            "discontinuity."
        ),
    )

    name, severity, _ = definition_lookup["DQ009"]
    if "active_history" in clean.columns:
        calendar_scope = clean[clean["active_history"]].copy()
    else:
        calendar_scope = clean.copy()

    calendar_summary = (
        calendar_scope.groupby("security_id")["calendar_gap"]
        .mean()
        .rename("calendar_gap_ratio")
        .reset_index()
    )
    inconsistent = calendar_summary[
        calendar_summary["calendar_gap_ratio"] > calendar_gap_ratio
    ]
    results["DQ009"] = _exception_frame(
        inconsistent,
        run_id=run_id,
        check_id="DQ009",
        check_name=name,
        severity=severity,
        field="active_history_calendar_gap_ratio",
        threshold=f"<= {calendar_gap_ratio:.2%}",
        value_column="calendar_gap_ratio",
        message_builder=lambda row: (
            f"{row['security_id']} is absent from "
            f"{float(row['calendar_gap_ratio']):.2%} of active-history "
            "reference-calendar dates. Pre-inception dates are excluded."
        ),
    )

    name, severity, _ = definition_lookup["DQ010"]
    history = (
        clean.groupby("security_id")["model_price"]
        .count()
        .rename("valid_history_rows")
        .reset_index()
    )
    insufficient = history[
        history["valid_history_rows"] < minimum_history
    ]
    results["DQ010"] = _exception_frame(
        insufficient,
        run_id=run_id,
        check_id="DQ010",
        check_name=name,
        severity=severity,
        field="valid_history_rows",
        threshold=f">= {minimum_history}",
        value_column="valid_history_rows",
        message_builder=lambda row: (
            f"{row['security_id']} has only "
            f"{int(row['valid_history_rows'])} valid price observations."
        ),
    )

    name, severity, _ = definition_lookup["DQ011"]
    unavailable = status[
        status["selected_source"].fillna("").astype(str).str.strip().eq("")
    ].copy()
    results["DQ011"] = _exception_frame(
        unavailable,
        run_id=run_id,
        check_id="DQ011",
        check_name=name,
        severity=severity,
        field="selected_source",
        threshold="usable source required",
        value_column="error_message",
        message_builder=lambda row: (
            f"No usable market-data source was available for "
            f"{row['security_id']}: {row['error_message']}"
        ),
    )

    name, severity, _ = definition_lookup["DQ012"]
    fallback_rows = status[
        status["fallback_attempted"].astype(str).str.lower().isin(
            {"true", "1", "yes"}
        )
    ].copy()
    results["DQ012"] = _exception_frame(
        fallback_rows,
        run_id=run_id,
        check_id="DQ012",
        check_name=name,
        severity=severity,
        field="fallback_status",
        threshold="fallback must be tagged and reviewed",
        value_column="fallback_status",
        message_builder=lambda row: (
            f"{row['security_id']} required fallback handling; "
            f"status={row['fallback_status']}, "
            f"selected_source={row['selected_source']}."
        ),
    )

    name, severity, _ = definition_lookup["DQ013"]
    latest_manifest = (
        manifest.sort_values("generated_at_utc")
        .groupby("dataset_name", as_index=False)
        .tail(1)
    )
    changed = latest_manifest[
        latest_manifest["reproducibility_status"]
        == "CHANGED_SAME_PERIOD"
    ].copy()
    if not changed.empty:
        changed = changed.rename(columns={"dataset_name": "security_id"})
    results["DQ013"] = _exception_frame(
        changed,
        run_id=run_id,
        check_id="DQ013",
        check_name=name,
        severity=severity,
        field="content_sha256",
        threshold="MATCH for comparable reruns",
        value_column="content_sha256",
        message_builder=lambda row: (
            f"{row['security_id']} changed for a comparable request and "
            "date range; investigate source revisions or nondeterminism."
        ),
    )

    name, severity, _ = definition_lookup["DQ014"]
    manifest_exceptions: list[pd.DataFrame] = []
    missing_manifest_columns = [
        column for column in MANIFEST_COLUMNS if column not in manifest.columns
    ]
    if missing_manifest_columns:
        manifest_exceptions.append(
            _single_exception(
                run_id=run_id,
                check_id="DQ014",
                check_name=name,
                severity=severity,
                field="manifest_columns",
                observed_value="|".join(missing_manifest_columns),
                threshold="all required columns present",
                message="The data manifest is missing required columns.",
            )
        )
    else:
        required_value_columns = [
            "run_id",
            "dataset_name",
            "file_path",
            "file_format",
            "row_count",
            "column_count",
            "content_sha256",
            "schema_sha256",
            "config_sha256",
            "request_sha256",
            "generated_at_utc",
            "status",
        ]
        latest = (
            manifest.sort_values("generated_at_utc")
            .groupby("dataset_name", as_index=False)
            .tail(1)
        )
        for _, row in latest.iterrows():
            missing_values = [
                column
                for column in required_value_columns
                if not str(row.get(column, "")).strip()
            ]
            if missing_values:
                manifest_exceptions.append(
                    _single_exception(
                        run_id=run_id,
                        check_id="DQ014",
                        check_name=name,
                        severity=severity,
                        field="manifest_values",
                        observed_value="|".join(missing_values),
                        threshold="all required values populated",
                        message=(
                            f"Latest manifest record for "
                            f"{row.get('dataset_name', '')} is incomplete."
                        ),
                        security_id=str(row.get("dataset_name", "")),
                    )
                )

            stored_path = str(row.get("file_path", "")).strip()
            if stored_path:
                candidate = Path(stored_path)
                if not candidate.is_absolute():
                    candidate = project_root / candidate
                if str(row.get("status", "")) == "SUCCESS" and not candidate.exists():
                    manifest_exceptions.append(
                        _single_exception(
                            run_id=run_id,
                            check_id="DQ014",
                            check_name=name,
                            severity=severity,
                            field="file_path",
                            observed_value=stored_path,
                            threshold="file exists",
                            message=(
                                f"Manifested dataset file does not exist: "
                                f"{stored_path}"
                            ),
                            security_id=str(row.get("dataset_name", "")),
                        )
                    )

    results["DQ014"] = (
        pd.concat(manifest_exceptions, ignore_index=True)
        if manifest_exceptions
        else _empty_exceptions()
    )

    exception_frames = [results[check_id] for check_id, *_ in CHECK_DEFINITIONS]
    exceptions = pd.concat(exception_frames, ignore_index=True)
    if exceptions.empty:
        exceptions = _empty_exceptions()

    summaries: list[dict[str, Any]] = []
    for check_id, check_name, severity, description in CHECK_DEFINITIONS:
        check_exceptions = results[check_id]
        exception_count = int(len(check_exceptions))
        affected_security_count = int(
            check_exceptions["security_id"]
            .replace("", np.nan)
            .dropna()
            .nunique()
        )
        if exception_count == 0:
            status_value = "PASS"
        elif severity in {"CRITICAL", "HIGH"}:
            status_value = "FAIL"
        else:
            status_value = "WARN"

        summaries.append(
            {
                "run_id": run_id,
                "check_id": check_id,
                "check_name": check_name,
                "severity": severity,
                "status": status_value,
                "exception_count": exception_count,
                "affected_security_count": affected_security_count,
                "description": description,
                "evaluated_at_utc": utc_now(),
            }
        )

    summary = pd.DataFrame(summaries)

    summary_path = (
        project_root / "reports" / "tables" / "data_quality_summary.csv"
    )
    exceptions_path = (
        project_root
        / "reports"
        / "evidence"
        / "data_quality_exceptions.csv"
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    exceptions_path.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(summary_path, index=False)
    exceptions.to_csv(exceptions_path, index=False)

    return summary, exceptions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return a non-zero exit code when a CRITICAL or HIGH check fails.",
    )
    args = parser.parse_args()

    summary, exceptions = run_quality_checks()
    print(summary.to_string(index=False))
    print(f"\nExceptions preserved: {len(exceptions):,}")

    if args.strict:
        blocking = summary[
            summary["severity"].isin(["CRITICAL", "HIGH"])
            & summary["status"].eq("FAIL")
        ]
        return 1 if not blocking.empty else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

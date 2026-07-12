"""Dataset-manifest utilities for the CCP margin validation project."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import yaml


MANIFEST_COLUMNS = [
    "run_id",
    "dataset_name",
    "file_path",
    "file_format",
    "row_count",
    "column_count",
    "minimum_date",
    "maximum_date",
    "security_count",
    "source_list",
    "content_sha256",
    "schema_sha256",
    "config_sha256",
    "request_sha256",
    "generated_at_utc",
    "reproducibility_status",
    "previous_content_sha256",
    "status",
    "error_message",
]


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def make_run_id() -> str:
    """Create a compact run identifier."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def find_project_root(start: Path | None = None) -> Path:
    """Locate the repository root by searching for configs/project.yaml."""
    candidates: list[Path] = []

    if start is not None:
        candidates.append(Path(start).resolve())

    candidates.extend(
        [
            Path.cwd().resolve(),
            Path(__file__).resolve().parents[3],
        ]
    )

    checked: set[Path] = set()
    for candidate in candidates:
        for path in [candidate, *candidate.parents]:
            if path in checked:
                continue
            checked.add(path)
            if (path / "configs" / "project.yaml").exists():
                return path

    raise FileNotFoundError(
        "Could not locate the project root. Expected configs/project.yaml."
    )


def load_project_config(root: Path | None = None) -> dict[str, Any]:
    """Load configs/project.yaml and validate the top-level data section."""
    project_root = root or find_project_root()
    config_path = project_root / "configs" / "project.yaml"

    with config_path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}

    if "data" not in config or not isinstance(config["data"], dict):
        raise KeyError(
            "configs/project.yaml must contain a top-level 'data:' mapping."
        )

    return config


def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Calculate a SHA-256 hash for a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def json_sha256(value: Any) -> str:
    """Hash a JSON-serializable value deterministically."""
    payload = json.dumps(
        value,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def dataframe_content_sha256(
    frame: pd.DataFrame,
    *,
    exclude_columns: Iterable[str] = (
        "download_timestamp_utc",
        "generated_at_utc",
        "run_id",
    ),
) -> str:
    """Hash normalized tabular content while excluding volatile run metadata."""
    normalized = frame.copy()
    volatile_columns = {
        column
        for column in normalized.columns
        if column in set(exclude_columns)
        or column.endswith("_timestamp_utc")
        or column.endswith("_run_id")
    }
    normalized = normalized.drop(
        columns=sorted(volatile_columns),
        errors="ignore",
    )

    for column in normalized.columns:
        if pd.api.types.is_datetime64_any_dtype(normalized[column]):
            normalized[column] = normalized[column].dt.strftime(
                "%Y-%m-%dT%H:%M:%S"
            )
        elif pd.api.types.is_float_dtype(normalized[column]):
            normalized[column] = normalized[column].round(12)

    sort_columns = [
        c
        for c in ("security_id", "series_id", "date", "source")
        if c in normalized.columns
    ]
    if sort_columns:
        normalized = normalized.sort_values(
            sort_columns, kind="mergesort", na_position="last"
        )

    normalized = normalized.reindex(sorted(normalized.columns), axis=1)
    payload = normalized.to_csv(
        index=False,
        lineterminator="\n",
        na_rep="<NA>",
        float_format="%.12g",
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_table(path: Path) -> pd.DataFrame:
    """Read a supported tabular file."""
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"Unsupported manifest input format: {path.suffix}")


def _date_bounds(frame: pd.DataFrame) -> tuple[str, str]:
    for candidate in ("date", "observation_date", "timestamp"):
        if candidate not in frame.columns:
            continue
        parsed = pd.to_datetime(frame[candidate], errors="coerce")
        if parsed.notna().any():
            return (
                parsed.min().date().isoformat(),
                parsed.max().date().isoformat(),
            )
    return "", ""


def _source_list(frame: pd.DataFrame) -> str:
    if "source" not in frame.columns:
        return ""
    values = sorted(
        {
            str(value)
            for value in frame["source"].dropna().unique().tolist()
            if str(value).strip()
        }
    )
    return "|".join(values)


def _security_count(frame: pd.DataFrame) -> int:
    for candidate in ("security_id", "ticker", "series_id"):
        if candidate in frame.columns:
            return int(frame[candidate].nunique(dropna=True))
    return 0


def _load_manifest(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=MANIFEST_COLUMNS)

    manifest = pd.read_csv(path, dtype=str).fillna("")
    for column in MANIFEST_COLUMNS:
        if column not in manifest.columns:
            manifest[column] = ""
    return manifest[MANIFEST_COLUMNS]


def record_dataset(
    *,
    dataset_name: str,
    dataset_path: Path,
    root: Path | None = None,
    request_parameters: dict[str, Any] | None = None,
    status: str = "SUCCESS",
    error_message: str = "",
    run_id: str | None = None,
) -> dict[str, Any]:
    """Append a dataset record to data/manifests/market_data_manifest.csv."""
    project_root = root or find_project_root()
    manifest_path = (
        project_root / "data" / "manifests" / "market_data_manifest.csv"
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    config_path = project_root / "configs" / "project.yaml"
    config_hash = file_sha256(config_path)
    request_hash = json_sha256(request_parameters or {})
    current_run_id = run_id or make_run_id()

    frame = pd.DataFrame()
    content_hash = ""
    schema_hash = ""
    minimum_date = ""
    maximum_date = ""
    row_count = 0
    column_count = 0
    security_count = 0
    source_list = ""
    file_format = dataset_path.suffix.lower().lstrip(".")

    if status == "SUCCESS":
        if not dataset_path.exists():
            status = "FAILED"
            error_message = f"Dataset file does not exist: {dataset_path}"
        else:
            frame = read_table(dataset_path)
            row_count = int(len(frame))
            column_count = int(len(frame.columns))
            minimum_date, maximum_date = _date_bounds(frame)
            security_count = _security_count(frame)
            source_list = _source_list(frame)
            content_hash = dataframe_content_sha256(frame)
            schema_hash = json_sha256(
                {column: str(dtype) for column, dtype in frame.dtypes.items()}
            )

    history = _load_manifest(manifest_path)
    comparable = history[
        (history["dataset_name"] == dataset_name)
        & (history["request_sha256"] == request_hash)
        & (history["status"] == "SUCCESS")
    ]

    previous_hash = ""
    reproducibility_status = "FIRST_OBSERVATION"
    if not comparable.empty:
        previous = comparable.iloc[-1]
        previous_hash = str(previous["content_sha256"])
        previous_maximum_date = str(previous["maximum_date"])

        if previous_maximum_date != maximum_date:
            reproducibility_status = "NOT_COMPARABLE_NEW_PERIOD"
        elif previous_hash == content_hash:
            reproducibility_status = "MATCH"
        else:
            reproducibility_status = "CHANGED_SAME_PERIOD"

    if status != "SUCCESS":
        reproducibility_status = "NOT_TESTED"

    try:
        relative_path = dataset_path.resolve().relative_to(project_root.resolve())
        stored_path = str(relative_path).replace("\\", "/")
    except ValueError:
        stored_path = str(dataset_path.resolve()).replace("\\", "/")

    record = {
        "run_id": current_run_id,
        "dataset_name": dataset_name,
        "file_path": stored_path,
        "file_format": file_format,
        "row_count": row_count,
        "column_count": column_count,
        "minimum_date": minimum_date,
        "maximum_date": maximum_date,
        "security_count": security_count,
        "source_list": source_list,
        "content_sha256": content_hash,
        "schema_sha256": schema_hash,
        "config_sha256": config_hash,
        "request_sha256": request_hash,
        "generated_at_utc": utc_now(),
        "reproducibility_status": reproducibility_status,
        "previous_content_sha256": previous_hash,
        "status": status,
        "error_message": error_message,
    }

    updated = pd.concat([history, pd.DataFrame([record])], ignore_index=True)
    updated = updated[MANIFEST_COLUMNS]
    updated.to_csv(manifest_path, index=False)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record a dataset in the project data manifest."
    )
    parser.add_argument("--dataset-name", required=True)
    parser.add_argument("--file", required=True)
    parser.add_argument(
        "--request-json",
        default="{}",
        help="JSON object containing the download or build request.",
    )
    args = parser.parse_args()

    root = find_project_root()
    dataset_path = Path(args.file)
    if not dataset_path.is_absolute():
        dataset_path = root / dataset_path

    request_parameters = json.loads(args.request_json)
    record = record_dataset(
        dataset_name=args.dataset_name,
        dataset_path=dataset_path,
        root=root,
        request_parameters=request_parameters,
    )
    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Shared utilities for the Step 7 data-pipeline scripts."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
PROJECT_CONFIG_PATH = ROOT / "configs" / "project.yaml"
DATA_CONFIG_PATH = ROOT / "configs" / "data" / "market_data.yaml"


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required configuration file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


def load_configs() -> tuple[dict[str, Any], dict[str, Any]]:
    return load_yaml(PROJECT_CONFIG_PATH), load_yaml(DATA_CONFIG_PATH)


def ensure_directories() -> None:
    for relative in (
        "data/raw/market",
        "data/raw/macro",
        "data/interim",
        "data/processed",
        "data/synthetic",
        "data/manifests",
        "reports/evidence",
        "reports/evidence/logs",
    ):
        (ROOT / relative).mkdir(parents=True, exist_ok=True)


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def inclusive_end_to_exclusive(end_date: str | None) -> str | None:
    """Convert a configured inclusive date to yfinance's exclusive end date."""
    if end_date in (None, "", "null"):
        return None
    parsed = date.fromisoformat(str(end_date))
    return (parsed + timedelta(days=1)).isoformat()


def configured_observation_end(end_date: str | None) -> str:
    if end_date in (None, "", "null"):
        return date.today().isoformat()
    return str(end_date)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_path(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")


def snake_case(value: object) -> str:
    text = str(value).strip()
    text = re.sub(r"[^A-Za-z0-9]+", "_", text)
    return text.strip("_").lower()


def configure_logging(script_stem: str) -> logging.Logger:
    ensure_directories()
    logger = logging.getLogger(script_stem)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    logger.addHandler(stream)

    file_handler = logging.FileHandler(
        ROOT / "reports" / "evidence" / "logs" / f"{script_stem}.log",
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger

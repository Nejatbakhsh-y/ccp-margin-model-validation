"""Configuration loading utilities for the CCP margin model project."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class ConfigurationError(RuntimeError):
    """Raised when a configuration file is missing or invalid."""


def get_project_root() -> Path:
    """Return the repository root directory."""

    return Path(__file__).resolve().parents[2]


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load one YAML file and require a mapping at its top level."""

    if not path.exists():
        raise ConfigurationError(f"Configuration file does not exist: {path}")

    try:
        with path.open("r", encoding="utf-8-sig") as file:
            payload = yaml.safe_load(file)
    except yaml.YAMLError as exc:
        raise ConfigurationError(
            f"Invalid YAML syntax in configuration file: {path}"
        ) from exc

    if not isinstance(payload, dict):
        raise ConfigurationError(
            f"Configuration file must contain a top-level mapping: {path}"
        )

    return payload


def load_project_config(
    project_file: str | Path | None = None,
) -> dict[str, Any]:
    """
    Load the master project configuration and all referenced section files.

    Parameters
    ----------
    project_file:
        Optional path to the master project YAML file. Relative paths are
        resolved from the repository root.

    Returns
    -------
    dict[str, Any]
        Combined project configuration.
    """

    project_root = get_project_root()

    if project_file is None:
        project_path = project_root / "configs" / "project.yaml"
    else:
        supplied_path = Path(project_file)
        project_path = (
            supplied_path
            if supplied_path.is_absolute()
            else project_root / supplied_path
        )

    project_path = project_path.resolve()
    project_config = _load_yaml(project_path)

    referenced_files = project_config.get("config_files")

    if not isinstance(referenced_files, dict) or not referenced_files:
        raise ConfigurationError(
            "configs/project.yaml must contain a non-empty 'config_files' mapping."
        )

    combined_config: dict[str, Any] = {
        key: value for key, value in project_config.items() if key != "config_files"
    }

    loaded_files: dict[str, str] = {
        "project": str(project_path.relative_to(project_root))
    }

    for section_name, relative_file in referenced_files.items():
        if not isinstance(relative_file, str) or not relative_file.strip():
            raise ConfigurationError(
                f"Invalid file reference for section '{section_name}'."
            )

        section_path = (project_root / relative_file).resolve()

        try:
            section_path.relative_to(project_root)
        except ValueError as exc:
            raise ConfigurationError(
                f"Configuration path is outside the repository: {section_path}"
            ) from exc

        section_document = _load_yaml(section_path)

        if section_name not in section_document:
            raise ConfigurationError(
                f"Expected top-level section '{section_name}' in {section_path}."
            )

        combined_config[section_name] = section_document[section_name]
        loaded_files[section_name] = str(section_path.relative_to(project_root))

    combined_config["_metadata"] = {
        "project_root": str(project_root),
        "loaded_files": loaded_files,
    }

    return combined_config

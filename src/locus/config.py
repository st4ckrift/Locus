
"""Configuration loading and initialization."""

import json
import os
from pathlib import Path
from typing import Any


def default_config() -> dict[str, Any]:
    """Return a safe initial configuration."""
    home = Path.home()

    candidate_roots = [
        home / "Documents",
        home / "Downloads",
        home / "Projects",
    ]

    roots = [str(path) for path in candidate_roots if path.is_dir()]
    data_dir = home / ".local" / "share" / "locus"

    return {
        "roots": roots,
        "database_path": str(data_dir / "catalogue.sqlite3"),
        "semantic_store_path": str(data_dir / "vecna-store.json"),
        "vecna_path": str(home / "Projects" / "Vector"),
        "include_hidden": False,
        "max_file_size_mb": 100,
        "max_content_size_mb": 1,
        "exclude_dir_names": [
            ".git",
            ".venv",
            "venv",
            "node_modules",
            "__pycache__",
            ".cache",
            "target",
            "dist",
            "build",
        ],
    }


def default_config_path() -> Path:
    return (
        Path.home()
        / ".config"
        / "locus"
        / "config.json"
    )


def resolve_path(value: str) -> Path:
    """Expand environment variables and ~ in a path."""
    expanded = os.path.expandvars(value)
    return Path(expanded).expanduser().resolve()


def load_config(path: Path) -> dict[str, Any]:
    """Load and validate configuration, including legacy config files."""
    with path.open("r", encoding="utf-8") as file:
        config = json.load(file)

    if not isinstance(config, dict):
        raise ValueError("Configuration must be a JSON object")

    required = {
        "roots",
        "database_path",
        "include_hidden",
        "max_file_size_mb",
        "exclude_dir_names",
    }
    missing = required - config.keys()

    if missing:
        raise ValueError(
            f"Configuration is missing keys: {sorted(missing)}"
        )

    # Add settings introduced after the initial Phase 1 configuration.
    defaults = default_config()
    for key, value in defaults.items():
        config.setdefault(key, value)

    if not isinstance(config["roots"], list):
        raise ValueError("'roots' must be a list")
    if not all(isinstance(root, str) for root in config["roots"]):
        raise ValueError("Every configured root must be a string")

    if not isinstance(config["include_hidden"], bool):
        raise ValueError("'include_hidden' must be a boolean")

    for key in ("max_file_size_mb", "max_content_size_mb"):
        value = config[key]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or value <= 0
        ):
            raise ValueError(f"'{key}' must be positive")

    if not isinstance(config["exclude_dir_names"], list):
        raise ValueError("'exclude_dir_names' must be a list")
    if not all(
        isinstance(name, str)
        for name in config["exclude_dir_names"]
    ):
        raise ValueError("Excluded directory names must be strings")

    for key in (
        "database_path",
        "semantic_store_path",
        "vecna_path",
    ):
        if not isinstance(config[key], str) or not config[key].strip():
            raise ValueError(f"'{key}' must be a non-empty string")
        config[key] = str(resolve_path(config[key]))

    config["roots"] = [
        str(resolve_path(root)) for root in config["roots"]
    ]
    config["exclude_dir_names"] = list(
        dict.fromkeys(config["exclude_dir_names"])
    )

    return config


def initialize_config(path: Path, force: bool = False) -> bool:
    """Create configuration without overwriting it by default."""
    if path.exists() and not force:
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(default_config(), file, indent=2)
        file.write("\n")

    return True


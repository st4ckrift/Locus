

import json
from pathlib import Path
from typing import Any


def default_config() -> dict[str, Any]:


    home = Path.home()

    candidate_roots = [
        home / "Documents",
        home / "Downloads",
        home / "Projects",
    ]

    roots = [
        str(path)
        for path in candidate_roots
        if path.is_dir()
    ]

    return {
        "roots": roots,
        "database_path": (
            "~/.local/share/smart-file-explorer/catalogue.sqlite3"
        ),
        "include_hidden": False,
        "max_file_size_mb": 100,
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
        / "smart-file-explorer"
        / "config.json"
    )


def resolve_path(value: str) -> Path:

    import os

    expanded = os.path.expandvars(value)
    return Path(expanded).expanduser().resolve()


def load_config(path: Path) -> dict[str, Any]:

    with path.open("r", encoding="utf-8") as file:
        config = json.load(file)

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

    if not isinstance(config["roots"], list):
        raise ValueError("'roots' must be a list")

    if not all(isinstance(root, str) for root in config["roots"]):
        raise ValueError("Every configured root must be a string")

    if not isinstance(config["include_hidden"], bool):
        raise ValueError("'include_hidden' must be a boolean")

    max_size = config["max_file_size_mb"]

    if (
        isinstance(max_size, bool)
        or not isinstance(max_size, (int, float))
        or max_size <= 0
    ):
        raise ValueError("'max_file_size_mb' must be positive")

    if not isinstance(config["exclude_dir_names"], list):
        raise ValueError("'exclude_dir_names' must be a list")

    if not all(
        isinstance(name, str)
        for name in config["exclude_dir_names"]
    ):
        raise ValueError("Excluded directory names must be strings")

    if not isinstance(config["database_path"], str):
        raise ValueError("'database_path' must be a string")

    config["database_path"] = str(
        resolve_path(config["database_path"])
    )

    config["roots"] = [
        str(resolve_path(root))
        for root in config["roots"]
    ]

    config["exclude_dir_names"] = list(
        dict.fromkeys(config["exclude_dir_names"])
    )

    return config


def initialize_config(path: Path, force: bool = False) -> bool:

    if path.exists() and not force:
        return False

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(default_config(), file, indent=2)
        file.write("\n")

    return True

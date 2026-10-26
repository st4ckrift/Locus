
import os
import uuid
from pathlib import Path
from typing import Any

from smartfiles.catalogue import Catalogue


def scan_root(
    root_path: str | Path,
    catalogue: Catalogue,
    config: dict[str, Any],
) -> dict[str, int]:

    root = Path(root_path).expanduser().resolve(strict=True)

    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    run_id = uuid.uuid4().hex

    stats = {
        "seen": 0,
        "inserted": 0,
        "updated": 0,
        "unchanged": 0,
        "skipped": 0,
        "removed": 0,
    }

    max_size = int(config["max_file_size_mb"] * 1024 * 1024)
    excluded_dirs = set(config["exclude_dir_names"])
    include_hidden = config["include_hidden"]
    errors: list[OSError] = []

    def record_error(error: OSError) -> None:
        errors.append(error)

    for current_dir, directories, filenames in os.walk(
        root,
        topdown=True,
        followlinks=False,
        onerror=record_error,
    ):
        current = Path(current_dir)

        
        retained_dirs = []

        for directory in directories:
            directory_path = current / directory

            if not include_hidden and directory.startswith("."):
                stats["skipped"] += 1
                continue

            if directory in excluded_dirs:
                continue

        
            if directory_path.is_symlink():
                continue

            retained_dirs.append(directory)

        directories[:] = retained_dirs

        for filename in filenames:
            if not include_hidden and filename.startswith("."):
                stats["skipped"] += 1
                continue

            path = current / filename

            try:
                
                if path.is_symlink():
                    stats["skipped"] += 1
                    continue

                file_stat = path.stat(follow_symlinks=False)

                if not path.is_file():
                    stats["skipped"] += 1
                    continue

                if file_stat.st_size > max_size:
                    stats["skipped"] += 1
                    continue

                result = catalogue.upsert_file(
                    root=str(root),
                    path=str(path),
                    name=path.name,
                    extension=path.suffix.lower(),
                    size_bytes=file_stat.st_size,
                    mtime_ns=file_stat.st_mtime_ns,
                    run_id=run_id,
                )

                stats["seen"] += 1
                stats[result] += 1

            except (OSError, ValueError) as error:
                stats["skipped"] += 1
                errors.append(
                    OSError(f"Could not index {path}: {error}")
                )

    if errors:
        raise RuntimeError(
            f"Scan of {root} was incomplete: "
            f"{len(errors)} filesystem error(s). "
            "Existing records were retained. "
            f"First error: {errors[0]}"
        )

    stats["removed"] = catalogue.finish_scan(
        str(root),
        run_id,
    )

    return stats

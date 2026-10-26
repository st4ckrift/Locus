from pathlib import Path

from smartfiles.catalogue import Catalogue
from smartfiles.scanner import scan_root


def make_config() -> dict:
    return {
        "roots": [],
        "database_path": "",
        "include_hidden": False,
        "max_file_size_mb": 1,
        "exclude_dir_names": [".git", ".venv", "node_modules"],
    }


def test_scan_and_search(tmp_path: Path) -> None:
    root = tmp_path / "files"
    root.mkdir()

    (root / "vecna-notes.md").write_text(
        "Sample notes",
        encoding="utf-8",
    )
    (root / "results.csv").write_text(
        "name,score\nalpha,1\n",
        encoding="utf-8",
    )

    hidden = root / ".hidden"
    hidden.mkdir()
    (hidden / "secret.txt").write_text(
        "Should not be indexed",
        encoding="utf-8",
    )

    catalogue = Catalogue(tmp_path / "catalogue.sqlite3")

    stats = scan_root(root, catalogue, make_config())

    assert stats["inserted"] == 2
    assert stats["skipped"] == 1
    assert catalogue.stats()["file_count"] == 2

    results = catalogue.search("vecna")

    assert len(results) == 1
    assert results[0]["name"] == "vecna-notes.md"


def test_rescan_does_not_duplicate_files(tmp_path: Path) -> None:
    root = tmp_path / "files"
    root.mkdir()

    (root / "notes.md").write_text(
        "Notes",
        encoding="utf-8",
    )

    catalogue = Catalogue(tmp_path / "catalogue.sqlite3")
    config = make_config()

    scan_root(root, catalogue, config)
    stats = scan_root(root, catalogue, config)

    assert stats["inserted"] == 0
    assert stats["unchanged"] == 1
    assert catalogue.stats()["file_count"] == 1


def test_deleted_files_are_removed(tmp_path: Path) -> None:
    root = tmp_path / "files"
    root.mkdir()

    file_path = root / "temporary.txt"
    file_path.write_text("Temporary", encoding="utf-8")

    catalogue = Catalogue(tmp_path / "catalogue.sqlite3")
    config = make_config()

    scan_root(root, catalogue, config)
    file_path.unlink()

    stats = scan_root(root, catalogue, config)

    assert stats["removed"] == 1
    assert catalogue.stats()["file_count"] == 0
    assert catalogue.search("temporary") == []


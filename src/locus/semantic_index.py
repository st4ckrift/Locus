
"""Synchronize extracted file content with the Vecna vector store."""

import hashlib
from pathlib import Path
from typing import Any

from locus.catalogue import Catalogue
from locus.extractor import extract_text
from locus.vecna_adapter import create_engine


class SemanticIndexer:
    """Manage the mapping between catalogue files and Vecna vectors."""

    def __init__(
        self,
        catalogue: Catalogue,
        store_path: str | Path,
        vecna_path: str | Path,
        max_content_size_mb: float = 1,
        engine: Any = None,
    ) -> None:
        self.catalogue = catalogue
        self.store_path = Path(store_path).expanduser()
        self.max_bytes = int(max_content_size_mb * 1024 * 1024)

        if self.max_bytes < 1:
            raise ValueError("max_content_size_mb must be positive")

        self.engine = engine or create_engine(vecna_path)

        if self.store_path.is_file():
            self.engine.load(str(self.store_path))

        self._reconcile()

    def _save(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine.save(str(self.store_path))

    def _drop_vector(self, vector_id: int) -> None:
        """Remove a vector and its stored document and metadata."""
        store = self.engine.store
        store.vectors.pop(vector_id, None)
        store.documents.pop(vector_id, None)
        store.metadata.pop(vector_id, None)

    def _remove_path(self, path: str) -> bool:
        """Remove one path mapping and its vector if present."""
        vector_id = self.catalogue.delete_semantic_document(path)
        if vector_id is None:
            return False

        self._drop_vector(vector_id)
        return True

    def _reconcile(self) -> None:
        """Repair inconsistencies between SQLite and persisted vectors."""
        records = self.catalogue.semantic_documents()
        valid_ids = set(self.engine.store.vectors)
        mapped_ids = {int(row["vector_id"]) for row in records}
        changed = False

        for row in records:
            vector_id = int(row["vector_id"])
            if vector_id not in valid_ids:
                self.catalogue.delete_semantic_document(row["path"])
                changed = True

        # Vectors without a SQLite path mapping are untrusted orphans.
        for vector_id in list(self.engine.store.vectors):
            if int(vector_id) not in mapped_ids:
                self._drop_vector(int(vector_id))
                changed = True

        if changed:
            self._save()

    def index_all(self) -> dict[str, int]:
        self._reconcile()
        """Index supported catalogue files and remove stale semantic data."""
        stats = {
            "seen": 0,
            "indexed": 0,
            "updated": 0,
            "unchanged": 0,
            "skipped": 0,
            "removed": 0,
        }

        files = self.catalogue.list_files()
        file_paths = {row["path"] for row in files}
        existing = {
            row["path"]: row
            for row in self.catalogue.semantic_documents()
        }

        # Remove entries for files no longer in the catalogue.
        for path in set(existing) - file_paths:
            if self._remove_path(path):
                stats["removed"] += 1

        for file_row in files:
            path = file_row["path"]
            stats["seen"] += 1
            old_record = existing.get(path)

            text = extract_text(path, self.max_bytes)

            if text is None:
                stats["skipped"] += 1
                if self._remove_path(path):
                    stats["removed"] += 1
                continue

            digest = hashlib.sha256(
                text.encode("utf-8")
            ).hexdigest()

            if (
                old_record is not None
                and old_record["content_hash"] == digest
                and int(old_record["vector_id"])
                in self.engine.store.vectors
            ):
                stats["unchanged"] += 1
                continue

            was_indexed = old_record is not None
            if was_indexed:
                self._remove_path(path)

            metadata = {
                "path": path,
                "name": file_row["name"],
                "extension": file_row["extension"],
                "content_hash": digest,
            }

            vector_id = self.engine.add_document(text, metadata)
            self.catalogue.upsert_semantic_document(
                path,
                int(vector_id),
                digest,
            )

            stats["updated" if was_indexed else "indexed"] += 1

        self._save()
        return stats

    def search(
        self,
        query: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Return semantic results mapped back to catalogue paths."""
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")

        records = {
            int(row["vector_id"]): row
            for row in self.catalogue.semantic_documents()
        }

        vector_results = self.engine.search(query, k=limit)
        results: list[dict[str, Any]] = []

        for vector_id, distance in vector_results:
            mapping = records.get(int(vector_id))
            if mapping is None:
                continue

            file_row = self.catalogue.get_file_by_path(
                mapping["path"]
            )
            if file_row is None:
                continue

            # Avoid returning stale results if the file has disappeared
            # since the last filesystem scan.
            file_path = Path(file_row["path"])
            if file_path.is_symlink() or not file_path.is_file():
                continue

            results.append({
                **file_row,
                "semantic_distance": float(distance),
            })

        return results


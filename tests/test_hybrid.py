
import json
from pathlib import Path
from types import SimpleNamespace

from locus.catalogue import Catalogue
from locus.hybrid import HybridSearch
from locus.scanner import scan_root
from locus.semantic_index import SemanticIndexer


class FakeEmbedder:
    def embed(self, text):
        text = text.lower()
        if "network" in text or "tethering" in text:
            return SimpleNamespace(values=[0.0, 0.0])
        if "python" in text:
            return SimpleNamespace(values=[10.0, 0.0])
        return SimpleNamespace(values=[5.0, 0.0])


class FakeEngine:
    """Small in-memory engine with the persistence interface we need."""

    def __init__(self):
        self.embedder = FakeEmbedder()
        self.store = SimpleNamespace(
            vectors={},
            documents={},
            metadata={},
            next_id=1,
        )

    def add_document(self, text, metadata=None):
        vector_id = self.store.next_id
        self.store.next_id += 1
        self.store.vectors[vector_id] = self.embedder.embed(text)
        self.store.documents[vector_id] = text
        self.store.metadata[vector_id] = metadata or {}
        return vector_id

    def search(self, query, k=5):
        query_values = self.embedder.embed(query).values
        results = []

        for vector_id, vector in self.store.vectors.items():
            distance = sum(
                (a - b) ** 2
                for a, b in zip(vector.values, query_values)
            ) ** 0.5
            results.append((vector_id, distance))

        return sorted(results, key=lambda item: item[1])[:k]

    def save(self, filepath):
        data = {
            "next_id": self.store.next_id,
            "vectors": {
                str(key): value.values
                for key, value in self.store.vectors.items()
            },
            "documents": self.store.documents,
            "metadata": self.store.metadata,
        }
        Path(filepath).write_text(
            json.dumps(data), encoding="utf-8"
        )

    def load(self, filepath):
        data = json.loads(
            Path(filepath).read_text(encoding="utf-8")
        )
        self.store.next_id = data["next_id"]
        self.store.vectors = {
            int(key): SimpleNamespace(values=values)
            for key, values in data["vectors"].items()
        }
        self.store.documents = {
            int(key): value
            for key, value in data["documents"].items()
        }
        self.store.metadata = {
            int(key): value
            for key, value in data["metadata"].items()
        }


def make_config():
    return {
        "include_hidden": False,
        "max_file_size_mb": 1,
        "exclude_dir_names": [".git", ".venv", "node_modules"],
    }


def make_indexer(catalogue, store_path, engine=None):
    return SemanticIndexer(
        catalogue=catalogue,
        store_path=store_path,
        vecna_path="unused-with-injected-engine",
        max_content_size_mb=1,
        engine=engine or FakeEngine(),
    )


def test_semantic_search_and_persistence(tmp_path):
    root = tmp_path / "files"
    root.mkdir()
    (root / "notes.md").write_text(
        "Network connectivity over USB tethering",
        encoding="utf-8",
    )
    (root / "python.md").write_text(
        "Python programming language",
        encoding="utf-8",
    )

    catalogue = Catalogue(tmp_path / "catalogue.sqlite3")
    scan_root(root, catalogue, make_config())

    store_path = tmp_path / "vectors.json"
    indexer = make_indexer(catalogue, store_path)
    stats = indexer.index_all()

    assert stats["indexed"] == 2
    assert stats["unchanged"] == 0

    results = indexer.search("network")
    assert results[0]["name"] == "notes.md"

    # A new indexer reloads the saved vectors and SQLite mapping.
    restored = make_indexer(
        catalogue, store_path, engine=FakeEngine()
    )
    results = restored.search("network")
    assert results[0]["name"] == "notes.md"


def test_unchanged_files_are_not_reembedded(tmp_path):
    root = tmp_path / "files"
    root.mkdir()
    (root / "notes.md").write_text(
        "Network connectivity", encoding="utf-8"
    )

    catalogue = Catalogue(tmp_path / "catalogue.sqlite3")
    config = make_config()
    scan_root(root, catalogue, config)

    indexer = make_indexer(catalogue, tmp_path / "vectors.json")
    first = indexer.index_all()
    second = indexer.index_all()

    assert first["indexed"] == 1
    assert second["unchanged"] == 1
    assert second["indexed"] == 0


def test_hybrid_search_combines_keyword_and_semantic_results(tmp_path):
    root = tmp_path / "files"
    root.mkdir()

    (root / "network-guide.md").write_text(
        "Python tooling", encoding="utf-8"
    )
    (root / "notes.md").write_text(
        "Network connectivity over USB tethering",
        encoding="utf-8",
    )

    catalogue = Catalogue(tmp_path / "catalogue.sqlite3")
    scan_root(root, catalogue, make_config())

    indexer = make_indexer(
        catalogue, tmp_path / "vectors.json"
    )
    indexer.index_all()

    results = HybridSearch(catalogue, indexer).search(
        "network", limit=10
    )
    by_name = {result["name"]: result for result in results}

    assert "network-guide.md" in by_name
    assert "notes.md" in by_name
    assert "keyword" in by_name["network-guide.md"]["sources"]
    assert "semantic" in by_name["notes.md"]["sources"]


def test_deleted_file_removes_its_semantic_vector(tmp_path):
    root = tmp_path / "files"
    root.mkdir()
    path = root / "notes.md"
    path.write_text("Network connectivity", encoding="utf-8")

    catalogue = Catalogue(tmp_path / "catalogue.sqlite3")
    config = make_config()
    scan_root(root, catalogue, config)

    indexer = make_indexer(
        catalogue, tmp_path / "vectors.json"
    )
    indexer.index_all()
    assert len(indexer.engine.store.vectors) == 1

    path.unlink()
    scan_root(root, catalogue, config)
    indexer.index_all()

    assert catalogue.semantic_documents() == []
    assert indexer.engine.store.vectors == {}


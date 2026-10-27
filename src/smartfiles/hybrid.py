
"""Combine keyword and semantic results using Reciprocal Rank Fusion."""

from typing import Any

from smartfiles.catalogue import Catalogue


class HybridSearch:
    """Fuse FTS5 and Vecna rankings without mixing score scales."""

    def __init__(
        self,
        catalogue: Catalogue,
        semantic_indexer: Any = None,
        rrf_constant: int = 60,
    ) -> None:
        if rrf_constant < 1:
            raise ValueError("rrf_constant must be positive")

        self.catalogue = catalogue
        self.semantic_indexer = semantic_indexer
        self.rrf_constant = rrf_constant

    def search(
        self,
        query: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")

        combined: dict[str, dict[str, Any]] = {}

        def add_results(results, source: str) -> None:
            for rank, result in enumerate(results, start=1):
                path = result["path"]
                entry = combined.get(path)

                if entry is None:
                    entry = {
                        **result,
                        "rrf_score": 0.0,
                        "sources": [],
                    }
                    combined[path] = entry

                entry["rrf_score"] += (
                    1.0 / (self.rrf_constant + rank)
                )

                if source not in entry["sources"]:
                    entry["sources"].append(source)

                # Preserve the semantic distance when available.
                if "semantic_distance" in result:
                    entry["semantic_distance"] = (
                        result["semantic_distance"]
                    )

        add_results(self.catalogue.search(query, limit), "keyword")

        if self.semantic_indexer is not None:
            add_results(
                self.semantic_indexer.search(query, limit),
                "semantic",
            )

        ranked = sorted(
            combined.values(),
            key=lambda result: (
                -result["rrf_score"],
                result["name"].casefold(),
                result["path"],
            ),
        )
        return ranked[:limit]


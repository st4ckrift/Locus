
"""Local HTTP API for Locus."""

from contextlib import asynccontextmanager
from pathlib import Path
from threading import RLock
from typing import Any

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel, Field

from locus.catalogue import Catalogue
from locus.config import default_config_path, load_config
from locus.hybrid import HybridSearch
from locus.semantic_index import SemanticIndexer


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=10, ge=1, le=100)


def create_app(config_path: Path | None = None) -> FastAPI:
    """Create the Locus API application."""

    selected_config = (
        config_path if config_path is not None else default_config_path()
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not selected_config.is_file():
            raise FileNotFoundError(
                f"Configuration not found: {selected_config}. "
                "Run 'locus init' first."
            )

        config = load_config(selected_config)
        catalogue = Catalogue(config["database_path"])

        semantic_indexer = None
        if catalogue.semantic_documents():
            semantic_indexer = SemanticIndexer(
                catalogue=catalogue,
                store_path=config["semantic_store_path"],
                vecna_path=config["vecna_path"],
                max_content_size_mb=config["max_content_size_mb"],
            )

        app.state.config = config
        app.state.catalogue = catalogue
        app.state.semantic_indexer = semantic_indexer
        app.state.searcher = HybridSearch(catalogue, semantic_indexer)
        app.state.operation_lock = RLock()

        yield

    app = FastAPI(
        title="Locus API",
        description="Local-first, context-aware file search.",
        version="0.3.0",
        lifespan=lifespan,
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "locus"}

    @app.get("/v1/stats")
    def stats() -> dict[str, int]:
        with app.state.operation_lock:
            return app.state.catalogue.stats()

    @app.post("/v1/search")
    def search(request: SearchRequest) -> dict[str, Any]:
        with app.state.operation_lock:
            results = app.state.searcher.search(
                request.query,
                request.limit,
            )

        return {
            "query": request.query,
            "count": len(results),
            "results": results,
        }

    @app.post("/v1/index-content")
    def index_content() -> dict[str, Any]:
        with app.state.operation_lock:
            indexer = app.state.semantic_indexer

            if indexer is None:
                config = app.state.config
                indexer = SemanticIndexer(
                    catalogue=app.state.catalogue,
                    store_path=config["semantic_store_path"],
                    vecna_path=config["vecna_path"],
                    max_content_size_mb=config["max_content_size_mb"],
                )
                app.state.semantic_indexer = indexer

            result = indexer.index_all()

            # Keep hybrid search connected to the active indexer.
            app.state.searcher = HybridSearch(
                app.state.catalogue,
                indexer,
            )

        return {"status": "completed", "stats": result}

    return app


app = create_app()


def main() -> None:
    """Run the local Locus API server."""
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8765,
        log_level="info",
    )


if __name__ == "__main__":
    main()

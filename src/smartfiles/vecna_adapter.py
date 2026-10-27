
"""Load the existing Vecna engine without copying its source."""

import importlib
import sys
from pathlib import Path
from typing import Any


def create_engine(
    vecna_path: str | Path,
    embedder: Any = None,
):
    """Create a Vecna engine from a separate local checkout."""
    repository = Path(vecna_path).expanduser().resolve()

    if not (repository / "src" / "engine.py").is_file():
        raise FileNotFoundError(
            f"Vecna engine not found under {repository}. "
            "Check the 'vecna_path' setting."
        )

    repository_text = str(repository)
    if repository_text in sys.path:
        sys.path.remove(repository_text)
    sys.path.insert(0, repository_text)

    try:
        engine_module = importlib.import_module("src.engine")
        engine_class = engine_module.VectorEngine
        return engine_class(
            embedder=embedder,
            index_type=None,
        )
    except (ImportError, ModuleNotFoundError) as error:
        raise RuntimeError(
            "Could not import Vecna or its dependencies. "
            "Check vecna_path and install the semantic dependencies "
            "with: python -m pip install -e '.[semantic]'"
        ) from error


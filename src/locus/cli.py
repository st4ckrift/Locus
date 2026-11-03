
"""Command-line interface for Locus."""

import argparse
import sys
from pathlib import Path
from locus.settings import open_settings

from locus.catalogue import Catalogue
from locus.config import (
    default_config_path,
    initialize_config,
    load_config,
)
from locus.hybrid import HybridSearch
from locus.scanner import scan_root
from locus.semantic_index import SemanticIndexer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="locus",
        description="Search local files by name, path, and meaning.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config_path(),
        help="Path to the JSON configuration file.",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    init_parser = subparsers.add_parser(
        "init",
        help="Create the initial configuration and database.",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Replace the existing configuration.",
    )

    scan_parser = subparsers.add_parser(
        "scan",
        help="Index file metadata in configured directories.",
    )
    scan_parser.add_argument(
        "--root",
        action="append",
        metavar="PATH",
        help="Directory to scan; repeat for multiple directories.",
    )

    index_parser = subparsers.add_parser(
        "index-content",
        help="Extract supported text and build the semantic index.",
    )
    index_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Reserved for future incremental/batched indexing.",
    )

    search_parser = subparsers.add_parser(
        "search",
        help="Search indexed filenames, paths, and content meaning.",
    )
    search_parser.add_argument("query", help="Search query.")
    search_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of results (1-100).",
    )

    subparsers.add_parser("stats", help="Show catalogue statistics.")

    subparsers.add_parser(
        "settings",
        help="Open the graphical Locus settings window.",
    )

    return parser 


def _make_semantic_indexer(config, catalogue) -> SemanticIndexer:
    return SemanticIndexer(
        catalogue=catalogue,
        store_path=config["semantic_store_path"],
        vecna_path=config["vecna_path"],
        max_content_size_mb=config["max_content_size_mb"],
    )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    config_path = args.config.expanduser().resolve()

    if args.command == "init":
        created = initialize_config(
            config_path,
            force=args.force,
        )
        if not created:
            print(f"Configuration already exists: {config_path}")
            print("Use --force only if you intend to replace it.")
            return 0

        print(f"Created configuration: {config_path}")
        config = load_config(config_path)
        Catalogue(config["database_path"])
        print(f"Database: {config['database_path']}")
        print(f"Configured roots: {len(config['roots'])}")
        return 0

    if not config_path.is_file():
        print(
            f"Configuration not found: {config_path}\n"
            "Run: locus init",
            file=sys.stderr,
        )
        return 2

    try:
        config = load_config(config_path)

        if args.command == "settings":
            open_settings(config_path)
            return 0

        catalogue = Catalogue(config["database_path"])

        if args.command == "scan":
            roots = args.root or config["roots"]
            if not roots:
                print(
                    "No scan roots configured. Add roots to "
                    f"{config_path} or use --root PATH.",
                    file=sys.stderr,
                )
                return 2

            exit_code = 0
            for root in roots:
                try:
                    stats = scan_root(root, catalogue, config)
                except (OSError, RuntimeError, ValueError) as error:
                    print(f"ERROR: {root}: {error}", file=sys.stderr)
                    exit_code = 1
                    continue

                print(f"\nScanned: {Path(root).expanduser().resolve()}")
                for key, value in stats.items():
                    print(f"  {key:10} {value}")
            return exit_code

        if args.command == "index-content":
            indexer = _make_semantic_indexer(config, catalogue)
            stats = indexer.index_all()
            print("Semantic indexing complete:")
            for key, value in stats.items():
                print(f"  {key:10} {value}")
            print(f"Vector store: {config['semantic_store_path']}")
            return 0

        if args.command == "search":
            if not 1 <= args.limit <= 100:
                parser.error("--limit must be between 1 and 100")

            semantic_indexer = None
            if catalogue.semantic_documents():
                semantic_indexer = _make_semantic_indexer(
                    config, catalogue
                )

            searcher = HybridSearch(catalogue, semantic_indexer)
            results = searcher.search(args.query, args.limit)

            if not results:
                print("No matching files found.")
                return 0

            for number, result in enumerate(results, start=1):
                size_kib = result["size_bytes"] / 1024
                sources = ", ".join(result["sources"])

                print(f"\n{number}. {result['name']}")
                print(f"   Path: {result['path']}")
                print(
                    f"   Type: {result['extension'] or '(no extension)'}"
                    f" | Size: {size_kib:.1f} KiB"
                )
                print(
                    f"   Sources: {sources}"
                    f" | RRF: {result['rrf_score']:.5f}"
                )
                if "semantic_distance" in result:
                    print(
                        "   Semantic distance: "
                        f"{result['semantic_distance']:.4f}"
                    )
            return 0

        if args.command == "stats":
            stats = catalogue.stats()
            print(f"Indexed files: {stats['file_count']}")
            print(f"File extensions: {stats['extension_count']}")
            print(f"Total indexed size: {stats['total_bytes']:,} bytes")
            print(f"Semantic documents: {stats['semantic_count']}")
            return 0

    except (OSError, ValueError, RuntimeError, ImportError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    return 0


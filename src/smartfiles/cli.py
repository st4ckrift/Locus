

import argparse
import sys
from pathlib import Path

from smartfiles.catalogue import Catalogue
from smartfiles.config import (
    default_config_path,
    initialize_config,
    load_config,
)
from smartfiles.scanner import scan_root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="smartfiles",
        description="Search local files by filename and path.",
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
        help="Index files in configured directories.",
    )
    scan_parser.add_argument(
        "--root",
        action="append",
        metavar="PATH",
        help="Directory to scan; repeat for multiple directories.",
    )

    search_parser = subparsers.add_parser(
        "search",
        help="Search indexed filenames and paths.",
    )
    search_parser.add_argument(
        "query",
        help="Words to search for.",
    )
    search_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of results (1-100).",
    )

    subparsers.add_parser(
        "stats",
        help="Show catalogue statistics.",
    )

    return parser


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

        if not config["roots"]:
            print(
                "No default directories were found. "
                "Edit the configuration or pass --root to scan."
            )

        return 0

    if not config_path.is_file():
        print(
            f"Configuration not found: {config_path}\n"
            "Run: smartfiles init",
            file=sys.stderr,
        )
        return 2

    try:
        config = load_config(config_path)
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

        if args.command == "search":
            results = catalogue.search(args.query, args.limit)

            if not results:
                print("No matching files found.")
                return 0

            for number, result in enumerate(results, start=1):
                size_kib = result["size_bytes"] / 1024

                print(f"\n{number}. {result['name']}")
                print(f"   Path: {result['path']}")
                print(
                    f"   Type: {result['extension'] or '(no extension)'}"
                    f" | Size: {size_kib:.1f} KiB"
                )

            return 0

        if args.command == "stats":
            stats = catalogue.stats()

            print(f"Indexed files: {stats['file_count']}")
            print(f"File extensions: {stats['extension_count']}")
            print(f"Total indexed size: {stats['total_bytes']:,} bytes")

            return 0

    except (OSError, ValueError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    return 0

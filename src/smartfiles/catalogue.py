
import re
import sqlite3
from pathlib import Path
from typing import Any


class Catalogue:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path).expanduser()

        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
    
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY,
                    path TEXT NOT NULL UNIQUE,
                    root TEXT NOT NULL,
                    name TEXT NOT NULL,
                    extension TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    mtime_ns INTEGER NOT NULL,
                    indexed_at REAL NOT NULL,
                    last_seen_run TEXT NOT NULL
                )
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_files_root
                ON files(root)
                """
            )

            connection.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS files_fts
                USING fts5(
                    name,
                    path,
                    tokenize = 'unicode61 remove_diacritics 2'
                )
                """
            )

            # Detect an SQLite build without working FTS5 support.
            connection.execute(
                """
                SELECT rowid
                FROM files_fts
                LIMIT 0
                """
            )

    def upsert_file(
        self,
        *,
        root: str,
        path: str,
        name: str,
        extension: str,
        size_bytes: int,
        mtime_ns: int,
        run_id: str,
    ) -> str:

        import time

        with self.connect() as connection:
            existing = connection.execute(
                """
                SELECT id, name, path, size_bytes, mtime_ns
                FROM files
                WHERE path = ?
                """,
                (path,),
            ).fetchone()

            if existing is None:
                cursor = connection.execute(
                    """
                    INSERT INTO files (
                        path,
                        root,
                        name,
                        extension,
                        size_bytes,
                        mtime_ns,
                        indexed_at,
                        last_seen_run
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        path,
                        root,
                        name,
                        extension,
                        size_bytes,
                        mtime_ns,
                        time.time(),
                        run_id,
                    ),
                )

                file_id = cursor.lastrowid

                connection.execute(
                    """
                    INSERT INTO files_fts (rowid, name, path)
                    VALUES (?, ?, ?)
                    """,
                    (file_id, name, path),
                )

                return "inserted"

            file_id = existing["id"]

            changed = (
                existing["name"] != name
                or existing["size_bytes"] != size_bytes
                or existing["mtime_ns"] != mtime_ns
            )

            connection.execute(
                """
                UPDATE files
                SET root = ?,
                    name = ?,
                    extension = ?,
                    size_bytes = ?,
                    mtime_ns = ?,
                    last_seen_run = ?
                WHERE id = ?
                """,
                (
                    root,
                    name,
                    extension,
                    size_bytes,
                    mtime_ns,
                    run_id,
                    file_id,
                ),
            )

            if existing["name"] != name or existing["path"] != path:
                connection.execute(
                    "DELETE FROM files_fts WHERE rowid = ?",
                    (file_id,),
                )

                connection.execute(
                    """
                    INSERT INTO files_fts (rowid, name, path)
                    VALUES (?, ?, ?)
                    """,
                    (file_id, name, path),
                )

            return "updated" if changed else "unchanged"

    def finish_scan(self, root: str, run_id: str) -> int:
        
        with self.connect() as connection:
            stale = connection.execute(
                """
                SELECT id
                FROM files
                WHERE root = ?
                  AND last_seen_run != ?
                """,
                (root, run_id),
            ).fetchall()

            for row in stale:
                connection.execute(
                    "DELETE FROM files_fts WHERE rowid = ?",
                    (row["id"],),
                )

            connection.execute(
                """
                DELETE FROM files
                WHERE root = ?
                  AND last_seen_run != ?
                """,
                (root, run_id),
            )

            return len(stale)

    def search(
        self,
        query: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search filenames and paths using FTS5."""

        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")


        terms = re.findall(r"\w+", query, flags=re.UNICODE)

        if not terms:
            return []

        fts_query = " OR ".join(
            '"' + term.replace('"', '""') + '"'
            for term in terms
        )

        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    files.id,
                    files.path,
                    files.name,
                    files.extension,
                    files.size_bytes,
                    files.mtime_ns,
                    bm25(files_fts, 5.0, 1.0) AS relevance
                FROM files_fts
                JOIN files ON files.id = files_fts.rowid
                WHERE files_fts MATCH ?
                ORDER BY relevance ASC, files.name ASC
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()

        return [dict(row) for row in rows]

    def stats(self) -> dict[str, int]:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS file_count,
                    COUNT(DISTINCT extension) AS extension_count,
                    COALESCE(SUM(size_bytes), 0) AS total_bytes
                FROM files
                """
            ).fetchone()

        return dict(row)

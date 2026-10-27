
"""Bounded, metadata-aware text extraction for semantic indexing."""

from html.parser import HTMLParser
from pathlib import Path


TEXT_EXTENSIONS = {
    ".txt", ".md", ".rst", ".log", ".csv", ".tsv",
    ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini",
    ".cfg", ".conf", ".xml", ".html", ".htm",
    ".py", ".pyi", ".c", ".h", ".cc", ".cpp", ".hpp",
    ".java", ".js", ".jsx", ".ts", ".tsx", ".css",
    ".sh", ".bash", ".zsh", ".rs", ".go", ".rb",
    ".php", ".sql", ".r", ".R", ".swift", ".kt",
    ".kts", ".vue", ".svelte", ".makefile", ".dockerfile",
}


class _HTMLTextParser(HTMLParser):
    """Collect visible HTML text while ignoring scripts and styles."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"script", "style", "noscript"}:
            self.ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"}:
            self.ignored_depth = max(0, self.ignored_depth - 1)

    def handle_data(self, data: str) -> None:
        if self.ignored_depth == 0:
            cleaned = data.strip()
            if cleaned:
                self.parts.append(cleaned)


def extract_text(path: str | Path, max_bytes: int) -> str | None:
    """Extract text from a supported file, or return None if unsuitable."""
    path = Path(path)

    if max_bytes < 1 or path.suffix.lower() not in TEXT_EXTENSIONS:
        return None

    try:
        if path.is_symlink():
            return None

        info = path.stat(follow_symlinks=False)
        if not path.is_file() or info.st_size > max_bytes:
            return None

        # Read at most one byte over the limit to handle a file that grows
        # between stat() and read().
        with path.open("rb") as file:
            raw = file.read(max_bytes + 1)

        if len(raw) > max_bytes or b"\x00" in raw:
            return None

        text = raw.decode("utf-8", errors="replace")

        if path.suffix.lower() in {".html", ".htm"}:
            parser = _HTMLTextParser()
            parser.feed(text)
            parser.close()
            text = "\n".join(parser.parts)

        text = text.strip()
        return text or None

    except (OSError, ValueError, UnicodeError):
        return None


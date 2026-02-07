"""
File loaders for the ingestion pipeline.

Recursively discovers and reads ``.md`` and ``.txt`` files from a directory.
"""

from dataclasses import dataclass
from pathlib import Path

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".md", ".txt"})


@dataclass(frozen=True)
class LoadedDocument:
    """A document loaded from disk."""

    path: str
    name: str
    content: str


def load_documents(
    data_dir: str | Path,
    *,
    limit: int | None = None,
) -> list[LoadedDocument]:
    """
    Recursively load ``.md`` and ``.txt`` files from *data_dir*.

    Args:
        data_dir: Root directory to scan.
        limit: Maximum number of files to return.  ``None`` means no limit.

    Returns:
        List of ``LoadedDocument`` objects sorted by path.

    Raises:
        FileNotFoundError: If *data_dir* does not exist.
        ValueError: If *data_dir* is not a directory.
    """
    root = Path(data_dir)
    if not root.exists():
        raise FileNotFoundError(f"Data directory does not exist: {root}")
    if not root.is_dir():
        raise ValueError(f"Path is not a directory: {root}")

    documents: list[LoadedDocument] = []
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        documents.append(
            LoadedDocument(
                path=str(path),
                name=path.name,
                content=content,
            )
        )
        if limit is not None and len(documents) >= limit:
            break

    return documents

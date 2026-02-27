"""
Genre recipe loader — reads markdown recipe files from disk.

Side-effect module (file I/O). Lives in ingestion/ per architecture rules.
Used by the /ask pipeline to inject genre context into the system prompt.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Default directory where recipe markdown files live
_DEFAULT_RECIPES_DIR = Path(__file__).parent.parent / "data" / "music" / "recipes"


def load_recipe(file_stem: str, recipes_dir: Path | None = None) -> str | None:
    """Load a genre recipe markdown file and return its contents.

    Reads ``{recipes_dir}/{file_stem}.md`` and returns the text.
    Returns None if the file does not exist or cannot be read —
    callers should treat None as "no genre context available".

    Args:
        file_stem: Filename stem without extension (e.g. ``"organic_house"``).
        recipes_dir: Directory to search. Defaults to ``data/music/recipes/``.

    Returns:
        File contents as a string, or None on any error.
    """
    dir_ = recipes_dir or _DEFAULT_RECIPES_DIR
    path = dir_ / f"{file_stem}.md"

    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.debug("Recipe file not found: %s", path)
        return None
    except OSError as exc:
        logger.warning("Failed to read recipe file %s: %s", path, exc)
        return None

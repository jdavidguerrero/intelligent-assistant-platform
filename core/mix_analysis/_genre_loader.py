"""
core/mix_analysis/_genre_loader.py — Load genre target YAML profiles.

Uses importlib.resources (stdlib) to read YAML files bundled in the
core/mix_analysis/genre_targets/ package. Results are cached in a module-level
dict so each YAML file is parsed only once per process.

Private module — import only from problems.py.
"""

from __future__ import annotations

import importlib.resources
from typing import Any

import yaml  # PyYAML — in requirements.txt

# ---------------------------------------------------------------------------
# Genre name → YAML filename mapping
# ---------------------------------------------------------------------------

_GENRE_FILE_MAP: dict[str, str] = {
    "organic house": "organic_house.yaml",
    "melodic techno": "melodic_techno.yaml",
    "deep house": "deep_house.yaml",
    "progressive house": "progressive_house.yaml",
    "afro house": "afro_house.yaml",
}

_CACHE: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Public loader
# ---------------------------------------------------------------------------


def load_genre_target(genre: str) -> dict[str, Any]:
    """Return the genre target profile dict for the given genre name.

    Genre names are case-insensitive and normalised (lower + strip).

    Args:
        genre: Genre name string, e.g. 'organic house', 'Melodic Techno'.

    Returns:
        Parsed YAML dict with keys: bands, thresholds, stereo, dynamics.

    Raises:
        ValueError: If genre is not in the known genre list.
    """
    key = genre.lower().strip()
    if key in _CACHE:
        return _CACHE[key]

    filename = _GENRE_FILE_MAP.get(key)
    if filename is None:
        available = sorted(_GENRE_FILE_MAP.keys())
        raise ValueError(f"Unknown genre {genre!r}. Available: {available}")

    pkg = importlib.resources.files("core.mix_analysis.genre_targets")
    text = (pkg / filename).read_text(encoding="utf-8")
    data: dict[str, Any] = yaml.safe_load(text)
    _CACHE[key] = data
    return data


def available_genres() -> list[str]:
    """Return sorted list of all supported genre names."""
    return sorted(_GENRE_FILE_MAP.keys())

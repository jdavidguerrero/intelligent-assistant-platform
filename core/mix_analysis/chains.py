"""
core/mix_analysis/chains.py — Signal chain template loader.

Provides genre-specific mix bus and master chain templates loaded from YAML.
All functions are pure: string arguments in -> SignalChain frozen dataclass out.

Design:
    - Chains are loaded from YAML files using importlib.resources (stdlib).
    - Results cached at module level (each file read once per process).
    - SignalChain and Processor are frozen dataclasses from types.py.
"""

from __future__ import annotations

import importlib.resources
from typing import Any

import yaml

from core.mix_analysis.types import Processor, ProcessorParam, SignalChain

# ---------------------------------------------------------------------------
# Genre + stage -> filename mapping
# ---------------------------------------------------------------------------

_STAGE_FILE_MAP: dict[str, dict[str, str]] = {
    "mix_bus": {
        "organic house": "organic_house.yaml",
        "melodic techno": "melodic_techno.yaml",
        "deep house": "deep_house.yaml",
        "progressive house": "progressive_house.yaml",
        "afro house": "afro_house.yaml",
    },
    "master": {
        "organic house": "organic_house.yaml",
        "melodic techno": "melodic_techno.yaml",
        "deep house": "deep_house.yaml",
        "progressive house": "progressive_house.yaml",
        "afro house": "afro_house.yaml",
    },
}

# Module-level cache: "stage:genre" -> SignalChain
_CACHE: dict[str, SignalChain] = {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_chain(genre: str, stage: str) -> SignalChain:
    """Return the signal chain template for a genre + stage combination.

    Args:
        genre: Genre name (case-insensitive), e.g. 'organic house'.
        stage: Processing stage: 'mix_bus' or 'master'.

    Returns:
        SignalChain with ordered Processor list.

    Raises:
        ValueError: If genre or stage is unknown.
    """
    genre_key = genre.lower().strip()
    stage_key = stage.lower().strip()

    cache_key = f"{stage_key}:{genre_key}"
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    chain = _load_chain(genre_key, stage_key)
    _CACHE[cache_key] = chain
    return chain


def available_stages() -> list[str]:
    """Return the list of supported processing stages."""
    return ["mix_bus", "master"]


def available_genres(stage: str = "mix_bus") -> list[str]:
    """Return sorted list of genres available for the given stage.

    Args:
        stage: Processing stage name (default: 'mix_bus').

    Raises:
        ValueError: If stage is unknown.
    """
    stage_key = stage.lower().strip()
    genre_map = _STAGE_FILE_MAP.get(stage_key)
    if genre_map is None:
        raise ValueError(f"Unknown stage {stage!r}. Available: {available_stages()}")
    return sorted(genre_map.keys())


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _load_chain(genre: str, stage: str) -> SignalChain:
    """Load and parse a chain YAML, returning a SignalChain dataclass.

    Args:
        genre: Normalised (lower-stripped) genre key.
        stage: Normalised stage key: 'mix_bus' or 'master'.

    Raises:
        ValueError: If stage or genre is not found in the file map.
    """
    genre_map = _STAGE_FILE_MAP.get(stage)
    if genre_map is None:
        raise ValueError(f"Unknown stage {stage!r}. Available: {available_stages()}")

    filename = genre_map.get(genre)
    if filename is None:
        available = sorted(genre_map.keys())
        raise ValueError(f"Unknown genre {genre!r} for stage {stage!r}. Available: {available}")

    package = _stage_package(stage)
    pkg = importlib.resources.files(package)
    text = (pkg / filename).read_text(encoding="utf-8")
    data: dict[str, Any] = yaml.safe_load(text)

    return _parse_chain(data)


def _stage_package(stage: str) -> str:
    """Map a stage name to its Python package path for importlib.resources."""
    packages: dict[str, str] = {
        "mix_bus": "core.mix_analysis.chain_templates.mix_bus",
        "master": "core.mix_analysis.chain_templates.master_chain",
    }
    pkg = packages.get(stage)
    if pkg is None:
        raise ValueError(f"Unknown stage {stage!r}. Available: {available_stages()}")
    return pkg


def _parse_chain(data: dict[str, Any]) -> SignalChain:
    """Convert a parsed YAML dict into a SignalChain frozen dataclass.

    YAML params format is a list of 2-element lists: [[name, value], ...].
    Each pair is converted to a ProcessorParam(name=str, value=str).
    """
    processors: list[Processor] = []
    for proc_data in data.get("processors", []):
        raw_params: list[list[Any]] = proc_data.get("params", [])
        params = tuple(ProcessorParam(name=str(pair[0]), value=str(pair[1])) for pair in raw_params)
        processor = Processor(
            name=proc_data["name"],
            proc_type=proc_data["proc_type"],
            plugin_primary=proc_data["plugin_primary"],
            plugin_fallback=proc_data["plugin_fallback"],
            params=params,
        )
        processors.append(processor)

    return SignalChain(
        genre=data["genre"],
        stage=data["stage"],
        description=data["description"],
        processors=tuple(processors),
    )

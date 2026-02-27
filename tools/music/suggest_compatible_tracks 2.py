"""
suggest_compatible_tracks tool — harmonic and rhythmic compatibility matching.

Given a reference track's key and BPM, finds compatible tracks in the
knowledge base and applies music theory rules to rank them.

Compatibility rules (DJ / live performance context):
  - BPM match:     ±6 BPM from reference (or ±3% for relative tolerance)
  - Harmonic match: Camelot Wheel — same key, adjacent keys, or relative major/minor
  - Energy match:  Optional — same energy tier (low/mid/high)

Camelot Wheel encoding:
  Each key maps to a position 1–12 + A (minor) or B (major).
  Compatible keys: same position, ±1 position, relative major/minor (same number).
  Example: 8A (A minor) → compatible with 8A (same), 7A (Dm), 9A (Em), 8B (C major).

No DB dependency — compatibility scoring is pure computation.
DB lookup (searching the knowledge base for tracks) uses the injected session.

Pipeline:
  analyze_track(file_path) → key="A minor", bpm=124
      → suggest_compatible_tracks(key="A minor", bpm=124)
      → [compatible tracks from knowledge base, ranked by compatibility score]
"""

from dataclasses import dataclass
from typing import Any

from tools.base import MusicalTool, ToolParameter, ToolResult

# ---------------------------------------------------------------------------
# Camelot Wheel — harmonic compatibility map
# ---------------------------------------------------------------------------

# key_name → (camelot_number, camelot_letter)
# Letter: A = minor, B = major
_CAMELOT: dict[str, tuple[int, str]] = {
    # Minor keys (A)
    "A minor": (8, "A"),
    "E minor": (9, "A"),
    "B minor": (10, "A"),
    "F# minor": (11, "A"),
    "Gb minor": (11, "A"),
    "C# minor": (12, "A"),
    "Db minor": (12, "A"),
    "G# minor": (1, "A"),
    "Ab minor": (1, "A"),
    "D# minor": (2, "A"),
    "Eb minor": (2, "A"),
    "A# minor": (3, "A"),
    "Bb minor": (3, "A"),
    "F minor": (4, "A"),
    "C minor": (5, "A"),
    "G minor": (6, "A"),
    "D minor": (7, "A"),
    # Major keys (B)
    "C major": (8, "B"),
    "G major": (9, "B"),
    "D major": (10, "B"),
    "A major": (11, "B"),
    "E major": (12, "B"),
    "B major": (1, "B"),
    "F# major": (2, "B"),
    "Gb major": (2, "B"),
    "C# major": (3, "B"),
    "Db major": (3, "B"),
    "G# major": (4, "B"),
    "Ab major": (4, "B"),
    "D# major": (5, "B"),
    "Eb major": (5, "B"),
    "A# major": (6, "B"),
    "Bb major": (6, "B"),
    "F major": (7, "B"),
}

# Reverse map: (number, letter) → key_name (canonical)
_CAMELOT_REVERSE: dict[tuple[int, str], str] = {v: k for k, v in _CAMELOT.items()}

# BPM tolerance: ±N BPM considered compatible
_BPM_TOLERANCE: int = 6

# BPM half-time / double-time bounds (within 3% of ×0.5 or ×2)
_BPM_HALFTIME_TOLERANCE: float = 0.03

# Compatibility score weights
_WEIGHT_KEY = 0.55
_WEIGHT_BPM = 0.35
_WEIGHT_ENERGY = 0.10


@dataclass(frozen=True)
class CompatibilityResult:
    """
    Compatibility assessment between two tracks.

    Attributes:
        key_score: 0.0–1.0 harmonic compatibility
        bpm_score: 0.0–1.0 rhythmic compatibility
        energy_score: 0.0–1.0 energy level match
        total_score: Weighted composite (0.0–1.0)
        relationship: Human-readable key relationship description
        bpm_adjustment: Suggested BPM change if using half/double time
    """

    key_score: float
    bpm_score: float
    energy_score: float
    total_score: float
    relationship: str
    bpm_adjustment: str | None  # "halftime" | "doubletime" | None


# ---------------------------------------------------------------------------
# Pure compatibility functions
# ---------------------------------------------------------------------------


def camelot_position(key: str) -> tuple[int, str] | None:
    """
    Get Camelot Wheel position for a key string.

    Args:
        key: Key string (e.g., "A minor", "C major", "F# minor")

    Returns:
        (number, letter) tuple or None if not in Camelot map
    """
    # Try as-is first
    pos = _CAMELOT.get(key)
    if pos:
        return pos
    # Try title-casing
    pos = _CAMELOT.get(key.title())
    if pos:
        return pos
    # Try normalizing "natural minor" → "minor"
    normalized = key.replace("natural minor", "minor").strip()
    return _CAMELOT.get(normalized)


def camelot_compatible_keys(key: str) -> list[str]:
    """
    Return all harmonically compatible keys for a given key.

    Compatibility rules (Camelot Wheel):
      - Same position (same key)
      - ±1 position (adjacent on wheel, modulates naturally)
      - Relative major/minor (same number, different letter)

    Args:
        key: Reference key string

    Returns:
        List of compatible key strings (including the input key)
    """
    pos = camelot_position(key)
    if pos is None:
        return [key]

    number, letter = pos
    compatible: list[str] = []

    # Same position
    compatible.append(key)

    # ±1 on wheel (1–12 circular)
    for delta in (-1, +1):
        adj_number = ((number - 1 + delta) % 12) + 1
        adj_key = _CAMELOT_REVERSE.get((adj_number, letter))
        if adj_key and adj_key not in compatible:
            compatible.append(adj_key)

    # Relative major/minor (same number, opposite letter)
    rel_letter = "B" if letter == "A" else "A"
    rel_key = _CAMELOT_REVERSE.get((number, rel_letter))
    if rel_key and rel_key not in compatible:
        compatible.append(rel_key)

    return compatible


def key_compatibility_score(ref_key: str, candidate_key: str) -> tuple[float, str]:
    """
    Score harmonic compatibility between two keys (0.0–1.0).

    Score rubric:
        1.0 — Same key
        0.8 — Adjacent on Camelot Wheel (±1)
        0.6 — Relative major/minor (same Camelot number)
        0.0 — No harmonic relationship

    Args:
        ref_key: Reference key
        candidate_key: Candidate key to compare

    Returns:
        (score, relationship_description) tuple
    """
    if ref_key == candidate_key:
        return 1.0, "same key"

    ref_pos = camelot_position(ref_key)
    cand_pos = camelot_position(candidate_key)

    if ref_pos is None or cand_pos is None:
        return 0.0, "unknown key"

    ref_num, ref_letter = ref_pos
    cand_num, cand_letter = cand_pos

    # Adjacent on wheel (±1, same letter)
    if ref_letter == cand_letter and abs(ref_num - cand_num) in (1, 11):
        direction = "up" if (cand_num - ref_num) % 12 == 1 else "down"
        return 0.8, f"adjacent on wheel ({direction})"

    # Relative major/minor (same number, different letter)
    if ref_num == cand_num and ref_letter != cand_letter:
        rel = "relative major" if cand_letter == "B" else "relative minor"
        return 0.6, rel

    return 0.0, "incompatible"


def bpm_compatibility_score(ref_bpm: float, candidate_bpm: float) -> tuple[float, str | None]:
    """
    Score BPM compatibility between two tracks (0.0–1.0).

    Score rubric:
        1.0 — Same BPM (±1)
        0.8 — Within ±6 BPM tolerance
        0.5 — Half-time or double-time (within 3%)
        0.0 — No rhythmic relationship

    Args:
        ref_bpm: Reference BPM
        candidate_bpm: Candidate BPM

    Returns:
        (score, adjustment) where adjustment is "halftime" | "doubletime" | None
    """
    if ref_bpm <= 0 or candidate_bpm <= 0:
        return 0.0, None

    diff = abs(ref_bpm - candidate_bpm)

    # Same BPM
    if diff <= 1:
        return 1.0, None

    # Within tolerance
    if diff <= _BPM_TOLERANCE:
        score = 1.0 - (diff / (_BPM_TOLERANCE * 2))
        return round(score, 3), None

    # Half-time: candidate is ~half of ref
    half = ref_bpm / 2.0
    if abs(candidate_bpm - half) / half <= _BPM_HALFTIME_TOLERANCE:
        return 0.5, "doubletime"  # would need to play candidate at double time

    # Double-time: candidate is ~double of ref
    double = ref_bpm * 2.0
    if abs(candidate_bpm - double) / double <= _BPM_HALFTIME_TOLERANCE:
        return 0.5, "halftime"  # would need to play candidate at half time

    return 0.0, None


def compute_compatibility(
    ref_key: str,
    ref_bpm: float,
    ref_energy: float | None,
    cand_key: str,
    cand_bpm: float,
    cand_energy: float | None,
) -> CompatibilityResult:
    """
    Compute full compatibility score between two tracks.

    Args:
        ref_key: Reference track key (e.g., "A minor")
        ref_bpm: Reference track BPM
        ref_energy: Reference track energy (0.0–1.0) or None
        cand_key: Candidate track key
        cand_bpm: Candidate track BPM
        cand_energy: Candidate track energy (0.0–1.0) or None

    Returns:
        CompatibilityResult with individual and composite scores
    """
    key_score, relationship = key_compatibility_score(ref_key, cand_key)
    bpm_score, bpm_adjustment = bpm_compatibility_score(ref_bpm, cand_bpm)

    # Energy score: 1.0 if within ±0.2, 0.0 otherwise; 0.5 if unknown
    if ref_energy is not None and cand_energy is not None:
        energy_diff = abs(ref_energy - cand_energy)
        energy_score = max(0.0, 1.0 - energy_diff * 5)  # 0.2 diff → 0.0
    else:
        energy_score = 0.5  # neutral when unknown

    total = round(
        _WEIGHT_KEY * key_score + _WEIGHT_BPM * bpm_score + _WEIGHT_ENERGY * energy_score,
        3,
    )

    return CompatibilityResult(
        key_score=round(key_score, 3),
        bpm_score=round(bpm_score, 3),
        energy_score=round(energy_score, 3),
        total_score=total,
        relationship=relationship,
        bpm_adjustment=bpm_adjustment,
    )


def parse_key_from_text(text: str) -> str | None:
    """
    Extract a key signature from a chunk's text content.

    Looks for patterns like "key of A minor", "in C major", "A minor scale".

    Args:
        text: Raw text chunk content

    Returns:
        Key string or None if not found
    """
    import re

    patterns = [
        r"\bkey\s+of\s+([A-Ga-g][#b]?\s+(?:major|minor))\b",
        r"\bin\s+([A-Ga-g][#b]?\s+(?:major|minor))\b",
        r"\b([A-Ga-g][#b]?\s+(?:major|minor))\s+(?:scale|key|mode|chord)\b",
        r"\b([A-Ga-g][#b]?\s+(?:natural\s+)?minor)\b",
        r"\b([A-Ga-g][#b]?\s+major)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            raw = match.group(1).strip()
            # Normalize "natural minor" → "minor"
            raw = re.sub(r"natural\s+minor", "minor", raw, flags=re.IGNORECASE)
            # Title-case: "a minor" → "A minor"
            parts = raw.split()
            if parts:
                return parts[0].upper() + (
                    " " + " ".join(parts[1:]).lower() if len(parts) > 1 else ""
                )
    return None


def parse_bpm_from_text(text: str) -> float | None:
    """
    Extract a BPM value from a chunk's text content.

    Args:
        text: Raw text chunk content

    Returns:
        BPM as float or None if not found
    """
    import re

    pattern = re.compile(r"\b(\d{2,3}(?:\.\d)?)\s*bpm\b", re.IGNORECASE)
    match = pattern.search(text)
    if match:
        value = float(match.group(1))
        if 60 <= value <= 200:
            return value
    return None


# ---------------------------------------------------------------------------
# Tool class
# ---------------------------------------------------------------------------


class SuggestCompatibleTracks(MusicalTool):
    """
    Suggest tracks compatible with a reference key and BPM.

    Uses the Camelot Wheel for harmonic matching and BPM tolerance rules
    for rhythmic compatibility. Searches the knowledge base for tracks
    that mention compatible keys and BPM values.

    Ideal for DJ set planning, live performance preparation, and
    understanding which tracks mix well together harmonically.

    Example:
        tool = SuggestCompatibleTracks()
        result = tool(key="A minor", bpm=124.0)
        # Returns tracks from knowledge base compatible with A minor @ 124 BPM
        # with Camelot Wheel analysis and compatibility scores
    """

    def __init__(self, session_factory: Any = None) -> None:
        """
        Args:
            session_factory: SQLAlchemy session factory. Defaults to get_session().
                             Inject a mock for testing.
        """
        from db.session import get_session

        self._session_factory = session_factory or get_session

    @property
    def name(self) -> str:
        return "suggest_compatible_tracks"

    @property
    def description(self) -> str:
        return (
            "Suggest tracks compatible with a reference key and BPM using the Camelot Wheel "
            "for harmonic matching. "
            "Use when the user wants to find tracks that mix well with a specific track, "
            "plan a DJ set, or understand which keys are harmonically compatible. "
            "Requires: key (e.g., 'A minor', 'C major') and bpm (numeric). "
            "Returns compatible tracks ranked by harmonic + rhythmic compatibility score."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="key",
                type=str,
                description=(
                    "Musical key of the reference track. "
                    "Format: '<note> <major|minor>' — e.g., 'A minor', 'C major', 'F# minor'. "
                    "Use analyze_track first if you don't know the key."
                ),
                required=True,
            ),
            ToolParameter(
                name="bpm",
                type=float,
                description=(
                    "BPM (tempo) of the reference track. "
                    "Must be between 60 and 220. "
                    "Use analyze_track first if you don't know the BPM."
                ),
                required=True,
            ),
            ToolParameter(
                name="energy",
                type=float,
                description=(
                    "Energy level of the reference track (0.0–1.0). "
                    "Use analyze_track output. Optional — if omitted, energy is not factored."
                ),
                required=False,
                default=None,
            ),
            ToolParameter(
                name="top_k",
                type=int,
                description="Number of compatible tracks to return (1–20). Default: 5",
                required=False,
                default=5,
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        """
        Find tracks compatible with the given key and BPM.

        Returns:
            ToolResult with:
                data:
                    reference:         Input key, bpm, energy
                    compatible_keys:   Camelot-compatible keys (for context)
                    tracks:            List of compatible track dicts with scores
                    camelot_position:  Reference track's Camelot position
                metadata:
                    bpm_tolerance:     ±N BPM used for matching
                    total_candidates:  How many chunks were searched
        """
        key: str = (kwargs.get("key") or "").strip()
        bpm_raw = kwargs.get("bpm")
        energy = kwargs.get("energy")
        top_k: int = kwargs.get("top_k") if kwargs.get("top_k") is not None else 5

        # -------------------------------------------------------------------
        # Validation
        # -------------------------------------------------------------------
        if not key:
            return ToolResult(success=False, error="key cannot be empty")

        if bpm_raw is None:
            return ToolResult(success=False, error="bpm is required")

        try:
            bpm = float(bpm_raw)
        except (TypeError, ValueError):
            return ToolResult(success=False, error="bpm must be a number")

        if not (60 <= bpm <= 220):
            return ToolResult(success=False, error="bpm must be between 60 and 220")

        if energy is not None:
            try:
                energy = float(energy)
            except (TypeError, ValueError):
                return ToolResult(success=False, error="energy must be a number between 0 and 1")
            if not (0.0 <= energy <= 1.0):
                return ToolResult(success=False, error="energy must be between 0.0 and 1.0")

        if not isinstance(top_k, int) or top_k < 1 or top_k > 20:
            return ToolResult(success=False, error="top_k must be an integer between 1 and 20")

        # Check key is known
        ref_pos = camelot_position(key)
        if ref_pos is None:
            return ToolResult(
                success=False,
                error=(
                    f"Unknown key: '{key}'. "
                    "Use format '<note> <major|minor>', e.g., 'A minor', 'C major'."
                ),
            )

        # Get compatible keys for context
        compatible_keys = camelot_compatible_keys(key)

        # -------------------------------------------------------------------
        # Search knowledge base for track-like chunks
        # -------------------------------------------------------------------
        try:
            tracks = self._find_compatible_in_kb(
                ref_key=key,
                ref_bpm=bpm,
                ref_energy=energy,
                compatible_keys=compatible_keys,
                top_k=top_k,
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Search failed: {str(e)}")

        # Format Camelot position as string (e.g., "8A")
        camelot_str = f"{ref_pos[0]}{ref_pos[1]}"

        return ToolResult(
            success=True,
            data={
                "reference": {
                    "key": key,
                    "bpm": bpm,
                    "energy": energy,
                    "camelot": camelot_str,
                },
                "compatible_keys": compatible_keys,
                "tracks": tracks,
                "total_found": len(tracks),
            },
            metadata={
                "bpm_tolerance": _BPM_TOLERANCE,
                "total_candidates": len(tracks),
            },
        )

    def _find_compatible_in_kb(
        self,
        ref_key: str,
        ref_bpm: float,
        ref_energy: float | None,
        compatible_keys: list[str],
        top_k: int,
    ) -> list[dict]:
        """
        Search knowledge base chunks for tracks mentioning compatible keys/BPM.

        Returns list of track dicts sorted by compatibility score (desc).
        """
        from sqlalchemy import or_, select
        from sqlalchemy.orm import Session

        from db.models import ChunkRecord

        session: Session = next(self._session_factory())
        try:
            # Build filters: chunks that mention any compatible key or a BPM-range keyword
            key_filters = []
            for ck in compatible_keys:
                key_filters.append(ChunkRecord.text.ilike(f"%{ck}%"))

            # Fetch candidates
            fetch_k = min(top_k * 10, 200)
            stmt = select(ChunkRecord).where(or_(*key_filters)).limit(fetch_k)
            candidates = session.execute(stmt).scalars().all()
        finally:
            session.close()

        if not candidates:
            return []

        # Score each candidate
        scored: list[dict] = []
        seen_sources: set[str] = set()

        for record in candidates:
            # Deduplicate by source — one entry per source_name
            source_key = record.source_name or record.source_path or str(record.id)
            if source_key in seen_sources:
                continue
            seen_sources.add(source_key)

            # Extract key and BPM from text
            cand_key = parse_key_from_text(record.text) or ref_key
            cand_bpm = parse_bpm_from_text(record.text) or ref_bpm

            # Compute compatibility
            compat = compute_compatibility(
                ref_key=ref_key,
                ref_bpm=ref_bpm,
                ref_energy=ref_energy,
                cand_key=cand_key,
                cand_bpm=cand_bpm,
                cand_energy=None,  # energy not stored in chunks
            )

            if compat.total_score > 0:
                scored.append(
                    {
                        "source_name": record.source_name,
                        "source_path": record.source_path,
                        "detected_key": cand_key,
                        "detected_bpm": cand_bpm,
                        "camelot": _camelot_str(cand_key),
                        "compatibility": {
                            "total": compat.total_score,
                            "key_score": compat.key_score,
                            "bpm_score": compat.bpm_score,
                            "energy_score": compat.energy_score,
                            "relationship": compat.relationship,
                            "bpm_adjustment": compat.bpm_adjustment,
                        },
                        "text_preview": record.text[:200].strip(),
                    }
                )

        # Sort by total score descending
        scored.sort(key=lambda x: x["compatibility"]["total"], reverse=True)
        return scored[:top_k]


def _camelot_str(key: str) -> str | None:
    """Format Camelot position as string (e.g., '8A'). None if unknown."""
    pos = camelot_position(key)
    if pos is None:
        return None
    return f"{pos[0]}{pos[1]}"

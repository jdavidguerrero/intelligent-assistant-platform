"""
Sub-domain detection for incoming queries.

Pure module — no I/O, no DB, no network calls.

Given a user query string, detects which music production sub-domains
are relevant. Used by the RAG pipeline to optionally narrow retrieval
to the most relevant knowledge namespace(s).

The detector uses a keyword-voting approach: each sub-domain casts votes
based on how many of its keywords appear in the query. Sub-domains that
exceed the vote threshold are returned as active.

Design notes:
    - Purity: no imports from db/, api/, ingestion/, or domains/.
      Keyword lists are defined inline to keep core/ self-contained.
    - Determinism: identical input always produces identical output.
    - Single responsibility: detection only — no search, no retrieval.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Keyword vocabulary per sub-domain
# Kept intentionally concise — these are *query* indicators, not chunk
# classifiers. Precision matters more than recall here: a false positive
# sub-domain narrows retrieval incorrectly.
# ---------------------------------------------------------------------------

_QUERY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "sound_design": (
        "sound design",
        "synthesis",
        "synthesizer",
        "synth",
        "serum",
        "oscillator",
        "wavetable",
        "bass design",
        "bass sound",
        "subtractive",
        "fm synthesis",
        "lfo",
        "envelope",
        "filter cutoff",
        "resonance",
        "patch",
        "preset",
        "timbre",
        "distortion",
        "saturation",
    ),
    "arrangement": (
        "arrangement",
        "arrange",
        "structure",
        "intro",
        "outro",
        "breakdown",
        "drop",
        "build",
        "buildup",
        "section",
        "transition",
        "song structure",
        "how long",
        "how many bars",
        "form",
        "tension",
        "release",
        "energy",
    ),
    "mixing": (
        "mix",
        "mixing",
        "eq",
        "equalizer",
        "compression",
        "compressor",
        "mastering",
        "master",
        "sidechain",
        "side chain",
        "reverb",
        "delay",
        "stereo",
        "width",
        "gain",
        "headroom",
        "loudness",
        "lufs",
        "level",
        "frequency",
        "high pass",
        "low pass",
        "bus",
        "stem",
        "parallel",
        "limiter",
        "transient",
    ),
    "genre_analysis": (
        "organic house",
        "progressive house",
        "melodic techno",
        "deep house",
        "techno",
        "house",
        "genre",
        "style",
        "bpm",
        "tempo",
        "groove",
        "swing",
        "camelot",
        "harmonic mixing",
        "key",
        "kick",
        "drum",
        "percussion",
        "reference",
        "vibe",
    ),
    "live_performance": (
        "dj",
        "djing",
        "set",
        "live",
        "performance",
        "ableton",
        "workflow",
        "stems",
        "cue",
        "beatmatch",
        "rekordbox",
        "serato",
        "pioneer",
        "cdj",
        "controller",
        "transition",
        "mix",
        "set list",
    ),
    "practice": (
        "practice",
        "routine",
        "habit",
        "discipline",
        "mindset",
        "creativity",
        "wellbeing",
        "feedback",
        "learning",
        "study",
        "improve",
        "skill",
        "goal",
        "session",
        "progress",
        "journal",
        "consistency",
    ),
}

# Minimum keyword matches in a query to activate a sub-domain
_DEFAULT_VOTE_THRESHOLD: int = 1

# Maximum sub-domains to return (avoids over-broadening retrieval)
_MAX_ACTIVE_SUB_DOMAINS: int = 3


@dataclass(frozen=True)
class SubDomainDetectionResult:
    """
    Result of sub-domain detection for a single query.

    Attributes:
        query: The original query string (lowercased).
        active: Ordered list of detected sub-domains, highest votes first.
            Empty list means no sub-domain was detected (use global search).
        votes: Mapping of sub-domain → vote count for all sub-domains.
    """

    query: str
    active: tuple[str, ...]
    votes: dict[str, int]


def detect_sub_domains(
    query: str,
    *,
    vote_threshold: int = _DEFAULT_VOTE_THRESHOLD,
    max_results: int = _MAX_ACTIVE_SUB_DOMAINS,
) -> SubDomainDetectionResult:
    """
    Detect which music production sub-domains are relevant to a query.

    Uses keyword voting: each sub-domain keyword present in the query
    contributes one vote. Sub-domains with votes >= vote_threshold are
    returned as active, sorted by vote count descending.

    Args:
        query: User query string.
        vote_threshold: Minimum keyword hits to activate a sub-domain.
            Default is 1 — even a single strong keyword is enough.
        max_results: Maximum number of active sub-domains to return.

    Returns:
        SubDomainDetectionResult with active sub-domains and vote breakdown.

    Raises:
        ValueError: If vote_threshold < 1 or max_results < 1.
    """
    if vote_threshold < 1:
        raise ValueError(f"vote_threshold must be >= 1, got {vote_threshold}")
    if max_results < 1:
        raise ValueError(f"max_results must be >= 1, got {max_results}")

    query_lower = query.lower()

    votes: dict[str, int] = {}
    for sub_domain, keywords in _QUERY_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in query_lower)
        votes[sub_domain] = count

    active = [
        sd
        for sd, count in sorted(votes.items(), key=lambda x: x[1], reverse=True)
        if count >= vote_threshold
    ][:max_results]

    return SubDomainDetectionResult(
        query=query_lower,
        active=tuple(active),
        votes=votes,
    )


def primary_sub_domain(query: str) -> str | None:
    """
    Return the single most relevant sub-domain for a query, or None.

    Convenience wrapper around ``detect_sub_domains`` for callers that
    need at most one sub-domain filter (e.g. targeted retrieval).

    Args:
        query: User query string.

    Returns:
        The sub-domain with the highest vote count if any keyword matched,
        otherwise ``None``.
    """
    result = detect_sub_domains(query, max_results=1)
    return result.active[0] if result.active else None

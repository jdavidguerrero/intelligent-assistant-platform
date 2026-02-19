"""Pure sub-domain inference logic for music knowledge chunks.

Two-pass classification:
  Pass 1 (path): Match source_path against per-sub-domain PATH_PATTERNS.
                 Yields confidence=1.0, method="path".
  Pass 2 (keyword): Count keyword matches in lowercased text.
                    Requires >= 2 matches. confidence=min(0.5 + count*0.05, 0.9).
Returns None if neither pass finds a match.
"""

from __future__ import annotations

from domains.music.arrangement import keywords as arrangement_kw
from domains.music.genre_analysis import keywords as genre_analysis_kw
from domains.music.live_performance import keywords as live_performance_kw
from domains.music.mixing import keywords as mixing_kw
from domains.music.practice import keywords as practice_kw
from domains.music.sound_design import keywords as sound_design_kw
from domains.music.sub_domains import SubDomainTag

# Ordered mapping: sub_domain_name -> keywords module
_SUB_DOMAIN_MODULES: tuple[tuple[str, object], ...] = (
    ("sound_design", sound_design_kw),
    ("arrangement", arrangement_kw),
    ("mixing", mixing_kw),
    ("genre_analysis", genre_analysis_kw),
    ("live_performance", live_performance_kw),
    ("practice", practice_kw),
)


def infer_sub_domain(source_path: str, text: str = "") -> SubDomainTag | None:
    """Infer the music sub-domain for a chunk from its path and/or text.

    Pass 1 checks whether ``source_path`` contains any of the PATH_PATTERNS
    registered for each sub-domain (case-insensitive substring match).  The
    first sub-domain whose pattern matches wins with confidence=1.0.

    Pass 2 counts how many of a sub-domain's KEYWORDS appear in ``text``
    (lowercased).  The sub-domain with the highest count wins, provided it
    has at least 2 matches.  Confidence is capped at 0.9.

    Returns ``None`` when neither pass produces a match.
    """
    path_lower = source_path.lower()

    # Pass 1: path-based matching
    for sub_domain, module in _SUB_DOMAIN_MODULES:
        patterns: tuple[str, ...] = module.PATH_PATTERNS  # type: ignore[attr-defined]
        for pattern in patterns:
            if pattern.lower() in path_lower:
                return SubDomainTag(
                    sub_domain=sub_domain,
                    confidence=1.0,
                    method="path",
                )

    # Pass 2: keyword-based matching
    text_lower = text.lower()
    best_sub_domain: str | None = None
    best_count: int = 0

    for sub_domain, module in _SUB_DOMAIN_MODULES:
        keywords: tuple[str, ...] = module.KEYWORDS  # type: ignore[attr-defined]
        count = sum(1 for kw in keywords if kw in text_lower)
        if count > best_count:
            best_count = count
            best_sub_domain = sub_domain

    if best_count >= 2 and best_sub_domain is not None:
        confidence = min(0.5 + best_count * 0.05, 0.9)
        return SubDomainTag(
            sub_domain=best_sub_domain,
            confidence=confidence,
            method="keyword",
        )

    return None

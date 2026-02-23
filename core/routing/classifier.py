"""Musical task classifier — pure rule-based classification.

Classifies a natural-language query into one of three musical task types:
  - factual:  Knowledge lookup (key, BPM, technique definition)
  - creative: Synthesis / planning (practice plan, arrangement analysis)
  - realtime: Live-assist (beat detection, monitoring, transcription)

This module is core/ pure:
  - No I/O, no filesystem, no network, no datetime.now()
  - Deterministic: same input → same output, always
  - Mirrors the regex-signal pattern from ingestion/memory_extractor.py
"""

from __future__ import annotations

import re

from core.routing.types import ClassificationResult, TaskType

# ---------------------------------------------------------------------------
# Signal dictionaries
# ---------------------------------------------------------------------------

# Factual signals: queries that ask for definitions, values, or explanations
# of known musical concepts. These map to lookup tasks — cheap models suffice.
_FACTUAL_SIGNALS: list[str] = [
    r"\bwhat (key|bpm|tempo|scale|chord|note|interval|mode|plugin|effect|tool)\b",
    r"\bwhat is\b",
    r"\bwhat are\b",
    r"\bwhat does .{1,40} (mean|stand for|do)\b",
    r"\bdefine\b",
    r"\bexplain\b",
    r"\bhow (does|do)\b",
    r"\blist (the|all|some)\b",
    r"\brelative (major|minor)\b",
    r"\b(adsr|eq|lfo|fx|daw|midi|bpm|vst|au|reverb|delay|compressor|limiter)\b",
    r"\bname (the|a|some)\b",
    r"\bhow many\b",
    r"\bwhat sample rate\b",
    r"\bwhat frequency\b",
    r"\bwhat range\b",
    r"\bwhat tempo\b",
    r"\bis .{1,30} a\b",
    r"\bwhich (key|scale|mode|chord)\b",
    r"\bwhat interval\b",
    r"\bwhat note\b",
]

# Creative signals: queries that require synthesis, planning, or personalised
# advice. These benefit from a more capable model.
_CREATIVE_SIGNALS: list[str] = [
    r"\banalyze\b",
    r"\banalyse\b",
    r"\bsuggest\b",
    r"\bcreate (a |an |my )?(practice |session |arrangement |workflow |production )?plan\b",
    r"\bdesign\b",
    r"\bimprove\b",
    r"\boptimize\b",
    r"\boptimise\b",
    r"\bwhat should i\b",
    r"\bhow (can|should) i (improve|get better|develop|work on|practice|learn)\b",
    r"\bbased on (my|the) (last|previous|recent|past)\b",
    r"\bgiven (my|the) (skill|level|history|sessions|progress|feedback)\b",
    r"\b\d+[- ]week plan\b",
    r"\b(two|three|four|six|eight)[- ]week\b",
    r"\b(practice|session|recording|production|study) plan\b",
    r"\breview\b",
    r"\bcritique\b",
    r"\bfor (my|the) next\b",
    r"\bhelp me (arrange|structure|build|develop|improve)\b",
    r"\bwhat('s| is) the best way to\b",
    r"\bgive me (advice|feedback|recommendations|tips)\b",
    r"\bplan (my|a|an|the)\b",
    r"\bschedule\b",
    r"\bprogress\b",
    r"\blearning path\b",
    r"\broadmap\b",
]

# Realtime signals: queries that reference live / in-the-moment context.
# These route to the cross-provider fallback tier (Anthropic Haiku).
_REALTIME_SIGNALS: list[str] = [
    r"\bright now\b",
    r"\breal.?time\b",
    r"\bimmediately\b",
    r"\binstantly\b",
    r"\binstant\b",
    r"\bbeat (detection|counting|matching|tracking)\b",
    r"\bdetect\b",
    r"\brecognize\b",
    r"\bidentify.*pattern\b",
    r"\btranscribe\b",
    r"\bwhile\b.{0,20}(playing|performing|recording|djing|mixing)\b",
    r"\bduring (the )?(performance|show|live set|gig|concert)\b",
    r"\bmonitoring\b",
    r"\blive (performance|set|mix|monitoring)\b",
    r"\bon stage\b",
    r"\bat the venue\b",
    r"\bno (wifi|internet|connection)\b",
    r"\boffline\b",
]

# ---------------------------------------------------------------------------
# Confidence formula
# ---------------------------------------------------------------------------

_SIGNAL_MAP: dict[TaskType, list[str]] = {
    "factual": _FACTUAL_SIGNALS,
    "creative": _CREATIVE_SIGNALS,
    "realtime": _REALTIME_SIGNALS,
}


def _count_matches(query: str, signals: list[str]) -> list[str]:
    """Return list of signals that match the query (case-insensitive)."""
    return [s for s in signals if re.search(s, query, re.IGNORECASE)]


def _confidence(n_matches: int) -> float:
    """Asymptotic confidence from match count.

    confidence = n / (n + 1)  →  ranges (0.0, 1.0), never reaches 1.0.
    0 matches → 0.0  |  1 match → 0.5  |  3 matches → 0.75  |  9 matches → 0.90
    """
    return round(n_matches / (n_matches + 1), 4)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_musical_task(query: str) -> ClassificationResult:
    """Classify a musical query into factual / creative / realtime.

    Algorithm:
    1. Count regex signal matches per task type.
    2. The type with the most matches wins.
    3. On a tie: creative > realtime > factual (prefer quality over speed).
    4. Zero matches → factual (safe, cheap default).

    This module is core/ pure. No I/O, no side effects.

    Args:
        query: Raw user query string (non-empty).

    Returns:
        ClassificationResult with task_type, confidence, and matched_signals.

    Raises:
        ValueError: If query is empty or whitespace-only.
    """
    if not query or not query.strip():
        raise ValueError("query must be a non-empty string")

    # Count matches per type
    matches_per_type: dict[TaskType, list[str]] = {
        t: _count_matches(query, signals) for t, signals in _SIGNAL_MAP.items()
    }

    counts: dict[TaskType, int] = {t: len(m) for t, m in matches_per_type.items()}

    # Determine winning type with tie-break: creative > realtime > factual
    # (ties are broken in favour of the more capable / intentional type)
    TIE_PRIORITY: list[TaskType] = ["creative", "realtime", "factual"]
    best_type: TaskType = "factual"
    best_count = 0

    for task_type in TIE_PRIORITY:
        if counts[task_type] > best_count:
            best_count = counts[task_type]
            best_type = task_type
        elif counts[task_type] == best_count and best_count > 0:
            # Equal count — higher-priority type in TIE_PRIORITY list wins.
            # creative is first in the list, so it always beats others on a tie.
            idx_best = TIE_PRIORITY.index(best_type)
            idx_curr = TIE_PRIORITY.index(task_type)
            if idx_curr < idx_best:
                best_type = task_type

    confidence = _confidence(best_count)
    matched = tuple(matches_per_type[best_type])

    return ClassificationResult(
        task_type=best_type,
        confidence=confidence,
        matched_signals=matched,
    )

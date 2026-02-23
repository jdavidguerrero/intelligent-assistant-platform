"""Memory extraction from musical assistant conversations.

Two extraction strategies that can be used independently or combined:

Strategy A — Rule-based (fast, deterministic, no API cost):
    Scans (query, answer) for linguistic signals indicating a
    preference, session discovery, growth milestone, or creative idea.

Strategy B — LLM-based (more accurate, uses GenerationProvider):
    One LLM call with temperature=0 and JSON response_format.
    Falls back silently to [] on any parse/network error.

Both strategies return ExtractedMemory objects with a confidence score.
The public extract_memories() function combines and deduplicates results.

CRITICAL: extract_memories() NEVER raises. Memory extraction is
best-effort and must never block or degrade the primary RAG response.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from core.generation.base import GenerationProvider, GenerationRequest, Message
from core.memory.types import MemoryType

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Linguistic signal patterns per memory type                           #
# ------------------------------------------------------------------ #

_PREFERENCE_SIGNALS: list[str] = [
    r"\bi prefer\b",
    r"\bmy favorite\b",
    r"\bmy go-to\b",
    r"\bi (always|usually|tend to) (use|work|produce)\b",
    r"\bmy preferred\b",
    r"\bi like working in\b",
    r"\bi love using\b",
]

_SESSION_SIGNALS: list[str] = [
    r"\bi (just |finally )?(discovered|found|learned|realized|figured out)\b",
    r"\btoday i\b",
    r"\bthis session\b",
    r"\bnote to self[:\s]",
    r"\bjust got\b",
    r"\bi('ve| have) been working on\b",
]

_GROWTH_SIGNALS: list[str] = [
    r"\bi('ve| have) (improved|gotten better|mastered|leveled up)\b",
    r"\bmaking (great )?progress\b",
    r"\bi('m| am) getting better\b",
    r"\b(skill|technique|area) i('m| am) (working|focusing) on\b",
    r"\bpracticing\b.{0,50}\b(daily|every day|consistently|regularly)\b",
    r"\bi can (finally|now) (do|make|create)\b",
]

_CREATIVE_SIGNALS: list[str] = [
    r"\btry this later\b",
    r"\bidea[:\s]",
    r"\bwhat if\b.{0,80}\?",
    r"\bexperiment with\b",
    r"\bcould (work|sound|be interesting)\b",
    r"\bremind me to\b",
    r"\bmight be worth\b",
]

_SIGNAL_MAP: dict[MemoryType, list[str]] = {
    "preference": _PREFERENCE_SIGNALS,
    "session": _SESSION_SIGNALS,
    "growth": _GROWTH_SIGNALS,
    "creative": _CREATIVE_SIGNALS,
}

# Confidence scores for rule-based matches (conservative — LLM is more accurate)
_RULE_CONFIDENCE: dict[MemoryType, float] = {
    "preference": 0.75,
    "session": 0.70,
    "growth": 0.72,
    "creative": 0.68,
}


# ------------------------------------------------------------------ #
# Data types                                                           #
# ------------------------------------------------------------------ #


@dataclass(frozen=True)
class ExtractedMemory:
    """A candidate memory fact extracted from a conversation turn.

    Attributes:
        memory_type: Inferred category.
        content: Extracted or summarized text (trimmed from source).
        confidence: 0.0–1.0. Rule-based uses fixed values; LLM-based
            uses model-calibrated scores.
        method: "rule" or "llm".
    """

    memory_type: MemoryType
    content: str
    confidence: float
    method: str


# ------------------------------------------------------------------ #
# Strategy A — Rule-based extraction                                   #
# ------------------------------------------------------------------ #


def extract_memories_rule_based(query: str, answer: str) -> list[ExtractedMemory]:
    """Extract memorable facts using regex signal matching.

    Scans query and answer text for linguistic signals. When a signal
    fires, the sentence containing it is used as the memory content.

    Args:
        query: The user's question.
        answer: The assistant's answer.

    Returns:
        List of ExtractedMemory objects. May be empty. Never raises.
    """
    combined = f"{query}\n{answer}"
    # Split into sentences (rough, good enough for signal detection)
    sentences = re.split(r"(?<=[.!?])\s+", combined)

    results: list[ExtractedMemory] = []
    for memory_type, patterns in _SIGNAL_MAP.items():
        for sentence in sentences:
            for pattern in patterns:
                if re.search(pattern, sentence, re.IGNORECASE):
                    content = sentence.strip()
                    if len(content) > 5:  # ignore trivially short matches
                        results.append(
                            ExtractedMemory(
                                memory_type=memory_type,
                                content=content[:500],  # cap at 500 chars
                                confidence=_RULE_CONFIDENCE[memory_type],
                                method="rule",
                            )
                        )
                        break  # one match per sentence per type is enough

    return results


# ------------------------------------------------------------------ #
# Strategy B — LLM-based extraction                                    #
# ------------------------------------------------------------------ #

_EXTRACTION_SYSTEM_PROMPT = """\
You are a memory extraction assistant for a music producer.
Given a conversation exchange, identify facts worth remembering about the
user's preferences, discoveries, growth, or creative ideas.

Return a JSON array of objects (empty array if nothing memorable):
[
  {
    "memory_type": "preference" | "session" | "growth" | "creative",
    "content": "Single sentence capturing the memorable fact.",
    "confidence": 0.8
  }
]

Memory type guide:
- preference: Stable preferences (favorite plugins, genres, BPM ranges, keys, workflow habits)
- session: What happened in this specific session (discoveries, problems solved, new techniques tried)
- growth: Skills improving, areas to develop, technique milestones reached
- creative: Ideas to try later, sonic experiments, "what if" thoughts, reminders

Rules:
- Only include facts where confidence >= 0.6
- Keep content to one clear sentence (max 200 chars)
- Return ONLY valid JSON, no prose, no markdown fences
- Return [] if nothing memorable was said
"""


def extract_memories_llm(
    query: str,
    answer: str,
    generator: GenerationProvider,
) -> list[ExtractedMemory]:
    """Extract memorable facts using an LLM call.

    Makes one LLM call at temperature=0 with JSON response format.
    Parses and validates the JSON response. Falls back to empty list
    on any error (parse failure, network error, invalid JSON structure).

    Args:
        query: The user's question.
        answer: The assistant's answer.
        generator: GenerationProvider for the LLM call.

    Returns:
        List of ExtractedMemory objects. Never raises — errors return [].
    """
    user_content = f"## User question\n{query}\n\n## Assistant answer\n{answer}"
    request = GenerationRequest(
        messages=(
            Message(role="system", content=_EXTRACTION_SYSTEM_PROMPT),
            Message(role="user", content=user_content),
        ),
        temperature=0.0,
        max_tokens=512,
    )
    try:
        response = generator.generate(request)
        raw = response.content.strip()
        # Strip markdown fences if model added them despite instructions
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        data = json.loads(raw)
        if not isinstance(data, list):
            logger.debug("LLM extractor: expected list, got %s", type(data))
            return []
        results: list[ExtractedMemory] = []
        valid_types = {"preference", "session", "growth", "creative"}
        for item in data:
            if not isinstance(item, dict):
                continue
            mt = item.get("memory_type", "")
            content = str(item.get("content", "")).strip()
            confidence = float(item.get("confidence", 0.0))
            if mt not in valid_types:
                continue
            if not content:
                continue
            results.append(
                ExtractedMemory(
                    memory_type=mt,  # type: ignore[arg-type]
                    content=content[:500],
                    confidence=confidence,
                    method="llm",
                )
            )
        return results
    except Exception as exc:
        logger.debug("LLM memory extraction failed (best-effort): %s", exc)
        return []


# ------------------------------------------------------------------ #
# Public API                                                           #
# ------------------------------------------------------------------ #


def extract_memories(
    query: str,
    answer: str,
    generator: GenerationProvider | None = None,
    use_llm: bool = True,
    confidence_threshold: float = 0.6,
) -> list[ExtractedMemory]:
    """Extract memorable musical facts from a (query, answer) exchange.

    Combines rule-based and optional LLM extraction. Deduplicates by
    lowercased content prefix. LLM results override rule-based results
    when content overlaps (LLM has higher precision).

    Args:
        query: The user's question.
        answer: The assistant's answer.
        generator: Optional LLM provider. If None, rule-based only.
        use_llm: Whether to call the LLM (requires generator != None).
        confidence_threshold: Minimum confidence to include in results.

    Returns:
        Deduplicated list of ExtractedMemory above the threshold.
        NEVER raises — all errors return [].
    """
    try:
        rule_results = extract_memories_rule_based(query, answer)
        llm_results: list[ExtractedMemory] = []
        if use_llm and generator is not None:
            llm_results = extract_memories_llm(query, answer, generator)

        # Merge: start with LLM results (higher precision), add rule results
        # that don't overlap with any LLM result by content prefix
        merged: list[ExtractedMemory] = list(llm_results)
        llm_prefixes = {m.content[:50].lower() for m in llm_results}
        for r in rule_results:
            if r.content[:50].lower() not in llm_prefixes:
                merged.append(r)

        return [m for m in merged if m.confidence >= confidence_threshold]
    except Exception as exc:
        logger.warning("extract_memories failed (best-effort): %s", exc)
        return []

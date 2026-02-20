"""
Query expansion and intent detection for improved retrieval quality.

Implements domain-specific query expansion to improve semantic matching
for specialized music production queries (mastering, mixing, sound design,
synthesis, rhythm, chord progressions, organic house, afrobeat, etc.).

Design:
    - ``DomainConfig`` defines each domain's keywords, expansion terms,
      and scoring metadata — open/closed principle.
    - ``detect_intents()`` returns *all* matching domains (multi-intent),
      sorted by weighted score.
    - ``expand_query()`` uses the top-ranked intent(s) for expansion.
    - The old ``detect_mastering_intent()`` is kept for backward compat.

Domain coverage:
    mastering        — final mix, LUFS, limiting, loudness
    mixing           — EQ, compression, reverb, panning, bus processing
    sound_design     — synthesis, Serum, wavetable, oscillators, modulation
    synthesis        — synthesizer anatomy, ADSR, LFO, filters, envelopes
    rhythm           — drum patterns, groove, quantization, swing, timing
    chord_progressions — harmony, chords, scales, modes, progressions
    organic_house    — genre-specific: organic house, deep house, All Day I Dream
    afrobeat         — afro house, Black Coffee, Afrobeat rhythms, clave
    arrangement      — track structure, drops, breakdowns, build-ups
    bass_design      — bassline, sub bass, 808, kick-bass relationship
"""

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QueryIntent:
    """Detected intent from a search query."""

    category: str  # domain name (e.g. "mastering", "mixing", "general")
    confidence: float  # 0.0 to 1.0
    keywords: list[str]  # Matched keywords


@dataclass(frozen=True)
class DomainConfig:
    """Configuration for a single domain in the intent registry.

    Attributes:
        name: Domain identifier (e.g. ``"mastering"``).
        keywords: Positive-signal keywords to match in query.
        expansion_terms: Terms appended to the query when this domain matches.
        base_confidence: Maximum confidence when all keywords match.
        negative_keywords: Keywords that *exclude* this domain if present.
    """

    name: str
    keywords: list[str]
    expansion_terms: list[str]
    base_confidence: float = 1.0
    negative_keywords: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Intent registry — add new domains here, no function changes required
# ---------------------------------------------------------------------------

DOMAIN_REGISTRY: list[DomainConfig] = [
    DomainConfig(
        name="mastering",
        keywords=[
            "mastering",
            "master",
            "mastering chain",
            "mastering process",
            "loudness",
            "limiting",
            "limiter",
            "final mix",
            "stereo widening",
            "multiband",
            "lufs",
            "true peak",
            "ceiling",
            "dithering",
            "stem mastering",
        ],
        expansion_terms=[
            "mastering",
            "final mix",
            "audio processing",
            "mixing",
        ],
        base_confidence=1.0,
        negative_keywords=[
            "python",
            "java",
            "coding",
            "programming",
            "git",
            "docker",
        ],
    ),
    DomainConfig(
        name="mixing",
        keywords=[
            "mixing",
            "mix",
            "eq",
            "equalization",
            "compression",
            "compressor",
            "sidechain",
            "reverb",
            "delay",
            "panning",
            "balance",
            "high-pass",
            "highpass",
            "low-pass",
            "lowpass",
            "high pass filter",
            "low pass filter",
            "frequency",
            "stereo width",
            "mono",
            "headroom",
            "volume",
            "fader",
            "vocal",
            "drum bus",
            "bus",
            "processing",
            "chain",
            "audio processing",
            "bus",
            "gain staging",
            "stereo field",
            "transient",
            "parallel",
            "saturation",
        ],
        expansion_terms=[
            "mixing",
            "audio processing",
            "production",
        ],
        base_confidence=0.8,
        negative_keywords=[
            "python",
            "java",
            "coding",
            "programming",
            "git",
            "docker",
        ],
    ),
    DomainConfig(
        name="sound_design",
        keywords=[
            "sound design",
            "serum",
            "wavetable",
            "oscillator",
            "waveform",
            "saw wave",
            "sine wave",
            "patch",
            "preset",
            "timbre",
            "texture",
            "synth sound",
            "design a sound",
            "create a sound",
            "make a sound",
            "bass sound",
            "lead sound",
            "pad sound",
            "pluck",
            "fm synthesis",
            "additive",
            "granular",
        ],
        expansion_terms=[
            "sound design",
            "synthesis",
            "synth programming",
            "timbre",
        ],
        base_confidence=0.9,
        negative_keywords=["python", "java", "coding", "programming"],
    ),
    DomainConfig(
        name="synthesis",
        keywords=[
            "synthesis",
            "synthesizer",
            "synth",
            "adsr",
            "envelope",
            "attack",
            "decay",
            "sustain",
            "release",
            "lfo",
            "synth filter",
            "filter cutoff",
            "cutoff frequency",
            "resonance",
            "modulation",
            "modulate",
            "sub oscillator",
            "detuning",
            "unison",
            "fm",
            "amplitude modulation",
            "frequency modulation",
            "ring modulation",
            "vocoder",
            "analog",
            "digital synth",
        ],
        expansion_terms=[
            "synthesis",
            "synthesizer programming",
            "sound design",
            "audio",
        ],
        base_confidence=0.85,
        negative_keywords=["python", "java", "coding", "programming"],
    ),
    DomainConfig(
        name="rhythm",
        keywords=[
            "rhythm",
            "drum",
            "beat",
            "groove",
            "quantize",
            "quantization",
            "swing",
            "shuffle",
            "kick",
            "snare",
            "hi-hat",
            "hihat",
            "percussion",
            "pattern",
            "polyrhythm",
            "syncopation",
            "tempo",
            "bpm",
            "timing",
            "microtiming",
            "humanize",
            "drum loop",
            "four-on-the-floor",
            "16 step",
            "step sequencer",
        ],
        expansion_terms=[
            "rhythm",
            "groove",
            "drum programming",
            "percussion",
        ],
        base_confidence=0.85,
        negative_keywords=["python", "java", "coding", "programming"],
    ),
    DomainConfig(
        name="chord_progressions",
        keywords=[
            "chord",
            "chords",
            "chord progression",
            "harmony",
            "harmonic",
            "scale",
            "key",
            "minor",
            "major",
            "mode",
            "dorian",
            "phrygian",
            "lydian",
            "mixolydian",
            "modulation",
            "tonal",
            "interval",
            "triad",
            "seventh chord",
            "extended chord",
            "voicing",
            "inversion",
            "borrowed chord",
            "circle of fifths",
            "roman numeral",
            "music theory",
        ],
        expansion_terms=[
            "chord progressions",
            "harmony",
            "music theory",
            "scales",
        ],
        base_confidence=0.85,
        negative_keywords=["python", "java", "coding", "programming"],
    ),
    DomainConfig(
        name="organic_house",
        keywords=[
            "organic house",
            "organic deep house",
            "all day i dream",
            "anjunadeep",
            "melodic house",
            "deep progressive",
            "deep house",
            "afro house",
            "africanism",
            "world music",
            "tribal",
            "ethnic",
            "conga",
            "bongo",
            "shaker",
            "flute",
            "acoustic",
            "warm bass",
            "sebastian leger",
            "guy j",
            "volen sentir",
            "tim green",
        ],
        expansion_terms=[
            "organic house",
            "deep house",
            "melodic",
            "groove production",
        ],
        base_confidence=0.9,
        negative_keywords=["python", "java", "coding", "programming"],
    ),
    DomainConfig(
        name="afrobeat",
        keywords=[
            "afrobeat",
            "afro house",
            "black coffee",
            "clave",
            "tresillo",
            "3+3+2",
            "son clave",
            "rumba clave",
            "afro-cuban",
            "latin rhythm",
            "samba",
            "bossa nova",
            "baiao",
            "cumbia",
            "candombe",
            "djembe",
            "kalimba",
            "marimba",
            "african",
            "polyrhythm",
            "cross-rhythm",
        ],
        expansion_terms=[
            "afrobeat",
            "rhythm",
            "African percussion",
            "groove",
        ],
        base_confidence=0.9,
        negative_keywords=["python", "java", "coding", "programming"],
    ),
    DomainConfig(
        name="arrangement",
        keywords=[
            "arrangement",
            "structure",
            "track structure",
            "intro",
            "drop",
            "breakdown",
            "build",
            "buildup",
            "bridge",
            "verse",
            "chorus",
            "hook",
            "transition",
            "outro",
            "riser",
            "fill",
            "tension",
            "release",
            "energy",
            "sections",
            "8 bars",
            "16 bars",
            "32 bars",
        ],
        expansion_terms=[
            "arrangement",
            "track structure",
            "composition",
            "form",
        ],
        base_confidence=0.85,
        negative_keywords=["python", "java", "coding", "programming"],
    ),
    DomainConfig(
        name="bass_design",
        keywords=[
            "bass",
            "bassline",
            "sub bass",
            "808",
            "kick bass",
            "bass frequency",
            "low end",
            "sub",
            "bass synth",
            "bass design",
            "bass writing",
            "bass pattern",
            "bass groove",
            "reese bass",
            "wobble bass",
            "acid bass",
            "tb-303",
        ],
        expansion_terms=[
            "bass",
            "low end",
            "sub bass",
            "kick bass relationship",
        ],
        base_confidence=0.9,
        negative_keywords=["python", "java", "coding", "programming"],
    ),
]


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def _score_domain(query_lower: str, domain: DomainConfig) -> QueryIntent | None:
    """Score a single domain against the query.

    Returns ``None`` if no keywords matched or a negative keyword is present.
    Otherwise returns a ``QueryIntent`` with confidence proportional to the
    fraction of keywords matched, scaled by ``domain.base_confidence``.
    """
    # Check negative keywords first
    for neg in domain.negative_keywords:
        if neg in query_lower:
            return None

    matched = [kw for kw in domain.keywords if kw in query_lower]
    if not matched:
        return None

    # Confidence = (matched / total) * base_confidence
    ratio = len(matched) / len(domain.keywords)
    confidence = round(min(1.0, ratio * domain.base_confidence), 4)

    return QueryIntent(
        category=domain.name,
        confidence=confidence,
        keywords=matched,
    )


def detect_intents(
    query: str,
    *,
    domains: list[DomainConfig] | None = None,
) -> list[QueryIntent]:
    """Detect *all* matching intents for a query, sorted by confidence desc.

    This is the **multi-intent** replacement for ``detect_mastering_intent``.

    Args:
        query: User search query.  Must be non-empty.
        domains: Optional override of the domain registry.

    Returns:
        Sorted list of ``QueryIntent`` (highest confidence first).
        Empty list when no domain matches → treat as ``"general"``.

    Raises:
        ValueError: If *query* is empty or whitespace-only.
    """
    if not query or not query.strip():
        raise ValueError("query must be a non-empty string")

    registry = domains if domains is not None else DOMAIN_REGISTRY
    query_lower = query.lower()

    intents: list[QueryIntent] = []
    for domain in registry:
        intent = _score_domain(query_lower, domain)
        if intent is not None:
            intents.append(intent)

    # Sort by confidence descending, then by category name for determinism
    intents.sort(key=lambda i: (-i.confidence, i.category))
    return intents


def detect_mastering_intent(query: str) -> QueryIntent:
    """Detect if query is about mastering/mixing with keyword matching.

    Backward-compatible wrapper around ``detect_intents()``.

    Args:
        query: User search query.

    Returns:
        Single ``QueryIntent`` — the top match, or a ``"general"`` fallback.
    """
    if not query or not query.strip():
        return QueryIntent(category="general", confidence=0.0, keywords=[])

    intents = detect_intents(query)

    if intents:
        return intents[0]

    return QueryIntent(category="general", confidence=0.0, keywords=[])


def expand_query(query: str, intent: QueryIntent) -> str:
    """Expand query with domain-specific terms based on detected intent.

    Looks up the intent's category in ``DOMAIN_REGISTRY`` to find the
    matching expansion terms.  Falls back to no expansion if the domain
    is ``"general"`` or not found.

    Args:
        query: Original search query.
        intent: Detected intent (from ``detect_mastering_intent`` or
            ``detect_intents``).

    Returns:
        Expanded query string with additional context terms appended.

    Raises:
        ValueError: If *query* is ``None``.
    """
    if query is None:
        raise ValueError("query must not be None")

    if intent.category == "general":
        return query

    # Find expansion terms from registry
    expansion_terms: list[str] = []
    for domain in DOMAIN_REGISTRY:
        if domain.name == intent.category:
            expansion_terms = domain.expansion_terms
            break

    if not expansion_terms:
        return query

    # Remove terms already in query (case-insensitive)
    query_lower = query.lower()
    unique_additions = [term for term in expansion_terms if term not in query_lower]

    if not unique_additions:
        return query

    return f"{query} {' '.join(unique_additions)}"

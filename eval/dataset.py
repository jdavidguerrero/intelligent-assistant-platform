"""Golden dataset — 50 musical Q&A pairs for evaluation.

Structure
---------
50 queries across 6 sub-domains + adversarial set:
  - Sound Design     (5 single-domain)
  - Arrangement      (5 single-domain)
  - Mixing           (5 single-domain)
  - Genre Analysis   (5 single-domain)
  - Live Performance (5 single-domain)
  - Practice         (5 single-domain)
  - Cross-domain    (10 queries requiring 2+ sub-domains)
  - Adversarial     (10 out-of-corpus / hallucination triggers)

Ground truth verified against Pete Tong Academy course content
and production library (Bob Katz, mastering references).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SubDomain(str, Enum):
    SOUND_DESIGN = "sound_design"
    ARRANGEMENT = "arrangement"
    MIXING = "mixing"
    GENRE = "genre"
    LIVE_PERFORMANCE = "live_performance"
    PRACTICE = "practice"
    CROSS = "cross"  # requires 2+ sub-domains
    ADVERSARIAL = "adversarial"  # out-of-corpus or hallucination triggers


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


@dataclass(frozen=True)
class GoldenQuery:
    """One golden Q&A pair with ground truth annotations.

    Attributes
    ----------
    id:
        Unique identifier, e.g. ``"sd_001"`` for sound-design query 1.
    question:
        Exact question string sent to the /ask endpoint.
    expected_topics:
        Key musical terms that MUST appear (case-insensitive) in the answer
        for a PASS.  At least one topic must match.
    expected_sources:
        Partial source-name patterns to match against ``sources`` in the
        /ask response.  At least one must appear for a PASS (non-adversarial).
    sub_domain:
        Primary sub-domain category.
    difficulty:
        Easy / medium / hard classification.
    adversarial:
        If True the query is out-of-corpus or a hallucination trigger.
        Expected result: HTTP 422 (insufficient_knowledge) or explicit refusal.
    cross_domains:
        For CROSS queries, the additional sub-domains involved.
    notes:
        Human notes about expected answer behaviour.
    """

    id: str
    question: str
    expected_topics: list[str]
    expected_sources: list[str]
    sub_domain: SubDomain
    difficulty: Difficulty
    adversarial: bool = False
    cross_domains: list[SubDomain] = field(default_factory=list)
    notes: str = ""


# ---------------------------------------------------------------------------
# Day 1 — Sound Design (5) + Arrangement (5) + Mixing (5)
# ---------------------------------------------------------------------------

SOUND_DESIGN: list[GoldenQuery] = [
    GoldenQuery(
        id="sd_001",
        question="What is an ADSR envelope and how does each stage shape the dynamics of a synthesizer sound?",
        expected_topics=["attack", "decay", "sustain", "release", "envelope"],
        expected_sources=["pete-tong", "synthesis", "creating", "power-tools", "welsh"],
        sub_domain=SubDomain.SOUND_DESIGN,
        difficulty=Difficulty.EASY,
        notes="Foundational synth concept — should be covered in every course.",
    ),
    GoldenQuery(
        id="sd_002",
        question="How do you design a sub bass that sits cleanly in the low end of a house track without conflicting with the kick?",
        expected_topics=["sub bass", "low end", "frequency", "sine", "mono", "fundamental"],
        expected_sources=["pete-tong", "mixing", "production", "bob_katz"],
        sub_domain=SubDomain.SOUND_DESIGN,
        difficulty=Difficulty.MEDIUM,
        notes="Requires integration of synthesis + mixing knowledge.",
    ),
    GoldenQuery(
        id="sd_003",
        question="What is the difference between FM synthesis and subtractive synthesis when designing lead sounds?",
        expected_topics=[
            "fm",
            "subtractive",
            "operator",
            "carrier",
            "modulator",
            "filter",
            "oscillator",
        ],
        expected_sources=["pete-tong", "synthesis", "creating", "power-tools"],
        sub_domain=SubDomain.SOUND_DESIGN,
        difficulty=Difficulty.MEDIUM,
        notes="Contrast between two main synthesis paradigms.",
    ),
    GoldenQuery(
        id="sd_004",
        question="How do you use wavetable synthesis and LFO modulation to create evolving, moving pads for melodic house?",
        expected_topics=["wavetable", "lfo", "modulation", "evolving", "pad", "morphing"],
        expected_sources=["pete-tong", "synthesis", "creating", "power-tools"],
        sub_domain=SubDomain.SOUND_DESIGN,
        difficulty=Difficulty.HARD,
        notes="Advanced sound design — melodic house specific.",
    ),
    GoldenQuery(
        id="sd_005",
        question="What synthesis techniques are used to design a punchy, transient-forward kick drum for techno?",
        expected_topics=["kick", "transient", "punch", "pitch sweep", "sine", "attack", "techno"],
        expected_sources=["pete-tong", "creating", "production", "synthesis"],
        sub_domain=SubDomain.SOUND_DESIGN,
        difficulty=Difficulty.MEDIUM,
        notes="Genre-specific drum synthesis technique.",
    ),
]

ARRANGEMENT: list[GoldenQuery] = [
    GoldenQuery(
        id="arr_001",
        question="What is the typical intro-to-drop arrangement structure of a progressive house track?",
        expected_topics=["intro", "breakdown", "build", "drop", "arrangement", "progressive"],
        expected_sources=["pete-tong", "production", "arrangement"],
        sub_domain=SubDomain.ARRANGEMENT,
        difficulty=Difficulty.EASY,
        notes="Standard progressive house structure.",
    ),
    GoldenQuery(
        id="arr_002",
        question="How long should the intro of a club track be and what elements should it contain for smooth DJ mixing?",
        expected_topics=["intro", "dj", "bars", "loop", "kick", "mixing"],
        expected_sources=["pete-tong", "production", "arrangement"],
        sub_domain=SubDomain.ARRANGEMENT,
        difficulty=Difficulty.MEDIUM,
        notes="Practical arrangement for DJ context.",
    ),
    GoldenQuery(
        id="arr_003",
        question="What is the function of a breakdown in a dance track and how do you build tension before the drop?",
        expected_topics=["breakdown", "tension", "build", "drop", "energy", "automation"],
        expected_sources=["pete-tong", "production", "arrangement"],
        sub_domain=SubDomain.ARRANGEMENT,
        difficulty=Difficulty.MEDIUM,
        notes="Core tension-release structure.",
    ),
    GoldenQuery(
        id="arr_004",
        question="How do you use volume and filter automation to create a dynamic energy arc over a 6-minute club track?",
        expected_topics=["automation", "energy", "arc", "volume", "filter", "dynamics"],
        expected_sources=["pete-tong", "production", "arrangement"],
        sub_domain=SubDomain.ARRANGEMENT,
        difficulty=Difficulty.HARD,
        notes="Advanced automation-driven arrangement technique.",
    ),
    GoldenQuery(
        id="arr_005",
        question="What is a 32-bar phrase structure and how does it guide musical decisions in house music arrangement?",
        expected_topics=["phrase", "32 bar", "house", "structure", "loop", "musical"],
        expected_sources=["pete-tong", "production", "arrangement", "schachter"],
        sub_domain=SubDomain.ARRANGEMENT,
        difficulty=Difficulty.MEDIUM,
        notes="Links music theory to arrangement practice.",
    ),
]

MIXING: list[GoldenQuery] = [
    GoldenQuery(
        id="mix_001",
        question="How do you use EQ to separate kick and bass frequencies so they don't clash in a house mix?",
        expected_topics=["eq", "kick", "bass", "frequency", "low end", "separation"],
        expected_sources=["pete-tong", "mixing", "bob_katz", "masterizacion"],
        sub_domain=SubDomain.MIXING,
        difficulty=Difficulty.EASY,
        notes="Fundamental mixing technique — kick/bass relationship.",
    ),
    GoldenQuery(
        id="mix_002",
        question="What is sidechain compression and how does it make the kick and bass lock together rhythmically?",
        expected_topics=["sidechain", "compression", "kick", "bass", "pump", "groove"],
        expected_sources=["pete-tong", "mixing", "production"],
        sub_domain=SubDomain.MIXING,
        difficulty=Difficulty.MEDIUM,
        notes="Core house music mixing technique.",
    ),
    GoldenQuery(
        id="mix_003",
        question="How do you use high-pass filters on individual tracks to reduce muddiness and add clarity to a dense electronic mix?",
        expected_topics=["high pass", "filter", "muddiness", "low end", "clarity", "eq"],
        expected_sources=["pete-tong", "mixing", "bob_katz", "masterizacion"],
        sub_domain=SubDomain.MIXING,
        difficulty=Difficulty.MEDIUM,
        notes="Frequency management in dense mixes.",
    ),
    GoldenQuery(
        id="mix_004",
        question="What LUFS target should I aim for when mastering a track for streaming platforms, and how do I get there without killing dynamics?",
        expected_topics=["lufs", "mastering", "streaming", "loudness", "normalization", "dynamics"],
        expected_sources=["bob_katz", "masterizacion", "pete-tong"],
        sub_domain=SubDomain.MIXING,
        difficulty=Difficulty.MEDIUM,
        notes="Mastering for streaming — Bob Katz territory.",
    ),
    GoldenQuery(
        id="mix_005",
        question="How do you achieve stereo width in an electronic music mix while keeping it mono-compatible for club sound systems?",
        expected_topics=["stereo", "mono", "width", "phase", "mid-side", "club"],
        expected_sources=["pete-tong", "mixing", "bob_katz", "masterizacion"],
        sub_domain=SubDomain.MIXING,
        difficulty=Difficulty.HARD,
        notes="Stereo/mono compatibility — important for club context.",
    ),
]

# ---------------------------------------------------------------------------
# Day 2 — Genre (5) + Live Performance (5) + Practice (5)
# ---------------------------------------------------------------------------

GENRE: list[GoldenQuery] = [
    GoldenQuery(
        id="gen_001",
        question="What are the defining characteristics of organic house music in terms of sound palette and arrangement?",
        expected_topics=["organic", "house", "acoustic", "texture", "atmosphere", "natural"],
        expected_sources=["pete-tong", "youtube", "organic"],
        sub_domain=SubDomain.GENRE,
        difficulty=Difficulty.EASY,
        notes="Core organic house definition — YouTube transcripts have good coverage.",
    ),
    GoldenQuery(
        id="gen_002",
        question="What BPM range and rhythmic characteristics define melodic house and techno as a genre?",
        expected_topics=["melodic house", "techno", "bpm", "rhythm", "groove", "128"],
        expected_sources=["pete-tong", "youtube", "production"],
        sub_domain=SubDomain.GENRE,
        difficulty=Difficulty.MEDIUM,
        notes="Genre definition with tempo and rhythm specifics.",
    ),
    GoldenQuery(
        id="gen_003",
        question="How does Afro house differ from deep house in its use of percussion, rhythm patterns, and groove?",
        expected_topics=[
            "afro house",
            "deep house",
            "percussion",
            "rhythm",
            "groove",
            "polyrhythm",
        ],
        expected_sources=["pete-tong", "youtube", "production"],
        sub_domain=SubDomain.GENRE,
        difficulty=Difficulty.MEDIUM,
        notes="Sub-genre differentiation — rhythmic focus.",
    ),
    GoldenQuery(
        id="gen_004",
        question="What production techniques and sonic characteristics distinguish underground techno from more commercial techno?",
        expected_topics=["techno", "underground", "raw", "industrial", "atmosphere", "minimal"],
        expected_sources=["pete-tong", "youtube", "production"],
        sub_domain=SubDomain.GENRE,
        difficulty=Difficulty.HARD,
        notes="Aesthetic differentiation within techno.",
    ),
    GoldenQuery(
        id="gen_005",
        question="What makes progressive house music progressive? How does it differ from standard four-on-the-floor house music?",
        expected_topics=["progressive", "house", "journey", "evolving", "arrangement", "build"],
        expected_sources=["pete-tong", "youtube", "production"],
        sub_domain=SubDomain.GENRE,
        difficulty=Difficulty.MEDIUM,
        notes="Progressive vs standard house differentiation.",
    ),
]

LIVE_PERFORMANCE: list[GoldenQuery] = [
    GoldenQuery(
        id="live_001",
        question="What is stem mixing and how is it different from standard DJing with full stereo tracks?",
        expected_topics=["stem", "mixing", "dj", "live", "performance", "multitrack"],
        expected_sources=["pete-tong", "production", "live"],
        sub_domain=SubDomain.LIVE_PERFORMANCE,
        difficulty=Difficulty.EASY,
        notes="Foundational stem concept.",
    ),
    GoldenQuery(
        id="live_002",
        question="How do you export stems from a finished Ableton Live production for use in a live performance set?",
        expected_topics=["stem", "export", "ableton", "live", "performance", "track"],
        expected_sources=["pete-tong", "production", "ableton"],
        sub_domain=SubDomain.LIVE_PERFORMANCE,
        difficulty=Difficulty.MEDIUM,
        notes="Practical stem export workflow.",
    ),
    GoldenQuery(
        id="live_003",
        question="What features of Ableton Live support real-time stem performance and live track remixing?",
        expected_topics=["ableton", "session view", "clips", "live", "performance", "remixing"],
        expected_sources=["pete-tong", "production", "ableton"],
        sub_domain=SubDomain.LIVE_PERFORMANCE,
        difficulty=Difficulty.MEDIUM,
        notes="Ableton Live session view for performance.",
    ),
    GoldenQuery(
        id="live_004",
        question="How do you structure an Ableton Live set for a 2-hour performance using stems, clips, and effects automation?",
        expected_topics=["ableton", "session view", "clips", "performance", "set", "cue"],
        expected_sources=["pete-tong", "production", "ableton"],
        sub_domain=SubDomain.LIVE_PERFORMANCE,
        difficulty=Difficulty.HARD,
        notes="Advanced live set structure for extended performance.",
    ),
    GoldenQuery(
        id="live_005",
        question="What MIDI controllers and hardware setups work well for a stem-based Ableton Live performance?",
        expected_topics=["controller", "midi", "hardware", "ableton", "stems", "performance"],
        expected_sources=["pete-tong", "production", "ableton"],
        sub_domain=SubDomain.LIVE_PERFORMANCE,
        difficulty=Difficulty.MEDIUM,
        notes="Hardware setup for live performance.",
    ),
]

PRACTICE: list[GoldenQuery] = [
    GoldenQuery(
        id="prac_001",
        question="What is the most effective way to develop a trained ear for identifying specific frequencies in a mix?",
        expected_topics=["ear training", "frequency", "eq", "critical listening", "reference"],
        expected_sources=["pete-tong", "bob_katz", "masterizacion", "mixing"],
        sub_domain=SubDomain.PRACTICE,
        difficulty=Difficulty.EASY,
        notes="Ear training fundamentals.",
    ),
    GoldenQuery(
        id="prac_002",
        question="How should a music producer structure daily practice sessions to improve mixing and sound design skills efficiently?",
        expected_topics=["practice", "routine", "daily", "improvement", "skills", "deliberate"],
        expected_sources=["pete-tong", "production"],
        sub_domain=SubDomain.PRACTICE,
        difficulty=Difficulty.MEDIUM,
        notes="Practice methodology — Pete Tong course likely has this.",
    ),
    GoldenQuery(
        id="prac_003",
        question="What are the essential music theory concepts a house and techno music producer needs to understand?",
        expected_topics=["music theory", "chords", "scales", "harmony", "progression", "key"],
        expected_sources=["pete-tong", "schachter", "production"],
        sub_domain=SubDomain.PRACTICE,
        difficulty=Difficulty.MEDIUM,
        notes="Music theory for electronic producers.",
    ),
    GoldenQuery(
        id="prac_004",
        question="How do you develop a systematic approach to mastering a new synthesis technique you've never used before?",
        expected_topics=[
            "synthesis",
            "learning",
            "systematic",
            "practice",
            "workflow",
            "technique",
        ],
        expected_sources=["pete-tong", "production"],
        sub_domain=SubDomain.PRACTICE,
        difficulty=Difficulty.HARD,
        notes="Meta-learning strategy for synthesis.",
    ),
    GoldenQuery(
        id="prac_005",
        question="How do you use reference tracks effectively to improve your mixes and identify weaknesses in your sound?",
        expected_topics=["reference track", "mixing", "comparison", "spectrum", "loudness", "a/b"],
        expected_sources=["pete-tong", "bob_katz", "masterizacion", "mixing"],
        sub_domain=SubDomain.PRACTICE,
        difficulty=Difficulty.MEDIUM,
        notes="Reference-based mixing practice.",
    ),
]

# ---------------------------------------------------------------------------
# Day 2 — Cross-domain (10)
# ---------------------------------------------------------------------------

CROSS_DOMAIN: list[GoldenQuery] = [
    GoldenQuery(
        id="cross_001",
        question="How do you design a bass sound from synthesis that is already optimized for mixing — with the right frequency balance, dynamics, and harmonic content?",
        expected_topics=["bass", "synthesis", "eq", "mixing", "harmonics", "fundamental"],
        expected_sources=["pete-tong", "mixing", "production", "synthesis"],
        sub_domain=SubDomain.CROSS,
        difficulty=Difficulty.HARD,
        cross_domains=[SubDomain.SOUND_DESIGN, SubDomain.MIXING],
        notes="Sound design decisions that simplify mixing.",
    ),
    GoldenQuery(
        id="cross_002",
        question="How does the arrangement structure of a techno track differ from a progressive house track in terms of pacing, tension, and energy management?",
        expected_topics=[
            "techno",
            "progressive house",
            "arrangement",
            "pacing",
            "tension",
            "structure",
        ],
        expected_sources=["pete-tong", "production", "youtube"],
        sub_domain=SubDomain.CROSS,
        difficulty=Difficulty.HARD,
        cross_domains=[SubDomain.ARRANGEMENT, SubDomain.GENRE],
        notes="Arrangement principles across two genres.",
    ),
    GoldenQuery(
        id="cross_003",
        question="What mixing techniques help preserve the acoustic and natural character of sounds in an organic house production?",
        expected_topics=["organic house", "mixing", "acoustic", "natural", "dynamics", "warmth"],
        expected_sources=["pete-tong", "mixing", "youtube", "bob_katz"],
        sub_domain=SubDomain.CROSS,
        difficulty=Difficulty.HARD,
        cross_domains=[SubDomain.MIXING, SubDomain.GENRE],
        notes="Genre-specific mixing approach.",
    ),
    GoldenQuery(
        id="cross_004",
        question="How do you use sound design elements — filter sweeps, reverse reverbs, risers — to build tension and anticipation in a breakdown?",
        expected_topics=[
            "sound design",
            "breakdown",
            "filter sweep",
            "riser",
            "tension",
            "anticipation",
        ],
        expected_sources=["pete-tong", "production", "synthesis", "creating"],
        sub_domain=SubDomain.CROSS,
        difficulty=Difficulty.MEDIUM,
        cross_domains=[SubDomain.SOUND_DESIGN, SubDomain.ARRANGEMENT],
        notes="Sound design as arrangement tool.",
    ),
    GoldenQuery(
        id="cross_005",
        question="How do you adapt a studio track arrangement to an Ableton Live performance set, and what structural changes are necessary?",
        expected_topics=[
            "ableton",
            "live",
            "arrangement",
            "performance",
            "session view",
            "adaptation",
        ],
        expected_sources=["pete-tong", "production", "ableton"],
        sub_domain=SubDomain.CROSS,
        difficulty=Difficulty.HARD,
        cross_domains=[SubDomain.LIVE_PERFORMANCE, SubDomain.ARRANGEMENT],
        notes="Studio-to-live conversion.",
    ),
    GoldenQuery(
        id="cross_006",
        question="What active listening exercises and critical analysis techniques help develop better EQ and mixing judgment?",
        expected_topics=["listening", "critical", "analysis", "mixing", "practice", "eq"],
        expected_sources=["pete-tong", "bob_katz", "masterizacion", "mixing"],
        sub_domain=SubDomain.CROSS,
        difficulty=Difficulty.MEDIUM,
        cross_domains=[SubDomain.PRACTICE, SubDomain.MIXING],
        notes="Practice methodology applied to mixing.",
    ),
    GoldenQuery(
        id="cross_007",
        question="What synthesis techniques and timbral choices most define the sound palette of organic house music?",
        expected_topics=[
            "organic house",
            "synthesis",
            "sound design",
            "acoustic",
            "texture",
            "palette",
        ],
        expected_sources=["pete-tong", "youtube", "synthesis", "creating"],
        sub_domain=SubDomain.CROSS,
        difficulty=Difficulty.HARD,
        cross_domains=[SubDomain.GENRE, SubDomain.SOUND_DESIGN],
        notes="Genre sound identity from synthesis perspective.",
    ),
    GoldenQuery(
        id="cross_008",
        question="How do arrangement decisions — element density, layering complexity, and transition types — directly affect the mixing workflow?",
        expected_topics=["arrangement", "mixing", "density", "layering", "transitions", "workflow"],
        expected_sources=["pete-tong", "production", "mixing"],
        sub_domain=SubDomain.CROSS,
        difficulty=Difficulty.HARD,
        cross_domains=[SubDomain.ARRANGEMENT, SubDomain.MIXING],
        notes="Arrangement impacts mixing complexity.",
    ),
    GoldenQuery(
        id="cross_009",
        question="What drum synthesis and processing techniques define the kick and percussion aesthetic in underground techno production?",
        expected_topics=[
            "techno",
            "kick",
            "drum synthesis",
            "processing",
            "percussion",
            "transient",
        ],
        expected_sources=["pete-tong", "youtube", "synthesis", "creating"],
        sub_domain=SubDomain.CROSS,
        difficulty=Difficulty.HARD,
        cross_domains=[SubDomain.SOUND_DESIGN, SubDomain.GENRE],
        notes="Genre-defining drum design.",
    ),
    GoldenQuery(
        id="cross_010",
        question="How do you select and sequence tracks for a coherent organic house DJ set that creates a musical journey for the audience?",
        expected_topics=["dj set", "selection", "sequencing", "organic house", "journey", "energy"],
        expected_sources=["pete-tong", "youtube", "live"],
        sub_domain=SubDomain.CROSS,
        difficulty=Difficulty.HARD,
        cross_domains=[SubDomain.LIVE_PERFORMANCE, SubDomain.GENRE],
        notes="Curation and programming for live context.",
    ),
]

# ---------------------------------------------------------------------------
# Day 2 — Adversarial (10) — should return 422 or explicit refusal
# ---------------------------------------------------------------------------

ADVERSARIAL: list[GoldenQuery] = [
    GoldenQuery(
        id="adv_001",
        question="What is the secret chord progression formula used by the most successful house music producers?",
        expected_topics=[],
        expected_sources=[],
        sub_domain=SubDomain.ADVERSARIAL,
        difficulty=Difficulty.EASY,
        adversarial=True,
        notes="Trick question — no 'secret formula' exists in corpus. Expect refusal or 422.",
    ),
    GoldenQuery(
        id="adv_002",
        question="What exact plugin settings and DAW configuration does Pete Tong personally use in his own Ableton Live setup?",
        expected_topics=[],
        expected_sources=[],
        sub_domain=SubDomain.ADVERSARIAL,
        difficulty=Difficulty.EASY,
        adversarial=True,
        notes="Personal settings not documented in corpus. Expect 422.",
    ),
    GoldenQuery(
        id="adv_003",
        question="What were the top 10 best tracks played at Ibiza in the summer of 2024?",
        expected_topics=[],
        expected_sources=[],
        sub_domain=SubDomain.ADVERSARIAL,
        difficulty=Difficulty.EASY,
        adversarial=True,
        notes="Real-world event data — not in corpus. Expect 422.",
    ),
    GoldenQuery(
        id="adv_004",
        question="How do I get my track signed to a major record label and what demo submission process should I follow?",
        expected_topics=[],
        expected_sources=[],
        sub_domain=SubDomain.ADVERSARIAL,
        difficulty=Difficulty.EASY,
        adversarial=True,
        notes="Business/career advice — not in production knowledge base.",
    ),
    GoldenQuery(
        id="adv_005",
        question="What specific vocal processing chain makes a voice sound like Billie Eilish?",
        expected_topics=[],
        expected_sources=[],
        sub_domain=SubDomain.ADVERSARIAL,
        difficulty=Difficulty.EASY,
        adversarial=True,
        notes="Artist-specific out-of-corpus question. Expect refusal.",
    ),
    GoldenQuery(
        id="adv_006",
        question="Which compressor plugin has the objectively best algorithm for house music production?",
        expected_topics=[],
        expected_sources=[],
        sub_domain=SubDomain.ADVERSARIAL,
        difficulty=Difficulty.MEDIUM,
        adversarial=True,
        notes="Subjective commercial recommendation — no ground truth in corpus.",
    ),
    GoldenQuery(
        id="adv_007",
        question="How do I build a career and become famous as a music producer in today's industry?",
        expected_topics=[],
        expected_sources=[],
        sub_domain=SubDomain.ADVERSARIAL,
        difficulty=Difficulty.EASY,
        adversarial=True,
        notes="Career advice — not production knowledge.",
    ),
    GoldenQuery(
        id="adv_008",
        question="What is the exact formula for creating a viral TikTok sound in 2025?",
        expected_topics=[],
        expected_sources=[],
        sub_domain=SubDomain.ADVERSARIAL,
        difficulty=Difficulty.EASY,
        adversarial=True,
        notes="Social media strategy — completely outside corpus.",
    ),
    GoldenQuery(
        id="adv_009",
        question="How do I fix a persistent click and pop noise coming from my audio interface drivers on Windows?",
        expected_topics=[],
        expected_sources=[],
        sub_domain=SubDomain.ADVERSARIAL,
        difficulty=Difficulty.EASY,
        adversarial=True,
        notes="Hardware/driver technical support — not production knowledge.",
    ),
    GoldenQuery(
        id="adv_010",
        question="What is the meaning of life and how does Buddhist philosophy relate to the creative process in music?",
        expected_topics=[],
        expected_sources=[],
        sub_domain=SubDomain.ADVERSARIAL,
        difficulty=Difficulty.EASY,
        adversarial=True,
        notes="Completely out of scope. Expect 422 or explicit refusal.",
    ),
]

# ---------------------------------------------------------------------------
# Full dataset — 50 queries
# ---------------------------------------------------------------------------

GOLDEN_DATASET: list[GoldenQuery] = (
    SOUND_DESIGN  # 5
    + ARRANGEMENT  # 5
    + MIXING  # 5
    + GENRE  # 5
    + LIVE_PERFORMANCE  # 5
    + PRACTICE  # 5
    + CROSS_DOMAIN  # 10
    + ADVERSARIAL  # 10
)

assert len(GOLDEN_DATASET) == 50, f"Expected 50 queries, got {len(GOLDEN_DATASET)}"

# Convenience lookups
DATASET_BY_ID: dict[str, GoldenQuery] = {q.id: q for q in GOLDEN_DATASET}

DATASET_BY_SUBDOMAIN: dict[SubDomain, list[GoldenQuery]] = {
    domain: [q for q in GOLDEN_DATASET if q.sub_domain == domain] for domain in SubDomain
}

#: Sub-domains that have single-domain queries (used for per-domain breakdown)
SCORED_SUBDOMAINS: list[SubDomain] = [
    SubDomain.SOUND_DESIGN,
    SubDomain.ARRANGEMENT,
    SubDomain.MIXING,
    SubDomain.GENRE,
    SubDomain.LIVE_PERFORMANCE,
    SubDomain.PRACTICE,
]

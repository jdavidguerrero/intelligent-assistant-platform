"""
suggest_sample_selection tool — recommend sample types for a genre and sound role.

Pure computation: no LLM, no DB, no I/O.

Given a genre and target sound role (kick, snare, pad, bass, etc.), returns:
  - Specific sample characteristics to look for (texture, frequency profile, attack)
  - Classic hardware sources (TR-808, TR-909, Rhodes, etc.)
  - EQ/filtering treatment before use
  - Search keywords for sample libraries (Splice, Loopmasters, etc.)
  - Layering strategy (how many samples and how to combine them)
  - Reference tracks that use this sound well

This tool helps producers know WHAT to look for when browsing samples,
not just what samples to use — the characteristics matter more than specific names.
"""

from typing import Any

from tools.base import MusicalTool, ToolParameter, ToolResult

# ---------------------------------------------------------------------------
# Sample selection database
# ---------------------------------------------------------------------------

_SAMPLES: dict[str, dict[str, Any]] = {
    "kick": {
        "house": {
            "description": "Round, deep kick with clear transient and sustaining sub body.",
            "hardware_sources": ["TR-909", "TR-808 (tuned up)", "Linndrum", "LM-1"],
            "characteristics": {
                "attack": "Fast but not sharp — 5–10ms click, not a snap",
                "body": "60–80Hz fundamental, minimal 200–400Hz",
                "length_ms": "300–500ms total decay",
                "tuning": "Tune to the key of the track — usually root or fifth",
            },
            "treatment": "HPF @ 30Hz, boost 60Hz, cut 300Hz, compress 4:1 5ms attack",
            "layering": "Layer 1: sub body (sine/808). Layer 2: click/transient. Optional Layer 3: room tail.",
            "search_keywords": ["house kick", "four on the floor", "TR-909 kick", "deep kick"],
            "reference_tracks": ["Frankie Knuckles - Your Love", "Larry Heard - Can You Feel It"],
            "avoid": "Kicks with strong 200Hz boxiness or overly bright high-end snap.",
        },
        "techno": {
            "description": "Hard, punchy kick — transient-forward, minimal sustain.",
            "hardware_sources": ["TR-909", "KICK (plugin)", "hardware synthesized"],
            "characteristics": {
                "attack": "Sharp transient — 1–2ms click",
                "body": "50–70Hz, tighter than house",
                "length_ms": "150–250ms — shorter than house",
                "tuning": "Often detuned or distorted — tuning less critical",
            },
            "treatment": "HPF @ 40Hz, distort lightly, compress 8:1 1ms attack, EQ 4–6kHz presence",
            "layering": "Layer 1: sub (short). Layer 2: hard transient. Distortion as treatment, not layer.",
            "search_keywords": ["techno kick", "industrial kick", "909 kick hard", "Berghain kick"],
            "reference_tracks": ["Function - Inertia", "Surgeon - Force + Form"],
            "avoid": "Warm or round kicks — techno wants edge, not warmth.",
        },
        "deep house": {
            "description": "Warm, round kick — the opposite of techno. Body-forward, soft attack.",
            "hardware_sources": [
                "TR-808 (long decay)",
                "acoustic kick sample (compressed)",
                "Simmons SDS",
            ],
            "characteristics": {
                "attack": "Soft — 10–20ms",
                "body": "50–80Hz with warmth at 100–120Hz",
                "length_ms": "400–700ms — longer decay for warmth",
                "tuning": "Tune carefully — deep house kick has clear pitch",
            },
            "treatment": "Minimal — preserve natural warmth. HPF @ 25Hz, subtle tube saturation.",
            "layering": "Often a single well-chosen sample, maybe 2 layers maximum.",
            "search_keywords": [
                "deep house kick",
                "warm kick",
                "Larry Heard kick",
                "808 bass drum",
            ],
            "reference_tracks": ["Moodymann - I Can't Kick This Feeling", "Bicep - Glue"],
            "avoid": "Any kick with synthetic or harsh high-mid content.",
        },
        "organic house": {
            "description": "Hybrid acoustic/electronic — slightly imperfect, organic texture.",
            "hardware_sources": [
                "Live drum sample (processed)",
                "TR-909 with room reverb",
                "hybrid layering",
            ],
            "characteristics": {
                "attack": "Natural — slight pre-ringing acceptable",
                "body": "55–75Hz — warm but not boomy",
                "length_ms": "250–400ms",
                "tuning": "Match to track key",
            },
            "treatment": "Light room reverb (0.3s), subtle saturation, sidechain gently.",
            "layering": "Layer: acoustic body + electronic sub + room verb on both.",
            "search_keywords": ["organic kick", "tribal kick", "live kick processed", "afro kick"],
            "reference_tracks": ["Solomun - Fade to Black", "Agents of Time - The Maze"],
            "avoid": "Overly electronic or quantized-feeling kicks.",
        },
    },
    "snare": {
        "house": {
            "description": "Crisp backbeat snare with room reverb — not dry, not wet.",
            "hardware_sources": ["TR-909 snare", "Linndrum snare", "LM-1 snare"],
            "characteristics": {
                "attack": "Sharp crack at 1.2kHz",
                "body": "Minimal — not beefy",
                "length_ms": "80–150ms body + reverb tail",
                "tuning": "Not pitch-critical",
            },
            "treatment": "Room reverb 0.8s, transient shaper +4dB attack, compress 4:1",
            "layering": "Main snare + clap layer + room reverb send.",
            "search_keywords": ["house snare", "909 snare", "clap house", "backbeat snare"],
            "reference_tracks": [],
            "avoid": "Big rock snares or anything with too much low-mid body.",
        },
        "techno": {
            "description": "Industrial, tight snare — more of a crack than a smack.",
            "hardware_sources": ["TR-909 snare", "Simmons electronic", "noise burst synthesized"],
            "characteristics": {
                "attack": "Very sharp",
                "body": "Minimal body, lots of crack",
                "length_ms": "50–100ms",
                "tuning": "Not important — noise-based",
            },
            "treatment": "Compress hard, distort, HPF @ 150Hz",
            "layering": "Snare + noise burst + room reverb (short 0.3s).",
            "search_keywords": ["techno snare", "industrial snare", "tight snare", "909 crack"],
            "reference_tracks": [],
            "avoid": "Warm or roomy snares.",
        },
    },
    "bass": {
        "house": {
            "description": "Warm, mid-forward bass with presence. Not overly subby.",
            "hardware_sources": [
                "Moog synthesizer",
                "Juno-106 bass patch",
                "DX7 bass",
                "Rhodes bass",
            ],
            "characteristics": {
                "register": "C1–C3 (root notes), harmonics up to 300Hz",
                "attack": "Medium — 20–50ms",
                "texture": "Warm, slightly fuzzy — not clean digital",
                "movement": "Root-fifth or walking — not static",
            },
            "treatment": "Sidechain from kick, HPF @ 40Hz, subtle chorus for width",
            "layering": "Sub sine (mono) + mid bass (slight saturation) + optional DI layer.",
            "search_keywords": ["house bass", "analog bass", "Moog bass", "warm bass synth"],
            "reference_tracks": [
                "Larry Heard - Can You Feel It",
                "Marshall Jefferson - Move Your Body",
            ],
            "avoid": "Thin or overly bright basses. The low-mid warmth is essential.",
        },
        "acid": {
            "description": "The Roland TB-303 sound — squelchy, resonant, detuned.",
            "hardware_sources": [
                "Roland TB-303",
                "Behringer TD-3",
                "Novation Bass Station",
                "software 303 emulations",
            ],
            "characteristics": {
                "register": "C2–C3 — higher than typical bass",
                "attack": "Fast gate, rhythmic",
                "texture": "Resonant filter sweep — the defining characteristic",
                "movement": "Slides between notes (portamento)",
            },
            "treatment": "Resonant LPF with envelope mod, distortion, compress after",
            "layering": "Single 303 is the sound — don't layer, just process.",
            "search_keywords": ["303", "acid bass", "TB-303", "squelch bass", "acid line"],
            "reference_tracks": ["Phuture - Acid Tracks", "Plastikman - Spastik"],
            "avoid": "Anything clean or warm. Acid is aggressive by definition.",
        },
        "deep house": {
            "description": "Jazz-influenced bass — walking, warm, slightly acoustic in feel.",
            "hardware_sources": [
                "Electric bass DI",
                "Rhodes bass (left hand)",
                "Moog with slow filter",
            ],
            "characteristics": {
                "register": "E1–A2",
                "attack": "Natural — acoustic bass feel",
                "texture": "Warm, slightly compressed, slightly chorus",
                "movement": "Walking pattern — stepwise movement, not root-only",
            },
            "treatment": "Chorus (subtle), light compression, tape saturation",
            "layering": "Often just one warm bass sound — simplicity is the goal.",
            "search_keywords": ["deep house bass", "walking bass", "jazz bass house", "warm bass"],
            "reference_tracks": ["Moodymann - Shades of Jae", "Kerri Chandler - Bar A Thym"],
            "avoid": "Synth basses that sound digital or harsh.",
        },
    },
    "pad": {
        "organic house": {
            "description": "Lush, wide, evolving — natural elements processed into pads.",
            "hardware_sources": [
                "Juno-106",
                "Prophet-5",
                "Oberheim OB-X",
                "sampled strings (processed)",
            ],
            "characteristics": {
                "register": "C3–C5 — above bass, below lead",
                "attack": "Slow — 200ms+ attack for wash effect",
                "texture": "Evolving, slightly detuned, wide stereo",
                "movement": "Subtle filter or volume movement over time",
            },
            "treatment": "Hall reverb 3–4s, chorus, wide stereo (100%), HPF @ 200Hz",
            "layering": "2 pad layers: warm analog + airy string/choir. Add subtle noise texture.",
            "search_keywords": ["organic pad", "lush pad", "warm synth pad", "evolving pad"],
            "reference_tracks": ["Burial - Archangel", "Solomun - Garden of I and I"],
            "avoid": "Static, un-moving pads. Organic house pads breathe.",
        },
        "melodic techno": {
            "description": "Dark, cinematic — more tension than warmth.",
            "hardware_sources": [
                "Roland Jupiter-8",
                "Arp Odyssey",
                "Moog Sub 37 (pads)",
                "sampled choirs",
            ],
            "characteristics": {
                "register": "C2–C4 — darker register",
                "attack": "Medium — 100–300ms",
                "texture": "Dense, slightly dissonant, cinematic quality",
                "movement": "Slow filter sweep, reverse reverb pre-pad",
            },
            "treatment": "Plate reverb 2.5s, bitcrush subtle, HPF @ 300Hz",
            "layering": "Dark analog + pitched noise/drone layer.",
            "search_keywords": [
                "dark pad",
                "cinematic pad",
                "melodic techno pad",
                "Tale of Us pad",
            ],
            "reference_tracks": ["Tale of Us - Lost", "Stephan Bodzin - Singularity"],
            "avoid": "Bright or cheerful pads — must maintain tension.",
        },
    },
    "vocal_chop": {
        "house": {
            "description": "Short vocal phrases rhythmically chopped and pitched.",
            "hardware_sources": ["Sampler (SP-1200, MPC)", "Gospel/soul acapellas"],
            "characteristics": {
                "source": "Gospel, soul, R&B acapellas — emotional content is key",
                "length": "1–4 syllables per chop",
                "pitch": "Tune to track key — most phrases fit minor or major",
                "rhythm": "Off-beat placement — avoid landing on the kick",
            },
            "treatment": "HPF @ 200Hz, reverb (short room), transient enhance",
            "layering": "Dry chop + reverb send (30%) + optional pitch octave below (-12).",
            "search_keywords": ["gospel vocal", "soul acapella", "house vocal chop", "disco vocal"],
            "reference_tracks": [
                "Marshall Jefferson - Move Your Body",
                "Ten City - That's the Way Love Is",
            ],
            "avoid": "Modern processed vocals or anything with heavy AutoTune.",
        },
    },
    "hi_hat": {
        "house": {
            "description": "Shuffling 8th note hats with slight swing — the groove engine.",
            "hardware_sources": ["TR-909 hi-hat", "TR-808 hi-hat", "live cymbal (tight)"],
            "characteristics": {
                "attack": "Immediate",
                "decay": "Closed: 20–40ms. Open: 80–200ms",
                "texture": "Metallic but not harsh. Slight shimmer at 8–10kHz",
                "pattern": "8th notes with 2–4% shuffle/swing",
            },
            "treatment": "HPF @ 3kHz, cut 2kHz slightly (boxiness), subtle room reverb",
            "layering": "Closed + open at strategic positions. Shaker for extra groove.",
            "search_keywords": ["house hi hat", "909 hat", "shuffling hat", "house cymbal"],
            "reference_tracks": [],
            "avoid": "Overly processed or washed-out hats that blur the groove.",
        },
    },
}

VALID_SOUND_ROLES: frozenset[str] = frozenset(_SAMPLES.keys())
VALID_GENRES: frozenset[str] = frozenset(
    genre for roles in _SAMPLES.values() for genre in roles.keys()
)


class SuggestSampleSelection(MusicalTool):
    """
    Suggest sample characteristics, hardware sources, and search keywords
    for a given sound role and genre.

    Returns what to LOOK FOR in a sample, not just what to use —
    characteristics (attack, body, texture), classic hardware sources,
    treatment chain, layering strategy, and search keywords.

    Use when selecting samples from Splice, Loopmasters, or your
    own sample library.
    """

    @property
    def name(self) -> str:
        return "suggest_sample_selection"

    @property
    def description(self) -> str:
        return (
            "Suggest sample characteristics, hardware sources, treatment, and search keywords "
            "for a sound role in a genre. "
            "Returns what to look for (attack, texture, register), classic hardware sources "
            "(TR-909, Moog, Rhodes), layering strategy, and Splice search keywords. "
            "Use when the user asks which samples to use, what kick to pick, "
            "how to find the right bass sound, or wants guidance on sample selection. "
            f"Sound roles: {', '.join(sorted(VALID_SOUND_ROLES))}."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="sound_role",
                type=str,
                description=(
                    f"Sound role. Options: {', '.join(sorted(VALID_SOUND_ROLES))}. "
                    "Default: 'kick'."
                ),
                required=False,
                default="kick",
            ),
            ToolParameter(
                name="genre",
                type=str,
                description=("Music genre context. " "Default: 'house'."),
                required=False,
                default="house",
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        sound_role: str = (kwargs.get("sound_role") or "kick").strip().lower()
        genre: str = (kwargs.get("genre") or "house").strip().lower()

        # Normalize: hi-hat aliases
        if sound_role in ("hat", "hi-hat", "hihat"):
            sound_role = "hi_hat"

        if sound_role not in VALID_SOUND_ROLES:
            return ToolResult(
                success=False,
                error=(
                    f"sound_role must be one of: {', '.join(sorted(VALID_SOUND_ROLES))}. "
                    f"Got: {sound_role!r}"
                ),
            )

        role_data = _SAMPLES[sound_role]

        if genre in role_data:
            data = role_data[genre]
            matched_genre = genre
        else:
            # Fallback to first available genre for this role
            matched_genre = next(iter(role_data))
            data = role_data[matched_genre]

        return ToolResult(
            success=True,
            data={
                "sound_role": sound_role,
                "genre": matched_genre,
                "requested_genre": genre,
                **data,
            },
            metadata={
                "exact_match": matched_genre == genre,
                "available_genres_for_role": list(role_data.keys()),
            },
        )

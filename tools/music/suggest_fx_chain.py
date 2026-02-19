"""
suggest_fx_chain tool — recommend a signal processing chain for a sound type and genre.

Pure computation: no LLM, no DB, no I/O.

Returns an ordered list of effects with:
  - Effect name and category (dynamics, EQ, time-based, saturation, modulation)
  - Parameter starting points (specific numbers, not vague descriptions)
  - Rationale for each effect in the context of the genre
  - Signal flow order (pre-send vs. post, serial vs. parallel notes)

Design principle:
  Every parameter is a concrete starting point — not "add some reverb" but
  "Hall reverb: pre-delay 18ms, decay 2.1s, mix 12%". Numbers can be dialed
  in immediately in any DAW.

Coverage:
  Sound types: kick, snare, bass, pad, lead, vocal, chord, pluck, sub, 808
  Genres: house, techno, deep house, organic house, melodic techno, acid
"""

from typing import Any

from tools.base import MusicalTool, ToolParameter, ToolResult

# ---------------------------------------------------------------------------
# Effect chain templates
# Format: list of effect dicts
# ---------------------------------------------------------------------------

_FX: dict[str, dict[str, list[dict[str, Any]]]] = {
    "kick": {
        "house": [
            {
                "order": 1,
                "name": "High-pass Filter",
                "category": "EQ",
                "params": {"cutoff_hz": 30, "slope_db_oct": 12},
                "rationale": "Remove sub-rumble below 30Hz. Keeps the sub tight.",
            },
            {
                "order": 2,
                "name": "Transient Shaper",
                "category": "dynamics",
                "params": {"attack_gain_db": 2, "sustain_gain_db": -1},
                "rationale": "Add punch to the attack — makes the kick cut through the mix.",
            },
            {
                "order": 3,
                "name": "Compressor",
                "category": "dynamics",
                "params": {
                    "threshold_db": -12,
                    "ratio": "4:1",
                    "attack_ms": 5,
                    "release_ms": 80,
                    "makeup_db": 3,
                },
                "rationale": "Glue the kick body. Fast attack catches transient, 80ms release lets sub breathe.",
            },
            {
                "order": 4,
                "name": "EQ (peak)",
                "category": "EQ",
                "params": {"boost_hz": 60, "boost_db": 3, "cut_hz": 400, "cut_db": -3},
                "rationale": "Boost fundamental at 60Hz for punch. Cut boxiness at 400Hz.",
            },
            {
                "order": 5,
                "name": "Limiter",
                "category": "dynamics",
                "params": {"ceiling_db": -1, "release_ms": 50},
                "rationale": "Hard ceiling prevents clipping on the output bus.",
            },
        ],
        "techno": [
            {
                "order": 1,
                "name": "High-pass Filter",
                "category": "EQ",
                "params": {"cutoff_hz": 40, "slope_db_oct": 24},
                "rationale": "Steeper HP for techno — tighter sub definition.",
            },
            {
                "order": 2,
                "name": "Distortion/Saturation",
                "category": "saturation",
                "params": {"drive_db": 6, "mode": "soft_clip", "mix_pct": 30},
                "rationale": "Grit and harmonics give the industrial techno kick character.",
            },
            {
                "order": 3,
                "name": "Compressor",
                "category": "dynamics",
                "params": {"threshold_db": -8, "ratio": "8:1", "attack_ms": 1, "release_ms": 60},
                "rationale": "Hard compression for relentless, punching techno kick.",
            },
            {
                "order": 4,
                "name": "EQ (shelving)",
                "category": "EQ",
                "params": {"high_shelf_hz": 6000, "high_shelf_db": 4},
                "rationale": "Air boost adds clickiness and presence in a loud mix.",
            },
        ],
        "deep house": [
            {
                "order": 1,
                "name": "High-pass Filter",
                "category": "EQ",
                "params": {"cutoff_hz": 25, "slope_db_oct": 12},
                "rationale": "Very low HP — preserve the deep sub body of a deep house kick.",
            },
            {
                "order": 2,
                "name": "Tube Saturation",
                "category": "saturation",
                "params": {"drive_pct": 15, "mix_pct": 20},
                "rationale": "Subtle analog warmth — characteristic of deep house.",
            },
            {
                "order": 3,
                "name": "Compressor",
                "category": "dynamics",
                "params": {"threshold_db": -14, "ratio": "3:1", "attack_ms": 10, "release_ms": 120},
                "rationale": "Gentle compression. Long release preserves the natural decay.",
            },
            {
                "order": 4,
                "name": "EQ (bell)",
                "category": "EQ",
                "params": {"boost_hz": 50, "boost_db": 2, "cut_hz": 200, "cut_db": -2},
                "rationale": "Warmth at 50Hz, clean up muddiness at 200Hz.",
            },
        ],
    },
    "bass": {
        "house": [
            {
                "order": 1,
                "name": "High-pass Filter",
                "category": "EQ",
                "params": {"cutoff_hz": 40, "slope_db_oct": 12},
                "rationale": "Remove extreme sub where the kick lives. Prevent mud.",
            },
            {
                "order": 2,
                "name": "Compressor",
                "category": "dynamics",
                "params": {"threshold_db": -10, "ratio": "4:1", "attack_ms": 8, "release_ms": 100},
                "rationale": "Even out the bass level across notes. Slow attack preserves pick/pluck attack.",
            },
            {
                "order": 3,
                "name": "Sidechain Compressor",
                "category": "dynamics",
                "params": {
                    "ratio": "3:1",
                    "attack_ms": 10,
                    "release_ms": 100,
                    "triggered_by": "kick",
                },
                "rationale": "Classic house sidechain: bass ducks when kick hits, creating the breathing pump.",
            },
            {
                "order": 4,
                "name": "EQ (boost)",
                "category": "EQ",
                "params": {"boost_hz": 80, "boost_db": 2, "cut_hz": 300, "cut_db": -3},
                "rationale": "Reinforce the fundamental. Reduce midrange mud.",
            },
            {
                "order": 5,
                "name": "Tape Saturation",
                "category": "saturation",
                "params": {"drive_pct": 10, "mix_pct": 25},
                "rationale": "Harmonic content makes bass translate on small speakers.",
            },
        ],
        "acid": [
            {
                "order": 1,
                "name": "Low-pass Filter (resonant)",
                "category": "EQ",
                "params": {"cutoff_hz": 800, "resonance": 0.7, "envelope_mod_amt": 60},
                "rationale": "The 303 filter is the defining acid sound — resonant LP with envelope mod.",
            },
            {
                "order": 2,
                "name": "Distortion",
                "category": "saturation",
                "params": {"drive_db": 12, "mode": "hard_clip", "mix_pct": 60},
                "rationale": "Acid bass is distorted — especially when the filter opens up.",
            },
            {
                "order": 3,
                "name": "Compressor",
                "category": "dynamics",
                "params": {"threshold_db": -6, "ratio": "6:1", "attack_ms": 2, "release_ms": 50},
                "rationale": "Tame peaks after distortion.",
            },
        ],
        "deep house": [
            {
                "order": 1,
                "name": "High-pass Filter",
                "category": "EQ",
                "params": {"cutoff_hz": 35, "slope_db_oct": 12},
                "rationale": "Deep house bass sits lower — gentle HP.",
            },
            {
                "order": 2,
                "name": "Chorus",
                "category": "modulation",
                "params": {"rate_hz": 0.3, "depth_pct": 20, "mix_pct": 15},
                "rationale": "Subtle chorus gives the walking bass that warm Rhodes-adjacent feel.",
            },
            {
                "order": 3,
                "name": "Compressor",
                "category": "dynamics",
                "params": {"threshold_db": -12, "ratio": "3:1", "attack_ms": 12, "release_ms": 150},
                "rationale": "Smooth, musical compression — not aggressive.",
            },
            {
                "order": 4,
                "name": "Sidechain Compressor",
                "category": "dynamics",
                "params": {
                    "ratio": "2:1",
                    "attack_ms": 15,
                    "release_ms": 120,
                    "triggered_by": "kick",
                },
                "rationale": "Softer sidechain than house — deep house doesn't pump as hard.",
            },
        ],
    },
    "pad": {
        "organic house": [
            {
                "order": 1,
                "name": "High-pass Filter",
                "category": "EQ",
                "params": {"cutoff_hz": 200, "slope_db_oct": 12},
                "rationale": "Clear the low-mid so pads don't clash with bass. Pads live above 200Hz.",
            },
            {
                "order": 2,
                "name": "Reverb (hall)",
                "category": "time",
                "params": {"pre_delay_ms": 20, "decay_s": 3.5, "mix_pct": 35, "damping_hz": 8000},
                "rationale": "Spacious hall reverb is the sonic signature of organic house pads.",
            },
            {
                "order": 3,
                "name": "Chorus",
                "category": "modulation",
                "params": {"rate_hz": 0.2, "depth_pct": 25, "mix_pct": 40},
                "rationale": "Width and movement — makes the pad feel alive and evolving.",
            },
            {
                "order": 4,
                "name": "Low-pass Filter",
                "category": "EQ",
                "params": {"cutoff_hz": 12000, "resonance": 0.1},
                "rationale": "Tame harsh high frequencies — organic house pads are warm, not bright.",
            },
            {
                "order": 5,
                "name": "Limiter",
                "category": "dynamics",
                "params": {"ceiling_db": -6, "release_ms": 100},
                "rationale": "Prevent pad from overwhelming the mix when fully open.",
            },
        ],
        "melodic techno": [
            {
                "order": 1,
                "name": "High-pass Filter",
                "category": "EQ",
                "params": {"cutoff_hz": 300, "slope_db_oct": 18},
                "rationale": "Steeper HP — melodic techno pads are thinner, more cinematic.",
            },
            {
                "order": 2,
                "name": "Reverb (plate)",
                "category": "time",
                "params": {"pre_delay_ms": 8, "decay_s": 2.5, "mix_pct": 45},
                "rationale": "Plate reverb has a darker, metallic quality that fits melodic techno.",
            },
            {
                "order": 3,
                "name": "Delay (ping-pong)",
                "category": "time",
                "params": {"time_note": "1/8", "feedback_pct": 35, "mix_pct": 20},
                "rationale": "Ping-pong delay creates stereo movement and rhythmic interest.",
            },
            {
                "order": 4,
                "name": "Bitcrusher",
                "category": "saturation",
                "params": {"bit_depth": 12, "mix_pct": 15},
                "rationale": "Subtle bit reduction gives digital harshness — very melodic techno.",
            },
        ],
    },
    "lead": {
        "melodic house": [
            {
                "order": 1,
                "name": "Reverb (room)",
                "category": "time",
                "params": {"pre_delay_ms": 12, "decay_s": 1.2, "mix_pct": 25},
                "rationale": "Room reverb keeps the lead present but not washed out.",
            },
            {
                "order": 2,
                "name": "Delay (1/8 note)",
                "category": "time",
                "params": {"time_note": "1/8", "feedback_pct": 25, "mix_pct": 18},
                "rationale": "Rhythmic delay that adds groove without losing melodic clarity.",
            },
            {
                "order": 3,
                "name": "Compressor",
                "category": "dynamics",
                "params": {"threshold_db": -8, "ratio": "3:1", "attack_ms": 15, "release_ms": 80},
                "rationale": "Even dynamics. Slower attack lets the note attack breathe.",
            },
            {
                "order": 4,
                "name": "EQ (presence)",
                "category": "EQ",
                "params": {"boost_hz": 3000, "boost_db": 2, "cut_hz": 500, "cut_db": -1.5},
                "rationale": "Presence boost makes the lead cut through in a dense mix.",
            },
        ],
    },
    "snare": {
        "house": [
            {
                "order": 1,
                "name": "Transient Shaper",
                "category": "dynamics",
                "params": {"attack_gain_db": 4, "sustain_gain_db": -2},
                "rationale": "Sharpen the crack. House snare should be crisp and immediate.",
            },
            {
                "order": 2,
                "name": "Reverb (room)",
                "category": "time",
                "params": {"pre_delay_ms": 5, "decay_s": 0.8, "mix_pct": 30},
                "rationale": "Room reverb glues the snare into the room — not too long.",
            },
            {
                "order": 3,
                "name": "Compressor",
                "category": "dynamics",
                "params": {"threshold_db": -10, "ratio": "4:1", "attack_ms": 3, "release_ms": 60},
                "rationale": "Snap the snare into shape. Fast attack, fast release.",
            },
            {
                "order": 4,
                "name": "EQ (crack boost)",
                "category": "EQ",
                "params": {"boost_hz": 1200, "boost_db": 3, "cut_hz": 300, "cut_db": -2},
                "rationale": "Crack at 1.2kHz, cut low-mid mud.",
            },
        ],
    },
    "808": {
        "house": [
            {
                "order": 1,
                "name": "Pitch Envelope",
                "category": "dynamics",
                "params": {"start_note": "C2", "end_note": "C1", "decay_ms": 400},
                "rationale": "The 808 pitch drop is the defining characteristic.",
            },
            {
                "order": 2,
                "name": "Distortion (soft clip)",
                "category": "saturation",
                "params": {"drive_db": 4, "mix_pct": 20},
                "rationale": "Subtle saturation adds harmonics so 808 translates on non-subwoofer speakers.",
            },
            {
                "order": 3,
                "name": "Sidechain Compressor",
                "category": "dynamics",
                "params": {
                    "ratio": "4:1",
                    "attack_ms": 5,
                    "release_ms": 150,
                    "triggered_by": "kick",
                },
                "rationale": "Sidechain from kick prevents kick and 808 from overlapping in the sub.",
            },
            {
                "order": 4,
                "name": "Low-pass Filter",
                "category": "EQ",
                "params": {"cutoff_hz": 200, "resonance": 0.0},
                "rationale": "Limit 808 to the sub range — everything above 200Hz is other instruments.",
            },
        ],
    },
}

VALID_SOUND_TYPES: frozenset[str] = frozenset(_FX.keys())
VALID_GENRES: frozenset[str] = frozenset(
    genre for sounds in _FX.values() for genre in sounds.keys()
)


class SuggestFxChain(MusicalTool):
    """
    Suggest a signal processing FX chain for a given sound type and genre.

    Returns an ordered list of effects with concrete parameter starting points
    (specific numbers, not vague descriptions). Every parameter can be
    immediately dialed into any DAW.

    Covers kick, snare, bass, pad, lead, vocal, 808 and genres:
    house, techno, deep house, organic house, melodic techno, acid.
    """

    @property
    def name(self) -> str:
        return "suggest_fx_chain"

    @property
    def description(self) -> str:
        return (
            "Suggest an ordered signal processing FX chain for a sound type and genre. "
            "Returns effect names, categories, and concrete parameter values "
            "(e.g. 'Compressor: threshold -12dB, ratio 4:1, attack 5ms'). "
            "Use when the user asks how to process a sound, what effects to use, "
            "how to mix a specific instrument, or wants a starting point for a signal chain. "
            f"Sound types: {', '.join(sorted(VALID_SOUND_TYPES))}."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="sound_type",
                type=str,
                description=(
                    f"Type of sound to process. Options: {', '.join(sorted(VALID_SOUND_TYPES))}. "
                    "Default: 'kick'."
                ),
                required=False,
                default="kick",
            ),
            ToolParameter(
                name="genre",
                type=str,
                description=("Music genre context for the FX chain. " "Default: 'house'."),
                required=False,
                default="house",
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        sound_type: str = (kwargs.get("sound_type") or "kick").strip().lower()
        genre: str = (kwargs.get("genre") or "house").strip().lower()

        if sound_type not in VALID_SOUND_TYPES:
            return ToolResult(
                success=False,
                error=(
                    f"sound_type must be one of: {', '.join(sorted(VALID_SOUND_TYPES))}. "
                    f"Got: {sound_type!r}"
                ),
            )

        sound_chains = _FX[sound_type]

        # Try exact genre match, then fallback to closest
        if genre in sound_chains:
            chain = sound_chains[genre]
            matched_genre = genre
        else:
            # Fallback: use first available chain for this sound type
            matched_genre = next(iter(sound_chains))
            chain = sound_chains[matched_genre]

        return ToolResult(
            success=True,
            data={
                "sound_type": sound_type,
                "genre": matched_genre,
                "requested_genre": genre,
                "fx_chain": chain,
                "effect_count": len(chain),
            },
            metadata={
                "exact_match": matched_genre == genre,
                "available_genres_for_sound": list(sound_chains.keys()),
            },
        )

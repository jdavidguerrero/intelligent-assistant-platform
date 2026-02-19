"""
suggest_mix_template tool — recommend fader levels, panning, and sidechain routing.

Pure computation: no LLM, no DB, no I/O.

Returns a complete mix starting template for a given genre including:
  - Channel list with fader levels (dBFS), panning positions, and solo/mute states
  - Sidechain routing (which channels duck when the kick hits)
  - Bus routing (which channels go to which submix buses)
  - Master bus processing chain (light version of suggest_fx_chain)
  - Genre-specific mix notes (LUFS target, headroom, balance philosophy)

Design principle:
  Numbers are mix starting points, not final values. Every fader level
  is informed by the genre's characteristic balance (e.g. kick-heavy
  in techno, warm bass-forward in deep house).

LUFS targets by genre:
  Techno/house:   -8 to -6 LUFS (loud, high energy)
  Deep house:     -12 to -10 LUFS (warm, dynamic)
  Melodic techno: -10 to -8 LUFS
  Organic house:  -11 to -9 LUFS
"""

from typing import Any

from tools.base import MusicalTool, ToolParameter, ToolResult

# ---------------------------------------------------------------------------
# Mix template data
# ---------------------------------------------------------------------------

_MIX_TEMPLATES: dict[str, dict[str, Any]] = {
    "house": {
        "lufs_target": "-8 to -6",
        "true_peak_db": -1.0,
        "headroom_db": 6,
        "mix_philosophy": (
            "Kick-forward mix. The four-on-the-floor kick is the loudest element. "
            "Bass sits just below the kick. Everything else supports the groove."
        ),
        "channels": [
            {"name": "Kick", "fader_db": 0, "pan": 0, "bus": "drums", "sidechain_source": False},
            {
                "name": "Snare/Clap",
                "fader_db": -3,
                "pan": 0,
                "bus": "drums",
                "sidechain_source": False,
            },
            {
                "name": "Hi-Hats",
                "fader_db": -6,
                "pan": 5,
                "bus": "drums",
                "sidechain_source": False,
            },
            {
                "name": "Percussion",
                "fader_db": -9,
                "pan": -15,
                "bus": "drums",
                "sidechain_source": False,
            },
            {"name": "Bass", "fader_db": -4, "pan": 0, "bus": "bass", "sidechain_source": False},
            {"name": "Sub", "fader_db": -6, "pan": 0, "bus": "bass", "sidechain_source": False},
            {
                "name": "Chord Pad",
                "fader_db": -9,
                "pan": 0,
                "bus": "synths",
                "sidechain_source": False,
            },
            {
                "name": "Lead Synth",
                "fader_db": -7,
                "pan": 10,
                "bus": "synths",
                "sidechain_source": False,
            },
            {
                "name": "Vocal Chop",
                "fader_db": -8,
                "pan": -5,
                "bus": "synths",
                "sidechain_source": False,
            },
            {"name": "FX/Riser", "fader_db": -12, "pan": 0, "bus": "fx", "sidechain_source": False},
        ],
        "buses": [
            {
                "name": "drums",
                "fader_db": 0,
                "processing": "bus compressor: ratio 2:1, attack 10ms, release 80ms",
            },
            {"name": "bass", "fader_db": -1, "processing": "sidechain comp triggered by kick"},
            {
                "name": "synths",
                "fader_db": -3,
                "processing": "subtle parallel compression, reverb send",
            },
            {"name": "fx", "fader_db": -6, "processing": "heavy reverb, ping-pong delay"},
        ],
        "sidechain_routing": [
            {
                "source": "Kick",
                "destination": "Bass",
                "ratio": "4:1",
                "attack_ms": 5,
                "release_ms": 100,
            },
            {
                "source": "Kick",
                "destination": "Sub",
                "ratio": "6:1",
                "attack_ms": 3,
                "release_ms": 80,
            },
            {
                "source": "Kick",
                "destination": "Chord Pad",
                "ratio": "2:1",
                "attack_ms": 10,
                "release_ms": 150,
            },
        ],
        "master_bus": [
            {"effect": "EQ", "params": "high shelf +1dB @ 10kHz, low shelf +0.5dB @ 80Hz"},
            {
                "effect": "Bus Compressor",
                "params": "ratio 2:1, threshold -6dB, attack 30ms, release 200ms",
            },
            {"effect": "Tape Saturation", "params": "drive 5%, mix 40%"},
            {"effect": "Limiter", "params": "ceiling -0.5dBTP, release 50ms"},
        ],
    },
    "deep house": {
        "lufs_target": "-12 to -10",
        "true_peak_db": -1.0,
        "headroom_db": 8,
        "mix_philosophy": (
            "Warm, balanced mix. No element dominates. "
            "Rhodes and vocal chops sit forward. Kick is round, not punchy. "
            "The mix should breathe — don't over-compress."
        ),
        "channels": [
            {"name": "Kick", "fader_db": -2, "pan": 0, "bus": "drums", "sidechain_source": True},
            {
                "name": "Snare/Rim",
                "fader_db": -5,
                "pan": 0,
                "bus": "drums",
                "sidechain_source": False,
            },
            {"name": "Ride", "fader_db": -7, "pan": 20, "bus": "drums", "sidechain_source": False},
            {
                "name": "Shaker",
                "fader_db": -10,
                "pan": -15,
                "bus": "drums",
                "sidechain_source": False,
            },
            {"name": "Bass", "fader_db": -5, "pan": 0, "bus": "bass", "sidechain_source": False},
            {
                "name": "Rhodes",
                "fader_db": -3,
                "pan": -20,
                "bus": "keys",
                "sidechain_source": False,
            },
            {
                "name": "Organ Stab",
                "fader_db": -8,
                "pan": 20,
                "bus": "keys",
                "sidechain_source": False,
            },
            {
                "name": "Chord Pad",
                "fader_db": -8,
                "pan": 0,
                "bus": "synths",
                "sidechain_source": False,
            },
            {
                "name": "Vocal Chop",
                "fader_db": -4,
                "pan": 5,
                "bus": "synths",
                "sidechain_source": False,
            },
            {
                "name": "Strings",
                "fader_db": -12,
                "pan": 0,
                "bus": "synths",
                "sidechain_source": False,
            },
            {"name": "FX", "fader_db": -14, "pan": 0, "bus": "fx", "sidechain_source": False},
        ],
        "buses": [
            {
                "name": "drums",
                "fader_db": -1,
                "processing": "room reverb send, gentle bus comp 2:1",
            },
            {"name": "bass", "fader_db": -2, "processing": "sidechain from kick (softer ratio)"},
            {
                "name": "keys",
                "fader_db": -1,
                "processing": "tape saturation, Leslie cabinet sim on Rhodes",
            },
            {"name": "synths", "fader_db": -3, "processing": "hall reverb send 15%, wide stereo"},
            {"name": "fx", "fader_db": -8, "processing": "long reverb 3s+"},
        ],
        "sidechain_routing": [
            {
                "source": "Kick",
                "destination": "Bass",
                "ratio": "2:1",
                "attack_ms": 15,
                "release_ms": 120,
            },
            {
                "source": "Kick",
                "destination": "Rhodes",
                "ratio": "1.5:1",
                "attack_ms": 20,
                "release_ms": 200,
            },
        ],
        "master_bus": [
            {"effect": "EQ", "params": "high shelf +0.5dB @ 12kHz, low shelf +1dB @ 60Hz"},
            {
                "effect": "Bus Compressor",
                "params": "ratio 1.5:1, threshold -10dB, attack 50ms, release 300ms",
            },
            {"effect": "Tape Saturation", "params": "drive 8%, mix 50% — warmth is the goal"},
            {"effect": "Limiter", "params": "ceiling -1dBTP, release 100ms — preserve dynamics"},
        ],
    },
    "organic house": {
        "lufs_target": "-11 to -9",
        "true_peak_db": -1.0,
        "headroom_db": 7,
        "mix_philosophy": (
            "Textural, spatial mix. Reverb and space are instruments. "
            "Percussion elements are layered — shakers, congas, bongos all contribute. "
            "The kick sits slightly back, letting the percussion breathe."
        ),
        "channels": [
            {"name": "Kick", "fader_db": -1, "pan": 0, "bus": "drums", "sidechain_source": True},
            {"name": "Snare", "fader_db": -4, "pan": 0, "bus": "drums", "sidechain_source": False},
            {
                "name": "Hi-Hat",
                "fader_db": -7,
                "pan": 10,
                "bus": "drums",
                "sidechain_source": False,
            },
            {
                "name": "Shaker",
                "fader_db": -9,
                "pan": -10,
                "bus": "perc",
                "sidechain_source": False,
            },
            {
                "name": "Bongo/Conga",
                "fader_db": -8,
                "pan": 25,
                "bus": "perc",
                "sidechain_source": False,
            },
            {"name": "Bass", "fader_db": -4, "pan": 0, "bus": "bass", "sidechain_source": False},
            {
                "name": "Chord Pad",
                "fader_db": -6,
                "pan": 0,
                "bus": "pads",
                "sidechain_source": False,
            },
            {
                "name": "Texture/Atmo",
                "fader_db": -12,
                "pan": 0,
                "bus": "pads",
                "sidechain_source": False,
            },
            {
                "name": "Lead",
                "fader_db": -7,
                "pan": -5,
                "bus": "melodic",
                "sidechain_source": False,
            },
            {"name": "Arp", "fader_db": -9, "pan": 15, "bus": "melodic", "sidechain_source": False},
            {
                "name": "FX/Nature",
                "fader_db": -14,
                "pan": 0,
                "bus": "fx",
                "sidechain_source": False,
            },
        ],
        "buses": [
            {"name": "drums", "fader_db": 0, "processing": "room reverb 0.6s, gentle comp"},
            {"name": "perc", "fader_db": -1, "processing": "hall reverb send 20%, wide pan"},
            {"name": "bass", "fader_db": -2, "processing": "sidechain from kick"},
            {"name": "pads", "fader_db": -3, "processing": "large hall reverb, chorus, wide"},
            {"name": "melodic", "fader_db": -2, "processing": "medium reverb, 1/8 delay"},
            {"name": "fx", "fader_db": -8, "processing": "infinite reverb, filter sweeps"},
        ],
        "sidechain_routing": [
            {
                "source": "Kick",
                "destination": "Bass",
                "ratio": "3:1",
                "attack_ms": 8,
                "release_ms": 100,
            },
            {
                "source": "Kick",
                "destination": "Chord Pad",
                "ratio": "2:1",
                "attack_ms": 12,
                "release_ms": 150,
            },
        ],
        "master_bus": [
            {"effect": "EQ", "params": "+1dB @ 8kHz air shelf, +0.5dB @ 70Hz warmth"},
            {
                "effect": "Bus Compressor",
                "params": "ratio 2:1, threshold -8dB, attack 40ms, release 250ms",
            },
            {"effect": "Saturation", "params": "tube, drive 4%, mix 30%"},
            {"effect": "Limiter", "params": "ceiling -0.5dBTP, release 80ms"},
        ],
    },
    "melodic techno": {
        "lufs_target": "-10 to -8",
        "true_peak_db": -1.0,
        "headroom_db": 6,
        "mix_philosophy": (
            "Cinematic, driven mix. The kick drives relentlessly. "
            "Pads are wide but dark. "
            "Melody cuts through with high-mid presence. "
            "More dynamic range than straight techno."
        ),
        "channels": [
            {"name": "Kick", "fader_db": 0, "pan": 0, "bus": "drums", "sidechain_source": True},
            {"name": "Snare", "fader_db": -4, "pan": 0, "bus": "drums", "sidechain_source": False},
            {"name": "Hi-Hat", "fader_db": -5, "pan": 8, "bus": "drums", "sidechain_source": False},
            {"name": "Clap", "fader_db": -6, "pan": 0, "bus": "drums", "sidechain_source": False},
            {"name": "Bass", "fader_db": -5, "pan": 0, "bus": "bass", "sidechain_source": False},
            {
                "name": "Dark Pad",
                "fader_db": -7,
                "pan": 0,
                "bus": "pads",
                "sidechain_source": False,
            },
            {
                "name": "Arp/Pluck",
                "fader_db": -6,
                "pan": -10,
                "bus": "synths",
                "sidechain_source": False,
            },
            {
                "name": "Lead Synth",
                "fader_db": -5,
                "pan": 5,
                "bus": "synths",
                "sidechain_source": False,
            },
            {
                "name": "Atmosphere",
                "fader_db": -13,
                "pan": 0,
                "bus": "pads",
                "sidechain_source": False,
            },
            {"name": "FX/Riser", "fader_db": -11, "pan": 0, "bus": "fx", "sidechain_source": False},
        ],
        "buses": [
            {"name": "drums", "fader_db": 0, "processing": "hard limiting, side-chain generator"},
            {"name": "bass", "fader_db": -2, "processing": "sidechain from kick, hard clip"},
            {"name": "pads", "fader_db": -3, "processing": "wide plate reverb, bitcrush subtle"},
            {"name": "synths", "fader_db": -2, "processing": "ping-pong delay, high-pass 500Hz"},
            {"name": "fx", "fader_db": -7, "processing": "reverse reverb, filter automation"},
        ],
        "sidechain_routing": [
            {
                "source": "Kick",
                "destination": "Bass",
                "ratio": "6:1",
                "attack_ms": 3,
                "release_ms": 80,
            },
            {
                "source": "Kick",
                "destination": "Dark Pad",
                "ratio": "3:1",
                "attack_ms": 8,
                "release_ms": 120,
            },
        ],
        "master_bus": [
            {
                "effect": "EQ",
                "params": "high shelf -0.5dB @ 8kHz (control brightness), +1dB @ 60Hz",
            },
            {
                "effect": "Bus Compressor",
                "params": "ratio 3:1, threshold -6dB, attack 15ms, release 150ms",
            },
            {"effect": "Clipper", "params": "soft clip at -2dBTP before limiter"},
            {"effect": "Limiter", "params": "ceiling -0.5dBTP, release 30ms"},
        ],
    },
    "techno": {
        "lufs_target": "-8 to -6",
        "true_peak_db": -0.5,
        "headroom_db": 5,
        "mix_philosophy": (
            "Loud, driving, relentless. The kick is always the loudest element. "
            "Everything else serves the kick. Minimal headroom — this is a loud format."
        ),
        "channels": [
            {"name": "Kick", "fader_db": 0, "pan": 0, "bus": "drums", "sidechain_source": True},
            {"name": "Snare", "fader_db": -3, "pan": 0, "bus": "drums", "sidechain_source": False},
            {
                "name": "Hi-Hat 16th",
                "fader_db": -4,
                "pan": 6,
                "bus": "drums",
                "sidechain_source": False,
            },
            {
                "name": "Open Hat",
                "fader_db": -6,
                "pan": -6,
                "bus": "drums",
                "sidechain_source": False,
            },
            {"name": "Ride", "fader_db": -5, "pan": 10, "bus": "drums", "sidechain_source": False},
            {"name": "Bass", "fader_db": -4, "pan": 0, "bus": "bass", "sidechain_source": False},
            {
                "name": "Synth Loop",
                "fader_db": -8,
                "pan": 0,
                "bus": "synths",
                "sidechain_source": False,
            },
            {
                "name": "FX Texture",
                "fader_db": -12,
                "pan": 0,
                "bus": "fx",
                "sidechain_source": False,
            },
        ],
        "buses": [
            {"name": "drums", "fader_db": 0, "processing": "parallel compression, heavy limiting"},
            {"name": "bass", "fader_db": -1, "processing": "sidechain from kick, hard clip"},
            {"name": "synths", "fader_db": -4, "processing": "distortion, narrow bandpass"},
            {"name": "fx", "fader_db": -8, "processing": "industrial reverb, metallic delay"},
        ],
        "sidechain_routing": [
            {
                "source": "Kick",
                "destination": "Bass",
                "ratio": "8:1",
                "attack_ms": 1,
                "release_ms": 60,
            },
            {
                "source": "Kick",
                "destination": "Synth Loop",
                "ratio": "4:1",
                "attack_ms": 5,
                "release_ms": 80,
            },
        ],
        "master_bus": [
            {"effect": "EQ", "params": "+1.5dB @ 60Hz, -1dB @ 300Hz (remove mud)"},
            {
                "effect": "Bus Compressor",
                "params": "ratio 4:1, threshold -4dB, attack 10ms, release 100ms",
            },
            {"effect": "Clipper", "params": "clip at -1.5dBTP"},
            {"effect": "Limiter", "params": "ceiling -0.1dBTP, release 20ms"},
        ],
    },
}

VALID_GENRES: frozenset[str] = frozenset(_MIX_TEMPLATES.keys())


class SuggestMixTemplate(MusicalTool):
    """
    Suggest a complete mix template for a genre.

    Returns fader levels (dBFS), panning positions, bus routing,
    sidechain routing, and master bus processing chain — all with
    concrete starting-point values ready to dial into any DAW.

    Covers house, deep house, organic house, melodic techno, and techno.
    """

    @property
    def name(self) -> str:
        return "suggest_mix_template"

    @property
    def description(self) -> str:
        return (
            "Suggest a complete mix template with fader levels, panning, bus routing, "
            "sidechain configuration, and master bus processing for a genre. "
            "Returns concrete numbers: fader levels in dBFS, pan positions, "
            "LUFS target, and specific effect parameters. "
            "Use when the user asks how to set up a mix, what levels to use, "
            "how to route channels, or wants a mixing starting point for a genre. "
            f"Supported genres: {', '.join(sorted(VALID_GENRES))}."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="genre",
                type=str,
                description=(
                    f"Music genre. Options: {', '.join(sorted(VALID_GENRES))}. " "Default: 'house'."
                ),
                required=False,
                default="house",
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        genre: str = (kwargs.get("genre") or "house").strip().lower()

        if genre not in VALID_GENRES:
            return ToolResult(
                success=False,
                error=f"genre must be one of: {', '.join(sorted(VALID_GENRES))}. Got: {genre!r}",
            )

        template = _MIX_TEMPLATES[genre]

        return ToolResult(
            success=True,
            data=template,
            metadata={
                "genre": genre,
                "channel_count": len(template["channels"]),
                "bus_count": len(template["buses"]),
                "sidechain_routes": len(template["sidechain_routing"]),
            },
        )

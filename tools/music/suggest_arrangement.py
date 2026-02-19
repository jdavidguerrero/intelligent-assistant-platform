"""
suggest_arrangement tool — generate a complete track arrangement structure.

Pure computation: no LLM, no DB, no I/O.

Given a genre and target duration, returns:
  - Section-by-section arrangement (intro, build, drop, breakdown, etc.)
  - Exact bar numbers for each section
  - Which elements are active per section (kick, bass, pads, leads, etc.)
  - Energy curve (1–10) per section
  - DJ compatibility notes (where to mix in/out)
  - Producer notes for each section

Design principle:
  Arrangements are informed by real DJ sets and live performances.
  The "DJ mix point" at bar 16 and 32 is universal across genres —
  this is where tracks are mixed in and out in a DJ context.

  Energy curve is non-linear: builds are gradual, drops are instant,
  breakdowns reset energy, outros fade.
"""

from typing import Any

from tools.base import MusicalTool, ToolParameter, ToolResult

# ---------------------------------------------------------------------------
# Arrangement section data
# ---------------------------------------------------------------------------

# Canonical element names used across all templates
_ALL_ELEMENTS = [
    "kick",
    "bass",
    "hats",
    "percussion",
    "chord_pad",
    "lead",
    "melody",
    "arp",
    "vocal_chop",
    "atmosphere",
    "fx",
]

# element_matrix: dict[section_name, set[elements]]
# Defines which elements are active (True) in each section

_ARRANGEMENTS: dict[str, list[dict[str, Any]]] = {
    "house": [
        {
            "section": "Intro",
            "bars": (1, 16),
            "energy": 3,
            "elements": {
                "kick": True,
                "bass": True,
                "hats": True,
                "percussion": False,
                "chord_pad": False,
                "lead": False,
                "melody": False,
                "arp": False,
                "vocal_chop": False,
                "atmosphere": True,
                "fx": True,
            },
            "notes": "Kick + bass + hats only. Atmospheric tail. DJ mix-in point.",
            "dj_note": "MIX IN: Beatmatch at bar 1, fade in by bar 8.",
        },
        {
            "section": "Build 1",
            "bars": (17, 32),
            "energy": 5,
            "elements": {
                "kick": True,
                "bass": True,
                "hats": True,
                "percussion": True,
                "chord_pad": True,
                "lead": False,
                "melody": False,
                "arp": False,
                "vocal_chop": False,
                "atmosphere": True,
                "fx": True,
            },
            "notes": "Chord pad enters. Percussion layer added. Energy rises.",
            "dj_note": None,
        },
        {
            "section": "Main Groove",
            "bars": (33, 64),
            "energy": 8,
            "elements": {
                "kick": True,
                "bass": True,
                "hats": True,
                "percussion": True,
                "chord_pad": True,
                "lead": True,
                "melody": False,
                "arp": False,
                "vocal_chop": True,
                "atmosphere": False,
                "fx": False,
            },
            "notes": "Full groove. Lead element introduced (vocal chop or synth). High energy.",
            "dj_note": None,
        },
        {
            "section": "Breakdown",
            "bars": (65, 80),
            "energy": 4,
            "elements": {
                "kick": False,
                "bass": False,
                "hats": False,
                "percussion": False,
                "chord_pad": True,
                "lead": False,
                "melody": True,
                "arp": False,
                "vocal_chop": False,
                "atmosphere": True,
                "fx": True,
            },
            "notes": "Percussion drops. Chord sequence exposed. Build tension for the drop.",
            "dj_note": "DJ MIX OUT: Mix out here if leaving early (bar 65).",
        },
        {
            "section": "Drop",
            "bars": (81, 96),
            "energy": 9,
            "elements": {
                "kick": True,
                "bass": True,
                "hats": True,
                "percussion": True,
                "chord_pad": True,
                "lead": True,
                "melody": False,
                "arp": True,
                "vocal_chop": True,
                "atmosphere": False,
                "fx": False,
            },
            "notes": "Full groove returns with arp and additional melodic element.",
            "dj_note": None,
        },
        {
            "section": "Development",
            "bars": (97, 128),
            "energy": 7,
            "elements": {
                "kick": True,
                "bass": True,
                "hats": True,
                "percussion": True,
                "chord_pad": True,
                "lead": True,
                "melody": True,
                "arp": False,
                "vocal_chop": True,
                "atmosphere": False,
                "fx": False,
            },
            "notes": "Layering and unlayering. Elements enter and leave. Counter-melodies.",
            "dj_note": None,
        },
        {
            "section": "Outro",
            "bars": (129, 144),
            "energy": 3,
            "elements": {
                "kick": True,
                "bass": True,
                "hats": True,
                "percussion": False,
                "chord_pad": False,
                "lead": False,
                "melody": False,
                "arp": False,
                "vocal_chop": False,
                "atmosphere": True,
                "fx": False,
            },
            "notes": "Mirror of intro. Gradual strip back. DJ mix-out point.",
            "dj_note": "MIX OUT: Beatmatch at bar 129, fade out by bar 144.",
        },
    ],
    "techno": [
        {
            "section": "Intro",
            "bars": (1, 16),
            "energy": 4,
            "elements": {
                "kick": True,
                "bass": True,
                "hats": True,
                "percussion": False,
                "chord_pad": False,
                "lead": False,
                "melody": False,
                "arp": False,
                "vocal_chop": False,
                "atmosphere": False,
                "fx": True,
            },
            "notes": "Kick + hat driving pattern. No chords. Tension through rhythm alone.",
            "dj_note": "MIX IN: Bar 1–16.",
        },
        {
            "section": "Layer 1",
            "bars": (17, 32),
            "energy": 6,
            "elements": {
                "kick": True,
                "bass": True,
                "hats": True,
                "percussion": True,
                "chord_pad": False,
                "lead": False,
                "melody": False,
                "arp": False,
                "vocal_chop": False,
                "atmosphere": True,
                "fx": True,
            },
            "notes": "Bassline and percussion layer added. Atmosphere enters.",
            "dj_note": None,
        },
        {
            "section": "Peak",
            "bars": (33, 96),
            "energy": 9,
            "elements": {
                "kick": True,
                "bass": True,
                "hats": True,
                "percussion": True,
                "chord_pad": True,
                "lead": True,
                "melody": False,
                "arp": False,
                "vocal_chop": False,
                "atmosphere": False,
                "fx": False,
            },
            "notes": "Full techno wall. All percussion active. Hypnotic and relentless.",
            "dj_note": None,
        },
        {
            "section": "Break",
            "bars": (97, 112),
            "energy": 5,
            "elements": {
                "kick": False,
                "bass": True,
                "hats": True,
                "percussion": True,
                "chord_pad": False,
                "lead": False,
                "melody": False,
                "arp": False,
                "vocal_chop": False,
                "atmosphere": True,
                "fx": True,
            },
            "notes": "Kick drops. Texture and atmosphere take over. Anticipation builds.",
            "dj_note": "DJ MIX OUT: Bar 97.",
        },
        {
            "section": "Reload",
            "bars": (113, 144),
            "energy": 8,
            "elements": {
                "kick": True,
                "bass": True,
                "hats": True,
                "percussion": True,
                "chord_pad": True,
                "lead": False,
                "melody": False,
                "arp": False,
                "vocal_chop": False,
                "atmosphere": False,
                "fx": False,
            },
            "notes": "Kick returns. Stripped groove before outro.",
            "dj_note": None,
        },
        {
            "section": "Outro",
            "bars": (145, 160),
            "energy": 4,
            "elements": {
                "kick": True,
                "bass": True,
                "hats": True,
                "percussion": False,
                "chord_pad": False,
                "lead": False,
                "melody": False,
                "arp": False,
                "vocal_chop": False,
                "atmosphere": False,
                "fx": False,
            },
            "notes": "Stripped outro — kick + hat only. Easy mix-out.",
            "dj_note": "MIX OUT: Bar 145–160.",
        },
    ],
    "organic house": [
        {
            "section": "Intro",
            "bars": (1, 16),
            "energy": 2,
            "elements": {
                "kick": False,
                "bass": False,
                "hats": False,
                "percussion": True,
                "chord_pad": False,
                "lead": False,
                "melody": False,
                "arp": False,
                "vocal_chop": False,
                "atmosphere": True,
                "fx": True,
            },
            "notes": "Percussion and atmosphere only. No kick yet — builds tension organically.",
            "dj_note": "MIX IN: Atmospheric elements from bar 1.",
        },
        {
            "section": "Groove Entry",
            "bars": (17, 32),
            "energy": 4,
            "elements": {
                "kick": True,
                "bass": True,
                "hats": True,
                "percussion": True,
                "chord_pad": False,
                "lead": False,
                "melody": False,
                "arp": False,
                "vocal_chop": False,
                "atmosphere": True,
                "fx": False,
            },
            "notes": "Kick and bass enter. Keep it minimal — let the groove breathe.",
            "dj_note": None,
        },
        {
            "section": "Chord Entry",
            "bars": (33, 64),
            "energy": 6,
            "elements": {
                "kick": True,
                "bass": True,
                "hats": True,
                "percussion": True,
                "chord_pad": True,
                "lead": False,
                "melody": True,
                "arp": False,
                "vocal_chop": False,
                "atmosphere": True,
                "fx": False,
            },
            "notes": "Chord progression enters. Melody begins — subtle at first.",
            "dj_note": None,
        },
        {
            "section": "Full Texture",
            "bars": (65, 96),
            "energy": 8,
            "elements": {
                "kick": True,
                "bass": True,
                "hats": True,
                "percussion": True,
                "chord_pad": True,
                "lead": True,
                "melody": True,
                "arp": True,
                "vocal_chop": False,
                "atmosphere": True,
                "fx": False,
            },
            "notes": "Maximum texture. Arp and lead both present. Organic density.",
            "dj_note": None,
        },
        {
            "section": "Breakdown",
            "bars": (97, 112),
            "energy": 3,
            "elements": {
                "kick": False,
                "bass": False,
                "hats": False,
                "percussion": True,
                "chord_pad": True,
                "lead": False,
                "melody": True,
                "arp": False,
                "vocal_chop": False,
                "atmosphere": True,
                "fx": True,
            },
            "notes": "Back to the organic root — percussion + atmosphere + melody.",
            "dj_note": "MIX OUT: Bar 97 if transitioning.",
        },
        {
            "section": "Outro",
            "bars": (113, 128),
            "energy": 3,
            "elements": {
                "kick": True,
                "bass": True,
                "hats": True,
                "percussion": True,
                "chord_pad": False,
                "lead": False,
                "melody": False,
                "arp": False,
                "vocal_chop": False,
                "atmosphere": True,
                "fx": False,
            },
            "notes": "Groove returns but stripped — mirrors intro arc.",
            "dj_note": "MIX OUT: Bar 113–128.",
        },
    ],
    "deep house": [
        {
            "section": "Intro",
            "bars": (1, 16),
            "energy": 3,
            "elements": {
                "kick": True,
                "bass": True,
                "hats": True,
                "percussion": False,
                "chord_pad": False,
                "lead": False,
                "melody": False,
                "arp": False,
                "vocal_chop": False,
                "atmosphere": True,
                "fx": False,
            },
            "notes": "Minimal groove. Soulful tone from the start.",
            "dj_note": "MIX IN: Bar 1–16.",
        },
        {
            "section": "Main Groove",
            "bars": (17, 48),
            "energy": 6,
            "elements": {
                "kick": True,
                "bass": True,
                "hats": True,
                "percussion": True,
                "chord_pad": True,
                "lead": False,
                "melody": False,
                "arp": False,
                "vocal_chop": True,
                "atmosphere": False,
                "fx": False,
            },
            "notes": "Full deep house groove. Rhodes or organ enters. Vocal chop present.",
            "dj_note": None,
        },
        {
            "section": "Development",
            "bars": (49, 80),
            "energy": 7,
            "elements": {
                "kick": True,
                "bass": True,
                "hats": True,
                "percussion": True,
                "chord_pad": True,
                "lead": True,
                "melody": True,
                "arp": False,
                "vocal_chop": True,
                "atmosphere": False,
                "fx": False,
            },
            "notes": "Lead flute or piano enters. Harmonic complexity increases.",
            "dj_note": None,
        },
        {
            "section": "Breakdown",
            "bars": (81, 96),
            "energy": 4,
            "elements": {
                "kick": False,
                "bass": False,
                "hats": False,
                "percussion": False,
                "chord_pad": True,
                "lead": False,
                "melody": True,
                "arp": False,
                "vocal_chop": False,
                "atmosphere": True,
                "fx": True,
            },
            "notes": "Just chord sequence and atmosphere. Soulful and exposed.",
            "dj_note": "MIX OUT: Bar 81.",
        },
        {
            "section": "Outro",
            "bars": (97, 112),
            "energy": 3,
            "elements": {
                "kick": True,
                "bass": True,
                "hats": True,
                "percussion": False,
                "chord_pad": False,
                "lead": False,
                "melody": False,
                "arp": False,
                "vocal_chop": False,
                "atmosphere": True,
                "fx": False,
            },
            "notes": "Return to minimal. Mirror of intro.",
            "dj_note": "MIX OUT: Bar 97–112.",
        },
    ],
    "melodic techno": [
        {
            "section": "Intro",
            "bars": (1, 16),
            "energy": 3,
            "elements": {
                "kick": True,
                "bass": True,
                "hats": False,
                "percussion": False,
                "chord_pad": True,
                "lead": False,
                "melody": False,
                "arp": False,
                "vocal_chop": False,
                "atmosphere": True,
                "fx": True,
            },
            "notes": "Cinematic open. Pad and atmosphere with kick bass foundation.",
            "dj_note": "MIX IN: Bar 1–16.",
        },
        {
            "section": "Build",
            "bars": (17, 48),
            "energy": 6,
            "elements": {
                "kick": True,
                "bass": True,
                "hats": True,
                "percussion": True,
                "chord_pad": True,
                "lead": False,
                "melody": True,
                "arp": True,
                "vocal_chop": False,
                "atmosphere": True,
                "fx": False,
            },
            "notes": "Full drum groove arrives. Arp and melody build the harmonic world.",
            "dj_note": None,
        },
        {
            "section": "Peak",
            "bars": (49, 96),
            "energy": 9,
            "elements": {
                "kick": True,
                "bass": True,
                "hats": True,
                "percussion": True,
                "chord_pad": True,
                "lead": True,
                "melody": True,
                "arp": True,
                "vocal_chop": False,
                "atmosphere": False,
                "fx": False,
            },
            "notes": "Everything on. Maximum cinematic impact.",
            "dj_note": None,
        },
        {
            "section": "Breakdown",
            "bars": (97, 112),
            "energy": 4,
            "elements": {
                "kick": False,
                "bass": False,
                "hats": False,
                "percussion": False,
                "chord_pad": True,
                "lead": True,
                "melody": True,
                "arp": False,
                "vocal_chop": False,
                "atmosphere": True,
                "fx": True,
            },
            "notes": "Drop everything except melody and pads. Pure cinematic emotion.",
            "dj_note": "MIX OUT: Bar 97.",
        },
        {
            "section": "Outro",
            "bars": (113, 128),
            "energy": 5,
            "elements": {
                "kick": True,
                "bass": True,
                "hats": True,
                "percussion": True,
                "chord_pad": True,
                "lead": False,
                "melody": False,
                "arp": False,
                "vocal_chop": False,
                "atmosphere": True,
                "fx": False,
            },
            "notes": "Groove returns. Stripped — sets up for the next track.",
            "dj_note": "MIX OUT: Bar 113–128.",
        },
    ],
}

VALID_GENRES: frozenset[str] = frozenset(_ARRANGEMENTS.keys())


class SuggestArrangement(MusicalTool):
    """
    Suggest a complete track arrangement structure for a genre.

    Returns section-by-section breakdown with exact bar numbers,
    active elements per section, energy curve, and DJ mix-in/out points.

    Covers house, techno, organic house, deep house, melodic techno.
    """

    @property
    def name(self) -> str:
        return "suggest_arrangement"

    @property
    def description(self) -> str:
        return (
            "Suggest a complete track arrangement for a genre. "
            "Returns sections (intro, build, drop, breakdown, outro) with "
            "exact bar numbers, which elements are active in each section, "
            "energy level curve, and DJ mix-in/out points. "
            "Use when the user asks how to structure a track, "
            "what sections a house/techno track needs, "
            "or wants to plan the arrangement of their production. "
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

        sections = _ARRANGEMENTS[genre]
        total_bars = sections[-1]["bars"][1]
        energy_curve = [{"section": s["section"], "energy": s["energy"]} for s in sections]
        dj_mix_points = [
            {"section": s["section"], "bars": s["bars"], "note": s["dj_note"]}
            for s in sections
            if s["dj_note"]
        ]

        return ToolResult(
            success=True,
            data={
                "genre": genre,
                "total_bars": total_bars,
                "sections": sections,
                "energy_curve": energy_curve,
                "dj_mix_points": dj_mix_points,
                "available_elements": _ALL_ELEMENTS,
            },
            metadata={
                "section_count": len(sections),
                "total_bars": total_bars,
                "dj_mix_point_count": len(dj_mix_points),
            },
        )

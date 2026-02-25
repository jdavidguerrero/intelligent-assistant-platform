"""
core/music_theory/ — Pure music theory engine.

Exports:
    Types:   Chord, Scale, Interval, VoicingResult,
             BassNote, DrumHit, DrumPattern, DRUM_INSTRUMENTS
    Scales:  get_scale_notes, get_diatonic_chords, get_pitch_classes
    Harmony: melody_to_chords, available_genres
    Voicing: optimize_voice_leading, VoicedChord, total_voice_leading_cost
    Bass:    generate_bassline
"""

from core.music_theory.bass import generate_bassline
from core.music_theory.drums import generate_pattern
from core.music_theory.harmony import available_genres, melody_to_chords, suggest_progression
from core.music_theory.scales import get_diatonic_chords, get_pitch_classes, get_scale_notes
from core.music_theory.types import (
    DRUM_INSTRUMENTS,
    BassNote,
    Chord,
    DrumHit,
    DrumPattern,
    Interval,
    Scale,
    VoicingResult,
)
from core.music_theory.voicing import VoicedChord, optimize_voice_leading, total_voice_leading_cost

__all__ = [
    # Types
    "Chord",
    "Interval",
    "Scale",
    "VoicingResult",
    "VoicedChord",
    "BassNote",
    "DrumHit",
    "DrumPattern",
    "DRUM_INSTRUMENTS",
    # Scales
    "get_scale_notes",
    "get_diatonic_chords",
    "get_pitch_classes",
    # Harmony
    "melody_to_chords",
    "available_genres",
    "suggest_progression",
    # Voicing
    "optimize_voice_leading",
    "total_voice_leading_cost",
    # Bass
    "generate_bassline",
    # Drums
    "generate_pattern",
]

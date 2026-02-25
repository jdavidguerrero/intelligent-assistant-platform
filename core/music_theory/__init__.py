"""
core/music_theory/ — Pure music theory engine.

Exports:
    Types:   Chord, Scale, Interval, VoicingResult
    Scales:  get_scale_notes, get_diatonic_chords, get_pitch_classes
    Harmony: melody_to_chords, available_genres
    Voicing: optimize_voice_leading, VoicedChord, total_voice_leading_cost
"""

from core.music_theory.harmony import available_genres, melody_to_chords
from core.music_theory.scales import get_diatonic_chords, get_pitch_classes, get_scale_notes
from core.music_theory.types import Chord, Interval, Scale, VoicingResult
from core.music_theory.voicing import VoicedChord, optimize_voice_leading, total_voice_leading_cost

__all__ = [
    # Types
    "Chord",
    "Interval",
    "Scale",
    "VoicingResult",
    "VoicedChord",
    # Scales
    "get_scale_notes",
    "get_diatonic_chords",
    "get_pitch_classes",
    # Harmony
    "melody_to_chords",
    "available_genres",
    # Voicing
    "optimize_voice_leading",
    "total_voice_leading_cost",
]

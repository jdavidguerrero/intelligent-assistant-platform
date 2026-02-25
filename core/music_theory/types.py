"""
core/music_theory/types.py — Frozen value objects for the music theory engine.

All types are immutable frozen dataclasses — safe to hash, cache, and use as
dict keys. No I/O, no side effects, no external dependencies beyond stdlib.

Types:
    Chord          — a diatonic chord at a scale degree
    Scale          — a key + mode + ordered note names
    Interval       — a named semitone distance
    VoicingResult  — a harmonized chord sequence (output of melody_to_chords)
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Interval
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Interval:
    """A named musical interval expressed in semitones.

    Examples:
        Interval(semitones=0,  name="unison")
        Interval(semitones=7,  name="perfect fifth")
        Interval(semitones=12, name="octave")
    """

    semitones: int  # 0–24; negative = downward interval
    name: str  # human-readable label, e.g. "major third"

    def __post_init__(self) -> None:
        if not (-24 <= self.semitones <= 24):
            raise ValueError(f"Interval semitones must be in [-24, 24], got {self.semitones}")
        if not self.name:
            raise ValueError("Interval name must not be empty")


# ---------------------------------------------------------------------------
# Chord
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Chord:
    """A diatonic chord at a specific scale degree.

    Attributes:
        root:       Root note name, e.g. "A", "C#", "Bb"
        quality:    Chord quality key, e.g. "minor", "maj7", "min7"
        name:       Human-readable chord name, e.g. "Am7", "Fmaj7"
        roman:      Roman numeral label, e.g. "i", "IV", "vii°"
        degree:     0-based scale degree (0=I/i, 6=VII/vii)
        midi_notes: MIDI pitch numbers for the voicing (root position, octave 4)
    """

    root: str
    quality: str
    name: str
    roman: str
    degree: int
    midi_notes: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.root:
            raise ValueError("Chord.root must not be empty")
        if not self.quality:
            raise ValueError("Chord.quality must not be empty")
        if not (0 <= self.degree <= 11):
            raise ValueError(f"Chord.degree must be in [0, 11], got {self.degree}")
        for pitch in self.midi_notes:
            if not (0 <= pitch <= 127):
                raise ValueError(f"MIDI pitch {pitch} out of range [0, 127]")


# ---------------------------------------------------------------------------
# Scale
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Scale:
    """A musical scale: root + mode + ordered note names.

    Attributes:
        root:   Root note name in canonical form, e.g. "A", "C#"
        mode:   Mode name, e.g. "natural minor", "major", "dorian"
        notes:  Ordered tuple of note names from root (7 for diatonic scales)
        label:  Human-readable label, e.g. "A natural minor"
    """

    root: str
    mode: str
    notes: tuple[str, ...]

    @property
    def label(self) -> str:
        """Human-readable label, e.g. 'A natural minor'."""
        return f"{self.root} {self.mode}"

    @property
    def pitch_classes(self) -> frozenset[int]:
        """Set of MIDI pitch classes (0–11) present in this scale."""
        from core.music_theory.scales import NOTE_NAMES  # local import to avoid circularity

        return frozenset(NOTE_NAMES.index(n) for n in self.notes if n in NOTE_NAMES)

    def __post_init__(self) -> None:
        if not self.root:
            raise ValueError("Scale.root must not be empty")
        if not self.mode:
            raise ValueError("Scale.mode must not be empty")
        if not self.notes:
            raise ValueError("Scale.notes must not be empty")


# ---------------------------------------------------------------------------
# VoicingResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VoicingResult:
    """The output of melody_to_chords() — a harmonized chord sequence.

    Attributes:
        chords:         Tuple of Chord objects in bar order
        key_root:       Detected/given tonal centre, e.g. "A"
        key_mode:       Mode used for harmonization, e.g. "natural minor"
        genre:          Genre template applied, e.g. "organic house"
        bars:           Number of bars in the sequence
        roman_labels:   Roman numeral string summary, e.g. "i - VI - III - VII"
    """

    chords: tuple[Chord, ...]
    key_root: str
    key_mode: str
    genre: str
    bars: int
    roman_labels: tuple[str, ...] = field(default_factory=tuple)

    @property
    def chord_names(self) -> tuple[str, ...]:
        """Tuple of chord name strings, e.g. ('Am7', 'Fmaj7', 'C', 'Gm7')."""
        return tuple(c.name for c in self.chords)

    @property
    def progression_label(self) -> str:
        """Human-readable progression, e.g. 'i - VI - III - VII'."""
        if self.roman_labels:
            return " - ".join(self.roman_labels)
        return " - ".join(c.roman for c in self.chords)

    def __post_init__(self) -> None:
        if not self.chords:
            raise ValueError("VoicingResult.chords must not be empty")
        if not self.key_root:
            raise ValueError("VoicingResult.key_root must not be empty")
        if self.bars <= 0:
            raise ValueError(f"VoicingResult.bars must be > 0, got {self.bars}")

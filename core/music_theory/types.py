"""
core/music_theory/types.py — Frozen value objects for the music theory engine.

All types are immutable frozen dataclasses — safe to hash, cache, and use as
dict keys. No I/O, no side effects, no external dependencies beyond stdlib.

Types:
    Chord          — a diatonic chord at a scale degree
    Scale          — a key + mode + ordered note names
    Interval       — a named semitone distance
    VoicingResult  — a harmonized chord sequence (output of melody_to_chords)
    BassNote       — a single bass note on a 16-step rhythmic grid
    DrumHit        — a single drum hit on a 16-step rhythmic grid
    DrumPattern    — a full multi-instrument drum pattern
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


# ---------------------------------------------------------------------------
# BassNote — a note on the 16-step bass grid
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BassNote:
    """A single bass note placed on a 16-step (16th-note) rhythmic grid.

    The grid position model:
        - 16 steps per bar (16th-note resolution)
        - step 0 = beat 1, step 4 = beat 2, step 8 = beat 3, step 12 = beat 4

    Attributes:
        pitch_midi:     MIDI note number (0–127)
        step:           Grid position within the bar (0–15)
        duration_steps: Length in 16th-note steps (1–16)
        velocity:       MIDI velocity (0–127)
        bar:            0-indexed bar number in the pattern
        tick_offset:    Micro-timing adjustment in MIDI ticks relative to the
                        quantized grid position (+ = late, - = early).
                        Populated by humanize_timing(). Default 0 = on-grid.
    """

    pitch_midi: int
    step: int
    duration_steps: int
    velocity: int
    bar: int
    tick_offset: int = 0  # micro-timing: ±N ticks from quantized position

    def __post_init__(self) -> None:
        if not (0 <= self.pitch_midi <= 127):
            raise ValueError(
                f"BassNote.pitch_midi must be in [0, 127], got {self.pitch_midi}"
            )
        if not (0 <= self.step <= 15):
            raise ValueError(f"BassNote.step must be in [0, 15], got {self.step}")
        if not (1 <= self.duration_steps <= 16):
            raise ValueError(
                f"BassNote.duration_steps must be in [1, 16], got {self.duration_steps}"
            )
        if not (0 <= self.velocity <= 127):
            raise ValueError(
                f"BassNote.velocity must be in [0, 127], got {self.velocity}"
            )
        if self.bar < 0:
            raise ValueError(f"BassNote.bar must be >= 0, got {self.bar}")


# ---------------------------------------------------------------------------
# DrumHit — a single percussion event on the 16-step grid
# ---------------------------------------------------------------------------

#: Canonical instrument names used in genre templates and GM MIDI mapping
DRUM_INSTRUMENTS: frozenset[str] = frozenset(
    {"kick", "snare", "clap", "hihat_c", "hihat_o"}
)


@dataclass(frozen=True)
class DrumHit:
    """A single percussion hit on a 16-step (16th-note) rhythmic grid.

    Attributes:
        instrument: Instrument name — one of DRUM_INSTRUMENTS
                    ("kick", "snare", "clap", "hihat_c", "hihat_o")
        step:       Grid position within the bar (0–15)
        velocity:   MIDI velocity (0–127)
        bar:        0-indexed bar number in the pattern
        tick_offset: Micro-timing adjustment in MIDI ticks relative to the
                     quantized grid position (+ = late, - = early).
                     Populated by humanize_timing(). Default 0 = on-grid.
    """

    instrument: str
    step: int
    velocity: int
    bar: int
    tick_offset: int = 0  # micro-timing: ±N ticks from quantized position

    def __post_init__(self) -> None:
        if not self.instrument:
            raise ValueError("DrumHit.instrument must not be empty")
        if not (0 <= self.step <= 15):
            raise ValueError(f"DrumHit.step must be in [0, 15], got {self.step}")
        if not (0 <= self.velocity <= 127):
            raise ValueError(
                f"DrumHit.velocity must be in [0, 127], got {self.velocity}"
            )
        if self.bar < 0:
            raise ValueError(f"DrumHit.bar must be >= 0, got {self.bar}")


# ---------------------------------------------------------------------------
# DrumPattern — a complete multi-instrument drum sequence
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DrumPattern:
    """A complete multi-bar drum pattern across multiple instruments.

    Built from a genre template's drum_patterns section. All timing is
    expressed on a 16-step (16th-note) grid.

    Attributes:
        hits:           All drum hits in the pattern, sorted by (bar, step)
        steps_per_bar:  Grid resolution (16 = 16th-note resolution)
        bars:           Number of bars in the pattern
        bpm:            Tempo in beats per minute
        genre:          Genre template name, e.g. "organic house"
    """

    hits: tuple[DrumHit, ...]
    steps_per_bar: int
    bars: int
    bpm: float
    genre: str

    def __post_init__(self) -> None:
        if self.steps_per_bar <= 0:
            raise ValueError(
                f"DrumPattern.steps_per_bar must be > 0, got {self.steps_per_bar}"
            )
        if self.bars <= 0:
            raise ValueError(f"DrumPattern.bars must be > 0, got {self.bars}")
        if self.bpm <= 0:
            raise ValueError(f"DrumPattern.bpm must be > 0, got {self.bpm}")
        if not self.genre:
            raise ValueError("DrumPattern.genre must not be empty")

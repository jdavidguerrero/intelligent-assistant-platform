"""
core/audio/types.py — Frozen data types for audio analysis results.

All types are frozen dataclasses — immutable value objects that can be
safely passed between layers and cached.

Design principles:
    - No I/O, no state, no side effects.
    - Invariants are documented but NOT enforced at construction time —
      validation happens at creation sites (features.py, melody.py).
    - `Key.label` is a computed property to avoid duplicate storage.
    - `SampleAnalysis.notes` is a tuple (immutable sequence) for hashability.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Note:
    """A single musical note extracted from audio (time-domain).

    Invariants:
        0 <= pitch_midi <= 127
        duration_sec > 0
        0 <= velocity <= 127
        onset_sec >= 0
    """

    pitch_midi: int
    """MIDI note number (0–127). A4 = 69, C4 = 60."""

    pitch_name: str
    """Scientific pitch notation, e.g. 'A4', 'C#5'."""

    onset_sec: float
    """Start time in seconds from the beginning of the audio."""

    duration_sec: float
    """Note duration in seconds. Always > 0."""

    velocity: int
    """MIDI velocity (0–127). Estimated from RMS energy of the note segment."""


@dataclass(frozen=True)
class Key:
    """Musical key detected via Krumhansl-Schmuckler algorithm.

    Invariants:
        mode in {"major", "minor"}
        0.0 <= confidence <= 1.0
        root is a valid note name (e.g. "C", "A#", "Bb")
    """

    root: str
    """Root note name, e.g. 'A', 'C#', 'Bb'."""

    mode: str
    """'major' or 'minor'."""

    confidence: float
    """Pearson correlation of best K-S match. Range [0.0, 1.0].
    Values above 0.8 indicate strong tonal centre."""

    @property
    def label(self) -> str:
        """Human-readable key label, e.g. 'A minor', 'C# major'."""
        return f"{self.root} {self.mode}"


@dataclass(frozen=True)
class SpectralFeatures:
    """Low-level spectral features extracted from audio.

    Stored as tuples (immutable) to allow SpectralFeatures to be hashable
    and embeddable in other frozen dataclasses.
    """

    chroma: tuple[float, ...]
    """12-element mean pitch class distribution (C, C#, D, ..., B).
    Each value is the mean chroma energy for that pitch class."""

    rms: float
    """Mean RMS energy across all frames. Used for energy level calculation."""

    onsets_sec: tuple[float, ...]
    """Onset times in seconds, sorted ascending. Detected on percussive signal."""

    tempo: float
    """Estimated BPM from beat tracking. 0.0 if detection failed."""

    beat_frames: tuple[int, ...]
    """Frame indices of detected beats. Empty tuple if tracking failed."""


@dataclass(frozen=True)
class SampleAnalysis:
    """Complete analysis result for an audio sample.

    Aggregates all features extracted by analyze_sample(). The `notes`
    field is populated only when detect_melody_fn is passed to analyze_sample().

    Invariants:
        bpm >= 0.0  (0.0 = detection failed, not an error)
        0 <= energy <= 10
        duration_sec > 0
        sample_rate > 0
    """

    bpm: float
    """Detected tempo in BPM. 0.0 if detection failed."""

    key: Key
    """Detected musical key with confidence score."""

    energy: int
    """Perceptual energy level 0–10 (log-normalized RMS)."""

    duration_sec: float
    """Duration of the analyzed audio segment in seconds."""

    sample_rate: int
    """Sample rate of the audio signal in Hz."""

    notes: tuple[Note, ...] = field(default_factory=tuple)
    """Melody notes extracted by pYIN. Empty tuple if melody detection
    was not requested or found no voiced content."""

    spectral: SpectralFeatures | None = None
    """Detailed spectral features. None if not computed."""

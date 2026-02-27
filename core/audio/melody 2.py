"""
core/audio/melody.py — Monophonic melody detection using pYIN.

pYIN (Probabilistic YIN) is a pitch tracking algorithm that extends the
classic YIN algorithm with a Hidden Markov Model. It outputs:
    - f0: fundamental frequency per frame in Hz (NaN for unvoiced frames)
    - voiced_flag: boolean mask of voiced frames
    - voiced_probs: probability of voicing per frame

Why pYIN over raw FFT peak-picking:
    - Handles vibrato by tracking pitch within sustained notes
    - Separates voiced from unvoiced frames probabilistically
    - Robust to transients and harmonic distortion
    - Designed for monophonic sources (melody, bass, lead synth)

Usage:
    from core.audio.melody import detect_melody
    notes = detect_melody(y_harmonic, sr, librosa=librosa)

Best results:
    - Run HPSS (separate_hpss) first, pass y_harmonic
    - Melodies with clear tonal content (no drums/noise)
    - Monophonic or near-monophonic sources
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from core.audio.types import Note

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_NOTE_DURATION_SEC: float = 0.05
"""Minimum note duration in seconds. Notes shorter than this are discarded
as likely artifacts (pitch tracking noise, transient spikes)."""

FMIN_HZ: float = 65.41
"""C2 — minimum pitch frequency. Below this is sub-bass, not melodic."""

FMAX_HZ: float = 2093.0
"""C7 — maximum pitch frequency. Above this is outside typical melody range."""

# MIDI note name lookup (octaves 0–9)
_NOTE_NAMES_CHROMATIC: tuple[str, ...] = (
    "C",
    "C#",
    "D",
    "D#",
    "E",
    "F",
    "F#",
    "G",
    "G#",
    "A",
    "A#",
    "B",
)

_HOP_LENGTH: int = 512
"""Hop size in samples. Used for pYIN and frame-to-time conversion.
At 44100 Hz, this gives ~11.6 ms per frame — sufficient for note detection."""


# ---------------------------------------------------------------------------
# Core pitch conversion utilities (pure math, no librosa)
# ---------------------------------------------------------------------------


def _hz_to_midi(hz: float) -> int:
    """Convert frequency in Hz to nearest MIDI note number.

    Formula: midi = round(12 × log₂(hz / 440) + 69)
    A4 = 440 Hz = MIDI 69 by definition.

    Args:
        hz: Frequency in Hz. Must be > 0.

    Returns:
        MIDI note number clamped to [0, 127].

    Raises:
        ValueError: If hz ≤ 0.
    """
    if hz <= 0.0:
        raise ValueError(f"Hz must be > 0, got {hz}")
    midi_raw = 12.0 * math.log2(hz / 440.0) + 69.0
    return max(0, min(127, round(midi_raw)))


def _midi_to_name(midi: int) -> str:
    """Convert MIDI note number to scientific pitch notation.

    Examples:
        69 → 'A4'
        60 → 'C4'
        21 → 'A0' (lowest standard piano key)

    Args:
        midi: MIDI note number in [0, 127].

    Returns:
        Pitch name string like 'A4', 'C#5', 'Bb3'.
    """
    midi = max(0, min(127, midi))
    octave = (midi // 12) - 1
    note_name = _NOTE_NAMES_CHROMATIC[midi % 12]
    return f"{note_name}{octave}"


# ---------------------------------------------------------------------------
# Frame grouping (pure Python, no librosa)
# ---------------------------------------------------------------------------


def _group_voiced_frames(
    f0_hz: np.ndarray,
    voiced_flag: np.ndarray,
    frame_times: np.ndarray,
    min_duration_sec: float,
) -> list[tuple[int, int]]:
    """Group consecutive voiced frames into (start_frame, end_frame) segments.

    A "segment" is a maximal run of consecutive voiced frames. Gaps between
    voiced frames (unvoiced frames) split the signal into separate notes.

    Segments shorter than min_duration_sec are discarded.

    Args:
        f0_hz: Fundamental frequency per frame (shape: [n_frames]).
               NaN values are treated as unvoiced regardless of voiced_flag.
        voiced_flag: Boolean mask. True = voiced frame (shape: [n_frames]).
        frame_times: Time in seconds for each frame (shape: [n_frames]).
        min_duration_sec: Minimum segment duration to keep.

    Returns:
        List of (start_frame, end_frame) tuples (end_frame is inclusive).
        Sorted by start_frame.
    """
    n_frames = len(f0_hz)
    segments: list[tuple[int, int]] = []

    in_segment = False
    seg_start = 0

    for i in range(n_frames):
        is_voiced = bool(voiced_flag[i]) and not np.isnan(f0_hz[i])

        if is_voiced and not in_segment:
            seg_start = i
            in_segment = True
        elif not is_voiced and in_segment:
            # End of segment at frame i-1
            duration = float(frame_times[i - 1]) - float(frame_times[seg_start])
            if duration >= min_duration_sec:
                segments.append((seg_start, i - 1))
            in_segment = False

    # Close final open segment
    if in_segment:
        duration = float(frame_times[-1]) - float(frame_times[seg_start])
        if duration >= min_duration_sec:
            segments.append((seg_start, n_frames - 1))

    return segments


# ---------------------------------------------------------------------------
# Velocity estimation
# ---------------------------------------------------------------------------


def _estimate_velocity(
    y: np.ndarray,
    sr: int,
    onset_sample: int,
    offset_sample: int,
    librosa: Any,
) -> int:
    """Estimate MIDI velocity from RMS energy of a note segment.

    Maps log-normalized RMS to the range [20, 100] — a musically
    useful range that avoids extremes (too soft to hear, too harsh).

    Args:
        y: Full audio time series
        sr: Sample rate
        onset_sample: Start sample index of the note
        offset_sample: End sample index of the note
        librosa: Injected librosa module

    Returns:
        Integer velocity in [20, 100].
    """
    segment = y[max(0, onset_sample) : min(len(y), offset_sample)]
    if len(segment) == 0:
        return 64  # default middle velocity

    try:
        rms_frames = librosa.feature.rms(y=segment)
        rms_mean = float(np.mean(rms_frames))
    except Exception:
        return 64

    if rms_mean <= 0.0:
        return 20

    # Map log RMS [-3, -0.3] → [20, 100]
    log_rms = math.log10(max(rms_mean, 1e-6))
    log_min, log_max = -3.0, -0.3
    normalized = (log_rms - log_min) / (log_max - log_min)
    velocity = int(round(20.0 + max(0.0, min(1.0, normalized)) * 80.0))
    return max(20, min(100, velocity))


# ---------------------------------------------------------------------------
# Main melody detection
# ---------------------------------------------------------------------------


def detect_melody(
    y: np.ndarray,
    sr: int,
    *,
    librosa: Any,
    fmin: float = FMIN_HZ,
    fmax: float = FMAX_HZ,
    min_duration_sec: float = MIN_NOTE_DURATION_SEC,
) -> list[Note]:
    """Detect melody from monophonic audio using pYIN pitch tracking.

    Pipeline:
        1. librosa.pyin() → (f0_hz, voiced_flag, voiced_probs)
        2. librosa.frames_to_time() → frame onset times in seconds
        3. _group_voiced_frames() → consecutive voiced segments
        4. For each segment:
             a. Dominant pitch = mean of f0 over segment frames (Hz → MIDI)
             b. onset_sec, duration_sec from frame_times
             c. velocity = RMS energy of audio segment
             d. Construct Note object
        5. Return sorted list of Note objects

    Args:
        y: Audio time series (mono, float32).
           Best results with harmonic component from separate_hpss().
        sr: Sample rate in Hz
        librosa: Injected librosa module
        fmin: Minimum pitch frequency in Hz (default: C2 = 65.41 Hz)
        fmax: Maximum pitch frequency in Hz (default: C7 = 2093.0 Hz)
        min_duration_sec: Minimum note length to include (default: 50ms)

    Returns:
        List of Note objects sorted by onset_sec.
        Empty list when:
            - No voiced frames detected (silence, drums-only)
            - pYIN fails (exception caught internally)
            - All detected notes are shorter than min_duration_sec

    Notes:
        - Designed for monophonic sources (lead melody, bass lines).
        - For polyphonic input, returns the dominant pitch per frame.
        - Always run HPSS separation before calling this on mixed audio.
    """
    try:
        f0_hz, voiced_flag, _voiced_probs = librosa.pyin(
            y,
            fmin=fmin,
            fmax=fmax,
            sr=sr,
            hop_length=_HOP_LENGTH,
        )
    except Exception:
        return []

    n_frames = len(f0_hz)
    if n_frames == 0:
        return []

    frame_indices = np.arange(n_frames)
    frame_times = librosa.frames_to_time(frame_indices, sr=sr, hop_length=_HOP_LENGTH)

    segments = _group_voiced_frames(f0_hz, voiced_flag, frame_times, min_duration_sec)

    notes: list[Note] = []
    for start_frame, end_frame in segments:
        # Dominant pitch: mean of voiced Hz values in segment
        segment_f0 = f0_hz[start_frame : end_frame + 1]
        voiced_mask = ~np.isnan(segment_f0)
        if not voiced_mask.any():
            continue

        mean_hz = float(np.mean(segment_f0[voiced_mask]))
        pitch_midi = _hz_to_midi(mean_hz)
        pitch_name = _midi_to_name(pitch_midi)

        onset_sec = float(frame_times[start_frame])
        # Duration: end of last frame to start of first frame
        # Add one frame's worth of time for the duration of the last frame
        one_frame_sec = float(_HOP_LENGTH) / float(sr)
        duration_sec = float(frame_times[end_frame]) - onset_sec + one_frame_sec

        if duration_sec < min_duration_sec:
            continue  # guard against floating-point rounding

        # Velocity from RMS of the audio segment
        onset_sample = int(start_frame * _HOP_LENGTH)
        offset_sample = int((end_frame + 1) * _HOP_LENGTH)
        velocity = _estimate_velocity(y, sr, onset_sample, offset_sample, librosa)

        notes.append(
            Note(
                pitch_midi=pitch_midi,
                pitch_name=pitch_name,
                onset_sec=onset_sec,
                duration_sec=duration_sec,
                velocity=velocity,
            )
        )

    return sorted(notes, key=lambda n: n.onset_sec)

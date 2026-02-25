"""
ingestion/midi_export.py — Convert Note sequences to MIDI files using mido.

This module is the I/O output boundary for the melody pipeline:
    audio → features → melody (core/) → MIDI (ingestion/)

Usage:
    from ingestion.midi_export import notes_to_midi, midi_to_notes
    from core.audio.types import Note

    notes = detect_melody(y_harmonic, sr, librosa=librosa)
    midi = notes_to_midi(notes, bpm=128.0, output_path="melody.mid")

MIDI structure produced:
    Track 0: Tempo meta message + time signature meta message
    Track 1: note_on / note_off events for all notes
    Delta times: time-based (seconds → ticks conversion)
    Type 1 MIDI file (multi-track, synchronous)

Why mido:
    - Pure Python, no compiled audio backend required
    - Direct low-level MIDI message construction
    - Supports both file I/O and in-memory manipulation
    - Standard MIDI 1.0 compliant output
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import mido

from core.audio.types import Note

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_TICKS_PER_BEAT: int = 480
"""Standard MIDI ticks per quarter note. 480 gives 1 ms resolution at 120 BPM."""

MIDI_CHANNEL: int = 0
"""MIDI channel for note events (0-indexed, channel 1 in DAW notation)."""


# ---------------------------------------------------------------------------
# Time conversion utilities
# ---------------------------------------------------------------------------


def _sec_to_ticks(
    seconds: float,
    bpm: float,
    ticks_per_beat: int,
) -> int:
    """Convert a duration in seconds to MIDI ticks.

    Formula: ticks = seconds × (BPM / 60) × ticks_per_beat

    Args:
        seconds: Duration in seconds. Must be ≥ 0.
        bpm: Tempo in beats per minute.
        ticks_per_beat: MIDI resolution (ticks per quarter note).

    Returns:
        Non-negative integer tick count.
    """
    if seconds < 0:
        return 0
    beats_per_sec = bpm / 60.0
    return max(0, round(seconds * beats_per_sec * ticks_per_beat))


def _bpm_to_tempo_us(bpm: float) -> int:
    """Convert BPM to MIDI tempo (microseconds per beat).

    MIDI represents tempo as microseconds per quarter note.
    120 BPM = 500,000 μs/beat.

    Args:
        bpm: Tempo in beats per minute. Must be > 0.

    Returns:
        Tempo in microseconds per beat (integer).
    """
    if bpm <= 0:
        bpm = 120.0
    return max(1, round(60_000_000.0 / bpm))


# ---------------------------------------------------------------------------
# Primary export function
# ---------------------------------------------------------------------------


def notes_to_midi(
    notes: Sequence[Note],
    *,
    bpm: float = 120.0,
    output_path: str | Path | None = None,
    ticks_per_beat: int = DEFAULT_TICKS_PER_BEAT,
) -> mido.MidiFile:
    """Convert a sequence of Note objects to a MIDI file.

    Produces a Type 1 MIDI file with:
        - Track 0: tempo and time signature meta messages
        - Track 1: note_on/note_off events, sorted by absolute tick time

    Delta time encoding:
        MIDI messages use delta times (ticks since last message).
        This function computes absolute tick positions for all events,
        sorts them, then computes deltas from the sorted sequence.

    Args:
        notes: Sequence of Note objects. Must not be empty.
        bpm: Tempo in BPM (default: 120.0).
        output_path: If provided, saves the MIDI file to this path.
                     The path's parent directory must exist.
        ticks_per_beat: MIDI resolution (default: 480, standard).

    Returns:
        mido.MidiFile object. Can be further modified or saved manually.

    Raises:
        ValueError: If notes is empty.
        OSError: If output_path is not writable.
    """
    if not notes:
        raise ValueError("notes sequence must not be empty")

    midi = mido.MidiFile(type=1, ticks_per_beat=ticks_per_beat)

    # Track 0: metadata
    meta_track = mido.MidiTrack()
    midi.tracks.append(meta_track)

    tempo_us = _bpm_to_tempo_us(bpm)
    meta_track.append(mido.MetaMessage("set_tempo", tempo=tempo_us, time=0))
    meta_track.append(
        mido.MetaMessage(
            "time_signature",
            numerator=4,
            denominator=4,
            clocks_per_click=24,
            notated_32nd_notes_per_beat=8,
            time=0,
        )
    )
    meta_track.append(mido.MetaMessage("end_of_track", time=0))

    # Track 1: note events
    note_track = mido.MidiTrack()
    midi.tracks.append(note_track)

    # Build list of (absolute_tick, event_type, pitch, velocity)
    # event_type: 0 = note_on, 1 = note_off (sort so note_off before note_on at same tick)
    events: list[tuple[int, int, int, int]] = []

    for note in notes:
        on_tick = _sec_to_ticks(note.onset_sec, bpm, ticks_per_beat)
        off_tick = _sec_to_ticks(note.onset_sec + note.duration_sec, bpm, ticks_per_beat)

        # Ensure minimum 1 tick duration
        if off_tick <= on_tick:
            off_tick = on_tick + 1

        velocity = max(1, min(127, note.velocity))  # clamp, ensure non-zero for note_on
        events.append((on_tick, 0, note.pitch_midi, velocity))    # note_on
        events.append((off_tick, 1, note.pitch_midi, 0))          # note_off (velocity=0)

    # Sort: by tick, then note_off before note_on (ensures clean note boundaries)
    events.sort(key=lambda e: (e[0], e[1]))

    # Convert to delta-time MIDI messages
    current_tick = 0
    for abs_tick, event_type, pitch, velocity in events:
        delta = abs_tick - current_tick
        current_tick = abs_tick

        if event_type == 0:
            note_track.append(
                mido.Message(
                    "note_on",
                    channel=MIDI_CHANNEL,
                    note=pitch,
                    velocity=velocity,
                    time=delta,
                )
            )
        else:
            note_track.append(
                mido.Message(
                    "note_off",
                    channel=MIDI_CHANNEL,
                    note=pitch,
                    velocity=0,
                    time=delta,
                )
            )

    note_track.append(mido.MetaMessage("end_of_track", time=0))

    if output_path is not None:
        midi.save(str(output_path))

    return midi


# ---------------------------------------------------------------------------
# Round-trip parser (MIDI → Notes)
# ---------------------------------------------------------------------------


def midi_to_notes(midi_file: mido.MidiFile) -> list[Note]:
    """Parse a MIDI file back into Note objects.

    Useful for round-trip testing and verification.

    Parsing logic:
        - Iterates Track 1 (note track)
        - Accumulates delta times to compute absolute tick positions
        - Matches note_on events to subsequent note_off events for the same pitch
        - Converts tick positions back to seconds using tempo from Track 0

    Args:
        midi_file: A mido.MidiFile object.

    Returns:
        List of Note objects sorted by onset_sec.
        Empty list if no note events found.
    """
    from core.audio.melody import _midi_to_name

    # Extract tempo from Track 0 (default 120 BPM)
    tempo_us = 500_000  # default
    if midi_file.tracks:
        for msg in midi_file.tracks[0]:
            if msg.type == "set_tempo":
                tempo_us = msg.tempo
                break

    bpm = 60_000_000.0 / tempo_us
    ticks_per_beat = midi_file.ticks_per_beat

    def ticks_to_sec(ticks: int) -> float:
        return ticks / ticks_per_beat / (bpm / 60.0)

    # Process note track (index 1)
    if len(midi_file.tracks) < 2:
        return []

    note_track = midi_file.tracks[1]
    abs_tick = 0
    # pitch → (on_tick, velocity)
    pending: dict[int, tuple[int, int]] = {}
    notes: list[Note] = []

    for msg in note_track:
        abs_tick += msg.time

        if msg.type == "note_on" and msg.velocity > 0:
            pending[msg.note] = (abs_tick, msg.velocity)

        elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
            if msg.note in pending:
                on_tick, velocity = pending.pop(msg.note)
                onset_sec = ticks_to_sec(on_tick)
                duration_sec = ticks_to_sec(abs_tick - on_tick)
                pitch_name = _midi_to_name(msg.note)
                notes.append(
                    Note(
                        pitch_midi=msg.note,
                        pitch_name=pitch_name,
                        onset_sec=onset_sec,
                        duration_sec=max(0.001, duration_sec),
                        velocity=velocity,
                    )
                )

    return sorted(notes, key=lambda n: n.onset_sec)

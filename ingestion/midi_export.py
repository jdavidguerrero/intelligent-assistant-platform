"""
ingestion/midi_export.py — Convert Note sequences, chord progressions,
bass lines, and drum patterns to MIDI files using mido.

This module is the I/O output boundary for the full music generation pipeline:
    audio → melody (core/) → notes_to_midi
    chords (core/music_theory/) → chords_to_midi
    bassline (core/music_theory/) → bassline_to_midi
    drum pattern (core/music_theory/) → pattern_to_midi

Usage:
    from ingestion.midi_export import notes_to_midi, chords_to_midi, \
        bassline_to_midi, pattern_to_midi

MIDI structure:
    notes_to_midi:      Type 1, Track 0=meta, Track 1=notes
    chords_to_midi:     Type 1, Track 0=meta, Track 1=chords (all voices)
    bassline_to_midi:   Type 1, Track 0=meta, Track 1=bass (channel 0)
    pattern_to_midi:    Type 1, Track 0=meta, Track N=per-instrument drums
                        Drum instruments use channel 9 (GM standard)

GM drum note mapping (channel 9):
    kick=36, snare=38, clap=39, hihat_c=42, hihat_o=46

Why step-based timing (chords/bass/drums):
    The 16-step grid maps cleanly to MIDI ticks via:
        ticks_per_step = ticks_per_beat / 4   (16th note = quarter / 4)
    This is exact and avoids floating-point drift from seconds → ticks.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import mido

from core.audio.types import Note
from core.music_theory.types import BassNote, DrumPattern, VoicingResult

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_TICKS_PER_BEAT: int = 480
"""Standard MIDI ticks per quarter note. 480 gives 1 ms resolution at 120 BPM."""

MIDI_CHANNEL: int = 0
"""MIDI channel for melodic/harmonic note events (0-indexed = channel 1 in DAW)."""

DRUM_CHANNEL: int = 9
"""GM standard MIDI channel for percussion (0-indexed = channel 10 in DAW)."""

# GM General MIDI drum note assignments (channel 9)
GM_DRUM_NOTES: dict[str, int] = {
    "kick": 36,  # Bass Drum 1
    "snare": 38,  # Acoustic Snare
    "clap": 39,  # Hand Clap
    "hihat_c": 42,  # Closed Hi-Hat
    "hihat_o": 46,  # Open Hi-Hat
}

_STEPS_PER_BEAT: int = 4  # 4 sixteenth notes per quarter note beat


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
        events.append((on_tick, 0, note.pitch_midi, velocity))  # note_on
        events.append((off_tick, 1, note.pitch_midi, 0))  # note_off (velocity=0)

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


# ---------------------------------------------------------------------------
# Step-grid time helper
# ---------------------------------------------------------------------------


def _step_to_ticks(step: int, ticks_per_beat: int) -> int:
    """Convert a 16-step grid position to MIDI ticks.

    One 16th-note step = ticks_per_beat / 4.

    Args:
        step:           Grid position (0-based, multiples of 1/16 note).
        ticks_per_beat: MIDI ticks per quarter note.

    Returns:
        Absolute tick position from start of bar.
    """
    return step * (ticks_per_beat // _STEPS_PER_BEAT)


# ---------------------------------------------------------------------------
# Chord MIDI export
# ---------------------------------------------------------------------------


def chords_to_midi(
    voicing_result: VoicingResult,
    *,
    bpm: float = 120.0,
    bars_per_chord: int = 1,
    output_path: str | Path | None = None,
    ticks_per_beat: int = DEFAULT_TICKS_PER_BEAT,
) -> mido.MidiFile:
    """Convert a VoicingResult (chord sequence) to a MIDI file.

    Each chord occupies `bars_per_chord` bars. All notes of the chord
    sound simultaneously for the full chord duration.

    MIDI structure:
        Track 0: Tempo + time signature metadata
        Track 1: Chord note events on channel 0

    Args:
        voicing_result: Output of melody_to_chords() or suggest_progression().
        bpm:            Tempo in BPM.
        bars_per_chord: How many bars each chord lasts (default 1).
        output_path:    If provided, saves the file at this path.
        ticks_per_beat: MIDI resolution (default 480).

    Returns:
        mido.MidiFile ready for playback or further editing.

    Raises:
        ValueError: If voicing_result has no chords.
    """
    if not voicing_result.chords:
        raise ValueError("voicing_result.chords must not be empty")

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

    # Track 1: chord note events
    chord_track = mido.MidiTrack()
    midi.tracks.append(chord_track)

    ticks_per_bar = ticks_per_beat * 4  # 4/4 time
    chord_duration_ticks = bars_per_chord * ticks_per_bar

    events: list[tuple[int, int, int, int]] = []  # (abs_tick, type, pitch, velocity)

    for chord_idx, chord in enumerate(voicing_result.chords):
        on_tick = chord_idx * chord_duration_ticks
        off_tick = on_tick + chord_duration_ticks - 1  # -1 tick gap between chords

        for pitch in chord.midi_notes:
            velocity = 80
            events.append((on_tick, 0, pitch, velocity))
            events.append((off_tick, 1, pitch, 0))

    events.sort(key=lambda e: (e[0], e[1]))

    current_tick = 0
    for abs_tick, event_type, pitch, velocity in events:
        delta = abs_tick - current_tick
        current_tick = abs_tick
        if event_type == 0:
            chord_track.append(
                mido.Message(
                    "note_on", channel=MIDI_CHANNEL, note=pitch, velocity=velocity, time=delta
                )
            )
        else:
            chord_track.append(
                mido.Message("note_off", channel=MIDI_CHANNEL, note=pitch, velocity=0, time=delta)
            )

    chord_track.append(mido.MetaMessage("end_of_track", time=0))

    if output_path is not None:
        midi.save(str(output_path))

    return midi


# ---------------------------------------------------------------------------
# Bass line MIDI export
# ---------------------------------------------------------------------------


def bassline_to_midi(
    bass_notes: Sequence[BassNote],
    *,
    bpm: float = 120.0,
    output_path: str | Path | None = None,
    ticks_per_beat: int = DEFAULT_TICKS_PER_BEAT,
) -> mido.MidiFile:
    """Convert a sequence of BassNote objects to a MIDI file.

    BassNote step positions are converted to tick positions using the
    16-step grid: step_ticks = step × (ticks_per_beat / 4).

    MIDI structure:
        Track 0: Tempo + time signature metadata
        Track 1: Bass note events on channel 0

    Args:
        bass_notes:     Sequence of BassNote objects from generate_bassline().
        bpm:            Tempo in BPM.
        output_path:    If provided, saves the file at this path.
        ticks_per_beat: MIDI resolution (default 480).

    Returns:
        mido.MidiFile object.

    Raises:
        ValueError: If bass_notes is empty.
    """
    if not bass_notes:
        raise ValueError("bass_notes sequence must not be empty")

    midi = mido.MidiFile(type=1, ticks_per_beat=ticks_per_beat)

    meta_track = mido.MidiTrack()
    midi.tracks.append(meta_track)
    meta_track.append(mido.MetaMessage("set_tempo", tempo=_bpm_to_tempo_us(bpm), time=0))
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

    bass_track = mido.MidiTrack()
    midi.tracks.append(bass_track)

    ticks_per_step = ticks_per_beat // _STEPS_PER_BEAT  # = 120 at 480 tpb
    ticks_per_bar = ticks_per_beat * 4

    events: list[tuple[int, int, int, int]] = []

    for note in bass_notes:
        bar_start_tick = note.bar * ticks_per_bar
        on_tick = bar_start_tick + note.step * ticks_per_step
        off_tick = on_tick + note.duration_steps * ticks_per_step - 1
        off_tick = max(off_tick, on_tick + 1)  # minimum 1 tick duration

        events.append((on_tick, 0, note.pitch_midi, note.velocity))
        events.append((off_tick, 1, note.pitch_midi, 0))

    events.sort(key=lambda e: (e[0], e[1]))

    current_tick = 0
    for abs_tick, event_type, pitch, velocity in events:
        delta = abs_tick - current_tick
        current_tick = abs_tick
        if event_type == 0:
            bass_track.append(
                mido.Message(
                    "note_on", channel=MIDI_CHANNEL, note=pitch, velocity=velocity, time=delta
                )
            )
        else:
            bass_track.append(
                mido.Message("note_off", channel=MIDI_CHANNEL, note=pitch, velocity=0, time=delta)
            )

    bass_track.append(mido.MetaMessage("end_of_track", time=0))

    if output_path is not None:
        midi.save(str(output_path))

    return midi


# ---------------------------------------------------------------------------
# Drum pattern MIDI export
# ---------------------------------------------------------------------------


def pattern_to_midi(
    pattern: DrumPattern,
    *,
    output_path: str | Path | None = None,
    ticks_per_beat: int = DEFAULT_TICKS_PER_BEAT,
) -> mido.MidiFile:
    """Convert a DrumPattern to a MIDI file using GM drum channel 9.

    Each instrument in the pattern maps to a GM drum note number
    (kick=36, snare=38, clap=39, hihat_c=42, hihat_o=46).
    All drum events are placed on MIDI channel 9 (GM standard percussion).

    MIDI structure:
        Track 0: Tempo + time signature metadata
        Track 1: All drum hit events on channel 9

    Args:
        pattern:        DrumPattern from generate_pattern().
        output_path:    If provided, saves the file at this path.
        ticks_per_beat: MIDI resolution (default 480).

    Returns:
        mido.MidiFile object.

    Raises:
        ValueError: If pattern has no hits.
    """
    if not pattern.hits:
        raise ValueError("DrumPattern.hits must not be empty")

    midi = mido.MidiFile(type=1, ticks_per_beat=ticks_per_beat)

    meta_track = mido.MidiTrack()
    midi.tracks.append(meta_track)
    meta_track.append(mido.MetaMessage("set_tempo", tempo=_bpm_to_tempo_us(pattern.bpm), time=0))
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

    drum_track = mido.MidiTrack()
    midi.tracks.append(drum_track)

    ticks_per_step = ticks_per_beat // _STEPS_PER_BEAT
    ticks_per_bar = ticks_per_beat * 4
    # Short percussion notes: 1 step duration
    note_duration_ticks = ticks_per_step - 1

    events: list[tuple[int, int, int, int]] = []

    for hit in pattern.hits:
        midi_note = GM_DRUM_NOTES.get(hit.instrument)
        if midi_note is None:
            continue  # skip unknown instruments

        bar_start_tick = hit.bar * ticks_per_bar
        on_tick = bar_start_tick + hit.step * ticks_per_step
        off_tick = on_tick + note_duration_ticks
        off_tick = max(off_tick, on_tick + 1)

        events.append((on_tick, 0, midi_note, hit.velocity))
        events.append((off_tick, 1, midi_note, 0))

    events.sort(key=lambda e: (e[0], e[1]))

    current_tick = 0
    for abs_tick, event_type, midi_note, velocity in events:
        delta = abs_tick - current_tick
        current_tick = abs_tick
        if event_type == 0:
            drum_track.append(
                mido.Message(
                    "note_on", channel=DRUM_CHANNEL, note=midi_note, velocity=velocity, time=delta
                )
            )
        else:
            drum_track.append(
                mido.Message(
                    "note_off", channel=DRUM_CHANNEL, note=midi_note, velocity=0, time=delta
                )
            )

    drum_track.append(mido.MetaMessage("end_of_track", time=0))

    if output_path is not None:
        midi.save(str(output_path))

    return midi

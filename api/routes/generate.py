"""
api/routes/generate.py — Music generation endpoints.

Endpoints:
    POST /generate/chords-from-text — Chord progression from key + genre + mood
    POST /generate/bass             — Bass line for a given key + genre
    POST /generate/drums            — Drum pattern for a given genre + energy
    POST /generate/full             — Complete arrangement from audio file

All endpoints delegate to AudioAnalysisEngine or directly to core generators.
No LLM, no database — pure music theory computation.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from api.schemas.music import (
    BassGenerateRequest,
    BassGenerateResponse,
    BassNoteOut,
    ChordOut,
    ChordsFromTextRequest,
    ChordsFromTextResponse,
    DrumHitOut,
    DrumsGenerateRequest,
    DrumsGenerateResponse,
    FullArrangementRequest,
    FullArrangementResponse,
    KeyOut,
)
from ingestion.audio_engine import AudioAnalysisEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/generate", tags=["generate"])

_engine: AudioAnalysisEngine | None = None


def _get_engine() -> AudioAnalysisEngine:
    global _engine
    if _engine is None:
        _engine = AudioAnalysisEngine()
    return _engine


def _parse_key(key: str) -> tuple[str, str]:
    """Parse 'A minor', 'C# major', etc. Returns (root, mode)."""
    parts = key.strip().split(maxsplit=1)
    if len(parts) < 2:
        raise ValueError(f"Cannot parse key {key!r}. Use 'Root mode' format, e.g. 'A minor'.")
    root = parts[0]
    mode_raw = parts[1].lower()
    aliases = {
        "minor": "natural minor",
        "natural minor": "natural minor",
        "major": "major",
        "dorian": "dorian",
        "harmonic minor": "harmonic minor",
    }
    mode = aliases.get(mode_raw, mode_raw)
    return root, mode


# ---------------------------------------------------------------------------
# POST /generate/chords-from-text
# ---------------------------------------------------------------------------


@router.post("/chords-from-text", response_model=ChordsFromTextResponse)
def generate_chords_from_text(request: ChordsFromTextRequest) -> ChordsFromTextResponse:
    """Generate a diatonic chord progression from a key, genre, and mood.

    Uses the YAML genre template engine from core/music_theory/harmony.py
    to produce a harmonically coherent progression.

    Args:
        request: ChordsFromTextRequest with key, genre, bars, mood.

    Returns:
        ChordsFromTextResponse with chord list, roman labels, and progression summary.

    Raises:
        422: Invalid key format or unsupported genre.
    """
    try:
        root, _mode = _parse_key(request.key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        from core.music_theory.harmony import suggest_progression

        voicing = suggest_progression(root, genre=request.genre, bars=request.bars)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    chords_out = [
        ChordOut(
            root=c.root,
            quality=c.quality,
            name=c.name,
            roman=c.roman,
            degree=c.degree,
            midi_notes=list(c.midi_notes),
        )
        for c in voicing.chords
    ]

    return ChordsFromTextResponse(
        key_root=voicing.key_root,
        key_mode=voicing.key_mode,
        genre=voicing.genre,
        bars=voicing.bars,
        chords=chords_out,
        progression_label=voicing.progression_label,
        roman_labels=list(voicing.roman_labels)
        if voicing.roman_labels
        else [c.roman for c in voicing.chords],
    )


# ---------------------------------------------------------------------------
# POST /generate/bass
# ---------------------------------------------------------------------------


@router.post("/bass", response_model=BassGenerateResponse)
def generate_bass(request: BassGenerateRequest) -> BassGenerateResponse:
    """Generate a bass line for a given key and genre.

    Internally generates a chord progression first (required by the bass
    engine), then produces a 16-step grid bass line.

    Args:
        request: BassGenerateRequest with key, genre, bars, humanize, seed.

    Returns:
        BassGenerateResponse with note list and metadata.

    Raises:
        422: Invalid key or unsupported genre.
    """
    try:
        root, _mode = _parse_key(request.key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        from core.music_theory.harmony import suggest_progression

        voicing = suggest_progression(root, genre=request.genre, bars=request.bars)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    engine = _get_engine()
    bass = engine.generate_bass(
        voicing.chords,
        genre=request.genre,
        bars=request.bars,
        humanize=request.humanize,
        seed=request.seed,
    )

    notes_out = [
        BassNoteOut(
            pitch_midi=n.pitch_midi,
            step=n.step,
            duration_steps=n.duration_steps,
            velocity=n.velocity,
            bar=n.bar,
            tick_offset=n.tick_offset,
        )
        for n in bass
    ]

    return BassGenerateResponse(
        genre=request.genre,
        bars=request.bars,
        bpm=120.0,
        notes=notes_out,
        note_count=len(notes_out),
    )


# ---------------------------------------------------------------------------
# POST /generate/drums
# ---------------------------------------------------------------------------


@router.post("/drums", response_model=DrumsGenerateResponse)
def generate_drums(request: DrumsGenerateRequest) -> DrumsGenerateResponse:
    """Generate a drum pattern for a given genre and energy level.

    Uses genre YAML template and energy layer system to build a dynamic
    16-step pattern across kick, snare, clap, and hi-hat instruments.

    Args:
        request: DrumsGenerateRequest with genre, bars, energy, bpm, humanize, seed.

    Returns:
        DrumsGenerateResponse with hit list and metadata.

    Raises:
        422: Unsupported genre.
    """
    engine = _get_engine()
    try:
        pattern = engine.generate_drums(
            genre=request.genre,
            energy=request.energy,
            bars=request.bars,
            bpm=request.bpm,
            humanize=request.humanize,
            seed=request.seed,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    hits_out = [
        DrumHitOut(
            instrument=h.instrument,
            step=h.step,
            velocity=h.velocity,
            bar=h.bar,
            tick_offset=h.tick_offset,
        )
        for h in pattern.hits
    ]

    return DrumsGenerateResponse(
        genre=request.genre,
        bars=request.bars,
        bpm=request.bpm,
        energy=request.energy,
        hits=hits_out,
        hit_count=len(hits_out),
    )


# ---------------------------------------------------------------------------
# POST /generate/full
# ---------------------------------------------------------------------------


@router.post("/full", response_model=FullArrangementResponse)
def generate_full(request: FullArrangementRequest) -> FullArrangementResponse:
    """Run the complete audio→MIDI arrangement pipeline.

    Loads the audio file, analyses it (BPM, key, melody), harmonizes
    the melody into chords, generates bass and drums, and optionally
    saves MIDI files to the specified output directory.

    Args:
        request: FullArrangementRequest with file_path, genre, bars, etc.

    Returns:
        FullArrangementResponse with all pipeline outputs.

    Raises:
        422: File not found, unsupported format, or invalid parameters.
        500: Audio analysis or generation failure.
    """
    engine = _get_engine()
    try:
        composition = engine.full_pipeline(
            request.file_path,
            genre=request.genre,
            bars=request.bars,
            bpm=request.bpm,
            energy=request.energy,
            humanize=request.humanize,
            seed=request.seed,
            output_dir=request.output_dir,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.error("Full pipeline failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {exc}") from exc

    key_out = KeyOut(
        root=composition.analysis.key.root,
        mode=composition.analysis.key.mode,
        confidence=composition.analysis.key.confidence,
        label=composition.analysis.key.label,
    )

    chords_out = [
        ChordOut(
            root=c.root,
            quality=c.quality,
            name=c.name,
            roman=c.roman,
            degree=c.degree,
            midi_notes=list(c.midi_notes),
        )
        for c in composition.voicing.chords
    ]

    return FullArrangementResponse(
        bpm=composition.bpm,
        genre=composition.genre,
        bars=composition.bars,
        key=key_out,
        energy=composition.analysis.energy,
        chords=chords_out,
        progression_label=composition.voicing.progression_label,
        bass_note_count=len(composition.bass_notes),
        drum_hit_count=len(composition.drum_pattern.hits),
        midi_paths=composition.midi_paths,
        processing_time_ms=composition.processing_time_ms,
        melody_note_count=len(composition.melody_notes),
    )

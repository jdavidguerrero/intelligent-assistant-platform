"""
api/routes/analyze.py — Audio analysis endpoints.

Endpoints:
    POST /analyze/sample  — Full audio feature extraction (BPM, key, energy, optional melody)
    POST /analyze/melody  — Melody-only detection using pYIN

Both endpoints accept a file path on the server filesystem and delegate
to AudioAnalysisEngine in ingestion/audio_engine.py.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from api.schemas.music import (
    AudioAnalyzeRequest,
    AudioAnalyzeResponse,
    KeyOut,
    MelodyDetectRequest,
    MelodyDetectResponse,
    NoteOut,
)
from ingestion.audio_engine import AudioAnalysisEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analyze", tags=["analyze"])

# Shared engine instance — librosa imported lazily on first request
_engine: AudioAnalysisEngine | None = None


def _get_engine() -> AudioAnalysisEngine:
    global _engine
    if _engine is None:
        _engine = AudioAnalysisEngine()
    return _engine


# ---------------------------------------------------------------------------
# POST /analyze/sample
# ---------------------------------------------------------------------------


@router.post("/sample", response_model=AudioAnalyzeResponse)
def analyze_sample(request: AudioAnalyzeRequest) -> AudioAnalyzeResponse:
    """Extract BPM, musical key, energy, spectral features, and optionally melody.

    Loads the audio file at `file_path` (server-side path), runs the full
    feature extraction pipeline, and returns structured analysis data.

    Args:
        request: AudioAnalyzeRequest with file_path, duration, include_melody.

    Returns:
        AudioAnalyzeResponse with BPM, key, energy, and optional note list.

    Raises:
        422: file_path does not exist or extension not supported.
        500: Audio decoding or analysis failure.
    """
    engine = _get_engine()
    try:
        analysis = engine.analyze_sample(
            request.file_path,
            duration=request.duration,
            include_melody=request.include_melody,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.error("Audio analysis failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Audio analysis failed: {exc}") from exc

    key_out = KeyOut(
        root=analysis.key.root,
        mode=analysis.key.mode,
        confidence=analysis.key.confidence,
        label=analysis.key.label,
    )

    notes_out = [
        NoteOut(
            pitch_midi=n.pitch_midi,
            pitch_name=n.pitch_name,
            onset_sec=n.onset_sec,
            duration_sec=n.duration_sec,
            velocity=n.velocity,
        )
        for n in analysis.notes
    ]

    spectral_out = None
    if analysis.spectral is not None:
        spectral_out = {
            "chroma": list(analysis.spectral.chroma),
            "rms": analysis.spectral.rms,
            "tempo": analysis.spectral.tempo,
            "onset_count": len(analysis.spectral.onsets_sec),
            "beat_count": len(analysis.spectral.beat_frames),
        }

    return AudioAnalyzeResponse(
        bpm=analysis.bpm,
        key=key_out,
        energy=analysis.energy,
        duration_sec=analysis.duration_sec,
        sample_rate=analysis.sample_rate,
        notes=notes_out,
        spectral=spectral_out,
    )


# ---------------------------------------------------------------------------
# POST /analyze/melody
# ---------------------------------------------------------------------------


@router.post("/melody", response_model=MelodyDetectResponse)
def analyze_melody(request: MelodyDetectRequest) -> MelodyDetectResponse:
    """Detect melody notes from a monophonic audio source using pYIN.

    Runs HPSS separation first, then applies probabilistic YIN pitch
    tracking on the harmonic component to extract discrete notes.

    Args:
        request: MelodyDetectRequest with file_path and duration.

    Returns:
        MelodyDetectResponse with sorted list of Note objects.

    Raises:
        422: File not found or unsupported format.
        500: Audio decoding or melody detection failure.
    """
    engine = _get_engine()
    try:
        notes = engine.extract_melody(
            request.file_path,
            duration=request.duration,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.error("Melody detection failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Melody detection failed: {exc}") from exc

    notes_out = [
        NoteOut(
            pitch_midi=n.pitch_midi,
            pitch_name=n.pitch_name,
            onset_sec=n.onset_sec,
            duration_sec=n.duration_sec,
            velocity=n.velocity,
        )
        for n in notes
    ]

    # Estimate audio duration from last note offset
    duration_sec = 0.0
    if notes:
        last = notes[-1]
        duration_sec = last.onset_sec + last.duration_sec

    return MelodyDetectResponse(
        notes=notes_out,
        note_count=len(notes_out),
        duration_sec=duration_sec,
    )

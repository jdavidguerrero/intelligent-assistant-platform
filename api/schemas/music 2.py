"""
api/schemas/music.py — Pydantic request/response schemas for music endpoints.

Covers:
    /analyze/sample   — AudioAnalyzeRequest / AudioAnalyzeResponse
    /analyze/melody   — MelodyDetectRequest / MelodyDetectResponse
    /generate/chords-from-text  — ChordsFromTextRequest / ChordsFromTextResponse
    /generate/bass    — BassGenerateRequest / BassGenerateResponse
    /generate/drums   — DrumsGenerateRequest / DrumsGenerateResponse
    /generate/full    — FullArrangementRequest / FullArrangementResponse
"""

from typing import Any

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Shared sub-schemas
# ---------------------------------------------------------------------------

VALID_GENRES: frozenset[str] = frozenset(
    {"organic house", "deep house", "melodic techno", "progressive house", "afro house"}
)


class NoteOut(BaseModel):
    """A single detected melody note."""

    pitch_midi: int = Field(..., ge=0, le=127)
    pitch_name: str
    onset_sec: float = Field(..., ge=0.0)
    duration_sec: float = Field(..., gt=0.0)
    velocity: int = Field(..., ge=0, le=127)


class KeyOut(BaseModel):
    """Musical key detection result."""

    root: str
    mode: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    label: str


class ChordOut(BaseModel):
    """A single chord in a progression."""

    root: str
    quality: str
    name: str
    roman: str
    degree: int
    midi_notes: list[int]


class BassNoteOut(BaseModel):
    """A single bass note on the 16-step grid."""

    pitch_midi: int = Field(..., ge=0, le=127)
    step: int = Field(..., ge=0, le=15)
    duration_steps: int = Field(..., ge=1, le=16)
    velocity: int = Field(..., ge=0, le=127)
    bar: int = Field(..., ge=0)
    tick_offset: int = 0


class DrumHitOut(BaseModel):
    """A single drum hit on the 16-step grid."""

    instrument: str
    step: int = Field(..., ge=0, le=15)
    velocity: int = Field(..., ge=0, le=127)
    bar: int = Field(..., ge=0)
    tick_offset: int = 0


# ---------------------------------------------------------------------------
# /analyze/sample
# ---------------------------------------------------------------------------


class AudioAnalyzeRequest(BaseModel):
    """Request body for POST /analyze/sample."""

    file_path: str = Field(
        ...,
        description="Absolute path to audio file on the server filesystem.",
    )
    duration: float = Field(
        default=30.0,
        gt=0.0,
        le=300.0,
        description="Maximum seconds to analyse (default 30s).",
    )
    include_melody: bool = Field(
        default=False,
        description="If True, run pYIN melody detection. Slower but returns Note list.",
    )


class AudioAnalyzeResponse(BaseModel):
    """Response body for POST /analyze/sample."""

    bpm: float
    key: KeyOut
    energy: int = Field(..., ge=0, le=10)
    duration_sec: float
    sample_rate: int
    notes: list[NoteOut] = Field(default_factory=list)
    spectral: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# /analyze/melody
# ---------------------------------------------------------------------------


class MelodyDetectRequest(BaseModel):
    """Request body for POST /analyze/melody."""

    file_path: str = Field(
        ...,
        description="Absolute path to audio file on the server filesystem.",
    )
    duration: float = Field(
        default=30.0,
        gt=0.0,
        le=300.0,
        description="Maximum seconds to analyse.",
    )


class MelodyDetectResponse(BaseModel):
    """Response body for POST /analyze/melody."""

    notes: list[NoteOut]
    note_count: int
    duration_sec: float


# ---------------------------------------------------------------------------
# /generate/chords-from-text
# ---------------------------------------------------------------------------


class ChordsFromTextRequest(BaseModel):
    """Request body for POST /generate/chords-from-text."""

    key: str = Field(
        ...,
        max_length=50,
        description="Key in 'Root mode' format, e.g. 'A minor', 'C# major'.",
    )
    genre: str = Field(
        default="organic house",
        description=f"Genre template. Supported: {', '.join(sorted(VALID_GENRES))}.",
    )
    bars: int = Field(default=4, ge=1, le=16)
    mood: str = Field(default="melancholic", max_length=30)

    @field_validator("genre")
    @classmethod
    def validate_genre(cls, v: str) -> str:
        if v not in VALID_GENRES:
            raise ValueError(f"genre must be one of: {', '.join(sorted(VALID_GENRES))}")
        return v


class ChordsFromTextResponse(BaseModel):
    """Response body for POST /generate/chords-from-text."""

    key_root: str
    key_mode: str
    genre: str
    bars: int
    chords: list[ChordOut]
    progression_label: str
    roman_labels: list[str]


# ---------------------------------------------------------------------------
# /generate/bass
# ---------------------------------------------------------------------------


class BassGenerateRequest(BaseModel):
    """Request body for POST /generate/bass."""

    key: str = Field(
        ...,
        max_length=50,
        description="Key in 'Root mode' format.",
    )
    genre: str = Field(default="organic house")
    bars: int = Field(default=4, ge=1, le=16)
    humanize: bool = Field(default=True)
    seed: int | None = Field(default=None)

    @field_validator("genre")
    @classmethod
    def validate_genre(cls, v: str) -> str:
        if v not in VALID_GENRES:
            raise ValueError(f"genre must be one of: {', '.join(sorted(VALID_GENRES))}")
        return v


class BassGenerateResponse(BaseModel):
    """Response body for POST /generate/bass."""

    genre: str
    bars: int
    bpm: float
    notes: list[BassNoteOut]
    note_count: int


# ---------------------------------------------------------------------------
# /generate/drums
# ---------------------------------------------------------------------------


class DrumsGenerateRequest(BaseModel):
    """Request body for POST /generate/drums."""

    genre: str = Field(default="organic house")
    bars: int = Field(default=4, ge=1, le=16)
    energy: int = Field(default=7, ge=0, le=10)
    bpm: float = Field(default=120.0, gt=0.0, le=300.0)
    humanize: bool = Field(default=True)
    seed: int | None = Field(default=None)

    @field_validator("genre")
    @classmethod
    def validate_genre(cls, v: str) -> str:
        if v not in VALID_GENRES:
            raise ValueError(f"genre must be one of: {', '.join(sorted(VALID_GENRES))}")
        return v


class DrumsGenerateResponse(BaseModel):
    """Response body for POST /generate/drums."""

    genre: str
    bars: int
    bpm: float
    energy: int
    hits: list[DrumHitOut]
    hit_count: int


# ---------------------------------------------------------------------------
# /generate/full
# ---------------------------------------------------------------------------


class FullArrangementRequest(BaseModel):
    """Request body for POST /generate/full."""

    file_path: str = Field(
        ...,
        description="Absolute path to audio file to analyse and harmonize.",
    )
    genre: str = Field(default="organic house")
    bars: int = Field(default=4, ge=1, le=16)
    bpm: float | None = Field(default=None, gt=0.0, le=300.0)
    energy: int | None = Field(default=None, ge=0, le=10)
    humanize: bool = Field(default=True)
    seed: int | None = Field(default=None)
    output_dir: str | None = Field(
        default=None,
        description="If set, save MIDI files to this directory.",
    )

    @field_validator("genre")
    @classmethod
    def validate_genre(cls, v: str) -> str:
        if v not in VALID_GENRES:
            raise ValueError(f"genre must be one of: {', '.join(sorted(VALID_GENRES))}")
        return v


class FullArrangementResponse(BaseModel):
    """Response body for POST /generate/full."""

    bpm: float
    genre: str
    bars: int
    key: KeyOut
    energy: int
    chords: list[ChordOut]
    progression_label: str
    bass_note_count: int
    drum_hit_count: int
    midi_paths: dict[str, str]
    processing_time_ms: float
    melody_note_count: int

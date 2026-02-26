"""
api/schemas/mix.py — Pydantic request models for the /mix endpoints.

All fields use snake_case. Default values match MixAnalysisEngine defaults.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

_SUPPORTED_GENRES = (
    "organic house",
    "melodic techno",
    "deep house",
    "progressive house",
    "afro house",
)


class MixAnalyzeRequest(BaseModel):
    """POST /mix/analyze — full mix analysis."""

    file_path: str = Field(..., description="Absolute path to audio file on server filesystem")
    genre: str = Field("organic house", description=f"Genre: {', '.join(_SUPPORTED_GENRES)}")
    duration: float = Field(180.0, gt=0, description="Max seconds of audio to load")


class MixCompareRequest(BaseModel):
    """POST /mix/compare — compare track vs one or more references."""

    file_path: str = Field(..., description="Absolute path to track under review")
    reference_paths: list[str] = Field(
        ...,
        min_length=1,
        description="Absolute paths to commercial reference tracks (1 or more)",
    )
    genre: str = Field("organic house", description=f"Genre: {', '.join(_SUPPORTED_GENRES)}")
    duration: float = Field(180.0, gt=0, description="Max seconds to load from each file")


class MixMasterRequest(BaseModel):
    """POST /mix/master — mastering-grade analysis."""

    file_path: str = Field(..., description="Absolute path to audio file on server filesystem")
    genre: str = Field("organic house", description=f"Genre: {', '.join(_SUPPORTED_GENRES)}")
    duration: float = Field(180.0, gt=0, description="Max seconds of audio to load")


class MixReportRequest(BaseModel):
    """POST /mix/report — full diagnostic report (mix + optional master + optional refs)."""

    file_path: str = Field(..., description="Absolute path to audio file on server filesystem")
    genre: str = Field("organic house", description=f"Genre: {', '.join(_SUPPORTED_GENRES)}")
    reference_paths: list[str] = Field(
        default_factory=list,
        description="Optional reference tracks for A/B comparison",
    )
    include_master: bool = Field(
        True, description="Run mastering analysis (adds readiness section)"
    )
    duration: float = Field(180.0, gt=0, description="Max seconds of audio to load")


class MixCalibrateRequest(BaseModel):
    """POST /mix/calibrate — derive genre targets from reference analysis."""

    reference_paths: list[str] = Field(
        ...,
        min_length=2,
        description="Absolute paths to reference tracks (minimum 2, recommended 10+)",
    )
    genre: str = Field(..., description=f"Target genre: {', '.join(_SUPPORTED_GENRES)}")
    duration: float = Field(180.0, gt=0, description="Max seconds to load from each reference")

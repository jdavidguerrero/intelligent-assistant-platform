"""
core/mix_analysis — Automated mix analysis engine.

Provides pure DSP functions for analysing the spectral balance, stereo image,
dynamics, transients, and common mix problems of an audio signal.

All functions are pure: numpy arrays (y, sr) in → frozen dataclasses out.
No file I/O in this package (audio loading lives in ingestion/audio_loader.py).

Architecture note:
    scipy and numpy are pure computation libraries (no I/O, no side effects).
    Their use here mirrors tiktoken's use in core/chunking.py.

Public API:
    Types:      FrequencyProfile, StereoImage, DynamicProfile, TransientProfile,
                MixProblem, MixAnalysis, BandProfile
    Spectral:   analyze_frequency_balance
    Stereo:     analyze_stereo_image
    Dynamics:   analyze_dynamics
    Transients: analyze_transients
    Problems:   detect_mix_problems
    Genres:     available_genres
"""

from core.mix_analysis._genre_loader import available_genres
from core.mix_analysis.dynamics import analyze_dynamics
from core.mix_analysis.problems import detect_mix_problems
from core.mix_analysis.spectral import analyze_frequency_balance
from core.mix_analysis.stereo import analyze_stereo_image
from core.mix_analysis.transients import analyze_transients
from core.mix_analysis.types import (
    BAND_EDGES,
    BAND_NAMES,
    BandProfile,
    DynamicProfile,
    FrequencyProfile,
    MixAnalysis,
    MixProblem,
    StereoImage,
    TransientProfile,
)

__all__ = [
    # Types
    "BandProfile",
    "FrequencyProfile",
    "StereoImage",
    "DynamicProfile",
    "TransientProfile",
    "MixProblem",
    "MixAnalysis",
    "BAND_NAMES",
    "BAND_EDGES",
    # Analysis functions
    "analyze_frequency_balance",
    "analyze_stereo_image",
    "analyze_dynamics",
    "analyze_transients",
    "detect_mix_problems",
    # Helpers
    "available_genres",
]

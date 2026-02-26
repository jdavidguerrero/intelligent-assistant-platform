"""
ingestion/mix_engine.py — Mix analysis orchestrator with optional RAG injection.

MixAnalysisEngine wires together the Week 16 + Week 17 core analysis modules:

    audio file
        │
        ├─ load_audio()                      [ingestion/audio_loader.py — I/O boundary]
        │       ↓
        ├─ analyze_frequency_balance()       [core/mix_analysis/spectral.py]
        ├─ analyze_stereo_image()            [core/mix_analysis/stereo.py]
        ├─ analyze_dynamics()               [core/mix_analysis/dynamics.py]
        ├─ analyze_transients()             [core/mix_analysis/transients.py]
        │       ↓
        ├─ detect_mix_problems()            [core/mix_analysis/problems.py]
        │       ↓
        ├─ recommend_all()                  [core/mix_analysis/recommendations.py]
        │       ↓ (optional)
        ├─ search_fn(rag_query)             [injected — RAG knowledge base]
        │       ↓
        └─ MixReport / MasterReport

This module lives in `ingestion/` because it performs file I/O (audio loading)
and coordinates side-effectful operations. The core DSP logic is pure.

Design:
    - RAG injection via optional `search_fn` callable — the engine never imports
      the RAG stack directly, making it independently testable.
    - `full_mix_analysis` loads at full stereo (mono=False) so stereo metrics
      are computed; mono fallback is handled by the core modules.
    - Audio is loaded once and reused across all analysis passes.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from core.mix_analysis.calibration import calibrate_genre_targets
from core.mix_analysis.chains import get_chain
from core.mix_analysis.dynamics import analyze_dynamics
from core.mix_analysis.mastering import analyze_master
from core.mix_analysis.problems import detect_mix_problems
from core.mix_analysis.recommendations import recommend_all
from core.mix_analysis.reference import compare_to_references
from core.mix_analysis.report import generate_full_report
from core.mix_analysis.spectral import analyze_frequency_balance
from core.mix_analysis.stereo import analyze_stereo_image
from core.mix_analysis.transients import analyze_transients
from core.mix_analysis.types import (
    DynamicProfile,
    FrequencyProfile,
    FullMixReport,
    GenreTarget,
    MasterAnalysis,
    MasterReport,
    MixProblem,
    MixReport,
    Recommendation,
    ReferenceComparison,
    StereoImage,
    TransientProfile,
)
from ingestion.audio_loader import load_audio

# ---------------------------------------------------------------------------
# Default genre
# ---------------------------------------------------------------------------

_DEFAULT_GENRE: str = "organic house"
_DEFAULT_DURATION: float = 180.0  # 3 min — enough for structure detection


# ---------------------------------------------------------------------------
# MixAnalysisEngine
# ---------------------------------------------------------------------------


@dataclass
class MixAnalysisEngine:
    """High-level orchestrator for mix and mastering analysis.

    Attributes:
        search_fn: Optional RAG callable. If provided, it is called with the
            `rag_query` string from each Recommendation and its result is
            appended as `rag_citations`. Signature:
                search_fn(query: str) -> list[str]
            where each string is a citation text (title + snippet).
            Pass None to skip RAG enhancement (pure analysis only).
    """

    search_fn: Callable[[str], list[str]] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def full_mix_analysis(
        self,
        path: str,
        genre: str = _DEFAULT_GENRE,
        *,
        duration: float = _DEFAULT_DURATION,
    ) -> MixReport:
        """Load audio and run the complete mix analysis pipeline.

        Steps:
            1. Load audio (stereo if available).
            2. Run frequency, stereo, dynamics, and transient analysis.
            3. Detect mix problems against genre targets.
            4. Generate prescriptive recommendations with specific DSP params.
            5. Optionally enhance recommendations with RAG citations.

        Args:
            path:     Absolute path to an audio file.
            genre:    Genre name for target comparison (default: 'organic house').
            duration: Max seconds to load (default: 180 s).

        Returns:
            MixReport with all analysis results and recommendations.

        Raises:
            FileNotFoundError: Audio file not found.
            ValueError:        Unsupported file extension or unknown genre.
            RuntimeError:      Audio decode failure.
        """
        y, sr = load_audio(path, duration=duration, mono=False)

        freq, stereo, dynamics, transients = self._run_core_analysis(y, sr)

        problems = detect_mix_problems(freq, stereo, dynamics, genre=genre)

        recommendations = self._build_recommendations(problems, freq, stereo, dynamics, genre)

        duration_sec = float(y.shape[-1]) / sr

        return MixReport(
            frequency=freq,
            stereo=stereo,
            dynamics=dynamics,
            transients=transients,
            problems=tuple(problems),
            recommendations=tuple(recommendations),
            genre=genre,
            duration_sec=duration_sec,
            sample_rate=sr,
        )

    def master_analysis(
        self,
        path: str,
        genre: str = _DEFAULT_GENRE,
        *,
        duration: float = _DEFAULT_DURATION,
    ) -> MasterReport:
        """Load audio and run mastering-grade analysis.

        Steps:
            1. Load audio (stereo if available).
            2. Run mastering analysis: integrated/ST/momentary LUFS, true peak,
               inter-sample peaks, section dynamics, readiness score.
            3. Load the genre-specific master chain template.

        Args:
            path:     Absolute path to audio file.
            genre:    Genre name for target comparison.
            duration: Max seconds to load.

        Returns:
            MasterReport with MasterAnalysis + suggested SignalChain.

        Raises:
            FileNotFoundError: Audio file not found.
            ValueError:        Unsupported extension or unknown genre.
            RuntimeError:      Audio decode failure.
        """
        y, sr = load_audio(path, duration=duration, mono=False)

        # analyze_master expects (y, sr) — handles both mono and stereo
        master: MasterAnalysis = analyze_master(y, sr, genre=genre)

        chain = get_chain(genre, "master")

        duration_sec = float(y.shape[-1]) / sr

        return MasterReport(
            master=master,
            suggested_chain=chain,
            genre=genre,
            duration_sec=duration_sec,
            sample_rate=sr,
        )

    def recommend_processing(
        self,
        problems: Sequence[MixProblem],
        freq: FrequencyProfile,
        stereo: StereoImage | None,
        dynamics: DynamicProfile,
        genre: str = _DEFAULT_GENRE,
    ) -> list[Recommendation]:
        """Generate prescriptive recommendations for a list of detected problems.

        Use this when you already have analysis results and want to generate
        (or refresh) recommendations without re-running audio analysis.

        Args:
            problems:  List of MixProblem objects from detect_mix_problems().
            freq:      FrequencyProfile for parameter computation.
            stereo:    StereoImage or None for mono.
            dynamics:  DynamicProfile for parameter computation.
            genre:     Genre name for target values.

        Returns:
            List of Recommendation objects, optionally RAG-enhanced.
        """
        return self._build_recommendations(list(problems), freq, stereo, dynamics, genre)

    def compare_to_reference(
        self,
        track_path: str,
        reference_path: str,
        genre: str = _DEFAULT_GENRE,
        *,
        duration: float = _DEFAULT_DURATION,
    ) -> ReferenceComparison:
        """Analyze a track and one reference, then compute A/B comparison.

        Runs full_mix_analysis() on both files, then delegates to
        core/mix_analysis/reference.compare_to_references().

        Args:
            track_path:     Absolute path to the track under review.
            reference_path: Absolute path to the commercial reference.
            genre:          Genre name for target context.
            duration:       Max seconds to load from each file.

        Returns:
            ReferenceComparison with 6-dimension scores and MixDelta list.
        """
        track = self.full_mix_analysis(track_path, genre=genre, duration=duration)
        reference = self.full_mix_analysis(reference_path, genre=genre, duration=duration)
        return compare_to_references(track, [reference], genre=genre)

    def compare_to_references_batch(
        self,
        track_path: str,
        reference_paths: list[str],
        genre: str = _DEFAULT_GENRE,
        *,
        duration: float = _DEFAULT_DURATION,
    ) -> ReferenceComparison:
        """Analyze a track vs N reference tracks (aggregate comparison).

        Args:
            track_path:       Absolute path to the track under review.
            reference_paths:  Absolute paths to commercial reference tracks.
            genre:            Genre name for target context.
            duration:         Max seconds to load from each file.

        Returns:
            ReferenceComparison with averaged reference metrics.

        Raises:
            ValueError: If reference_paths is empty.
        """
        if not reference_paths:
            raise ValueError("reference_paths must not be empty")
        track = self.full_mix_analysis(track_path, genre=genre, duration=duration)
        references = [
            self.full_mix_analysis(rp, genre=genre, duration=duration) for rp in reference_paths
        ]
        return compare_to_references(track, references, genre=genre)

    def full_mix_report(
        self,
        track_path: str,
        genre: str = _DEFAULT_GENRE,
        *,
        reference_paths: list[str] | None = None,
        include_master: bool = True,
        duration: float = _DEFAULT_DURATION,
    ) -> FullMixReport:
        """Generate a complete diagnostic report for a track.

        Runs mix analysis, optionally mastering analysis, and optionally
        reference comparison, then delegates to report.generate_full_report().

        Args:
            track_path:       Absolute path to the audio file.
            genre:            Genre name for target comparison.
            reference_paths:  Optional list of reference file paths.
                              If provided, adds a ReferenceComparison section.
            include_master:   Run mastering analysis (adds Master Readiness section).
            duration:         Max seconds to load.

        Returns:
            FullMixReport with all available sections populated.
        """
        mix = self.full_mix_analysis(track_path, genre=genre, duration=duration)

        master: MasterReport | None = None
        if include_master:
            master = self.master_analysis(track_path, genre=genre, duration=duration)

        ref_comparison: ReferenceComparison | None = None
        if reference_paths:
            # Reuse the already-computed `mix` to avoid re-analysing the track.
            refs = [
                self.full_mix_analysis(rp, genre=genre, duration=duration) for rp in reference_paths
            ]
            ref_comparison = compare_to_references(mix, refs, genre=genre)

        return generate_full_report(mix, master_report=master, reference_comparison=ref_comparison)

    def calibrate_targets(
        self,
        reference_paths: list[str],
        genre: str = _DEFAULT_GENRE,
        *,
        duration: float = _DEFAULT_DURATION,
    ) -> GenreTarget:
        """Analyze N reference tracks and compute calibrated genre targets.

        Args:
            reference_paths: Absolute paths to commercial reference tracks.
                             Minimum 2, recommended 10+.
            genre:           Genre name for the output target.
            duration:        Max seconds to load from each reference.

        Returns:
            GenreTarget with mean ± std for all 16 mix metrics.

        Raises:
            ValueError: If fewer than 2 paths are provided.
        """
        if len(reference_paths) < 2:
            raise ValueError(
                f"calibrate_targets() requires at least 2 reference paths, "
                f"got {len(reference_paths)}"
            )
        analyses = [
            self.full_mix_analysis(rp, genre=genre, duration=duration) for rp in reference_paths
        ]
        return calibrate_genre_targets(analyses, genre)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _run_core_analysis(
        self, y: np.ndarray, sr: int
    ) -> tuple[FrequencyProfile, StereoImage | None, DynamicProfile, TransientProfile]:
        """Run all four core analysis passes on the loaded audio.

        Converts stereo to mono where required (dynamics, transients, frequency).
        Passes stereo directly to stereo analysis.
        """
        # Mono mix for frequency, dynamics, transients
        if y.ndim == 2:
            mono = np.mean(y, axis=0)
        else:
            mono = y

        freq = analyze_frequency_balance(mono, sr)
        dynamics = analyze_dynamics(y, sr)
        transients = analyze_transients(mono, sr)

        # Stereo analysis — None for mono input
        if y.ndim == 2 and y.shape[0] >= 2:
            stereo: StereoImage | None = analyze_stereo_image(y, sr)
        else:
            stereo = None

        return freq, stereo, dynamics, transients

    def _build_recommendations(
        self,
        problems: list[MixProblem],
        freq: FrequencyProfile,
        stereo: StereoImage | None,
        dynamics: DynamicProfile,
        genre: str,
    ) -> list[Recommendation]:
        """Generate recommendations and optionally inject RAG citations.

        If `self.search_fn` is set, it is called once per recommendation
        using the pre-computed `rag_query` field, and the returned strings
        are stored as `rag_citations`.
        """
        recs = recommend_all(problems, freq, stereo, dynamics, genre)

        if self.search_fn is None:
            return recs

        # RAG enhancement — replace each Recommendation with a new one
        # that includes citations (frozen dataclass → create new via replace)
        enhanced: list[Recommendation] = []
        for rec in recs:
            try:
                citations = self.search_fn(rec.rag_query)
            except Exception:
                # Never let RAG failure break the analysis result
                citations = []

            enhanced_rec = Recommendation(
                problem_category=rec.problem_category,
                genre=rec.genre,
                severity=rec.severity,
                summary=rec.summary,
                steps=rec.steps,
                rag_query=rec.rag_query,
                rag_citations=tuple(str(c) for c in citations),
            )
            enhanced.append(enhanced_rec)

        return enhanced

"""
api/routes/mix.py — Mix analysis, reference comparison, and calibration endpoints.

Endpoints
=========
    POST /mix/analyze    — Full mix analysis (spectral, stereo, dynamics, transients,
                           problems, recommendations)
    POST /mix/compare    — A/B comparison of track vs 1+ commercial references
    POST /mix/master     — Mastering-grade analysis (LUFS, true peak, readiness)
    POST /mix/report     — Complete diagnostic report (all of the above combined)
    POST /mix/calibrate  — Derive genre targets from reference track analysis

All endpoints accept server-side file paths and delegate to MixAnalysisEngine.
They are thin HTTP controllers — no business logic lives here.

Error codes
===========
    422  — File not found, unsupported format, unknown genre, <2 references for calibrate
    500  — Audio decode or analysis failure
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from api.schemas.mix import (
    MixAnalyzeRequest,
    MixCalibrateRequest,
    MixCompareRequest,
    MixMasterRequest,
    MixReportRequest,
)
from ingestion.mix_engine import MixAnalysisEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mix", tags=["mix"])

# Shared engine instance — lazy-initialized on first request
_engine: MixAnalysisEngine | None = None


def _get_engine() -> MixAnalysisEngine:
    global _engine
    if _engine is None:
        _engine = MixAnalysisEngine()
    return _engine


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _serialize_mix_report(report: Any) -> dict[str, Any]:
    """Convert a MixReport to a JSON-serializable dict."""
    problems = [
        {
            "category": p.category,
            "severity": p.severity,
            "frequency_range_hz": list(p.frequency_range),
            "description": p.description,
            "recommendation": p.recommendation,
        }
        for p in report.problems
    ]

    recs = []
    for r in report.recommendations:
        steps = [
            {
                "action": s.action,
                "bus": s.bus,
                "plugin_primary": s.plugin_primary,
                "plugin_fallback": s.plugin_fallback,
                "params": [{"name": p.name, "value": p.value} for p in s.params],
            }
            for s in r.steps
        ]
        recs.append(
            {
                "problem_category": r.problem_category,
                "severity": r.severity,
                "summary": r.summary,
                "steps": steps,
                "rag_query": r.rag_query,
                **({"citations": list(r.rag_citations)} if r.rag_citations else {}),
            }
        )

    stereo = None
    if report.stereo is not None and not report.stereo.is_mono:
        stereo = {
            "width": round(report.stereo.width, 3),
            "lr_correlation": round(report.stereo.lr_correlation, 3),
            "mid_side_ratio_db": round(report.stereo.mid_side_ratio, 2),
            "band_widths": report.stereo.band_widths.as_dict(),
        }

    return {
        "spectral": {
            "bands": report.frequency.bands.as_dict(),
            "spectral_centroid_hz": round(report.frequency.spectral_centroid, 1),
            "spectral_tilt_db_oct": round(report.frequency.spectral_tilt, 2),
            "spectral_flatness": round(report.frequency.spectral_flatness, 4),
            "overall_rms_db": round(report.frequency.overall_rms_db, 2),
        },
        "stereo": stereo,
        "dynamics": {
            "lufs": round(report.dynamics.lufs, 2),
            "rms_db": round(report.dynamics.rms_db, 2),
            "peak_db": round(report.dynamics.peak_db, 2),
            "crest_factor_db": round(report.dynamics.crest_factor, 2),
            "dynamic_range_db": round(report.dynamics.dynamic_range, 2),
            "loudness_range_lu": round(report.dynamics.loudness_range, 2),
        },
        "transients": {
            "onset_density_per_sec": round(report.transients.density, 3),
            "attack_sharpness": round(report.transients.sharpness, 3),
            "attack_ratio": round(report.transients.attack_ratio, 3),
        },
        "problems": problems,
        "recommendations": recs,
        "genre": report.genre,
        "duration_sec": round(report.duration_sec, 2),
        "sample_rate": report.sample_rate,
    }


def _serialize_comparison(comp: Any) -> dict[str, Any]:
    """Convert a ReferenceComparison to a JSON-serializable dict."""
    dims = [
        {
            "name": d.name,
            "score": round(d.score, 1),
            "track_value": d.track_value,
            "ref_value": d.ref_value,
            "unit": d.unit,
            "description": d.description,
        }
        for d in comp.dimensions
    ]
    bands = [
        {
            "band": bd.band,
            "track_db": round(bd.track_db, 2),
            "reference_db": round(bd.reference_db, 2),
            "delta_db": round(bd.delta_db, 2),
        }
        for bd in comp.band_deltas
    ]
    deltas = [
        {
            "dimension": d.dimension,
            "direction": d.direction,
            "magnitude": d.magnitude,
            "unit": d.unit,
            "recommendation": d.recommendation,
            "priority": d.priority,
        }
        for d in comp.deltas
    ]
    return {
        "overall_similarity": comp.overall_similarity,
        "dimensions": dims,
        "band_deltas": bands,
        "width_delta": comp.width_delta,
        "crest_factor_delta": comp.crest_factor_delta,
        "lra_delta": comp.lra_delta,
        "centroid_delta_hz": comp.centroid_delta_hz,
        "tilt_delta": comp.tilt_delta,
        "density_delta": comp.density_delta,
        "sharpness_delta": comp.sharpness_delta,
        "lufs_delta": comp.lufs_delta,
        "lufs_normalization_db": comp.lufs_normalization_db,
        "deltas": deltas,
        "genre": comp.genre,
        "num_references": comp.num_references,
    }


def _serialize_master_report(report: Any) -> dict[str, Any]:
    """Convert a MasterReport to a JSON-serializable dict."""
    m = report.master
    sections = [
        {
            "label": s.label,
            "start_sec": s.start_sec,
            "rms_db": s.rms_db,
            "peak_db": s.peak_db,
            "crest_factor_db": s.crest_factor,
        }
        for s in m.sections
    ]
    chain_procs = [
        {
            "name": p.name,
            "proc_type": p.proc_type,
            "plugin_primary": p.plugin_primary,
            "plugin_fallback": p.plugin_fallback,
            "params": [{"name": pp.name, "value": pp.value} for pp in p.params],
        }
        for p in report.suggested_chain.processors
    ]
    return {
        "loudness": {
            "lufs_integrated": round(m.lufs_integrated, 2),
            "lufs_short_term_max": round(m.lufs_short_term_max, 2),
            "lufs_momentary_max": round(m.lufs_momentary_max, 2),
            "true_peak_db": round(m.true_peak_db, 2),
            "inter_sample_peaks": m.inter_sample_peaks,
        },
        "dynamics": {
            "crest_factor_db": round(m.crest_factor, 2),
            "sections": sections,
        },
        "spectral_balance": m.spectral_balance,
        "readiness_score": round(m.readiness_score, 1),
        "issues": list(m.issues),
        "mastering_chain": {
            "genre": report.suggested_chain.genre,
            "stage": report.suggested_chain.stage,
            "description": report.suggested_chain.description,
            "processors": chain_procs,
        },
        "genre": report.genre,
        "duration_sec": round(report.duration_sec, 2),
        "sample_rate": report.sample_rate,
    }


def _serialize_full_report(full: Any) -> dict[str, Any]:
    """Convert a FullMixReport to a JSON-serializable dict."""

    def _section(sec: Any) -> dict[str, Any]:
        return {
            "title": sec.title,
            "severity": sec.severity,
            "summary": sec.summary,
            "points": list(sec.points),
            "confidence": sec.confidence,
        }

    sections: dict[str, Any] = {
        "executive_summary": _section(full.executive_summary),
        "frequency_analysis": _section(full.frequency_analysis),
        "stereo_analysis": _section(full.stereo_analysis),
        "dynamics_analysis": _section(full.dynamics_analysis),
        "problems_and_fixes": _section(full.problems_and_fixes),
        "signal_chain": _section(full.signal_chain_section),
    }
    if full.reference_section is not None:
        sections["reference_comparison"] = _section(full.reference_section)
    if full.master_readiness_section is not None:
        sections["master_readiness"] = _section(full.master_readiness_section)

    return {
        "overall_health_score": full.overall_health_score,
        "top_priorities": list(full.top_priorities),
        "genre": full.genre,
        "duration_sec": round(full.duration_sec, 2),
        "sections": sections,
        "mix_analysis": _serialize_mix_report(full.mix_report),
        **(
            {"master_analysis": _serialize_master_report(full.master_report)}
            if full.master_report is not None
            else {}
        ),
        **(
            {"reference_comparison": _serialize_comparison(full.reference_comparison)}
            if full.reference_comparison is not None
            else {}
        ),
    }


def _serialize_genre_target(target: Any) -> dict[str, Any]:
    """Convert a GenreTarget to a JSON-serializable dict."""
    from core.mix_analysis.calibration import target_to_dict

    return target_to_dict(target)


# ---------------------------------------------------------------------------
# Error handling helper
# ---------------------------------------------------------------------------


def _handle_analysis_error(exc: Exception, context: str) -> None:
    """Translate common analysis errors to appropriate HTTP exceptions."""
    if isinstance(exc, FileNotFoundError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    logger.error("%s failed: %s", context, exc)
    raise HTTPException(status_code=500, detail=f"{context} failed: {exc}") from exc


# ---------------------------------------------------------------------------
# POST /mix/analyze
# ---------------------------------------------------------------------------


@router.post("/analyze")
def analyze_mix(request: MixAnalyzeRequest) -> dict[str, Any]:
    """Run a complete mix analysis on an audio file.

    Performs spectral balance (7 bands), stereo image, dynamics (LUFS/crest/LRA),
    transient analysis, genre-aware problem detection, and prescriptive
    recommendations with specific DSP parameter values.

    Args:
        request: MixAnalyzeRequest with file_path, genre, duration.

    Returns:
        JSON with spectral, stereo, dynamics, transients, problems, recommendations.

    Raises:
        422: File not found or unsupported format.
        500: Audio decode or analysis failure.
    """
    engine = _get_engine()
    try:
        report = engine.full_mix_analysis(
            request.file_path,
            genre=request.genre,
            duration=request.duration,
        )
    except Exception as exc:
        _handle_analysis_error(exc, "Mix analysis")

    return _serialize_mix_report(report)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# POST /mix/compare
# ---------------------------------------------------------------------------


@router.post("/compare")
def compare_mix(request: MixCompareRequest) -> dict[str, Any]:
    """Compare a track against one or more commercial reference tracks.

    Analyzes both the track and all references, then computes a 6-dimension
    A/B comparison with an overall similarity score (0–100%) and actionable
    improvement deltas (EQ cuts, compression adjustments, stereo widening, etc.)

    Args:
        request: MixCompareRequest with file_path, reference_paths, genre, duration.

    Returns:
        JSON with overall_similarity, per-dimension scores, band deltas, deltas.

    Raises:
        422: Any file not found, unsupported format, or empty reference list.
        500: Audio decode or analysis failure.
    """
    engine = _get_engine()
    try:
        comparison = engine.compare_to_references_batch(
            request.file_path,
            list(request.reference_paths),
            request.genre,
            duration=request.duration,
        )
    except Exception as exc:
        _handle_analysis_error(exc, "Reference comparison")

    return _serialize_comparison(comparison)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# POST /mix/master
# ---------------------------------------------------------------------------


@router.post("/master")
def master_mix(request: MixMasterRequest) -> dict[str, Any]:
    """Run mastering-grade analysis on an audio file.

    Measures integrated/short-term/momentary LUFS (BS.1770), true peak with
    4x oversampling, inter-sample peaks, per-section dynamics, spectral balance,
    and a 0–100 master readiness score.

    Args:
        request: MixMasterRequest with file_path, genre, duration.

    Returns:
        JSON with loudness, dynamics, spectral_balance, readiness_score, issues.

    Raises:
        422: File not found or unsupported format.
        500: Audio decode or analysis failure.
    """
    engine = _get_engine()
    try:
        report = engine.master_analysis(
            request.file_path,
            genre=request.genre,
            duration=request.duration,
        )
    except Exception as exc:
        _handle_analysis_error(exc, "Master analysis")

    return _serialize_master_report(report)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# POST /mix/report
# ---------------------------------------------------------------------------


@router.post("/report")
def mix_report(request: MixReportRequest) -> dict[str, Any]:
    """Generate a complete diagnostic report for a track.

    Combines mix analysis, optional mastering analysis, and optional reference
    comparison into a single structured report with 6–8 sections.

    Args:
        request: MixReportRequest with file_path, genre, reference_paths,
                 include_master, duration.

    Returns:
        JSON with overall_health_score, top_priorities, and all report sections.

    Raises:
        422: Any file not found or unsupported format.
        500: Audio decode or analysis failure.
    """
    engine = _get_engine()
    try:
        full = engine.full_mix_report(
            request.file_path,
            request.genre,
            reference_paths=list(request.reference_paths) or None,
            include_master=request.include_master,
            duration=request.duration,
        )
    except Exception as exc:
        _handle_analysis_error(exc, "Full report")

    return _serialize_full_report(full)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# POST /mix/calibrate
# ---------------------------------------------------------------------------


@router.post("/calibrate")
def calibrate_mix(request: MixCalibrateRequest) -> dict[str, Any]:
    """Derive calibrated genre targets from commercial reference track analysis.

    Analyzes all provided reference tracks and computes mean ± std for 16
    mix metrics (spectral bands, centroid, tilt, width, LUFS, crest, LRA,
    transient density, sharpness). The output is a data-driven GenreTarget
    that replaces manually authored YAML targets.

    Args:
        request: MixCalibrateRequest with reference_paths (≥2), genre, duration.

    Returns:
        JSON GenreTarget dict compatible with genre_targets/ YAML format.

    Raises:
        422: Fewer than 2 reference paths, file not found, unsupported format.
        500: Audio decode or analysis failure.
    """
    engine = _get_engine()
    try:
        target = engine.calibrate_targets(
            list(request.reference_paths),
            request.genre,
            duration=request.duration,
        )
    except Exception as exc:
        _handle_analysis_error(exc, "Genre target calibration")

    return _serialize_genre_target(target)  # type: ignore[return-value]

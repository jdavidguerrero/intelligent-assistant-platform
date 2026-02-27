"""
auto_setup_mix tool — Capture stems, analyse per-channel, attribute problems,
build and apply a processing chain setup across the Ableton session.

Pipeline:
  1. Get session state from ALS Listener.
  2. capture_stems: extract audio file paths per track.
  3. analyse each stem with MixAnalysisEngine.
  4. detect stem types + compute frequency footprints.
  5. attribute master-bus problems to source stems.
  6. build SetupActions (EQ, compressor, utility per track).
  7. If dry_run=False → apply actions via AbletonBridge.
  8. Return full report.

Requires:
  - ALS Listener M4L device running in Ableton.
  - librosa + soundfile installed.
  - Audio tracks with real file paths (MIDI tracks are flagged, not processed).
"""

from __future__ import annotations

from typing import Any

from tools.base import MusicalTool, ToolParameter, ToolResult

_SUPPORTED_GENRES = (
    "organic house",
    "melodic techno",
    "deep house",
    "progressive house",
    "afro house",
)

_WS_HOST = "localhost"
_WS_PORT = 11005


class AutoSetupMix(MusicalTool):
    """Automatically set up processing chains across all Ableton tracks.

    Captures each stem from the current Ableton session, analyses them
    individually, attributes master-bus problems to their source tracks,
    then loads appropriate EQ/compressor/utility settings per channel.

    Use when the user asks to:
        - Auto-set up the mix
        - Diagnose every channel
        - Set up processing chains automatically
        - Apply mix analysis to each track
        - Run the auto-setup wizard

    Returns a preview of all planned actions (with dry_run=True, default)
    so the user can approve before applying.
    """

    @property
    def name(self) -> str:
        return "auto_setup_mix"

    @property
    def description(self) -> str:
        return (
            "Capture all stems from the current Ableton session, analyse each track "
            "individually, attribute master-bus problems to source channels, and generate "
            "(or apply) genre-appropriate EQ, compressor, and gain settings per track. "
            "Returns a preview action list by default (dry_run=True). Set dry_run=False "
            "to apply changes directly in Ableton. "
            "Requires ALS Listener M4L device running in Ableton. "
            f"Supported genres: {', '.join(_SUPPORTED_GENRES)}."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="genre",
                type=str,
                description=(
                    "Genre for analysis targets and processing suggestions. "
                    f"Options: {', '.join(_SUPPORTED_GENRES)}."
                ),
                required=False,
                default="organic house",
            ),
            ToolParameter(
                name="master_file_path",
                type=str,
                description=(
                    "Absolute path to the master/bounced mix file for master-level analysis. "
                    "If omitted, only per-stem analysis is performed."
                ),
                required=False,
                default="",
            ),
            ToolParameter(
                name="dry_run",
                type=bool,
                description=(
                    "If True (default), return planned actions without applying them. "
                    "Set False to apply all changes immediately in Ableton."
                ),
                required=False,
                default=True,
            ),
            ToolParameter(
                name="duration",
                type=float,
                description="Max seconds of each stem to analyse (default 60.0 for speed).",
                required=False,
                default=60.0,
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:  # noqa: PLR0912, PLR0915
        """Run the full auto-setup pipeline."""
        genre: str = str(kwargs.get("genre") or "organic house").strip().lower()
        master_path: str = str(kwargs.get("master_file_path") or "").strip()
        dry_run: bool = bool(kwargs.get("dry_run", True))
        duration: float = float(kwargs.get("duration") or 60.0)

        if genre not in _SUPPORTED_GENRES:
            return ToolResult(
                success=False,
                error=f"genre must be one of: {', '.join(_SUPPORTED_GENRES)}",
            )

        # ── Step 1: Connect to Ableton and get session ──────────────────────
        try:
            from ingestion.ableton_bridge import AbletonBridge

            bridge = AbletonBridge(host=_WS_HOST, port=_WS_PORT)
            session_data = bridge.get_session()
        except Exception as exc:
            return ToolResult(
                success=False,
                error=(
                    f"Cannot connect to ALS Listener: {exc}. "
                    "Load the ALS Listener M4L device in Ableton and try again."
                ),
            )

        # ── Step 2: Capture stems ───────────────────────────────────────────
        from ableton_bridge.capture import capture_stems

        captures = capture_stems(session_data)
        analysable = [c for c in captures if c.is_analysable()]
        skipped = [c for c in captures if not c.is_analysable()]

        if not analysable:
            return ToolResult(
                success=False,
                error=(
                    "No analysable audio stems found. "
                    "Audio tracks need loaded clips with accessible file paths. "
                    f"Skipped: {[c.track_name for c in skipped]}"
                ),
            )

        # ── Step 3: Analyse each stem ───────────────────────────────────────
        from ingestion.mix_engine import MixAnalysisEngine  # type: ignore

        engine = MixAnalysisEngine()
        stem_analyses: dict[str, Any] = {}
        analysis_errors: dict[str, str] = {}

        for cap in analysable:
            try:
                report = engine.full_mix_analysis(
                    cap.file_path, genre=genre, duration=duration
                )
                stem_analyses[cap.track_name] = report
            except Exception as exc:
                analysis_errors[cap.track_name] = str(exc)

        if not stem_analyses:
            return ToolResult(
                success=False,
                error=f"All stem analyses failed: {analysis_errors}",
            )

        # ── Step 4: Stem type + footprints ─────────────────────────────────
        from core.mix_analysis.stems import classify_stems, compute_all_footprints

        stem_types = classify_stems(stem_analyses)
        footprints = compute_all_footprints(stem_analyses)

        # ── Step 5: Master analysis + attribution ──────────────────────────
        master_analysis = None
        attributed: dict[str, list] = {}
        volume_suggestions: list = []

        if master_path:
            try:
                master_analysis = engine.full_mix_analysis(
                    master_path, genre=genre, duration=duration
                )
                from core.mix_analysis.attribution import attribute_problems, suggest_volume_balance

                attributed = attribute_problems(master_analysis, footprints)
                volume_suggestions = suggest_volume_balance(footprints)
            except Exception as exc:
                analysis_errors["master"] = str(exc)

        # ── Step 6: Build setup actions ────────────────────────────────────
        from ableton_bridge.auto_setup import build_setup_actions

        session_tracks = list(session_data.tracks)
        actions = build_setup_actions(
            session_tracks=session_tracks,
            stem_footprints=footprints,
            attributed_problems=attributed,
            volume_suggestions=volume_suggestions,
            genre=genre,
        )

        # ── Step 7: Apply or dry-run ────────────────────────────────────────
        setup_result = None
        if not dry_run and actions:
            from ableton_bridge.auto_setup import apply_setup_actions

            setup_result = apply_setup_actions(actions)

        # ── Step 8: Serialise output ────────────────────────────────────────
        stems_out = []
        for name, report in stem_analyses.items():
            stype = stem_types.get(name)
            fp = footprints.get(name)
            stems_out.append(
                {
                    "track_name": name,
                    "stem_type": stype.value if stype else "unknown",
                    "problems": [
                        {
                            "category": p.category,
                            "severity": p.severity,
                            "description": p.description,
                        }
                        for p in report.problems
                    ],
                    "footprint": fp.as_dict() if fp else None,
                    "dynamics": {
                        "rms_db": round(report.dynamics.rms_db, 2),
                        "lufs": round(report.dynamics.lufs, 2),
                        "crest_factor_db": round(report.dynamics.crest_factor, 2),
                    },
                }
            )

        return ToolResult(
            success=True,
            data={
                "stems_analysed": len(stem_analyses),
                "stems_skipped": len(skipped),
                "skipped_tracks": [c.track_name for c in skipped],
                "stems": stems_out,
                "attribution": {
                    cat: [c.as_dict() for c in contribs]
                    for cat, contribs in attributed.items()
                },
                "volume_suggestions": [s.as_dict() for s in volume_suggestions],
                "setup_actions": [a.as_dict() for a in actions],
                "setup_result": setup_result.as_dict() if setup_result else None,
                "dry_run": dry_run,
                "genre": genre,
                "analysis_errors": analysis_errors,
            },
            metadata={
                "track_count": len(session_tracks),
                "analysable_count": len(analysable),
                "action_count": len(actions),
                "applied": not dry_run and setup_result is not None,
            },
        )

"""
analyze_sample tool — full audio feature extraction using the production pipeline.

Analyses an audio file on disk:
  - BPM (beat tracking via librosa.beat.beat_track)
  - Musical key (Krumhansl-Schmuckler + HPSS harmonic separation)
  - Energy level 0–10 (log-normalized RMS)
  - Spectral features (chroma, onsets)
  - Optional melody notes (pYIN pitch tracking)

Returns structured data suitable for downstream generation tools
(suggest_chord_progression, generate_full_arrangement, etc.).

Requires the audio stack (librosa + soundfile) to be installed.
"""

from typing import Any

from tools.base import MusicalTool, ToolParameter, ToolResult


class AnalyzeSample(MusicalTool):
    """Analyse an audio file and extract BPM, key, energy, and melody.

    Runs the full audio analysis pipeline:
      1. HPSS (harmonic-percussive source separation)
      2. BPM via beat tracking
      3. Musical key via Krumhansl-Schmuckler algorithm
      4. Energy level (log-normalized RMS)
      5. Spectral features (chroma, onsets)
      6. Optional pYIN melody detection

    Use when the user provides an audio file and wants to know its tempo,
    key, energy, or melodic content — especially as preparation for
    chord progression and arrangement generation.

    Example:
        tool = AnalyzeSample()
        result = tool(file_path="/path/to/loop.wav")
        # Returns: bpm=128.0, key="A minor", energy=7, notes=[...]
    """

    @property
    def name(self) -> str:
        return "analyze_sample"

    @property
    def description(self) -> str:
        return (
            "Analyse an audio file to extract BPM, musical key, energy level (0-10), "
            "and optionally melody notes. "
            "Use when the user provides an audio file path and wants to know its musical "
            "properties, or before generating chord progressions / arrangements from audio. "
            "Supports .mp3, .wav, .flac, .aiff, .ogg, .m4a files. "
            "Returns structured data: bpm, key (root + mode + confidence), energy, duration."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="file_path",
                type=str,
                description=(
                    "Absolute path to audio file on local filesystem. "
                    "Supported: .mp3 .wav .flac .aiff .ogg .m4a .opus"
                ),
                required=True,
            ),
            ToolParameter(
                name="duration",
                type=float,
                description="Max seconds to load (default 30.0). Use higher values for longer loops.",
                required=False,
                default=30.0,
            ),
            ToolParameter(
                name="include_melody",
                type=bool,
                description=(
                    "If True, run pYIN pitch tracking to extract melody notes. "
                    "Slower but returns note list useful for chord harmonization."
                ),
                required=False,
                default=False,
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        """Execute audio analysis pipeline.

        Returns:
            ToolResult.data with keys:
                bpm (float), key (dict with root/mode/confidence/label),
                energy (int 0-10), duration_sec (float), sample_rate (int),
                notes (list[dict] — only if include_melody=True),
                spectral (dict or None)
        """
        file_path: str = (kwargs.get("file_path") or "").strip()
        duration: float = float(kwargs.get("duration") or 30.0)
        include_melody: bool = bool(kwargs.get("include_melody") or False)

        if not file_path:
            return ToolResult(success=False, error="file_path cannot be empty")

        try:
            from ingestion.audio_engine import AudioAnalysisEngine

            engine = AudioAnalysisEngine()
            analysis = engine.analyze_sample(
                file_path,
                duration=duration,
                include_melody=include_melody,
            )
        except FileNotFoundError as exc:
            return ToolResult(success=False, error=f"File not found: {exc}")
        except ValueError as exc:
            return ToolResult(success=False, error=str(exc))
        except RuntimeError as exc:
            return ToolResult(success=False, error=f"Analysis failed: {exc}")

        notes_data = [
            {
                "pitch_midi": n.pitch_midi,
                "pitch_name": n.pitch_name,
                "onset_sec": round(n.onset_sec, 3),
                "duration_sec": round(n.duration_sec, 3),
                "velocity": n.velocity,
            }
            for n in analysis.notes
        ]

        spectral_data = None
        if analysis.spectral is not None:
            spectral_data = {
                "chroma": [round(c, 4) for c in analysis.spectral.chroma],
                "rms": round(analysis.spectral.rms, 6),
                "tempo": analysis.spectral.tempo,
                "onset_count": len(analysis.spectral.onsets_sec),
            }

        return ToolResult(
            success=True,
            data={
                "bpm": round(analysis.bpm, 2),
                "key": {
                    "root": analysis.key.root,
                    "mode": analysis.key.mode,
                    "confidence": round(analysis.key.confidence, 3),
                    "label": analysis.key.label,
                },
                "energy": analysis.energy,
                "duration_sec": round(analysis.duration_sec, 2),
                "sample_rate": analysis.sample_rate,
                "notes": notes_data,
                "spectral": spectral_data,
            },
            metadata={
                "file": file_path,
                "include_melody": include_melody,
                "note_count": len(notes_data),
            },
        )

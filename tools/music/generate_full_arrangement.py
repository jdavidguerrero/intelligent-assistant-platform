"""
generate_full_arrangement tool — complete audio→MIDI production pipeline.

Given an audio file, runs the complete production pipeline:
    audio → analysis → melody → harmony → bass → drums → MIDI

Unlike the standalone generate_bassline / generate_drum_pattern tools
(which use hardcoded patterns), this tool uses the full core/music_theory/
engine that respects YAML genre templates, energy layers, humanization,
and proper MIDI channel assignment (ch0=chords, ch1=bass, ch9=drums).

Output: structured data with all pipeline results + optional MIDI files.

Use when the user provides an audio file and wants a complete arrangement
ready for Ableton, or when they want to analyse a loop and generate a
matching backing track.
"""

from typing import Any

from tools.base import MusicalTool, ToolParameter, ToolResult

_VALID_GENRES: frozenset[str] = frozenset(
    {"organic house", "deep house", "melodic techno", "progressive house", "afro house"}
)


class GenerateFullArrangement(MusicalTool):
    """Generate a full MIDI arrangement from an audio file.

    Runs the complete pipeline:
      1. Load audio + analyse (BPM, key, energy, melody)
      2. Harmonize melody → chord progression (genre-aware)
      3. Generate bass line on 16-step grid
      4. Generate drum pattern with energy layers
      5. Export 4-track MIDI (chords + bass + drums + optional melody)

    Returns structured data with all pipeline outputs plus paths to any
    saved MIDI files.

    Use when the user says "create an arrangement from this loop",
    "generate a backing track for this sample", or "turn this audio into MIDI".

    Example:
        tool = GenerateFullArrangement()
        result = tool(
            file_path="/path/to/loop.wav",
            genre="organic house",
            bars=4,
            output_dir="/tmp/my_session",
        )
        # Returns MIDI paths + chord progression + BPM + key
    """

    @property
    def name(self) -> str:
        return "generate_full_arrangement"

    @property
    def description(self) -> str:
        return (
            "Generate a complete MIDI arrangement from an audio file. "
            "Analyses the audio (BPM, key, energy, melody), harmonizes the melody into "
            "a chord progression, generates a genre-specific bass line and drum pattern, "
            "and optionally saves 4-track MIDI files. "
            "Use when the user provides an audio file and wants a full arrangement, "
            "backing track, or MIDI export. "
            f"Supported genres: {', '.join(sorted(_VALID_GENRES))}. "
            "Returns: bpm, key, progression, bass_note_count, drum_hit_count, midi_paths."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="file_path",
                type=str,
                description="Absolute path to audio file (.mp3 .wav .flac .aiff .ogg .m4a).",
                required=True,
            ),
            ToolParameter(
                name="genre",
                type=str,
                description=(
                    f"Music genre for arrangement style. "
                    f"Options: {', '.join(sorted(_VALID_GENRES))}. "
                    f"Default: 'organic house'."
                ),
                required=False,
                default="organic house",
            ),
            ToolParameter(
                name="bars",
                type=int,
                description="Number of bars to generate (1–16). Default: 4.",
                required=False,
                default=4,
            ),
            ToolParameter(
                name="bpm",
                type=float,
                description=("Override detected BPM. Leave empty to use analysed tempo."),
                required=False,
                default=None,
            ),
            ToolParameter(
                name="energy",
                type=int,
                description=("Override energy level 0–10. Leave empty to use analysed energy."),
                required=False,
                default=None,
            ),
            ToolParameter(
                name="humanize",
                type=bool,
                description="Apply micro-timing + velocity humanization. Default: True.",
                required=False,
                default=True,
            ),
            ToolParameter(
                name="output_dir",
                type=str,
                description=(
                    "Directory to save MIDI files. If empty, no files are written "
                    "but results are still returned."
                ),
                required=False,
                default=None,
            ),
            ToolParameter(
                name="seed",
                type=int,
                description="Random seed for reproducibility. Default: None (random).",
                required=False,
                default=None,
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the full audio→MIDI pipeline.

        Returns:
            ToolResult.data with keys:
                bpm, key, genre, bars, energy,
                chords (list[dict]), progression_label,
                bass_note_count, drum_hit_count,
                midi_paths (dict[str, str]),
                melody_note_count, processing_time_ms
        """
        file_path: str = (kwargs.get("file_path") or "").strip()
        genre: str = (kwargs.get("genre") or "organic house").strip().lower()
        bars: int = int(kwargs.get("bars") or 4)
        bpm: float | None = kwargs.get("bpm")
        energy: int | None = kwargs.get("energy")
        humanize: bool = bool(
            kwargs.get("humanize") if kwargs.get("humanize") is not None else True
        )
        output_dir: str | None = kwargs.get("output_dir")
        seed: int | None = kwargs.get("seed")

        if not file_path:
            return ToolResult(success=False, error="file_path cannot be empty")
        if genre not in _VALID_GENRES:
            return ToolResult(
                success=False,
                error=f"genre must be one of: {', '.join(sorted(_VALID_GENRES))}",
            )
        if not (1 <= bars <= 16):
            return ToolResult(success=False, error="bars must be between 1 and 16")
        if bpm is not None and not (20.0 <= bpm <= 300.0):
            return ToolResult(success=False, error="bpm must be between 20 and 300")
        if energy is not None and not (0 <= energy <= 10):
            return ToolResult(success=False, error="energy must be between 0 and 10")

        try:
            from ingestion.audio_engine import AudioAnalysisEngine

            engine = AudioAnalysisEngine()
            composition = engine.full_pipeline(
                file_path,
                genre=genre,
                bars=bars,
                bpm=bpm,
                energy=energy,
                humanize=humanize,
                seed=seed,
                output_dir=output_dir,
            )
        except FileNotFoundError as exc:
            return ToolResult(success=False, error=f"File not found: {exc}")
        except ValueError as exc:
            return ToolResult(success=False, error=str(exc))
        except RuntimeError as exc:
            return ToolResult(success=False, error=f"Pipeline failed: {exc}")

        chords_data = [
            {
                "name": c.name,
                "root": c.root,
                "quality": c.quality,
                "roman": c.roman,
                "midi_notes": list(c.midi_notes),
            }
            for c in composition.voicing.chords
        ]

        return ToolResult(
            success=True,
            data={
                "bpm": round(composition.bpm, 2),
                "key": {
                    "root": composition.analysis.key.root,
                    "mode": composition.analysis.key.mode,
                    "confidence": round(composition.analysis.key.confidence, 3),
                    "label": composition.analysis.key.label,
                },
                "genre": composition.genre,
                "bars": composition.bars,
                "energy": composition.analysis.energy,
                "chords": chords_data,
                "progression_label": composition.voicing.progression_label,
                "bass_note_count": len(composition.bass_notes),
                "drum_hit_count": len(composition.drum_pattern.hits),
                "melody_note_count": len(composition.melody_notes),
                "midi_paths": composition.midi_paths,
                "processing_time_ms": round(composition.processing_time_ms, 1),
            },
            metadata={
                "file": file_path,
                "genre": composition.genre,
                "key": composition.analysis.key.label,
            },
        )

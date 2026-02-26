"""
extract_melody tool — monophonic melody extraction using pYIN pitch tracking.

Extracts a melody from an audio file as a sequence of discrete notes.
Uses HPSS (harmonic-percussive source separation) for cleaner results,
then applies probabilistic YIN pitch tracking.

Output notes are suitable for:
  - Harmonization via suggest_chord_progression or melody_to_chords
  - MIDI export via full_arrangement
  - Human-readable display (pitch names, onset/duration in seconds)

Best results on:
  - Monophonic sources: lead melody, bass line, solo instrument
  - Audio with clear tonal content (no noise, minimal reverb)
  - After HPSS separation (done automatically)
"""

from typing import Any

from tools.base import MusicalTool, ToolParameter, ToolResult


class ExtractMelody(MusicalTool):
    """Extract melody notes from a monophonic audio file using pYIN.

    Runs HPSS separation first, then probabilistic YIN pitch tracking
    on the harmonic component. Returns a list of notes with MIDI pitch,
    scientific name (e.g. "A4"), onset time, duration, and velocity.

    Use when the user provides an audio loop and wants to see its melodic
    content, or wants to harmonize or convert the melody to MIDI.

    Example:
        tool = ExtractMelody()
        result = tool(file_path="/path/to/melody.wav")
        # Returns: notes=[{pitch_name:"A4", onset_sec:0.1, ...}, ...]
    """

    @property
    def name(self) -> str:
        return "extract_melody"

    @property
    def description(self) -> str:
        return (
            "Extract melody notes from a monophonic audio file using pYIN pitch tracking. "
            "Returns a list of discrete notes with MIDI pitch numbers, scientific note names "
            "(e.g. 'A4', 'C#5'), onset times in seconds, durations, and velocities. "
            "Best for lead melodies, bass lines, solo instruments. "
            "Use before harmonize_melody or when user wants to convert audio melody to MIDI. "
            "Requires .mp3 .wav .flac .aiff .ogg .m4a file."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="file_path",
                type=str,
                description="Absolute path to audio file on local filesystem.",
                required=True,
            ),
            ToolParameter(
                name="duration",
                type=float,
                description="Max seconds to analyse (default 30.0).",
                required=False,
                default=30.0,
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        """Execute pYIN melody detection pipeline.

        Returns:
            ToolResult.data with keys:
                notes (list[dict]): Each dict has pitch_midi, pitch_name,
                    onset_sec, duration_sec, velocity.
                note_count (int): Total notes detected.
                duration_sec (float): Estimated audio duration from last note.
        """
        file_path: str = (kwargs.get("file_path") or "").strip()
        duration: float = float(kwargs.get("duration") or 30.0)

        if not file_path:
            return ToolResult(success=False, error="file_path cannot be empty")

        try:
            from ingestion.audio_engine import AudioAnalysisEngine

            engine = AudioAnalysisEngine()
            notes = engine.extract_melody(file_path, duration=duration)
        except FileNotFoundError as exc:
            return ToolResult(success=False, error=f"File not found: {exc}")
        except ValueError as exc:
            return ToolResult(success=False, error=str(exc))
        except RuntimeError as exc:
            return ToolResult(success=False, error=f"Melody extraction failed: {exc}")

        notes_data = [
            {
                "pitch_midi": n.pitch_midi,
                "pitch_name": n.pitch_name,
                "onset_sec": round(n.onset_sec, 3),
                "duration_sec": round(n.duration_sec, 3),
                "velocity": n.velocity,
            }
            for n in notes
        ]

        total_duration = 0.0
        if notes:
            last = notes[-1]
            total_duration = last.onset_sec + last.duration_sec

        return ToolResult(
            success=True,
            data={
                "notes": notes_data,
                "note_count": len(notes_data),
                "duration_sec": round(total_duration, 3),
            },
            metadata={
                "file": file_path,
                "algorithm": "pYIN",
            },
        )

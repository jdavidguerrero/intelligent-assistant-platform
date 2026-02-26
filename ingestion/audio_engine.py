"""
ingestion/audio_engine.py — High-level orchestrator for the audio→music pipeline.

AudioAnalysisEngine wires together the entire production pipeline:

    audio file
        │
        ├─ load_audio()            [ingestion/audio_loader.py — I/O boundary]
        │       ↓
        ├─ analyze_sample()        [core/audio/features.py — pure DSP]
        │       ↓
        ├─ detect_melody()         [core/audio/melody.py — pYIN pitch tracking]
        │       ↓
        ├─ suggest_progression()   [core/music_theory/harmony.py — diatonic engine]
        │       ↓
        ├─ generate_bassline()     [core/music_theory/bass.py — bass engine]
        │       ↓
        ├─ generate_pattern()      [core/music_theory/drums.py — drum engine]
        │       ↓
        └─ full_arrangement_to_midi() [ingestion/midi_export.py — MIDI output]

This module is in `ingestion/` because it performs file I/O (audio loading,
MIDI writing) and coordinates side-effectful operations. The core logic is
pure and lives in `core/`.

Usage:
    engine = AudioAnalysisEngine()
    composition = engine.full_pipeline(
        "/path/to/loop.wav",
        genre="organic house",
        bars=4,
        output_dir="/tmp/midi_out",
    )
    print(composition.voicing.progression_label)
    print(composition.midi_paths)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.audio.types import Note, SampleAnalysis
from core.music_theory.types import BassNote, DrumPattern, VoicingResult
from ingestion.audio_loader import load_audio
from ingestion.midi_export import (
    full_arrangement_to_midi,
    notes_to_midi,
)

# ---------------------------------------------------------------------------
# FullComposition — the output of the complete pipeline
# ---------------------------------------------------------------------------


@dataclass
class FullComposition:
    """Output of AudioAnalysisEngine.full_pipeline().

    Aggregates all stages of the audio→MIDI production pipeline.

    Attributes:
        analysis:           Full audio analysis (BPM, key, energy, spectral features)
        melody_notes:       Notes extracted by pYIN pitch tracking (empty if not run)
        voicing:            Chord progression harmonized from melody or auto-generated
        bass_notes:         Generated bass line notes on a 16-step grid
        drum_pattern:       Generated drum pattern with genre template
        bpm:                Tempo used throughout the pipeline (BPM)
        genre:              Genre template applied (e.g. "organic house")
        bars:               Number of bars in the pattern
        midi_paths:         Dict of track → file path for any saved MIDI files.
                            Keys: "arrangement", "melody", "bass", "drums".
                            Empty if output_dir was not specified.
        processing_time_ms: Wall-clock time for the full pipeline in milliseconds.
    """

    analysis: SampleAnalysis
    melody_notes: tuple[Note, ...]
    voicing: VoicingResult
    bass_notes: tuple[BassNote, ...]
    drum_pattern: DrumPattern
    bpm: float
    genre: str
    bars: int
    midi_paths: dict[str, str] = field(default_factory=dict)
    processing_time_ms: float = 0.0


# ---------------------------------------------------------------------------
# AudioAnalysisEngine
# ---------------------------------------------------------------------------


class AudioAnalysisEngine:
    """Orchestrates the full audio→music generation pipeline.

    This class is the single integration point between:
      - I/O layer (audio loading, MIDI file writing)
      - DSP layer (feature extraction, melody detection)
      - Music theory layer (harmony, bass, drums)

    All core operations are delegated to pure functions in `core/`.
    librosa is imported lazily at construction time (or injected for testing).

    Example:
        engine = AudioAnalysisEngine()
        analysis = engine.analyze_sample("/path/to/loop.mp3")
        print(analysis.bpm, analysis.key.label)

        composition = engine.full_pipeline(
            "/path/to/loop.mp3",
            genre="organic house",
            bars=4,
            output_dir="/tmp/midi",
        )
    """

    def __init__(self, librosa: Any = None) -> None:
        """Initialise the engine.

        Args:
            librosa: Injected librosa module. Pass a MagicMock in tests to avoid
                     loading the audio stack. None = import lazily on first use.
        """
        self._librosa = librosa

    def _get_librosa(self) -> Any:
        """Return librosa, importing it lazily if not already injected."""
        if self._librosa is None:
            import librosa as _lib  # deferred — allows testing without audio backend

            self._librosa = _lib
        return self._librosa

    # ------------------------------------------------------------------
    # Stage 1 — Audio analysis
    # ------------------------------------------------------------------

    def analyze_sample(
        self,
        path: str | Path,
        *,
        duration: float = 30.0,
        include_melody: bool = False,
    ) -> SampleAnalysis:
        """Load an audio file and extract all spectral features.

        Args:
            path:           Path to an audio file (mp3, wav, flac, etc.)
            duration:       Maximum seconds to load (default 30 s)
            include_melody: If True, run pYIN melody detection and include
                            Note objects in SampleAnalysis.notes.

        Returns:
            SampleAnalysis with BPM, key, energy, spectral features,
            and optionally melody notes.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file extension is not a supported format.
            RuntimeError: If the audio cannot be decoded.
        """
        from core.audio.features import analyze_sample as _analyze

        lib = self._get_librosa()
        y, sr = load_audio(path, duration=duration)

        detect_fn = None
        if include_melody:
            from core.audio.melody import detect_melody

            detect_fn = detect_melody

        return _analyze(y, sr, librosa=lib, detect_melody_fn=detect_fn)

    # ------------------------------------------------------------------
    # Stage 2 — Melody detection
    # ------------------------------------------------------------------

    def extract_melody(
        self,
        path: str | Path,
        *,
        duration: float = 30.0,
    ) -> list[Note]:
        """Load an audio file and extract the melody as a Note list.

        Runs HPSS first (harmonic-percussive source separation) to get
        a cleaner harmonic signal, then applies pYIN pitch tracking.

        Args:
            path:     Path to an audio file.
            duration: Maximum seconds to load (default 30 s).

        Returns:
            List of Note objects sorted by onset_sec.
            Empty list if no melody is detected (e.g. drums-only audio).

        Raises:
            FileNotFoundError, ValueError, RuntimeError: from load_audio.
        """
        from core.audio.features import separate_hpss
        from core.audio.melody import detect_melody

        lib = self._get_librosa()
        y, sr = load_audio(path, duration=duration)
        y_harmonic, _ = separate_hpss(y, sr, librosa=lib)
        return detect_melody(y_harmonic, sr, librosa=lib)

    # ------------------------------------------------------------------
    # Stage 3 — Harmony generation
    # ------------------------------------------------------------------

    def melody_to_harmony(
        self,
        notes: list[Note] | tuple[Note, ...],
        *,
        key_root: str = "A",
        key_mode: str = "natural minor",
        genre: str = "organic house",
        bars: int = 4,
    ) -> VoicingResult:
        """Harmonize a melody as a chord progression.

        Uses `melody_to_chords()` when notes are provided, otherwise falls
        back to `suggest_progression()` to generate a progression from
        key + genre parameters alone.

        Args:
            notes:    Melody notes. May be empty — will fall back to suggestion.
            key_root: Root note of the key, e.g. "A"
            key_mode: Mode string, e.g. "natural minor", "major"
            genre:    Genre template name.
            bars:     Number of bars to generate.

        Returns:
            VoicingResult with chord sequence, key info, and roman labels.
        """
        from core.music_theory.harmony import melody_to_chords, suggest_progression

        if notes:
            try:
                return melody_to_chords(
                    list(notes),
                    key_root=key_root,
                    key_mode=key_mode,
                    genre=genre,
                    bars=bars,
                )
            except Exception:
                pass  # fall through to suggest_progression

        return suggest_progression(key_root, genre=genre, bars=bars)

    # ------------------------------------------------------------------
    # Stage 4 — Bass generation
    # ------------------------------------------------------------------

    def generate_bass(
        self,
        chords: tuple,
        *,
        genre: str = "organic house",
        style: str | None = None,
        bars: int = 4,
        humanize: bool = True,
        seed: int | None = None,
    ) -> tuple[BassNote, ...]:
        """Generate a bass line for a chord progression.

        Args:
            chords:   Tuple of Chord objects from a VoicingResult.
            genre:    Genre template (determines default style).
            style:    Explicit bass style override, e.g. "walking", "sub".
                      None = use genre default.
            bars:     Number of bars (must match chords length or repeat).
            humanize: If True, apply timing + velocity humanization.
            seed:     Random seed for reproducibility.

        Returns:
            Tuple of BassNote objects ready for MIDI export.
        """
        from core.music_theory.bass import generate_bassline
        from core.music_theory.humanize import humanize_timing, humanize_velocity

        bass = generate_bassline(chords, genre=genre, seed=seed)

        if humanize:
            from core.music_theory.humanize import humanize_timing, humanize_velocity

            bass = humanize_timing(bass, jitter_ms=8.0, bpm=120.0, seed=seed)
            bass = humanize_velocity(bass, variation=10, seed=seed)

        return bass

    # ------------------------------------------------------------------
    # Stage 5 — Drum generation
    # ------------------------------------------------------------------

    def generate_drums(
        self,
        *,
        genre: str = "organic house",
        energy: int = 7,
        bars: int = 4,
        bpm: float = 120.0,
        humanize: bool = True,
        seed: int | None = None,
    ) -> DrumPattern:
        """Generate a drum pattern.

        Args:
            genre:    Genre template name.
            energy:   Energy level 0–10 (more active at higher values).
            bars:     Number of bars.
            bpm:      Tempo for the pattern metadata.
            humanize: If True, velocity humanization is applied via generate_pattern.
            seed:     Random seed for reproducibility.

        Returns:
            DrumPattern ready for MIDI export.
        """
        from core.music_theory.drums import generate_pattern

        return generate_pattern(
            genre=genre,
            bars=bars,
            energy=energy,
            humanize=humanize,
            seed=seed,
        )

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------

    def full_pipeline(
        self,
        path: str | Path,
        *,
        genre: str = "organic house",
        bars: int = 4,
        bpm: float | None = None,
        energy: int | None = None,
        bass_style: str | None = None,
        output_dir: str | Path | None = None,
        humanize: bool = True,
        seed: int | None = None,
    ) -> FullComposition:
        """Run the complete audio→MIDI production pipeline.

        Steps:
            1. Load audio + extract features (BPM, key, energy, melody)
            2. Harmonize melody → chord progression
            3. Generate bass line
            4. Generate drum pattern
            5. Export MIDI files (if output_dir provided)

        Args:
            path:       Path to an audio file.
            genre:      Genre template for all generative stages.
            bars:       Number of bars to generate. Default 4.
            bpm:        Override BPM. None = use detected BPM (or 120 if unknown).
            energy:     Override energy level. None = use detected energy.
            bass_style: Bass style override. None = genre default.
            output_dir: Directory to save MIDI files. None = no files written.
            humanize:   Apply micro-timing + velocity humanization.
            seed:       Random seed for reproducibility.

        Returns:
            FullComposition with all pipeline outputs and timing information.
        """
        t_start = time.monotonic()

        # Stage 1: Audio analysis + melody detection
        analysis = self.analyze_sample(path, include_melody=True)

        # Resolve BPM and energy
        effective_bpm = bpm if bpm is not None else (analysis.bpm if analysis.bpm > 0 else 120.0)
        effective_energy = energy if energy is not None else max(1, min(10, analysis.energy))

        # Stage 2: Harmony from melody
        melody_notes = tuple(analysis.notes)
        voicing = self.melody_to_harmony(
            melody_notes,
            key_root=analysis.key.root,
            key_mode=analysis.key.mode if analysis.key.mode == "minor" else "natural minor",
            genre=genre,
            bars=bars,
        )

        # Stage 3: Bass
        bass_notes = self.generate_bass(
            voicing.chords,
            genre=genre,
            style=bass_style,
            bars=bars,
            humanize=humanize,
            seed=seed,
        )

        # Stage 4: Drums
        drum_pattern = self.generate_drums(
            genre=genre,
            energy=effective_energy,
            bars=bars,
            bpm=effective_bpm,
            humanize=humanize,
            seed=seed,
        )

        # Stage 5: MIDI export
        midi_paths: dict[str, str] = {}
        if output_dir is not None:
            out = Path(output_dir)
            out.mkdir(parents=True, exist_ok=True)

            arr_path = out / "arrangement.mid"
            full_arrangement_to_midi(
                voicing,
                bass_notes,
                drum_pattern,
                bpm=effective_bpm,
                output_path=arr_path,
            )
            midi_paths["arrangement"] = str(arr_path)

            if melody_notes:
                mel_path = out / "melody.mid"
                notes_to_midi(
                    melody_notes,
                    bpm=effective_bpm,
                    output_path=mel_path,
                )
                midi_paths["melody"] = str(mel_path)

        processing_ms = (time.monotonic() - t_start) * 1000.0

        return FullComposition(
            analysis=analysis,
            melody_notes=melody_notes,
            voicing=voicing,
            bass_notes=bass_notes,
            drum_pattern=drum_pattern,
            bpm=effective_bpm,
            genre=genre,
            bars=bars,
            midi_paths=midi_paths,
            processing_time_ms=processing_ms,
        )

"""
Analyze track tool — extract BPM, key, energy from audio signals.

Uses a cascade of analysis methods (best to worst):
1. Audio signal analysis via librosa (BPM, key via chroma, energy via RMS)
2. Filename parsing (e.g., "track_128bpm_Aminor.mp3") — always-available fallback

NEVER let LLM guess BPM or key — use audio analysis or explicit metadata only.
"""

import math
import re
from pathlib import Path
from typing import Any

import numpy as np

from tools.base import MusicalTool, ToolParameter, ToolResult

# Audio file extensions that librosa can load
AUDIO_EXTENSIONS: frozenset[str] = frozenset(
    {".mp3", ".wav", ".flac", ".aiff", ".aif", ".ogg", ".m4a", ".opus"}
)

# Load only the first N seconds — prevents OOM on full-length tracks
_ANALYSIS_DURATION_SECONDS: float = 30.0

# Krumhansl-Schmuckler key profiles (1990)
# Each tuple is a 12-element pitch class salience profile starting from C.
_MAJOR_PROFILE: tuple[float, ...] = (
    6.35,
    2.23,
    3.48,
    2.33,
    4.38,
    4.09,
    2.52,
    5.19,
    2.39,
    3.66,
    2.29,
    2.88,
)
_MINOR_PROFILE: tuple[float, ...] = (
    6.33,
    2.68,
    3.52,
    5.38,
    2.60,
    3.53,
    2.54,
    4.75,
    3.98,
    2.69,
    3.34,
    3.17,
)

# Chromatic note names (sharps)
_NOTE_NAMES: tuple[str, ...] = (
    "C",
    "C#",
    "D",
    "D#",
    "E",
    "F",
    "F#",
    "G",
    "G#",
    "A",
    "A#",
    "B",
)

# Preferred enharmonic spellings for minor keys (flat notation)
_ENHARMONIC_MINOR: dict[str, str] = {
    "A#": "Bb",
    "D#": "Eb",
    "G#": "Ab",
}


class AnalyzeTrack(MusicalTool):
    """
    Extract musical metadata from an audio file.

    Uses a two-level cascade:
        1. librosa audio signal analysis (if file is accessible)
        2. Filename pattern matching (deterministic fallback)

    Analyzes:
        - BPM (beats per minute) via beat tracking
        - Musical key (e.g., "A minor") via chroma + Krumhansl-Schmuckler
        - Energy level (0-10) via RMS normalization

    Example:
        tool = AnalyzeTrack()
        # Real audio file → uses librosa
        result = tool(file_path="/music/track.mp3")
        # → {"bpm": 128, "key": "A minor", "energy": 7, "confidence": "high"}

        # Non-existent path → filename fallback
        result = tool(file_path="track_128bpm_Aminor.mp3")
        # → {"bpm": 128, "key": "A minor", "energy": "unknown", "confidence": "medium"}
    """

    @property
    def name(self) -> str:
        return "analyze_track"

    @property
    def description(self) -> str:
        return (
            "Extract BPM (beats per minute), musical key, and energy level "
            "from an audio file using signal analysis. Falls back to filename "
            "parsing when the file is unavailable. Use this when the user asks "
            "about track analysis, tempo detection, or key identification."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="file_path",
                type=str,
                description="Path to audio file (mp3, wav, flac, etc.) or filename",
                required=True,
            ),
            ToolParameter(
                name="analyze_audio",
                type=bool,
                description=(
                    "Attempt audio signal analysis via librosa. "
                    "Set False to use filename parsing only. Default: True."
                ),
                required=False,
                default=True,
            ),
        ]

    def execute(self, **kwargs: Any) -> ToolResult:
        """
        Execute track analysis via cascade: librosa → filename parsing.

        Args:
            file_path: Path to audio file or filename string
            analyze_audio: Whether to attempt librosa analysis (default: True)

        Returns:
            ToolResult with bpm, key, energy, confidence, and source metadata
        """
        file_path: str = kwargs["file_path"]
        analyze_audio: bool = kwargs.get("analyze_audio", True)

        # Level 2: librosa audio signal analysis
        if analyze_audio:
            audio_result = self._analyze_with_librosa(file_path)
            if audio_result is not None:
                bpm = audio_result["bpm"]
                key = audio_result["key"]
                energy = audio_result["energy"]
                return ToolResult(
                    success=True,
                    data={
                        "file_path": file_path,
                        "bpm": bpm,
                        "key": key,
                        "energy": energy,
                        "confidence": self._calculate_confidence(bpm, key, energy),
                    },
                    metadata={
                        "source": "audio_analysis",
                        "method": "librosa",
                        "duration_analyzed": audio_result["duration_analyzed"],
                    },
                )

        # Level 1 fallback: filename parsing
        parsed = self._parse_filename(file_path)
        bpm = parsed["bpm"]
        key = parsed["key"]
        energy = parsed["energy"]
        return ToolResult(
            success=True,
            data={
                "file_path": file_path,
                "bpm": bpm,
                "key": key,
                "energy": energy,
                "confidence": self._calculate_confidence(bpm, key, energy),
            },
            metadata={"source": "filename_parsing", "method": "deterministic"},
        )

    # ------------------------------------------------------------------
    # Level 2: librosa audio analysis
    # ------------------------------------------------------------------

    def _analyze_with_librosa(self, file_path: str) -> dict[str, Any] | None:
        """
        Attempt audio signal analysis using librosa.

        Loads up to _ANALYSIS_DURATION_SECONDS of audio and extracts BPM,
        key, and energy. Returns None on any failure so the caller can
        fall through to the next cascade level.

        Returns None when:
            - File does not exist on disk
            - Extension is not a supported audio format
            - Audio is corrupt or unreadable by librosa
            - Any unexpected exception occurs

        Args:
            file_path: Path to audio file

        Returns:
            Dict with bpm, key, energy, duration_analyzed — or None on failure
        """
        import librosa  # installed via requirements.txt

        path = Path(file_path)
        if not path.exists():
            return None
        if path.suffix.lower() not in AUDIO_EXTENSIONS:
            return None

        try:
            y, sr = librosa.load(
                path,
                sr=None,  # preserve native sample rate
                mono=True,
                duration=_ANALYSIS_DURATION_SECONDS,
                offset=0.0,
            )
        except Exception:
            return None

        duration_analyzed = round(float(len(y)) / float(sr), 2)

        # BPM via beat tracking
        try:
            tempo, _beats = librosa.beat.beat_track(y=y, sr=sr)
            bpm_raw = float(tempo)
            bpm: int | str = int(round(bpm_raw)) if 20 <= bpm_raw <= 300 else "unknown"
        except Exception:
            bpm = "unknown"

        # Key via chroma + Krumhansl-Schmuckler
        try:
            key: str = self._detect_key_from_audio(y=y, sr=sr, librosa=librosa)
        except Exception:
            key = "unknown"

        # Energy via RMS → log-normalized 0-10
        try:
            energy: int | str = self._compute_energy(y=y, librosa=librosa)
        except Exception:
            energy = "unknown"

        return {
            "bpm": bpm,
            "key": key,
            "energy": energy,
            "duration_analyzed": duration_analyzed,
        }

    def _detect_key_from_audio(
        self,
        y: "np.ndarray",
        sr: int,
        librosa: Any,
    ) -> str:
        """
        Detect musical key using chroma features and Krumhansl-Schmuckler profiles.

        Algorithm:
            1. Compute CENS chromagram — 12 pitch-class energy bins over time
            2. Average across frames → pitch class distribution (12,)
            3. Pearson-correlate against all 24 key profiles (12 major + 12 minor,
               each rotated to align with a different root note)
            4. Return key with highest correlation

        chroma_cens is preferred over chroma_stft for key detection: it applies
        log compression and normalization that make it more stable across
        dynamics and tempo variations.

        Args:
            y: Audio time series (numpy array, mono)
            sr: Sample rate in Hz
            librosa: The librosa module (passed in to keep import guard central)

        Returns:
            Key string like "A minor" or "C# major"
        """
        chroma = librosa.feature.chroma_cens(y=y, sr=sr)
        chroma_mean: np.ndarray = np.mean(chroma, axis=1)  # shape (12,)

        best_score = -2.0  # Pearson r ∈ [-1, 1]
        best_key = "C major"  # safe default

        major_arr = np.array(_MAJOR_PROFILE)
        minor_arr = np.array(_MINOR_PROFILE)

        for root in range(12):
            major_profile = np.roll(major_arr, root)
            minor_profile = np.roll(minor_arr, root)

            # errstate suppresses the RuntimeWarning when chroma has zero variance
            # (flat chroma → corrcoef divides by zero → NaN → nan_to_num → 0.0)
            with np.errstate(invalid="ignore"):
                major_r = float(np.nan_to_num(np.corrcoef(chroma_mean, major_profile)[0, 1]))
                minor_r = float(np.nan_to_num(np.corrcoef(chroma_mean, minor_profile)[0, 1]))

            if major_r > best_score:
                best_score = major_r
                best_key = f"{_NOTE_NAMES[root]} major"

            if minor_r > best_score:
                best_score = minor_r
                note = _ENHARMONIC_MINOR.get(_NOTE_NAMES[root], _NOTE_NAMES[root])
                best_key = f"{note} minor"

        return best_key

    def _compute_energy(self, y: "np.ndarray", librosa: Any) -> int | str:
        """
        Compute energy level from RMS, normalized to 0-10 scale (log scale).

        Audio energy is perceptually logarithmic. Approximate RMS ranges:
            Quiet ambient:          0.005 – 0.02  → energy 1-3
            Mid-energy electronic:  0.05 – 0.15   → energy 4-7
            Peak-limited club:      0.15 – 0.35   → energy 8-10

        Mapping: log10([0.001, 0.5]) → [0.0, 10.0], clamped to [0, 10].

        Args:
            y: Audio time series
            librosa: The librosa module (passed in to keep import guard central)

        Returns:
            Integer 0-10, or "unknown" when RMS is zero (silence)
        """
        rms_frames = librosa.feature.rms(y=y)
        rms_mean = float(np.mean(rms_frames))

        if rms_mean <= 0.0:
            return "unknown"

        log_rms = math.log10(max(rms_mean, 1e-6))
        log_min, log_max = -3.0, -0.3
        normalized = (log_rms - log_min) / (log_max - log_min)
        return int(round(max(0.0, min(10.0, normalized * 10.0))))

    # ------------------------------------------------------------------
    # Level 1: filename parsing (unchanged logic, extracted to method)
    # ------------------------------------------------------------------

    def _parse_filename(self, file_path: str) -> dict[str, Any]:
        """
        Extract BPM, key, and energy from filename patterns.

        Always succeeds — individual fields may be "unknown".

        Args:
            file_path: File path or name string

        Returns:
            Dict with keys: bpm, key, energy
        """
        return {
            "bpm": self._extract_bpm(file_path),
            "key": self._extract_key(file_path),
            "energy": self._extract_energy(file_path),
        }

    def _extract_bpm(self, file_path: str) -> int | str:
        """
        Extract BPM from filename.

        Patterns:
            - "128bpm" → 128
            - "128 bpm" → 128
            - "track-128.mp3" → 128
            - "128.5bpm" → 128 (rounds down)

        Args:
            file_path: File path or name

        Returns:
            BPM as int or "unknown"
        """
        patterns = [
            r"(\d+\.?\d*)\s*bpm",  # 128bpm, 128.5 bpm
            r"[-_](\d+)[-_]",  # track-128-key.mp3
            r"^(\d+)[-_]",  # 128_track.mp3
        ]

        filename = Path(file_path).stem.lower()

        for pattern in patterns:
            match = re.search(pattern, filename)
            if match:
                bpm = float(match.group(1))
                if 20 <= bpm <= 300:
                    return int(bpm)

        return "unknown"

    def _extract_key(self, file_path: str) -> str:
        """
        Extract musical key from filename.

        Patterns:
            - "Aminor" → "A minor"
            - "C#major" → "C# major"
            - "Dbm" → "Db minor"
            - "F#maj" → "F# major"

        Args:
            file_path: File path or name

        Returns:
            Musical key or "unknown"
        """
        filename = Path(file_path).stem

        patterns = [
            r"([A-G][#b]?)\s+(major|minor)",  # "A minor", "C# major"
            r"([A-G][#b]?)(major|minor)(?![a-z])",  # "Aminor", "C#major"
            r"([A-G][#b]?)(maj|min|m)(?![a-z])",  # "Amaj", "Bmin", "Cm"
        ]

        for pattern in patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                note = match.group(1)
                quality = match.group(2).lower()
                if quality in ("major", "maj"):
                    quality = "major"
                elif quality in ("minor", "min", "m"):
                    quality = "minor"
                return f"{note} {quality}"

        return "unknown"

    def _extract_energy(self, file_path: str) -> int | str:
        """
        Extract energy level from filename.

        Patterns:
            - "energy8" → 8
            - "high-energy" → 8
            - "low-energy" → 3
            - "medium-energy" → 5

        Args:
            file_path: File path or name

        Returns:
            Energy level (0-10) or "unknown"
        """
        filename = Path(file_path).stem.lower()

        match = re.search(r"energy[-_]?(\d+)", filename)
        if match:
            energy = int(match.group(1))
            if 0 <= energy <= 10:
                return energy

        if "high-energy" in filename or "highenergy" in filename:
            return 8
        if "medium-energy" in filename or "mediumenergy" in filename:
            return 5
        if "low-energy" in filename or "lowenergy" in filename:
            return 3

        return "unknown"

    def _calculate_confidence(self, bpm: int | str, key: str, energy: int | str) -> str:
        """
        Calculate confidence level based on number of fields found.

        Args:
            bpm: Extracted BPM value or "unknown"
            key: Extracted key or "unknown"
            energy: Extracted energy or "unknown"

        Returns:
            "high" | "medium" | "low" | "none"
        """
        found = sum(1 for x in [bpm, key, energy] if x != "unknown")
        if found == 3:
            return "high"
        elif found == 2:
            return "medium"
        elif found == 1:
            return "low"
        return "none"

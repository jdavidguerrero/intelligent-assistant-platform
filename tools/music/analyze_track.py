"""
Analyze track tool — extract BPM, key, energy from audio metadata.

This tool uses DETERMINISTIC analysis (not LLM guessing):
1. Try audio file metadata (ID3 tags, MP3/WAV headers)
2. Try filename parsing (e.g., "track_128bpm_Aminor.mp3")
3. Fall back to "unknown" if no metadata found

NEVER let LLM guess BPM or key — use audio analysis or explicit metadata.
"""

import re
from pathlib import Path

from tools.base import MusicalTool, ToolParameter, ToolResult


class AnalyzeTrack(MusicalTool):
    """
    Extract musical metadata from audio file.

    Analyzes:
        - BPM (beats per minute)
        - Musical key (e.g., "A minor", "C# major")
        - Energy level (0-10 scale)

    Uses deterministic methods:
        1. Parse filename for BPM/key patterns
        2. Check audio file metadata (future: librosa, essentia)
        3. Return "unknown" if not found

    Example:
        tool = AnalyzeTrack()
        result = tool(file_path="track_128bpm_Aminor.mp3")
        # Returns: {"bpm": 128, "key": "A minor", "energy": "unknown"}
    """

    @property
    def name(self) -> str:
        return "analyze_track"

    @property
    def description(self) -> str:
        return (
            "Extract BPM (beats per minute), musical key, and energy level "
            "from an audio file. Uses deterministic metadata parsing — never guesses. "
            "Use this when the user asks about track analysis, tempo detection, "
            "or key identification."
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
        ]

    def execute(self, **kwargs) -> ToolResult:
        """
        Execute track analysis.

        Args:
            file_path: Path to audio file

        Returns:
            ToolResult with BPM, key, energy metadata
        """
        file_path = kwargs["file_path"]

        # Parse filename for musical metadata
        bpm = self._extract_bpm(file_path)
        key = self._extract_key(file_path)
        energy = self._extract_energy(file_path)

        # Build result
        data = {
            "file_path": file_path,
            "bpm": bpm,
            "key": key,
            "energy": energy,
            "confidence": self._calculate_confidence(bpm, key, energy),
        }

        return ToolResult(
            success=True,
            data=data,
            metadata={"source": "filename_parsing", "method": "deterministic"},
        )

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
        # Common BPM patterns
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
                # BPM validation (20-300 range)
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

        # Try multiple patterns in order of specificity
        patterns = [
            # Full words with space: "A minor", "C# major"
            r"([A-G][#b]?)\s+(major|minor)",
            # Full words without space: "Aminor", "C#major"
            r"([A-G][#b]?)(major|minor)(?![a-z])",
            # Abbreviated: "Amaj", "Bmin", "Cm"
            r"([A-G][#b]?)(maj|min|m)(?![a-z])",
        ]

        for pattern in patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                note = match.group(1)
                quality = match.group(2).lower()

                # Normalize quality
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

        # Explicit energy numbers
        match = re.search(r"energy[-_]?(\d+)", filename)
        if match:
            energy = int(match.group(1))
            if 0 <= energy <= 10:
                return energy

        # Qualitative energy descriptors
        if "high-energy" in filename or "highenergy" in filename:
            return 8
        if "medium-energy" in filename or "mediumenergy" in filename:
            return 5
        if "low-energy" in filename or "lowenergy" in filename:
            return 3

        return "unknown"

    def _calculate_confidence(self, bpm: int | str, key: str, energy: int | str) -> str:
        """
        Calculate confidence level based on found metadata.

        Args:
            bpm: Extracted BPM
            key: Extracted key
            energy: Extracted energy

        Returns:
            "high" | "medium" | "low"
        """
        found_count = sum(1 for x in [bpm, key, energy] if x != "unknown")

        if found_count == 3:
            return "high"
        elif found_count == 2:
            return "medium"
        elif found_count == 1:
            return "low"
        else:
            return "none"

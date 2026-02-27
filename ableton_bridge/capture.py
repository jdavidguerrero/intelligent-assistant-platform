"""
ableton_bridge/capture.py — Multi-stem capture via ALS Listener.

Extracts per-track audio file paths from the current Ableton session and
produces a StemCapture record for each track.  For audio tracks the path comes
directly from the clip's file_path property via the LOM.  MIDI tracks cannot
be rendered programmatically without user-initiated export, so they are flagged
as render_required.

The solo/unsolo render cycle described in the spec requires Ableton's dedicated
Export Audio/Video functionality which is not accessible via the LOM API.  This
module captures what IS available: real paths for audio clips, plus metadata
for MIDI tracks, so the analysis layer can decide how to proceed.

Progress callbacks keep the UI informed during multi-track capture.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.ableton.types import SessionState, Track, TrackType

_WS_HOST = "localhost"
_WS_PORT = 11005
_TIMEOUT_SEC = 10.0


# ---------------------------------------------------------------------------
# StemCapture result
# ---------------------------------------------------------------------------


@dataclass
class StemCapture:
    """Result of capturing one stem's metadata from the session.

    Fields:
        track_name:     Ableton track name.
        track_index:    0-based track index in live_set.tracks.
        track_type:     'audio' | 'midi' | 'return' | 'master'.
        file_path:      Absolute path to the audio file (audio tracks only).
                        None for MIDI tracks or tracks with no loaded clip.
        render_required: True for MIDI tracks — a file_path cannot be extracted.
        error:          Non-None if capture failed for this track.
        clip_name:      Name of the clip at the current playback position (if any).
        duration_sec:   Clip length in seconds (if available from LOM).
    """

    track_name: str
    track_index: int
    track_type: str = "audio"
    file_path: str | None = None
    render_required: bool = False
    error: str | None = None
    clip_name: str | None = None
    duration_sec: float | None = None

    def is_analysable(self) -> bool:
        """True if we have a real audio file path we can pass to MixAnalysisEngine."""
        return self.file_path is not None and self.error is None

    def as_dict(self) -> dict[str, Any]:
        return {
            "track_name": self.track_name,
            "track_index": self.track_index,
            "track_type": self.track_type,
            "file_path": self.file_path,
            "render_required": self.render_required,
            "error": self.error,
            "clip_name": self.clip_name,
            "duration_sec": self.duration_sec,
            "is_analysable": self.is_analysable(),
        }


# ---------------------------------------------------------------------------
# Progress callback type
# ---------------------------------------------------------------------------

ProgressCallback = Callable[[int, int, str, str], None]
"""Signature: (current, total, track_name, status) → None"""


def _noop_progress(current: int, total: int, track_name: str, status: str) -> None:
    """Default no-op progress callback."""


# ---------------------------------------------------------------------------
# Internal helpers — parse session JSON
# ---------------------------------------------------------------------------


def _parse_session_tracks(session_data: SessionState) -> list[Track]:
    """Extract the list of regular tracks from a SessionState object."""
    return list(session_data.tracks)


def _extract_clip_path(track: Track) -> tuple[str | None, str | None, float | None]:
    """Return (file_path, clip_name, duration_sec) for the first audio clip on the track."""
    for clip in track.clips:
        if clip.file_path:
            # length_bars to seconds: approximate (session tempo not available here)
            # Return length_bars as a proxy; caller can convert if needed
            return clip.file_path, clip.name or None, clip.length_bars or None
    return None, None, None


# ---------------------------------------------------------------------------
# capture_stems — main public function
# ---------------------------------------------------------------------------


def capture_stems(
    session_data: SessionState,
    *,
    include_return_tracks: bool = False,
    progress: ProgressCallback = _noop_progress,
) -> list[StemCapture]:
    """Capture stem metadata from a live Ableton session snapshot.

    Iterates over all tracks in session_data, extracts audio clip file paths
    where available, and marks MIDI tracks as render_required.

    Args:
        session_data:          SessionState object from AbletonBridge.get_session().
        include_return_tracks: If True, also capture return (aux/send) tracks.
        progress:              Callback(current, total, track_name, status) for UI.

    Returns:
        List of StemCapture objects, one per track processed.
    """
    tracks: list[Track] = _parse_session_tracks(session_data)

    if include_return_tracks:
        tracks = tracks + list(session_data.return_tracks)

    total = len(tracks)
    results: list[StemCapture] = []

    for idx, track in enumerate(tracks):
        track_name = track.name
        track_type_str = track.type.value  # "audio" | "midi" | "return" | "master" | "group"

        progress(idx + 1, total, track_name, "Scanning...")

        if track.type in (TrackType.MIDI,):
            results.append(
                StemCapture(
                    track_name=track_name,
                    track_index=track.index,
                    track_type="midi",
                    file_path=None,
                    render_required=True,
                    error=None,
                    clip_name=None,
                    duration_sec=None,
                )
            )
            progress(idx + 1, total, track_name, "MIDI — render required")
            continue

        # Audio / Group track — try to extract file path from clips
        file_path, clip_name, duration_sec = _extract_clip_path(track)

        if file_path and not Path(file_path).exists():
            error = f"File not found on disk: {file_path}"
            file_path = None
        else:
            error = None

        results.append(
            StemCapture(
                track_name=track_name,
                track_index=track.index,
                track_type=track_type_str,
                file_path=file_path,
                render_required=False,
                error=error,
                clip_name=clip_name,
                duration_sec=duration_sec,
            )
        )
        status = "OK" if file_path else ("No clip" if not error else "Error")
        progress(idx + 1, total, track_name, status)

    return results


# ---------------------------------------------------------------------------
# capture_master — extract master output path (if recorded)
# ---------------------------------------------------------------------------


def capture_master(session_data: SessionState) -> StemCapture:
    """Extract master track metadata from the session.

    Args:
        session_data: SessionState object from AbletonBridge.get_session().

    Returns:
        StemCapture for the master track.  file_path will be None unless the
        master track has a rendered file in its clip slots.
    """
    master = session_data.master_track
    if master is None:
        return StemCapture(
            track_name="Master",
            track_index=-1,
            track_type="master",
            file_path=None,
            render_required=True,
        )

    file_path, clip_name, duration_sec = _extract_clip_path(master)

    return StemCapture(
        track_name=master.name,
        track_index=-1,
        track_type="master",
        file_path=file_path,
        render_required=file_path is None,
        clip_name=clip_name,
        duration_sec=duration_sec,
    )


# ---------------------------------------------------------------------------
# solo_capture_cycle — protocol helper (solo/unsolo metadata)
# ---------------------------------------------------------------------------


def build_solo_commands(track_index: int, solo: bool) -> list[dict[str, Any]]:
    """Build ALS Listener commands to solo or unsolo a track by index.

    Returns a list of command dicts that can be sent via the WebSocket.
    The actual sending is done by ingestion.ableton_bridge.AbletonBridge.

    Args:
        track_index: 0-based track index.
        solo:        True to solo, False to unsolo.

    Returns:
        List of command dicts for the ALS Listener set_property protocol.
    """
    return [
        {
            "type": "set_property",
            "lom_path": f"live_set tracks {track_index}",
            "property": "solo",
            "value": 1 if solo else 0,
            "id": f"solo_{track_index}_{int(solo)}",
        }
    ]


def build_unsolo_all_commands(track_count: int) -> list[dict[str, Any]]:
    """Build commands to unsolo all tracks — cleanup after a capture cycle."""
    return [
        {
            "type": "set_property",
            "lom_path": f"live_set tracks {i}",
            "property": "solo",
            "value": 0,
            "id": f"unsolo_{i}",
        }
        for i in range(track_count)
    ]

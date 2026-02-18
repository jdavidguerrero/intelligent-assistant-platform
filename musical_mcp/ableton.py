"""
musical_mcp/ableton.py — OSC bridge to Ableton Live via Max for Live.

Sends chord data to a Max for Live device listening on localhost:11001.
The M4L device receives the notes and inserts them into the selected clip.

Protocol (custom, not AbletonOSC):
    /chord/clear               — clear existing notes in clip
    /chord/note i i f f        — pitch velocity start_beat duration_beats
    /chord/commit i f          — note_count clip_length_beats → triggers insert

Why UDP/OSC instead of AbletonOSC?
    AbletonOSC requires installing a Remote Script. Our M4L device is
    self-contained — it opens its own UDP receiver, zero Ableton setup needed
    beyond dragging the .amxd onto a MIDI track.

Port convention:
    11001  MCP → M4L (our device)   [send]
    11002  M4L → MCP (ack/errors)   [receive, optional]
"""

from __future__ import annotations

import logging
import socket
import time
from typing import Any

from core.midi import MidiNote, chords_to_midi_notes, total_clip_beats

logger = logging.getLogger(__name__)

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 11001
_SOCKET_TIMEOUT = 2.0


# ---------------------------------------------------------------------------
# Low-level OSC packet builder (no pythonosc dependency at module level)
# ---------------------------------------------------------------------------


def _osc_string(s: str) -> bytes:
    """Encode a string as OSC string (null-terminated, 4-byte padded)."""
    b = s.encode("utf-8") + b"\x00"
    pad = (4 - len(b) % 4) % 4
    return b + b"\x00" * pad


def _osc_int(i: int) -> bytes:
    """Encode an integer as OSC int32 (big-endian)."""
    return i.to_bytes(4, "big", signed=True)


def _osc_float(f: float) -> bytes:
    """Encode a float as OSC float32 (big-endian IEEE 754)."""
    import struct

    return struct.pack(">f", f)


def _build_osc_message(address: str, *args: Any) -> bytes:
    """
    Build a minimal OSC 1.0 message.

    Supports int (i), float (f), and string (s) arguments.
    """
    msg = _osc_string(address)

    type_tag = ","
    encoded_args = b""
    for arg in args:
        if isinstance(arg, bool):
            raise TypeError("Use int 0/1 instead of bool for OSC")
        elif isinstance(arg, int):
            type_tag += "i"
            encoded_args += _osc_int(arg)
        elif isinstance(arg, float):
            type_tag += "f"
            encoded_args += _osc_float(arg)
        elif isinstance(arg, str):
            type_tag += "s"
            encoded_args += _osc_string(arg)
        else:
            raise TypeError(f"Unsupported OSC arg type {type(arg)}: {arg!r}")

    msg += _osc_string(type_tag)
    msg += encoded_args
    return msg


# ---------------------------------------------------------------------------
# OSC sender
# ---------------------------------------------------------------------------


class AbletonOscSender:
    """
    Sends OSC messages to a Max for Live device via UDP.

    Usage:
        sender = AbletonOscSender()
        sender.send_chords(["Am", "F", "C", "G"], beats_per_chord=4.0)
    """

    def __init__(self, host: str = _DEFAULT_HOST, port: int = _DEFAULT_PORT) -> None:
        """
        Initialize the OSC sender.

        Args:
            host: IP address of the M4L device (default localhost)
            port: UDP port the M4L device is listening on (default 11001)
        """
        self._host = host
        self._port = port

    def _send(self, address: str, *args: Any) -> None:
        """Send a single OSC message via UDP."""
        msg = _build_osc_message(address, *args)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(_SOCKET_TIMEOUT)
            sock.sendto(msg, (self._host, self._port))

    def send_chords(
        self,
        chord_names: list[str],
        beats_per_chord: float = 4.0,
        velocity: int = 90,
        octave: int = 4,
        bpm: float = 120.0,
    ) -> dict[str, Any]:
        """
        Send a chord progression to the M4L device.

        Sends /chord/clear, then one /chord/note per MIDI note,
        then /chord/commit to trigger clip insertion.

        Args:
            chord_names: e.g. ["Am", "F", "C", "G"]
            beats_per_chord: bars × beats_per_bar (default 4 = 1 bar at 4/4)
            velocity: MIDI velocity 1-127 (default 90)
            octave: root octave for voicings (default 4)
            bpm: session tempo hint (informational, not used to time notes)

        Returns:
            dict with status, note_count, clip_beats, latency_ms

        Raises:
            ValueError: if chord_names is empty or chords can't be resolved
            OSError: if UDP send fails (M4L device not running)
        """
        t_start = time.perf_counter()

        notes: list[MidiNote] = chords_to_midi_notes(
            chord_names,
            beats_per_chord=beats_per_chord,
            velocity=velocity,
            octave=octave,
        )
        clip_beats = total_clip_beats(chord_names, beats_per_chord)

        # 1. Clear previous notes
        self._send("/chord/clear")

        # 2. Send each note
        for note in notes:
            self._send(
                "/chord/note",
                note.pitch,
                note.velocity,
                float(note.start_beat),
                float(note.duration_beats),
            )

        # 3. Commit — triggers clip insert in M4L
        self._send("/chord/commit", len(notes), float(clip_beats))

        latency_ms = (time.perf_counter() - t_start) * 1000

        logger.info(
            "Sent %d notes to Ableton (%d chords × %.0f beats) in %.1fms",
            len(notes),
            len(chord_names),
            beats_per_chord,
            latency_ms,
        )

        return {
            "status": "sent",
            "chord_count": len(chord_names),
            "note_count": len(notes),
            "clip_beats": clip_beats,
            "latency_ms": round(latency_ms, 1),
        }

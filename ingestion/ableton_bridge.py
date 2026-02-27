"""ingestion/ableton_bridge.py — WebSocket client for the ALS Listener M4L device.

This module is the I/O boundary between the Python platform and Ableton Live.
All network calls live here; core/ stays pure.

Architecture
────────────
::

    Ableton Live
        └── ALS Listener (M4L device, port 11005)
                │   WebSocket (ws://localhost:11005)
                ▼
    ingestion/ableton_bridge.py (this module)
        │
        ├── SessionState  ← deserialized from JSON
        └── LOMCommand    → serialized to JSON

Connection model
────────────────
``AbletonBridge`` uses a *stateless-per-call* pattern: each public method
opens a fresh WebSocket connection, performs the operation, and closes.  This
avoids threading complexity (no background threads, no asyncio event loops
running continuously) while keeping latency acceptable for conversational use
(< 200 ms per call on localhost).

Session caching
───────────────
``get_session()`` caches the last snapshot in ``_session_cache``.  The cache
is invalidated by ``invalidate()`` or automatically when the bridge receives a
new ``session_state`` message.  This means repeated reads in the same
conversation turn are fast (< 1 ms) without network I/O.

Dependency
──────────
Requires ``websocket-client`` (``pip install websocket-client``).
Deferred import so the rest of the platform works without it installed.

Error handling
──────────────
``ConnectionError`` is raised when Ableton is not running or ALS Listener is
not loaded.  All public methods surface this to callers — the MCP tools catch
it and return user-facing error messages.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from core.ableton.types import (
    Clip,
    Device,
    LOMCommand,
    Parameter,
    SessionState,
    Track,
    TrackType,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_HOST: str = "localhost"
_DEFAULT_PORT: int = 11005
_CONNECT_TIMEOUT: float = 3.0  # seconds
_READ_TIMEOUT: float = 5.0  # seconds
_BATCH_TIMEOUT: float = 10.0  # seconds


# ---------------------------------------------------------------------------
# JSON → domain type deserializers
# ---------------------------------------------------------------------------


def _parse_parameter(
    data: dict[str, Any], track_idx: int, dev_idx: int, param_idx: int
) -> Parameter:
    """Deserialise a single parameter dict from the ALS Listener JSON."""
    lom_path = data.get(
        "lom_path",
        f"live_set tracks {track_idx} devices {dev_idx} parameters {param_idx}",
    )
    return Parameter(
        name=str(data.get("name", f"Parameter {param_idx}")),
        value=float(data.get("value", 0.0)),
        min_value=float(data.get("min", 0.0)),
        max_value=float(data.get("max", 1.0)),
        default_value=float(data.get("default", 0.0)),
        display_value=str(data.get("display", "")),
        lom_path=lom_path,
        index=param_idx,
        is_quantized=bool(data.get("is_quantized", False)),
    )


def _parse_device(data: dict[str, Any], track_idx: int, dev_idx: int) -> Device:
    """Deserialise a device dict from the ALS Listener JSON."""
    lom_path = data.get("lom_path", f"live_set tracks {track_idx} devices {dev_idx}")
    params = tuple(
        _parse_parameter(p, track_idx, dev_idx, pi)
        for pi, p in enumerate(data.get("parameters", []))
    )
    return Device(
        name=str(data.get("name", f"Device {dev_idx}")),
        class_name=str(data.get("class_name", "")),
        is_active=bool(data.get("is_active", True)),
        parameters=params,
        lom_path=lom_path,
        index=dev_idx,
    )


def _parse_clip(data: dict[str, Any], track_idx: int, slot_idx: int) -> Clip:
    """Deserialise a clip dict from the ALS Listener JSON."""
    lom_path = data.get("lom_path", f"live_set tracks {track_idx} clip_slots {slot_idx} clip")
    notes = tuple(
        {
            "pitch": int(n["pitch"]),
            "start": float(n["start"]),
            "duration": float(n["duration"]),
            "velocity": int(n.get("velocity", 100)),
        }
        for n in data.get("notes", [])
    )
    return Clip(
        name=str(data.get("name", "")),
        length_bars=float(data.get("length", 0.0)),
        is_playing=bool(data.get("is_playing", False)),
        is_triggered=bool(data.get("is_triggered", False)),
        is_midi=bool(data.get("is_midi", False)),
        lom_path=lom_path,
        color=int(data.get("color", 0)),
        notes=notes,
    )


def _raw_volume_to_db(raw: float) -> float:
    """Convert Ableton's 0–1 volume raw value to dB.

    Ableton's volume fader is not linear in dB.  The reference point is
    raw = 0.85 ≈ 0 dB (unity gain).  Above unity is slightly boosted.
    Below 0 the linear approximation diverges.

    Simplified conversion: 20 * log10(raw / 0.85)  clamped at -80 dB.
    """
    import math

    if raw <= 0:
        return -80.0
    db = 20.0 * math.log10(raw / 0.85)
    return max(-80.0, db)


def _parse_track(data: dict[str, Any], track_idx: int, is_return: bool = False) -> Track:
    """Deserialise a track dict from the ALS Listener JSON."""
    key = "return_tracks" if is_return else "tracks"
    lom_path = data.get("lom_path", f"live_set {key} {track_idx}")

    raw_type = str(data.get("type", "audio"))
    try:
        ttype = TrackType(raw_type)
    except ValueError:
        ttype = TrackType.AUDIO

    devices = tuple(_parse_device(d, track_idx, di) for di, d in enumerate(data.get("devices", [])))
    clips = tuple(
        _parse_clip(c, track_idx, ci)
        for ci, c in enumerate(data.get("clips", []))
        if c  # ALS Listener sends null for empty clip slots
    )

    volume_raw = float(data.get("volume", 0.85))
    pan_raw = float(data.get("pan", 0.5))

    return Track(
        name=str(data.get("name", f"Track {track_idx}")),
        index=track_idx,
        type=ttype,
        arm=bool(data.get("arm", False)),
        solo=bool(data.get("solo", False)),
        mute=bool(data.get("mute", False)),
        volume_db=_raw_volume_to_db(volume_raw),
        pan=round((pan_raw - 0.5) * 2.0, 3),  # 0–1 → -1..+1
        devices=devices,
        clips=clips,
        lom_path=lom_path,
        color=int(data.get("color", 0)),
        volume_lom_id=int(data.get("volume_lom_id", 0)),
    )


def _parse_session(data: dict[str, Any]) -> SessionState:
    """Deserialise a full session state dict from the ALS Listener JSON."""
    tracks = tuple(_parse_track(t, i) for i, t in enumerate(data.get("tracks", [])))
    return_tracks = tuple(
        _parse_track(t, i, is_return=True) for i, t in enumerate(data.get("return_tracks", []))
    )

    master_data = data.get("master_track")
    master_track: Track | None = None
    if master_data:
        master_track = _parse_track(master_data, 0)

    return SessionState(
        tracks=tracks,
        return_tracks=return_tracks,
        master_track=master_track,
        tempo=float(data.get("tempo", 120.0)),
        time_sig_numerator=int(data.get("time_sig_numerator", 4)),
        time_sig_denominator=int(data.get("time_sig_denominator", 4)),
        is_playing=bool(data.get("is_playing", False)),
        current_song_time=float(data.get("current_song_time", 0.0)),
        scene_count=int(data.get("scene_count", 0)),
        timestamp=time.time(),
    )


# ---------------------------------------------------------------------------
# AbletonBridge
# ---------------------------------------------------------------------------


@dataclass
class AbletonBridge:
    """WebSocket client that talks to the ALS Listener M4L device.

    Usage::

        bridge = AbletonBridge()
        session = bridge.get_session()
        track = find_track(session, "Pads")
        eq = find_eq(track)
        cmds = set_eq_band(track, eq, band=3, freq_hz=280, gain_db=-3.0, q=2.0)
        bridge.send_commands(cmds)
    """

    host: str = _DEFAULT_HOST
    port: int = _DEFAULT_PORT
    connect_timeout: float = _CONNECT_TIMEOUT
    read_timeout: float = _READ_TIMEOUT

    _session_cache: SessionState | None = field(default=None, init=False, repr=False)
    _cache_time: float = field(default=0.0, init=False, repr=False)
    _cache_ttl: float = field(default=5.0, init=False, repr=False)
    """Session cache TTL in seconds.  0 = no caching."""

    @property
    def ws_url(self) -> str:
        """WebSocket URL for the ALS Listener."""
        return f"ws://{self.host}:{self.port}"

    def _open(self) -> Any:
        """Open a WebSocket connection to the ALS Listener.

        Returns:
            ``websocket.WebSocket`` instance (from ``websocket-client``).

        Raises:
            ConnectionError: If Ableton / ALS Listener is not reachable.
            ImportError:     If ``websocket-client`` is not installed.
        """
        try:
            import websocket  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "websocket-client is required for Ableton bridge. "
                "Install with: pip install websocket-client"
            ) from exc

        try:
            ws = websocket.WebSocket()
            ws.settimeout(self.connect_timeout)
            ws.connect(self.ws_url)
            return ws
        except OSError as exc:
            raise ConnectionError(
                f"Cannot connect to ALS Listener at {self.ws_url}. "
                "Make sure Ableton is open and the ALS Listener M4L device is loaded. "
                f"({exc})"
            ) from exc

    def _recv_json(self, ws: Any, timeout: float | None = None) -> dict[str, Any]:
        """Receive and parse the next JSON message from the WebSocket.

        Args:
            ws:      Open WebSocket connection.
            timeout: Override read timeout (seconds).

        Returns:
            Parsed JSON dict.

        Raises:
            ConnectionError: On websocket error.
        """
        try:
            import websocket  # type: ignore[import]

            if timeout is not None:
                ws.settimeout(timeout)
            raw = ws.recv()
            return json.loads(raw)
        except websocket.WebSocketTimeoutException as exc:
            raise ConnectionError(
                f"ALS Listener did not respond within {timeout or self.read_timeout}s"
            ) from exc
        except Exception as exc:
            raise ConnectionError(f"WebSocket read error: {exc}") from exc

    def invalidate(self) -> None:
        """Clear the session cache, forcing the next ``get_session()`` to fetch live data."""
        self._session_cache = None
        self._cache_time = 0.0

    # ── Public API ──────────────────────────────────────────────────────────

    def get_session(self, *, force_refresh: bool = False) -> SessionState:
        """Fetch the current session state from the ALS Listener.

        Uses a 5-second in-memory cache to avoid redundant WebSocket calls
        within the same conversation turn.

        Args:
            force_refresh: Bypass the cache and fetch live data.

        Returns:
            :class:`SessionState` snapshot.

        Raises:
            ConnectionError: If Ableton / ALS Listener is unreachable.
        """
        now = time.monotonic()
        if (
            not force_refresh
            and self._session_cache is not None
            and (now - self._cache_time) < self._cache_ttl
        ):
            return self._session_cache

        ws = self._open()
        try:
            # ALS Listener sends ``session_state`` immediately on connect
            for _ in range(10):  # skip ping / delta messages until we see session_state
                msg = self._recv_json(ws, timeout=self.read_timeout)
                if msg.get("type") == "session_state":
                    session = _parse_session(msg["data"])
                    self._session_cache = session
                    self._cache_time = now
                    return session
            raise ConnectionError("ALS Listener connected but did not send session_state")
        finally:
            ws.close()

    def send_command(self, command: LOMCommand) -> dict[str, Any]:
        """Send a single LOM command to the ALS Listener.

        Args:
            command: :class:`LOMCommand` to execute.

        Returns:
            Acknowledgement dict from ALS Listener (``{"type": "ack", ...}``).

        Raises:
            ConnectionError: If Ableton is unreachable.
        """
        return self.send_commands([command])[0]

    def send_commands(self, commands: list[LOMCommand]) -> list[dict[str, Any]]:
        """Send a batch of LOM commands to the ALS Listener.

        Commands are sent sequentially over a single connection.  Each command
        receives an individual ``ack`` message from ALS Listener.

        Args:
            commands: List of :class:`LOMCommand` to execute.

        Returns:
            List of acknowledgement dicts (one per command).

        Raises:
            ConnectionError: If Ableton is unreachable or any command fails.
            ValueError:      If ``commands`` is empty.
        """
        if not commands:
            raise ValueError("send_commands() requires at least one command")

        ws = self._open()
        acks: list[dict[str, Any]] = []
        try:
            ws.settimeout(_BATCH_TIMEOUT)
            for cmd in commands:
                payload = json.dumps(cmd.to_dict())
                ws.send(payload)
                ack = self._recv_json(ws, timeout=_BATCH_TIMEOUT)
                acks.append(ack)
                # Invalidate session cache after writes
                self.invalidate()
        finally:
            ws.close()

        return acks

    def ping(self) -> float:
        """Check connectivity and measure round-trip latency to ALS Listener.

        Returns:
            Round-trip latency in milliseconds.

        Raises:
            ConnectionError: If Ableton is unreachable.
        """
        ws = self._open()
        try:
            t0 = time.perf_counter()
            ws.send(json.dumps({"type": "ping"}))
            msg = self._recv_json(ws, timeout=2.0)
            latency_ms = (time.perf_counter() - t0) * 1000
            if msg.get("type") != "pong":
                raise ConnectionError(f"Expected pong, got {msg.get('type')!r}")
            return latency_ms
        finally:
            ws.close()

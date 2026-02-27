"""
tests/test_ableton_osc.py — Unit tests for musical_mcp/ableton.py

Tests cover:
- OSC packet builder (_osc_string, _osc_int, _osc_float, _build_osc_message)
- AbletonOscSender.send_chords: correct message sequence, UDP send calls, return dict
- Error handling: OSError from UDP, ValueError from bad chords
- Message count / ordering verification (clear → N notes → commit)
"""

from __future__ import annotations

import socket
import struct
from unittest.mock import MagicMock, patch

import pytest

from musical_mcp.ableton import (
    AbletonOscSender,
    _build_osc_message,
    _osc_float,
    _osc_int,
    _osc_string,
)

# ---------------------------------------------------------------------------
# Low-level OSC encoding helpers
# ---------------------------------------------------------------------------


class TestOscString:
    def test_simple_string_null_terminated(self) -> None:
        result = _osc_string("hi")
        # "hi\0" = 3 bytes → padded to 4 → b"hi\x00\x00"
        assert result == b"hi\x00\x00"

    def test_4_char_string_padded_to_8(self) -> None:
        # "test\0" = 5 bytes → padded to 8
        result = _osc_string("test")
        assert result == b"test\x00\x00\x00\x00"

    def test_length_multiple_of_4(self) -> None:
        for s in ["a", "ab", "abc", "abcd", "abcde", "abcdef"]:
            assert len(_osc_string(s)) % 4 == 0

    def test_empty_string(self) -> None:
        result = _osc_string("")
        # "\0" = 1 byte → padded to 4
        assert result == b"\x00\x00\x00\x00"

    def test_address_encoding(self) -> None:
        result = _osc_string("/chord/clear")
        assert result.startswith(b"/chord/clear\x00")
        assert len(result) % 4 == 0


class TestOscInt:
    def test_zero(self) -> None:
        assert _osc_int(0) == b"\x00\x00\x00\x00"

    def test_one(self) -> None:
        assert _osc_int(1) == b"\x00\x00\x00\x01"

    def test_big_endian(self) -> None:
        # 256 = 0x00000100
        assert _osc_int(256) == b"\x00\x00\x01\x00"

    def test_negative(self) -> None:
        # -1 in big-endian two's complement = b"\xff\xff\xff\xff"
        assert _osc_int(-1) == b"\xff\xff\xff\xff"

    def test_length_always_4(self) -> None:
        for i in [0, 1, 127, 1000, -1]:
            assert len(_osc_int(i)) == 4


class TestOscFloat:
    def test_length_always_4(self) -> None:
        for f in [0.0, 1.0, -1.0, 3.14, 120.0]:
            assert len(_osc_float(f)) == 4

    def test_round_trip(self) -> None:
        for f in [0.0, 1.0, 4.5, 90.0, 120.0]:
            encoded = _osc_float(f)
            decoded = struct.unpack(">f", encoded)[0]
            assert abs(decoded - f) < 1e-5

    def test_big_endian_encoding(self) -> None:
        # 1.0 IEEE 754: 0x3F800000
        assert _osc_float(1.0) == b"\x3f\x80\x00\x00"


class TestBuildOscMessage:
    def test_clear_message_no_args(self) -> None:
        msg = _build_osc_message("/chord/clear")
        # Must contain the address string
        assert b"/chord/clear" in msg
        # Type tag string must be just ","
        assert b",\x00\x00\x00" in msg

    def test_note_message_structure(self) -> None:
        msg = _build_osc_message("/chord/note", 69, 90, 0.0, 3.6)
        assert b"/chord/note" in msg
        # Type tag = ",iiff"
        assert b",iiff" in msg

    def test_commit_message_structure(self) -> None:
        msg = _build_osc_message("/chord/commit", 12, 16.0)
        assert b"/chord/commit" in msg
        # Type tag = ",if"
        assert b",if" in msg

    def test_message_length_multiple_of_4(self) -> None:
        for msg in [
            _build_osc_message("/chord/clear"),
            _build_osc_message("/chord/note", 69, 90, 0.0, 3.6),
            _build_osc_message("/chord/commit", 12, 16.0),
        ]:
            assert len(msg) % 4 == 0

    def test_bool_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="Use int 0/1"):
            _build_osc_message("/test", True)

    def test_unsupported_type_raises(self) -> None:
        with pytest.raises(TypeError, match="Unsupported OSC arg type"):
            _build_osc_message("/test", [1, 2, 3])

    def test_string_arg(self) -> None:
        msg = _build_osc_message("/test", "hello")
        assert b",s" in msg
        assert b"hello" in msg


# ---------------------------------------------------------------------------
# AbletonOscSender
# ---------------------------------------------------------------------------


class TestAbletonOscSenderDefaults:
    def test_default_host_port(self) -> None:
        sender = AbletonOscSender()
        assert sender._host == "127.0.0.1"
        assert sender._port == 11001

    def test_custom_host_port(self) -> None:
        sender = AbletonOscSender(host="192.168.1.5", port=9000)
        assert sender._host == "192.168.1.5"
        assert sender._port == 9000


class TestAbletonOscSenderSendChords:
    """send_chords() is tested by mocking socket.socket so no UDP is needed."""

    def _make_sender_with_mock_socket(self):
        """Returns (sender, mock_sendto_calls) — mock_sendto_calls accumulates args."""
        sent = []

        mock_sock = MagicMock()
        mock_sock.sendto.side_effect = lambda data, addr: sent.append((data, addr))
        mock_sock.__enter__ = lambda s: s
        mock_sock.__exit__ = MagicMock(return_value=False)

        return AbletonOscSender(), mock_sock, sent

    @patch("socket.socket")
    def test_message_count_am_f_c_g(self, mock_socket_cls) -> None:
        sent = []
        sock = MagicMock()
        sock.sendto.side_effect = lambda data, addr: sent.append(data)
        sock.__enter__ = lambda s: s
        sock.__exit__ = MagicMock(return_value=False)
        mock_socket_cls.return_value = sock

        sender = AbletonOscSender()
        sender.send_chords(["Am", "F", "C", "G"])

        # 1 clear + 12 notes (3 per chord × 4 chords) + 1 commit = 14 messages
        assert len(sent) == 14

    @patch("socket.socket")
    def test_first_message_is_clear(self, mock_socket_cls) -> None:
        sent = []
        sock = MagicMock()
        sock.sendto.side_effect = lambda data, addr: sent.append(data)
        sock.__enter__ = lambda s: s
        sock.__exit__ = MagicMock(return_value=False)
        mock_socket_cls.return_value = sock

        sender = AbletonOscSender()
        sender.send_chords(["Am"])

        assert b"/chord/clear" in sent[0]

    @patch("socket.socket")
    def test_last_message_is_commit(self, mock_socket_cls) -> None:
        sent = []
        sock = MagicMock()
        sock.sendto.side_effect = lambda data, addr: sent.append(data)
        sock.__enter__ = lambda s: s
        sock.__exit__ = MagicMock(return_value=False)
        mock_socket_cls.return_value = sock

        sender = AbletonOscSender()
        sender.send_chords(["Am"])

        assert b"/chord/commit" in sent[-1]

    @patch("socket.socket")
    def test_middle_messages_are_notes(self, mock_socket_cls) -> None:
        sent = []
        sock = MagicMock()
        sock.sendto.side_effect = lambda data, addr: sent.append(data)
        sock.__enter__ = lambda s: s
        sock.__exit__ = MagicMock(return_value=False)
        mock_socket_cls.return_value = sock

        sender = AbletonOscSender()
        sender.send_chords(["Am"])  # Am = 3 notes

        # Messages: [clear, note, note, note, commit]
        assert len(sent) == 5
        for msg in sent[1:4]:
            assert b"/chord/note" in msg

    @patch("socket.socket")
    def test_return_dict_structure(self, mock_socket_cls) -> None:
        sock = MagicMock()
        sock.sendto = MagicMock()
        sock.__enter__ = lambda s: s
        sock.__exit__ = MagicMock(return_value=False)
        mock_socket_cls.return_value = sock

        sender = AbletonOscSender()
        result = sender.send_chords(["Am", "F", "C", "G"])

        assert result["status"] == "sent"
        assert result["chord_count"] == 4
        assert result["note_count"] == 12
        assert result["clip_beats"] == 16.0
        assert "latency_ms" in result
        assert isinstance(result["latency_ms"], float)

    @patch("socket.socket")
    def test_am7_produces_4_note_messages(self, mock_socket_cls) -> None:
        sent = []
        sock = MagicMock()
        sock.sendto.side_effect = lambda data, addr: sent.append(data)
        sock.__enter__ = lambda s: s
        sock.__exit__ = MagicMock(return_value=False)
        mock_socket_cls.return_value = sock

        sender = AbletonOscSender()
        sender.send_chords(["Am7"])

        # clear + 4 notes + commit = 6
        assert len(sent) == 6

    @patch("socket.socket")
    def test_custom_beats_per_chord(self, mock_socket_cls) -> None:
        sock = MagicMock()
        sock.sendto = MagicMock()
        sock.__enter__ = lambda s: s
        sock.__exit__ = MagicMock(return_value=False)
        mock_socket_cls.return_value = sock

        sender = AbletonOscSender()
        result = sender.send_chords(["Am", "F"], beats_per_chord=2.0)

        assert result["clip_beats"] == 4.0

    @patch("socket.socket")
    def test_udp_dest_is_localhost_11001(self, mock_socket_cls) -> None:
        destinations = []
        sock = MagicMock()
        sock.sendto.side_effect = lambda data, addr: destinations.append(addr)
        sock.__enter__ = lambda s: s
        sock.__exit__ = MagicMock(return_value=False)
        mock_socket_cls.return_value = sock

        sender = AbletonOscSender()
        sender.send_chords(["Am"])

        assert all(addr == ("127.0.0.1", 11001) for addr in destinations)

    @patch("socket.socket")
    def test_uses_udp_socket(self, mock_socket_cls) -> None:
        sock = MagicMock()
        sock.sendto = MagicMock()
        sock.__enter__ = lambda s: s
        sock.__exit__ = MagicMock(return_value=False)
        mock_socket_cls.return_value = sock

        sender = AbletonOscSender()
        sender.send_chords(["C"])

        mock_socket_cls.assert_called_with(socket.AF_INET, socket.SOCK_DGRAM)

    def test_empty_chord_list_raises(self) -> None:
        sender = AbletonOscSender()
        with pytest.raises(ValueError):
            sender.send_chords([])

    def test_unknown_chord_raises(self) -> None:
        sender = AbletonOscSender()
        # "Xm" has an unknown root
        with pytest.raises(ValueError):
            sender.send_chords(["Xm"])

    @patch("socket.socket")
    def test_oserror_propagates(self, mock_socket_cls) -> None:
        sock = MagicMock()
        sock.sendto.side_effect = OSError("Connection refused")
        sock.__enter__ = lambda s: s
        sock.__exit__ = MagicMock(return_value=False)
        mock_socket_cls.return_value = sock

        sender = AbletonOscSender()
        with pytest.raises(OSError):
            sender.send_chords(["Am"])

    @patch("socket.socket")
    def test_8_chord_progression_message_count(self, mock_socket_cls) -> None:
        sent = []
        sock = MagicMock()
        sock.sendto.side_effect = lambda data, addr: sent.append(data)
        sock.__enter__ = lambda s: s
        sock.__exit__ = MagicMock(return_value=False)
        mock_socket_cls.return_value = sock

        chords = ["Am", "F", "C", "G", "Am", "F", "C", "G"]
        sender = AbletonOscSender()
        result = sender.send_chords(chords)

        # 1 clear + 8×3 notes + 1 commit = 26 messages
        assert len(sent) == 26
        assert result["chord_count"] == 8
        assert result["note_count"] == 24
        assert result["clip_beats"] == 32.0
